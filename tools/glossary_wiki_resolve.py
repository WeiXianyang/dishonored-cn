# -*- coding: utf-8 -*-
"""把 Wiki 核查结论叠加到 Phase 2 的 20 条疑难术语上。

原始两轮模型产物保持只读。本工具要求核查文件完整覆盖原来的人工审核
分区，并在独立目录生成新的 1,200 条完备分区，供最终化预览使用。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from phase1_extract import json_write, jsonl_write, sha256_file


ALLOWED_ACTIONS = {'lock', 'exclude', 'defer'}


def load_jsonl(path):
    with open(path, encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def corpus_support(corpus_path, support_terms):
    """为新组合译名找可回源的天邈中文组件证据。"""
    missing = set(support_terms)
    evidence = {}
    if not missing:
        return evidence
    with open(corpus_path, encoding='utf-8') as stream:
        for line in stream:
            if not line.strip():
                continue
            row = json.loads(line)
            chinese = row.get('cn', '')
            for term in list(missing):
                if term in chinese:
                    evidence[term] = row['id']
                    missing.remove(term)
            if not missing:
                break
    if missing:
        raise ValueError(f'本地 corpus 缺少中文组件证据: {sorted(missing)}')
    return evidence


def validate_wiki_decisions(wiki_decisions, deferred):
    errors = []
    deferred_by_id = {item['id']: item for item in deferred}
    if len(deferred_by_id) != len(deferred):
        errors.append('原始疑难分区存在重复 ID')
    seen = set()
    for item in wiki_decisions:
        item_id = item.get('id')
        if not item_id or item_id in seen:
            errors.append(f'Wiki 决策 ID 缺失或重复: {item_id!r}')
            continue
        seen.add(item_id)
        original = deferred_by_id.get(item_id)
        if not original:
            errors.append(f'Wiki 决策不属于原始疑难项: {item_id}')
            continue
        if item.get('en_term') != original.get('en_term'):
            errors.append(f'{item_id}: 英文术语与原始疑难项不一致')
        action = item.get('action')
        if action not in ALLOWED_ACTIONS:
            errors.append(f'{item_id}: action 非法: {action!r}')
        if action == 'lock' and not item.get('cn_term', '').strip():
            errors.append(f'{item_id}: lock 缺少 cn_term')
        if action != 'lock' and item.get('cn_term', '').strip():
            errors.append(f'{item_id}: 非 lock 决策不得提供全局 cn_term')
        if not item.get('reason', '').strip():
            errors.append(f'{item_id}: 缺少决策理由')
        urls = item.get('wiki_urls')
        if not isinstance(urls, list) or not urls or any(
                not isinstance(url, str) or
                not url.startswith('https://dishonored.fandom.com/wiki/')
                for url in urls):
            errors.append(f'{item_id}: Wiki URL 缺失或不属于指定 Wiki')
        support_terms = item.get('support_cn_terms', [])
        if not isinstance(support_terms, list) or any(
                not isinstance(term, str) or not term for term in support_terms):
            errors.append(f'{item_id}: support_cn_terms 非法')
    expected = set(deferred_by_id)
    if seen != expected:
        errors.append(
            f'Wiki 决策未完整覆盖原始疑难项: '
            f'缺少={sorted(expected - seen)} 多出={sorted(seen - expected)}')
    if errors:
        raise ValueError('；'.join(errors))


def merge_resolution(resolved, deferred, rejected, decisions, wiki_decisions,
                     corpus_path):
    validate_wiki_decisions(wiki_decisions, deferred)
    decision_by_id = {item['id']: dict(item) for item in decisions}
    deferred_by_id = {item['id']: item for item in deferred}
    all_support_terms = sorted({
        term for item in wiki_decisions
        for term in item.get('support_cn_terms', [])
    })
    support_ids = corpus_support(corpus_path, all_support_terms)

    merged_resolved = list(resolved)
    merged_deferred = []
    phase3_queue = []
    action_counts = Counter()
    for wiki in wiki_decisions:
        action_counts[wiki['action']] += 1
        original = deferred_by_id[wiki['id']]
        evidence_ids = list(original.get('evidence_ids', []))
        for term in wiki.get('support_cn_terms', []):
            evidence_id = support_ids[term]
            if evidence_id not in evidence_ids:
                evidence_ids.append(evidence_id)
        final_action = 'lock' if wiki['action'] == 'lock' else 'review'
        final_cn = wiki.get('cn_term', '').strip() if final_action == 'lock' else ''
        final_decision = dict(decision_by_id[wiki['id']])
        final_decision.update({
            'action': final_action,
            'cn_term': final_cn,
            'category': wiki.get('category', original.get('category', 'other')),
            'confidence': float(wiki['confidence']),
            'reason': wiki['reason'].strip(),
            'conflict': final_action != 'lock',
            'conflict_reason': (
                wiki.get('conflict_reason', '').strip()
                if final_action != 'lock' else ''),
            'evidence_ids': evidence_ids,
            'source': 'dishonored_fandom_wiki_resolution',
            'wiki_action': wiki['action'],
            'wiki_urls': wiki['wiki_urls'],
        })
        decision_by_id[wiki['id']] = final_decision

        if final_action == 'lock':
            merged_resolved.append({
                'id': wiki['id'], 'en_term': wiki['en_term'],
                'cn_term': final_cn,
                'category': final_decision['category'],
                'confidence': final_decision['confidence'],
                'reason': final_decision['reason'],
                'evidence_ids': evidence_ids,
                'source': 'dishonored_fandom_wiki_resolution',
                'wiki_urls': wiki['wiki_urls'],
            })
        else:
            deferred_item = dict(original)
            deferred_item.update({
                'action': 'review', 'cn_term': '',
                'confidence': final_decision['confidence'],
                'reason': final_decision['reason'],
                'conflict': True,
                'conflict_reason': final_decision['conflict_reason'],
                'evidence_ids': evidence_ids,
                'wiki_action': wiki['action'],
                'wiki_urls': wiki['wiki_urls'],
                'source': 'dishonored_fandom_wiki_resolution',
            })
            merged_deferred.append(deferred_item)
            phase3_queue.append({
                'id': wiki['id'], 'en_term': wiki['en_term'],
                'route': 'context_rule' if wiki['action'] == 'exclude'
                else 'targeted_translation',
                'reason': final_decision['reason'],
                'conflict_reason': final_decision['conflict_reason'],
                'evidence_ids': evidence_ids,
                'wiki_urls': wiki['wiki_urls'],
            })

    merged_resolved.sort(key=lambda item: item['en_term'].casefold())
    merged_deferred.sort(key=lambda item: item['en_term'].casefold())
    merged_rejected = sorted(rejected, key=lambda item: item['en_term'].casefold())
    merged_decisions = sorted(
        decision_by_id.values(), key=lambda item: item['en_term'].casefold())
    phase3_queue.sort(key=lambda item: item['en_term'].casefold())
    return {
        'resolved': merged_resolved,
        'deferred': merged_deferred,
        'rejected': merged_rejected,
        'decisions': merged_decisions,
        'phase3_queue': phase3_queue,
        'wiki_action_counts': dict(sorted(action_counts.items())),
        'support_ids': support_ids,
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--resolved',
        default='data/review/glossary/resolution/resolved_terms.jsonl')
    parser.add_argument(
        '--deferred',
        default='data/review/glossary/resolution/remaining_human_review.jsonl')
    parser.add_argument(
        '--rejected',
        default='data/review/glossary/resolution/resolved_rejected.jsonl')
    parser.add_argument(
        '--decisions',
        default='data/review/glossary/resolution/resolution_decisions.jsonl')
    parser.add_argument(
        '--wiki-decisions', default='docs/phase2-wiki-decisions.json')
    parser.add_argument('--corpus', default='data/aligned/corpus.jsonl')
    parser.add_argument('--formal-terms', default='glossary/terms.json')
    parser.add_argument(
        '--output-dir', default='data/review/glossary/wiki_resolution')
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    inputs = (
        args.resolved, args.deferred, args.rejected, args.decisions,
        args.wiki_decisions, args.corpus, args.formal_terms,
    )
    missing = [path for path in inputs if not Path(path).is_file()]
    if missing:
        print(json.dumps({'status': 'fail', 'missing': missing},
                         ensure_ascii=False, indent=1))
        return 2
    try:
        wiki_decisions = json.loads(
            Path(args.wiki_decisions).read_text(encoding='utf-8'))
        if not isinstance(wiki_decisions, list):
            raise ValueError('Wiki 决策顶层必须是数组')
        merged = merge_resolution(
            load_jsonl(args.resolved), load_jsonl(args.deferred),
            load_jsonl(args.rejected), load_jsonl(args.decisions),
            wiki_decisions, args.corpus)
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({'status': 'fail', 'error': str(exc)},
                         ensure_ascii=False, indent=1))
        return 1

    out_dir = Path(args.output_dir)
    outputs = {
        'resolved': out_dir / 'resolved_terms.jsonl',
        'deferred': out_dir / 'deferred_terms.jsonl',
        'rejected': out_dir / 'rejected_terms.jsonl',
        'decisions': out_dir / 'decisions.jsonl',
        'phase3_queue': out_dir / 'phase3_context_queue.jsonl',
    }
    for key, path in outputs.items():
        jsonl_write(path, merged[key])

    total = sum(len(merged[key]) for key in ('resolved', 'deferred', 'rejected'))
    errors = []
    if total != len(merged['decisions']):
        errors.append('最终分区总数与 decisions 数量不一致')
    partition_ids = [
        item['id'] for key in ('resolved', 'deferred', 'rejected')
        for item in merged[key]
    ]
    if len(partition_ids) != len(set(partition_ids)):
        errors.append('最终分区 ID 重叠')
    formal_sha = sha256_file(args.formal_terms)
    validation = {
        'status': 'pass' if not errors else 'fail',
        'candidate_count': len(merged['decisions']),
        'resolved_term_count': len(merged['resolved']),
        'remaining_human_review_count': len(merged['deferred']),
        'rejected_count': len(merged['rejected']),
        'wiki_input_count': len(wiki_decisions),
        'wiki_action_counts': merged['wiki_action_counts'],
        'phase3_context_queue_count': len(merged['phase3_queue']),
        'formal_terms_sha256_before': formal_sha,
        'formal_terms_sha256_after': formal_sha,
        'support_cn_evidence': merged['support_ids'],
        'errors': errors,
    }
    json_write(out_dir / 'validation.json', validation)
    source_hashes = {
        'original_resolved': sha256_file(args.resolved),
        'original_deferred': sha256_file(args.deferred),
        'original_rejected': sha256_file(args.rejected),
        'original_decisions': sha256_file(args.decisions),
        'wiki_decisions': sha256_file(args.wiki_decisions),
        'corpus': sha256_file(args.corpus),
    }
    manifest = {
        **validation,
        'source_hashes': source_hashes,
        'output_hashes': {
            key: sha256_file(path) for key, path in outputs.items()
        },
        'formal_terms_modified': False,
    }
    json_write(out_dir / 'manifest.json', manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=1))
    return 0 if validation['status'] == 'pass' else 1


if __name__ == '__main__':
    sys.exit(main())
