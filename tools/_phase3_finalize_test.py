# -*- coding: utf-8 -*-
import phase3_finalize as pf


def source(identifier, en='English', cn='旧译', status='aligned'):
    return {
        'id': identifier, 'layer': 'int',
        'context': {'file': 'T.int', 'section': 'S', 'key': identifier},
        'en': en, 'cn': cn, 'tags': [], 'status': status,
    }


def review(identifier, action='keep', new_text='', confidence=0.99,
           uncertain=False):
    return {
        'id': identifier, 'action': action, 'new_text': new_text,
        'reason': '判断', 'confidence': confidence, 'uncertain': uncertain,
        'uncertain_reason': '需人工' if uncertain else '', '_old': '旧译',
    }


def escalated(entry, medium, reasons=None, term_review=None):
    baseline = medium['new_text'] if medium['action'] == 'fix' else entry['cn']
    out = dict(entry, cn=baseline, status='aligned')
    out['prior_review'] = {
        'original_cn': entry['cn'], 'medium_action': medium['action'],
        'medium_candidate_cn': baseline,
    }
    out['escalation'] = {'reasons': reasons or ['test']}
    if term_review:
        out['term_review'] = term_review
    return out


def main():
    corpus = [
        source('medium-fix'), source('medium-keep'), source('high-revert'),
        source('high-fix'), source('high-uncertain'),
        source('term-rejected', "some assassin's blade", '某个刺客的刀'),
        source('auto', '', '', 'aligned'), source('cn-only', '', '只有中文', 'cn_only'),
    ]
    medium = [
        review('medium-fix', 'fix', '中阶修补'), review('medium-keep'),
        review('high-revert', 'fix', '过度改写', 0.9),
        review('high-fix', 'keep', confidence=0.9),
        review('high-uncertain', 'fix', '待定候选', 0.7, True),
        review('term-rejected', 'fix', '某个刺客的刺客之刃', 0.99),
    ]
    by_id = {entry['id']: entry for entry in corpus}
    medium_by_id = {item['id']: item for item in medium}
    escalation = [
        escalated(by_id[identifier], medium_by_id[identifier])
        for identifier in ('high-revert', 'high-fix', 'high-uncertain')]
    escalation.append(escalated(
        by_id['term-rejected'], medium_by_id['term-rejected'],
        reasons=['term_direct_application'], term_review={
            'mode': 'agent_secondary_review',
            'candidates': [{
                'en': "Assassin's Blade", 'cn': '刺客之刃',
                'old_contains_approved': False,
                'candidate_contains_approved': True,
            }],
        }))
    high = [
        review('high-revert', 'fix', '旧译'),
        review('high-fix', 'fix', '高阶修补'),
        review('high-uncertain', 'keep', confidence=0.5, uncertain=True),
        review('term-rejected', 'fix', '某个刺客的刀刃'),
    ]
    automatic = [review('auto')]
    unpaired = [review('cn-only', confidence=0.0, uncertain=True)]
    final, accepted, human, routes = pf.build_final(
        corpus, medium, automatic, unpaired, escalation, high,
        {"Assassin's Blade": '刺客之刃'})
    result = {item['id']: item for item in final}
    assert len(final) == 8
    assert result['medium-fix']['action'] == 'fix'
    assert result['high-revert']['action'] == 'keep'
    assert result['high-revert']['route'] == 'high_revert_to_tianmiao'
    assert result['high-fix']['new_text'] == '高阶修补'
    assert result['high-uncertain']['action'] == 'keep'
    assert result['high-uncertain']['uncertain']
    assert result['term-rejected']['new_text'] == '某个刺客的刀刃'
    assert result['term-rejected']['term_reviewed']
    assert result['term-rejected']['term_scope_overrides'] == [{
        'en': "Assassin's Blade", 'cn': '刺客之刃',
    }]
    assert result['auto']['route'] == 'automatic_empty_keep'
    assert result['cn-only']['route'] == 'human_unpaired_cn_only'
    assert {item['id'] for item in accepted} == {
        'medium-fix', 'high-fix', 'term-rejected'}
    assert {item['id'] for item in human} == {'high-uncertain', 'cn-only'}
    assert sum(routes.values()) == 8

    try:
        pf.build_final(corpus, medium, automatic, unpaired, escalation, high[:-1], {})
    except ValueError as exc:
        assert 'High 覆盖不完整' in str(exc)
    else:
        raise AssertionError('未拒绝不完整 High 结果')

    effective, count = pf.merge_high_overrides(
        high, [('targeted', [review('high-fix', 'fix', '定向复审')])])
    assert count == 1
    assert [item['id'] for item in effective] == [item['id'] for item in high]
    assert {item['id']: item for item in effective}['high-fix']['new_text'] == '定向复审'
    try:
        pf.merge_high_overrides(high, [('bad', [review('unknown')])])
    except ValueError as exc:
        assert '未知 ID' in str(exc)
    else:
        raise AssertionError('未拒绝未知 High override')
    print('phase3 finalization tests: PASS')


if __name__ == '__main__':
    main()
