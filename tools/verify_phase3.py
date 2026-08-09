# -*- coding: utf-8 -*-
"""Phase 3 独立验收：从最终产物反向复算覆盖、路由和硬约束。"""
import argparse
import json
from collections import Counter
from pathlib import Path

import review_pipeline as rp


P0_RULES = {
    'upk:281290178F077DFEF82116B3B2F373B3': {
        'required_any': ['指望', '依靠'],
        'forbidden': ['我们取决于你', '追求真相'],
    },
    'upk:9EF2CA8AAC46376916E50EE7AC2E73BB': {
        'required_any': ['困'],
        'forbidden': ['我中陷阱了'],
    },
}


def read_jsonl(path):
    with open(path, encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def index_unique(rows, label, errors):
    out = {}
    for row in rows:
        identifier = row.get('id')
        if not isinstance(identifier, str) or not identifier:
            errors.append(f'{label}: 空/非字符串 ID')
            continue
        if identifier in out:
            errors.append(f'{label}: 重复 ID {identifier}')
        out[identifier] = row
    return out


def verify(corpus, final_rows, accepted_rows, human_rows, terms,
           medium_summary=None, high_summary=None, research_rows=None,
           advisory_terms=None):
    errors = []
    warnings = []
    corpus_by_id = index_unique(corpus, 'corpus', errors)
    final = index_unique(final_rows, 'final', errors)
    accepted = index_unique(accepted_rows, 'accepted', errors)
    human = index_unique(human_rows, 'human', errors)

    source_ids = set(corpus_by_id)
    final_ids = set(final)
    if final_ids != source_ids:
        errors.append(
            f'final ID 覆盖不等于 corpus: '
            f'缺少={sorted(source_ids-final_ids)[:5]} '
            f'多出={sorted(final_ids-source_ids)[:5]}')
    fix_ids = {identifier for identifier, row in final.items()
               if row.get('action') == 'fix'}
    if set(accepted) != fix_ids:
        errors.append(
            f'accepted 与 final fix 集合不等: '
            f'缺少={sorted(fix_ids-set(accepted))[:5]} '
            f'多出={sorted(set(accepted)-fix_ids)[:5]}')
    uncertain_ids = {identifier for identifier, row in final.items()
                     if row.get('uncertain')}
    if set(human) != uncertain_ids:
        errors.append(
            f'human 与 final uncertain 集合不等: '
            f'缺少={sorted(uncertain_ids-set(human))[:5]} '
            f'多出={sorted(set(human)-uncertain_ids)[:5]}')

    route_counts = Counter()
    format_checked = 0
    term_checked = 0
    for identifier, row in final.items():
        entry = corpus_by_id.get(identifier)
        if entry is None:
            continue
        route_counts[row.get('route', '')] += 1
        if row.get('action') not in {'keep', 'fix'}:
            errors.append(f'{identifier}: 非法 action {row.get("action")}')
            continue
        if row.get('action') == 'keep' and row.get('new_text'):
            errors.append(f'{identifier}: keep 时 new_text 非空')
        if row.get('action') == 'fix':
            if row.get('uncertain'):
                errors.append(f'{identifier}: uncertain 修补不得进 accepted')
            new_text = row.get('new_text', '')
            item = {'id': identifier, 'action': 'fix', 'new_text': new_text,
                    '_old': entry.get('cn', ''),
                    'term_scope_overrides': row.get('term_scope_overrides', [])}
            if not new_text:
                errors.append(f'{identifier}: fix 文本为空')
            if not rp.check_placeholders(item, entry):
                errors.append(f'{identifier}: 最终占位符/换行不一致')
            else:
                format_checked += 1
            term_error = rp.check_terms(item, terms, entry)
            if term_error:
                errors.append(f'{identifier}: {term_error}')
            else:
                term_checked += 1
            directly_applied = [{
                'en': english, 'cn': chinese,
            } for english, chinese in rp.required_term_pairs(entry, terms)
                if chinese not in entry.get('cn', '') and chinese in new_text]
            directly_applied.extend(
                {'en': value['en'], 'cn': value['cn']}
                for value in rp.advisory_term_candidates(entry, advisory_terms)
                if value['cn'] not in entry.get('cn', '') and
                value['cn'] in new_text and
                (value['en'], value['cn']) not in {
                    (item['en'], item['cn']) for item in directly_applied})
            if directly_applied and not row.get('term_reviewed'):
                errors.append(
                    f'{identifier}: 术语直接应用未经 Agent 二次复核')
            if row.get('term_scope_overrides') and not row.get('term_reviewed'):
                errors.append(
                    f'{identifier}: 未经 Agent 复核却声明术语作用域豁免')
            accepted_item = accepted.get(identifier, {})
            if accepted_item.get('new_text') != new_text:
                errors.append(f'{identifier}: accepted new_text 与 final 不一致')
            if accepted_item.get('old_text') != entry.get('cn', ''):
                errors.append(f'{identifier}: accepted old_text 与 corpus 不一致')

        if (entry.get('status') == 'en_only' and entry.get('en') and
                not entry.get('cn') and row.get('action') != 'fix' and
                not row.get('uncertain')):
            errors.append(f'{identifier}: en_only 既未补译也未进人工')
        if (entry.get('status') == 'cn_only' and
                (entry.get('en') or entry.get('cn')) and
                row.get('route') not in {
                    'human_unpaired_cn_only', 'phase4_wiki_keep_cn_only'}):
            errors.append(f'{identifier}: cn_only 路由错误')
        if (not entry.get('en') and not entry.get('cn') and
                row.get('route') != 'automatic_empty_keep'):
            errors.append(f'{identifier}: 双空条目未自动保留')

    for identifier, rule in P0_RULES.items():
        entry = final.get(identifier)
        if entry is None:
            errors.append(f'P0 缺失: {identifier}')
            continue
        text = entry.get('new_text', '') if entry.get('action') == 'fix' else \
            corpus_by_id[identifier].get('cn', '')
        if entry.get('action') != 'fix':
            errors.append(f'P0 未修复: {identifier}')
        if not any(token in text for token in rule['required_any']):
            errors.append(f'P0 缺少正向语义: {identifier}')
        for token in rule['forbidden']:
            if token in text:
                errors.append(f'P0 仍含旧错译 {token}: {identifier}')

    if medium_summary is not None:
        expected_medium = {
            'source_entries': len(corpus),
            'completed_entries': 22034,
            'automatic_empty_keep': 9547,
            'unpaired_manual_review': 2,
            'covered_entries': len(corpus),
        }
        for key, expected_value in expected_medium.items():
            if medium_summary.get(key) != expected_value:
                errors.append(
                    f'Medium summary {key}: '
                    f'{medium_summary.get(key)} != {expected_value}')
        if medium_summary.get('coverage_rate') != 1.0:
            errors.append('Medium coverage_rate 不为 1.0')
        if medium_summary.get('failed_batches'):
            errors.append('Medium 存在失败批次')
    if high_summary is not None:
        if high_summary.get('coverage_rate') != 1.0:
            errors.append('High coverage_rate 不为 1.0')
        if high_summary.get('failed_batches'):
            errors.append('High 存在失败批次')

    research_checked = 0
    seen_research = set()
    for research in research_rows or []:
        identifier = research.get('id')
        if research.get('status') != 'resolved' or not identifier:
            continue
        if identifier in seen_research:
            errors.append(f'research 重复 ID: {identifier}')
            continue
        seen_research.add(identifier)
        row = final.get(identifier)
        if row is None:
            errors.append(f'research 含未知/缺失 ID: {identifier}')
            continue
        expected_action = research.get('recommended_action')
        if row.get('uncertain'):
            errors.append(f'{identifier}: 已裁决 research 仍进入人工')
        elif expected_action == 'fix' and row.get('action') != 'fix':
            errors.append(f'{identifier}: research 要求 fix 但最终未修补')
        elif expected_action == 'keep' and row.get('action') != 'keep':
            errors.append(f'{identifier}: research 要求 keep 但最终被修改')
        research_checked += 1

    if corpus and len(human) / len(corpus) > 0.05:
        warnings.append(
            f'人工审核占比 {len(human)/len(corpus):.2%} 高于 5%')
    report = {
        'status': 'pass' if not errors else 'fail',
        'counts': {
            'corpus': len(corpus), 'final': len(final_rows),
            'accepted_fixes': len(accepted_rows), 'human_review': len(human_rows),
            'final_keep': sum(row.get('action') == 'keep' for row in final_rows),
            'final_fix': len(fix_ids), 'final_uncertain': len(uncertain_ids),
            'format_checked_fixes': format_checked,
            'term_checked_fixes': term_checked,
            'resolved_research_checked': research_checked,
        },
        'routes': dict(sorted(route_counts.items())),
        'p0_ids': list(P0_RULES),
        'errors': errors,
        'warnings': warnings,
    }
    return report


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--corpus', default='data/aligned/corpus.jsonl')
    parser.add_argument('--final-dir', required=True)
    parser.add_argument('--medium-summary')
    parser.add_argument('--high-summary')
    parser.add_argument('--terms', default='glossary/terms.json')
    parser.add_argument('--advisory-terms', default='glossary/advisory_terms.json')
    parser.add_argument('--research', help='展开后的 status=resolved 裁决 JSONL')
    parser.add_argument('--out')
    args = parser.parse_args(argv)

    final_dir = Path(args.final_dir)
    corpus = read_jsonl(args.corpus)
    final_rows = read_jsonl(final_dir / 'final_results.jsonl')
    accepted_rows = read_jsonl(final_dir / 'accepted_fixes.jsonl')
    human_rows = read_jsonl(final_dir / 'human_review.jsonl')
    raw_terms = json.loads(Path(args.terms).read_text(encoding='utf-8'))
    terms = {key: value for key, value in raw_terms.items()
             if not key.startswith('_')}
    advisory_terms = rp.load_advisory_terms(args.advisory_terms)
    medium_summary = (json.loads(Path(args.medium_summary).read_text(encoding='utf-8'))
                      if args.medium_summary else None)
    high_summary = (json.loads(Path(args.high_summary).read_text(encoding='utf-8'))
                    if args.high_summary else None)
    research = read_jsonl(args.research) if args.research else []
    report = verify(
        corpus, final_rows, accepted_rows, human_rows, terms,
        medium_summary, high_summary, research, advisory_terms)
    out = Path(args.out) if args.out else final_dir / 'verification.json'
    report['created_at'] = rp.now_utc()
    report['hashes'] = {
        'corpus': rp.sha256_file(args.corpus),
        'final_results': rp.sha256_file(str(final_dir / 'final_results.jsonl')),
        'accepted_fixes': rp.sha256_file(str(final_dir / 'accepted_fixes.jsonl')),
        'human_review': rp.sha256_file(str(final_dir / 'human_review.jsonl')),
        'terms': rp.sha256_file(args.terms),
        'advisory_terms': (rp.sha256_file(args.advisory_terms)
                           if Path(args.advisory_terms).exists() else None),
        'research': rp.sha256_file(args.research) if args.research else None,
    }
    rp.atomic_write_json(str(out), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
