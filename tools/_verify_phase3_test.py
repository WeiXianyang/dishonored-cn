# -*- coding: utf-8 -*-
import verify_phase3 as vp


def main():
    corpus = [
        {
            'id': 'upk:281290178F077DFEF82116B3B2F373B3', 'layer': 'upk',
            'context': {}, 'en': "We're counting on you.",
            'cn': '我们取决于你。', 'tags': [], 'status': 'aligned',
        },
        {
            'id': 'upk:9EF2CA8AAC46376916E50EE7AC2E73BB', 'layer': 'upk',
            'context': {}, 'en': "I'm trapped!", 'cn': '我中陷阱了！',
            'tags': [], 'status': 'aligned',
        },
        {
            'id': 'auto', 'layer': 'int', 'context': {}, 'en': '', 'cn': '',
            'tags': [], 'status': 'aligned',
        },
        {
            'id': 'cn', 'layer': 'int', 'context': {}, 'en': '', 'cn': '中文',
            'tags': [], 'status': 'cn_only',
        },
        {
            'id': 'cn-empty', 'layer': 'int', 'context': {}, 'en': '', 'cn': '',
            'tags': [], 'status': 'cn_only',
        },
        {
            'id': 'term-reviewed', 'layer': 'upk', 'context': {},
            'en': "The Assassin's Blade is sharp.", 'cn': '这把刀很锋利。',
            'tags': [], 'status': 'aligned',
        },
    ]
    final = [
        {'id': corpus[0]['id'], 'action': 'fix', 'new_text': '我们都指望你了。',
         'uncertain': False, 'route': 'high_decision'},
        {'id': corpus[1]['id'], 'action': 'fix', 'new_text': '我被困住了！',
         'uncertain': False, 'route': 'high_decision'},
        {'id': 'auto', 'action': 'keep', 'new_text': '', 'uncertain': False,
         'route': 'automatic_empty_keep'},
        {'id': 'cn', 'action': 'keep', 'new_text': '', 'uncertain': True,
         'route': 'human_unpaired_cn_only'},
        {'id': 'cn-empty', 'action': 'keep', 'new_text': '', 'uncertain': False,
         'route': 'automatic_empty_keep'},
        {'id': 'term-reviewed', 'action': 'fix',
         'new_text': '这把刺客之刃很锋利。', 'uncertain': False,
         'route': 'high_decision', 'term_reviewed': True,
         'term_scope_overrides': []},
    ]
    accepted = [
        {**final[0], 'old_text': corpus[0]['cn']},
        {**final[1], 'old_text': corpus[1]['cn']},
        {**final[5], 'old_text': corpus[5]['cn']},
    ]
    human = [{'id': 'cn'}]
    research = [{
        'id': corpus[0]['id'], 'status': 'resolved',
        'recommended_action': 'fix',
    }, {
        'id': 'auto', 'status': 'resolved', 'recommended_action': 'keep',
    }]
    terms = {"Assassin's Blade": '刺客之刃'}
    report = vp.verify(
        corpus, final, accepted, human, terms, research_rows=research)
    assert report['status'] == 'pass', report
    assert report['counts']['final_fix'] == 3
    assert report['counts']['resolved_research_checked'] == 2

    resolved_final = [dict(row) for row in final]
    resolved_final[3].update({
        'uncertain': False, 'route': 'phase4_wiki_keep_cn_only',
    })
    report = vp.verify(
        corpus, resolved_final, accepted, [], terms, research_rows=research)
    assert report['status'] == 'pass', report
    assert report['counts']['human_review'] == 0

    bad = [dict(row) for row in final]
    bad[1]['new_text'] = '我中陷阱了！'
    bad_accepted = [dict(row) for row in accepted]
    bad_accepted[1]['new_text'] = '我中陷阱了！'
    report = vp.verify(
        corpus, bad, bad_accepted, human, terms, research_rows=research)
    assert report['status'] == 'fail'
    assert any('P0' in error for error in report['errors'])

    unreviewed = [dict(row) for row in final]
    unreviewed[5].pop('term_reviewed')
    report = vp.verify(
        corpus, unreviewed, accepted, human, terms, research_rows=research)
    assert report['status'] == 'fail'
    assert any('Agent 二次复核' in error for error in report['errors'])
    print('phase3 verification tests: PASS')


if __name__ == '__main__':
    main()
