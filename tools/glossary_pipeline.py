# -*- coding: utf-8 -*-
"""用当前 Codex/ChatGPT 登录分类 Phase 2 术语候选并生成审阅产物。

本工具绝不覆盖 ``glossary/terms.json``。模型结果经过 JSON Schema、ID、
证据 ID、中文来源、冲突与自动锁阈值硬校验后，才进入建议文件。
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import glossary_extract
import review_pipeline as rp
from phase1_extract import json_write, jsonl_write, sha256_file


ROOT = Path(__file__).resolve().parent.parent
PIPELINE_VERSION = 1
OUTPUT_FIELDS = {
    'id', 'action', 'cn_term', 'category', 'confidence', 'reason',
    'evidence_ids', 'conflict', 'conflict_reason',
}
CATEGORIES = {
    'person', 'place', 'organization', 'title', 'item', 'ability',
    'world_term', 'ui_term', 'generic', 'noise', 'other',
}


def load_jsonl(path):
    with open(path, encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def candidate_for_model(candidate):
    """限制批次体积，同时让每个冲突变体保留至少一个真实上下文。"""
    contexts = candidate.get('contexts', [])
    wanted = []
    for variant in candidate.get('exact_cn_variants', []):
        match = next(
            (ctx for ctx in contexts if ctx.get('cn', '').strip() == variant['cn']),
            None)
        if match and match not in wanted:
            wanted.append(match)
    wanted.extend(ctx for ctx in contexts if ctx not in wanted)
    return {
        'id': candidate['id'],
        'en_term': candidate['en_term'],
        'seed_value': candidate.get('seed_value', ''),
        'required_core_or_seed': candidate.get('required_core_or_seed', False),
        'row_count': candidate.get('row_count', 0),
        'proper_row_count': candidate.get('proper_row_count', 0),
        'label_row_count': candidate.get('label_row_count', 0),
        'releases': candidate.get('releases', {}),
        'exact_cn_variants': candidate.get('exact_cn_variants', [])[:8],
        'contexts': [
            {
                'id': ctx['id'],
                'layer': ctx.get('layer', ''),
                'release': ctx.get('release', ''),
                'en': ctx.get('en', ''),
                'cn': ctx.get('cn', ''),
            }
            for ctx in wanted[:5]
        ],
    }


def cn_supported(item, candidate):
    cn_term = item['cn_term']
    if not cn_term:
        return False
    evidence = set(item['evidence_ids'])
    for context in candidate.get('contexts', []):
        if context['id'] in evidence and cn_term in context.get('cn', ''):
            return True
    return False


def validate_items(items, expected_ids, candidate_by_id):
    if not isinstance(items, list):
        raise ValueError('items 不是数组')
    expected_ids = list(expected_ids)
    seen = set()
    normalized = []
    for index, raw in enumerate(items):
        if not isinstance(raw, dict):
            raise ValueError(f'items[{index}] 不是对象')
        missing = OUTPUT_FIELDS - set(raw)
        extra = set(raw) - OUTPUT_FIELDS
        if missing or extra:
            raise ValueError(
                f'items[{index}] 字段错误: 缺少={sorted(missing)} 多出={sorted(extra)}')
        item = dict(raw)
        item_id = item['id']
        if not isinstance(item_id, str) or item_id not in candidate_by_id:
            raise ValueError(f'items[{index}].id 非法: {item_id!r}')
        if item_id in seen:
            raise ValueError(f'重复 id: {item_id}')
        seen.add(item_id)
        if item['action'] not in ('lock', 'review', 'reject'):
            raise ValueError(f'{item_id}: action 非法')
        if item['category'] not in CATEGORIES:
            raise ValueError(f'{item_id}: category 非法')
        for field in ('cn_term', 'reason', 'conflict_reason'):
            if not isinstance(item[field], str):
                raise ValueError(f'{item_id}: {field} 必须是字符串')
            item[field] = item[field].strip()
        confidence = item['confidence']
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise ValueError(f'{item_id}: confidence 必须是数字')
        item['confidence'] = float(confidence)
        if not 0 <= item['confidence'] <= 1:
            raise ValueError(f'{item_id}: confidence 超出 0..1')
        if not item['reason']:
            raise ValueError(f'{item_id}: reason 不能为空')
        if not isinstance(item['conflict'], bool):
            raise ValueError(f'{item_id}: conflict 必须是布尔值')
        if item['conflict'] and not item['conflict_reason']:
            raise ValueError(f'{item_id}: conflict=true 时理由不能为空')
        if not item['conflict']:
            item['conflict_reason'] = ''
        if not isinstance(item['evidence_ids'], list) or any(
                not isinstance(value, str) or not value
                for value in item['evidence_ids']):
            raise ValueError(f'{item_id}: evidence_ids 非法')
        if len(item['evidence_ids']) != len(set(item['evidence_ids'])):
            raise ValueError(f'{item_id}: evidence_ids 重复')

        candidate = candidate_by_id[item_id]
        allowed_evidence = {ctx['id'] for ctx in candidate.get('contexts', [])}
        unknown = set(item['evidence_ids']) - allowed_evidence
        if unknown:
            raise ValueError(f'{item_id}: 引用了未提供的证据 {sorted(unknown)}')

        variants = [entry['cn'] for entry in candidate.get('exact_cn_variants', [])]
        seed = candidate.get('seed_value', '').strip()
        if item['action'] == 'reject':
            if item['cn_term'] or item['evidence_ids']:
                raise ValueError(f'{item_id}: reject 必须清空 cn_term/evidence_ids')
        else:
            if item['cn_term'] and not item['evidence_ids']:
                raise ValueError(f'{item_id}: 给出 cn_term 时必须引用证据')
            if item['cn_term'] and not cn_supported(item, candidate):
                raise ValueError(f'{item_id}: cn_term 不是所引中文证据的连续子串')

        if item['action'] == 'lock':
            if not item['cn_term'] or not item['evidence_ids']:
                raise ValueError(f'{item_id}: lock 必须有译名和证据')
            if item['confidence'] < 0.90:
                raise ValueError(f'{item_id}: lock 置信度低于 0.90')
            if item['conflict']:
                raise ValueError(f'{item_id}: 有冲突的候选不能 lock')
            if item['category'] in ('generic', 'noise'):
                raise ValueError(f'{item_id}: 普通词/噪声不能 lock')
            if len(variants) > 1:
                raise ValueError(f'{item_id}: 多个直接译名必须 review')
            if len(variants) == 1 and item['cn_term'] != variants[0]:
                raise ValueError(f'{item_id}: lock 译名必须等于唯一直接译名')
            if seed and item['cn_term'] != seed:
                raise ValueError(f'{item_id}: 与旧种子冲突必须 review')
            if candidate['en_term'].casefold() == 'whale' \
                    and item['cn_term'] == '鲸油':
                raise ValueError(f'{item_id}: 禁止把 Whale 泛化锁定为鲸油')
        normalized.append(item)

    got = [item['id'] for item in normalized]
    if len(got) != len(expected_ids) or set(got) != set(expected_ids):
        raise ValueError(
            f'ID 集合不匹配: 期望={len(expected_ids)} 实得={len(got)} '
            f'缺少={sorted(set(expected_ids)-set(got))[:5]} '
            f'多出={sorted(set(got)-set(expected_ids))[:5]}')
    return normalized


def parse_response(content, expected_ids, candidate_by_id):
    content = content.strip()
    match = re.fullmatch(r'```(?:json)?\s*(.*?)\s*```', content, re.S)
    if match:
        content = match.group(1)
    data = json.loads(content)
    if not isinstance(data, dict) or set(data) != {'items'}:
        raise ValueError('顶层必须严格为 {"items": [...]}')
    return validate_items(data['items'], expected_ids, candidate_by_id)


def render_prompt(template, entries):
    return template.replace(
        '{entries}', json.dumps(entries, ensure_ascii=False, indent=1))


def load_cached(path, expected_ids, input_hash, config_hash, candidate_by_id):
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        meta = data.get('meta', {})
        if meta.get('input_hash') != input_hash:
            raise ValueError('input_hash 已变化')
        if meta.get('config_hash') != config_hash:
            raise ValueError('config_hash 已变化')
        items = validate_items(data.get('items'), expected_ids, candidate_by_id)
        return {'items': items, 'meta': meta, 'cached': True}
    except Exception as exc:
        archived = rp.archive_stale(str(path))
        print(f'  [过期] {path.name}: {exc}; 保留为 {Path(archived).name}')
        return None


def classify_batch(batch, batch_index, system_prompt, template, settings,
                   config_hash, batch_dir, caller=rp.call_model,
                   max_retries=3, sleep_fn=time.sleep):
    model_entries = [candidate_for_model(candidate) for candidate in batch]
    expected_ids = [candidate['id'] for candidate in batch]
    candidate_by_id = {candidate['id']: candidate for candidate in batch}
    input_hash = rp.sha256_value(model_entries)
    result_path = batch_dir / f'batch_{batch_index:04d}.json'
    request_path = batch_dir / 'requests' / f'batch_{batch_index:04d}.json'
    failure_path = batch_dir / 'failures' / f'batch_{batch_index:04d}.json'
    rp.atomic_write_json(str(request_path), {
        'batch': batch_index,
        'input_hash': input_hash,
        'config_hash': config_hash,
        'entries': model_entries,
    })
    cached = load_cached(
        result_path, expected_ids, input_hash, config_hash, candidate_by_id)
    if cached:
        print(f'  [跳过] glossary batch_{batch_index:04d}（缓存有效）')
        return cached

    user_prompt = render_prompt(template, model_entries)
    errors = []
    for attempt in range(max_retries):
        try:
            response = caller(system_prompt, user_prompt, settings)
            if isinstance(response, tuple):
                content, call_meta = response
            else:
                content, call_meta = response, {}
            items = parse_response(content, expected_ids, candidate_by_id)
            meta = {
                'backend': settings['backend'],
                'model': settings['model'],
                'reasoning_effort': settings.get('reasoning_effort'),
                'input_hash': input_hash,
                'config_hash': config_hash,
                'completed_at': rp.now_utc(),
                'usage': call_meta.get('usage', {}),
            }
            rp.atomic_write_json(str(result_path), {
                'batch': batch_index, 'meta': meta, 'items': items,
            })
            rp.safe_unlink(str(failure_path))
            print(f'  [OK] glossary batch_{batch_index:04d}: {len(items)} 条')
            return {'items': items, 'meta': meta, 'cached': False}
        except Exception as exc:
            message = str(exc)
            errors.append(message)
            print(
                f'  [重试 {attempt + 1}/{max_retries}] '
                f'glossary batch_{batch_index:04d}: {message}')
            if not rp.is_retryable_error(message):
                break
            if attempt + 1 < max_retries:
                sleep_fn(3 * (2 ** attempt))
    rp.atomic_write_json(str(failure_path), {
        'batch': batch_index,
        'input_hash': input_hash,
        'config_hash': config_hash,
        'failed_at': rp.now_utc(),
        'errors': errors,
    })
    print(f'  [失败] glossary batch_{batch_index:04d}')
    return None


def enriched_items(candidates, model_items):
    candidate_by_id = {item['id']: item for item in candidates}
    enriched = []
    for item in model_items:
        candidate = candidate_by_id[item['id']]
        value = {
            **item,
            'en_term': candidate['en_term'],
            'seed_value': candidate.get('seed_value', ''),
            'required_core_or_seed': candidate.get('required_core_or_seed', False),
            'row_count': candidate.get('row_count', 0),
            'proper_row_count': candidate.get('proper_row_count', 0),
            'label_row_count': candidate.get('label_row_count', 0),
            'releases': candidate.get('releases', {}),
            'exact_cn_variants': candidate.get('exact_cn_variants', []),
            'evidence': [
                context for context in candidate.get('contexts', [])
                if context['id'] in item['evidence_ids']
            ],
        }
        value['route'], value['route_reason'] = routing_decision(value)
        enriched.append(value)
    return enriched


def routing_decision(item):
    """模型结论之上再加一层保守放行，单条证据不得自动进入术语锁。"""
    if item['action'] == 'reject':
        return 'reject', '模型判定为普通词、句首误抓或其他非术语候选。'
    if item['action'] == 'review':
        return 'human_review', '模型已发现译名、词义或旧种子冲突。'
    if item['confidence'] < 0.95:
        return 'human_review', '模型虽建议锁定，但置信度低于自动放行阈值 0.95。'
    if item['row_count'] < 2:
        return 'human_review', '仅有一条 corpus 记录，证据不足以自动放行。'
    if item['category'] == 'other':
        return 'human_review', '类别边界不明确，需人工确认。'
    return 'auto_lock', '模型高置信、至少两条语料记录且无已知冲突。'


def build_conflicts(items):
    conflicts = []
    for item in items:
        kinds = []
        if len(item['exact_cn_variants']) > 1:
            kinds.append('multiple_exact_cn')
        if item['seed_value'] and item['cn_term'] \
                and item['seed_value'] != item['cn_term']:
            kinds.append('seed_mismatch')
        if item['conflict']:
            kinds.append('model_flagged')
        if kinds:
            conflicts.append({
                'id': item['id'],
                'en_term': item['en_term'],
                'types': kinds,
                'seed_value': item['seed_value'],
                'recommended_cn': item['cn_term'],
                'exact_cn_variants': item['exact_cn_variants'],
                'reason': item['reason'],
                'conflict_reason': item['conflict_reason'],
                'evidence': item['evidence'],
            })

    by_cn = defaultdict(list)
    for item in items:
        if item['action'] != 'reject' and item['cn_term']:
            by_cn[item['cn_term']].append(item)
    for cn_term, matches in sorted(by_cn.items()):
        english = sorted({item['en_term'] for item in matches})
        if len(english) > 1:
            conflicts.append({
                'id': 'cn-collision:' + rp.sha256_text(cn_term)[:16],
                'en_term': ' / '.join(english),
                'types': ['same_cn_multiple_en'],
                'seed_value': '',
                'recommended_cn': cn_term,
                'exact_cn_variants': [],
                'reason': '多个英文候选指向同一中文，可能是别名/单复数，也可能是过度泛化。',
                'conflict_reason': '需人工决定是否合并为别名或仅保留一个键。',
                'evidence': [],
            })
    return conflicts


def seed_audit(items, seeds):
    by_en = {item['en_term'].casefold(): item for item in items}
    audit = []
    for english, old_cn in seeds.items():
        key = glossary_extract.canonical_term(english).casefold()
        item = by_en.get(key)
        if not item:
            audit.append({
                'en_term': english, 'old_cn': old_cn, 'status': 'missing',
                'recommended_cn': '', 'model_action': '',
                'reason': '旧种子未进入候选集。', 'evidence_ids': [],
            })
            continue
        if item['action'] == 'reject':
            status = 'remove_recommended'
        elif item['cn_term'] and item['cn_term'] != old_cn:
            status = 'replace_recommended'
        elif item['action'] == 'lock' and item['cn_term'] == old_cn:
            status = 'confirmed'
        else:
            status = 'review'
        audit.append({
            'en_term': english,
            'old_cn': old_cn,
            'status': status,
            'recommended_cn': item['cn_term'],
            'model_action': item['action'],
            'reason': item['reason'],
            'conflict_reason': item['conflict_reason'],
            'evidence_ids': item['evidence_ids'],
            'exact_cn_variants': item['exact_cn_variants'],
        })
    return audit


def review_priority(item):
    seed_conflict = (
        item['seed_value'] and
        (item['action'] == 'reject' or
         (item['cn_term'] and item['cn_term'] != item['seed_value'])))
    if seed_conflict or len(item['exact_cn_variants']) > 1:
        return 1
    if item['route'] == 'human_review':
        return 2
    if item['required_core_or_seed']:
        return 3
    return 4


def write_review_csv(path, items):
    fields = [
        'priority', 'route', 'route_reason', 'model_action', 'user_decision', 'en_term',
        'recommended_cn', 'user_cn', 'category', 'confidence', 'seed_value',
        'exact_cn_variants', 'row_count', 'releases', 'reason',
        'conflict_reason', 'evidence_ids', 'examples',
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for item in sorted(items, key=lambda value: (
                review_priority(value), -value['row_count'],
                value['en_term'].casefold())):
            if item['action'] == 'reject':
                continue
            examples = ' || '.join(
                f"{entry['id']} | EN: {entry['en']} | CN: {entry['cn']}"
                for entry in item['evidence'])
            writer.writerow({
                'priority': review_priority(item),
                'route': item['route'],
                'route_reason': item['route_reason'],
                'model_action': item['action'],
                'user_decision': '',
                'en_term': item['en_term'],
                'recommended_cn': item['cn_term'],
                'user_cn': '',
                'category': item['category'],
                'confidence': f"{item['confidence']:.2f}",
                'seed_value': item['seed_value'],
                'exact_cn_variants': json.dumps(
                    item['exact_cn_variants'], ensure_ascii=False,
                    separators=(',', ':')),
                'row_count': item['row_count'],
                'releases': json.dumps(
                    item['releases'], ensure_ascii=False,
                    separators=(',', ':')),
                'reason': item['reason'],
                'conflict_reason': item['conflict_reason'],
                'evidence_ids': ' | '.join(item['evidence_ids']),
                'examples': examples,
            })


def validate_outputs(candidates, items, formal_terms_path, formal_terms_sha):
    errors = []
    warnings = []
    ids = [item['id'] for item in items]
    if len(ids) != len(set(ids)):
        errors.append('模型汇总 ID 重复')
    expected = {candidate['id'] for candidate in candidates}
    if set(ids) != expected:
        errors.append('模型汇总 ID 与候选集不一致')
    locks = [item for item in items if item['route'] == 'auto_lock']
    for item in locks:
        if not item['en_term'].strip() or not item['cn_term'].strip():
            errors.append(f'{item["id"]}: 锁定键或值为空')
        if '\n' in item['en_term'] or re.search(r'<[^>]*>|`[^`]*`', item['en_term']):
            errors.append(f'{item["id"]}: 锁定键含格式标签/换行')
        if len(item['en_term']) < 2:
            warnings.append(f'{item["id"]}: 锁定键过短')

    by_cn = defaultdict(list)
    for item in locks:
        by_cn[item['cn_term']].append(item['en_term'])
    for cn_term, english in by_cn.items():
        if len(english) > 1:
            warnings.append(f'同一中文 {cn_term!r} 对应多个英文: {english}')

    core_keys = {
        glossary_extract.canonical_term(term).casefold()
        for term in (*glossary_extract.CORE_TERMS,)
    }
    present = {item['en_term'].casefold() for item in items}
    missing_core = sorted(core_keys - present)
    if missing_core:
        errors.append(f'缺少核心术语结论: {missing_core}')

    current_formal_sha = sha256_file(formal_terms_path)
    if current_formal_sha != formal_terms_sha:
        errors.append('正式 glossary/terms.json 在 Phase 2 分类期间发生变化')
    return {
        'status': 'pass' if not errors else 'fail',
        'candidate_count': len(candidates),
        'result_count': len(items),
        'lock_count': len(locks),
        'model_lock_count': sum(item['action'] == 'lock' for item in items),
        'core_term_count': len(core_keys),
        'missing_core_terms': missing_core,
        'formal_terms_sha256_before': formal_terms_sha,
        'formal_terms_sha256_after': current_formal_sha,
        'errors': errors,
        'warnings': warnings,
    }


def main(argv=None):
    rp.load_env()
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidates', default='data/review/glossary/candidates.jsonl')
    parser.add_argument('--corpus', default='data/aligned/corpus.jsonl')
    parser.add_argument('--terms', default='glossary/terms.json')
    parser.add_argument('--system', default='prompt/glossary_system.md')
    parser.add_argument('--template', default='prompt/glossary_template.md')
    parser.add_argument('--schema', default='tools/glossary_schema.json')
    parser.add_argument('--review-dir', default='data/review/glossary')
    parser.add_argument('--backend', choices=('codex', 'api'),
                        default=rp.cfg('LLM_BACKEND', 'codex'))
    parser.add_argument('--model')
    parser.add_argument('--reasoning-effort',
                        choices=('none', 'low', 'medium', 'high', 'xhigh', 'max'),
                        default=rp.cfg('CODEX_REASONING_EFFORT', 'medium'))
    parser.add_argument('--batch-size', type=int, default=50)
    parser.add_argument('--concurrency', type=int, default=0)
    parser.add_argument('--max-batches', type=int, default=0)
    args = parser.parse_args(argv)
    if args.batch_size < 1:
        parser.error('--batch-size 必须大于 0')
    paths = [
        args.candidates, args.corpus, args.terms, args.system,
        args.template, args.schema,
    ]
    for path in paths:
        if not Path(path).is_file():
            parser.error(f'文件不存在: {path}')

    formal_terms_sha = sha256_file(args.terms)
    candidates = load_jsonl(args.candidates)
    candidate_ids = [item['id'] for item in candidates]
    if len(candidate_ids) != len(set(candidate_ids)):
        parser.error('候选 ID 重复')

    try:
        settings = rp.build_settings(args)
    except Exception as exc:
        print(f'错误: {exc}')
        return 2
    system_prompt = Path(args.system).read_text(encoding='utf-8')
    template = Path(args.template).read_text(encoding='utf-8')
    terms_raw = json.loads(Path(args.terms).read_text(encoding='utf-8'))
    seeds = {key: value for key, value in terms_raw.items() if not key.startswith('_')}

    settings_public = rp.public_settings(settings)
    hashes = {
        'corpus': sha256_file(args.corpus),
        'corpus_schema': sha256_file('tools/corpus_schema.json'),
        'p0_regression': sha256_file('data/aligned/regression_cases.json'),
        'formal_terms': formal_terms_sha,
        'candidates': sha256_file(args.candidates),
        'extractor': sha256_file('tools/glossary_extract.py'),
        'system_prompt': sha256_file(args.system),
        'template': sha256_file(args.template),
        'schema': sha256_file(args.schema),
    }
    config_hash = rp.sha256_value({
        'pipeline_version': PIPELINE_VERSION,
        'backend': rp.fingerprint_settings(settings),
        'batch_size': args.batch_size,
        'hashes': {key: value for key, value in hashes.items() if key != 'corpus'},
    })
    batches = [
        candidates[index:index + args.batch_size]
        for index in range(0, len(candidates), args.batch_size)
    ]
    if args.max_batches:
        batches = batches[:args.max_batches]
    selected = [item for batch in batches for item in batch]
    out_dir = Path(args.review_dir)
    batch_dir = out_dir / 'model_batches'
    manifest = {
        'pipeline_version': PIPELINE_VERSION,
        'created_at': rp.now_utc(),
        'backend': settings_public,
        'auth_status': settings.get('auth_status'),
        'batch_size': args.batch_size,
        'max_batches': args.max_batches,
        'candidate_count': len(candidates),
        'selected_candidates': len(selected),
        'scheduled_batches': len(batches),
        'formal_terms_protected': True,
        'formal_terms_overwrite_authorized': False,
        'config_hash': config_hash,
        'hashes': hashes,
    }
    rp.atomic_write_json(str(out_dir / 'run_manifest.json'), manifest)

    concurrency = args.concurrency
    if concurrency <= 0:
        concurrency = int(rp.cfg(
            'CODEX_CONCURRENCY' if settings['backend'] == 'codex'
            else 'LLM_CONCURRENCY', '1' if settings['backend'] == 'codex' else '4'))
    concurrency = max(1, concurrency)
    print(f'后端: {settings["backend"]} / 模型: {settings["model"]}')
    print(f'候选: {len(selected)} / 批次: {len(batches)} / 并发: {concurrency}')

    outcomes = []
    failures = []
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        future_map = {
            executor.submit(
                classify_batch, batch, index, system_prompt, template,
                settings, config_hash, batch_dir): index
            for index, batch in enumerate(batches)
        }
        for future in as_completed(future_map):
            index = future_map[future]
            try:
                outcome = future.result()
            except Exception as exc:
                print(f'  [异常] glossary batch_{index:04d}: {exc}')
                outcome = None
            if outcome:
                outcomes.append(outcome)
            else:
                failures.append(index)

    model_items = [item for outcome in outcomes for item in outcome['items']]
    items = enriched_items(selected, model_items)
    items.sort(key=lambda item: candidate_ids.index(item['id']))
    jsonl_write(out_dir / 'recommendations.jsonl', items)
    jsonl_write(
        out_dir / 'model_locks.jsonl',
        [item for item in items if item['action'] == 'lock'])
    jsonl_write(
        out_dir / 'suggested_locks.jsonl',
        [item for item in items if item['route'] == 'auto_lock'])
    jsonl_write(
        out_dir / 'needs_review.jsonl',
        [item for item in items if item['route'] == 'human_review'])
    jsonl_write(
        out_dir / 'rejected.jsonl',
        [item for item in items if item['action'] == 'reject'])

    conflicts = build_conflicts(items)
    json_write(out_dir / 'conflicts.json', conflicts)
    audit = seed_audit(items, seeds)
    json_write(out_dir / 'seed_audit.json', audit)
    core_keys = {
        glossary_extract.canonical_term(term).casefold()
        for term in (*glossary_extract.CORE_TERMS, *seeds)
    }
    core = [item for item in items if item['en_term'].casefold() in core_keys]
    json_write(out_dir / 'core_terms.json', core)
    write_review_csv(out_dir / 'glossary_review.csv', items)
    write_review_csv(
        out_dir / 'human_review.csv',
        [item for item in items if item['route'] == 'human_review'])
    validation = validate_outputs(
        selected, items, args.terms, formal_terms_sha)
    json_write(out_dir / 'glossary_validation.json', validation)

    actions = Counter(item['action'] for item in items)
    routes = Counter(item['route'] for item in items)
    categories = Counter(item['category'] for item in items)
    summary = {
        'expected_candidates': len(selected),
        'completed_candidates': len(items),
        'scheduled_batches': len(batches),
        'completed_batches': len(outcomes),
        'cached_batches': sum(outcome.get('cached', False) for outcome in outcomes),
        'failed_batches': sorted(failures),
        'actions': dict(sorted(actions.items())),
        'routes': dict(sorted(routes.items())),
        'categories': dict(sorted(categories.items())),
        'conflicts': len(conflicts),
        'seed_audit': dict(Counter(entry['status'] for entry in audit)),
        'validation_status': validation['status'],
        'usage_all_completed_batches': rp.sum_usage(outcomes),
        'usage_this_run': rp.sum_usage(
            [outcome for outcome in outcomes if not outcome.get('cached')]),
        'config_hash': config_hash,
        'updated_at': rp.now_utc(),
    }
    json_write(out_dir / 'recommendation_summary.json', summary)
    print('\n汇总:', json.dumps(summary, ensure_ascii=False, indent=1))
    return 1 if failures or validation['status'] != 'pass' else 0


if __name__ == '__main__':
    sys.exit(main())
