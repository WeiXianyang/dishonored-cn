# -*- coding: utf-8 -*-
"""汇总并验收 Phase 1 的 INT + UPK 对齐语料。"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from phase1_extract import atomic_replace, json_write, jsonl_write, sha256_file


REQUIRED = {'id', 'layer', 'context', 'en', 'cn', 'tags', 'status'}
P0 = {
    '281290178F077DFEF82116B3B2F373B3': {
        'expected_en': "We're counting on you.",
        'bad_cn': '我们取决于你',
        'problem': 'count on 被错译为“取决于”',
    },
    '9EF2CA8AAC46376916E50EE7AC2E73BB': {
        'expected_en': "I'm trapped!",
        'bad_cn': '我中陷阱了',
        'problem': 'trapped 被错译为“中了陷阱”',
    },
}


def load_jsonl(path):
    rows = []
    with open(path, encoding='utf-8') as f:
        for number, line in enumerate(f, 1):
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f'{path}:{number}: JSON 无效: {exc}') from exc
    return rows


def format_tokens(text):
    patterns = (
        r'<[^>]*>',
        r'`[^`]+`',
        r'\\[rnt]',
        r'%(?:\d+\$)?[-+#0 ]*(?:\d+|\*)?(?:\.\d+)?[diouxXeEfFgGcrs%]',
        r'\{[A-Za-z_][A-Za-z0-9_.:-]*\}',
    )
    tokens = []
    for pattern in patterns:
        tokens.extend(re.findall(pattern, text or ''))
    return sorted(tokens)


def validate_rows(rows, int_expected, upk_expected):
    blockers = []
    ids = Counter()
    for number, row in enumerate(rows, 1):
        missing = sorted(REQUIRED - set(row))
        if missing:
            blockers.append({'id': row.get('id', f'line:{number}'), 'type': 'schema_missing',
                             'detail': missing})
            continue
        rid = row['id']
        ids[rid] += 1
        if row['layer'] not in ('int', 'upk'):
            blockers.append({'id': rid, 'type': 'invalid_layer'})
        if not isinstance(row['context'], dict) or not isinstance(row['tags'], list):
            blockers.append({'id': rid, 'type': 'invalid_container_type'})
        if not isinstance(row['en'], str) or not isinstance(row['cn'], str):
            blockers.append({'id': rid, 'type': 'invalid_text_type'})
        target = row['cn'] if row['cn'] or row['status'] != 'en_only' else row['en']
        stored = sorted(row['tags'])
        expected_stored = sorted(re.findall(r'<[^>]*>|`[^`]+`|\\[rnt]', target))
        if stored != expected_stored:
            blockers.append({
                'id': rid,
                'type': 'target_tag_index_mismatch',
                'stored': stored,
                'expected': expected_stored,
            })
        if '\0' in row['en'] or '\0' in row['cn']:
            blockers.append({'id': rid, 'type': 'embedded_nul_in_payload'})
        if row['layer'] == 'upk':
            digest = rid.removeprefix('upk:')
            if not re.fullmatch(r'[0-9A-F]{32}', digest):
                blockers.append({'id': rid, 'type': 'invalid_upk_id'})
            elif row['en'] and hashlib.md5(
                    row['en'].encode('utf-16-le')).hexdigest().upper() != digest:
                blockers.append({'id': rid, 'type': 'english_md5_mismatch'})
            if row.get('target_format', {}).get('nul_terminated') is not True:
                blockers.append({'id': rid, 'type': 'missing_nul_format_contract'})

    blockers.extend({'id': rid, 'type': 'duplicate_id', 'count': count}
                    for rid, count in ids.items() if count > 1)
    layer_counts = Counter(row.get('layer') for row in rows)
    if layer_counts['int'] != int_expected:
        blockers.append({'type': 'int_count_mismatch', 'actual': layer_counts['int'],
                         'expected': int_expected})
    if layer_counts['upk'] != upk_expected:
        blockers.append({'type': 'upk_count_mismatch', 'actual': layer_counts['upk'],
                         'expected': upk_expected})
    return blockers


def build_format_report(rows, blockers):
    differences = []
    target_token_counts = Counter()
    target_newlines = 0
    source_newlines = 0
    for row in rows:
        source = format_tokens(row['en'])
        target = format_tokens(row['cn'] if row['cn'] else row['en'])
        target_token_counts.update(target)
        source_newlines += row['en'].count('\n')
        target_newlines += row['cn'].count('\n')
        if source != target or row['en'].count('\n') != row['cn'].count('\n'):
            differences.append({
                'id': row['id'],
                'source_tokens': source,
                'target_tokens': target,
                'source_newlines': row['en'].count('\n'),
                'target_newlines': row['cn'].count('\n'),
                'classification': (
                    'target_format_is_writeback_contract'
                    if row['layer'] == 'upk' else 'source_target_layout_difference'),
            })
    return {
        'hard_blockers': blockers,
        'hard_blocker_count': len(blockers),
        'target_token_occurrences': sum(target_token_counts.values()),
        'target_token_kinds': dict(sorted(target_token_counts.items())),
        'source_newline_count': source_newlines,
        'target_newline_count': target_newlines,
        'source_target_difference_count': len(differences),
        'source_target_differences': differences,
        'policy': (
            '中英 token/换行差异用于后续校对提示，不直接判错；写回硬约束是新译文必须'
            '保留旧中文 target tokens、换行与 UPK NUL 终止契约。'),
    }


def validate_sample(csv_path, corpus_by_id, evidence_path):
    with open(csv_path, encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames
    errors = []
    for row in rows:
        corpus = corpus_by_id.get(row['id'])
        if corpus is None:
            errors.append({'id': row['id'], 'error': 'id_not_in_corpus'})
            row['alignment_ok'] = 'FAIL'
            continue
        expected = {
            'en': corpus['en'],
            'cn': corpus['cn'],
            'release': corpus['domain']['release'],
            'file': corpus['context']['file'],
            'section': corpus['context']['section'],
        }
        mismatch = [key for key, value in expected.items() if row.get(key) != value]
        if mismatch:
            errors.append({'id': row['id'], 'error': 'field_mismatch', 'fields': mismatch})
            row['alignment_ok'] = 'FAIL'
        else:
            row['alignment_ok'] = 'PASS(source-resolved)'
            row['note'] = row.get('note', '') or '稳定 ID 可回源；此处只验对齐，不评价译文质量'
    temp = csv_path.with_suffix(csv_path.suffix + '.tmp')
    with open(temp, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    atomic_replace(temp, csv_path)
    evidence = {'sample_count': len(rows), 'passed': len(rows) - len(errors),
                'failed': len(errors), 'errors': errors}
    json_write(evidence_path, evidence)
    return evidence


def build_regressions(corpus_by_id):
    cases = []
    for digest, expected in P0.items():
        row = corpus_by_id.get(f'upk:{digest}', {})
        passed = (expected['expected_en'] in row.get('en', '')
                  and expected['bad_cn'] in row.get('cn', ''))
        cases.append({
            'id': f'upk:{digest}',
            **expected,
            'en': row.get('en', ''),
            'old_cn': row.get('cn', ''),
            'context': row.get('context', {}),
            'phase1_trace_passed': passed,
            'phase2_required_action': 'fix',
        })
    return cases


def update_source_summary(project, rows):
    path = project / 'data' / 'raw' / 'manifests' / 'source_summary.json'
    summary = json.load(open(path, encoding='utf-8'))
    integrity = json.load(open(
        project / 'data' / 'raw' / 'manifests' / 'source_integrity_before.json',
        encoding='utf-8'))
    package_rows = [row for row in integrity['files'] if row['category'] == 'package_identity']
    int_rows = [row for row in rows if row['layer'] == 'int']
    upk_rows = [row for row in rows if row['layer'] == 'upk']
    cjk = re.compile(r'[\u3400-\u9fff]')
    summary['identity_checks'] = {
        'english_int_nonempty': sum(bool(row['en']) for row in int_rows),
        'english_int_rows_with_cjk': sum(bool(cjk.search(row['en'])) for row in int_rows),
        'chinese_int_nonempty': sum(bool(row['cn']) for row in int_rows),
        'chinese_int_rows_with_cjk': sum(bool(cjk.search(row['cn'])) for row in int_rows),
        'chinese_upk_rows_with_cjk': sum(bool(cjk.search(row['cn'])) for row in upk_rows),
        'package_label': '天邈汉化组 Dishonored GOTY 中文补丁 v1.4（用户提供备份）',
        'package_identity_files': [
            {'path': row['path'], 'size': row['size'], 'sha256': row['sha256']}
            for row in package_rows
        ],
        'conclusion': '英文侧为英文源；中文侧含天邈中文与 DGOTYCNv1.4 分发身份文件。',
    }
    json_write(path, summary)


def update_run_manifest(project):
    """把最终工具链与核心语料哈希补入初始运行清单。"""
    path = project / 'data' / 'raw' / 'manifests' / 'phase1_run.json'
    manifest = json.load(open(path, encoding='utf-8'))
    relative_tools = (
        'tools/parse_int.py',
        'tools/parse_textsdb.py',
        'tools/phase1_extract.py',
        'tools/extract_upk_texts.py',
        'tools/phase1_finalize.py',
        'tools/apply_patch.py',
        'tools/corpus_schema.json',
    )
    manifest['finalized_at'] = dt.datetime.now(
        dt.timezone.utc).astimezone().isoformat()
    manifest['final_toolchain_sha256'] = {
        relative: sha256_file(project / relative) for relative in relative_tools
    }
    manifest['final_outputs_sha256'] = {
        'data/aligned/corpus.jsonl': sha256_file(
            project / 'data' / 'aligned' / 'corpus.jsonl'),
        'data/aligned/corpus_summary.json': sha256_file(
            project / 'data' / 'aligned' / 'corpus_summary.json'),
        'data/raw/upk_en_texts.json': sha256_file(
            project / 'data' / 'raw' / 'upk_en_texts.json'),
    }
    json_write(path, manifest)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--project-root', default=Path(__file__).resolve().parent.parent)
    args = ap.parse_args()
    project = Path(args.project_root).resolve()
    aligned = project / 'data' / 'aligned'
    raw = project / 'data' / 'raw'

    int_rows = load_jsonl(aligned / 'int_corpus.jsonl')
    upk_rows = load_jsonl(aligned / 'upk_corpus.jsonl')
    rows = int_rows + upk_rows
    int_coverage = json.load(open(aligned / 'int_coverage.json', encoding='utf-8'))
    upk_manifest = json.load(open(raw / 'upk_extraction_manifest.json', encoding='utf-8'))
    if upk_manifest['english_recovered'] != upk_manifest['texts_db_entries']:
        raise SystemExit('UPK 英文尚未完整恢复')
    issues = json.load(open(aligned / 'upk_alignment_issues.json', encoding='utf-8'))
    if any(issues.values()):
        raise SystemExit('UPK 对齐仍有未解决问题')

    blockers = validate_rows(
        rows, int_coverage['entries']['corpus_rows'], upk_manifest['texts_db_entries'])
    jsonl_write(aligned / 'corpus.jsonl', rows)
    format_report = build_format_report(rows, blockers)
    json_write(aligned / 'format_issues.json', format_report)

    ids = Counter(row['id'] for row in rows)
    layer = Counter(row['layer'] for row in rows)
    status = Counter(row['status'] for row in rows)
    releases = Counter()
    for row in rows:
        if row['layer'] == 'int':
            releases[row['domain']['release']] += 1
        else:
            releases[row['domain']['primary_release']] += 1
    summary = {
        'schema': 'tools/corpus_schema.json',
        'schema_sha256': sha256_file(project / 'tools' / 'corpus_schema.json'),
        'total_rows': len(rows),
        'unique_ids': len(ids),
        'duplicate_ids': sorted(rid for rid, count in ids.items() if count > 1),
        'layer': dict(sorted(layer.items())),
        'status': dict(sorted(status.items())),
        'primary_release': dict(sorted(releases.items())),
        'long_text_rows': sum(row.get('domain', {}).get('long_text', False) for row in rows),
        'target_tagged_rows': sum(bool(row['tags']) for row in rows),
        'format_hard_blockers': len(blockers),
        'int_alignment_warnings': {
            'normalized_identifier': int_coverage['normalized_identifier_matches'],
            'en_only': int_coverage['status'].get('en_only', 0),
            'cn_only': int_coverage['status'].get('cn_only', 0),
        },
        'upk_coverage': {
            'texts_db': upk_manifest['texts_db_entries'],
            'english_recovered': upk_manifest['english_recovered'],
            'missing': upk_manifest['english_missing'],
        },
    }
    json_write(aligned / 'corpus_summary.json', summary)

    corpus_by_id = {row['id']: row for row in rows}
    sample = validate_sample(
        aligned / 'int_sample_review.csv', corpus_by_id,
        aligned / 'int_sample_validation.json')
    regressions = build_regressions(corpus_by_id)
    json_write(aligned / 'regression_cases.json', regressions)
    update_source_summary(project, rows)
    update_run_manifest(project)

    result = {
        **summary,
        'int_sample': sample,
        'p0_trace_passed': sum(case['phase1_trace_passed'] for case in regressions),
    }
    print(json.dumps(result, ensure_ascii=False, indent=1))
    if blockers or sample['failed'] or result['p0_trace_passed'] != len(P0):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
