# -*- coding: utf-8 -*-
"""确定性生成 Phase 3 冒烟/校准语料，覆盖高风险结构与四个版本。"""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from phase1_extract import json_write, jsonl_write, sha256_file


P0_IDS = {
    'upk:281290178F077DFEF82116B3B2F373B3',
    'upk:9EF2CA8AAC46376916E50EE7AC2E73BB',
}
RELEASE_QUOTAS_40 = {
    'base_game': 24,
    'knife_of_dunwall': 6,
    'brigmore_witches': 6,
    'dunwall_city_trials': 4,
}


def stable_key(row):
    return hashlib.sha256(row['id'].encode('utf-8')).hexdigest()


def release_of(row):
    domain = row.get('domain', {})
    return domain.get('primary_release') or domain.get('release') or 'unknown'


def select_layer(rows, target, required_ids=()):
    rows = sorted(rows, key=stable_key)
    chosen = []
    seen = set()

    def add(row):
        if len(chosen) < target and row['id'] not in seen:
            chosen.append(row)
            seen.add(row['id'])

    by_id = {row['id']: row for row in rows}
    for item_id in sorted(required_ids):
        if item_id in by_id:
            add(by_id[item_id])
    for row in rows:
        if row.get('status') in ('en_only', 'aligned_normalized'):
            add(row)

    feature_targets = (
        (lambda row: bool(row.get('domain', {}).get('long_text')), 10),
        (lambda row: bool(row.get('tags')), 12),
    )
    for predicate, count in feature_targets:
        have = sum(1 for row in chosen if predicate(row))
        for row in rows:
            if have >= min(count, target):
                break
            if row['id'] not in seen and predicate(row):
                add(row)
                have += 1

    multiplier = target / 40
    for release, base_quota in RELEASE_QUOTAS_40.items():
        quota = round(base_quota * multiplier)
        have = sum(1 for row in chosen if release_of(row) == release)
        for row in rows:
            if have >= quota:
                break
            if row['id'] not in seen and release_of(row) == release:
                add(row)
                have += 1
    for row in rows:
        add(row)
    if len(chosen) != target:
        raise ValueError(f'无法为该层选满 {target} 条，仅得到 {len(chosen)}')
    return chosen


def summary(rows):
    return {
        'count': len(rows),
        'layers': dict(Counter(row['layer'] for row in rows)),
        'statuses': dict(Counter(row['status'] for row in rows)),
        'releases': dict(Counter(release_of(row) for row in rows)),
        'long_text': sum(bool(row.get('domain', {}).get('long_text')) for row in rows),
        'tagged': sum(bool(row.get('tags')) for row in rows),
        'p0_ids': sorted(P0_IDS & {row['id'] for row in rows}),
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--corpus', default='data/aligned/corpus.jsonl')
    parser.add_argument('--output-dir', default='data/review/phase3-samples')
    args = parser.parse_args(argv)
    rows = [
        json.loads(line) for line in
        Path(args.corpus).read_text(encoding='utf-8').splitlines()
        if line.strip()
    ]
    reviewable = [
        row for row in rows
        if row.get('status') in ('aligned', 'aligned_normalized', 'en_only')
        and (row.get('en', '') or row.get('cn', ''))
    ]
    ints = [row for row in reviewable if row['layer'] == 'int']
    upks = [row for row in reviewable if row['layer'] == 'upk']
    selected_int = select_layer(ints, 120)
    selected_upk = select_layer(upks, 80, P0_IDS)
    smoke = selected_int[:40] + selected_upk[:40]
    calibration = selected_int + selected_upk
    out_dir = Path(args.output_dir)
    jsonl_write(out_dir / 'smoke_corpus.jsonl', smoke)
    jsonl_write(out_dir / 'calibration_corpus.jsonl', calibration)
    manifest = {
        'source_corpus_sha256': sha256_file(args.corpus),
        'selection': 'stable sha256 strata; required en_only/normalized/P0',
        'smoke': summary(smoke),
        'calibration': summary(calibration),
        'smoke_sha256': sha256_file(out_dir / 'smoke_corpus.jsonl'),
        'calibration_sha256': sha256_file(out_dir / 'calibration_corpus.jsonl'),
    }
    json_write(out_dir / 'manifest.json', manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
