# -*- coding: utf-8 -*-
"""独立验收术语全量审计覆盖、作用域和已知高风险锚点。"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import glossary_audit as ga
import review_pipeline as rp


def read_jsonl(path):
    with open(path, encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def verify(entries, results, hard_terms=None, advisory_items=None):
    errors = []
    try:
        ga.validate_items([
            {key: row[key] for key in ga.OUTPUT_FIELDS}
            for row in results
        ], entries)
    except Exception as exc:
        errors.append(str(exc))
    entry_by_id = {row['id']: row for row in entries}
    result_by_term = {
        entry_by_id[row['id']]['en_term']: row
        for row in results if row.get('id') in entry_by_id
    }

    def require(term, predicate, message):
        item = result_by_term.get(term)
        if item is None:
            errors.append(f'高风险锚点缺失: {term}')
        elif not predicate(item):
            errors.append(f'{term}: {message}; 实际={item}')

    require("Regent's Safe", lambda x: x['decision'] == 'restrict_scope',
            '保险箱短词不得继续全局硬锁')
    require("Regent's Safe Room", lambda x:
            '安全' in x['proposed_cn'] and '保险箱' not in x['proposed_cn'],
            'safe room 必须是安全屋/安全室，不能是保险箱室')
    require("Assassin's Blade", lambda x: x['decision'] == 'restrict_scope',
            '武器标签不得覆盖普通所有格短语')
    require('Wedding Band', lambda x:
            bool(x['proposed_cn']) and '缎带' not in x['proposed_cn'],
            'wedding band 的物件类型是婚戒')
    require('Arc Mine Extra Charge', lambda x:
            bool(x['proposed_cn']) and '过充' not in x['proposed_cn'],
            'extra charge 不是 overcharge')
    require('Estate Key', lambda x: x['decision'] == 'restrict_scope',
            '跨 DLC 的 estate key 指代不同庄园')
    require('Locker Key', lambda x:
            bool(x['proposed_cn']) and '抽屉' not in x['proposed_cn'],
            'locker 不是抽屉')

    if hard_terms is not None and advisory_items is not None:
        advisory_names = {row['en_term'] for row in advisory_items}
        overlap = sorted(set(hard_terms) & advisory_names)
        if overlap:
            errors.append(f'硬锁与作用域候选重叠: {overlap[:5]}')
        for term, item in result_by_term.items():
            should_hard = item['decision'] in {'keep_global', 'correct_global'}
            if should_hard != (term in hard_terms):
                errors.append(f'{term}: 审计决策与硬锁输出不一致')
            should_advisory = item['decision'] == 'restrict_scope'
            if should_advisory != (term in advisory_names):
                errors.append(f'{term}: 审计决策与参考层输出不一致')

    return {
        'status': 'pass' if not errors else 'fail',
        'counts': {
            'audit_entries': len(entries), 'results': len(results),
            'decisions': dict(sorted(Counter(
                row.get('decision') for row in results).items())),
            'hard_terms': len(hard_terms or {}),
            'advisory_terms': len(advisory_items or []),
        },
        'known_risk_anchors': [
            "Regent's Safe", "Regent's Safe Room", "Assassin's Blade",
            'Wedding Band', 'Arc Mine Extra Charge', 'Estate Key', 'Locker Key',
        ],
        'errors': errors,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--audit-corpus',
                        default='data/review/glossary-audit/audit_corpus.jsonl')
    parser.add_argument('--results',
                        default='data/review/glossary-audit/results.jsonl')
    parser.add_argument('--terms', default='glossary/terms.json')
    parser.add_argument('--advisory', default='glossary/advisory_terms.json')
    parser.add_argument('--out',
                        default='data/review/glossary-audit/verification.json')
    args = parser.parse_args(argv)
    raw_terms = json.loads(Path(args.terms).read_text(encoding='utf-8'))
    hard = {key: value for key, value in raw_terms.items()
            if not key.startswith('_')}
    raw_advisory = json.loads(Path(args.advisory).read_text(encoding='utf-8'))
    advisory = raw_advisory.get('items', raw_advisory)
    report = verify(
        read_jsonl(args.audit_corpus), read_jsonl(args.results), hard, advisory)
    report['created_at'] = rp.now_utc()
    report['hashes'] = {
        'audit_corpus': rp.sha256_file(args.audit_corpus),
        'results': rp.sha256_file(args.results),
        'terms': rp.sha256_file(args.terms),
        'advisory': rp.sha256_file(args.advisory),
    }
    rp.atomic_write_json(args.out, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
