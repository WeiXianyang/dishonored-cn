# -*- coding: utf-8 -*-
"""Independent safety audit for every formal hard-locked glossary term.

The module has two public seams used by tests and the CLI:

* ``build_audit_entries`` derives complete, traceable evidence from the corpus;
* ``validate_items`` validates one independent Agent decision per formal term.

It never edits ``glossary/terms.json`` or either game directory.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import review_pipeline as rp


PIPELINE_VERSION = 1
DECISIONS = {'keep_global', 'correct_global', 'restrict_scope', 'remove'}
SCOPES = {'global', 'exact_case', 'label_only', 'context_only', 'none'}
OUTPUT_FIELDS = {
    'id', 'decision', 'proposed_cn', 'scope', 'confidence', 'reason',
    'evidence_ids', 'risk_tags',
}
LABEL_FIELDS = {
    'm_name', 'm_itemname', 'm_pluralitemname', 'm_locationname',
    'm_targetname', 'm_interacttext', 'm_altinteracttext',
}


def read_jsonl(path):
    with open(path, encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def load_terms(path):
    raw = json.loads(Path(path).read_text(encoding='utf-8'))
    return {key: value for key, value in raw.items() if not key.startswith('_')}


def release_codes(entry):
    domain = entry.get('domain', {}) or {}
    values = []
    for key in ('release', 'primary_release'):
        if domain.get(key):
            values.append(domain[key])
    values.extend(domain.get('releases') or [])
    values.extend(
        ref.get('release') for ref in
        (entry.get('context', {}).get('references', []) or [])
        if ref.get('release'))
    return list(dict.fromkeys(values)) or ['unknown']


def context_field(entry):
    context = entry.get('context', {}) or {}
    return str(context.get('subkey') or context.get('key') or '').casefold()


def is_label(entry, term):
    field = context_field(entry)
    source = (entry.get('en') or '').strip()
    return field in LABEL_FIELDS or source.casefold() == term.casefold()


def effective_text(entry, final_by_id):
    result = final_by_id.get(entry['id'], {})
    if result.get('action') == 'fix':
        return result.get('new_text', '')
    return entry.get('cn', '')


def term_occurs(entry, term):
    return bool(rp.english_term_spans(
        entry.get('en', ''), term, case_sensitive_single_terms=False))


def nested_relations(terms, term):
    shorter = []
    longer = []
    probe = {'en': term}
    for other, chinese in terms.items():
        if other == term:
            continue
        if len(other) < len(term) and rp.english_term_spans(
                term, other, case_sensitive_single_terms=False):
            shorter.append({'en': other, 'cn': chinese})
        elif len(other) > len(term) and rp.english_term_spans(
                other, term, case_sensitive_single_terms=False):
            longer.append({'en': other, 'cn': chinese})
    return shorter, longer


def compact_context(entry, term, current_cn, final_by_id, evidence_ids):
    source = entry.get('en', '')
    releases = release_codes(entry)
    exact_case = term in source
    return {
        'id': entry['id'],
        'layer': entry.get('layer', ''),
        'releases': releases,
        'kind': 'label' if is_label(entry, term) else 'prose',
        'exact_case': exact_case,
        'prior_evidence': entry['id'] in evidence_ids,
        'en': source,
        'tianmiao_cn': entry.get('cn', ''),
        'phase4_cn': effective_text(entry, final_by_id),
        'current_cn_present_in_tianmiao': current_cn in (entry.get('cn') or ''),
    }


def choose_contexts(contexts, limit=12):
    """Keep risk-diverse evidence, not merely the first N rows."""
    ordered = sorted(contexts, key=lambda row: (
        not row['prior_evidence'],
        row['kind'] != 'prose',
        row['exact_case'],
        row['current_cn_present_in_tianmiao'],
        row['id'],
    ))
    chosen = []
    seen_releases = set()
    for row in ordered:
        novel_release = any(code not in seen_releases for code in row['releases'])
        if len(chosen) < limit and (novel_release or len(chosen) < 8):
            chosen.append(row)
            seen_releases.update(row['releases'])
    for row in ordered:
        if len(chosen) >= limit:
            break
        if row not in chosen:
            chosen.append(row)
    return chosen


def build_audit_entries(terms, evidence_items, corpus, final_rows):
    evidence_by_term = {item['en_term']: item for item in evidence_items}
    final_by_id = {item['id']: item for item in final_rows}
    corpus_by_id = {item['id']: item for item in corpus}
    if len(corpus_by_id) != len(corpus):
        raise ValueError('corpus contains duplicate IDs')
    output = []
    for term, current_cn in terms.items():
        prior = evidence_by_term.get(term, {})
        prior_evidence = set(prior.get('evidence_ids') or [])
        # A cheap substring prefilter avoids compiling/running a boundary regex
        # for every term×corpus pair (619×31,583 in the current corpus).
        folded_term = term.casefold()
        occurrences = [
            entry for entry in corpus
            if folded_term in (entry.get('en') or '').casefold()
            and term_occurs(entry, term)
        ]
        contexts = [
            compact_context(
                entry, term, current_cn, final_by_id, prior_evidence)
            for entry in occurrences
        ]
        releases = Counter(
            release for row in contexts for release in row['releases'])
        cn_variants = Counter(
            (entry.get('cn') or '').strip() for entry in occurrences
            if (entry.get('cn') or '').strip())
        shorter, longer = nested_relations(terms, term)
        risks = []
        if any(not row['exact_case'] for row in contexts):
            risks.append('case_drift')
        if len(releases) > 1:
            risks.append('cross_release')
        if any(row['kind'] == 'prose' for row in contexts):
            risks.append('prose_usage')
        if longer:
            risks.append('nested_in_longer_terms')
        if shorter:
            risks.append('contains_shorter_terms')
        if len(cn_variants) > 1:
            risks.append('multiple_tianmiao_contexts')
        if len(prior_evidence) <= 1:
            risks.append('thin_prior_evidence')
        prior_releases = {
            release for identifier in prior_evidence
            for release in release_codes(corpus_by_id[identifier])
            if identifier in corpus_by_id
        }
        occurrence_releases = set(releases)
        if prior_releases and occurrence_releases - prior_releases:
            risks.append('evidence_scope_expansion')
        output.append({
            'id': prior.get('id') or 'term:' + rp.sha256_text(term)[:16],
            'en_term': term,
            'current_cn': current_cn,
            'prior_category': prior.get('category', ''),
            'prior_confidence': prior.get('confidence'),
            'prior_reason': prior.get('reason', ''),
            'prior_evidence_ids': sorted(prior_evidence),
            'prior_wiki_urls': prior.get('wiki_urls', []),
            'stats': {
                'occurrences': len(contexts),
                'labels': sum(row['kind'] == 'label' for row in contexts),
                'prose': sum(row['kind'] == 'prose' for row in contexts),
                'case_drift': sum(not row['exact_case'] for row in contexts),
                'releases': dict(sorted(releases.items())),
            },
            'tianmiao_context_variants': [
                {'cn': cn, 'count': count}
                for cn, count in cn_variants.most_common(8)
            ],
            'nested_shorter': shorter,
            'nested_longer': longer,
            'static_risks': risks,
            'contexts': choose_contexts(contexts),
        })
    return output


def validate_items(items, expected_entries):
    by_id = {entry['id']: entry for entry in expected_entries}
    if not isinstance(items, list):
        raise ValueError('items must be an array')
    seen = set()
    output = []
    for index, raw in enumerate(items):
        if not isinstance(raw, dict):
            raise ValueError(f'items[{index}] is not an object')
        missing = OUTPUT_FIELDS - set(raw)
        extra = set(raw) - OUTPUT_FIELDS
        if missing or extra:
            raise ValueError(
                f'items[{index}] fields: missing={sorted(missing)} '
                f'extra={sorted(extra)}')
        item = dict(raw)
        identifier = item['id']
        if identifier not in by_id or identifier in seen:
            raise ValueError(f'invalid or duplicate id: {identifier!r}')
        seen.add(identifier)
        if item['decision'] not in DECISIONS:
            raise ValueError(f'{identifier}: invalid decision')
        if item['scope'] not in SCOPES:
            raise ValueError(f'{identifier}: invalid scope')
        for field in ('proposed_cn', 'reason'):
            if not isinstance(item[field], str):
                raise ValueError(f'{identifier}: {field} must be a string')
            item[field] = item[field].strip()
        if not item['reason']:
            raise ValueError(f'{identifier}: reason is empty')
        confidence = item['confidence']
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            raise ValueError(f'{identifier}: invalid confidence')
        item['confidence'] = float(confidence)
        if not 0 <= item['confidence'] <= 1:
            raise ValueError(f'{identifier}: confidence outside 0..1')
        for field in ('evidence_ids', 'risk_tags'):
            if not isinstance(item[field], list) or any(
                    not isinstance(value, str) or not value
                    for value in item[field]):
                raise ValueError(f'{identifier}: invalid {field}')
            if len(item[field]) != len(set(item[field])):
                raise ValueError(f'{identifier}: duplicate {field}')
        allowed = {row['id'] for row in by_id[identifier]['contexts']}
        unknown = set(item['evidence_ids']) - allowed
        if unknown:
            raise ValueError(f'{identifier}: unknown evidence IDs {sorted(unknown)}')
        current = by_id[identifier]['current_cn']
        decision = item['decision']
        if decision == 'keep_global':
            if item['scope'] != 'global' or item['proposed_cn'] != current:
                raise ValueError(f'{identifier}: invalid keep_global payload')
        elif decision == 'correct_global':
            if (item['scope'] != 'global' or not item['proposed_cn'] or
                    item['proposed_cn'] == current):
                raise ValueError(f'{identifier}: invalid correct_global payload')
        elif decision == 'restrict_scope':
            if item['scope'] not in {'exact_case', 'label_only', 'context_only'}:
                raise ValueError(f'{identifier}: invalid restricted scope')
            if not item['proposed_cn']:
                raise ValueError(f'{identifier}: restricted term needs a label value')
        elif decision == 'remove':
            if item['scope'] != 'none' or item['proposed_cn']:
                raise ValueError(f'{identifier}: invalid remove payload')
        output.append(item)
    if seen != set(by_id):
        raise ValueError(
            f'ID coverage mismatch: missing={sorted(set(by_id)-seen)[:5]} '
            f'extra={sorted(seen-set(by_id))[:5]}')
    return output


def parse_response(content, expected_entries):
    content = content.strip()
    match = re.fullmatch(r'```(?:json)?\s*(.*?)\s*```', content, re.S)
    if match:
        content = match.group(1)
    data = json.loads(content)
    if not isinstance(data, dict) or set(data) != {'items'}:
        raise ValueError('top level must be {"items": [...]}')
    return validate_items(data['items'], expected_entries)


def run_batch(batch, index, system_prompt, template, settings, config_hash,
              out_dir, max_retries=3):
    expected_ids = [entry['id'] for entry in batch]
    input_hash = rp.sha256_value(batch)
    result_path = out_dir / f'batch_{index:04d}.json'
    request_path = out_dir / 'requests' / f'batch_{index:04d}.json'
    failure_path = out_dir / 'failures' / f'batch_{index:04d}.json'
    rp.atomic_write_json(str(request_path), {
        'batch': index, 'input_hash': input_hash,
        'config_hash': config_hash, 'entries': batch,
    })
    if result_path.exists():
        try:
            data = json.loads(result_path.read_text(encoding='utf-8'))
            meta = data.get('meta', {})
            if (meta.get('input_hash') != input_hash or
                    meta.get('config_hash') != config_hash):
                raise ValueError('cache hash changed')
            items = validate_items(data.get('items'), batch)
            print(f'  [skip] audit batch_{index:04d}')
            return {'items': items, 'meta': meta, 'cached': True}
        except Exception as exc:
            archived = rp.archive_stale(str(result_path))
            print(f'  [stale] {result_path.name}: {exc}; {Path(archived).name}')
    prompt = template.replace(
        '{entries}', json.dumps(batch, ensure_ascii=False, indent=1))
    errors = []
    for attempt in range(max_retries):
        try:
            attempt_prompt = prompt
            if errors:
                attempt_prompt += (
                    '\n\n<retry_feedback>\n上一版未通过确定性校验：' +
                    errors[-1] +
                    '\n请逐字复制本批 contexts 中已有的 evidence id；不得改写、'
                    '补全或自行构造 ID。重新输出完整批次。\n</retry_feedback>')
            response = rp.call_model(system_prompt, attempt_prompt, settings)
            content, call_meta = response if isinstance(response, tuple) else (response, {})
            items = parse_response(content, batch)
            meta = {
                'backend': settings['backend'], 'model': settings['model'],
                'reasoning_effort': settings.get('reasoning_effort'),
                'input_hash': input_hash, 'config_hash': config_hash,
                'completed_at': rp.now_utc(), 'usage': call_meta.get('usage', {}),
                'attempts': attempt + 1,
            }
            rp.atomic_write_json(str(result_path), {
                'batch': index, 'meta': meta, 'items': items,
            })
            rp.safe_unlink(str(failure_path))
            print(f'  [OK] audit batch_{index:04d}: {len(items)} terms')
            return {'items': items, 'meta': meta, 'cached': False}
        except Exception as exc:
            errors.append(str(exc))
            print(f'  [retry {attempt + 1}/{max_retries}] audit batch_{index:04d}: {exc}')
            if not rp.is_retryable_error(str(exc)):
                break
            if attempt + 1 < max_retries:
                time.sleep(3 * (2 ** attempt))
    rp.atomic_write_json(str(failure_path), {
        'batch': index, 'input_hash': input_hash,
        'config_hash': config_hash, 'errors': errors,
    })
    return None


def main(argv=None):
    rp.load_env()
    parser = argparse.ArgumentParser()
    parser.add_argument('--terms', default='glossary/terms.json')
    parser.add_argument('--evidence', default='glossary/terms_evidence.json')
    parser.add_argument('--corpus', default='data/aligned/corpus.jsonl')
    parser.add_argument('--final-results',
                        default='data/review/phase4-final/final_results.jsonl')
    parser.add_argument('--system', default='prompt/glossary_audit_system.md')
    parser.add_argument('--template', default='prompt/glossary_audit_template.md')
    parser.add_argument('--schema', default='tools/glossary_audit_schema.json')
    parser.add_argument('--out-dir', default='data/review/glossary-audit')
    parser.add_argument('--backend', choices=('codex', 'api'),
                        default=rp.cfg('LLM_BACKEND', 'codex'))
    parser.add_argument('--model')
    parser.add_argument('--reasoning-effort',
                        choices=('none', 'low', 'medium', 'high', 'xhigh', 'max'),
                        default='high')
    parser.add_argument('--batch-size', type=int, default=20)
    parser.add_argument('--concurrency', type=int, default=2)
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args(argv)

    terms = load_terms(args.terms)
    evidence = json.loads(Path(args.evidence).read_text(encoding='utf-8'))['items']
    corpus = read_jsonl(args.corpus)
    final_rows = read_jsonl(args.final_results)
    entries = build_audit_entries(terms, evidence, corpus, final_rows)
    out = Path(args.out_dir)
    rp.atomic_write_jsonl(str(out / 'audit_corpus.jsonl'), entries)
    static_summary = {
        'created_at': rp.now_utc(), 'formal_terms': len(terms),
        'audit_entries': len(entries),
        'static_risk_counts': dict(sorted(Counter(
            risk for entry in entries for risk in entry['static_risks']).items())),
        'hashes': {
            'terms': rp.sha256_file(args.terms),
            'evidence': rp.sha256_file(args.evidence),
            'corpus': rp.sha256_file(args.corpus),
            'final_results': rp.sha256_file(args.final_results),
            'audit_corpus': rp.sha256_file(str(out / 'audit_corpus.jsonl')),
        },
    }
    rp.atomic_write_json(str(out / 'static_summary.json'), static_summary)
    if args.prepare_only:
        print(json.dumps(static_summary, ensure_ascii=False, indent=2))
        return 0

    settings = rp.build_settings(args)
    system_prompt = Path(args.system).read_text(encoding='utf-8')
    template = Path(args.template).read_text(encoding='utf-8')
    hashes = dict(static_summary['hashes'], **{
        'system': rp.sha256_file(args.system),
        'template': rp.sha256_file(args.template),
        'schema': rp.sha256_file(args.schema),
    })
    config_hash = rp.sha256_value({
        'pipeline_version': PIPELINE_VERSION,
        'backend': rp.fingerprint_settings(settings),
        'batch_size': args.batch_size, 'hashes': hashes,
    })
    batches = [entries[i:i + args.batch_size]
               for i in range(0, len(entries), args.batch_size)]
    rp.atomic_write_json(str(out / 'run_manifest.json'), {
        'pipeline_version': PIPELINE_VERSION, 'created_at': rp.now_utc(),
        'backend': rp.public_settings(settings),
        'input_terms': len(entries), 'scheduled_batches': len(batches),
        'batch_size': args.batch_size, 'concurrency': args.concurrency,
        'config_hash': config_hash, 'hashes': hashes,
    })
    print(f'Glossary audit: {len(entries)} terms / {len(batches)} batches')
    outcomes = {}
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as executor:
        future_map = {
            executor.submit(
                run_batch, batch, index, system_prompt, template, settings,
                config_hash, out / 'batches'): index
            for index, batch in enumerate(batches)
        }
        for future in as_completed(future_map):
            outcomes[future_map[future]] = future.result()
    failures = [index for index, result in outcomes.items() if result is None]
    if failures:
        print(f'Failed batches: {failures}')
        return 1
    decisions = [
        item for index in range(len(batches))
        for item in outcomes[index]['items']
    ]
    validate_items(decisions, entries)
    entry_by_id = {entry['id']: entry for entry in entries}
    enriched = [{**item,
                 'en_term': entry_by_id[item['id']]['en_term'],
                 'current_cn': entry_by_id[item['id']]['current_cn'],
                 'static_risks': entry_by_id[item['id']]['static_risks']}
                for item in decisions]
    rp.atomic_write_jsonl(str(out / 'results.jsonl'), enriched)
    summary = dict(static_summary, **{
        'completed_terms': len(enriched),
        'decisions': dict(sorted(Counter(
            item['decision'] for item in enriched).items())),
        'scopes': dict(sorted(Counter(
            item['scope'] for item in enriched).items())),
        'failed_batches': [],
    })
    summary['hashes'] = dict(summary['hashes'], **{
        'results': rp.sha256_file(str(out / 'results.jsonl')),
    })
    rp.atomic_write_json(str(out / 'summary.json'), summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
