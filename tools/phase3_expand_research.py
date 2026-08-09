# -*- coding: utf-8 -*-
"""把已裁决的 Phase 3 研究规则展开到所有匹配语料 ID。"""
import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import review_pipeline as rp


MATCH_FIELDS = ('en_exact', 'en_contains', 'en_regex')


def read_jsonl(path):
    with open(path, encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def validate_rule(rule, index):
    if not isinstance(rule, dict):
        raise ValueError(f'rules[{index}] 不是对象')
    for field in ('rule_id', 'status', 'finding'):
        if not isinstance(rule.get(field), str) or not rule[field].strip():
            raise ValueError(f'rules[{index}] 缺少非空 {field}')
    match_fields = [field for field in MATCH_FIELDS if field in rule]
    if len(match_fields) != 1:
        raise ValueError(
            f'{rule["rule_id"]}: 必须且只能指定一个 {MATCH_FIELDS}')
    if ('expected_count' not in rule or
            not isinstance(rule['expected_count'], int) or
            rule['expected_count'] < 1):
        raise ValueError(f'{rule["rule_id"]}: expected_count 必须为正整数')
    if 'sources' in rule and not isinstance(rule['sources'], list):
        raise ValueError(f'{rule["rule_id"]}: sources 必须是数组')
    if 'en_regex' in rule:
        re.compile(rule['en_regex'])


def rule_matches(entry, rule):
    source = entry.get('en', '') or ''
    case_sensitive = bool(rule.get('case_sensitive'))
    if 'en_exact' in rule:
        target = rule['en_exact']
        return source == target if case_sensitive else source.casefold() == target.casefold()
    if 'en_contains' in rule:
        target = rule['en_contains']
        return target in source if case_sensitive else target.casefold() in source.casefold()
    flags = 0 if case_sensitive else re.I
    return re.search(rule['en_regex'], source, flags) is not None


def expand_rules(corpus, rules):
    output = []
    counts = Counter()
    by_id = defaultdict(list)
    rule_ids = set()
    for index, rule in enumerate(rules):
        validate_rule(rule, index)
        rule_id = rule['rule_id']
        if rule_id in rule_ids:
            raise ValueError(f'重复 rule_id: {rule_id}')
        rule_ids.add(rule_id)
        matched = [entry for entry in corpus if rule_matches(entry, rule)]
        counts[rule_id] = len(matched)
        if len(matched) != rule['expected_count']:
            raise ValueError(
                f'{rule_id}: 预期命中 {rule["expected_count"]}，'
                f'实际 {len(matched)}；ID={[entry["id"] for entry in matched[:5]]}')
        resolution = {
            key: value for key, value in rule.items()
            if key not in (*MATCH_FIELDS, 'expected_count', 'case_sensitive')
        }
        for entry in matched:
            row = {
                'id': entry['id'], **resolution,
                'matched_rule': rule_id,
                'matched_en': entry.get('en', ''),
            }
            output.append(row)
            by_id[entry['id']].append(row)

    overlaps = {
        identifier: rows for identifier, rows in by_id.items() if len(rows) > 1}
    if overlaps:
        detail = {
            identifier: [row['matched_rule'] for row in rows]
            for identifier, rows in list(overlaps.items())[:5]
        }
        raise ValueError(
            '研究规则重叠；必须显式合并为单一规则: ' +
            json.dumps(detail, ensure_ascii=False))
    corpus_order = {entry['id']: index for index, entry in enumerate(corpus)}
    output.sort(key=lambda row: corpus_order[row['id']])
    return output, dict(counts)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--corpus', default='data/aligned/corpus.jsonl')
    parser.add_argument('--rules', default='research/phase3_manual_rules.json')
    parser.add_argument('--out', required=True)
    parser.add_argument('--manifest')
    args = parser.parse_args(argv)

    corpus = read_jsonl(args.corpus)
    rules = json.loads(Path(args.rules).read_text(encoding='utf-8'))
    if not isinstance(rules, list):
        raise ValueError('rules 顶层必须是数组')
    rows, counts = expand_rules(corpus, rules)
    rp.atomic_write_jsonl(args.out, rows)
    manifest = {
        'created_at': rp.now_utc(), 'rules': len(rules),
        'output_rows': len(rows), 'rule_match_counts': counts,
        'hashes': {
            'corpus': rp.sha256_file(args.corpus),
            'rules': rp.sha256_file(args.rules),
            'output': rp.sha256_file(args.out),
        },
    }
    manifest_path = args.manifest or args.out + '.manifest.json'
    rp.atomic_write_json(manifest_path, manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
