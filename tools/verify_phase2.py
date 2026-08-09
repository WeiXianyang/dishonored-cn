# -*- coding: utf-8 -*-
"""独立验证 Phase 2 预览或用户批准后的正式术语锁。"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from phase1_extract import sha256_file


def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def canonical_file_sha(value):
    raw = (json.dumps(value, ensure_ascii=False, indent=1) + '\n').encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--expect', choices=('preview', 'final'), default='preview')
    parser.add_argument('--corpus', default='data/aligned/corpus.jsonl')
    parser.add_argument(
        '--source-validation',
        default='data/review/glossary/wiki_resolution/validation.json')
    parser.add_argument(
        '--preview-dir', default='data/review/glossary/finalization_preview')
    parser.add_argument('--formal-terms', default='glossary/terms.json')
    args = parser.parse_args(argv)

    preview_dir = Path(args.preview_dir)
    paths = {
        'corpus': Path(args.corpus),
        'source_validation': Path(args.source_validation),
        'manifest': preview_dir / 'finalization_preview.json',
        'terms_preview': preview_dir / 'terms.preview.json',
        'evidence_preview': preview_dir / 'terms_evidence.preview.json',
        'deferred_preview': preview_dir / 'deferred_context_terms.preview.json',
        'formal_terms': Path(args.formal_terms),
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        print(json.dumps({'status': 'fail', 'missing': missing}, ensure_ascii=False, indent=1))
        return 1

    source_validation = load_json(paths['source_validation'])
    manifest = load_json(paths['manifest'])
    terms = load_json(paths['terms_preview'])
    evidence = load_json(paths['evidence_preview'])
    deferred = load_json(paths['deferred_preview'])
    formal = load_json(paths['formal_terms'])
    errors = []

    if source_validation.get('status') != 'pass':
        errors.append('resolution_validation 不是 pass')
    if manifest.get('status') != 'pass':
        errors.append('finalization_preview 不是 pass')
    expected_hashes = {
        'terms_preview_sha256': canonical_file_sha(terms),
        'evidence_preview_sha256': canonical_file_sha(evidence),
        'deferred_preview_sha256': canonical_file_sha(deferred),
    }
    for key, actual in expected_hashes.items():
        if manifest.get(key) != actual:
            errors.append(f'{key} 不匹配')

    term_map = {key: value for key, value in terms.items() if not key.startswith('_')}
    evidence_items = evidence.get('items', [])
    deferred_items = deferred.get('items', [])
    if len(term_map) != manifest.get('term_count'):
        errors.append('预览术语实际数量与 manifest 不一致')
    if terms.get('_term_count') != len(term_map):
        errors.append('terms._term_count 不一致')
    if len(evidence_items) != len(term_map):
        errors.append('证据项数量与术语数不一致')
    if len(deferred_items) != manifest.get('deferred_count'):
        errors.append('延后项数量与 manifest 不一致')

    evidence_ids = [item.get('id') for item in evidence_items]
    deferred_ids = [item.get('id') for item in deferred_items]
    if len(evidence_ids) != len(set(evidence_ids)):
        errors.append('术语证据稳定 ID 重复')
    if len(deferred_ids) != len(set(deferred_ids)):
        errors.append('延后项稳定 ID 重复')
    if set(evidence_ids) & set(deferred_ids):
        errors.append('正式建议与延后项 ID 重叠')

    for item in evidence_items:
        english = item.get('en_term', '')
        chinese = item.get('cn_term', '')
        if term_map.get(english) != chinese:
            errors.append(f'{item.get("id")}: terms 与证据映射不一致')
        if not item.get('evidence_ids'):
            errors.append(f'{item.get("id")}: 正式建议缺少 corpus 证据 ID')

    corpus_ids = set()
    with open(paths['corpus'], encoding='utf-8') as stream:
        for line in stream:
            if line.strip():
                corpus_ids.add(json.loads(line)['id'])
    unknown_evidence = []
    for item in (*evidence_items, *deferred_items):
        for evidence_id in item.get('evidence_ids', []):
            if evidence_id not in corpus_ids:
                unknown_evidence.append({
                    'term_id': item.get('id'), 'evidence_id': evidence_id,
                })
    if unknown_evidence:
        errors.append(f'{len(unknown_evidence)} 个证据 ID 不在 Phase 1 corpus')

    regressions = {
        'Emily': '艾米莉',
        'Dishonored': '耻辱',
        'Whale Oil': '鲸油',
    }
    for english, chinese in regressions.items():
        if term_map.get(english) != chinese:
            errors.append(f'预览术语回归失败: {english} -> {chinese}')
    if 'Whale' in term_map:
        errors.append('错误泛化回归失败: Whale 不得进入术语锁')

    formal_sha = sha256_file(paths['formal_terms'])
    preview_sha = expected_hashes['terms_preview_sha256']
    if args.expect == 'preview':
        protected_sha = source_validation.get('formal_terms_sha256_after')
        if formal_sha != protected_sha:
            errors.append('preview 状态下正式 terms.json 不再等于保护哈希')
        if manifest.get('formal_terms_modified'):
            errors.append('preview manifest 错误声称已修改正式表')
    else:
        if manifest.get('mode') != 'apply' or not manifest.get('formal_terms_modified'):
            errors.append('final manifest 未记录成功 apply')
        glossary_dir = paths['formal_terms'].parent
        final_support = {
            'evidence': glossary_dir / 'terms_evidence.json',
            'deferred': glossary_dir / 'deferred_context_terms.json',
            'decision': glossary_dir / 'phase2_decision.json',
            'backup': glossary_dir / 'terms.pre-phase2.json',
        }
        absent = [str(path) for path in final_support.values() if not path.is_file()]
        if absent:
            errors.append(f'正式化支撑文件缺失: {absent}')
        else:
            audit_state = formal.get('_policy') == \
                'independent-audit-global-only-secondary-review-on-insertion'
            if audit_state:
                audit_paths = {
                    'summary': glossary_dir / 'glossary_audit_summary.json',
                    'advisory': glossary_dir / 'advisory_terms.json',
                    'policies': glossary_dir / 'term_policies.json',
                    'backup': glossary_dir / 'terms.pre-glossary-audit.json',
                }
                audit_absent = [str(path) for path in audit_paths.values()
                                if not path.is_file()]
                if audit_absent:
                    errors.append(f'术语审计分层文件缺失: {audit_absent}')
                else:
                    audit_summary = load_json(audit_paths['summary'])
                    advisory_items = load_json(audit_paths['advisory']).get('items', [])
                    policy_items = load_json(audit_paths['policies']).get('items', [])
                    hard_map = {key: value for key, value in formal.items()
                                if not key.startswith('_')}
                    hard_names = set(hard_map)
                    advisory_names = {item.get('en_term')
                                      for item in advisory_items}
                    if len(policy_items) != audit_summary.get('source_terms'):
                        errors.append('术语审计策略账本数量不一致')
                    if len(hard_map) != audit_summary.get('hard_global_terms'):
                        errors.append('术语审计全局硬锁数量不一致')
                    if len(advisory_items) != audit_summary.get('advisory_terms'):
                        errors.append('术语审计作用域候选数量不一致')
                    if hard_names & advisory_names:
                        errors.append('术语审计硬锁与候选层发生重叠')
                    for item in policy_items:
                        english = item.get('en_term')
                        decision = item.get('decision')
                        expected_cn = item.get('cn_term')
                        if decision == 'keep_global':
                            expected_cn = item.get('previous_cn')
                        if decision in {'keep_global', 'correct_global'}:
                            if hard_map.get(english) != expected_cn:
                                errors.append(f'{english}: 审计硬锁译值不一致')
                        elif decision == 'restrict_scope':
                            if english not in advisory_names:
                                errors.append(f'{english}: 审计候选项缺失')
                        elif decision == 'remove':
                            if english in hard_names or english in advisory_names:
                                errors.append(f'{english}: 移除项仍在生效层')
                    hashes = audit_summary.get('hashes', {})
                    if hashes.get('hard_terms') != formal_sha:
                        errors.append('术语审计硬锁哈希不匹配')
                    if hashes.get('advisory_terms') != sha256_file(
                            audit_paths['advisory']):
                        errors.append('术语审计候选层哈希不匹配')
                    if audit_summary.get('source_hashes', {}).get(
                            'terms_before') != sha256_file(audit_paths['backup']):
                        errors.append('术语审计前备份哈希不匹配')
            else:
                decision = load_json(final_support['decision'])
                overrides = decision.get('phase3_term_overrides', [])
                expected_formal = dict(terms)
                override_by_en = {}
                for override in overrides:
                    english = override.get('en_term')
                    previous = override.get('previous_cn')
                    chinese = override.get('cn_term')
                    if not english or not chinese or english in override_by_en:
                        errors.append('Phase 3 术语覆盖记录非法或重复')
                        continue
                    if expected_formal.get(english) != previous:
                        errors.append(f'Phase 3 术语覆盖旧值不匹配: {english}')
                    expected_formal[english] = chinese
                    override_by_en[english] = override
                expected_formal_sha = canonical_file_sha(expected_formal)
                if formal != expected_formal:
                    errors.append('正式 terms.json 不等于批准预览 + Phase 3 声明覆盖')
                if formal_sha != expected_formal_sha:
                    errors.append('正式 terms.json 哈希不等于有效术语表哈希')

                formal_evidence = load_json(final_support['evidence'])
                preview_items = {
                    item.get('en_term'): item for item in evidence.get('items', [])}
                formal_items = {
                    item.get('en_term'): item
                    for item in formal_evidence.get('items', [])}
                if set(formal_items) != set(preview_items):
                    errors.append('正式证据术语集合与批准预览不同')
                for english, preview_item in preview_items.items():
                    actual = formal_items.get(english, {})
                    if english not in override_by_en:
                        if actual != preview_item:
                            errors.append(f'{english}: 非覆盖证据项发生变化')
                    else:
                        if (actual.get('id') != preview_item.get('id') or
                                actual.get('cn_term') != override_by_en[english]['cn_term'] or
                                actual.get('source') != 'phase3_adjudicated_correction' or
                                not actual.get('evidence_ids')):
                            errors.append(f'{english}: Phase 3 覆盖证据不完整')
                evidence_sha = decision.get('phase3_terms_evidence_sha256')
                if evidence_sha and sha256_file(final_support['evidence']) != evidence_sha:
                    errors.append('Phase 3 正式证据哈希不匹配')
                if load_json(final_support['deferred']) != deferred:
                    errors.append('正式延后项与批准预览不同')
                if decision.get('new_terms_sha256') != formal_sha:
                    errors.append('批准记录的新术语哈希不匹配')
                if sha256_file(final_support['backup']) != \
                        source_validation.get('formal_terms_sha256_before'):
                    errors.append('Phase 2 前术语表备份哈希不匹配')

    result = {
        'status': 'pass' if not errors else 'fail',
        'expected_state': args.expect,
        'corpus_id_count': len(corpus_ids),
        'term_count': len(term_map),
        'formal_term_count': len({key: value for key, value in formal.items()
                                  if not key.startswith('_')}),
        'evidence_item_count': len(evidence_items),
        'deferred_count': len(deferred_items),
        'unknown_evidence_count': len(unknown_evidence),
        'formal_terms_sha256': formal_sha,
        'terms_preview_sha256': preview_sha,
        'errors': errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    sys.exit(main())
