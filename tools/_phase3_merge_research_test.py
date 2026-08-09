# -*- coding: utf-8 -*-
import phase3_merge_research as pmr


def row(identifier, status, finding='证据', guidance=None):
    value = {
        'id': identifier, 'status': status, 'finding': finding,
        'sources': [],
    }
    if guidance is not None:
        value['recommended_text_guidance'] = guidance
    return value


def main():
    direct = row('a', 'direct_evidence')
    resolved = row('a', 'resolved', finding='已裁决', guidance='采用甲')
    merged, stats = pmr.merge_research([
        ('auto', [direct, row('b', 'no_match')]),
        ('manual', [resolved, direct]),
    ], known_ids={'a', 'b'}, corpus_order={'b': 0, 'a': 1})
    assert [item['id'] for item in merged] == ['b', 'a', 'a']
    assert [item['status'] for item in merged if item['id'] == 'a'] == [
        'resolved', 'direct_evidence']
    assert stats['exact_duplicates_suppressed'] == 1
    assert merged[1]['research_authority'] == 'adjudicated_conclusion'

    try:
        pmr.merge_research([('bad', [row('unknown', 'no_match')])],
                           known_ids={'a'})
    except ValueError as exc:
        assert '未知 corpus ID' in str(exc)
    else:
        raise AssertionError('未知 ID 应失败')

    try:
        pmr.merge_research([('bad', [
            row('a', 'resolved', guidance='甲'),
            row('a', 'resolved', guidance='乙'),
        ])])
    except ValueError as exc:
        assert '冲突' in str(exc)
    else:
        raise AssertionError('冲突 resolved 应失败')
    print('phase3 research merge tests: PASS')


if __name__ == '__main__':
    main()
