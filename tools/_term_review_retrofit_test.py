# -*- coding: utf-8 -*-
import term_review_finalize as trf
import term_review_prepare as trp


def corpus_row(identifier, en, cn, field='m_description'):
    return {
        'id': identifier, 'layer': 'int', 'status': 'aligned',
        'context': {'file': 'T.int', 'section': 'S', 'subkey': field},
        'en': en, 'cn': cn,
    }


def final_row(identifier, action, text='', reason=''):
    return {
        'id': identifier, 'action': action, 'new_text': text,
        'reason': reason, 'confidence': .99, 'uncertain': False,
        'uncertain_reason': '', 'route': 'medium_decision',
        'source_status': 'aligned',
    }


def decision(identifier, action='keep', text=''):
    return {
        'id': identifier, 'action': action, 'new_text': text,
        'reason': '独立复核', 'confidence': .99, 'uncertain': False,
        'uncertain_reason': '',
    }


def main():
    corpus = [
        corpus_row('safe', "Reach the Regent's Safe Room", '到达摄政王的安全屋'),
        corpus_row('ring', 'Place the Wedding Band on the tray', '把婚戒放在托盘上'),
        corpus_row('corvo', 'Speak to Corvo', '和主角交谈'),
        corpus_row('other', 'Open the door', '打开门'),
    ]
    final = [
        final_row('safe', 'fix', '到达摄政王的保险箱室', '按术语表修补'),
        final_row('ring', 'fix', '把婚礼缎带放在托盘上', '按术语表修补'),
        final_row('corvo', 'fix', '和科尔沃交谈', '按术语表修补'),
        final_row('other', 'fix', '把门打开', '顺句'),
    ]
    policies = [
        {'id': 't-safe', 'en_term': "Regent's Safe",
         'previous_cn': '摄政王的保险箱', 'decision': 'restrict_scope',
         'cn_term': '摄政王的保险箱', 'scope': 'label_only',
         'confidence': .99, 'reason': '仅保险箱标签',
         'evidence_ids': [], 'risk_tags': ['substring_collision']},
        {'id': 't-ring', 'en_term': 'Wedding Band',
         'previous_cn': '婚礼缎带', 'decision': 'correct_global',
         'cn_term': '婚戒', 'scope': 'global', 'confidence': .99,
         'reason': 'band 在此是戒指', 'evidence_ids': [],
         'risk_tags': ['mistranslation']},
        {'id': 't-corvo', 'en_term': 'Corvo', 'previous_cn': '科尔沃',
         'decision': 'keep_global', 'cn_term': '科尔沃', 'scope': 'global',
         'confidence': 1.0, 'reason': '人物名', 'evidence_ids': [],
         'risk_tags': []},
    ]
    selected, stats = trp.build_review_corpus(corpus, final, policies)
    assert {row['id'] for row in selected} == {'safe', 'ring', 'corvo'}
    assert stats['selected_entries'] == 3
    safe = next(row for row in selected if row['id'] == 'safe')
    assert safe['cn'] == '到达摄政王的保险箱室'
    assert safe['term_review']['candidates'][0]['decision'] == 'restrict_scope'

    results = [
        decision('safe', 'fix', '到达摄政王的安全屋'),
        decision('ring', 'fix', '把婚戒放在托盘上'),
        decision('corvo'),
    ]
    hard = {'Wedding Band': '婚戒', 'Corvo': '科尔沃'}
    out, accepted, human, summary = trf.apply_review(
        corpus, final, selected, results, hard)
    by_id = {row['id']: row for row in out}
    assert by_id['safe']['action'] == 'keep'
    assert by_id['safe']['new_text'] == ''
    assert by_id['ring']['action'] == 'keep'
    assert by_id['ring']['new_text'] == ''
    assert by_id['corvo']['new_text'] == '和科尔沃交谈'
    assert all(by_id[x]['term_reviewed'] for x in ('safe', 'ring', 'corvo'))
    assert not human
    assert len(accepted) == 2
    assert summary['reviewed_entries'] == 3
    merged, override_count = trf.merge_overrides(results, [(
        'fixture override', [decision('safe', 'fix', '到达摄政王的安全室')])])
    assert override_count == 1
    assert next(x for x in merged if x['id'] == 'safe')['new_text'].endswith('安全室')
    print('term review retrofit tests: PASS')


if __name__ == '__main__':
    main()
