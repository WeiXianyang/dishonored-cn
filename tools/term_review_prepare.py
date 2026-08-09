# -*- coding: utf-8 -*-
"""为既有 Phase 4 成品补建“术语直接应用”独立 Agent 复审队列。"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import review_pipeline as rp


def read_jsonl(path):
    with open(path, encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def index_unique(rows, label):
    output = {}
    for row in rows:
        identifier = row.get('id')
        if not identifier or identifier in output:
            raise ValueError(f'{label} 存在空或重复 ID: {identifier!r}')
        output[identifier] = row
    return output


def policy_matches(entry, policies):
    source = entry.get('en', '')
    matches = []
    for item in policies:
        english = item['en_term']
        if english.casefold() not in source.casefold():
            continue
        spans = rp.english_term_spans(
            source, english, case_sensitive_single_terms=False)
        if spans:
            matches.append((min(start for start, _end in spans), item))
    return [item for _start, item in sorted(
        matches, key=lambda value: (
            value[0], -len(value[1]['en_term']),
            value[1]['en_term'].casefold()))]


def effective_text(entry, final):
    return (final.get('new_text', '') if final.get('action') == 'fix'
            else entry.get('cn', ''))


def build_review_corpus(corpus, final_rows, policies):
    final = index_unique(final_rows, 'final results')
    if set(final) != {row['id'] for row in corpus}:
        raise ValueError('final results 与 corpus ID 覆盖不一致')
    selected = []
    reason_counts = Counter()
    policy_counts = Counter()
    for entry in corpus:
        row = final[entry['id']]
        current = effective_text(entry, row)
        old = entry.get('cn', '')
        matched = policy_matches(entry, policies)
        if not matched:
            continue
        reasons = []
        introduced = [item for item in matched
                      if item.get('previous_cn') and
                      item['previous_cn'] not in old and
                      item['previous_cn'] in current]
        corrected = [item for item in matched
                     if item.get('cn_term') and
                     item.get('cn_term') != item.get('previous_cn')]
        if introduced:
            reasons.append('direct_term_value_introduced')
        if corrected:
            reasons.append('audited_term_value_changed')
        if row.get('action') == 'fix' and '术语' in row.get('reason', ''):
            reasons.append('phase4_reason_cites_glossary')
        if not reasons:
            continue

        candidates = []
        for item in matched:
            value = item.get('cn_term') or item.get('previous_cn', '')
            candidates.append({
                'id': item.get('id', ''), 'en': item['en_term'], 'cn': value,
                'previous_cn': item.get('previous_cn', ''),
                'decision': item.get('decision', ''),
                'scope': item.get('scope', ''),
                'confidence': item.get('confidence'),
                'reason': item.get('reason', ''),
                'risk_tags': item.get('risk_tags', []),
                'source': 'full_glossary_audit',
                'requires_secondary_review': True,
                'old_contains_approved': value in old if value else False,
                'candidate_contains_approved': value in current if value else False,
            })
            policy_counts[item.get('decision', '')] += 1

        review = dict(entry)
        review['cn'] = current
        review['status'] = 'aligned'
        review['prior_review'] = {
            'original_cn': old,
            'medium_action': row.get('action'),
            'medium_candidate_cn': current,
            'medium_reason': row.get('reason', ''),
            'medium_confidence': row.get('confidence'),
            'medium_uncertain': row.get('uncertain', False),
            'medium_uncertain_reason': row.get('uncertain_reason', ''),
            'source_phase': 'phase4_final',
        }
        review['escalation'] = {
            'reasons': reasons,
            'original_status': entry.get('status', ''),
        }
        review['term_review'] = {
            'mode': 'agent_secondary_review', 'candidates': candidates,
        }
        selected.append(review)
        reason_counts.update(reasons)

    stats = {
        'source_entries': len(corpus), 'selected_entries': len(selected),
        'reason_counts': dict(sorted(reason_counts.items())),
        'matched_policy_decisions': dict(sorted(policy_counts.items())),
    }
    return selected, stats


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--corpus', default='data/aligned/corpus.jsonl')
    parser.add_argument('--final-results',
                        default='data/review/phase4-final/final_results.jsonl')
    parser.add_argument('--policies', default='glossary/term_policies.json')
    parser.add_argument('--out',
                        default='data/review/term-secondary/corpus.jsonl')
    parser.add_argument('--summary',
                        default='data/review/term-secondary/prepare_summary.json')
    args = parser.parse_args(argv)

    raw_policies = json.loads(Path(args.policies).read_text(encoding='utf-8'))
    policies = raw_policies.get('items', raw_policies)
    selected, stats = build_review_corpus(
        read_jsonl(args.corpus), read_jsonl(args.final_results), policies)
    rp.atomic_write_jsonl(args.out, selected)
    stats['created_at'] = rp.now_utc()
    stats['hashes'] = {
        'corpus': rp.sha256_file(args.corpus),
        'final_results': rp.sha256_file(args.final_results),
        'policies': rp.sha256_file(args.policies),
        'output': rp.sha256_file(args.out),
    }
    rp.atomic_write_json(args.summary, stats)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
