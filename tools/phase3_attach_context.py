# -*- coding: utf-8 -*-
"""为 Phase 3 High 复审条目附加可追溯的本地上下文与 Wiki 结论。"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

import review_pipeline as rp


def read_jsonl(path):
    with open(path, encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def clip(text, limit=500):
    text = text or ''
    return text if len(text) <= limit else text[:limit] + '…'


def primary_upk_context(entry):
    references = entry.get('context', {}).get('references', [])
    reference = references[0] if references else {}
    return (
        str(reference.get('upk', '')).casefold(),
        str(reference.get('dialog_path', '')).casefold(),
    )


def load_upk_orders(parts_dir):
    orders = {}
    parts_dir = Path(parts_dir)
    if not parts_dir.exists():
        return orders
    for path in parts_dir.glob('*.json'):
        try:
            data = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            continue
        upk = str(data.get('upk', path.stem)).casefold()
        values = data.get('values', {})
        if isinstance(values, dict):
            orders[upk] = {
                str(value_hash).upper(): index
                for index, value_hash in enumerate(values)
            }
    return orders


def neighbor_record(entry, relation):
    context = entry.get('context', {})
    if entry.get('layer') == 'int':
        location = ':'.join(str(context.get(key, '')) for key in (
            'file', 'section', 'key', 'subkey'))
    else:
        refs = context.get('references', [])
        ref = refs[0] if refs else {}
        location = '/'.join(str(ref.get(key, '')) for key in (
            'upk', 'dialog_path', 'object'))
    return {
        'relation': relation, 'id': entry['id'], 'location': location,
        'en': clip(entry.get('en', '')), 'cn': clip(entry.get('cn', '')),
    }


def build_neighbor_index(corpus, upk_orders, radius=2):
    position = {entry['id']: index for index, entry in enumerate(corpus)}
    groups = defaultdict(list)
    for entry in corpus:
        if entry.get('layer') == 'int':
            ctx = entry.get('context', {})
            key = ('int', str(ctx.get('file', '')).casefold(),
                   str(ctx.get('section', '')).casefold())
        else:
            upk, dialog_path = primary_upk_context(entry)
            key = ('upk', upk, dialog_path)
        groups[key].append(entry)

    neighbors = {}
    for key, entries in groups.items():
        if key[0] == 'int':
            entries.sort(key=lambda entry: (
                int(entry.get('context', {}).get('line', 10 ** 12)),
                position[entry['id']]))
        else:
            order = upk_orders.get(key[1], {})
            entries.sort(key=lambda entry: (
                order.get(entry['id'][4:].upper(), 10 ** 12),
                position[entry['id']]))
        for index, entry in enumerate(entries):
            local = []
            start = max(0, index - radius)
            end = min(len(entries), index + radius + 1)
            for peer_index in range(start, end):
                if peer_index == index:
                    continue
                relation = ('before' if peer_index < index else 'after')
                local.append(neighbor_record(entries[peer_index], relation))
            neighbors[entry['id']] = local
    return neighbors


def attach_context(escalation, corpus, wiki_rows=None, parts_dir='data/raw/upk_parts',
                   radius=2):
    corpus_ids = {entry['id'] for entry in corpus}
    unknown = sorted(entry['id'] for entry in escalation
                     if entry['id'] not in corpus_ids)
    if unknown:
        raise ValueError(f'escalation 含未知 corpus ID: {unknown[:5]}')
    wiki_by_id = {}
    for row in wiki_rows or []:
        identifier = row.get('id')
        if identifier:
            wiki_by_id.setdefault(identifier, []).append(row)
    neighbors = build_neighbor_index(
        corpus, load_upk_orders(parts_dir), radius=radius)
    output = []
    stats = {'with_neighbors': 0, 'with_wiki_research': 0}
    for entry in escalation:
        enriched = dict(entry)
        local = neighbors.get(entry['id'], [])
        wiki = wiki_by_id.get(entry['id'], [])
        enriched['research_context'] = {
            'local_neighbors': local,
            'wiki_research': wiki,
        }
        stats['with_neighbors'] += bool(local)
        stats['with_wiki_research'] += bool(wiki)
        output.append(enriched)
    return output, stats


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--escalation', required=True)
    parser.add_argument('--corpus', default='data/aligned/corpus.jsonl')
    parser.add_argument('--wiki-research')
    parser.add_argument('--parts-dir', default='data/raw/upk_parts')
    parser.add_argument('--radius', type=int, default=2)
    parser.add_argument('--out', required=True)
    parser.add_argument('--manifest')
    args = parser.parse_args(argv)
    if args.radius < 0 or args.radius > 5:
        parser.error('--radius 必须在 0..5')

    escalation = read_jsonl(args.escalation)
    corpus = read_jsonl(args.corpus)
    wiki = read_jsonl(args.wiki_research) if args.wiki_research else []
    output, stats = attach_context(
        escalation, corpus, wiki, args.parts_dir, args.radius)
    rp.atomic_write_jsonl(args.out, output)
    manifest_path = args.manifest or args.out + '.manifest.json'
    manifest = {
        'created_at': rp.now_utc(), 'entry_count': len(output), **stats,
        'radius': args.radius,
        'hashes': {
            'escalation': rp.sha256_file(args.escalation),
            'corpus': rp.sha256_file(args.corpus),
            'wiki_research': (rp.sha256_file(args.wiki_research)
                              if args.wiki_research else None),
            'output': rp.sha256_file(args.out),
        },
    }
    rp.atomic_write_json(manifest_path, manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
