# -*- coding: utf-8 -*-
import glossary_audit_finalize as gaf


def main():
    terms = {
        "Regent's Safe": '摄政王的保险箱',
        'Anton Sokolov': '安东·索科洛夫',
        'Arc Mine Extra Charge': '电弧地雷过充',
        'Assassin': '刺客',
    }
    entries = [
        {'id': 'safe', 'en_term': "Regent's Safe",
         'current_cn': '摄政王的保险箱'},
        {'id': 'anton', 'en_term': 'Anton Sokolov',
         'current_cn': '安东·索科洛夫'},
        {'id': 'arc', 'en_term': 'Arc Mine Extra Charge',
         'current_cn': '电弧地雷过充'},
        {'id': 'assassin', 'en_term': 'Assassin', 'current_cn': '刺客'},
    ]
    decisions = [
        {'id': 'safe', 'decision': 'restrict_scope',
         'proposed_cn': '摄政王的保险箱', 'scope': 'label_only',
         'confidence': .99, 'reason': '仅独立标签', 'evidence_ids': ['x'],
         'risk_tags': ['substring_collision']},
        {'id': 'anton', 'decision': 'keep_global',
         'proposed_cn': '安东·索科洛夫', 'scope': 'global',
         'confidence': .99, 'reason': '人物专名', 'evidence_ids': ['y'],
         'risk_tags': []},
        {'id': 'arc', 'decision': 'restrict_scope',
         'proposed_cn': '电弧地雷额外充能', 'scope': 'label_only',
         'confidence': .98, 'reason': '标签纠错', 'evidence_ids': ['z'],
         'risk_tags': ['mistranslation']},
        {'id': 'assassin', 'decision': 'remove', 'proposed_cn': '',
         'scope': 'none', 'confidence': .99, 'reason': '普通词多义',
         'evidence_ids': ['q'], 'risk_tags': ['generic_phrase']},
    ]
    hard, advisory, policies, summary = gaf.build_outputs(
        terms, entries, decisions, {'audit': 'abc'})
    assert hard['Anton Sokolov'] == '安东·索科洛夫'
    assert hard['_term_count'] == 1
    assert "Regent's Safe" not in hard
    assert [x['en_term'] for x in advisory['items']] == [
        'Arc Mine Extra Charge', "Regent's Safe"]
    assert advisory['items'][0]['cn_term'] == '电弧地雷额外充能'
    assert len(policies['items']) == 4
    assert summary['decisions'] == {
        'keep_global': 1, 'remove': 1, 'restrict_scope': 2}
    print('glossary audit finalization tests: PASS')


if __name__ == '__main__':
    main()
