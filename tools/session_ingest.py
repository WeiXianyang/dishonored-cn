# -*- coding: utf-8 -*-
"""本会话 AI 反方二审结果的校验与落盘工具（替代 codex 后端的续跑路径）。

背景：Phase 4.5 release gate 的批次请求已固化在
    data/review/phase45/{critical,high}-run/requests/batch_XXXX.json
（含原始 input_hash / config_hash）。由于 ChatGPT/Codex 额度中断，改为
由当前会话的 AI（Reasonix）逐批裁决。本工具：

1. 读取 request（请求快照，自包含全部上下文）；
2. 读取本会话裁决结果（{"items": [...]}，字段遵循 review_schema.json）；
3. 复用 review_pipeline.validate_items + validate_hard_rules（terms 为空）
   做与 codex 批次完全相同的硬校验（id 全集、占位符、单写入规则等）；
4. 通过后以与原 codex 批次相同的 input_hash/config_hash 原子落盘为
   batch_XXXX.json（meta 标注 backend=session-ai 以便追溯）；
5. 重建该 run 目录的 results.jsonl / summary.json / wiki_lookup_queue.json，
   保持与 review_pipeline 输出同构，供 release_gate.py finalize 直接消费。

用法：
    python tools/session_ingest.py --request data/review/phase45/critical-run/requests/batch_0038.json \
        --result data/review/phase45/session/critical/batch_0038.json
    python tools/session_ingest.py --request ... --result ... --dry-run
"""
import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone

import review_pipeline as rp

BATCH_RE = re.compile(r'^batch_(\d{4})\.json$')


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def load_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def load_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]


def atomic_write_json(path, value):
    rp.atomic_write_json(path, value)


def atomic_write_jsonl(path, rows):
    rp.atomic_write_jsonl(path, rows)


def build_wiki_lookup_items(uncertain_items, request_entries_by_id):
    queue = []
    for item in uncertain_items:
        source = request_entries_by_id.get(item['id'], {})
        reason = item.get('uncertain_reason', '')
        marker = re.match(r'\s*\[WIKI_LOOKUP:\s*(.*?)\s*\]\s*', reason, re.I | re.S)
        queue.append({
            'id': item['id'],
            'en': source.get('en', ''),
            'cn': source.get('cn', ''),
            'context': source.get('context', ''),
            'model_action': item.get('action', ''),
            'model_new_text': item.get('new_text', ''),
            'confidence': item.get('confidence'),
            'uncertain_reason': reason,
            'suggested_wiki_query': (
                marker.group(1).strip() if marker else source.get('en', '')[:160]),
            'research_status': 'pending',
        })
    return queue


def rebuild_artifacts(review_dir, run_manifest, dry_run=False):
    """扫描 run 目录全部正式批次，重建 results.jsonl / summary.json / wiki_lookup_queue.json。"""
    batch_files = []
    for name in sorted(os.listdir(review_dir)):
        m = BATCH_RE.match(name)
        if m:
            batch_files.append((int(m.group(1)), os.path.join(review_dir, name)))
    batch_files.sort()
    all_items = []
    for _, path in batch_files:
        data = load_json(path)
        all_items.extend(data.get('items', []))

    auto = load_jsonl(os.path.join(review_dir, 'automatic_empty_keep.jsonl'))
    manual = load_jsonl(os.path.join(review_dir, 'unpaired_manual_review.jsonl'))

    atomic_write_jsonl(os.path.join(review_dir, 'results.jsonl'), all_items)
    actions = Counter(item['action'] for item in all_items)
    uncertain = [item for item in all_items if item.get('uncertain')]

    # 从请求快照收集每个 id 的 en/cn/context，供研究队列使用。
    requests_dir = os.path.join(review_dir, 'requests')
    request_entries_by_id = {}
    if os.path.isdir(requests_dir):
        for name in sorted(os.listdir(requests_dir)):
            m = BATCH_RE.match(name)
            if not m:
                continue
            req = load_json(os.path.join(requests_dir, name))
            for entry in req.get('entries', []):
                request_entries_by_id[entry['id']] = entry
    wiki_items = build_wiki_lookup_items(uncertain, request_entries_by_id)
    atomic_write_json(os.path.join(review_dir, 'wiki_lookup_queue.json'), {
        'source': 'all uncertain=true results',
        'lookup_site': 'https://dishonored.fandom.com/wiki/',
        'site_note': '用户指定的社区 Wiki；用于核实实体事实，不覆盖天邈中文底色。',
        'count': len(wiki_items),
        'items': wiki_items,
    })

    failed_batches = []
    failures_dir = os.path.join(review_dir, 'failures')
    if os.path.isdir(failures_dir):
        for name in sorted(os.listdir(failures_dir)):
            m = BATCH_RE.match(name)
            if m:
                failed_batches.append(int(m.group(1)))

    completed_batches = len(batch_files)
    covered = len(all_items) + len(auto) + len(manual)
    source_total = int(run_manifest.get('source_entries_selected', covered))
    summary = {
        'source_entries': source_total,
        'model_entries_selected': int(run_manifest.get('model_entries_selected', covered)),
        'expected_entries': int(run_manifest.get('scheduled_entries', covered)),
        'completed_entries': len(all_items),
        'automatic_empty_keep': len(auto),
        'unpaired_manual_review': len(manual),
        'covered_entries': covered,
        'coverage_rate': round(covered / max(source_total, 1), 6),
        'scheduled_batches': int(run_manifest.get('scheduled_batches', 0)),
        'completed_batches': completed_batches,
        'cached_batches': 0,
        'failed_batches': sorted(failed_batches),
        'actions': dict(actions),
        'uncertain': len(uncertain),
        'uncertain_rate': round(len(uncertain) / max(len(all_items), 1), 4),
        'wiki_lookup_queue': len(wiki_items),
        'usage_all_completed_batches': {},
        'usage_this_run': {},
        'config_hash': run_manifest.get('config_hash'),
        'updated_at': now_utc(),
    }
    atomic_write_json(os.path.join(review_dir, 'summary.json'), summary)
    print(f'[汇总] completed_batches={completed_batches} entries={len(all_items)} '
          f'actions={dict(actions)} uncertain={len(uncertain)} failed={sorted(failed_batches)}')


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--request', required=True,
                        help='requests/batch_XXXX.json 请求快照')
    parser.add_argument('--result', required=True,
                        help='本会话裁决结果文件 {"items": [...]}')
    parser.add_argument('--review-dir',
                        help='run 目录（默认从 --request 推导）')
    parser.add_argument('--dry-run', action='store_true',
                        help='只校验，不落盘')
    args = parser.parse_args(argv)

    request = load_json(args.request)
    entries = request['entries']
    expected_ids = [entry['id'] for entry in entries]
    input_hash = request['input_hash']
    config_hash = request['config_hash']
    batch_idx = request['batch']

    result = load_json(args.result)
    if isinstance(result, dict) and 'items' in result:
        raw_items = result['items']
    elif isinstance(result, list):
        raw_items = result
    else:
        parser.error('--result 必须是 {"items": [...]} 或裸数组')

    items = rp.validate_items(raw_items, expected_ids)
    items = rp.validate_hard_rules(items, entries, {})
    print(f'[OK] batch_{batch_idx:04d}: {len(items)} 条通过硬校验 '
          f'(input_hash={input_hash[:12]}… config_hash={config_hash[:12]}…)')

    if args.dry_run:
        print('[dry-run] 未落盘')
        return 0

    if args.review_dir:
        review_dir = args.review_dir
    else:
        review_dir = os.path.dirname(os.path.dirname(os.path.abspath(args.request)))
    os.makedirs(review_dir, exist_ok=True)

    meta = {
        'backend': 'session-ai',
        'model': 'reasonix-session-ai',
        'reasoning_effort': None,
        'input_hash': input_hash,
        'config_hash': config_hash,
        'completed_at': now_utc(),
        'usage': {},
        'attempts': 1,
        'retry_errors': [],
        'session_ingest': True,
        'ingest_script': 'session_ingest.py',
    }
    atomic_write_json(os.path.join(review_dir, f'batch_{batch_idx:04d}.json'), {
        'batch': batch_idx,
        'meta': meta,
        'items': items,
    })
    rp.safe_unlink(os.path.join(review_dir, 'failures', f'batch_{batch_idx:04d}.json'))

    run_manifest = load_json(os.path.join(review_dir, 'run_manifest.json'))
    rebuild_artifacts(review_dir, run_manifest)
    print(f'[落盘] batch_{batch_idx:04d}.json 已写入 {review_dir}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
