# -*- coding: utf-8 -*-
"""AI 校对流水线：默认通过 Codex/ChatGPT 审核天邈中文。

流程：
    corpus.jsonl + glossary/terms.json + prompt/*.md
        -> 稳定批次快照 -> Codex 或 OpenAI 兼容 API
        -> JSON Schema / id / 术语 / 占位符硬校验
        -> data/review/batch_{i}.json + summary.json + run_manifest.json

Codex 后端（默认）：复用本机 ``codex login`` 的 ChatGPT 登录，不需要 API key。
API 后端（备用）：保留原有 OpenAI 兼容 ``/chat/completions`` 调用。

断点规则：只有 input_hash 与 config_hash 都一致、且内容重新校验通过的批次
才会跳过。过期或损坏结果会改名保留，再重新生成。
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_REVIEW_DIR = os.path.join(ROOT, 'data', 'review')
DEFAULT_SCHEMA = os.path.join(ROOT, 'tools', 'review_schema.json')
LOCAL_CODEX_COMMAND = os.path.join(
    ROOT, 'tools', '.codex-cli', 'node_modules', '.bin',
    'codex.cmd' if os.name == 'nt' else 'codex')
PIPELINE_VERSION = 8

LABEL_TERM_FIELDS = {
    'm_name', 'm_itemname', 'm_pluralitemname', 'm_locationname',
    'm_targetname', 'm_interacttext', 'm_altinteracttext',
}


# ---------- 通用配置与文件操作 ----------

def load_env(path='.env'):
    if not os.path.exists(path):
        return
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def cfg(name, default=None):
    return os.environ.get(name, default)


def now_utc():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'))


def sha256_value(value):
    return hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()


def sha256_text(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def atomic_write_json(path, value):
    """在目标目录内写临时文件，再原子替换，防止中断留下半文件。"""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=os.path.basename(path) + '.', suffix='.tmp', dir=directory)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(value, f, ensure_ascii=False, indent=1)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def atomic_write_jsonl(path, rows):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=os.path.basename(path) + '.', suffix='.tmp', dir=directory)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False,
                                   separators=(',', ':')) + '\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def archive_stale(path):
    """保留过期/损坏结果，避免静默覆盖历史产物。"""
    if not os.path.exists(path):
        return None
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    candidate = f'{path}.stale-{stamp}'
    index = 1
    while os.path.exists(candidate):
        candidate = f'{path}.stale-{stamp}-{index}'
        index += 1
    os.replace(path, candidate)
    return candidate


def safe_unlink(path):
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


def is_retryable_error(message):
    """短暂网络/限速可重试；配置错误或已给出恢复时间的额度用尽应立即停止。"""
    permanent_markers = (
        'not supported when using Codex with a ChatGPT account',
        'requires a newer version of Codex',
        'Codex 后端要求使用 ChatGPT 登录',
        '找不到 Codex CLI',
        'unknown model',
        'model_not_found',
        'invalid_json_schema',
        'invalid_api_key',
        'Incorrect API key',
        "You've hit your usage limit",
        'purchase more credits',
        'try again at',
    )
    return not any(marker.lower() in message.lower() for marker in permanent_markers)


def default_codex_command():
    """优先使用项目内固定版本，避免擅自改动用户的全局 Codex CLI。"""
    return LOCAL_CODEX_COMMAND if os.path.exists(LOCAL_CODEX_COMMAND) else 'codex'


def resolve_executable(command):
    if os.path.isabs(command):
        resolved = command
    elif os.path.dirname(command) and os.path.exists(command):
        resolved = os.path.abspath(command)
    else:
        resolved = shutil.which(command)
    if not resolved or not os.path.exists(resolved):
        raise RuntimeError(f'找不到 Codex CLI: {command}')
    return os.path.abspath(resolved)


# ---------- LLM 后端 ----------

def call_api(system_prompt, user_prompt, settings):
    """调用 OpenAI 兼容 Chat Completions API（备用后端）。"""
    url = settings['api_base'].rstrip('/') + '/chat/completions'
    body = {
        'model': settings['model'],
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ],
        'temperature': settings.get('temperature', 0.2),
        'max_tokens': settings['max_tokens'],
        'response_format': {'type': 'json_object'},
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + settings['api_key'],
        },
    )
    with urllib.request.urlopen(request, timeout=settings['timeout']) as response:
        data = json.loads(response.read().decode('utf-8'))
    return data['choices'][0]['message']['content'], {
        'usage': data.get('usage', {}),
    }


def extract_codex_usage(stdout):
    usage = {}
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except (TypeError, json.JSONDecodeError):
            continue
        if event.get('type') == 'turn.completed' and isinstance(event.get('usage'), dict):
            usage = event['usage']
    return usage


def call_codex(system_prompt, user_prompt, settings):
    """通过 codex exec 使用当前 ChatGPT 登录，并返回结构化最终消息。"""
    command = settings['codex_command']
    executable = resolve_executable(command)

    isolated_dir = tempfile.mkdtemp(prefix='dishonored_review_codex_')
    output_path = os.path.join(isolated_dir, 'result.json')
    prompt = (
        '你正在执行一个有界的翻译审校批次。任务所需数据已全部包含在本提示中。\n'
        '不要调用工具，不要读取或修改任何文件；只进行审校，并让最终回答严格符合 JSON Schema。\n\n'
        '<review_policy>\n' + system_prompt + '\n</review_policy>\n\n'
        '<batch_request>\n' + user_prompt + '\n</batch_request>\n'
    )
    args = [
        executable, 'exec', '--ephemeral', '--ignore-user-config', '--ignore-rules',
        '--skip-git-repo-check', '--sandbox', 'read-only', '--color', 'never',
        '--json', '-C', isolated_dir, '-m', settings['model'],
        '-c', f'model_reasoning_effort="{settings["reasoning_effort"]}"',
        '-c', 'approval_policy="never"',
        '--output-schema', os.path.abspath(settings['schema_path']),
        '-o', output_path, '-',
    ]

    # Codex 后端必须走已保存的 ChatGPT 登录，避免环境变量意外改成 API 计费。
    child_env = os.environ.copy()
    child_env.pop('CODEX_API_KEY', None)
    child_env.pop('OPENAI_API_KEY', None)

    try:
        completed = subprocess.run(
            args,
            input=prompt,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=settings['timeout'],
            env=child_env,
        )
        if completed.returncode != 0:
            detail = (
                'STDERR:\n' + (completed.stderr or '(空)') +
                '\nSTDOUT:\n' + (completed.stdout or '(空)'))[-8000:]
            raise RuntimeError(f'codex exec 失败 rc={completed.returncode}: {detail}')
        if not os.path.exists(output_path):
            raise RuntimeError('codex exec 未生成 --output-last-message 文件')
        with open(output_path, encoding='utf-8') as f:
            content = f.read()
        return content, {
            'usage': extract_codex_usage(completed.stdout),
        }
    finally:
        shutil.rmtree(isolated_dir, ignore_errors=True)


def call_model(system_prompt, user_prompt, settings):
    if settings['backend'] == 'codex':
        return call_codex(system_prompt, user_prompt, settings)
    return call_api(system_prompt, user_prompt, settings)


def command_output(args):
    completed = subprocess.run(
        args, capture_output=True, text=True, encoding='utf-8', errors='replace')
    text = (completed.stdout or completed.stderr).strip()
    if completed.returncode != 0:
        raise RuntimeError(text or f'命令失败: {args!r}')
    return text


def inspect_codex(command):
    executable = resolve_executable(command)
    return {
        'codex_command': executable,
        'codex_cli_version': command_output([executable, '--version']),
        'auth_status': command_output([executable, 'login', 'status']),
    }


# ---------- 模型输出契约 ----------

OUTPUT_FIELDS = {
    'id', 'action', 'new_text', 'reason', 'confidence',
    'uncertain', 'uncertain_reason',
}


def validate_items(items, expected_ids, allow_internal=False):
    if not isinstance(items, list):
        raise ValueError('输出 items 不是 JSON 数组')
    expected_ids = list(expected_ids)
    normalized = []
    seen = set()
    allowed = set(OUTPUT_FIELDS)
    if allow_internal:
        allowed.add('_old')

    for index, raw in enumerate(items):
        if not isinstance(raw, dict):
            raise ValueError(f'items[{index}] 不是对象')
        extra = set(raw) - allowed
        if extra:
            raise ValueError(f'items[{index}] 含未知字段: {sorted(extra)}')
        missing = OUTPUT_FIELDS - set(raw)
        if missing:
            raise ValueError(f'items[{index}] 缺少字段: {sorted(missing)}')
        item = dict(raw)
        if not isinstance(item['id'], str) or not item['id']:
            raise ValueError(f'items[{index}].id 非法')
        if item['id'] in seen:
            raise ValueError(f'重复 id: {item["id"]}')
        seen.add(item['id'])
        if item['action'] not in ('keep', 'fix'):
            raise ValueError(f'{item["id"]}: action 必须为 keep 或 fix')
        for field in ('new_text', 'reason', 'uncertain_reason'):
            if not isinstance(item[field], str):
                raise ValueError(f'{item["id"]}: {field} 必须为字符串')
        confidence = item['confidence']
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise ValueError(f'{item["id"]}: confidence 必须为数字')
        if not 0.0 <= float(confidence) <= 1.0:
            raise ValueError(f'{item["id"]}: confidence 超出 0..1')
        item['confidence'] = float(confidence)
        if not isinstance(item['uncertain'], bool):
            raise ValueError(f'{item["id"]}: uncertain 必须为布尔值')
        if item['action'] == 'fix' and not item['new_text']:
            raise ValueError(f'{item["id"]}: fix 时 new_text 不能为空')
        if item['action'] == 'fix' and not item['reason']:
            raise ValueError(f'{item["id"]}: fix 时 reason 不能为空')
        if item['uncertain'] and not item['uncertain_reason']:
            raise ValueError(f'{item["id"]}: uncertain=true 时必须填写 uncertain_reason')
        if item['action'] == 'keep':
            item['new_text'] = ''
        normalized.append(item)

    got_ids = [item['id'] for item in normalized]
    if len(got_ids) != len(expected_ids) or set(got_ids) != set(expected_ids):
        missing = sorted(set(expected_ids) - set(got_ids))
        extra = sorted(set(got_ids) - set(expected_ids))
        raise ValueError(
            f'id 集合不匹配: 期望 {len(expected_ids)} 实得 {len(got_ids)}; '
            f'缺少={missing[:5]} 多出={extra[:5]}')
    return normalized


def parse_response(content, expected_ids):
    content = content.strip()
    match = re.fullmatch(r'```(?:json)?\s*(.*?)\s*```', content, re.S)
    if match:
        content = match.group(1)
    data = json.loads(content)
    if not isinstance(data, dict) or 'items' not in data:
        raise ValueError('输出必须为 {"items": [...]} JSON 对象')
    if set(data) != {'items'}:
        raise ValueError(f'输出顶层含未知字段: {sorted(set(data) - {"items"})}')
    return validate_items(data['items'], expected_ids)


def placeholder_signature(text):
    """抽取标签、变量、反引号引用与换行标记。"""
    paired_backticks = re.findall(r'`[^`]*`', text)
    return {
        'angle': re.findall(r'<[^>]*>', text),
        'backtick': paired_backticks,
        # 具名变量可按中文语序重排，只要求多重集合一致。
        'section_variables': sorted(re.findall(r'§[^§]+§', text)),
        'dollar_variables': sorted(re.findall(r'\$[^$]+\$', text)),
        'literal_backticks': max(0, text.count('`') - 2 * len(paired_backticks)),
        'escaped_newline': re.findall(r'\\[nr]', text),
        'actual_newlines': len(re.findall(r'\r\n|\r|\n', text)),
    }


def required_format_signature(entry):
    """计算修补文本必须保留的格式。

    UPK 的 ``<XXXX/>`` 是中文目标串的时序遮罩，必须以现有中文为准；
    按键标识符则以英文源为准，允许修复天邈中的大小写错误。缺译项没有
    中文格式可继承时，回退到英文源格式。
    """
    old = placeholder_signature(entry.get('cn', ''))
    source = placeholder_signature(entry.get('en', ''))
    return {
        'angle': old['angle'] or source['angle'],
        'backtick': source['backtick'] or old['backtick'],
        'section_variables': (
            source['section_variables'] or old['section_variables']),
        'dollar_variables': (
            source['dollar_variables'] or old['dollar_variables']),
        # 只继承英文源中真实存在的未成对运行时标记。这样既保留 `k / `i，
        # 又允许修复仅由旧中文引入的损坏反引号。
        'source_literal_backticks': source['literal_backticks'],
        'escaped_newline': old['escaped_newline'] or source['escaped_newline'],
        'actual_newlines': (
            old['actual_newlines'] if entry.get('cn', '')
            else source['actual_newlines']),
    }


def check_placeholders(item, entry=None):
    if entry is not None:
        expected = required_format_signature(entry)
        text = (item.get('new_text', '') if item.get('action') == 'fix'
                else entry.get('cn', ''))
    else:
        old_signature = placeholder_signature(item.get('_old', ''))
        expected = {
            key: value for key, value in old_signature.items()
            if key != 'literal_backticks'
        }
        expected['source_literal_backticks'] = old_signature['literal_backticks']
        text = (item.get('new_text', '') if item.get('action') == 'fix'
                else item.get('_old', ''))
    actual = placeholder_signature(text or '')
    return (
        expected['angle'] == actual['angle'] and
        expected['backtick'] == actual['backtick'] and
        expected['section_variables'] == actual['section_variables'] and
        expected['dollar_variables'] == actual['dollar_variables'] and
        expected['source_literal_backticks'] == actual['literal_backticks'] and
        expected['escaped_newline'] == actual['escaped_newline'] and
        expected['actual_newlines'] == actual['actual_newlines']
    )


def english_term_present(text, term):
    pattern = re.escape(term)
    if term and term[0].isalnum():
        pattern = r'(?<![A-Za-z0-9_])' + pattern
    if term and term[-1].isalnum():
        pattern += r'(?![A-Za-z0-9_])'
    return re.search(pattern, text, re.I) is not None


def single_word_term_is_case_sensitive(term):
    """单词型 Title Case 术语只锁定同样大小写的专名/UI 用法。

    ``Favor``、``Heart``、``World`` 等经 Phase 2 批准的是特定 UI、物品
    或牌名；小写 ``in favor``、``heart``、``world`` 是普通词义，不能被
    扁平术语表强迫成批准值。多词专名继续不区分大小写，以兼容句首/标题
    大小写漂移。
    """
    return re.fullmatch(r'[A-Z][A-Za-z]*', term or '') is not None


def english_term_spans(text, term, case_sensitive_single_terms=True):
    """返回具有英文词边界的所有命中区间。"""
    pattern = re.escape(term)
    if term and term[0].isalnum():
        pattern = r'(?<![A-Za-z0-9_])' + pattern
    if term and term[-1].isalnum():
        pattern += r'(?![A-Za-z0-9_])'
    flags = 0 if (
        case_sensitive_single_terms and
        single_word_term_is_case_sensitive(term)
    ) else re.I
    return [match.span() for match in re.finditer(pattern, text, flags)]


def required_term_pairs(entry, terms, case_sensitive_single_terms=True):
    """英文实际命中的术语，同一片段实行最长匹配。

    例如 ``Blood Ox Heart`` 已覆盖 ``Heart`` 的命中区间，此时只应
    要求“血牛之心”，不能叠加“心脏”把译文逼成“血牛之心脏”。
    若较短术语还在句中的其他位置独立出现，仍会保留该独立命中。
    """
    source = entry.get('en', '')
    source_folded = source.casefold()
    candidates = []
    for english, chinese in terms.items():
        if not english or not chinese or english.casefold() not in source_folded:
            continue
        for start, end in english_term_spans(
                source, english, case_sensitive_single_terms):
            candidates.append((start, end, english, chinese))

    selected = []
    for candidate in sorted(
            candidates, key=lambda value: (-(value[1] - value[0]), value[0],
                                            value[2].casefold())):
        start, end, _english, _chinese = candidate
        if any(start < kept_end and kept_start < end
               for kept_start, kept_end, _ke, _kc in selected):
            continue
        selected.append(candidate)

    found = []
    seen = set()
    for _start, _end, english, chinese in sorted(selected):
        pair = (english, chinese)
        if pair not in seen:
            found.append(pair)
            seen.add(pair)
    return found


def load_advisory_terms(path):
    """读取带作用域的非硬锁术语；缺失文件等价于空策略层。"""
    if not path or not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as stream:
        raw = json.load(stream)
    items = raw.get('items') if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        raise ValueError('advisory terms 必须为数组或含 items 数组的对象')
    output = []
    seen = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f'advisory terms[{index}] 不是对象')
        english = item.get('en_term')
        chinese = item.get('cn_term')
        scope = item.get('scope')
        if (not isinstance(english, str) or not english or
                not isinstance(chinese, str) or not chinese or
                scope not in {'exact_case', 'label_only', 'context_only'}):
            raise ValueError(f'advisory terms[{index}] 字段非法')
        if english in seen:
            raise ValueError(f'advisory terms 重复英文: {english}')
        seen.add(english)
        output.append(dict(item))
    return output


def entry_is_term_label(entry):
    context = entry.get('context', {}) or {}
    field = str(context.get('subkey') or context.get('key') or '').casefold()
    return field in LABEL_TERM_FIELDS


def _case_sensitive_term_spans(text, term):
    pattern = re.escape(term)
    if term and term[0].isalnum():
        pattern = r'(?<![A-Za-z0-9_])' + pattern
    if term and term[-1].isalnum():
        pattern += r'(?![A-Za-z0-9_])'
    return [match.span() for match in re.finditer(pattern, text)]


def advisory_term_candidates(entry, advisory_terms):
    """返回当前条目可见的作用域术语，仅供语义判断，不形成硬约束。"""
    source = entry.get('en', '')
    candidates = []
    for item in advisory_terms or []:
        english = item['en_term']
        scope = item['scope']
        if english.casefold() not in source.casefold():
            continue
        if scope == 'label_only' and not entry_is_term_label(entry):
            continue
        spans = (_case_sensitive_term_spans(source, english)
                 if scope == 'exact_case'
                 else english_term_spans(
                     source, english, case_sensitive_single_terms=True))
        for start, end in spans:
            candidates.append((start, end, item))

    # 和硬锁层一样实行最长命中，避免较短参考词污染完整复合名称。
    selected = []
    for candidate in sorted(
            candidates, key=lambda value: (
                -(value[1] - value[0]), value[0],
                value[2]['en_term'].casefold())):
        start, end, _item = candidate
        if any(start < kept_end and kept_start < end
               for kept_start, kept_end, _kept in selected):
            continue
        selected.append(candidate)

    output = []
    seen = set()
    for _start, _end, item in sorted(
            selected, key=lambda value: (
                value[0], value[1], value[2]['en_term'].casefold())):
        key = (item['en_term'], item['cn_term'])
        if key in seen:
            continue
        seen.add(key)
        output.append({
            'id': item.get('id', ''), 'en': item['en_term'],
            'cn': item['cn_term'], 'scope': item['scope'],
            'confidence': item.get('confidence'),
            'reason': item.get('reason', ''),
            'risk_tags': item.get('risk_tags', []),
            'source': 'advisory', 'requires_secondary_review': True,
        })
    return output


def check_terms(item, terms, entry=None):
    """英文源命中正式术语时必须使用批准值。

    不能仅因为旧中文含有某个批准值就强制保留。多个术语值同时是
    普通中文词（如 ``Favor -> 帮助``），这种反向匹配会把普通叙事误判
    为界面术语。术语锁必须由英文原文触发。
    """
    new = (item['new_text'] if item['action'] == 'fix'
           else (entry or {}).get('cn', item.get('_old', ''))) or ''
    conflicts = []
    if entry is not None:
        excluded = {
            (value.get('en'), value.get('cn'))
            for value in ((entry.get('term_review') or {}).get('candidates') or [])
            if (entry.get('term_review') or {}).get('mode') ==
            'agent_secondary_review'
        }
        excluded.update({
            (value.get('en'), value.get('cn'))
            for value in (item.get('term_scope_overrides') or [])
        })
        for english, chinese in required_term_pairs(entry, terms):
            if (english, chinese) in excluded:
                continue
            if chinese not in new:
                conflicts.append(f'英文命中术语[{english}]，中文必须含 {chinese}')
    return '；'.join(conflicts) if conflicts else None


def validate_hard_rules(results, batch, terms, attach_old=True):
    entry_by_id = {entry['id']: entry for entry in batch}
    checked = []
    violations = []
    for raw in results:
        item = dict(raw)
        entry = entry_by_id[item['id']]
        old = entry['cn']
        item['_old'] = old
        escalation_reasons = set(
            (entry.get('escalation') or {}).get('reasons') or [])
        if 'release_gate_adversarial_review' in escalation_reasons:
            baseline = (entry.get('prior_review') or {}).get('original_cn', '')
            if not str(item.get('reason', '')).strip():
                violations.append(f'{item["id"]}: 反方二审缺少证据理由')
            if item.get('uncertain'):
                if (item.get('action') != 'keep' or item.get('new_text')):
                    violations.append(
                        f'{item["id"]}: research_required 必须 keep 且 new_text 为空')
                if not str(item.get('uncertain_reason', '')).strip():
                    violations.append(
                        f'{item["id"]}: research_required 缺少单一研究焦点')
            elif item.get('action') == 'keep':
                if item.get('new_text'):
                    violations.append(
                        f'{item["id"]}: accept_candidate 的 new_text 必须为空')
            elif (item.get('action') != 'fix' or
                  item.get('new_text') != baseline):
                violations.append(
                    f'{item["id"]}: 违反单写入规则；只能完整回退 original_cn')
        if 'release_gate_repair_proposal' in escalation_reasons:
            baseline = (entry.get('prior_review') or {}).get('original_cn', '')
            if item.get('uncertain'):
                if (item.get('action') != 'keep' or item.get('new_text') or
                        not str(item.get('uncertain_reason', '')).strip()):
                    violations.append(
                        f'{item["id"]}: 未解决 repair 必须 keep、空 new_text 且说明焦点')
            elif (item.get('action') != 'fix' or
                  not item.get('new_text') or item.get('new_text') == baseline):
                violations.append(
                    f'{item["id"]}: repair 必须提交不同于原译的完整候选')
        if 'release_gate_consistency_review' in escalation_reasons:
            sentinel = (entry.get('prior_review') or {}).get('original_cn', '')
            if not str(item.get('reason', '')).strip():
                violations.append(f'{item["id"]}: 一致性复核缺少上下文理由')
            if item.get('uncertain'):
                if (item.get('action') != 'keep' or item.get('new_text') or
                        not str(item.get('uncertain_reason', '')).strip()):
                    violations.append(
                        f'{item["id"]}: consistency research 必须 keep、空 new_text 且说明焦点')
            elif item.get('action') == 'keep':
                if item.get('new_text'):
                    violations.append(
                        f'{item["id"]}: consistency exception 的 new_text 必须为空')
            elif (item.get('action') != 'fix' or
                  item.get('new_text') != sentinel):
                violations.append(
                    f'{item["id"]}: consistency 复核只能完整回退冲突修改')
        if (entry.get('status') == 'en_only' and entry.get('en') and
                not entry.get('cn') and item['action'] != 'fix'):
            violations.append(f'{item["id"]}: en_only 非空英文必须补译')
        if not check_placeholders(item, entry):
            violations.append(f'{item["id"]}: 占位符/换行不一致')
        term_conflict = check_terms(item, terms, entry)
        if term_conflict:
            violations.append(f'{item["id"]}: {term_conflict}')
        if not attach_old:
            item.pop('_old', None)
        checked.append(item)
    if violations:
        raise ValueError('硬校验失败: ' + ' | '.join(violations[:10]))
    return checked


# ---------- 批次构建、缓存与执行 ----------

def build_batches(corpus, batch_size, upk_group=True, max_batch_chars=0):
    int_items = [entry for entry in corpus if entry['layer'] == 'int']
    upk_items = [entry for entry in corpus if entry['layer'] == 'upk']
    batches = []

    def chunk(items, size):
        for index in range(0, len(items), size):
            yield items[index:index + size]

    def pack(grouped_items):
        current = []
        current_chars = 0
        for items in grouped_items:
            for entry in items:
                entry_chars = len(json.dumps(
                    entry, ensure_ascii=False, separators=(',', ':')))
                over_chars = (
                    max_batch_chars > 0 and current and
                    current_chars + entry_chars > max_batch_chars)
                if current and (len(current) >= batch_size or over_chars):
                    yield current
                    current = []
                    current_chars = 0
                current.append(entry)
                current_chars += entry_chars
        if current:
            yield current

    int_groups = defaultdict(list)
    for entry in int_items:
        int_groups[entry.get('context', {}).get('file', 'unknown')].append(entry)
    batches.extend(pack(
        int_groups[key] for key in sorted(int_groups, key=str.casefold)))

    groups = defaultdict(list)
    for entry in upk_items:
        references = entry.get('context', {}).get('references', [])
        reference = references[0] if references else entry.get('context', {})
        upk = reference.get('upk', 'unknown') or 'unknown'
        path = reference.get('dialog_path', '') or ''
        tree = path.split(':disconversation_', 1)[0]
        key = f'{upk}|{tree}'
        groups[key].append(entry)
    batches.extend(pack(
        groups[key] for key in sorted(groups, key=str.casefold)))
    return batches


def compact_context(entry):
    context = entry.get('context', {})
    release = (entry.get('domain', {}).get('primary_release') or
               entry.get('domain', {}).get('release') or '')
    if entry.get('layer') == 'int':
        fields = [
            f'release={release}', f'file={context.get("file", "")}',
            f'section={context.get("section", "")}',
            f'key={context.get("key", "")}',
        ]
        if context.get('subkey'):
            fields.append(f'subkey={context["subkey"]}')
        return ', '.join(field for field in fields if not field.endswith('='))

    references = context.get('references', [])
    shown = []
    seen = set()
    for reference in references:
        value = '/'.join(str(reference.get(key, '')) for key in (
            'release', 'upk', 'dialog_path', 'object', 'kind'))
        if value not in seen:
            shown.append(value)
            seen.add(value)
        if len(shown) == 3:
            break
    suffix = (f' (+{len(references) - len(shown)} more)'
              if len(references) > len(shown) else '')
    return f'references={" | ".join(shown)}{suffix}'


def model_entries(batch, terms=None, advisory_terms=None):
    terms = terms or {}
    entries = []
    for entry in batch:
        term_review = entry.get('term_review') or {}
        secondary_pairs = {
            (value.get('en'), value.get('cn'))
            for value in (term_review.get('candidates') or [])
            if term_review.get('mode') == 'agent_secondary_review'
        }
        scoped_candidates = advisory_term_candidates(entry, advisory_terms)
        modeled = {
            'id': entry['id'],
            'context': compact_context(entry),
            'status': entry.get('status', ''),
            'en': entry['en'],
            'cn': entry['cn'],
            'required_format': required_format_signature(entry),
            'required_terms': [
                {'en': english, 'cn': chinese}
                for english, chinese in required_term_pairs(entry, terms)
                if (english, chinese) not in secondary_pairs
            ],
        }
        combined_candidates = []
        seen_candidates = set()
        for value in list(term_review.get('candidates') or []) + scoped_candidates:
            key = (value.get('en'), value.get('cn'))
            if key in seen_candidates:
                continue
            seen_candidates.add(key)
            combined_candidates.append(value)
        if combined_candidates:
            modeled['term_candidates'] = combined_candidates
        for field in ('prior_review', 'escalation', 'research_context'):
            if field in entry:
                modeled[field] = entry[field]
        entries.append(modeled)
    return entries


def render_user_prompt(template, terms, entries):
    terms_text = '\n'.join(f'- {en} -> {cn}' for en, cn in terms.items()) or '(空)'
    entries_text = json.dumps(entries, ensure_ascii=False, indent=2)
    return template.replace('{terms}', terms_text).replace('{entries}', entries_text)


def load_cached_batch(path, expected_ids, input_hash, config_hash, batch, terms):
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        meta = data.get('meta') if isinstance(data, dict) else None
        if not isinstance(meta, dict):
            raise ValueError('缺少 meta')
        if meta.get('input_hash') != input_hash:
            raise ValueError('input_hash 已变化')
        if meta.get('config_hash') != config_hash:
            raise ValueError('config_hash 已变化')
        items = validate_items(data.get('items'), expected_ids, allow_internal=True)
        # 缓存也重新执行硬校验，避免手工损坏后被错误跳过。
        validate_hard_rules(items, batch, terms)
        return {'items': items, 'meta': meta, 'cached': True}
    except Exception as exc:
        archived = archive_stale(path)
        print(f'  [过期] {os.path.basename(path)}: {exc}; 已保留为 {os.path.basename(archived)}')
        return None


def review_batch(batch, system_prompt, template, terms, batch_idx,
                 review_dir, settings, config_hash, caller=call_model,
                 max_retries=3, sleep_fn=time.sleep, advisory_terms=None,
                 stop_event=None):
    if stop_event is not None and stop_event.is_set():
        return None
    os.makedirs(review_dir, exist_ok=True)
    result_path = os.path.join(review_dir, f'batch_{batch_idx:04d}.json')
    request_path = os.path.join(review_dir, 'requests', f'batch_{batch_idx:04d}.json')
    failure_path = os.path.join(review_dir, 'failures', f'batch_{batch_idx:04d}.json')

    entries = model_entries(batch, terms, advisory_terms)
    expected_ids = [entry['id'] for entry in batch]
    input_hash = sha256_value(entries)
    request_payload = {
        'batch': batch_idx,
        'input_hash': input_hash,
        'config_hash': config_hash,
        'entries': entries,
    }
    atomic_write_json(request_path, request_payload)

    cached = load_cached_batch(
        result_path, expected_ids, input_hash, config_hash, batch, terms)
    if cached:
        print(f'  [跳过] batch_{batch_idx:04d}（缓存重新校验通过）')
        return cached

    user_prompt = render_user_prompt(template, terms, entries)
    errors = []
    for attempt in range(max_retries):
        try:
            attempt_prompt = user_prompt
            if errors:
                attempt_prompt += (
                    '\n\n<retry_feedback>\n'
                    '上一版输出未通过确定性校验。请修正下述错误后重新输出完整批次；'
                    '不得遗漏其他 ID：\n- ' + errors[-1] +
                    '\n</retry_feedback>')
            response = caller(system_prompt, attempt_prompt, settings)
            if isinstance(response, tuple):
                content, call_meta = response
            else:
                content, call_meta = response, {}
            results = parse_response(content, expected_ids)
            results = validate_hard_rules(results, batch, terms)
            meta = {
                'backend': settings['backend'],
                'model': settings['model'],
                'reasoning_effort': settings.get('reasoning_effort'),
                'input_hash': input_hash,
                'config_hash': config_hash,
                'completed_at': now_utc(),
                'usage': call_meta.get('usage', {}),
                'attempts': attempt + 1,
                'retry_errors': list(errors),
            }
            atomic_write_json(result_path, {
                'batch': batch_idx,
                'meta': meta,
                'items': results,
            })
            safe_unlink(failure_path)
            print(f'  [OK] batch_{batch_idx:04d}: {len(results)} 条')
            return {'items': results, 'meta': meta, 'cached': False}
        except Exception as exc:
            message = str(exc)
            errors.append(message)
            print(f'  [重试 {attempt + 1}/{max_retries}] batch_{batch_idx:04d}: {message}')
            if not is_retryable_error(message):
                if stop_event is not None:
                    stop_event.set()
                print('  [停止重试] 检测到不可立即恢复的配置/认证/额度错误')
                break
            if attempt + 1 < max_retries:
                sleep_fn(3 * (2 ** attempt))

    atomic_write_json(failure_path, {
        'batch': batch_idx,
        'input_hash': input_hash,
        'config_hash': config_hash,
        'failed_at': now_utc(),
        'errors': errors,
    })
    print(f'  [失败] batch_{batch_idx:04d}')
    return None


def public_settings(settings):
    fields = (
        'backend', 'model', 'reasoning_effort', 'api_base',
        'codex_cli_version', 'codex_command',
    )
    return {key: settings.get(key) for key in fields if settings.get(key) is not None}


def fingerprint_settings(settings):
    """只纳入会影响模型结果的设置；CLI 绝对路径仅记录、不参与缓存。"""
    fields = (
        'backend', 'model', 'reasoning_effort', 'api_base',
        'codex_cli_version',
    )
    return {key: settings.get(key) for key in fields if settings.get(key) is not None}


def sum_usage(outcomes):
    totals = Counter()
    for outcome in outcomes:
        usage = outcome.get('meta', {}).get('usage', {})
        if not isinstance(usage, dict):
            continue
        for key, value in usage.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                totals[key] += value
    return dict(totals)


def build_wiki_lookup_items(uncertain_items, corpus):
    """把模型不确定项转为外部事实核查队列，不在批次内擅自联网。"""
    corpus_by_id = {entry['id']: entry for entry in corpus}
    queue = []
    for item in uncertain_items:
        source = corpus_by_id.get(item['id'], {})
        reason = item.get('uncertain_reason', '')
        marker = re.match(r'\s*\[WIKI_LOOKUP:\s*(.*?)\]\s*', reason, re.I | re.S)
        queue.append({
            'id': item['id'],
            'en': source.get('en', ''),
            'cn': source.get('cn', ''),
            'context': source.get('context', {}),
            'model_action': item.get('action', ''),
            'model_new_text': item.get('new_text', ''),
            'confidence': item.get('confidence'),
            'uncertain_reason': reason,
            'suggested_wiki_query': (
                marker.group(1).strip() if marker else source.get('en', '')[:160]),
            'research_status': 'pending',
        })
    return queue


def build_settings(args):
    if args.backend == 'codex':
        settings = {
            'backend': 'codex',
            'model': args.model or cfg('CODEX_MODEL', 'gpt-5.6-sol'),
            'reasoning_effort': args.reasoning_effort,
            'codex_command': cfg('CODEX_COMMAND', default_codex_command()),
            'schema_path': os.path.abspath(args.schema),
            'timeout': int(cfg('CODEX_TIMEOUT', '1800')),
        }
        info = inspect_codex(settings['codex_command'])
        settings.update(info)
        if 'ChatGPT' not in settings['auth_status']:
            raise RuntimeError(
                'Codex 后端要求使用 ChatGPT 登录；当前状态: '
                + settings['auth_status'])
        return settings

    api_key = cfg('LLM_API_KEY', '')
    if not api_key:
        raise RuntimeError('API 后端需要 LLM_API_KEY')
    return {
        'backend': 'api',
        'model': args.model or cfg('LLM_MODEL', 'deepseek-chat'),
        'reasoning_effort': None,
        'api_base': cfg('LLM_API_BASE', 'https://api.deepseek.com/v1'),
        'api_key': api_key,
        'max_tokens': int(cfg('LLM_MAX_TOKENS', '16000')),
        'timeout': int(cfg('LLM_TIMEOUT', '300')),
        'temperature': float(cfg('LLM_TEMPERATURE', '0.2')),
        'schema_path': os.path.abspath(args.schema),
    }


def main(argv=None):
    load_env()
    parser = argparse.ArgumentParser()
    parser.add_argument('--corpus', default='data/aligned/corpus.jsonl')
    parser.add_argument('--terms', default='glossary/terms.json')
    parser.add_argument('--advisory-terms', default='glossary/advisory_terms.json')
    parser.add_argument('--system', default='prompt/system.md')
    parser.add_argument('--template', default='prompt/template.md')
    parser.add_argument('--schema', default=DEFAULT_SCHEMA)
    parser.add_argument('--review-dir', default=DEFAULT_REVIEW_DIR)
    parser.add_argument('--backend', choices=('codex', 'api'),
                        default=cfg('LLM_BACKEND', 'codex'))
    parser.add_argument('--model')
    parser.add_argument('--reasoning-effort',
                        choices=('none', 'low', 'medium', 'high', 'xhigh', 'max'),
                        default=cfg('CODEX_REASONING_EFFORT', 'medium'))
    parser.add_argument('--batch-size', type=int,
                        default=int(cfg('LLM_BATCH_SIZE', '40')))
    parser.add_argument(
        '--max-batch-chars', type=int,
        default=int(cfg('LLM_MAX_BATCH_CHARS', '0')),
        help='按原始 JSON 字符数软限制每批上下文（0=不限制）')
    parser.add_argument('--only', help='只处理该 id 前缀（如 int:Bridge 或 upk:）')
    parser.add_argument('--max-batches', type=int, default=0,
                        help='最多处理 N 批（0=全部）')
    args = parser.parse_args(argv)

    if args.batch_size < 1:
        parser.error('--batch-size 必须大于 0')
    if args.max_batch_chars < 0:
        parser.error('--max-batch-chars 不能小于 0')
    for path in (args.corpus, args.terms, args.system, args.template, args.schema):
        if not os.path.exists(path):
            parser.error(f'文件不存在: {path}')

    try:
        settings = build_settings(args)
    except Exception as exc:
        print(f'错误: {exc}')
        return 2

    with open(args.corpus, encoding='utf-8') as f:
        source_corpus = [json.loads(line) for line in f if line.strip()]
    if args.only:
        source_corpus = [
            entry for entry in source_corpus
            if entry['id'].startswith(args.only)]

    automatic_empty = [
        entry for entry in source_corpus
        if not entry.get('en', '') and not entry.get('cn', '')]
    unpaired_manual = [
        entry for entry in source_corpus
        if entry.get('status') == 'cn_only' and
        (entry.get('en', '') or entry.get('cn', ''))]
    eligible_statuses = {'aligned', 'aligned_normalized', 'en_only'}
    corpus = [
        entry for entry in source_corpus
        if entry.get('status') in eligible_statuses and
        (entry.get('en', '') or entry.get('cn', ''))]
    classified_ids = {
        entry['id'] for entry in (*automatic_empty, *unpaired_manual, *corpus)
    }
    unclassified = [
        entry for entry in source_corpus if entry['id'] not in classified_ids]
    if unclassified:
        print('错误: 存在未分类 corpus 状态: ' + ', '.join(
            f'{entry["id"]}({entry.get("status")})'
            for entry in unclassified[:10]))
        return 2

    with open(args.terms, encoding='utf-8') as f:
        raw_terms = json.load(f)
    terms = {key: value for key, value in raw_terms.items()
             if not key.startswith('_')}
    advisory_terms = load_advisory_terms(args.advisory_terms)
    with open(args.system, encoding='utf-8') as f:
        system_prompt = f.read()
    with open(args.template, encoding='utf-8') as f:
        template = f.read()

    batches = build_batches(corpus, args.batch_size, max_batch_chars=args.max_batch_chars)
    if args.max_batches:
        batches = batches[:args.max_batches]

    settings_public = public_settings(settings)
    settings_fingerprint = fingerprint_settings(settings)
    hashes = {
        'corpus': sha256_file(args.corpus),
        'terms': sha256_value(terms),
        'advisory_terms': sha256_value(advisory_terms),
        'system_prompt': sha256_text(system_prompt),
        'template': sha256_text(template),
        'schema': sha256_file(args.schema),
    }
    config_fingerprint = {
        'pipeline_version': PIPELINE_VERSION,
        'backend': settings_fingerprint,
        'batch_size': args.batch_size,
        'hashes': {key: value for key, value in hashes.items() if key != 'corpus'},
    }
    # 0 是历史无限制行为；不写入指纹以保持旧运行的缓存可恢复。
    if args.max_batch_chars:
        config_fingerprint['max_batch_chars'] = args.max_batch_chars
    config_hash = sha256_value(config_fingerprint)
    expected_entries = sum(len(batch) for batch in batches)
    manifest = {
        'pipeline_version': PIPELINE_VERSION,
        'created_at': now_utc(),
        'backend': settings_public,
        'auth_status': settings.get('auth_status'),
        'batch_size': args.batch_size,
        'max_batch_chars': args.max_batch_chars,
        'only': args.only,
        'max_batches': args.max_batches,
        'source_entries_selected': len(source_corpus),
        'model_entries_selected': len(corpus),
        'automatic_empty_entries': len(automatic_empty),
        'unpaired_manual_entries': len(unpaired_manual),
        'scheduled_batches': len(batches),
        'scheduled_entries': expected_entries,
        'config_hash': config_hash,
        'hashes': hashes,
    }
    atomic_write_json(os.path.join(args.review_dir, 'run_manifest.json'), manifest)

    print(f'后端: {settings["backend"]} / 模型: {settings["model"]}')
    if settings['backend'] == 'codex':
        print(f'Codex: {settings["codex_cli_version"]} / {settings["auth_status"]}')
        print(f'推理强度: {settings["reasoning_effort"]}')
    print(
        f'语料: {len(source_corpus)} 条；模型审校 {len(corpus)}；'
        f'双方空值自动覆盖 {len(automatic_empty)}；'
        f'无英文源人工项 {len(unpaired_manual)}')
    print(f'全局硬锁术语: {len(terms)} 条；作用域参考术语: {len(advisory_terms)} 条')
    print(f'批次: {len(batches)}（计划 {expected_entries} 条）')

    if settings['backend'] == 'codex':
        concurrency = int(cfg('CODEX_CONCURRENCY', '1'))
    else:
        concurrency = int(cfg('LLM_CONCURRENCY', '4'))
    concurrency = max(1, concurrency)

    outcomes = []
    failed_batches = []
    stop_event = threading.Event()
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {
            executor.submit(
                review_batch, batch, system_prompt, template, terms, batch_idx,
                args.review_dir, settings, config_hash,
                advisory_terms=advisory_terms,
                stop_event=stop_event): batch_idx
            for batch_idx, batch in enumerate(batches)
        }
        for future in as_completed(futures):
            batch_idx = futures[future]
            try:
                outcome = future.result()
            except Exception as exc:
                print(f'  [异常] batch_{batch_idx:04d}: {exc}')
                outcome = None
            if outcome:
                outcomes.append(outcome)
            else:
                failed_batches.append(batch_idx)

    unordered_results = [
        item for outcome in outcomes for item in outcome['items']]
    result_by_id = {item['id']: item for item in unordered_results}
    all_results = [
        result_by_id[entry['id']] for entry in corpus
        if entry['id'] in result_by_id]
    automatic_results = [{
        'id': entry['id'], 'action': 'keep', 'new_text': '',
        'reason': '英文与天邈中文均为空；作为覆盖/未使用字段确定性保留。',
        'confidence': 1.0, 'uncertain': False, 'uncertain_reason': '',
        'route': 'automatic_empty_keep', 'source_status': entry.get('status'),
    } for entry in automatic_empty]
    manual_results = [{
        'id': entry['id'], 'action': 'keep', 'new_text': '',
        'reason': '只有天邈中文而无英文源，Phase 3 无法进行中英对照。',
        'confidence': 0.0, 'uncertain': True,
        'uncertain_reason': '缺少英文源；保留现有中文并进入人工审核。',
        'route': 'unpaired_manual_review', 'source_status': entry.get('status'),
        'en': entry.get('en', ''), 'cn': entry.get('cn', ''),
        'context': entry.get('context', {}),
    } for entry in unpaired_manual]
    atomic_write_jsonl(
        os.path.join(args.review_dir, 'results.jsonl'), all_results)
    atomic_write_jsonl(
        os.path.join(args.review_dir, 'automatic_empty_keep.jsonl'),
        automatic_results)
    atomic_write_jsonl(
        os.path.join(args.review_dir, 'unpaired_manual_review.jsonl'),
        manual_results)
    actions = Counter(item['action'] for item in all_results)
    uncertain = [item for item in all_results if item.get('uncertain')]
    wiki_lookup_items = build_wiki_lookup_items(uncertain, corpus)
    atomic_write_json(os.path.join(args.review_dir, 'wiki_lookup_queue.json'), {
        'source': 'all uncertain=true results',
        'lookup_site': 'https://dishonored.fandom.com/wiki/',
        'site_note': '用户指定的社区 Wiki；用于核实实体事实，不覆盖天邈中文底色。',
        'count': len(wiki_lookup_items),
        'items': wiki_lookup_items,
    })
    covered_entries = len(all_results) + len(automatic_results) + len(manual_results)
    summary = {
        'source_entries': len(source_corpus),
        'model_entries_selected': len(corpus),
        'expected_entries': expected_entries,
        'completed_entries': len(all_results),
        'automatic_empty_keep': len(automatic_results),
        'unpaired_manual_review': len(manual_results),
        'covered_entries': covered_entries,
        'coverage_rate': round(
            covered_entries / max(len(source_corpus), 1), 6),
        'scheduled_batches': len(batches),
        'completed_batches': len(outcomes),
        'cached_batches': sum(1 for outcome in outcomes if outcome.get('cached')),
        'failed_batches': sorted(failed_batches),
        'actions': dict(actions),
        'uncertain': len(uncertain),
        'uncertain_rate': round(len(uncertain) / max(len(all_results), 1), 4),
        'wiki_lookup_queue': len(wiki_lookup_items),
        'usage_all_completed_batches': sum_usage(outcomes),
        'usage_this_run': sum_usage(
            [outcome for outcome in outcomes if not outcome.get('cached')]),
        'config_hash': config_hash,
        'updated_at': now_utc(),
    }
    atomic_write_json(os.path.join(args.review_dir, 'summary.json'), summary)
    print('\n汇总:', summary)
    if uncertain:
        print(f'\n不确定条目 {len(uncertain)} 条（进入人工审核）：')
        for item in uncertain[:10]:
            print(f'  {item["id"]}: {item.get("uncertain_reason", "")[:60]}')
    return 1 if failed_batches else 0


if __name__ == '__main__':
    sys.exit(main())
