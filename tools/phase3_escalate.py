# -*- coding: utf-8 -*-
"""从 Phase 3 Medium 首审产物构建 High 复审语料。

High 条目的 ``cn`` 是 Medium 后的当前候选；``prior_review`` 同时
保留天邈原译和 Medium 判断，供高推理模型判断是接受、回退还是
再修补。本脚本只写工作区审核产物，不写游戏文件。
"""
import argparse
import difflib
import json
import re
from collections import Counter
from pathlib import Path

import review_pipeline as rp


DEFAULT_FORCE_IDS = Path('data/review/phase3-high-force-ids.txt')
ANGLE_RE = re.compile(r'<[^>]*>')
PUNCT_RE = re.compile(r'[\s\W_]+', re.UNICODE)


def read_jsonl(path):
    with open(path, encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def visible_text(text):
    return ANGLE_RE.sub('', text or '')


def normalized_visible(text):
    return PUNCT_RE.sub('', visible_text(text)).casefold()


def text_risk(old, new):
    old_visible = visible_text(old)
    new_visible = visible_text(new)
    old_norm = normalized_visible(old)
    new_norm = normalized_visible(new)
    similarity = difflib.SequenceMatcher(None, old_norm, new_norm).ratio()
    length_ratio = (
        len(new_visible) / len(old_visible) if old_visible else None)
    return {
        'similarity': round(similarity, 6),
        'visible_old_length': len(old_visible),
        'visible_new_length': len(new_visible),
        'visible_length_ratio': (
            round(length_ratio, 6) if length_ratio is not None else None),
    }


def load_force_ids(path):
    if not path or not Path(path).exists():
        return set()
    return {
        line.strip() for line in Path(path).read_text(encoding='utf-8').splitlines()
        if line.strip() and not line.lstrip().startswith('#')
    }


def load_resolved_research_ids(path):
    """已形成裁决的研究条目必须进入 High，不能停留在 Medium 候选。"""
    if not path or not Path(path).exists():
        return set()
    return {
        row['id'] for row in read_jsonl(path)
        if row.get('status') == 'resolved' and row.get('id')
    }


def load_terms(path):
    if not path or not Path(path).exists():
        return {}
    with open(path, encoding='utf-8') as stream:
        raw = json.load(stream)
    return {
        english: chinese for english, chinese in raw.items()
        if not english.startswith('_')
    }


def escalation_reasons(entry, result, force_ids, confidence_threshold,
                       similarity_threshold, min_length_ratio,
                       max_length_ratio, duplicate_conflict_ids=None,
                       resolved_research_ids=None, terms=None,
                       advisory_terms=None):
    reasons = []
    if result.get('uncertain'):
        reasons.append('medium_uncertain')
    if float(result.get('confidence', 0.0)) < confidence_threshold:
        reasons.append('low_confidence_decision')
    if entry['id'] in force_ids:
        reasons.append('forced_regression_or_calibration_case')
    if entry['id'] in (duplicate_conflict_ids or set()):
        reasons.append('duplicate_decision_conflict')
    if entry['id'] in (resolved_research_ids or set()):
        reasons.append('resolved_research_rule')

    # Medium 由旧版格式契约生成。High 必须接住旧中文本身或 Medium 候选中
    # 缺失 §...§ / $...$ 变量、损坏运行时反引号等确定性问题。
    if not rp.check_placeholders(result, entry):
        reasons.append('medium_format_violation')

    # Medium 的 v6 术语锁对所有英文命中都不区分大小写，会把 ``Favor``
    # 这种 UI 名误套到 ``in favor of`` 的普通词义。只要候选 fix 曾受旧规则
    # 覆盖而新规则不再锁定，就交给 High 对照原译复核。
    if result.get('action') == 'fix' and (terms or advisory_terms):
        current_pairs = set(rp.required_term_pairs(entry, terms))
        legacy_pairs = set(rp.required_term_pairs(
            entry, terms, case_sensitive_single_terms=False))
        if legacy_pairs - current_pairs:
            reasons.append('legacy_term_scope_warning')
        candidate = result.get('new_text', '')
        old = entry.get('cn', '')
        direct_pairs = list(current_pairs) + [
            (value['en'], value['cn'])
            for value in rp.advisory_term_candidates(entry, advisory_terms)]
        if any(chinese not in old and chinese in candidate
               for _english, chinese in direct_pairs):
            reasons.append('term_direct_application')

    if result.get('action') == 'fix':
        risk = text_risk(entry.get('cn', ''), result.get('new_text', ''))
        if entry.get('cn') and risk['similarity'] < similarity_threshold:
            reasons.append('aggressive_rewrite')
        ratio = risk['visible_length_ratio']
        if ratio is not None and (
                ratio < min_length_ratio or ratio > max_length_ratio):
            reasons.append('visible_length_warning')
    return reasons


def find_duplicate_decision_conflicts(corpus_by_id, result_by_id):
    """完全相同的英文+天邈旧译若得到不同候选，路由 High 而不擅自统一。"""
    groups = {}
    for identifier, result in result_by_id.items():
        entry = corpus_by_id[identifier]
        if not entry.get('en', ''):
            continue
        key = (entry.get('en', ''), entry.get('cn', ''))
        candidate = (result.get('new_text', '')
                     if result.get('action') == 'fix'
                     else entry.get('cn', ''))
        signature = (
            result.get('action'), candidate, bool(result.get('uncertain')))
        groups.setdefault(key, []).append((identifier, signature))
    conflicts = set()
    for values in groups.values():
        if len(values) > 1 and len({signature for _, signature in values}) > 1:
            conflicts.update(identifier for identifier, _ in values)
    return conflicts


def build_escalation(corpus, medium_results, force_ids,
                     confidence_threshold=0.96, similarity_threshold=0.35,
                     min_length_ratio=0.55, max_length_ratio=1.8,
                     resolved_research_ids=None, terms=None,
                     advisory_terms=None):
    resolved_research_ids = resolved_research_ids or set()
    terms = terms or {}
    corpus_by_id = {entry['id']: entry for entry in corpus}
    if len(corpus_by_id) != len(corpus):
        raise ValueError('corpus 存在重复 ID')
    result_by_id = {item['id']: item for item in medium_results}
    if len(result_by_id) != len(medium_results):
        raise ValueError('Medium results 存在重复 ID')
    unknown = sorted(set(result_by_id) - set(corpus_by_id))
    if unknown:
        raise ValueError(f'Medium results 含未知 ID: {unknown[:5]}')
    duplicate_conflicts = find_duplicate_decision_conflicts(
        corpus_by_id, result_by_id)

    selected = []
    reason_counts = Counter()
    for entry in corpus:
        result = result_by_id.get(entry['id'])
        if result is None:
            continue
        reasons = escalation_reasons(
            entry, result, force_ids, confidence_threshold,
            similarity_threshold, min_length_ratio, max_length_ratio,
            duplicate_conflicts, resolved_research_ids, terms)
        # 受限术语不是硬约束，但如果 Medium 直接采用了其批准值，仍须二审。
        if result.get('action') == 'fix' and advisory_terms:
            advisory_pairs = rp.advisory_term_candidates(entry, advisory_terms)
            candidate_text = result.get('new_text', '')
            old_text = entry.get('cn', '')
            if (any(value['cn'] not in old_text and
                    value['cn'] in candidate_text for value in advisory_pairs)
                    and 'term_direct_application' not in reasons):
                reasons.append('term_direct_application')
        if not reasons:
            continue
        baseline = (result.get('new_text', '')
                    if result.get('action') == 'fix'
                    else entry.get('cn', ''))
        risk = text_risk(entry.get('cn', ''), baseline)
        high_entry = dict(entry)
        high_entry['cn'] = baseline
        high_entry['status'] = 'aligned'
        high_entry['prior_review'] = {
            'original_cn': entry.get('cn', ''),
            'medium_action': result.get('action'),
            'medium_candidate_cn': baseline,
            'medium_reason': result.get('reason', ''),
            'medium_confidence': result.get('confidence'),
            'medium_uncertain': result.get('uncertain', False),
            'medium_uncertain_reason': result.get('uncertain_reason', ''),
        }
        high_entry['escalation'] = {
            'reasons': reasons,
            'text_risk': risk,
            'original_status': entry.get('status', ''),
        }
        if 'legacy_term_scope_warning' in reasons:
            current_pairs = set(rp.required_term_pairs(entry, terms))
            legacy_pairs = rp.required_term_pairs(
                entry, terms, case_sensitive_single_terms=False)
            high_entry['escalation']['legacy_only_terms'] = [
                {'en': english, 'cn': chinese}
                for english, chinese in legacy_pairs
                if (english, chinese) not in current_pairs
            ]
        if 'term_direct_application' in reasons:
            baseline = result.get('new_text', '')
            old = entry.get('cn', '')
            direct_candidates = [{
                'en': english, 'cn': chinese,
                'source': 'hard_global',
                'requires_secondary_review': True,
                'old_contains_approved': chinese in old,
                'candidate_contains_approved': chinese in baseline,
            } for english, chinese in rp.required_term_pairs(entry, terms)
                if chinese not in old and chinese in baseline]
            direct_candidates.extend({
                **value,
                'old_contains_approved': value['cn'] in old,
                'candidate_contains_approved': value['cn'] in baseline,
            } for value in rp.advisory_term_candidates(entry, advisory_terms)
                if value['cn'] not in old and value['cn'] in baseline and
                (value['en'], value['cn']) not in {
                    (candidate['en'], candidate['cn'])
                    for candidate in direct_candidates})
            high_entry['term_review'] = {
                'mode': 'agent_secondary_review',
                'candidates': direct_candidates,
            }
        selected.append(high_entry)
        reason_counts.update(reasons)
    return selected, dict(sorted(reason_counts.items()))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--corpus', default='data/aligned/corpus.jsonl')
    parser.add_argument('--medium-results', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--manifest')
    parser.add_argument('--force-ids', default=str(DEFAULT_FORCE_IDS))
    parser.add_argument('--research',
                        help='已展开的研究 JSONL；status=resolved 的 ID 强制复审')
    parser.add_argument('--terms', default='glossary/terms.json')
    parser.add_argument('--advisory-terms', default='glossary/advisory_terms.json')
    parser.add_argument('--confidence-threshold', type=float, default=0.96)
    parser.add_argument('--similarity-threshold', type=float, default=0.35)
    parser.add_argument('--min-length-ratio', type=float, default=0.55)
    parser.add_argument('--max-length-ratio', type=float, default=1.8)
    args = parser.parse_args(argv)

    corpus = read_jsonl(args.corpus)
    medium_results = read_jsonl(args.medium_results)
    force_ids = load_force_ids(args.force_ids)
    resolved_research_ids = load_resolved_research_ids(args.research)
    terms = load_terms(args.terms)
    advisory_terms = rp.load_advisory_terms(args.advisory_terms)
    selected, reason_counts = build_escalation(
        corpus, medium_results, force_ids,
        confidence_threshold=args.confidence_threshold,
        similarity_threshold=args.similarity_threshold,
        min_length_ratio=args.min_length_ratio,
        max_length_ratio=args.max_length_ratio,
        resolved_research_ids=resolved_research_ids,
        terms=terms, advisory_terms=advisory_terms)

    out_path = Path(args.out)
    manifest_path = Path(args.manifest) if args.manifest else Path(
        str(out_path) + '.manifest.json')
    rp.atomic_write_jsonl(str(out_path), selected)
    manifest = {
        'created_at': rp.now_utc(),
        'corpus': str(Path(args.corpus).resolve()),
        'medium_results': str(Path(args.medium_results).resolve()),
        'output': str(out_path.resolve()),
        'source_corpus_count': len(corpus),
        'medium_result_count': len(medium_results),
        'selected_count': len(selected),
        'selected_actions': dict(Counter(
            entry['prior_review']['medium_action'] for entry in selected)),
        'selected_uncertain': sum(
            entry['prior_review']['medium_uncertain'] for entry in selected),
        'reason_counts': reason_counts,
        'force_id_count': len(force_ids),
        'resolved_research_id_count': len(resolved_research_ids),
        'term_count': len(terms),
        'advisory_term_count': len(advisory_terms),
        'thresholds': {
            'confidence': args.confidence_threshold,
            'similarity': args.similarity_threshold,
            'min_length_ratio': args.min_length_ratio,
            'max_length_ratio': args.max_length_ratio,
        },
        'hashes': {
            'corpus': rp.sha256_file(args.corpus),
            'medium_results': rp.sha256_file(args.medium_results),
            'research': (
                rp.sha256_file(args.research)
                if args.research and Path(args.research).exists() else None),
            'terms': (
                rp.sha256_file(args.terms)
                if args.terms and Path(args.terms).exists() else None),
            'advisory_terms': (
                rp.sha256_file(args.advisory_terms)
                if args.advisory_terms and Path(args.advisory_terms).exists()
                else None),
            'output': rp.sha256_file(str(out_path)),
        },
    }
    rp.atomic_write_json(str(manifest_path), manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
