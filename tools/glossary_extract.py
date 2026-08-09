# -*- coding: utf-8 -*-
"""从 Phase 1 中英语料生成可追溯的术语候选，不修改正式术语表。"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from phase1_extract import json_write, jsonl_write, sha256_file


PROPER_RE = re.compile(
    r"\b(?:The\s+)?[A-Z][A-Za-z'’.-]+"
    r"(?:\s+(?:of|the|and|de|van|von|[A-Z][A-Za-z'’.-]+)){0,5}\b")
LABEL_KEYS = re.compile(
    r'^(?:m_)?(?:Name|ItemName|TargetName|DoorName|LocationName|Title|'
    r'ChapterTitle|PhaseName|PowerName)$', re.I)
CONTRACTION_RE = re.compile(
    r"^(?:I|you|we|they|he|she|it|that|there|what|who|where|how|let|"
    r"don|can|won|wouldn|couldn|shouldn|isn|aren|wasn|weren|hasn|haven)"
    r"['’](?:m|re|ve|ll|d|s|t)$", re.I)
STOP_SINGLE = {
    'a', 'all', 'also', 'an', 'and', 'another', 'any', 'are', 'as', 'at',
    'attention', 'back', 'be', 'because', 'been', 'before', 'but', 'by',
    'cancel', 'can', 'carry', 'chapter', 'close', 'come', 'congratulations',
    'continue', 'could', 'damn', 'dammit', 'dead', 'did', 'do', 'door',
    'even', 'excerpt', 'find', 'for', 'from', 'get', 'go', 'good', 'great',
    'guards', 'have', 'he', 'hello', 'help', 'here', 'hey', 'his', 'hold',
    'how', 'i', 'if', 'in', 'increases', 'is', 'it', 'just', 'keep', 'kill',
    'leave', 'let', 'listen', 'loading', 'locked', 'look', 'make', 'maybe',
    'mission', 'my', 'new', 'no', 'nonlethal', 'not', 'note', 'notes',
    'nothing', 'now', 'of', 'okay', 'on', 'once', 'one', 'only', 'open',
    'optional', 'our', 'perhaps', 'pick', 'please', 'press', 'probably',
    'read', 'reach', 'remember', 'return', 'round', 'save', 'see', 'she',
    'some', 'someone', 'something', 'start', 'stay', 'stop', 'survivor',
    'take', 'talk', 'tell', 'thank', 'that', 'the', 'their', 'then', 'there',
    'these', 'they', 'this', 'those', 'thug', 'to', 'total', 'travel', 'unlock',
    'use', 'very', 'wait', 'warning', 'watch', 'we', 'well', 'what', 'when',
    'where', 'who', 'why', 'will', 'with', 'you', 'your', 'yes', 'yeah',
}
CORE_TERMS = (
    'Corvo', 'Daud', 'Emily', 'Outsider', 'Dunwall', 'Piero', 'Sokolov',
    'Delilah', 'Billie Lurk', 'Pandyssia', 'Granny Rags', 'Slackjaw',
    'City Watch', 'Bottle Street Gang', 'Flooded District', 'Coldridge Prison',
    'Lord Regent', 'High Overseer', 'Bone Charm', 'Whale Oil', 'Blink',
)


def clean_text(text):
    return re.sub(r'<[^>]*>|`[^`]*`|\\[rnt]', ' ', text or '')


def canonical_term(term):
    term = re.sub(r'\s+', ' ', term).strip(' \t\r\n,;:!?()[]{}"')
    term = re.sub(r"(?:'s|’s)$", '', term, flags=re.I)
    if term.lower().startswith('the ') and len(term.split()) > 1:
        term = term[4:]
    return term.strip()


def candidate_ok(term):
    if not (2 <= len(term) <= 72) or '\n' in term:
        return False
    if not re.search(r'[A-Za-z]', term) or CONTRACTION_RE.fullmatch(term):
        return False
    words = term.split()
    if len(words) == 1 and term.casefold() in STOP_SINGLE:
        return False
    if len(words) > 6 or re.search(r'[!?;:]|\.{2,}', term):
        return False
    return True


def label_like(row):
    context = row.get('context', {})
    selector = context.get('subkey') or context.get('key', '')
    return bool(LABEL_KEYS.fullmatch(selector))


def release_of(row):
    domain = row.get('domain', {})
    return domain.get('release') or domain.get('primary_release') or 'unknown'


def row_context(row):
    context = row.get('context', {})
    if row['layer'] == 'int':
        location = f"{context.get('file', '')}:{context.get('section', '')}:{context.get('key', '')}"
    else:
        ref = (context.get('references') or [{}])[0]
        location = f"{ref.get('upk', '')}:{ref.get('dialog_path', '')}:{ref.get('object', '')}"
    return {
        'id': row['id'],
        'layer': row['layer'],
        'release': release_of(row),
        'location': location,
        'en': row['en'],
        'cn': row['cn'],
    }


def stable_id(term):
    return 'term:' + hashlib.sha1(term.casefold().encode('utf-8')).hexdigest()[:16]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--corpus', default='data/aligned/corpus.jsonl')
    ap.add_argument('--terms', default='glossary/terms.json')
    ap.add_argument('--out-dir', default='data/review/glossary')
    ap.add_argument('--max-candidates', type=int, default=1200)
    args = ap.parse_args()
    out_dir = Path(args.out_dir)
    rows = [json.loads(line) for line in open(args.corpus, encoding='utf-8') if line.strip()]
    seed_raw = json.load(open(args.terms, encoding='utf-8'))
    seeds = {key: value for key, value in seed_raw.items() if not key.startswith('_')}

    evidence = defaultdict(lambda: {
        'proper_rows': set(), 'label_rows': set(), 'all_rows': set(),
        'exact_pairs': Counter(), 'pair_rows': defaultdict(set),
        'releases': Counter(), 'layers': Counter(),
    })
    row_by_id = {row['id']: row for row in rows}

    def add(term, row, source, exact_pair=None):
        term = canonical_term(term)
        if not candidate_ok(term):
            return
        key = term.casefold()
        item = evidence[key]
        item['spellings'] = item.get('spellings', Counter())
        item['spellings'][term] += 1
        item['all_rows'].add(row['id'])
        item[f'{source}_rows'].add(row['id'])
        item['releases'][release_of(row)] += 1
        item['layers'][row['layer']] += 1
        if exact_pair:
            item['exact_pairs'][exact_pair] += 1
            item['pair_rows'][exact_pair].add(row['id'])

    for row in rows:
        if not row['en'] or not row['cn'] or row['status'] not in ('aligned', 'aligned_normalized'):
            continue
        english = clean_text(row['en'])
        if label_like(row) and len(english) <= 80 and len(row['cn']) <= 60:
            label = canonical_term(english)
            if candidate_ok(label):
                add(label, row, 'label', exact_pair=row['cn'].strip())
        for match in PROPER_RE.finditer(english):
            add(match.group(), row, 'proper')

    # 旧表种子和核心术语即使低频也必须进入审计。
    required = {canonical_term(term).casefold(): term for term in (*seeds, *CORE_TERMS)}
    for key, term in required.items():
        if key not in evidence:
            evidence[key]['spellings'] = Counter({term: 1})

    candidates = []
    for key, item in evidence.items():
        spelling = item['spellings'].most_common(1)[0][0]
        row_count = len(item['all_rows'])
        label_count = len(item['label_rows'])
        proper_count = len(item['proper_rows'])
        is_required = key in required
        if not is_required and not label_count and proper_count < 3:
            continue
        exact_variants = [
            {'cn': cn, 'count': count}
            for cn, count in item['exact_pairs'].most_common()
        ]
        sorted_ids = sorted(
            item['all_rows'],
            key=lambda rid: (
                0 if rid in item['label_rows'] else 1,
                len(row_by_id[rid]['en']), rid))
        # 每个直接中文变体至少保留一个例证，避免高频译名把低频冲突挤出
        # contexts，导致模型只能看到冲突计数却无法追溯到真实 corpus ID。
        context_ids = []
        for cn, _count in item['exact_pairs'].most_common():
            pair_ids = sorted(item['pair_rows'][cn])
            if pair_ids:
                context_ids.append(pair_ids[0])
        context_ids.extend(rid for rid in sorted_ids if rid not in context_ids)
        context_ids = context_ids[:8]
        score = (
            (10000 if is_required else 0)
            + min(label_count, 20) * 80
            + min(proper_count, 50) * 5
            + min(row_count, 100)
            + (100 if exact_variants else 0)
        )
        seed_key = next((seed for seed in seeds if canonical_term(seed).casefold() == key), None)
        candidates.append({
            'id': stable_id(spelling),
            'en_term': spelling,
            'score': score,
            'required_core_or_seed': is_required,
            'seed_value': seeds.get(seed_key, '') if seed_key else '',
            'row_count': row_count,
            'proper_row_count': proper_count,
            'label_row_count': label_count,
            'releases': dict(sorted(item['releases'].items())),
            'layers': dict(sorted(item['layers'].items())),
            'exact_cn_variants': exact_variants,
            'contexts': [row_context(row_by_id[rid]) for rid in context_ids],
        })

    candidates.sort(key=lambda item: (-item['score'], item['en_term'].casefold()))
    candidates = candidates[:args.max_candidates]
    ids = [item['id'] for item in candidates]
    if len(ids) != len(set(ids)):
        raise SystemExit('候选稳定 ID 碰撞')
    jsonl_write(out_dir / 'candidates.jsonl', candidates)

    exact_conflicts = [
        item for item in candidates if len(item['exact_cn_variants']) > 1
    ]
    summary = {
        'corpus_sha256': sha256_file(args.corpus),
        'seed_terms_sha256': sha256_file(args.terms),
        'corpus_rows': len(rows),
        'candidate_count': len(candidates),
        'required_core_or_seed': sum(item['required_core_or_seed'] for item in candidates),
        'with_exact_cn_evidence': sum(bool(item['exact_cn_variants']) for item in candidates),
        'exact_cn_conflict_candidates': len(exact_conflicts),
        'candidate_layers': dict(Counter(
            layer for item in candidates for layer in item['layers'])),
        'max_candidates': args.max_candidates,
    }
    json_write(out_dir / 'candidate_summary.json', summary)
    json_write(out_dir / 'exact_pair_conflicts.json', exact_conflicts)
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
