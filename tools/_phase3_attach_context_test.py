# -*- coding: utf-8 -*-
import phase3_attach_context as pac


def int_row(identifier, line):
    return {
        'id': identifier, 'layer': 'int',
        'context': {'file': 'A.int', 'section': 'S', 'key': identifier,
                    'line': line},
        'en': identifier + ' en', 'cn': identifier + ' cn',
        'tags': [], 'status': 'aligned',
    }


def upk_row(identifier, dialog):
    return {
        'id': 'upk:' + identifier, 'layer': 'upk',
        'context': {'references': [{
            'upk': 'pkg', 'dialog_path': dialog, 'object': identifier,
        }]},
        'en': identifier + ' en', 'cn': identifier + ' cn',
        'tags': [], 'status': 'aligned',
    }


def main():
    corpus = [
        int_row('i3', 3), int_row('i1', 1), int_row('i2', 2),
        upk_row('C', 'dlg'), upk_row('A', 'dlg'), upk_row('B', 'dlg'),
        upk_row('X', 'other'),
    ]
    orders = {'pkg': {'A': 0, 'B': 1, 'C': 2, 'X': 3}}
    neighbors = pac.build_neighbor_index(corpus, orders, radius=1)
    assert [item['id'] for item in neighbors['i2']] == ['i1', 'i3']
    assert [item['id'] for item in neighbors['upk:B']] == ['upk:A', 'upk:C']
    assert neighbors['upk:X'] == []

    escalation = [dict(corpus[2], prior_review={}, escalation={})]
    enriched, stats = pac.attach_context(
        escalation, corpus,
        wiki_rows=[{'id': 'i2', 'status': 'resolved', 'finding': '事实'}],
        parts_dir='does-not-exist', radius=1)
    assert enriched[0]['research_context']['wiki_research'][0]['finding'] == '事实'
    assert stats == {'with_neighbors': 1, 'with_wiki_research': 1}
    print('phase3 context attachment tests: PASS')


if __name__ == '__main__':
    main()
