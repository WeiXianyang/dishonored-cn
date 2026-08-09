# -*- coding: utf-8 -*-
"""Phase 4.5 防过修发布裁决门。

模型只负责对候选作反方裁决或在独立轮次中提出最小修复；本模块负责
风险分层、单写入规则、多源证据附着、修复后重审、默认回退和最终发布门禁。
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import phase3_attach_context as pac
import phase4_prepare as p4p
import review_pipeline as rp


RISK_ORDER = ('critical', 'high', 'medium', 'low')
CONSISTENCY_REVERT_SENTINEL = '__REVERT_CHANGED_ROWS__'
RESEARCH_STATUSES = {
    'direct_evidence', 'context_hits', 'context_only', 'conflict',
    'no_match', 'lookup_error',
}
NEGATION = ('不', '没', '无', '未', '别', '莫', '勿', '并非', '不能', '不会')
MODALITY = ('可能', '也许', '或许', '必须', '一定', '应该', '可以', '只能', '不得')
DIRECTION = ('进入', '离开', '返回', '前往', '带来', '带走', '升高', '降低',
             '上楼', '下楼', '向上', '向下', '左边', '右边', '里面', '外面',
             '之前', '之后', '远离', '靠近')
PRONOUNS = ('我', '你', '他', '她', '它', '我们', '你们', '他们', '她们')
EN_NEGATION = re.compile(
    r"\b(?:no|not|never|none|neither|nor|without|cannot|can't|won't|don't|"
    r"doesn't|didn't|isn't|aren't|wasn't|weren't)\b", re.I)
EN_MODALITY = re.compile(
    r'\b(?:may|might|could|should|must|possibly|probably|perhaps|only)\b', re.I)
EN_DIRECTION = re.compile(
    r'\b(?:up|down|before|after|left|right|inside|outside|into|out|back|'
    r'return|leave|enter|away|toward|towards|from|to)\b', re.I)
TITLE_PHRASE = re.compile(
    r"\b[A-Z][A-Za-z'’]*(?:\s+(?:of|the|and|de|von|[A-Z][A-Za-z'’]*)){0,5}")
TITLE_STOPWORDS = {
    'A', 'An', 'As', 'At', 'Be', 'Bring', 'But', 'Come', 'Do', 'Find', 'For',
    'From', 'Get', 'Go', 'He', 'Her', 'His', 'I', 'If', 'In', 'It', 'Its',
    'Keep', 'Meet', 'My', 'No', 'Not', 'Now', 'Of', 'On', 'Only', 'Optional',
    'Our', 'Return', 'She', 'Take', 'That', 'The', 'Their', 'Then', 'There',
    'These', 'They', 'This', 'Those', 'To', 'Use', 'We', 'What', 'When',
    'Where', 'Who', 'With', 'You', 'Your',
}


def read_jsonl(path):
    with open(path, encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def index_unique(rows, label):
    output = {}
    for row in rows:
        identifier = row.get('id')
        if not identifier or identifier in output:
            raise ValueError(f'{label} 存在空或重复 ID: {identifier!r}')
        output[identifier] = row
    return output


def effective_text(entry, result):
    return (result.get('new_text', '') if result.get('action') == 'fix'
            else entry.get('cn', ''))


def out_of_scope_reason(entry):
    """返回确定性作用域排除理由；空字符串表示玩家可见性尚不能排除。"""
    context = entry.get('context', {}) or {}
    if (entry.get('layer') == 'int' and
            str(context.get('file', '')).casefold() == 'dishonorededitor.int'):
        return '开发者 UnrealEd/调试界面文本；正常零售版游玩不会触发。'
    return ''


def sequence_change_ratio(old, new):
    return round(1 - difflib.SequenceMatcher(
        None, old or '', new or '', autojunk=False).ratio(), 6)


def marker_set(text, markers):
    return sorted(marker for marker in markers if marker in (text or ''))


def number_tokens(text):
    return re.findall(r'(?<![A-Za-z])\d+(?:[.,]\d+)?(?![A-Za-z])', text or '')


def placeholder_signature(text):
    return {
        'angle': re.findall(r'<[^>\r\n]+/?>', text or ''),
        'backtick': re.findall(r'`[^`\r\n]+`', text or ''),
        'newlines': (text or '').count('\n'),
    }


def title_subjects(source):
    output = []
    for match in TITLE_PHRASE.finditer(source or ''):
        value = re.sub(r'\s+', ' ', match.group(0)).strip()
        words = value.split()
        stripped_leader = False
        while len(words) > 1 and words[0] in TITLE_STOPWORDS:
            words.pop(0)
            stripped_leader = True
        value = ' '.join(words)
        if value in TITLE_STOPWORDS or len(value) < 3:
            continue
        # 句首单个大写词通常只是英语句首，不足以判定专名；若前面剥掉了
        # Meet/Find 等指令词，剩余单词仍可能是真正人物或地点名。
        if len(words) == 1 and match.start() == 0 and not stripped_leader:
            continue
        if value.casefold() not in {item.casefold() for item in output}:
            output.append(value)
    return output[:6]


def risk_profile(entry, original, candidate, source_route=''):
    ratio = sequence_change_ratio(original, candidate)
    flags = []
    if placeholder_signature(original) != placeholder_signature(candidate):
        flags.append('format_invariant_changed')
    if number_tokens(original) != number_tokens(candidate):
        flags.append('number_changed')
    if marker_set(original, NEGATION) != marker_set(candidate, NEGATION):
        flags.append('negation_changed')
    if marker_set(original, MODALITY) != marker_set(candidate, MODALITY):
        flags.append('modality_changed')
    if marker_set(original, DIRECTION) != marker_set(candidate, DIRECTION):
        flags.append('direction_changed')
    if marker_set(original, PRONOUNS) != marker_set(candidate, PRONOUNS):
        flags.append('participant_reference_changed')
    if ratio > 0.50:
        flags.append('rewrite_over_50pct')
    elif ratio > 0.30:
        flags.append('rewrite_over_30pct')
    elif ratio > 0.15:
        flags.append('rewrite_over_15pct')
    if entry.get('layer') == 'upk':
        flags.append('dialogue_or_voice')
    subjects = title_subjects(entry.get('en', ''))
    if subjects:
        flags.append('named_entity_or_title')
    if source_route == 'medium_decision':
        flags.append('single_medium_route')
    source = entry.get('en', '')
    if EN_NEGATION.search(source):
        flags.append('english_negation')
    if EN_MODALITY.search(source):
        flags.append('english_modality')
    if EN_DIRECTION.search(source):
        flags.append('english_direction')

    critical = {
        'format_invariant_changed', 'number_changed', 'negation_changed',
        'modality_changed', 'direction_changed', 'participant_reference_changed',
    }
    if critical.intersection(flags):
        level = 'critical'
    elif ratio > 0.30 or 'named_entity_or_title' in flags:
        level = 'high'
    elif ratio > 0.15 or entry.get('layer') == 'upk':
        level = 'medium'
    else:
        level = 'low'

    research_routes = ['local_corpus']
    if subjects or level in ('critical', 'high'):
        research_routes.extend([
            'dishonored_wiki', 'official_developer_or_publisher',
            'game_script_capture_or_walkthrough',
        ])
    return {
        'level': level,
        'change_ratio': ratio,
        'old_length': len(original or ''),
        'candidate_length': len(candidate or ''),
        'flags': flags,
        'research_routes': research_routes,
        'suggested_subjects': subjects,
    }


def same_english_index(corpus, candidate_results):
    groups = defaultdict(list)
    final = index_unique(candidate_results, 'candidate results')
    for entry in corpus:
        groups[(entry.get('en') or '').casefold()].append({
            'id': entry['id'],
            'release': (entry.get('domain', {}).get('primary_release') or
                        entry.get('domain', {}).get('release') or ''),
            'original_cn': entry.get('cn', ''),
            'candidate_cn': effective_text(entry, final[entry['id']]),
        })
    return groups


def build_review_corpus(corpus, candidate_results, parts_dir='data/raw/upk_parts',
                        include_already_reviewed=False):
    candidate = index_unique(candidate_results, 'candidate results')
    corpus_ids = {entry['id'] for entry in corpus}
    if set(candidate) != corpus_ids:
        raise ValueError('candidate results 与 corpus ID 覆盖不一致')
    neighbors = pac.build_neighbor_index(
        corpus, pac.load_upk_orders(parts_dir), radius=2)
    same_english = same_english_index(corpus, candidate_results)
    selected = []
    stats = Counter()
    for entry in corpus:
        row = candidate[entry['id']]
        if row.get('action') != 'fix':
            continue
        scope_reason = out_of_scope_reason(entry)
        if scope_reason:
            stats['excluded_nonretail_scope'] += 1
            continue
        if row.get('term_reviewed') and not include_already_reviewed:
            stats['excluded_existing_independent_review'] += 1
            continue
        original = entry.get('cn', '')
        current = effective_text(entry, row)
        risk = risk_profile(entry, original, current, row.get('route', ''))
        peer_rows = same_english.get((entry.get('en') or '').casefold(), [])
        peer_rows = [value for value in peer_rows if value['id'] != entry['id']]
        review = dict(entry)
        review['cn'] = current
        review['status'] = 'aligned'
        # 故意不传第一轮理由和置信度，避免反方 Agent 被锚定。
        review['prior_review'] = {'original_cn': original}
        review['escalation'] = {
            'reasons': ['release_gate_adversarial_review', *risk['flags']],
            'risk': risk,
            'single_write_rule': (
                '二审只能接受当前候选、完整回退 original_cn 或请求研究；'
                '不得输出第三版译文。'),
        }
        review['research_context'] = {
            'source_priority': [
                '本条英文与本地同场景/重复语料',
                '可定位的游戏脚本、对象绑定、实机截图或触发录像',
                '用户指定的 Dishonored Wiki',
                'Arkane/Bethesda/发行平台官方资料',
                '其他可靠一手资料或完整语境攻略',
                '一般词典与语言直觉',
            ],
            'game_context': p4p.build_game_context(entry),
            'local_neighbors': neighbors.get(entry['id'], []),
            'same_english_entries': peer_rows[:8],
            'external_research': [],
        }
        selected.append(review)
        stats[f'risk:{risk["level"]}'] += 1
        stats[f'route:{row.get("route", "")}'] += 1
        for flag in risk['flags']:
            stats[f'flag:{flag}'] += 1
    selected.sort(key=lambda row: (
        RISK_ORDER.index(row['escalation']['risk']['level']), row['id']))
    return selected, dict(sorted(stats.items()))


def validate_research_record(row, label):
    """验证研究适配器的最小证据契约。

    外部研究可来自 Wiki、官方资料、本地脚本或实机记录，字段可以
    更丰富，但不能只提供一个搜索命中或无来源的“结论”。
    """
    status = row.get('status')
    if status not in RESEARCH_STATUSES:
        raise ValueError(f'{label}: {row.get("id")}: 非法研究状态 {status!r}')
    if not str(row.get('finding', '')).strip():
        raise ValueError(f'{label}: {row.get("id")}: 研究记录缺少 finding')
    sources = row.get('sources', [])
    if not isinstance(sources, list) or any(
            not isinstance(source, dict) for source in sources):
        raise ValueError(f'{label}: {row.get("id")}: sources 必须是对象列表')
    if status == 'direct_evidence':
        usable = any(
            (source.get('url') or source.get('path')) and
            (source.get('excerpt') or source.get('evidence') or
             source.get('page_excerpt'))
            for source in sources)
        if not usable:
            raise ValueError(
                f'{label}: {row.get("id")}: direct_evidence 缺少可定位来源和证据摘要')


def attach_research(review_corpus, research_groups):
    known = {row['id'] for row in review_corpus}
    by_id = defaultdict(list)
    for label, rows in research_groups:
        for row in rows:
            identifier = row.get('id')
            if identifier not in known:
                raise ValueError(f'{label} 含未知 review ID: {identifier!r}')
            validate_research_record(row, label)
            enriched = dict(row)
            enriched['research_source'] = label
            by_id[identifier].append(enriched)
    output = []
    for row in review_corpus:
        enriched = dict(row)
        context = dict(enriched.get('research_context') or {})
        existing = list(context.get('external_research') or [])
        context['external_research'] = existing + by_id.get(row['id'], [])
        enriched['research_context'] = context
        output.append(enriched)
    return output, {
        'review_entries': len(review_corpus),
        'research_rows': sum(len(rows) for _label, rows in research_groups),
        'researched_ids': len(by_id),
    }


def build_repair_corpus(review_corpus, critic_results):
    reviews = index_unique(review_corpus, 'repair source review corpus')
    decisions = index_unique(critic_results, 'repair source critic results')
    if set(reviews) != set(decisions):
        raise ValueError('repair source critic results 覆盖不完整')
    output = []
    for identifier, entry in reviews.items():
        decision = decisions[identifier]
        if validate_critic_decision(entry, decision) != 'research':
            continue
        original = (entry.get('prior_review') or {}).get('original_cn', '')
        repair = dict(entry)
        repair['cn'] = original
        repair['prior_review'] = {
            'original_cn': original,
            'rejected_candidate_cn': entry.get('cn', ''),
            'critic_reason': decision.get('reason', ''),
            'repair_focus': decision.get('uncertain_reason', ''),
        }
        risk = (entry.get('escalation') or {}).get('risk', {})
        repair['escalation'] = {
            'reasons': ['release_gate_repair_proposal', *risk.get('flags', [])],
            'risk': risk,
            'repair_rule': (
                '以 original_cn 为底稿，只修 critic 指出的硬错；'
                '不得复用已被否决的无关改写。'),
        }
        output.append(repair)
    return output


def build_rereview_corpus(repair_corpus, repair_results):
    repairs = index_unique(repair_corpus, 'repair corpus')
    results = index_unique(repair_results, 'repair results')
    if set(repairs) != set(results):
        raise ValueError('repair results 与 repair corpus 覆盖不一致')
    output = []
    unresolved = []
    for identifier, entry in repairs.items():
        result = results[identifier]
        if result.get('uncertain') or result.get('action') != 'fix':
            unresolved.append({
                'id': identifier, 'en': entry.get('en', ''),
                'original_cn': (entry.get('prior_review') or {}).get(
                    'original_cn', ''),
                'rejected_candidate_cn': (entry.get('prior_review') or {}).get(
                    'rejected_candidate_cn', ''),
                'reason': result.get('reason', ''),
                'uncertain_reason': result.get('uncertain_reason', ''),
                'research_context': entry.get('research_context', {}),
            })
            continue
        candidate = result.get('new_text', '')
        original = (entry.get('prior_review') or {}).get('original_cn', '')
        rereview = dict(entry)
        rereview['cn'] = candidate
        rereview['prior_review'] = {'original_cn': original}
        risk = (entry.get('escalation') or {}).get('risk', {})
        rereview['escalation'] = {
            'reasons': [
                'release_gate_adversarial_review', 'repaired_candidate',
                *risk.get('flags', []),
            ],
            'risk': risk,
            'single_write_rule': (
                '二审只能接受修补候选、完整回退 original_cn 或再次请求研究。'),
        }
        output.append(rereview)
    return output, unresolved


def merge_repair_round(review_corpus, critic_results, rereview_corpus,
                       rereview_results):
    reviews = index_unique(review_corpus, 'merge source review corpus')
    decisions = index_unique(critic_results, 'merge source critic results')
    rereviews = index_unique(rereview_corpus, 'merge rereview corpus')
    redecisions = index_unique(rereview_results, 'merge rereview results')
    if set(reviews) != set(decisions):
        raise ValueError('merge source decisions 覆盖不完整')
    if set(rereviews) != set(redecisions):
        raise ValueError('merge rereview decisions 覆盖不完整')
    unknown = sorted(set(rereviews) - set(reviews))
    if unknown:
        raise ValueError(f'rereview 含未知 ID: {unknown[:5]}')
    for identifier in rereviews:
        if validate_critic_decision(reviews[identifier], decisions[identifier]) != 'research':
            raise ValueError(f'{identifier}: 只有初审 research 项才能替换')
        validate_critic_decision(rereviews[identifier], redecisions[identifier])
    merged_reviews = [
        rereviews.get(row['id'], row) for row in review_corpus]
    merged_decisions = [
        redecisions.get(row['id'], row) for row in critic_results]
    return merged_reviews, merged_decisions


def validate_critic_decision(entry, decision):
    original = entry.get('prior_review', {}).get('original_cn', '')
    if decision.get('uncertain'):
        if not decision.get('uncertain_reason', '').strip():
            raise ValueError(f'{entry["id"]}: uncertain 缺少具体研究焦点')
        return 'research'
    if decision.get('action') == 'keep':
        if decision.get('new_text'):
            raise ValueError(f'{entry["id"]}: accept 时 new_text 必须为空')
        return 'accept'
    if decision.get('action') == 'fix':
        if decision.get('new_text') != original:
            raise ValueError(
                f'{entry["id"]}: 违反单写入规则；二审只能完整回退天邈原译')
        return 'revert'
    raise ValueError(f'{entry["id"]}: 非法 critic action')


def finalize(corpus, candidate_results, review_corpus, critic_results):
    candidate = index_unique(candidate_results, 'candidate results')
    reviews = index_unique(review_corpus, 'review corpus')
    decisions = index_unique(critic_results, 'critic results')
    if set(reviews) != set(decisions):
        raise ValueError('critic results 与 review corpus 覆盖不一致')
    if set(candidate) != {row['id'] for row in corpus}:
        raise ValueError('candidate results 与 corpus 覆盖不一致')
    output = []
    unresolved = []
    stats = Counter()
    for entry in corpus:
        identifier = entry['id']
        row = dict(candidate[identifier])
        original = entry.get('cn', '')
        scope_reason = out_of_scope_reason(entry)
        if row.get('action') == 'fix' and scope_reason:
            row.update({
                'action': 'keep', 'new_text': '',
                'reason': scope_reason,
                'confidence': 1.0, 'uncertain': False,
                'uncertain_reason': '',
                'route': 'release_gate_scope_revert',
                'release_gate_reviewed': True,
                'release_gate_decision': 'revert_out_of_scope',
                'release_gate_reason': scope_reason,
            })
            stats['reverted_nonretail_scope'] += 1
            output.append(row)
            continue
        if identifier not in reviews:
            if row.get('action') == 'fix' and row.get('term_reviewed'):
                row['release_gate_reviewed'] = True
                row['release_gate_decision'] = 'accepted_existing_term_secondary'
                stats['accepted_existing_term_secondary'] += 1
            output.append(row)
            continue
        review = reviews[identifier]
        decision = decisions[identifier]
        verdict = validate_critic_decision(review, decision)
        risk = review.get('escalation', {}).get('risk', {})
        common = {
            'release_gate_reviewed': verdict != 'research',
            'release_gate_decision': verdict,
            'release_gate_risk': risk,
            'release_gate_reason': decision.get('reason', ''),
            'release_gate_confidence': decision.get('confidence'),
        }
        if verdict == 'accept':
            reviewed_candidate = review.get('cn', '')
            row.update(common)
            row.update({
                'action': 'fix' if reviewed_candidate != original else 'keep',
                'new_text': reviewed_candidate if reviewed_candidate != original else '',
                'reason': decision.get('reason', ''),
                'confidence': decision.get('confidence'),
                'uncertain': False, 'uncertain_reason': '',
                'route': 'release_gate_accept',
            })
            if row['action'] == 'fix':
                stats['accepted_candidate'] += 1
            else:
                stats['accepted_baseline_equivalent'] += 1
        elif verdict == 'revert':
            row.update(common)
            row.update({
                'action': 'keep', 'new_text': '',
                'reason': decision.get('reason', ''),
                'confidence': decision.get('confidence'),
                'uncertain': False, 'uncertain_reason': '',
                'route': 'release_gate_revert_tianmiao',
            })
            stats['reverted_tianmiao'] += 1
        else:
            row.update(common)
            row.update({
                'action': 'keep', 'new_text': '',
                'reason': '反方二审未能唯一裁决；候选不得进入补丁。',
                'confidence': decision.get('confidence'),
                'uncertain': True,
                'uncertain_reason': decision.get('uncertain_reason', ''),
                'route': 'release_gate_research_required',
            })
            unresolved.append({
                'id': identifier, 'en': entry.get('en', ''),
                'original_cn': original, 'candidate_cn': review.get('cn', ''),
                'context': entry.get('context', {}),
                'game_context': (review.get('research_context') or {}).get(
                    'game_context', {}),
                'risk': risk,
                'reason': decision.get('reason', ''),
                'uncertain_reason': decision.get('uncertain_reason', ''),
                'suggested_wiki_query': (
                    risk.get('suggested_subjects') or [entry.get('en', '')[:160]])[0],
                'source_priority': (review.get('research_context') or {}).get(
                    'source_priority', []),
            })
            stats['research_required'] += 1
        output.append(row)

    accepted = []
    output_by_id = index_unique(output, 'release gate output')
    for entry in corpus:
        row = output_by_id[entry['id']]
        if row.get('action') != 'fix':
            continue
        accepted.append({
            **row, 'layer': entry.get('layer'),
            'context': entry.get('context', {}), 'en': entry.get('en', ''),
            'old_text': entry.get('cn', ''),
        })
    summary = {
        'source_entries': len(corpus), 'review_entries': len(reviews),
        'accepted_fixes': len(accepted), 'unresolved': len(unresolved),
        'decisions': dict(sorted(stats.items())),
        'actions': dict(sorted(Counter(
            row.get('action') for row in output).items())),
    }
    return output, accepted, unresolved, summary


def release_code(entry):
    domain = entry.get('domain', {}) or {}
    return (domain.get('primary_release') or domain.get('release') or
            ','.join(domain.get('releases') or []) or 'unknown')


def consistency_conflicts(corpus, final_results):
    final = index_unique(final_results, 'consistency final')
    groups = defaultdict(list)
    for entry in corpus:
        source = entry.get('en', '')
        if not source:
            continue
        row = final[entry['id']]
        groups[(release_code(entry), source)].append({
            'id': entry['id'], 'cn': effective_text(entry, row),
            'changed': row.get('action') == 'fix',
        })
    output = []
    for (release, source), rows in groups.items():
        values = sorted({row['cn'] for row in rows})
        if len(rows) < 2 or len(values) < 2 or not any(
                row['changed'] for row in rows):
            continue
        raw = rp.canonical_json({'release': release, 'en': source})
        output.append({
            'group_id': 'same-en:' + hashlib.sha256(
                raw.encode('utf-8')).hexdigest()[:16],
            'release': release, 'en': source,
            'target_variants': values,
            'rows': rows,
        })
    output.sort(key=lambda row: (row['release'], row['en'], row['group_id']))
    return output


def build_consistency_review_corpus(corpus, final_results, examples_per_variant=5):
    """将同英文冲突压缩成组级反方复核语料。

    大型重复组可包含数百个资源实例；模型只看按目标译文分组的计数和
    代表上下文，合并器则使用原始完整冲突组执行确定性回退。
    """
    if examples_per_variant < 1:
        raise ValueError('examples_per_variant 必须大于 0')
    corpus_by_id = index_unique(corpus, 'consistency corpus')
    rows = []
    for conflict in consistency_conflicts(corpus, final_results):
        variants = defaultdict(list)
        for item in conflict['rows']:
            entry = corpus_by_id[item['id']]
            variants[item['cn']].append({
                'id': item['id'], 'changed': item['changed'],
                'layer': entry.get('layer'),
                'baseline_cn': entry.get('cn', ''),
                'game_context': p4p.build_game_context(entry),
                'context': entry.get('context', {}),
            })
        variant_summaries = []
        for target, examples in sorted(variants.items()):
            examples.sort(key=lambda value: (not value['changed'], value['id']))
            variant_summaries.append({
                'target_cn': target,
                'row_count': len(examples),
                'changed_count': sum(item['changed'] for item in examples),
                'examples': examples[:examples_per_variant],
                'examples_truncated': max(0, len(examples) - examples_per_variant),
            })
        rows.append({
            'id': conflict['group_id'], 'layer': 'int',
            'en': conflict['en'], 'cn': CONSISTENCY_REVERT_SENTINEL,
            'status': 'aligned',
            'context': {
                'file': 'phase45-consistency',
                'section': conflict['release'],
                'key': conflict['group_id'],
            },
            'prior_review': {'original_cn': CONSISTENCY_REVERT_SENTINEL},
            'escalation': {
                'reasons': ['release_gate_consistency_review'],
                'decision_contract': (
                    'keep=有证据地允许上下文差异；fix=回退本组所有已改行；'
                    'uncertain=请求研究；不得生成新译文。'),
            },
            'research_context': {
                'release': conflict['release'],
                'source_english': conflict['en'],
                'row_count': len(conflict['rows']),
                'variant_count': len(variant_summaries),
                'variants': variant_summaries,
                'source_priority': [
                    '资源路径、对象类型和触发语境',
                    '同场景语料与可定位游戏内容',
                    'Dishonored Wiki 与官方资料',
                ],
            },
        })
    return rows


def merge_consistency_review(corpus, final_results, review_corpus,
                             review_results):
    reviews = index_unique(review_corpus, 'consistency review corpus')
    decisions = index_unique(review_results, 'consistency review results')
    if set(reviews) != set(decisions):
        raise ValueError('consistency review results 与 review corpus 覆盖不一致')
    conflicts = {
        row['group_id']: row for row in consistency_conflicts(
            corpus, final_results)}
    if set(reviews) != set(conflicts):
        raise ValueError('consistency review corpus 已与当前冲突集漂移')
    output = [dict(row) for row in final_results]
    output_by_id = index_unique(output, 'consistency output')
    exceptions = []
    unresolved = []
    stats = Counter()
    for group_id, entry in reviews.items():
        decision = decisions[group_id]
        if decision.get('uncertain'):
            if (decision.get('action') != 'keep' or decision.get('new_text') or
                    not str(decision.get('uncertain_reason', '')).strip()):
                raise ValueError(f'{group_id}: consistency research 裁决非法')
            unresolved.append({
                'group_id': group_id, 'en': entry.get('en', ''),
                'reason': decision.get('reason', ''),
                'uncertain_reason': decision.get('uncertain_reason', ''),
                'research_context': entry.get('research_context', {}),
            })
            stats['research_required'] += 1
            continue
        if decision.get('action') == 'keep' and not decision.get('new_text'):
            reason = str(decision.get('reason', '')).strip()
            if not reason:
                raise ValueError(f'{group_id}: consistency exception 缺少理由')
            exceptions.append({
                'group_id': group_id, 'reason': reason,
                'review_confidence': decision.get('confidence'),
            })
            stats['accepted_context_exception'] += 1
            continue
        if (decision.get('action') != 'fix' or
                decision.get('new_text') != CONSISTENCY_REVERT_SENTINEL):
            raise ValueError(f'{group_id}: consistency 复核试图写入新译文')
        reverted = 0
        for item in conflicts[group_id]['rows']:
            if not item['changed']:
                continue
            row = output_by_id[item['id']]
            row.update({
                'action': 'keep', 'new_text': '',
                'reason': decision.get('reason', ''),
                'confidence': decision.get('confidence'),
                'uncertain': False, 'uncertain_reason': '',
                'route': 'release_gate_revert_consistency_conflict',
                'release_gate_reviewed': True,
                'release_gate_decision': 'revert_consistency_conflict',
                'release_gate_reason': decision.get('reason', ''),
            })
            reverted += 1
        stats['reverted_changed_rows'] += reverted
        stats['reverted_groups'] += 1
    return output, exceptions, unresolved, dict(sorted(stats.items()))


def load_consistency_exceptions(rows):
    output = {}
    for index, row in enumerate(rows or []):
        if (not isinstance(row, dict) or
                not isinstance(row.get('group_id'), str) or
                not row['group_id'] or
                not isinstance(row.get('reason'), str) or
                not row['reason'].strip()):
            raise ValueError(f'consistency exceptions[{index}] 字段非法')
        if row['group_id'] in output:
            raise ValueError(f'重复 consistency exception: {row["group_id"]}')
        output[row['group_id']] = row
    return output


def verify_release(corpus, final_results, consistency_exceptions=None):
    final = index_unique(final_results, 'release gate final')
    errors = []
    if set(final) != {row['id'] for row in corpus}:
        errors.append('最终结果与 corpus ID 覆盖不一致')
    checked = 0
    for entry in corpus:
        row = final.get(entry['id'])
        if not row:
            continue
        if row.get('uncertain'):
            errors.append(f'{entry["id"]}: 仍为 uncertain')
        if row.get('action') != 'fix':
            continue
        checked += 1
        if not row.get('release_gate_reviewed'):
            errors.append(f'{entry["id"]}: fix 缺少 release_gate_reviewed')
        item = {'id': entry['id'], 'action': 'fix',
                'new_text': row.get('new_text', '')}
        if not rp.check_placeholders(item, entry):
            errors.append(f'{entry["id"]}: 占位符/换行不一致')
    conflicts = consistency_conflicts(corpus, final_results)
    exceptions = load_consistency_exceptions(consistency_exceptions)
    conflict_ids = {row['group_id'] for row in conflicts}
    unknown_exceptions = sorted(set(exceptions) - conflict_ids)
    if unknown_exceptions:
        errors.append(
            f'一致性例外引用已不存在的 group_id: {unknown_exceptions[:5]}')
    unresolved_conflicts = [
        row for row in conflicts if row['group_id'] not in exceptions]
    if unresolved_conflicts:
        errors.append(
            f'存在 {len(unresolved_conflicts)} 个未裁决的同英文同版本译文差异')
    return {
        'status': 'pass' if not errors else 'fail',
        'corpus': len(corpus), 'final': len(final),
        'checked_fixes': checked,
        'consistency_conflicts': len(conflicts),
        'consistency_exceptions': len(exceptions),
        'unresolved_consistency_conflicts': unresolved_conflicts,
        'errors': errors,
    }


def write_prepare(args):
    out = Path(args.out_dir)
    (out / 'queues').mkdir(parents=True, exist_ok=True)
    corpus = read_jsonl(args.corpus)
    candidates = read_jsonl(args.candidate_results)
    reviews, stats = build_review_corpus(
        corpus, candidates, args.parts_dir, args.include_already_reviewed)
    review_path = out / 'review_corpus.jsonl'
    rp.atomic_write_jsonl(str(review_path), reviews)
    queue_hashes = {}
    for level in RISK_ORDER:
        path = out / 'queues' / f'{level}.jsonl'
        rows = [row for row in reviews
                if row['escalation']['risk']['level'] == level]
        rp.atomic_write_jsonl(str(path), rows)
        queue_hashes[level] = rp.sha256_file(str(path))
    manifest = {
        'created_at': rp.now_utc(), 'source_entries': len(corpus),
        'selected_entries': len(reviews), 'stats': stats,
        'single_write_rule': True,
        'source_priority': [
            'local_corpus', 'game_script_capture_or_walkthrough',
            'dishonored_wiki',
            'official_developer_or_publisher',
            'other_primary_or_full_context_walkthrough', 'language_reference',
        ],
        'hashes': {
            'corpus': rp.sha256_file(args.corpus),
            'candidate_results': rp.sha256_file(args.candidate_results),
            'review_corpus': rp.sha256_file(str(review_path)),
            'queues': queue_hashes,
        },
    }
    rp.atomic_write_json(str(out / 'prepare_manifest.json'), manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


def write_attach(args):
    rows = read_jsonl(args.review_corpus)
    groups = [(path, read_jsonl(path)) for path in args.research]
    output, stats = attach_research(rows, groups)
    rp.atomic_write_jsonl(args.out, output)
    manifest = {
        'created_at': rp.now_utc(), **stats,
        'hashes': {
            'review_corpus': rp.sha256_file(args.review_corpus),
            'research': {path: rp.sha256_file(path) for path in args.research},
            'output': rp.sha256_file(args.out),
        },
    }
    rp.atomic_write_json(args.out + '.manifest.json', manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


def combined_jsonl(paths, label):
    rows = [row for path in paths for row in read_jsonl(path)]
    index_unique(rows, label)
    return rows


def write_prepare_repairs(args):
    critics = combined_jsonl(args.critic_results, 'critic result groups')
    review_corpus = read_jsonl(args.review_corpus)
    repairs = build_repair_corpus(review_corpus, critics)
    rp.atomic_write_jsonl(args.out, repairs)
    research_queue_path = args.research_queue or args.out + '.research_queue.json'
    research_items = rp.build_wiki_lookup_items(
        [row for row in critics if row.get('uncertain')], review_corpus)
    rp.atomic_write_json(research_queue_path, {
        'source': 'Phase 4.5 adversarial critic research_required results',
        'lookup_site': 'https://dishonored.fandom.com/wiki/',
        'site_note': (
            '先路由本地语境/Wiki/语言修复；Wiki 只作证据，'
            '重要事实继续与游戏内容或官方资料交叉核对。'),
        'count': len(research_items), 'items': research_items,
    })
    summary = {
        'created_at': rp.now_utc(), 'repair_entries': len(repairs),
        'research_queue_entries': len(research_items),
        'hashes': {
            'review_corpus': rp.sha256_file(args.review_corpus),
            'critic_results': {
                path: rp.sha256_file(path) for path in args.critic_results},
            'output': rp.sha256_file(args.out),
            'research_queue': rp.sha256_file(research_queue_path),
        },
    }
    rp.atomic_write_json(args.out + '.manifest.json', summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def write_prepare_rereview(args):
    repairs = read_jsonl(args.repair_corpus)
    results = combined_jsonl(args.repair_results, 'repair result groups')
    rereviews, unresolved = build_rereview_corpus(repairs, results)
    rp.atomic_write_jsonl(args.out, rereviews)
    rp.atomic_write_jsonl(args.unresolved, unresolved)
    summary = {
        'created_at': rp.now_utc(), 'repair_entries': len(repairs),
        'rereview_entries': len(rereviews),
        'unresolved_repairs': len(unresolved),
        'hashes': {
            'repair_corpus': rp.sha256_file(args.repair_corpus),
            'repair_results': {
                path: rp.sha256_file(path) for path in args.repair_results},
            'rereview': rp.sha256_file(args.out),
            'unresolved': rp.sha256_file(args.unresolved),
        },
    }
    rp.atomic_write_json(args.out + '.manifest.json', summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def write_merge_round(args):
    critics = combined_jsonl(args.critic_results, 'critic result groups')
    recritics = combined_jsonl(
        args.rereview_results, 'rereview result groups')
    reviews, decisions = merge_repair_round(
        read_jsonl(args.review_corpus), critics,
        read_jsonl(args.rereview_corpus), recritics)
    rp.atomic_write_jsonl(args.out_review_corpus, reviews)
    rp.atomic_write_jsonl(args.out_results, decisions)
    summary = {
        'created_at': rp.now_utc(), 'review_entries': len(reviews),
        'replaced_entries': len(read_jsonl(args.rereview_corpus)),
        'hashes': {
            'review_corpus': rp.sha256_file(args.out_review_corpus),
            'results': rp.sha256_file(args.out_results),
        },
    }
    rp.atomic_write_json(args.out_results + '.manifest.json', summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def write_prepare_consistency(args):
    corpus = read_jsonl(args.corpus)
    final_results = read_jsonl(args.final_results)
    rows = build_consistency_review_corpus(
        corpus, final_results, args.examples_per_variant)
    rp.atomic_write_jsonl(args.out, rows)
    summary = {
        'created_at': rp.now_utc(), 'conflict_groups': len(rows),
        'examples_per_variant': args.examples_per_variant,
        'hashes': {
            'corpus': rp.sha256_file(args.corpus),
            'final_results': rp.sha256_file(args.final_results),
            'output': rp.sha256_file(args.out),
        },
    }
    rp.atomic_write_json(args.out + '.manifest.json', summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def write_merge_consistency(args):
    results = combined_jsonl(
        args.review_results, 'consistency review result groups')
    output, exceptions, unresolved, stats = merge_consistency_review(
        read_jsonl(args.corpus), read_jsonl(args.final_results),
        read_jsonl(args.review_corpus), results)
    rp.atomic_write_jsonl(args.out_results, output)
    rp.atomic_write_json(args.out_exceptions, exceptions)
    rp.atomic_write_jsonl(args.out_unresolved, unresolved)
    summary = {
        'created_at': rp.now_utc(), 'review_groups': len(results),
        'exceptions': len(exceptions), 'unresolved': len(unresolved),
        'stats': stats,
        'hashes': {
            'corpus': rp.sha256_file(args.corpus),
            'input_results': rp.sha256_file(args.final_results),
            'review_corpus': rp.sha256_file(args.review_corpus),
            'review_results': {
                path: rp.sha256_file(path) for path in args.review_results},
            'output_results': rp.sha256_file(args.out_results),
            'exceptions': rp.sha256_file(args.out_exceptions),
            'unresolved': rp.sha256_file(args.out_unresolved),
        },
    }
    rp.atomic_write_json(args.out_results + '.manifest.json', summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def write_finalize(args):
    results = combined_jsonl(args.review_results, 'final critic result groups')
    corpus = read_jsonl(args.corpus)
    final_rows, accepted, unresolved, summary = finalize(
        corpus, read_jsonl(args.candidate_results),
        read_jsonl(args.review_corpus), results)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        'final_results': out / 'final_results.jsonl',
        'accepted_fixes': out / 'accepted_fixes.jsonl',
        'research_required': out / 'research_required.jsonl',
    }
    rp.atomic_write_jsonl(str(paths['final_results']), final_rows)
    rp.atomic_write_jsonl(str(paths['accepted_fixes']), accepted)
    rp.atomic_write_jsonl(str(paths['research_required']), unresolved)
    summary['created_at'] = rp.now_utc()
    summary['hashes'] = {
        'corpus': rp.sha256_file(args.corpus),
        'candidate_results': rp.sha256_file(args.candidate_results),
        'review_corpus': rp.sha256_file(args.review_corpus),
        'review_results': {
            path: rp.sha256_file(path) for path in args.review_results},
        **{name: rp.sha256_file(str(path)) for name, path in paths.items()},
    }
    rp.atomic_write_json(str(out / 'summary.json'), summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def write_verify(args):
    exception_rows = (json.loads(Path(args.consistency_exceptions).read_text(
        encoding='utf-8')) if args.consistency_exceptions and
        Path(args.consistency_exceptions).exists() else [])
    result = verify_release(
        read_jsonl(args.corpus), read_jsonl(args.final_results), exception_rows)
    result['created_at'] = rp.now_utc()
    result['hashes'] = {
        'corpus': rp.sha256_file(args.corpus),
        'final_results': rp.sha256_file(args.final_results),
    }
    rp.atomic_write_json(args.out, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['status'] == 'pass' else 1


def build_parser():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    prepare = sub.add_parser('prepare')
    prepare.add_argument('--corpus', default='data/aligned/corpus.jsonl')
    prepare.add_argument('--candidate-results', default=(
        'data/review/phase4-term-reviewed/final_results.jsonl'))
    prepare.add_argument('--parts-dir', default='data/raw/upk_parts')
    prepare.add_argument('--out-dir', default='data/review/phase45')
    prepare.add_argument('--include-already-reviewed', action='store_true')
    attach = sub.add_parser('attach-research')
    attach.add_argument('--review-corpus', required=True)
    attach.add_argument('--research', action='append', required=True)
    attach.add_argument('--out', required=True)
    repair = sub.add_parser('prepare-repairs')
    repair.add_argument('--review-corpus', required=True)
    repair.add_argument('--critic-results', action='append', required=True)
    repair.add_argument('--out', required=True)
    repair.add_argument('--research-queue')
    rereview = sub.add_parser('prepare-rereview')
    rereview.add_argument('--repair-corpus', required=True)
    rereview.add_argument('--repair-results', action='append', required=True)
    rereview.add_argument('--out', required=True)
    rereview.add_argument('--unresolved', required=True)
    merge = sub.add_parser('merge-round')
    merge.add_argument('--review-corpus', required=True)
    merge.add_argument('--critic-results', action='append', required=True)
    merge.add_argument('--rereview-corpus', required=True)
    merge.add_argument('--rereview-results', action='append', required=True)
    merge.add_argument('--out-review-corpus', required=True)
    merge.add_argument('--out-results', required=True)
    consistency = sub.add_parser('prepare-consistency')
    consistency.add_argument('--corpus', default='data/aligned/corpus.jsonl')
    consistency.add_argument('--final-results', required=True)
    consistency.add_argument('--out', required=True)
    consistency.add_argument('--examples-per-variant', type=int, default=5)
    merge_consistency = sub.add_parser('merge-consistency')
    merge_consistency.add_argument(
        '--corpus', default='data/aligned/corpus.jsonl')
    merge_consistency.add_argument('--final-results', required=True)
    merge_consistency.add_argument('--review-corpus', required=True)
    merge_consistency.add_argument('--review-results', action='append', required=True)
    merge_consistency.add_argument('--out-results', required=True)
    merge_consistency.add_argument('--out-exceptions', required=True)
    merge_consistency.add_argument('--out-unresolved', required=True)
    finish = sub.add_parser('finalize')
    finish.add_argument('--corpus', default='data/aligned/corpus.jsonl')
    finish.add_argument('--candidate-results', default=(
        'data/review/phase4-term-reviewed/final_results.jsonl'))
    finish.add_argument('--review-corpus', default=(
        'data/review/phase45/review_corpus.jsonl'))
    finish.add_argument('--review-results', action='append', required=True)
    finish.add_argument('--out-dir', default='data/review/phase45-final')
    verify = sub.add_parser('verify')
    verify.add_argument('--corpus', default='data/aligned/corpus.jsonl')
    verify.add_argument('--final-results', default=(
        'data/review/phase45-final/final_results.jsonl'))
    verify.add_argument('--out', default=(
        'data/review/phase45-final/release_gate_verification.json'))
    verify.add_argument('--consistency-exceptions', default=(
        'research/phase45_consistency_exceptions.json'))
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command == 'prepare':
        write_prepare(args)
        return 0
    if args.command == 'attach-research':
        write_attach(args)
        return 0
    if args.command == 'prepare-repairs':
        write_prepare_repairs(args)
        return 0
    if args.command == 'prepare-rereview':
        write_prepare_rereview(args)
        return 0
    if args.command == 'merge-round':
        write_merge_round(args)
        return 0
    if args.command == 'prepare-consistency':
        write_prepare_consistency(args)
        return 0
    if args.command == 'merge-consistency':
        write_merge_consistency(args)
        return 0
    if args.command == 'finalize':
        write_finalize(args)
        return 0
    return write_verify(args)


if __name__ == '__main__':
    raise SystemExit(main())
