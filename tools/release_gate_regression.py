# -*- coding: utf-8 -*-
"""生成并验收 Phase 4.5 反方 Agent 的错误疫苗集。"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import release_gate as gate
import review_pipeline as rp


ALLOWED = {'accept', 'revert', 'research'}


def load_cases(path):
    rows = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(rows, list):
        raise ValueError('疫苗集顶层必须是数组')
    seen = set()
    for index, row in enumerate(rows):
        required = ('id', 'category', 'en', 'baseline', 'candidate',
                    'expected', 'why')
        if not isinstance(row, dict) or any(
                not isinstance(row.get(key), str) or not row[key]
                for key in required):
            raise ValueError(f'cases[{index}] 字段不完整')
        if row['id'] in seen:
            raise ValueError(f'重复疫苗 ID: {row["id"]}')
        if row['expected'] not in ALLOWED:
            raise ValueError(f'{row["id"]}: 非法 expected')
        seen.add(row['id'])
    return rows


def build_corpus(cases):
    output = []
    for row in cases:
        entry = {
            'id': row['id'], 'layer': 'int', 'status': 'aligned',
            'en': row['en'], 'cn': row['candidate'],
            'domain': {'release': 'regression_fixture'},
            'context': {
                'file': 'ReleaseGateRegression.int',
                'section': row['category'], 'key': 'm_Text', 'line': 1,
            },
            'prior_review': {'original_cn': row['baseline']},
            'escalation': {
                'reasons': ['release_gate_adversarial_review'],
                'risk': gate.risk_profile(
                    {'layer': 'int', 'en': row['en']},
                    row['baseline'], row['candidate'], 'fixture'),
                'single_write_rule': True,
            },
            'research_context': {
                'source_priority': [
                    'source_and_local_context', 'game_specific_wiki',
                    'official_or_primary_evidence', 'language_reference',
                ],
                'regression_category': row['category'],
            },
        }
        output.append(entry)
    return output


def verify(cases, corpus, results):
    case_by_id = gate.index_unique(cases, 'regression cases')
    corpus_by_id = gate.index_unique(corpus, 'regression corpus')
    result_by_id = gate.index_unique(results, 'regression results')
    errors = []
    if set(case_by_id) != set(result_by_id):
        errors.append('结果与疫苗 ID 覆盖不一致')
    counts = Counter()
    details = []
    for identifier, case in case_by_id.items():
        if identifier not in result_by_id:
            continue
        try:
            actual = gate.validate_critic_decision(
                corpus_by_id[identifier], result_by_id[identifier])
        except ValueError as exc:
            errors.append(str(exc))
            actual = 'contract_error'
        counts[actual] += 1
        passed = actual == case['expected']
        if not passed:
            errors.append(
                f'{identifier}: expected={case["expected"]}, actual={actual}')
        details.append({
            'id': identifier, 'category': case['category'],
            'expected': case['expected'], 'actual': actual, 'pass': passed,
        })
    return {
        'status': 'pass' if not errors else 'fail',
        'case_count': len(cases), 'counts': dict(sorted(counts.items())),
        'details': details, 'errors': errors,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--cases', default=(
        'research/localization_regression_cases.json'))
    parser.add_argument('--out-corpus', default=(
        'data/review/phase45/regression/corpus.jsonl'))
    parser.add_argument('--results')
    parser.add_argument('--verification', default=(
        'data/review/phase45/regression/verification.json'))
    args = parser.parse_args(argv)
    cases = load_cases(args.cases)
    corpus = build_corpus(cases)
    rp.atomic_write_jsonl(args.out_corpus, corpus)
    if not args.results:
        print(json.dumps({
            'status': 'prepared', 'cases': len(cases),
            'out': str(Path(args.out_corpus).resolve()),
            'sha256': rp.sha256_file(args.out_corpus),
        }, ensure_ascii=False, indent=2))
        return 0
    result = verify(cases, corpus, gate.read_jsonl(args.results))
    result['created_at'] = rp.now_utc()
    result['hashes'] = {
        'cases': rp.sha256_file(args.cases),
        'corpus': rp.sha256_file(args.out_corpus),
        'results': rp.sha256_file(args.results),
    }
    rp.atomic_write_json(args.verification, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
