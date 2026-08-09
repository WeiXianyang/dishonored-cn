# -*- coding: utf-8 -*-
import copy

import release_gate as gate


def entry(identifier, english, chinese, layer='int'):
    return {
        'id': identifier, 'layer': layer, 'en': english, 'cn': chinese,
        'status': 'aligned', 'domain': {'release': 'base_game'},
        'context': {
            'file': 'Sample.int', 'section': identifier, 'key': 'm_Text',
            'line': 1,
        } if layer == 'int' else {'references': [{
            'release': 'base_game', 'upk': 'l_sample_audio',
            'dialog_path': 'tree:disconversation_1', 'object': identifier,
            'kind': 'subtitle',
        }]},
    }


def result(identifier, action, new_text='', **extra):
    return {
        'id': identifier, 'action': action, 'new_text': new_text,
        'reason': 'hidden first-pass rationale', 'confidence': 0.99,
        'uncertain': False, 'uncertain_reason': '',
        'route': extra.pop('route', 'medium_decision'), **extra,
    }


def critic(identifier, action='keep', new_text='', uncertain=False,
           uncertain_reason=''):
    return {
        'id': identifier, 'action': action, 'new_text': new_text,
        'reason': 'adversarial verdict', 'confidence': 0.9,
        'uncertain': uncertain, 'uncertain_reason': uncertain_reason,
    }


def fixture():
    corpus = [
        entry('a', 'He never left.', '他从未离开。'),
        entry('b', 'Regent Safe Room', '摄政王的安全屋'),
        entry('c', 'Meet Slackjaw in the Distillery.', '在酿酒厂见大嘴巴。'),
        entry('d', 'Unchanged.', '不变。'),
        entry('e', 'Editor only.', 'Editor only.'),
    ]
    corpus[-1]['context']['file'] = 'DishonoredEditor.int'
    candidates = [
        result('a', 'fix', '他已经离开。'),
        result('b', 'fix', '摄政王的安全屋。', term_reviewed=True),
        result('c', 'fix', '前往酿酒区，与大嘴巴进行一次会面。'),
        result('d', 'keep'),
        result('e', 'fix', '仅供编辑器使用。'),
    ]
    return corpus, candidates


def test_prepare():
    corpus, candidates = fixture()
    reviews, stats = gate.build_review_corpus(corpus, candidates, parts_dir='missing')
    assert [row['id'] for row in reviews] == ['a', 'c']
    by_id = {row['id']: row for row in reviews}
    assert by_id['a']['escalation']['risk']['level'] == 'critical'
    assert 'hidden first-pass rationale' not in str(by_id['a'])
    assert by_id['a']['prior_review'] == {'original_cn': '他从未离开。'}
    assert stats['excluded_existing_independent_review'] == 1
    assert stats['excluded_nonretail_scope'] == 1
    source_priority = by_id['c']['research_context']['source_priority']
    assert '游戏脚本' in source_priority[1]
    assert source_priority[2].endswith('Wiki')


def test_single_write_and_finalize():
    corpus, candidates = fixture()
    reviews, _stats = gate.build_review_corpus(corpus, candidates, parts_dir='missing')
    decisions = [
        critic('a', 'fix', '他从未离开。'),
        critic('c', uncertain=True,
               uncertain_reason='[WIKI_LOOKUP: Distillery] 需确认对象类型。'),
    ]
    final, accepted, unresolved, summary = gate.finalize(
        corpus, candidates, reviews, decisions)
    by_id = {row['id']: row for row in final}
    assert by_id['a']['action'] == 'keep'
    assert by_id['a']['release_gate_decision'] == 'revert'
    assert by_id['b']['release_gate_reviewed'] is True
    assert by_id['c']['uncertain'] is True
    assert by_id['e']['action'] == 'keep'
    assert by_id['e']['release_gate_decision'] == 'revert_out_of_scope'
    assert len(accepted) == 1
    assert unresolved[0]['suggested_wiki_query']
    assert summary['decisions']['reverted_tianmiao'] == 1
    assert summary['decisions']['research_required'] == 1

    invalid = copy.deepcopy(decisions)
    invalid[0] = critic('a', 'fix', '第三版译文')
    try:
        gate.rp.validate_hard_rules([invalid[0]], [reviews[0]], {})
    except ValueError as exc:
        assert '单写入规则' in str(exc)
    else:
        raise AssertionError('批次校验必须立即拒绝第三版译文')
    try:
        gate.finalize(corpus, candidates, reviews, invalid)
    except ValueError as exc:
        assert '单写入规则' in str(exc)
    else:
        raise AssertionError('第三版译文必须被拒绝')


def test_attach_and_verify():
    corpus, candidates = fixture()
    reviews, _stats = gate.build_review_corpus(corpus, candidates, parts_dir='missing')
    enriched, stats = gate.attach_research(reviews, [
        ('wiki', [{'id': 'c', 'status': 'direct_evidence',
                   'finding': 'The Distillery is a building.',
                   'sources': [{
                       'title': 'Distillery',
                       'url': 'https://dishonored.fandom.com/wiki/Distillery',
                       'excerpt': 'The Distillery is a building.',
                   }]}]),
    ])
    c = {row['id']: row for row in enriched}['c']
    assert c['research_context']['external_research'][0]['research_source'] == 'wiki'
    assert stats['researched_ids'] == 1
    try:
        gate.attach_research(reviews, [
            ('bad-wiki', [{'id': 'c', 'status': 'direct_evidence',
                           'finding': '只有搜索标题，无正文证据。', 'sources': []}]),
        ])
    except ValueError as exc:
        assert 'direct_evidence' in str(exc)
    else:
        raise AssertionError('无可定位来源的 direct_evidence 必须被拒绝')

    decisions = [critic('a', 'fix', '他从未离开。'), critic('c', 'keep')]
    final, _accepted, _unresolved, _summary = gate.finalize(
        corpus, candidates, reviews, decisions)
    assert gate.verify_release(corpus, final)['status'] == 'pass'
    broken = copy.deepcopy(final)
    for row in broken:
        if row['id'] == 'c':
            row.pop('release_gate_reviewed')
    checked = gate.verify_release(corpus, broken)
    assert checked['status'] == 'fail'
    assert 'release_gate_reviewed' in checked['errors'][0]

    duplicate_corpus = [
        entry('x', 'Same source.', '同一原译。'),
        entry('y', 'Same source.', '同一原译。'),
    ]
    duplicate_final = [
        result('x', 'fix', '不同译文。', release_gate_reviewed=True),
        result('y', 'keep'),
    ]
    conflicts = gate.consistency_conflicts(duplicate_corpus, duplicate_final)
    assert len(conflicts) == 1
    assert gate.verify_release(
        duplicate_corpus, duplicate_final)['status'] == 'fail'
    exception = [{
        'group_id': conflicts[0]['group_id'],
        'reason': '两个字段受 UI 长度约束不同，已人工核对。',
    }]
    assert gate.verify_release(
        duplicate_corpus, duplicate_final, exception)['status'] == 'pass'


def test_repair_round():
    corpus, candidates = fixture()
    reviews, _stats = gate.build_review_corpus(corpus, candidates, parts_dir='missing')
    initial = [
        critic('a', 'fix', '他从未离开。'),
        critic('c', uncertain=True,
               uncertain_reason='只补回酒厂建筑类型，不改其他措辞。'),
    ]
    repairs = gate.build_repair_corpus(reviews, initial)
    assert [row['id'] for row in repairs] == ['c']
    assert repairs[0]['cn'] == '在酿酒厂见大嘴巴。'
    assert repairs[0]['prior_review']['rejected_candidate_cn'].startswith('前往')
    repair_results = [{
        'id': 'c', 'action': 'fix',
        'new_text': '在酿酒厂与大嘴巴见面。',
        'reason': '只修复见面措辞。', 'confidence': 0.9,
        'uncertain': False, 'uncertain_reason': '',
    }]
    gate.rp.validate_hard_rules(repair_results, repairs, {})
    rereviews, unresolved = gate.build_rereview_corpus(repairs, repair_results)
    assert not unresolved
    assert rereviews[0]['cn'] == '在酿酒厂与大嘴巴见面。'
    rereview_results = [critic('c', 'keep')]
    merged_reviews, merged_results = gate.merge_repair_round(
        reviews, initial, rereviews, rereview_results)
    final, _accepted, unresolved, _summary = gate.finalize(
        corpus, candidates, merged_reviews, merged_results)
    assert not unresolved
    c = {row['id']: row for row in final}['c']
    assert c['action'] == 'fix'
    assert c['new_text'] == '在酿酒厂与大嘴巴见面。'


def test_consistency_review():
    corpus = [
        entry('x', 'Open.', '打开。'),
        entry('y', 'Open.', '开启。'),
    ]
    final = [
        result('x', 'fix', '打开它。', release_gate_reviewed=True),
        result('y', 'keep'),
    ]
    reviews = gate.build_consistency_review_corpus(corpus, final)
    assert len(reviews) == 1
    assert reviews[0]['cn'] == gate.CONSISTENCY_REVERT_SENTINEL
    assert reviews[0]['research_context']['variant_count'] == 2

    allow = [critic(reviews[0]['id'], 'keep')]
    gate.rp.validate_hard_rules(allow, reviews, {})
    retained, exceptions, unresolved, stats = gate.merge_consistency_review(
        corpus, final, reviews, allow)
    assert not unresolved
    assert len(exceptions) == 1
    assert stats['accepted_context_exception'] == 1
    assert gate.verify_release(corpus, retained, exceptions)['status'] == 'pass'

    revert = [critic(
        reviews[0]['id'], 'fix', gate.CONSISTENCY_REVERT_SENTINEL)]
    gate.rp.validate_hard_rules(revert, reviews, {})
    reverted, exceptions, unresolved, stats = gate.merge_consistency_review(
        corpus, final, reviews, revert)
    assert not exceptions and not unresolved
    assert stats['reverted_changed_rows'] == 1
    assert {row['id']: row for row in reverted}['x']['action'] == 'keep'
    assert gate.verify_release(corpus, reverted)['status'] == 'pass'

    illegal = [critic(reviews[0]['id'], 'fix', '统一成新译文')]
    try:
        gate.rp.validate_hard_rules(illegal, reviews, {})
    except ValueError as exc:
        assert 'consistency' in str(exc)
    else:
        raise AssertionError('一致性复核不得写入新译文')


def main():
    test_prepare()
    test_single_write_and_finalize()
    test_attach_and_verify()
    test_repair_round()
    test_consistency_review()
    print('release gate tests: PASS')


if __name__ == '__main__':
    main()
