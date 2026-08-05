# -*- coding: utf-8 -*-
"""AI 校对流水线：对照英文原文审核天邈中文，输出结构化修改提案。

流程：
    corpus.jsonl + glossary/terms.json + prompt/template.md
        -> 分批 -> LLM API -> data/review/batch_{i}.json
        -> 汇总 data/review/summary.json

断点续跑：已存在的 batch 文件自动跳过。重试：API/解析错误重试 3 次。

配置（环境变量或 .env）：
    LLM_API_BASE   如 https://api.deepseek.com/v1
    LLM_API_KEY
    LLM_MODEL      如 deepseek-chat
    LLM_BATCH_SIZE 默认 40
    LLM_CONCURRENCY 默认 4（线程数）
"""
import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

import urllib.request

sys.path.insert(0, os.path.dirname(__file__))

REVIEW_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'review')


# ---------- 配置 ----------

def load_env(path='.env'):
    if not os.path.exists(path):
        return
    for line in open(path, encoding='utf-8'):
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def cfg(name, default=None):
    return os.environ.get(name, default)


# ---------- LLM 客户端 ----------

def call_llm(system_prompt, user_prompt, temperature=0.2, max_tokens=16000):
    url = cfg('LLM_API_BASE', 'https://api.deepseek.com/v1').rstrip('/') + '/chat/completions'
    body = {
        'model': cfg('LLM_MODEL', 'deepseek-chat'),
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ],
        'temperature': temperature,
        'max_tokens': int(cfg('LLM_MAX_TOKENS', max_tokens)),
        'response_format': {'type': 'json_object'},
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode('utf-8'),
        headers={
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + cfg('LLM_API_KEY', ''),
        },
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    return data['choices'][0]['message']['content']


def parse_response(content, expected_ids):
    """解析模型输出：JSON 数组或 {"items": [...]}；校验 id 集合"""
    content = content.strip()
    # 去掉可能的 ```json ... ``` 围栏
    m = re.match(r'```(?:json)?\s*(.*?)\s*```', content, re.S)
    if m:
        content = m.group(1)
    data = json.loads(content)
    if isinstance(data, dict):
        data = data.get('items') or data.get('results') or []
    if not isinstance(data, list):
        raise ValueError('输出不是 JSON 数组')
    out = []
    for item in data:
        if not isinstance(item, dict) or 'id' not in item:
            continue
        item.setdefault('action', 'keep')
        item.setdefault('new_text', '')
        item.setdefault('reason', '')
        item.setdefault('confidence', 0.0)
        item.setdefault('uncertain', False)
        item.setdefault('uncertain_reason', '')
        out.append(item)
    got = {i['id'] for i in out}
    if got != set(expected_ids):
        raise ValueError(f'id 集合不匹配: 期望 {len(expected_ids)} 实得 {len(got)}')
    return out


# ---------- 校验与后处理 ----------

def check_terms(item, terms):
    """校验：术语表锁定的译名若在原译文 cn 中出现，则修补后必须保留。
    返回 None=通过；返回字符串=冲突说明。"""
    if item['action'] != 'fix':
        return None
    old = item.get('_old', '') or ''
    new = item['new_text'] or ''
    conflicts = []
    for en, cn in terms.items():
        if not cn:
            continue
        if cn in old and cn not in new:
            conflicts.append(f'术语[{en}]={cn} 被移除')
    return '；'.join(conflicts) if conflicts else None


def check_placeholders(item):
    """new_text 的占位标签 <XX/> 与 `...` 必须与原文一致"""
    if item['action'] != 'fix':
        return True
    old_tags = re.findall(r'<[^>]*>', item.get('_old', ''))
    new_tags = re.findall(r'<[^>]*>', item['new_text'])
    if old_tags != new_tags:
        return False
    old_back = re.findall(r'`[^`]*`', item.get('_old', ''))
    new_back = re.findall(r'`[^`]*`', item['new_text'])
    return old_back == new_back


# ---------- 主流程 ----------

def build_batches(corpus, batch_size, upk_group=True):
    """分批：upk 层按 dialog_path 前缀分组保语境；int 层按文件分组"""
    int_items = [c for c in corpus if c['layer'] == 'int']
    upk_items = [c for c in corpus if c['layer'] == 'upk']
    batches = []

    def chunk(items, size):
        for i in range(0, len(items), size):
            yield items[i:i + size]

    for c in chunk(int_items, batch_size):
        batches.append(c)

    # upk：按关卡前缀聚合（DLC06_DaudsBase 等），组内再切 batch
    from collections import defaultdict
    groups = defaultdict(list)
    for c in upk_items:
        path = c['context'].get('dialog_path', '') or ''
        key = path.split('.')[0] if path else 'unknown'
        groups[key].append(c)
    for key, items in sorted(groups.items()):
        for c in chunk(items, batch_size):
            batches.append(c)
    return batches


def review_batch(batch, system_prompt, template, terms, batch_idx):
    """处理一批：组装 prompt -> 调 LLM -> 校验 -> 落盘"""
    out_path = os.path.join(REVIEW_DIR, f'batch_{batch_idx:04d}.json')
    if os.path.exists(out_path):
        print(f'  [跳过] batch_{batch_idx:04d}（已存在）')
        return None

    lines = []
    for i, c in enumerate(batch):
        ctx = c['context']
        ctx_str = ', '.join(f'{k}={v}' for k, v in ctx.items() if v)
        lines.append(json.dumps({
            'id': c['id'],
            'context': ctx_str,
            'en': c['en'],
            'cn': c['cn'],
            'tags': c['tags'],
        }, ensure_ascii=False))

    terms_text = '\n'.join(f'- {en} -> {cn}' for en, cn in terms.items()) or '(空)'
    user_prompt = (template.replace('{terms}', terms_text)
                   .replace('{entries}', '\n'.join(lines)))

    for attempt in range(3):
        try:
            content = call_llm(system_prompt, user_prompt)
            results = parse_response(content, [c['id'] for c in batch])
            # 关联旧文与占位符检查
            old_by_id = {c['id']: c for c in batch}
            for r in results:
                r['_old'] = old_by_id[r['id']]['cn']
                if r['action'] == 'fix':
                    if not check_placeholders(r):
                        r['action'] = 'keep'
                        r['reason'] += ' [占位符不一致，已回退为keep]'
                    else:
                        t = check_terms(r, terms)
                        if t:
                            r['action'] = 'keep'
                            r['reason'] += f' [{t}，已回退为keep]'
            os.makedirs(REVIEW_DIR, exist_ok=True)
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump({'batch': batch_idx, 'items': results},
                          f, ensure_ascii=False, indent=1)
            print(f'  [OK] batch_{batch_idx:04d}: {len(results)} 条')
            return results
        except Exception as e:
            print(f'  [重试 {attempt + 1}/3] batch_{batch_idx:04d}: {e}')
            time.sleep(3 * (attempt + 1))
    print(f'  [失败] batch_{batch_idx:04d}')
    return None


def main():
    load_env()
    ap = argparse.ArgumentParser()
    ap.add_argument('--corpus', default='data/aligned/corpus.jsonl')
    ap.add_argument('--terms', default='glossary/terms.json')
    ap.add_argument('--template', default='prompt/template.md')
    ap.add_argument('--batch-size', type=int, default=int(cfg('LLM_BATCH_SIZE', 40)))
    ap.add_argument('--only', help='只处理该 id 前缀（如 int:Bridge 或 upk:），用于调试')
    ap.add_argument('--max-batches', type=int, default=0, help='最多处理 N 批（0=全部）')
    args = ap.parse_args()

    if not cfg('LLM_API_KEY'):
        print('错误: 未设置 LLM_API_KEY（写入 .env 或环境变量）')
        sys.exit(1)

    corpus = [json.loads(l) for l in open(args.corpus, encoding='utf-8')]
    if args.only:
        corpus = [c for c in corpus if c['id'].startswith(args.only)]
    # 只校对已有中英对照的条目
    corpus = [c for c in corpus if c['status'] == 'aligned']
    print(f'语料: {len(corpus)} 条（仅 aligned）')

    terms = {}
    if os.path.exists(args.terms):
        raw = json.load(open(args.terms, encoding='utf-8'))
        terms = {k: v for k, v in raw.items() if not k.startswith('_')}
    print(f'术语表: {len(terms)} 条')

    base = os.path.dirname(os.path.abspath(__file__))
    system_prompt = open(os.path.join(base, '..', 'prompt', 'system.md'), encoding='utf-8').read()
    template = open(args.template, encoding='utf-8').read()

    batches = build_batches(corpus, args.batch_size)
    if args.max_batches:
        batches = batches[:args.max_batches]
    print(f'批次: {len(batches)}')

    concurrency = int(cfg('LLM_CONCURRENCY', 4))
    all_results = []
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futs = {
            ex.submit(review_batch, b, system_prompt, template, terms, i): i
            for i, b in enumerate(batches)
        }
        for fut in as_completed(futs):
            r = fut.result()
            if r:
                all_results.extend(r)

    # 汇总
    cnt = Counter(r['action'] for r in all_results)
    unc = [r for r in all_results if r.get('uncertain')]
    summary = {
        'total': len(all_results),
        'actions': dict(cnt),
        'uncertain': len(unc),
        'uncertain_rate': round(len(unc) / max(len(all_results), 1), 4),
    }
    os.makedirs(REVIEW_DIR, exist_ok=True)
    with open(os.path.join(REVIEW_DIR, 'summary.json'), 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    print('\n汇总:', summary)
    if unc:
        print(f'\n不确定条目 {len(unc)} 条（进入人工审核）：')
        for r in unc[:10]:
            print(f'  {r["id"]}: {r.get("uncertain_reason", "")[:60]}')


if __name__ == '__main__':
    main()
