# -*- coding: utf-8 -*-
"""将 Medium uncertain 队列去重并分流为 Fandom、本地上下文和语言 High。"""
import argparse
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import quote_plus

import review_pipeline as rp


WIKI_MARKER = re.compile(r'\[WIKI_LOOKUP:\s*(.*?)\]\s*', re.I | re.S)
LOCAL_HINTS = (
    '上下文', '语境', '说话对象', '指代', '词性', '孤立', '物件外观',
    '前后对白', '无法判断是', '缺少对象',
)
WIKI_HINTS = (
    '世界观', '正式译名', '既有中文译名', '疾病', '职位', '派系', '地名',
    '人名', '物件', '能力', '俚语', 'ricker', 'gaffer', 'thick lung',
)
WIKI_STRONG_HINTS = (
    '世界观', '正式译名', '既有中文译名', '疾病', '职位', '俚语',
    'ricker', 'gaffer', 'thick lung',
)


def load_queue(path):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if isinstance(data, dict) and isinstance(data.get('items'), list):
        return data['items'], data
    if isinstance(data, list):
        return data, {}
    raise ValueError('wiki lookup queue 格式错误')


def normalized_query(value):
    return ' '.join(str(value or '').split()).casefold()


def extract_query(item):
    reason = item.get('uncertain_reason', '')
    marker = WIKI_MARKER.search(reason)
    if marker:
        return ' '.join(marker.group(1).split()), True
    return ' '.join(str(item.get('suggested_wiki_query') or
                        item.get('en', '')).split()), False


def classify(item):
    reason = str(item.get('uncertain_reason', ''))
    query, explicit = extract_query(item)
    combined = (reason + ' ' + query).casefold()
    if explicit:
        return 'wiki_fandom', query
    if any(hint.casefold() in combined for hint in WIKI_STRONG_HINTS):
        return 'wiki_fandom', query
    if any(hint.casefold() in combined for hint in LOCAL_HINTS):
        return 'local_context', query
    if any(hint.casefold() in combined for hint in WIKI_HINTS):
        return 'wiki_fandom', query
    return 'language_high', query


def route_items(items):
    routed = {'wiki_fandom': [], 'local_context': [], 'language_high': []}
    wiki_groups = {}
    for item in items:
        route, query = classify(item)
        enriched = dict(item)
        enriched['research_route'] = route
        enriched['normalized_query'] = normalized_query(query)
        if route == 'wiki_fandom':
            key = enriched['normalized_query']
            group = wiki_groups.setdefault(key, {
                'query': query, 'normalized_query': key, 'ids': [],
                'reasons': [], 'status': 'pending',
                'lookup_order': [
                    'Dishonored Fandom 站内页面/搜索',
                    '本地英文语料与对话上下文',
                    '其他高信一手来源（Fandom 无结果时）',
                ],
                'fandom_search_url': (
                    'https://dishonored.fandom.com/wiki/Special:Search?query='
                    + quote_plus(query)),
            })
            group['ids'].append(item['id'])
            group['reasons'].append(item.get('uncertain_reason', ''))
        else:
            routed[route].append(enriched)
    routed['wiki_fandom'] = list(wiki_groups.values())
    return routed


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--queue', required=True)
    parser.add_argument('--out-dir', required=True)
    args = parser.parse_args(argv)
    items, source_meta = load_queue(args.queue)
    routed = route_items(items)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        'wiki_fandom': out_dir / 'wiki_fandom_queries.jsonl',
        'local_context': out_dir / 'local_context_queue.jsonl',
        'language_high': out_dir / 'language_high_queue.jsonl',
    }
    for route, path in paths.items():
        rp.atomic_write_jsonl(str(path), routed[route])
    manifest = {
        'created_at': rp.now_utc(), 'source_count': len(items),
        'routed_item_counts': {
            'wiki_fandom_unique_queries': len(routed['wiki_fandom']),
            'wiki_fandom_ids': sum(len(group['ids'])
                                   for group in routed['wiki_fandom']),
            'local_context': len(routed['local_context']),
            'language_high': len(routed['language_high']),
        },
        'source_site': source_meta.get('lookup_site'),
        'hashes': {
            'source_queue': rp.sha256_file(args.queue),
            **{route: rp.sha256_file(str(path)) for route, path in paths.items()},
        },
    }
    rp.atomic_write_json(str(out_dir / 'manifest.json'), manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
