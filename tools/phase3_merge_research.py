# -*- coding: utf-8 -*-
"""合并 Phase 3 自动 Fandom 证据与人工核查结论。"""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import review_pipeline as rp


STATUS_PRIORITY = {
    'resolved': 50,
    'direct_evidence': 40,
    'evidence_found': 35,  # 兼容早期校准产物，不建议用于正式全量。
    'context_hits': 20,
    'no_match': 10,
    'lookup_error': 0,
    'unresolved': 0,
}


def read_jsonl(path):
    with open(path, encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def validate_row(row, label, index):
    if not isinstance(row, dict):
        raise ValueError(f'{label}[{index}] 不是对象')
    for field in ('id', 'status', 'finding'):
        if not isinstance(row.get(field), str) or not row[field].strip():
            raise ValueError(f'{label}[{index}] 缺少非空 {field}')
    if 'sources' in row and not isinstance(row['sources'], list):
        raise ValueError(f'{label}[{index}].sources 必须是数组')


def resolved_signature(row):
    return rp.canonical_json({
        'recommended_action': row.get('recommended_action'),
        'recommended_text': row.get('recommended_text'),
        'recommended_text_guidance': row.get('recommended_text_guidance'),
        'finding': row.get('finding'),
    })


def merge_research(inputs, known_ids=None, corpus_order=None):
    """inputs: ``[(label, rows), ...]``；同 ID 可保留多层证据。"""
    merged = []
    seen_exact = set()
    duplicate_rows = 0
    unknown = []
    resolved_by_id = defaultdict(set)
    sequence = 0

    for label, rows in inputs:
        for index, raw in enumerate(rows):
            validate_row(raw, label, index)
            identifier = raw['id']
            if known_ids is not None and identifier not in known_ids:
                unknown.append(identifier)
            canonical = rp.canonical_json(raw)
            exact_key = (identifier, canonical)
            if exact_key in seen_exact:
                duplicate_rows += 1
                continue
            seen_exact.add(exact_key)
            row = dict(raw)
            row['research_source'] = label
            row['research_authority'] = (
                'adjudicated_conclusion' if row['status'] == 'resolved'
                else 'raw_direct_evidence' if row['status'] in (
                    'direct_evidence', 'evidence_found')
                else 'locator_only' if row['status'] in (
                    'context_hits', 'no_match') else 'none')
            row['_merge_sequence'] = sequence
            sequence += 1
            merged.append(row)
            if row['status'] == 'resolved':
                resolved_by_id[identifier].add(resolved_signature(row))

    if unknown:
        raise ValueError(f'研究记录含未知 corpus ID: {sorted(set(unknown))[:5]}')
    conflicts = sorted(
        identifier for identifier, signatures in resolved_by_id.items()
        if len(signatures) > 1)
    if conflicts:
        raise ValueError(f'同一 ID 存在互相冲突的 resolved 结论: {conflicts[:5]}')

    order = corpus_order or {}
    merged.sort(key=lambda row: (
        order.get(row['id'], 10 ** 12), row['id'],
        -STATUS_PRIORITY.get(row['status'], 5), row['_merge_sequence']))
    for row in merged:
        row.pop('_merge_sequence', None)
    stats = {
        'input_rows': sum(len(rows) for _label, rows in inputs),
        'output_rows': len(merged),
        'unique_ids': len({row['id'] for row in merged}),
        'exact_duplicates_suppressed': duplicate_rows,
        'status_counts': dict(Counter(row['status'] for row in merged)),
        'resolved_conflicts': 0,
    }
    return merged, stats


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', action='append', required=True,
                        help='可重复；自动证据与人工结论各传一次')
    parser.add_argument('--corpus', default='data/aligned/corpus.jsonl')
    parser.add_argument('--out', required=True)
    parser.add_argument('--manifest')
    args = parser.parse_args(argv)

    corpus = read_jsonl(args.corpus)
    known_ids = {row['id'] for row in corpus}
    corpus_order = {row['id']: index for index, row in enumerate(corpus)}
    inputs = [(str(Path(path).as_posix()), read_jsonl(path))
              for path in args.input]
    merged, stats = merge_research(
        inputs, known_ids=known_ids, corpus_order=corpus_order)
    rp.atomic_write_jsonl(args.out, merged)
    manifest = {
        'created_at': rp.now_utc(), **stats,
        'inputs': [
            {'path': str(Path(path).resolve()), 'rows': len(rows),
             'sha256': rp.sha256_file(path)}
            for path, (_label, rows) in zip(args.input, inputs)
        ],
        'hashes': {
            'corpus': rp.sha256_file(args.corpus),
            'output': rp.sha256_file(args.out),
        },
    }
    manifest_path = args.manifest or args.out + '.manifest.json'
    rp.atomic_write_json(manifest_path, manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
