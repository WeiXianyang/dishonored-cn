# -*- coding: utf-8 -*-
"""Wiki 疑难术语叠加层的最小回归测试。"""
import json
import tempfile
from pathlib import Path

from glossary_wiki_resolve import merge_resolution, validate_wiki_decisions


def main():
    original_resolved = [{
        'id': 'term:known', 'en_term': 'Known', 'cn_term': '已知',
        'evidence_ids': ['row:known'],
    }]
    original_deferred = [
        {
            'id': 'term:urn', 'en_term': 'Archer Urn', 'cn_term': '射手水壶',
            'category': 'item', 'confidence': 0.7, 'reason': '物件错译',
            'conflict_reason': 'Urn 不是水壶', 'evidence_ids': ['row:urn'],
        },
        {
            'id': 'term:brand', 'en_term': "Heretic's Brand", 'cn_term': '',
            'category': 'world_term', 'confidence': 0.7, 'reason': '双义',
            'conflict_reason': '概念和工具', 'evidence_ids': ['row:brand'],
        },
    ]
    original_rejected = [{
        'id': 'term:noise', 'en_term': 'Noise', 'action': 'reject',
    }]
    original_decisions = [
        {'id': 'term:known', 'en_term': 'Known', 'action': 'lock',
         'cn_term': '已知'},
        {'id': 'term:urn', 'en_term': 'Archer Urn', 'action': 'review',
         'cn_term': '射手水壶'},
        {'id': 'term:brand', 'en_term': "Heretic's Brand", 'action': 'review',
         'cn_term': ''},
        {'id': 'term:noise', 'en_term': 'Noise', 'action': 'reject',
         'cn_term': ''},
    ]
    wiki_decisions = [
        {
            'id': 'term:urn', 'en_term': 'Archer Urn', 'action': 'lock',
            'cn_term': '射手金瓮', 'category': 'item', 'confidence': 0.98,
            'reason': 'Wiki 证实为 urn，天邈同类项使用金瓮。',
            'conflict_reason': '', 'support_cn_terms': ['金瓮'],
            'wiki_urls': ['https://dishonored.fandom.com/wiki/Coin'],
        },
        {
            'id': 'term:brand', 'en_term': "Heretic's Brand",
            'action': 'exclude', 'cn_term': '', 'category': 'world_term',
            'confidence': 1.0, 'reason': 'Wiki 证实概念与工具双义。',
            'conflict_reason': '按语境分流。', 'support_cn_terms': [],
            'wiki_urls': [
                'https://dishonored.fandom.com/wiki/Heretic%27s_Brand'],
        },
    ]
    validate_wiki_decisions(wiki_decisions, original_deferred)
    with tempfile.TemporaryDirectory() as directory:
        corpus = Path(directory) / 'corpus.jsonl'
        corpus.write_text(
            json.dumps({'id': 'row:gold', 'cn': '伊斯蒙金瓮'},
                       ensure_ascii=False) + '\n', encoding='utf-8')
        merged = merge_resolution(
            original_resolved, original_deferred, original_rejected,
            original_decisions, wiki_decisions, corpus)
    assert len(merged['resolved']) == 2
    assert len(merged['deferred']) == 1
    assert len(merged['rejected']) == 1
    assert len(merged['decisions']) == 4
    urn = next(item for item in merged['resolved']
               if item['id'] == 'term:urn')
    assert urn['cn_term'] == '射手金瓮'
    assert urn['evidence_ids'] == ['row:urn', 'row:gold']
    brand = merged['deferred'][0]
    assert brand['wiki_action'] == 'exclude'
    assert merged['phase3_queue'][0]['route'] == 'context_rule'

    incomplete = wiki_decisions[:1]
    try:
        validate_wiki_decisions(incomplete, original_deferred)
    except ValueError:
        pass
    else:
        raise AssertionError('未完整覆盖原始疑难项时必须拒绝')
    print('glossary wiki resolution tests: PASS')


if __name__ == '__main__':
    main()
