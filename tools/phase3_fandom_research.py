# -*- coding: utf-8 -*-
"""批量查询 Dishonored Fandom，为 Phase 3 High 复核提供可追溯证据。

输入是 ``phase3_wiki_queue.py`` 生成的 ``wiki_fandom_queries.jsonl``。
程序同时查询英文与中文社区 Wiki，并把查询响应逐项缓存。搜索命中只作为
证据，不会被当作自动结论；最终译文仍由 High 复核结合英文、本地语料与
天邈底色裁决。
"""
import argparse
import hashlib
import html
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

import review_pipeline as rp


SITES = (
    ('en', 'https://dishonored.fandom.com/api.php',
     'https://dishonored.fandom.com/wiki/'),
    ('zh', 'https://dishonored.fandom.com/zh/api.php',
     'https://dishonored.fandom.com/zh/wiki/'),
)

STOPWORDS = {
    'about', 'after', 'again', 'also', 'been', 'before', 'between', 'could',
    'dishonored', 'down', 'from', 'have', 'into', 'itll', 'need', 'none',
    'official', 'other', 'should', 'since', 'street', 'their', 'there',
    'these', 'things', 'this', 'those', 'through', 'translation', 'when',
    'where', 'which', 'while', 'with', 'would', 'youll', 'your',
}


def read_jsonl(path):
    with open(path, encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def clean_text(value):
    value = html.unescape(re.sub(r'<[^>]+>', ' ', value or ''))
    return re.sub(r'\s+', ' ', value).strip()


def append_unique(values, value, max_length=160):
    value = re.sub(r'\s+', ' ', (value or '')).strip(' \t\r\n.,;:!?"“”')
    if not value or len(value) > max_length:
        return
    folded = value.casefold()
    if folded not in {item.casefold() for item in values}:
        values.append(value)


def query_variants(query, limit=6):
    """从模型给出的自然语言问题中提取适合 Wiki 搜索的短查询。"""
    query = re.sub(r'\s+', ' ', query or '').strip()
    variants = []
    append_unique(variants, query)

    # 中英混排的问题通常把真正的实体名放在一个连续拉丁字段中。
    for run in re.findall(r"[A-Za-z][A-Za-z0-9'’ -]{1,80}", query):
        words = re.findall(r"[A-Za-z][A-Za-z0-9'’]*", run)
        if 1 <= len(words) <= 8:
            append_unique(variants, ' '.join(words))

    # 标题式专名（Midrow Substation / Butterfly Case / Gaffer）。
    title_pattern = r"\b[A-Z][A-Za-z'’]*(?:\s+[A-Z][A-Za-z'’]*){0,4}"
    for match in re.findall(title_pattern, query):
        stopword_key = match.replace('’', "'").replace("'", '').casefold()
        if stopword_key in STOPWORDS:
            continue
        append_unique(variants, match)

    # 长台词没有显式标记时，用少数罕见词兜底，例如 ricker。
    tokens = re.findall(r"[A-Za-z][A-Za-z'’]{3,}", query)
    rare = []
    for token in tokens:
        normalized = token.replace('’', "'")
        stopword_key = normalized.replace("'", '').casefold()
        if stopword_key in STOPWORDS:
            continue
        if normalized.casefold() not in {item.casefold() for item in rare}:
            rare.append(normalized)
    rare.sort(key=lambda value: (-len(value), tokens.index(
        next(token for token in tokens
             if token.replace('’', "'").casefold() == value.casefold()))))
    added = 0
    for token in rare:
        before = len(variants)
        append_unique(variants, token)
        if len(variants) > before:
            added += 1
        if added == 3:
            break

    return variants[:limit]


def subject_query(group):
    """提取真正待核查的词，而不是整段台词或解释。"""
    for reason in group.get('reasons', []):
        marker = re.search(r'\[WIKI_LOOKUP:\s*(.*?)\]', reason, re.I | re.S)
        if marker:
            return re.sub(r'\s+', ' ', marker.group(1)).strip()
    for reason in group.get('reasons', []):
        leading = re.match(r"\s*([A-Za-z][A-Za-z0-9'’ -]{1,60})", reason)
        if leading:
            return leading.group(1).strip()
    return group.get('query', '')


def direct_variant(subject):
    """返回用于判断“直接命中”的核心英文实体短语。"""
    runs = re.findall(r"[A-Za-z][A-Za-z0-9'’ -]{1,80}", subject or '')
    for run in runs:
        words = re.findall(r"[A-Za-z][A-Za-z0-9'’]*", run)
        if not 1 <= len(words) <= 8:
            continue
        candidate = ' '.join(words).strip()
        if candidate.casefold() != 'dishonored':
            return candidate
    stripped = re.sub(r'\s+', ' ', subject or '').strip()
    return stripped if stripped and len(stripped) <= 80 else ''


def page_url(prefix, title):
    encoded = urllib.parse.quote(title.replace(' ', '_'), safe='()/,:')
    return prefix + encoded


def api_search(api_url, query, result_limit=5, timeout=25):
    params = urllib.parse.urlencode({
        'action': 'query', 'list': 'search', 'srsearch': query,
        'srnamespace': 0, 'srlimit': result_limit,
        'format': 'json', 'formatversion': 2,
    })
    request = urllib.request.Request(
        api_url + '?' + params,
        headers={'User-Agent': 'Dishonored-Tianmiao-Repair/Phase3'},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode('utf-8'))
    return payload.get('query', {}).get('search', [])


def api_page_content(api_url, pageid, timeout=25):
    params = urllib.parse.urlencode({
        'action': 'query', 'prop': 'revisions', 'pageids': pageid,
        'rvprop': 'content', 'rvslots': 'main',
        'format': 'json', 'formatversion': 2,
    })
    request = urllib.request.Request(
        api_url + '?' + params,
        headers={'User-Agent': 'Dishonored-Tianmiao-Repair/Phase3'},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode('utf-8'))
    pages = payload.get('query', {}).get('pages', [])
    if not pages:
        return ''
    revisions = pages[0].get('revisions', [])
    if not revisions:
        return ''
    return revisions[0].get('slots', {}).get('main', {}).get('content', '')


def cache_key(language, query):
    raw = json.dumps([language, query], ensure_ascii=False,
                     separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def page_cache_key(language, pageid):
    raw = json.dumps(['page', language, pageid], ensure_ascii=False,
                     separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def cached_search(language, api_url, query, cache_dir, requester=api_search,
                  result_limit=5, timeout=25, retries=3, sleep_fn=time.sleep):
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f'{cache_key(language, query)}.json'
    if path.exists():
        try:
            cached = json.loads(path.read_text(encoding='utf-8'))
            if (cached.get('language') == language and
                    cached.get('query') == query and
                    isinstance(cached.get('matches'), list)):
                return cached['matches'], cached.get('error'), True
        except (OSError, json.JSONDecodeError):
            rp.archive_stale(str(path))

    errors = []
    matches = []
    for attempt in range(retries):
        try:
            matches = requester(api_url, query, result_limit, timeout)
            errors = []
            break
        except (OSError, ValueError, urllib.error.URLError) as exc:
            errors.append(str(exc))
            if attempt + 1 < retries:
                sleep_fn(1 * (2 ** attempt))
    error = ' | '.join(errors[-3:]) if errors else None
    rp.atomic_write_json(str(path), {
        'language': language, 'query': query,
        'fetched_at': rp.now_utc(), 'matches': matches, 'error': error,
    })
    return matches, error, False


def cached_page_content(language, api_url, pageid, cache_dir,
                        requester=api_page_content, timeout=25, retries=3,
                        sleep_fn=time.sleep):
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f'{page_cache_key(language, pageid)}.json'
    if path.exists():
        try:
            cached = json.loads(path.read_text(encoding='utf-8'))
            if (cached.get('language') == language and
                    cached.get('pageid') == pageid and
                    isinstance(cached.get('content'), str)):
                return cached['content'], cached.get('error'), True
        except (OSError, json.JSONDecodeError):
            rp.archive_stale(str(path))

    errors = []
    content = ''
    for attempt in range(retries):
        try:
            content = requester(api_url, pageid, timeout)
            errors = []
            break
        except (OSError, ValueError, urllib.error.URLError) as exc:
            errors.append(str(exc))
            if attempt + 1 < retries:
                sleep_fn(1 * (2 ** attempt))
    error = ' | '.join(errors[-3:]) if errors else None
    rp.atomic_write_json(str(path), {
        'language': language, 'pageid': pageid,
        'fetched_at': rp.now_utc(), 'content': content, 'error': error,
    })
    return content, error, False


def plain_wikitext(value):
    value = re.sub(r'<!--.*?-->', ' ', value or '', flags=re.S)
    value = re.sub(r'<ref\b.*?</ref>|<ref\b[^>]*/>', ' ', value,
                   flags=re.I | re.S)
    value = re.sub(r'\{\{.*?\}\}', ' ', value, flags=re.S)
    value = re.sub(r'\[\[[^\]|]+\|([^\]]+)\]\]', r'\1', value)
    value = re.sub(r'\[\[([^\]]+)\]\]', r'\1', value)
    value = re.sub(r"'{2,5}", '', value)
    value = re.sub(r'={2,}\s*(.*?)\s*={2,}', r' \1 ', value)
    return clean_text(value)


def evidence_excerpt(content, needles, radius=260):
    """截取命中词附近正文；无命中时回退到页面开头。"""
    folded = (content or '').casefold()
    for needle in needles:
        needle = (needle or '').strip()
        if not needle:
            continue
        index = folded.find(needle.casefold())
        if index >= 0:
            start = max(0, index - radius)
            end = min(len(content), index + len(needle) + radius)
            return plain_wikitext(content[start:end])[:600]
    return plain_wikitext(content)[:600]


def research_group(group, cache_dir, requester=api_search,
                   page_requester=api_page_content, result_limit=5,
                   timeout=25, throttle=0.15, sleep_fn=time.sleep):
    subject = subject_query(group)
    core_variant = direct_variant(subject)
    variants = []
    append_unique(variants, core_variant)
    if core_variant:
        insource_variant = f'insource:"{core_variant}"'
        if insource_variant.casefold() not in {
                value.casefold() for value in variants}:
            variants.append(insource_variant)
    for candidate in (
            query_variants(subject) + query_variants(group.get('query', ''))):
        append_unique(variants, candidate)
    variants = variants[:8]
    attempted = []
    errors = []
    matches = []
    seen_pages = set()
    cache_hits = 0
    network_calls = 0
    page_cache_hits = 0
    page_network_calls = 0

    for variant in variants:
        for language, api_url, url_prefix in SITES:
            found, error, cached = cached_search(
                language, api_url, variant, cache_dir,
                requester=requester, result_limit=result_limit,
                timeout=timeout, sleep_fn=sleep_fn)
            attempted.append({'language': language, 'query': variant})
            cache_hits += int(cached)
            network_calls += int(not cached)
            if error:
                errors.append({
                    'language': language, 'query': variant, 'error': error,
                })
            for raw in found:
                key = (language, raw.get('pageid'), raw.get('title'))
                if key in seen_pages:
                    continue
                seen_pages.add(key)
                matches.append({
                    'language': language,
                    'query_variant': variant,
                    'title': raw.get('title', ''),
                    'pageid': raw.get('pageid'),
                    'url': page_url(url_prefix, raw.get('title', '')),
                    'snippet': clean_text(raw.get('snippet', ''))[:600],
                    'wordcount': raw.get('wordcount'),
                    'timestamp': raw.get('timestamp'),
                })
            if throttle and not cached:
                sleep_fn(throttle)

    core_query_keys = {
        core_variant.casefold(), f'insource:"{core_variant}"'.casefold(),
    }
    matches.sort(key=lambda match: (
        match['query_variant'].casefold() not in core_query_keys,
        match['language'] != 'en', match['title'].casefold()))
    site_by_language = {site[0]: site for site in SITES}
    for match in matches[:10]:
        language = match['language']
        api_url = site_by_language[language][1]
        content, error, cached = cached_page_content(
            language, api_url, match['pageid'], cache_dir,
            requester=page_requester, timeout=timeout, sleep_fn=sleep_fn)
        page_cache_hits += int(cached)
        page_network_calls += int(not cached)
        if error:
            errors.append({
                'language': language, 'pageid': match['pageid'],
                'error': error,
            })
        match['excerpt'] = evidence_excerpt(
            content, [core_variant, match['query_variant']])
        direct_haystack = (content + ' ' + match.get('snippet', '')).casefold()
        match['direct'] = bool(
            core_variant and core_variant.casefold() in direct_haystack)
        if throttle and not cached:
            sleep_fn(throttle)

    matches.sort(key=lambda match: (
        not match.get('direct', False), match['language'] != 'en',
        match['title'].casefold()))
    direct_matches = [match for match in matches if match.get('direct')]
    if direct_matches:
        status = 'direct_evidence'
        titles = '、'.join(match['title'] for match in direct_matches[:6])
        finding = (
            f'Fandom 对核心查询“{core_variant}”直接命中：{titles}。'
            '命中页仍只作为证据，须由 High 结合英文原文、本地重复语料与'
            '天邈既有译法裁决。')
    elif matches:
        status = 'context_hits'
        titles = '、'.join(match['title'] for match in matches[:6])
        finding = (
            f'Fandom 未直接命中核心查询“{core_variant}”，仅有上下文页面：'
            f'{titles}。这些页面不能证明词义，只能辅助定位场景。')
    elif errors and len(errors) == len(attempted):
        status = 'lookup_error'
        finding = '英文与中文 Fandom 查询均失败；不可据此作翻译结论。'
    else:
        status = 'no_match'
        finding = (
            '英文与中文 Fandom 均未找到相关页面；High 只能依靠本地上下文'
            '与语言证据，若仍无法唯一裁决则进入人工审核。')

    shared = {
        'status': status,
        'query': group.get('query', ''),
        'subject': subject,
        'direct_query_variant': core_variant,
        'finding': finding,
        'recommended_action': 'high_adjudication',
        'attempted_queries': attempted,
        'sources': [
            {'title': match['title'], 'url': match['url'],
             'evidence': match['snippet'],
             'page_excerpt': match.get('excerpt', ''),
             'direct': match.get('direct', False),
             'language': match['language'],
             'query_variant': match['query_variant']}
            for match in matches[:10]
        ],
        'lookup_errors': errors,
        'lookup_stats': {
            'cache_hits': cache_hits, 'network_calls': network_calls,
            'page_cache_hits': page_cache_hits,
            'page_network_calls': page_network_calls,
            'unique_matches': len(matches),
        },
        'notes': 'Dishonored Fandom 是用户指定的社区 Wiki，不等同于官方中文本地化。',
    }
    return [dict(shared, id=identifier) for identifier in group.get('ids', [])]


def run(groups, cache_dir, requester=api_search,
        page_requester=api_page_content, result_limit=5, timeout=25,
        throttle=0.15, sleep_fn=time.sleep):
    rows = []
    for index, group in enumerate(groups, 1):
        rows.extend(research_group(
            group, cache_dir, requester=requester, result_limit=result_limit,
            page_requester=page_requester, timeout=timeout,
            throttle=throttle, sleep_fn=sleep_fn))
        print(f'  [{index}/{len(groups)}] {group.get("query", "")[:70]}')
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--queries', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--cache-dir')
    parser.add_argument('--result-limit', type=int, default=5)
    parser.add_argument('--timeout', type=int, default=25)
    parser.add_argument('--throttle', type=float, default=0.15)
    parser.add_argument('--max-groups', type=int, default=0)
    parser.add_argument('--manifest')
    args = parser.parse_args(argv)
    if args.result_limit < 1 or args.result_limit > 20:
        parser.error('--result-limit 必须在 1..20')
    if args.timeout < 1:
        parser.error('--timeout 必须大于 0')
    if args.throttle < 0 or args.throttle > 5:
        parser.error('--throttle 必须在 0..5')

    groups = read_jsonl(args.queries)
    if args.max_groups:
        groups = groups[:args.max_groups]
    cache_dir = args.cache_dir or str(Path(args.out).with_suffix(
        Path(args.out).suffix + '.fandom-cache'))
    rows = run(
        groups, cache_dir, result_limit=args.result_limit,
        timeout=args.timeout, throttle=args.throttle)
    rp.atomic_write_jsonl(args.out, rows)
    counts = Counter(row['status'] for row in rows)
    manifest = {
        'created_at': rp.now_utc(),
        'query_groups': len(groups), 'output_rows': len(rows),
        'status_counts': dict(counts), 'cache_dir': os.path.abspath(cache_dir),
        'sites': [site[1] for site in SITES],
        'hashes': {
            'queries': rp.sha256_file(args.queries),
            'output': rp.sha256_file(args.out),
        },
    }
    manifest_path = args.manifest or args.out + '.manifest.json'
    rp.atomic_write_json(manifest_path, manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0 if counts.get('lookup_error', 0) == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
