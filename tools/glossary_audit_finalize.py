# -*- coding: utf-8 -*-
"""把 619 项独立审计裁决编译成硬锁层、作用域参考层和完整策略账本。"""
from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from pathlib import Path

import review_pipeline as rp


POLICY_VERSION = 1
DECISIONS = {'keep_global', 'correct_global', 'restrict_scope', 'remove'}


def read_jsonl(path):
    with open(path, encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def load_hard_terms(path):
    raw = json.loads(Path(path).read_text(encoding='utf-8'))
    return {key: value for key, value in raw.items() if not key.startswith('_')}


def index_unique(rows, label):
    output = {}
    for row in rows:
        identifier = row.get('id')
        if not identifier or identifier in output:
            raise ValueError(f'{label} 存在空或重复 ID: {identifier!r}')
        output[identifier] = row
    return output


def build_outputs(terms, audit_entries, decisions, source_hashes):
    entries = index_unique(audit_entries, 'audit corpus')
    results = index_unique(decisions, 'audit results')
    if set(entries) != set(results):
        raise ValueError(
            f'审计覆盖不完整: 缺少={sorted(set(entries)-set(results))[:5]} '
            f'多出={sorted(set(results)-set(entries))[:5]}')
    entry_terms = {row.get('en_term') for row in entries.values()}
    if entry_terms != set(terms) or None in entry_terms:
        raise ValueError('audit corpus 与原硬锁术语集合不一致')

    hard_values = {}
    advisory_items = []
    policy_items = []
    counts = Counter()
    scopes = Counter()
    corrections = 0
    for identifier, entry in entries.items():
        item = results[identifier]
        english = entry['en_term']
        current = entry.get('current_cn', terms[english])
        decision = item.get('decision')
        scope = item.get('scope')
        proposed = item.get('proposed_cn', '')
        if decision not in DECISIONS:
            raise ValueError(f'{identifier}: 非法 decision {decision!r}')
        if decision == 'keep_global':
            if scope != 'global' or proposed != current:
                raise ValueError(f'{identifier}: keep_global 载荷不一致')
            hard_values[english] = current
        elif decision == 'correct_global':
            if scope != 'global' or not proposed or proposed == current:
                raise ValueError(f'{identifier}: correct_global 载荷不一致')
            hard_values[english] = proposed
            corrections += 1
        elif decision == 'restrict_scope':
            if scope not in {'exact_case', 'label_only', 'context_only'} or not proposed:
                raise ValueError(f'{identifier}: restrict_scope 载荷不一致')
            if proposed != current:
                corrections += 1
            advisory_items.append({
                'id': identifier, 'en_term': english, 'cn_term': proposed,
                'scope': scope, 'confidence': float(item.get('confidence', 0)),
                'reason': item.get('reason', ''),
                'evidence_ids': item.get('evidence_ids', []),
                'risk_tags': item.get('risk_tags', []),
                'previous_cn': current,
            })
        elif decision == 'remove':
            if scope != 'none' or proposed:
                raise ValueError(f'{identifier}: remove 载荷不一致')

        counts[decision] += 1
        scopes[scope] += 1
        policy_items.append({
            'id': identifier, 'en_term': english, 'previous_cn': current,
            'decision': decision, 'cn_term': proposed, 'scope': scope,
            'confidence': float(item.get('confidence', 0)),
            'reason': item.get('reason', ''),
            'evidence_ids': item.get('evidence_ids', []),
            'risk_tags': item.get('risk_tags', []),
        })

    ordered_hard = dict(sorted(hard_values.items(), key=lambda row: row[0].casefold()))
    advisory_items.sort(key=lambda row: row['en_term'].casefold())
    policy_items.sort(key=lambda row: row['en_term'].casefold())
    hard = {
        '_note': ('独立 Agent 全量审计后，仅保留可跨语境全局硬锁的术语；'
                  '受限项见 advisory_terms.json，完整裁决见 term_policies.json。'),
        '_schema_version': 3,
        '_term_count': len(ordered_hard),
        '_policy': 'independent-audit-global-only-secondary-review-on-insertion',
        **ordered_hard,
    }
    advisory = {
        '_note': ('这些译法仅是带作用域的参考候选，不是硬约束；任何从候选直接'
                  '引入的译值都必须由独立 Agent 二次复核。'),
        '_schema_version': 1,
        '_term_count': len(advisory_items),
        'items': advisory_items,
    }
    policies = {
        '_note': '原 619 项硬锁术语的逐项独立 Agent 审计账本。',
        '_schema_version': POLICY_VERSION,
        '_source_hashes': source_hashes,
        '_term_count': len(policy_items),
        'items': policy_items,
    }
    summary = {
        'source_terms': len(terms), 'hard_global_terms': len(ordered_hard),
        'advisory_terms': len(advisory_items),
        'removed_terms': counts['remove'], 'corrected_values': corrections,
        'decisions': dict(sorted(counts.items())),
        'scopes': dict(sorted(scopes.items())),
        'source_hashes': source_hashes,
    }
    return hard, advisory, policies, summary


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--terms', default='glossary/terms.json')
    parser.add_argument('--audit-corpus',
                        default='data/review/glossary-audit/audit_corpus.jsonl')
    parser.add_argument('--audit-results',
                        default='data/review/glossary-audit/results.jsonl')
    parser.add_argument('--preview-dir',
                        default='data/review/glossary-audit/finalized')
    parser.add_argument('--glossary-dir', default='glossary')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)

    terms = load_hard_terms(args.terms)
    entries = read_jsonl(args.audit_corpus)
    decisions = read_jsonl(args.audit_results)
    hashes = {
        'terms_before': rp.sha256_file(args.terms),
        'audit_corpus': rp.sha256_file(args.audit_corpus),
        'audit_results': rp.sha256_file(args.audit_results),
    }
    hard, advisory, policies, summary = build_outputs(
        terms, entries, decisions, hashes)
    preview = Path(args.preview_dir)
    rp.atomic_write_json(str(preview / 'terms.json'), hard)
    rp.atomic_write_json(str(preview / 'advisory_terms.json'), advisory)
    rp.atomic_write_json(str(preview / 'term_policies.json'), policies)
    summary['hashes'] = {
        'hard_terms': rp.sha256_file(str(preview / 'terms.json')),
        'advisory_terms': rp.sha256_file(str(preview / 'advisory_terms.json')),
        'term_policies': rp.sha256_file(str(preview / 'term_policies.json')),
    }
    rp.atomic_write_json(str(preview / 'summary.json'), summary)

    if args.apply:
        glossary = Path(args.glossary_dir)
        glossary.mkdir(parents=True, exist_ok=True)
        backup = glossary / 'terms.pre-glossary-audit.json'
        if not backup.exists():
            shutil.copyfile(args.terms, backup)
        rp.atomic_write_json(str(glossary / 'terms.json'), hard)
        rp.atomic_write_json(str(glossary / 'advisory_terms.json'), advisory)
        rp.atomic_write_json(str(glossary / 'term_policies.json'), policies)
        rp.atomic_write_json(str(glossary / 'glossary_audit_summary.json'), summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
