# -*- coding: utf-8 -*-
"""把独立 Agent 术语二审覆盖回 Phase 4 成品，并重建验收产物。"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import review_pipeline as rp
import phase4_prepare as p4p
import phase3_finalize as p3f


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


def load_terms(path):
    raw = json.loads(Path(path).read_text(encoding='utf-8'))
    return {key: value for key, value in raw.items() if not key.startswith('_')}


def merge_overrides(review_results, override_groups):
    base = index_unique(review_results, 'term review results')
    overrides = {}
    for label, rows in override_groups:
        current = index_unique(rows, label)
        duplicate = sorted(set(overrides) & set(current))
        unknown = sorted(set(current) - set(base))
        if duplicate:
            raise ValueError(f'术语二审覆盖重复 ID: {duplicate[:5]}')
        if unknown:
            raise ValueError(f'术语二审覆盖含未知 ID: {unknown[:5]}')
        overrides.update(current)
    return [overrides.get(row['id'], row) for row in review_results], len(overrides)


def apply_review(corpus, base_final_rows, review_corpus, review_results, terms):
    corpus_by_id = index_unique(corpus, 'corpus')
    base = index_unique(base_final_rows, 'base final')
    review_entries = index_unique(review_corpus, 'term review corpus')
    decisions = index_unique(review_results, 'term review results')
    if set(corpus_by_id) != set(base):
        raise ValueError('base final 与 corpus 覆盖不一致')
    if set(review_entries) != set(decisions):
        raise ValueError('term review results 覆盖不完整')
    if not set(review_entries) <= set(corpus_by_id):
        raise ValueError('term review corpus 含未知 ID')

    output = []
    human = []
    changed_by_review = 0
    reviewed_reverts = 0
    for entry in corpus:
        identifier = entry['id']
        original = entry.get('cn', '')
        base_row = dict(base[identifier])
        if identifier not in review_entries:
            output.append(base_row)
            if base_row.get('uncertain'):
                human.append({
                    'id': identifier, 'route': base_row.get('route', ''),
                    'context': entry.get('context', {}), 'en': entry.get('en', ''),
                    'game_context': p4p.build_game_context(entry),
                    'original_cn': original,
                    'candidate_cn': (base_row.get('new_text', '')
                                     if base_row.get('action') == 'fix' else original),
                    'reason': base_row.get('reason', ''),
                    'uncertain_reason': base_row.get('uncertain_reason', ''),
                })
            continue

        review_entry = review_entries[identifier]
        decision = decisions[identifier]
        baseline = review_entry.get('cn', '')
        desired = (decision.get('new_text', '')
                   if decision.get('action') == 'fix' else baseline)
        if decision.get('uncertain'):
            # 不让未经裁决的候选进入补丁；保持天邈原译并给人工完整候选。
            final = {
                **base_row, 'action': 'keep', 'new_text': '',
                'reason': '术语二审仍不确定，回退天邈原译并进入人工。',
                'confidence': float(decision.get('confidence', 0)),
                'uncertain': True,
                'uncertain_reason': decision.get('uncertain_reason', ''),
                'route': 'human_after_term_secondary_review',
                'term_reviewed': True,
            }
            human.append({
                'id': identifier, 'route': final['route'],
                'context': entry.get('context', {}), 'en': entry.get('en', ''),
                'game_context': p4p.build_game_context(entry),
                'original_cn': original, 'candidate_cn': desired,
                'reason': decision.get('reason', ''),
                'uncertain_reason': decision.get('uncertain_reason', ''),
                'term_review': review_entry.get('term_review', {}),
            })
            output.append(final)
            continue

        action = 'keep' if desired == original else 'fix'
        candidates = review_entry.get('term_review', {}).get('candidates', [])
        hard_pairs = set(rp.required_term_pairs(entry, terms))
        overrides = [{
            'en': value['en'], 'cn': value['cn'],
        } for value in candidates
            if (value.get('en'), value.get('cn')) in hard_pairs and
            value.get('cn') not in desired]
        final = {
            **base_row, 'action': action,
            'new_text': desired if action == 'fix' else '',
            'reason': decision.get('reason', ''),
            'confidence': float(decision.get('confidence', 0)),
            'uncertain': False, 'uncertain_reason': '',
            'route': 'term_secondary_review',
            'term_reviewed': True,
            'term_review_candidates': candidates,
        }
        if overrides:
            final['term_scope_overrides'] = overrides
        else:
            final.pop('term_scope_overrides', None)
        if desired != baseline:
            changed_by_review += 1
        if desired == original and baseline != original:
            reviewed_reverts += 1
        output.append(final)

    accepted = []
    violations = []
    for row in output:
        if row.get('action') != 'fix':
            continue
        entry = corpus_by_id[row['id']]
        item = {
            'id': row['id'], 'action': 'fix',
            'new_text': row.get('new_text', ''), '_old': entry.get('cn', ''),
            'term_scope_overrides': row.get('term_scope_overrides', []),
        }
        errors = []
        if not rp.check_placeholders(item, entry):
            errors.append('占位符/换行不一致')
        term_error = rp.check_terms(item, terms, entry)
        if term_error:
            errors.append(term_error)
        if errors:
            violations.append({'id': row['id'], 'errors': errors})
        accepted.append({
            **row, 'layer': entry.get('layer'),
            'context': entry.get('context', {}), 'en': entry.get('en', ''),
            'old_text': entry.get('cn', ''),
        })
    if violations:
        raise ValueError('术语二审最终硬违规: ' + json.dumps(
            violations[:10], ensure_ascii=False))

    summary = {
        'source_entries': len(corpus), 'reviewed_entries': len(review_entries),
        'changed_by_secondary_review': changed_by_review,
        'reverted_to_tianmiao': reviewed_reverts,
        'accepted_fixes': len(accepted), 'human_review': len(human),
        'actions': dict(sorted(Counter(
            row.get('action') for row in output).items())),
        'routes': dict(sorted(Counter(
            row.get('route', '') for row in output).items())),
    }
    return output, accepted, human, summary


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--corpus', default='data/aligned/corpus.jsonl')
    parser.add_argument('--base-final-dir', default='data/review/phase4-final')
    parser.add_argument('--review-corpus',
                        default='data/review/term-secondary/corpus.jsonl')
    parser.add_argument('--review-results',
                        default='data/review/term-secondary/run/results.jsonl')
    parser.add_argument('--review-override-results', action='append', default=[],
                        help='可重复；Wiki/本地上下文定向裁决 JSONL')
    parser.add_argument('--terms', default='glossary/terms.json')
    parser.add_argument('--out-dir',
                        default='data/review/phase4-term-reviewed')
    args = parser.parse_args(argv)

    base = Path(args.base_final_dir)
    review_results = read_jsonl(args.review_results)
    review_results, override_count = merge_overrides(review_results, [
        (f'term review override {path}', read_jsonl(path))
        for path in args.review_override_results])
    final_rows, accepted, human, summary = apply_review(
        read_jsonl(args.corpus), read_jsonl(base / 'final_results.jsonl'),
        read_jsonl(args.review_corpus), review_results,
        load_terms(args.terms))
    out = Path(args.out_dir)
    final_path = out / 'final_results.jsonl'
    accepted_path = out / 'accepted_fixes.jsonl'
    human_path = out / 'human_review.jsonl'
    rp.atomic_write_jsonl(str(final_path), final_rows)
    rp.atomic_write_jsonl(str(accepted_path), accepted)
    rp.atomic_write_jsonl(str(human_path), human)
    csv_rows = []
    for item in human:
        game = item.get('game_context', {}) or {}
        csv_rows.append({
            'id': item['id'], 'route': item.get('route', ''),
            'release': game.get('release', ''),
            'mission': game.get('mission', ''),
            'location': game.get('location', ''),
            'trigger': game.get('trigger', ''),
            'en': item.get('en', ''),
            'original_cn': item.get('original_cn', ''),
            'candidate_cn': item.get('candidate_cn', ''),
            'reason': item.get('reason', ''),
            'uncertain_reason': item.get('uncertain_reason', ''),
            'term_review': json.dumps(
                item.get('term_review', {}), ensure_ascii=False),
            'decision': '', 'decided_text': '', 'note': '',
        })
    p3f.atomic_write_csv(str(out / 'human_review.csv'), [
        'id', 'route', 'release', 'mission', 'location', 'trigger', 'en',
        'original_cn', 'candidate_cn', 'reason', 'uncertain_reason',
        'term_review', 'decision', 'decided_text', 'note',
    ], csv_rows)
    summary['created_at'] = rp.now_utc()
    summary['review_overrides'] = override_count
    summary['hashes'] = {
        'corpus': rp.sha256_file(args.corpus),
        'base_final': rp.sha256_file(str(base / 'final_results.jsonl')),
        'review_corpus': rp.sha256_file(args.review_corpus),
        'review_results': rp.sha256_file(args.review_results),
        'review_overrides': {
            path: rp.sha256_file(path) for path in args.review_override_results},
        'terms': rp.sha256_file(args.terms),
        'final_results': rp.sha256_file(str(final_path)),
        'accepted_fixes': rp.sha256_file(str(accepted_path)),
        'human_review': rp.sha256_file(str(human_path)),
    }
    rp.atomic_write_json(str(out / 'summary.json'), summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
