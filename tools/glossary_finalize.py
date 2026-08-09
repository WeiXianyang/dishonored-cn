# -*- coding: utf-8 -*-
"""审批门禁后的 Phase 2 术语表最终化工具。

默认只在 ``data/review`` 生成确定性预览。只有同时提供 ``--apply``、
精确策略令牌、用户确认说明和预期旧表哈希时，才会备份并最后一步替换
``glossary/terms.json``。因此模型运行或误执行脚本都不能越过人工确认门槛。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

from phase1_extract import json_write, sha256_file


POLICY_TOKEN = 'accept-resolved-terms-exclude-deferred'
REGRESSIONS = {
    'Emily': ('lock', '艾米莉'),
    'Dishonored': ('lock', '耻辱'),
    'Whale': ('reject', ''),
    'Whale Oil': ('lock', '鲸油'),
}


def load_jsonl(path):
    with open(path, encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def canonical_json_bytes(value):
    text = json.dumps(value, ensure_ascii=False, indent=1) + '\n'
    return text.encode('utf-8')


def value_sha256(value):
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def validate_sources(resolved, deferred, rejected, decisions, validation,
                     formal_terms_path):
    errors = []
    if validation.get('status') != 'pass':
        errors.append('Phase 2 resolution_validation 不是 pass')

    expected = validation.get('candidate_count')
    counts = {
        'resolved': len(resolved),
        'deferred': len(deferred),
        'rejected': len(rejected),
        'decisions': len(decisions),
    }
    expected_counts = {
        'resolved': validation.get('resolved_term_count'),
        'deferred': validation.get('remaining_human_review_count'),
        'rejected': validation.get('rejected_count'),
        'decisions': expected,
    }
    for key, actual in counts.items():
        if actual != expected_counts[key]:
            errors.append(
                f'{key} 数量 {actual} != 验收记录 {expected_counts[key]}')

    decision_by_id = {}
    for item in decisions:
        item_id = item.get('id')
        if not item_id or item_id in decision_by_id:
            errors.append(f'最终结论 id 缺失或重复: {item_id!r}')
        decision_by_id[item_id] = item
    partition_ids = []
    for name, rows, action in (
            ('resolved', resolved, 'lock'),
            ('deferred', deferred, 'review'),
            ('rejected', rejected, 'reject')):
        for item in rows:
            item_id = item.get('id')
            partition_ids.append(item_id)
            decision = decision_by_id.get(item_id)
            if not decision:
                errors.append(f'{name} 中的 {item_id!r} 不在最终结论中')
                continue
            if decision.get('action') != action:
                errors.append(
                    f'{item_id}: {name} 分区要求 {action}，实际 '
                    f'{decision.get("action")!r}')
            if action == 'lock' and (
                    decision.get('en_term') != item.get('en_term') or
                    decision.get('cn_term') != item.get('cn_term')):
                errors.append(f'{item_id}: resolved_terms 与最终结论不一致')
    if len(partition_ids) != len(set(partition_ids)):
        errors.append('resolved/deferred/rejected 分区 ID 有重叠')
    if expected is not None and len(partition_ids) != expected:
        errors.append(f'分区总数 {len(partition_ids)} != 候选总数 {expected}')

    term_keys = []
    for item in resolved:
        english = item.get('en_term', '').strip()
        chinese = item.get('cn_term', '').strip()
        term_keys.append(english.casefold())
        if not english or not chinese:
            errors.append(f'{item.get("id")}: 术语键值为空')
        if '\n' in english or re.search(r'<[^>]*>|`[^`]*`', english):
            errors.append(f'{item.get("id")}: 英文键含格式标签或换行')
        if not item.get('evidence_ids'):
            errors.append(f'{item.get("id")}: 建议术语缺少证据 ID')
    if len(term_keys) != len(set(term_keys)):
        errors.append('建议术语英文键大小写归一后重复')

    decision_by_en = {
        item.get('en_term', '').casefold(): item for item in decisions
    }
    regression_results = []
    for english, (expected_action, expected_cn) in REGRESSIONS.items():
        item = decision_by_en.get(english.casefold())
        passed = bool(
            item and item.get('action') == expected_action and
            item.get('cn_term') == expected_cn)
        regression_results.append({
            'en_term': english,
            'expected_action': expected_action,
            'expected_cn': expected_cn,
            'actual_action': item.get('action') if item else '',
            'actual_cn': item.get('cn_term') if item else '',
            'passed': passed,
        })
        if not passed:
            errors.append(f'核心回归失败: {english}')

    formal_sha = sha256_file(formal_terms_path)
    expected_formal_sha = validation.get('formal_terms_sha256_after')
    if formal_sha != expected_formal_sha:
        errors.append(
            '当前正式 terms.json 与 Phase 2 保护哈希不同：'
            f'{formal_sha} != {expected_formal_sha}')
    return {
        'status': 'pass' if not errors else 'fail',
        'counts': counts,
        'expected_candidate_count': expected,
        'formal_terms_sha256': formal_sha,
        'seed_regressions': regression_results,
        'errors': errors,
    }


def build_outputs(resolved, deferred, source_hashes):
    terms = {
        '_note': (
            '基于天邈汉化 1.4 与英文原文建立；只含全局可锁定项。'
            '上下文多义项见 deferred_context_terms.json。'),
        '_schema_version': 2,
        '_term_count': len(resolved),
        '_policy': POLICY_TOKEN,
    }
    for item in sorted(resolved, key=lambda value: value['en_term'].casefold()):
        terms[item['en_term']] = item['cn_term']

    evidence = {
        '_note': (
            '每个正式术语的 Phase 1 corpus 证据，以及两轮模型/Wiki '
            '疑难核查裁决摘要。'),
        '_source_hashes': source_hashes,
        'items': [
            {
                'id': item['id'],
                'en_term': item['en_term'],
                'cn_term': item['cn_term'],
                'category': item['category'],
                'confidence': item['confidence'],
                'reason': item['reason'],
                'evidence_ids': item['evidence_ids'],
                'source': item['source'],
                'wiki_urls': item.get('wiki_urls', []),
            }
            for item in sorted(
                resolved, key=lambda value: value['en_term'].casefold())
        ],
    }
    deferred_output = {
        '_note': (
            '不进入全局术语锁；Phase 3 必须按具体实体/系统/语境审校，'
            '不得用单一译名强制覆盖。'),
        '_policy': 'exclude-from-global-lock-and-defer-to-phase3',
        'items': deferred,
    }
    return terms, evidence, deferred_output


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--resolved',
        default='data/review/glossary/wiki_resolution/resolved_terms.jsonl')
    parser.add_argument(
        '--deferred',
        default='data/review/glossary/wiki_resolution/deferred_terms.jsonl')
    parser.add_argument(
        '--rejected',
        default='data/review/glossary/wiki_resolution/rejected_terms.jsonl')
    parser.add_argument(
        '--decisions',
        default='data/review/glossary/wiki_resolution/decisions.jsonl')
    parser.add_argument(
        '--validation',
        default='data/review/glossary/wiki_resolution/validation.json')
    parser.add_argument('--formal-terms', default='glossary/terms.json')
    parser.add_argument(
        '--preview-dir', default='data/review/glossary/finalization_preview')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--approve-policy', default='')
    parser.add_argument('--approval-note', default='')
    parser.add_argument('--expected-formal-sha256', default='')
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    inputs = (
        args.resolved, args.deferred, args.rejected, args.decisions,
        args.validation, args.formal_terms,
    )
    for path in inputs:
        if not Path(path).is_file():
            print(f'错误: 文件不存在: {path}')
            return 2

    resolved = load_jsonl(args.resolved)
    deferred = load_jsonl(args.deferred)
    rejected = load_jsonl(args.rejected)
    decisions = load_jsonl(args.decisions)
    validation = json.loads(Path(args.validation).read_text(encoding='utf-8'))
    source_hashes = {
        'resolved_terms': sha256_file(args.resolved),
        'deferred_terms': sha256_file(args.deferred),
        'rejected_terms': sha256_file(args.rejected),
        'resolution_decisions': sha256_file(args.decisions),
        'resolution_validation': sha256_file(args.validation),
    }
    source_check = validate_sources(
        resolved, deferred, rejected, decisions, validation,
        args.formal_terms)
    terms, evidence, deferred_output = build_outputs(
        resolved, deferred, source_hashes)

    preview_dir = Path(args.preview_dir)
    json_write(preview_dir / 'terms.preview.json', terms)
    json_write(preview_dir / 'terms_evidence.preview.json', evidence)
    json_write(preview_dir / 'deferred_context_terms.preview.json', deferred_output)
    preview = {
        'status': source_check['status'],
        'mode': 'apply' if args.apply else 'preview',
        'policy_token_required': POLICY_TOKEN,
        'term_count': len(resolved),
        'deferred_count': len(deferred),
        'rejected_count': len(rejected),
        'terms_preview_sha256': value_sha256(terms),
        'evidence_preview_sha256': value_sha256(evidence),
        'deferred_preview_sha256': value_sha256(deferred_output),
        'source_hashes': source_hashes,
        'source_validation': source_check,
        'formal_terms_modified': False,
    }
    json_write(preview_dir / 'finalization_preview.json', preview)
    if source_check['status'] != 'pass':
        print(json.dumps(preview, ensure_ascii=False, indent=1))
        return 1

    if not args.apply:
        print(json.dumps(preview, ensure_ascii=False, indent=1))
        return 0

    approval_errors = []
    if args.approve_policy != POLICY_TOKEN:
        approval_errors.append('缺少或错误的 --approve-policy')
    if not args.approval_note.strip():
        approval_errors.append('--approval-note 不能为空')
    if args.expected_formal_sha256 != source_check['formal_terms_sha256']:
        approval_errors.append('--expected-formal-sha256 与当前正式表不匹配')
    if approval_errors:
        print('拒绝写入: ' + '；'.join(approval_errors))
        return 2

    formal_path = Path(args.formal_terms)
    backup_path = formal_path.with_name('terms.pre-phase2.json')
    if backup_path.exists():
        if sha256_file(backup_path) != source_check['formal_terms_sha256']:
            print(f'拒绝写入: 现有备份哈希异常: {backup_path}')
            return 2
    else:
        shutil.copyfile(formal_path, backup_path)

    # 支撑文件先落盘，正式 terms.json 最后原子替换。
    glossary_dir = formal_path.parent
    json_write(glossary_dir / 'terms_evidence.json', evidence)
    json_write(glossary_dir / 'deferred_context_terms.json', deferred_output)
    decision_record = {
        'policy': POLICY_TOKEN,
        'approval_note': args.approval_note.strip(),
        'previous_terms_sha256': source_check['formal_terms_sha256'],
        'new_terms_sha256': value_sha256(terms),
        'term_count': len(resolved),
        'deferred_count': len(deferred),
        'rejected_count': len(rejected),
        'source_hashes': source_hashes,
    }
    json_write(glossary_dir / 'phase2_decision.json', decision_record)
    json_write(formal_path, terms)
    applied_sha = sha256_file(formal_path)
    if applied_sha != value_sha256(terms):
        print('错误: 正式 terms.json 写入后哈希与预览不一致')
        return 1
    preview['formal_terms_modified'] = True
    preview['applied_terms_sha256'] = applied_sha
    json_write(preview_dir / 'finalization_preview.json', preview)
    print(json.dumps(preview, ensure_ascii=False, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
