# -*- coding: utf-8 -*-
"""合并 Phase 3 Medium/High/确定性路由，生成最终提案与人工清单。"""
import argparse
import csv
import json
import os
import tempfile
from collections import Counter
from pathlib import Path

import review_pipeline as rp


def read_jsonl(path):
    with open(path, encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def unique_by_id(rows, label):
    out = {}
    duplicates = []
    for row in rows:
        identifier = row.get('id')
        if identifier in out:
            duplicates.append(identifier)
        out[identifier] = row
    if duplicates:
        raise ValueError(f'{label} 存在重复 ID: {sorted(set(duplicates))[:5]}')
    return out


def merge_high_overrides(high_rows, override_groups):
    """以单条重审结果覆盖全量 High，同时保持原始顺序和完整覆盖。"""
    base = unique_by_id(high_rows, 'High results')
    overrides = {}
    for label, rows in override_groups:
        current = unique_by_id(rows, label)
        duplicate = sorted(set(overrides) & set(current))
        if duplicate:
            raise ValueError(f'High override 重复 ID: {duplicate[:5]}')
        unknown = sorted(set(current) - set(base))
        if unknown:
            raise ValueError(f'High override 含未知 ID: {unknown[:5]}')
        overrides.update(current)
    effective = [overrides.get(row['id'], row) for row in high_rows]
    return effective, len(overrides)


def atomic_write_csv(path, fieldnames, rows):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(
        prefix=os.path.basename(path) + '.', suffix='.tmp', dir=directory)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def validate_fix(entry, text, terms, term_scope_overrides=None):
    item = {
        'id': entry['id'], 'action': 'fix', 'new_text': text,
        '_old': entry.get('cn', ''),
        'term_scope_overrides': term_scope_overrides or [],
    }
    errors = []
    if not text:
        errors.append('修补文本为空')
    if not rp.check_placeholders(item, entry):
        errors.append('占位符/换行不一致')
    term_error = rp.check_terms(item, terms, entry)
    if term_error:
        errors.append(term_error)
    return errors


def build_final(corpus, medium_rows, automatic_rows, unpaired_rows,
                escalation_rows, high_rows, terms):
    corpus_by_id = unique_by_id(corpus, 'corpus')
    medium = unique_by_id(medium_rows, 'Medium results')
    automatic = unique_by_id(automatic_rows, 'automatic results')
    unpaired = unique_by_id(unpaired_rows, 'unpaired results')
    escalation = unique_by_id(escalation_rows, 'escalation corpus')
    high = unique_by_id(high_rows, 'High results')

    sets = [set(medium), set(automatic), set(unpaired)]
    if any(sets[i] & sets[j] for i in range(3) for j in range(i + 1, 3)):
        raise ValueError('Medium/automatic/unpaired ID 路由重叠')
    routed = set().union(*sets)
    expected = set(corpus_by_id)
    if routed != expected:
        raise ValueError(
            f'源 corpus 路由不完整: 缺少={sorted(expected-routed)[:5]} '
            f'未知={sorted(routed-expected)[:5]}')
    if not set(escalation) <= set(medium):
        raise ValueError('escalation 含非 Medium ID')
    if set(high) != set(escalation):
        raise ValueError(
            f'High 覆盖不完整: 缺少={sorted(set(escalation)-set(high))[:5]} '
            f'多出={sorted(set(high)-set(escalation))[:5]}')
    unrouted_uncertain = sorted(
        identifier for identifier, item in medium.items()
        if item.get('uncertain') and identifier not in escalation)
    if unrouted_uncertain:
        raise ValueError(f'Medium uncertain 未进 High: {unrouted_uncertain[:5]}')

    final_rows = []
    accepted = []
    human = []
    violations = []
    route_counts = Counter()

    for entry in corpus:
        identifier = entry['id']
        old = entry.get('cn', '')
        final = {
            'id': identifier, 'action': 'keep', 'new_text': '',
            'reason': '', 'confidence': 1.0, 'uncertain': False,
            'uncertain_reason': '', 'route': '',
            'source_status': entry.get('status', ''),
        }

        if identifier in automatic:
            final.update({
                'reason': automatic[identifier].get('reason', ''),
                'route': 'automatic_empty_keep',
            })
        elif identifier in unpaired:
            source = unpaired[identifier]
            final.update({
                'reason': source.get('reason', ''), 'confidence': 0.0,
                'uncertain': True,
                'uncertain_reason': source.get('uncertain_reason', ''),
                'route': 'human_unpaired_cn_only',
            })
            human.append({
                'id': identifier, 'route': final['route'],
                'context': entry.get('context', {}), 'en': entry.get('en', ''),
                'original_cn': old, 'candidate_cn': old,
                'reason': final['reason'],
                'uncertain_reason': final['uncertain_reason'],
                'medium': None, 'high': None, 'research_context': {},
            })
        else:
            medium_item = medium[identifier]
            if identifier in escalation:
                high_item = high[identifier]
                escalated = escalation[identifier]
                baseline = escalated.get('cn', '')
                proposed = (high_item.get('new_text', '')
                            if high_item.get('action') == 'fix' else baseline)
                if high_item.get('uncertain'):
                    final.update({
                        'reason': '经 High 复审仍无法确定，保留天邈原译并进入人工。',
                        'confidence': float(high_item.get('confidence', 0.0)),
                        'uncertain': True,
                        'uncertain_reason': high_item.get('uncertain_reason', ''),
                        'route': 'human_after_high',
                    })
                    human.append({
                        'id': identifier, 'route': final['route'],
                        'context': entry.get('context', {}),
                        'en': entry.get('en', ''), 'original_cn': old,
                        'candidate_cn': proposed,
                        'reason': high_item.get('reason', ''),
                        'uncertain_reason': high_item.get('uncertain_reason', ''),
                        'medium': medium_item, 'high': high_item,
                        'research_context': escalated.get('research_context', {}),
                    })
                else:
                    action = 'keep' if proposed == old else 'fix'
                    final.update({
                        'action': action,
                        'new_text': proposed if action == 'fix' else '',
                        'reason': high_item.get('reason', ''),
                        'confidence': float(high_item.get('confidence', 0.0)),
                        'route': ('high_revert_to_tianmiao' if proposed == old and
                                  baseline != old else 'high_decision'),
                    })
                    term_review = escalated.get('term_review') or {}
                    if term_review.get('mode') == 'agent_secondary_review':
                        final['term_reviewed'] = True
                        final['term_scope_overrides'] = [{
                            'en': value['en'], 'cn': value['cn'],
                        } for value in term_review.get('candidates', [])
                            if value.get('cn') not in proposed]
            else:
                proposed = (medium_item.get('new_text', '')
                            if medium_item.get('action') == 'fix' else old)
                action = 'keep' if proposed == old else 'fix'
                final.update({
                    'action': action,
                    'new_text': proposed if action == 'fix' else '',
                    'reason': medium_item.get('reason', ''),
                    'confidence': float(medium_item.get('confidence', 0.0)),
                    'route': 'medium_decision',
                })

        route_counts[final['route']] += 1
        if final['action'] == 'fix':
            errors = validate_fix(
                entry, final['new_text'], terms,
                final.get('term_scope_overrides'))
            if errors:
                violations.append({'id': identifier, 'errors': errors})
            accepted.append({
                **final,
                'layer': entry.get('layer'), 'context': entry.get('context', {}),
                'en': entry.get('en', ''), 'old_text': old,
            })
        final_rows.append(final)

    if violations:
        raise ValueError(
            '最终 fix 硬违规: ' + json.dumps(
                violations[:10], ensure_ascii=False))
    if len(final_rows) != len(corpus) or len({r['id'] for r in final_rows}) != len(corpus):
        raise ValueError('最终结果 ID 数量/唯一性异常')
    return final_rows, accepted, human, dict(sorted(route_counts.items()))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--corpus', default='data/aligned/corpus.jsonl')
    parser.add_argument('--medium-dir', required=True)
    parser.add_argument('--escalation-corpus', required=True)
    parser.add_argument('--high-results', required=True)
    parser.add_argument(
        '--high-override-results', action='append', default=[],
        help='可重复；经同配置单条重审的 High results.jsonl')
    parser.add_argument('--terms', default='glossary/terms.json')
    parser.add_argument('--out-dir', required=True)
    args = parser.parse_args(argv)

    medium_dir = Path(args.medium_dir)
    corpus = read_jsonl(args.corpus)
    medium = read_jsonl(medium_dir / 'results.jsonl')
    automatic = read_jsonl(medium_dir / 'automatic_empty_keep.jsonl')
    unpaired = read_jsonl(medium_dir / 'unpaired_manual_review.jsonl')
    escalation = read_jsonl(args.escalation_corpus)
    high = read_jsonl(args.high_results)
    override_groups = [
        (f'High override {path}', read_jsonl(path))
        for path in args.high_override_results]
    high, override_count = merge_high_overrides(high, override_groups)
    raw_terms = json.loads(Path(args.terms).read_text(encoding='utf-8'))
    terms = {key: value for key, value in raw_terms.items()
             if not key.startswith('_')}

    final_rows, accepted, human, route_counts = build_final(
        corpus, medium, automatic, unpaired, escalation, high, terms)
    out_dir = Path(args.out_dir)
    effective_high_path = out_dir / 'effective_high_results.jsonl'
    final_path = out_dir / 'final_results.jsonl'
    accepted_path = out_dir / 'accepted_fixes.jsonl'
    human_path = out_dir / 'human_review.jsonl'
    human_csv_path = out_dir / 'human_review.csv'
    rp.atomic_write_jsonl(str(final_path), final_rows)
    rp.atomic_write_jsonl(str(accepted_path), accepted)
    rp.atomic_write_jsonl(str(human_path), human)
    rp.atomic_write_jsonl(str(effective_high_path), high)

    csv_rows = []
    for item in human:
        csv_rows.append({
            'id': item['id'], 'route': item['route'],
            'context': json.dumps(item['context'], ensure_ascii=False),
            'en': item['en'], 'original_cn': item['original_cn'],
            'candidate_cn': item['candidate_cn'], 'reason': item['reason'],
            'uncertain_reason': item['uncertain_reason'],
            'decision': '', 'decided_text': '', 'note': '',
        })
    atomic_write_csv(str(human_csv_path), [
        'id', 'route', 'context', 'en', 'original_cn', 'candidate_cn',
        'reason', 'uncertain_reason', 'decision', 'decided_text', 'note',
    ], csv_rows)

    summary = {
        'created_at': rp.now_utc(), 'source_entries': len(corpus),
        'final_entries': len(final_rows),
        'actions': dict(Counter(row['action'] for row in final_rows)),
        'accepted_fixes': len(accepted), 'human_review': len(human),
        'routes': route_counts,
        'coverage_rate': len(final_rows) / len(corpus) if corpus else 1.0,
        'hard_violations': 0,
        'high_overrides': override_count,
        'hashes': {
            'corpus': rp.sha256_file(args.corpus),
            'medium_results': rp.sha256_file(str(medium_dir / 'results.jsonl')),
            'escalation_corpus': rp.sha256_file(args.escalation_corpus),
            'high_results': rp.sha256_file(args.high_results),
            'high_override_results': [
                rp.sha256_file(path) for path in args.high_override_results],
            'effective_high_results': rp.sha256_file(str(effective_high_path)),
            'final_results': rp.sha256_file(str(final_path)),
            'accepted_fixes': rp.sha256_file(str(accepted_path)),
            'human_review': rp.sha256_file(str(human_path)),
        },
    }
    rp.atomic_write_json(str(out_dir / 'summary.json'), summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
