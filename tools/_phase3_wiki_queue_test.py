# -*- coding: utf-8 -*-
import phase3_wiki_queue as pwq


def item(identifier, reason, query):
    return {
        'id': identifier, 'uncertain_reason': reason,
        'suggested_wiki_query': query, 'en': query,
    }


def main():
    rows = [
        item('gaffer-a', '[WIKI_LOOKUP: Gaffer position] 需确认', 'ignored'),
        item('gaffer-b', '[WIKI_LOOKUP:  Gaffer   position ] 需确认', 'ignored'),
        item('crazy', '缺少上下文，无法判断词性', 'Crazy.'),
        item('ricker', 'ricker 是俚语', 'slit your ricker'),
        item('pun', '两种译法都成立', 'Back Home'),
    ]
    routed = pwq.route_items(rows)
    assert len(routed['wiki_fandom']) == 2
    gaffer = next(group for group in routed['wiki_fandom']
                  if group['normalized_query'] == 'gaffer position')
    assert gaffer['ids'] == ['gaffer-a', 'gaffer-b']
    assert [row['id'] for row in routed['local_context']] == ['crazy']
    assert [row['id'] for row in routed['language_high']] == ['pun']
    assert 'dishonored.fandom.com' in gaffer['fandom_search_url']
    print('phase3 wiki queue tests: PASS')


if __name__ == '__main__':
    main()
