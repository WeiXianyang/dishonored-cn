# -*- coding: utf-8 -*-
import glossary_audit as ga


def main():
    terms = {"Regent's Safe": '摄政王的保险箱'}
    evidence = [{
        'id': 'term:safe', 'en_term': "Regent's Safe",
        'cn_term': '摄政王的保险箱', 'category': 'item',
        'confidence': 0.96, 'reason': '目标名', 'evidence_ids': ['label'],
        'wiki_urls': [],
    }]
    corpus = [{
        'id': 'label', 'layer': 'int',
        'context': {'key': 'm_TargetName'},
        'domain': {'release': 'base_game'},
        'en': "Regent's Safe", 'cn': '摄政王的保险箱',
    }, {
        'id': 'room', 'layer': 'upk',
        'context': {'references': [{'release': 'base_game'}]},
        'en': "Reach the Lord Regent's safe room",
        'cn': '到达摄政王的安全屋',
    }]
    final = [
        {'id': 'label', 'action': 'keep', 'new_text': ''},
        {'id': 'room', 'action': 'fix', 'new_text': '到达摄政王的保险箱室'},
    ]
    entries = ga.build_audit_entries(terms, evidence, corpus, final)
    assert len(entries) == 1
    entry = entries[0]
    assert entry['stats']['occurrences'] == 2
    assert entry['stats']['case_drift'] == 1
    assert 'case_drift' in entry['static_risks']
    assert {row['id'] for row in entry['contexts']} == {'label', 'room'}
    decision = [{
        'id': 'term:safe', 'decision': 'restrict_scope',
        'proposed_cn': '摄政王的保险箱', 'scope': 'label_only',
        'confidence': 0.99, 'reason': '仅独立目标名为保险箱',
        'evidence_ids': ['label', 'room'],
        'risk_tags': ['substring_collision', 'case_drift'],
    }]
    assert ga.validate_items(decision, entries)[0]['scope'] == 'label_only'
    print('glossary audit tests: PASS')


if __name__ == '__main__':
    main()
