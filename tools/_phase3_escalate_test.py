# -*- coding: utf-8 -*-
import phase3_escalate as pe


def row(identifier, cn='旧译', status='aligned'):
    return {
        'id': identifier, 'layer': 'int',
        'context': {'file': 'T.int', 'section': 'S', 'key': identifier},
        'en': identifier + ' source', 'cn': cn, 'tags': [], 'status': status,
    }


def result(identifier, action='keep', new_text='', confidence=0.99,
           uncertain=False):
    return {
        'id': identifier, 'action': action, 'new_text': new_text,
        'reason': '理由', 'confidence': confidence, 'uncertain': uncertain,
        'uncertain_reason': '疑点' if uncertain else '', '_old': '旧译',
    }


def main():
    corpus = [
        row('keep-high'), row('keep-low'), row('uncertain'), row('forced'),
        row('rewrite', '这是一条完整的旧译'), row('length', '旧译文'),
        row('missing', '', 'en_only'),
        {**row('dup-a'), 'en': 'Duplicate source'},
        {**row('dup-b'), 'en': 'Duplicate source'},
        {**row('format-bad', '杀死目标'), 'en': 'Kill §Victim§'},
        row('researched'),
        {**row('legacy-favor', '我并不赞成这件事。'),
         'en': "I'm not in favor of it."},
        {**row('exact-favor', '帮助'), 'en': 'Favor'},
        {**row('term-applied', '某个刺客的刀'),
         'en': "some assassin's blade"},
        {**row('term-already-present', '刺客之刃很锋利'),
         'en': "The Assassin's Blade is sharp"},
    ]
    results = [
        result('keep-high'),
        result('keep-low', confidence=0.9),
        result('uncertain', uncertain=True),
        result('forced'),
        result('rewrite', 'fix', '完全不同', 0.99),
        result('length', 'fix', '这是一条长得多得多得多的新译文', 0.99),
        result('missing', 'fix', '缺译已补', 0.99),
        result('dup-a'), result('dup-b', 'fix', '不同候选', 0.99),
        result('format-bad'), result('researched'),
        result('legacy-favor', 'fix', '从道德上说，我不帮助这件事。', 0.99),
        result('exact-favor', 'fix', '帮助', 0.99),
        result('term-applied', 'fix', '某个刺客的刺客之刃', 0.99),
        result('term-already-present', 'fix', '刺客之刃十分锋利', 0.99),
    ]
    selected, reasons = pe.build_escalation(
        corpus, results, {'forced'}, confidence_threshold=0.96,
        similarity_threshold=0.35, min_length_ratio=0.55,
        max_length_ratio=1.8,
        resolved_research_ids={'researched'}, terms={
            'Favor': '帮助', "Assassin's Blade": '刺客之刃',
        })
    ids = {entry['id'] for entry in selected}
    assert 'keep-high' not in ids
    assert {'keep-low', 'uncertain', 'forced', 'rewrite', 'length',
            'dup-a', 'dup-b'} <= ids
    assert {'format-bad', 'researched', 'legacy-favor'} <= ids
    assert 'missing' not in ids
    assert 'exact-favor' not in ids
    assert 'term-applied' in ids
    assert 'term-already-present' not in ids
    by_id = {entry['id']: entry for entry in selected}
    assert by_id['rewrite']['cn'] == '完全不同'
    assert by_id['rewrite']['prior_review']['original_cn'] == \
        '这是一条完整的旧译'
    assert reasons['low_confidence_decision'] == 1
    assert reasons['medium_uncertain'] == 1
    assert reasons['forced_regression_or_calibration_case'] == 1
    assert reasons['aggressive_rewrite'] >= 1
    assert reasons['visible_length_warning'] >= 1
    assert reasons['duplicate_decision_conflict'] == 2
    assert reasons['medium_format_violation'] == 1
    assert reasons['resolved_research_rule'] == 1
    assert reasons['legacy_term_scope_warning'] == 1
    assert reasons['term_direct_application'] == 1
    assert by_id['legacy-favor']['escalation']['legacy_only_terms'] == [
        {'en': 'Favor', 'cn': '帮助'}]
    assert by_id['term-applied']['term_review'] == {
        'mode': 'agent_secondary_review',
        'candidates': [{
            'en': "Assassin's Blade", 'cn': '刺客之刃',
            'source': 'hard_global',
            'requires_secondary_review': True,
            'old_contains_approved': False,
            'candidate_contains_approved': True,
        }],
    }

    advisory = [{
        'id': 'term:blade', 'en_term': "Assassin's Blade",
        'cn_term': '刺客之刃', 'scope': 'context_only',
        'confidence': 0.99, 'reason': '武器标签与普通所有格需区分',
        'evidence_ids': ['term-applied'], 'risk_tags': ['generic_phrase'],
    }]
    selected, advisory_reasons = pe.build_escalation(
        corpus, results, set(), confidence_threshold=0.96,
        similarity_threshold=0.35, min_length_ratio=0.55,
        max_length_ratio=1.8, terms={}, advisory_terms=advisory)
    advisory_by_id = {entry['id']: entry for entry in selected}
    assert advisory_reasons['term_direct_application'] == 1
    assert advisory_by_id['term-applied']['term_review']['candidates'][0][
        'source'] == 'advisory'
    print('phase3 escalation tests: PASS')


if __name__ == '__main__':
    main()
