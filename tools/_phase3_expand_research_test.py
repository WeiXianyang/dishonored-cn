# -*- coding: utf-8 -*-
import phase3_expand_research as per


def main():
    corpus = [
        {'id': 'a', 'en': 'To Midrow Substation'},
        {'id': 'b', 'en': 'MIDROW SUBSTATION'},
        {'id': 'c', 'en': 'Butterfly Case'},
    ]
    rules = [{
        'rule_id': 'midrow', 'en_contains': 'Midrow Substation',
        'expected_count': 2, 'status': 'resolved', 'finding': '中街变电站',
    }, {
        'rule_id': 'case', 'en_exact': 'Butterfly Case',
        'expected_count': 1, 'status': 'resolved', 'finding': '蝴蝶笼',
    }]
    rows, counts = per.expand_rules(corpus, rules)
    assert [row['id'] for row in rows] == ['a', 'b', 'c']
    assert counts == {'midrow': 2, 'case': 1}
    assert rows[0]['matched_rule'] == 'midrow'

    bad = [dict(rules[0], expected_count=3)]
    try:
        per.expand_rules(corpus, bad)
    except ValueError as exc:
        assert '预期命中' in str(exc)
    else:
        raise AssertionError('命中数量漂移应失败')

    overlapping = rules + [{
        'rule_id': 'station', 'en_regex': 'Substation',
        'expected_count': 2, 'status': 'resolved', 'finding': '冲突',
    }]
    try:
        per.expand_rules(corpus, overlapping)
    except ValueError as exc:
        assert '规则重叠' in str(exc)
    else:
        raise AssertionError('规则重叠应失败')
    print('phase3 research expansion tests: PASS')


if __name__ == '__main__':
    main()
