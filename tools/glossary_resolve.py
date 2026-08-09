# -*- coding: utf-8 -*-
"""Phase 2 高推理二审：裁决首轮冲突/低证据项，压缩人工审核。"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import glossary_pipeline as gp
import review_pipeline as rp
from phase1_extract import json_write, jsonl_write, sha256_file


PIPELINE_VERSION = 1


def entry_for_model(candidate, prior):
    return {
        'id': candidate['id'],
        'en_term': candidate['en_term'],
        'seed_value': candidate.get('seed_value', ''),
        'row_count': candidate.get('row_count', 0),
        'proper_row_count': candidate.get('proper_row_count', 0),
        'label_row_count': candidate.get('label_row_count', 0),
        'releases': candidate.get('releases', {}),
        'exact_cn_variants': candidate.get('exact_cn_variants', []),
        'prior': {
            'action': prior['action'],
            'cn_term': prior['cn_term'],
            'category': prior['category'],
            'confidence': prior['confidence'],
            'reason': prior['reason'],
            'conflict_reason': prior['conflict_reason'],
            'route_reason': prior['route_reason'],
        },
        'contexts': [
            {
                'id': context['id'],
                'layer': context['layer'],
                'release': context['release'],
                'en': context['en'],
                'cn': context['cn'],
            }
            for context in candidate.get('contexts', [])
        ],
    }


def validate_resolution(items, expected_ids, candidate_by_id):
    if not isinstance(items, list):
        raise ValueError('items 不是数组')
    expected_ids = list(expected_ids)
    seen = set()
    normalized = []
    for index, raw in enumerate(items):
        if not isinstance(raw, dict):
            raise ValueError(f'items[{index}] 不是对象')
        missing = gp.OUTPUT_FIELDS - set(raw)
        extra = set(raw) - gp.OUTPUT_FIELDS
        if missing or extra:
            raise ValueError(
                f'items[{index}] 字段错误: 缺少={sorted(missing)} 多出={sorted(extra)}')
        item = dict(raw)
        item_id = item['id']
        if item_id not in candidate_by_id or item_id in seen:
            raise ValueError(f'非法或重复 id: {item_id!r}')
        seen.add(item_id)
        if item['action'] not in ('lock', 'review', 'reject'):
            raise ValueError(f'{item_id}: action 非法')
        if item['category'] not in gp.CATEGORIES:
            raise ValueError(f'{item_id}: category 非法')
        for field in ('cn_term', 'reason', 'conflict_reason'):
            if not isinstance(item[field], str):
                raise ValueError(f'{item_id}: {field} 必须是字符串')
            item[field] = item[field].strip()
        if not item['reason']:
            raise ValueError(f'{item_id}: reason 不能为空')
        value = item['confidence']
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f'{item_id}: confidence 必须是数字')
        item['confidence'] = float(value)
        if not 0 <= item['confidence'] <= 1:
            raise ValueError(f'{item_id}: confidence 超出 0..1')
        if not isinstance(item['conflict'], bool):
            raise ValueError(f'{item_id}: conflict 必须是布尔值')
        if item['conflict'] and not item['conflict_reason']:
            raise ValueError(f'{item_id}: conflict=true 必须说明理由')
        if not item['conflict']:
            item['conflict_reason'] = ''
        if not isinstance(item['evidence_ids'], list) or any(
                not isinstance(evidence_id, str) or not evidence_id
                for evidence_id in item['evidence_ids']):
            raise ValueError(f'{item_id}: evidence_ids 非法')
        if len(item['evidence_ids']) != len(set(item['evidence_ids'])):
            raise ValueError(f'{item_id}: evidence_ids 重复')

        candidate = candidate_by_id[item_id]
        contexts = candidate.get('contexts', [])
        context_by_id = {context['id']: context for context in contexts}
        unknown = set(item['evidence_ids']) - set(context_by_id)
        if unknown:
            raise ValueError(f'{item_id}: 未提供的证据 ID {sorted(unknown)}')
        supported = any(
            item['cn_term'] and item['cn_term'] in context_by_id[evidence_id]['cn']
            for evidence_id in item['evidence_ids'])

        if item['action'] == 'reject':
            if item['cn_term'] or item['evidence_ids']:
                raise ValueError(f'{item_id}: reject 必须清空译名和证据')
        elif item['cn_term'] and (not item['evidence_ids'] or not supported):
            raise ValueError(f'{item_id}: cn_term 缺少连续子串证据')
        if item['action'] == 'lock':
            if not item['cn_term'] or not item['evidence_ids']:
                raise ValueError(f'{item_id}: lock 必须有译名和证据')
            if item['confidence'] < 0.95:
                raise ValueError(f'{item_id}: lock 置信度低于 0.95')
            if item['conflict']:
                raise ValueError(f'{item_id}: lock 不得保留未解决冲突')
            if item['category'] in ('generic', 'noise'):
                raise ValueError(f'{item_id}: 普通词/噪声不能 lock')
            if candidate['en_term'].casefold() == 'whale' \
                    and item['cn_term'] == '鲸油':
                raise ValueError(f'{item_id}: 禁止 Whale -> 鲸油')
        normalized.append(item)

    got = [item['id'] for item in normalized]
    if len(got) != len(expected_ids) or set(got) != set(expected_ids):
        raise ValueError('输出 ID 集合与输入不一致')
    return normalized


def parse_response(content, expected_ids, candidate_by_id):
    content = content.strip()
    match = re.fullmatch(r'```(?:json)?\s*(.*?)\s*```', content, re.S)
    if match:
        content = match.group(1)
    data = json.loads(content)
    if not isinstance(data, dict) or set(data) != {'items'}:
        raise ValueError('顶层必须严格为 {"items": [...]}')
    return validate_resolution(data['items'], expected_ids, candidate_by_id)


def resolve_batch(batch, index, prior_by_id, system_prompt, template,
                  settings, config_hash, batch_dir, max_retries=3):
    candidate_by_id = {candidate['id']: candidate for candidate in batch}
    entries = [entry_for_model(candidate, prior_by_id[candidate['id']])
               for candidate in batch]
    expected_ids = [candidate['id'] for candidate in batch]
    input_hash = rp.sha256_value(entries)
    result_path = batch_dir / f'batch_{index:04d}.json'
    request_path = batch_dir / 'requests' / f'batch_{index:04d}.json'
    failure_path = batch_dir / 'failures' / f'batch_{index:04d}.json'
    rp.atomic_write_json(str(request_path), {
        'batch': index, 'input_hash': input_hash,
        'config_hash': config_hash, 'entries': entries,
    })
    if result_path.exists():
        try:
            data = json.loads(result_path.read_text(encoding='utf-8'))
            meta = data.get('meta', {})
            if meta.get('input_hash') != input_hash or meta.get('config_hash') != config_hash:
                raise ValueError('缓存哈希变化')
            items = validate_resolution(data.get('items'), expected_ids, candidate_by_id)
            print(f'  [跳过] resolve batch_{index:04d}（缓存有效）')
            return {'items': items, 'meta': meta, 'cached': True}
        except Exception as exc:
            archived = rp.archive_stale(str(result_path))
            print(f'  [过期] {result_path.name}: {exc}; 保留为 {Path(archived).name}')

    user_prompt = template.replace(
        '{entries}', json.dumps(entries, ensure_ascii=False, indent=1))
    errors = []
    for attempt in range(max_retries):
        try:
            content, call_meta = rp.call_model(system_prompt, user_prompt, settings)
            items = parse_response(content, expected_ids, candidate_by_id)
            meta = {
                'backend': settings['backend'], 'model': settings['model'],
                'reasoning_effort': settings.get('reasoning_effort'),
                'input_hash': input_hash, 'config_hash': config_hash,
                'completed_at': rp.now_utc(),
                'usage': call_meta.get('usage', {}),
            }
            rp.atomic_write_json(str(result_path), {
                'batch': index, 'meta': meta, 'items': items,
            })
            rp.safe_unlink(str(failure_path))
            print(f'  [OK] resolve batch_{index:04d}: {len(items)} 条')
            return {'items': items, 'meta': meta, 'cached': False}
        except Exception as exc:
            message = str(exc)
            errors.append(message)
            print(f'  [重试 {attempt + 1}/{max_retries}] resolve batch_{index:04d}: {message}')
            if not rp.is_retryable_error(message):
                break
            if attempt + 1 < max_retries:
                time.sleep(3 * (2 ** attempt))
    rp.atomic_write_json(str(failure_path), {
        'batch': index, 'input_hash': input_hash,
        'config_hash': config_hash, 'failed_at': rp.now_utc(), 'errors': errors,
    })
    return None


def compact_term(item, source):
    return {
        'id': item['id'], 'en_term': item['en_term'], 'cn_term': item['cn_term'],
        'category': item['category'], 'confidence': item['confidence'],
        'reason': item['reason'], 'evidence_ids': item['evidence_ids'],
        'source': source,
    }


def write_remaining_csv(path, items):
    fields = [
        'user_decision', 'en_term', 'recommended_cn', 'user_cn', 'category',
        'confidence', 'seed_value', 'exact_cn_variants', 'reason',
        'conflict_reason', 'evidence_ids', 'examples',
    ]
    with open(path, 'w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for item in sorted(items, key=lambda value: (-value['row_count'], value['en_term'])):
            writer.writerow({
                'user_decision': '', 'en_term': item['en_term'],
                'recommended_cn': item['cn_term'], 'user_cn': '',
                'category': item['category'], 'confidence': f"{item['confidence']:.2f}",
                'seed_value': item['seed_value'],
                'exact_cn_variants': json.dumps(
                    item['exact_cn_variants'], ensure_ascii=False,
                    separators=(',', ':')),
                'reason': item['reason'], 'conflict_reason': item['conflict_reason'],
                'evidence_ids': ' | '.join(item['evidence_ids']),
                'examples': ' || '.join(
                    f"{ctx['id']} | EN: {ctx['en']} | CN: {ctx['cn']}"
                    for ctx in item['evidence']),
            })


def main(argv=None):
    rp.load_env()
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidates', default='data/review/glossary/candidates.jsonl')
    parser.add_argument('--recommendations', default='data/review/glossary/recommendations.jsonl')
    parser.add_argument('--terms', default='glossary/terms.json')
    parser.add_argument('--system', default='prompt/glossary_resolve_system.md')
    parser.add_argument('--template', default='prompt/glossary_resolve_template.md')
    parser.add_argument('--schema', default='tools/glossary_schema.json')
    parser.add_argument('--review-dir', default='data/review/glossary/resolution')
    parser.add_argument('--backend', choices=('codex', 'api'),
                        default=rp.cfg('LLM_BACKEND', 'codex'))
    parser.add_argument('--model')
    parser.add_argument('--reasoning-effort',
                        choices=('none', 'low', 'medium', 'high', 'xhigh', 'max'),
                        default='high')
    parser.add_argument('--batch-size', type=int, default=45)
    parser.add_argument('--concurrency', type=int, default=2)
    args = parser.parse_args(argv)

    candidates = gp.load_jsonl(args.candidates)
    recommendations = gp.load_jsonl(args.recommendations)
    candidate_by_id = {item['id']: item for item in candidates}
    prior_by_id = {item['id']: item for item in recommendations}
    selected_prior = [item for item in recommendations
                      if item['route'] == 'human_review']
    selected = [candidate_by_id[item['id']] for item in selected_prior]
    try:
        settings = rp.build_settings(args)
    except Exception as exc:
        print(f'错误: {exc}')
        return 2
    system_prompt = Path(args.system).read_text(encoding='utf-8')
    template = Path(args.template).read_text(encoding='utf-8')
    hashes = {
        'candidates': sha256_file(args.candidates),
        'recommendations': sha256_file(args.recommendations),
        'formal_terms': sha256_file(args.terms),
        'system_prompt': sha256_file(args.system),
        'template': sha256_file(args.template),
        'schema': sha256_file(args.schema),
    }
    config_hash = rp.sha256_value({
        'pipeline_version': PIPELINE_VERSION,
        'backend': rp.fingerprint_settings(settings),
        'batch_size': args.batch_size, 'hashes': hashes,
    })
    batches = [selected[i:i + args.batch_size]
               for i in range(0, len(selected), args.batch_size)]
    out_dir = Path(args.review_dir)
    batch_dir = out_dir / 'model_batches'
    rp.atomic_write_json(str(out_dir / 'run_manifest.json'), {
        'pipeline_version': PIPELINE_VERSION, 'created_at': rp.now_utc(),
        'backend': rp.public_settings(settings),
        'auth_status': settings.get('auth_status'),
        'input_review_count': len(selected), 'batch_size': args.batch_size,
        'scheduled_batches': len(batches), 'config_hash': config_hash,
        'formal_terms_protected': True, 'hashes': hashes,
    })
    print(f'高推理二审: {len(selected)} 条 / {len(batches)} 批 / 并发 {args.concurrency}')
    outcomes = []
    failures = []
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as executor:
        future_map = {
            executor.submit(
                resolve_batch, batch, index, prior_by_id, system_prompt,
                template, settings, config_hash, batch_dir): index
            for index, batch in enumerate(batches)
        }
        for future in as_completed(future_map):
            index = future_map[future]
            try:
                outcome = future.result()
            except Exception as exc:
                print(f'  [异常] resolve batch_{index:04d}: {exc}')
                outcome = None
            if outcome:
                outcomes.append(outcome)
            else:
                failures.append(index)

    resolution = [item for outcome in outcomes for item in outcome['items']]
    resolution_by_id = {item['id']: item for item in resolution}
    enriched = []
    for prior in selected_prior:
        if prior['id'] not in resolution_by_id:
            continue
        result = resolution_by_id[prior['id']]
        candidate = candidate_by_id[prior['id']]
        enriched.append({
            **result,
            'en_term': candidate['en_term'],
            'seed_value': candidate.get('seed_value', ''),
            'row_count': candidate.get('row_count', 0),
            'exact_cn_variants': candidate.get('exact_cn_variants', []),
            'prior_action': prior['action'],
            'prior_cn_term': prior['cn_term'],
            'prior_reason': prior['reason'],
            'evidence': [context for context in candidate.get('contexts', [])
                         if context['id'] in result['evidence_ids']],
        })
    enriched.sort(key=lambda item: item['en_term'].casefold())
    jsonl_write(out_dir / 'resolution.jsonl', enriched)

    pass1_auto = [item for item in recommendations if item['route'] == 'auto_lock']
    resolved_locks = [item for item in enriched if item['action'] == 'lock']
    all_locks = [compact_term(item, 'medium_pass') for item in pass1_auto]
    all_locks.extend(compact_term(item, 'high_resolution') for item in resolved_locks)
    all_locks.sort(key=lambda item: item['en_term'].casefold())
    jsonl_write(out_dir / 'resolved_terms.jsonl', all_locks)
    remaining = [item for item in enriched if item['action'] == 'review']
    jsonl_write(out_dir / 'remaining_human_review.jsonl', remaining)
    rejected = [item for item in recommendations if item['route'] == 'reject']
    rejected.extend(item for item in enriched if item['action'] == 'reject')
    jsonl_write(out_dir / 'resolved_rejected.jsonl', rejected)
    write_remaining_csv(out_dir / 'remaining_human_review.csv', remaining)

    resolution_by_id = {item['id']: item for item in enriched}
    decisions = []
    for prior in recommendations:
        if prior['route'] == 'human_review':
            result = resolution_by_id[prior['id']]
            source = 'high_resolution'
            decision = {
                'id': result['id'], 'en_term': result['en_term'],
                'action': result['action'], 'cn_term': result['cn_term'],
                'category': result['category'], 'confidence': result['confidence'],
                'reason': result['reason'],
                'conflict': result['conflict'],
                'conflict_reason': result['conflict_reason'],
                'evidence_ids': result['evidence_ids'],
                'seed_value': result['seed_value'], 'source': source,
            }
        else:
            source = 'medium_pass'
            decision = {
                'id': prior['id'], 'en_term': prior['en_term'],
                'action': prior['action'], 'cn_term': prior['cn_term'],
                'category': prior['category'], 'confidence': prior['confidence'],
                'reason': prior['reason'],
                'conflict': prior['conflict'],
                'conflict_reason': prior['conflict_reason'],
                'evidence_ids': prior['evidence_ids'],
                'seed_value': prior['seed_value'], 'source': source,
            }
        decisions.append(decision)
    jsonl_write(out_dir / 'resolution_decisions.jsonl', decisions)

    decision_by_en = {item['en_term'].casefold(): item for item in decisions}
    terms_raw = json.loads(Path(args.terms).read_text(encoding='utf-8'))
    seeds = {key: value for key, value in terms_raw.items() if not key.startswith('_')}
    seed_audit = []
    for english, old_cn in seeds.items():
        decision = decision_by_en.get(english.casefold())
        if not decision:
            status = 'missing'
            recommended = ''
            reason = '旧种子未进入最终候选结论。'
        elif decision['action'] == 'reject':
            status = 'remove_recommended'
            recommended = ''
            reason = decision['reason']
        elif decision['action'] == 'review':
            status = 'human_review'
            recommended = decision['cn_term']
            reason = decision['reason']
        elif decision['cn_term'] == old_cn:
            status = 'confirmed'
            recommended = decision['cn_term']
            reason = decision['reason']
        else:
            status = 'replace_recommended'
            recommended = decision['cn_term']
            reason = decision['reason']
        seed_audit.append({
            'en_term': english, 'old_cn': old_cn, 'status': status,
            'recommended_cn': recommended,
            'action': decision['action'] if decision else '',
            'reason': reason,
            'evidence_ids': decision['evidence_ids'] if decision else [],
        })
    json_write(out_dir / 'resolution_seed_audit.json', seed_audit)

    core_names = {
        name.casefold() for name in (*gp.glossary_extract.CORE_TERMS, *seeds)
    }
    core = [item for item in decisions if item['en_term'].casefold() in core_names]
    json_write(out_dir / 'resolution_core_terms.json', core)

    validation_errors = []
    validation_warnings = []
    decision_ids = [item['id'] for item in decisions]
    if len(decision_ids) != len(set(decision_ids)):
        validation_errors.append('最终结论 ID 重复')
    if len(decisions) != len(candidates):
        validation_errors.append(
            f'最终结论数量 {len(decisions)} != 候选数量 {len(candidates)}')
    if sum(1 for item in decisions if item['action'] == 'lock') \
            + sum(1 for item in decisions if item['action'] == 'review') \
            + sum(1 for item in decisions if item['action'] == 'reject') \
            != len(decisions):
        validation_errors.append('最终结论分区不完备')
    term_keys = [item['en_term'].casefold() for item in all_locks]
    if len(term_keys) != len(set(term_keys)):
        validation_errors.append('建议术语英文 key 重复')
    for item in all_locks:
        if not item['en_term'].strip() or not item['cn_term'].strip():
            validation_errors.append(f'{item["id"]}: 建议术语键值为空')
        if '\n' in item['en_term'] or re.search(r'<[^>]*>|`[^`]*`', item['en_term']):
            validation_errors.append(f'{item["id"]}: 建议术语键含格式标签/换行')
    missing_core = sorted(core_names - set(decision_by_en))
    if missing_core:
        validation_errors.append(f'缺少核心词结论: {missing_core}')

    regressions = {
        'Emily': ('lock', '艾米莉'),
        'Dishonored': ('lock', '耻辱'),
        'Whale': ('reject', ''),
        'Whale Oil': ('lock', '鲸油'),
    }
    regression_results = []
    for english, (wanted_action, wanted_cn) in regressions.items():
        item = decision_by_en.get(english.casefold())
        passed = bool(
            item and item['action'] == wanted_action and item['cn_term'] == wanted_cn)
        regression_results.append({
            'en_term': english, 'expected_action': wanted_action,
            'expected_cn': wanted_cn,
            'actual_action': item['action'] if item else '',
            'actual_cn': item['cn_term'] if item else '', 'passed': passed,
        })
        if not passed:
            validation_errors.append(f'旧种子回归失败: {english}')

    by_cn = defaultdict(list)
    for item in all_locks:
        by_cn[item['cn_term']].append(item['en_term'])
    for cn_term, english_terms in sorted(by_cn.items()):
        if len(english_terms) > 1:
            validation_warnings.append({
                'type': 'same_cn_multiple_en', 'cn_term': cn_term,
                'en_terms': sorted(english_terms),
            })
    formal_after = sha256_file(args.terms)
    if formal_after != hashes['formal_terms']:
        validation_errors.append('正式 terms.json 在二审期间发生变化')
    validation = {
        'status': 'pass' if not validation_errors else 'fail',
        'candidate_count': len(candidates), 'decision_count': len(decisions),
        'resolved_term_count': len(all_locks),
        'remaining_human_review_count': len(remaining),
        'rejected_count': len(rejected), 'core_conclusion_count': len(core),
        'missing_core_terms': missing_core,
        'formal_terms_sha256_before': hashes['formal_terms'],
        'formal_terms_sha256_after': formal_after,
        'seed_regressions': regression_results,
        'errors': validation_errors, 'warnings': validation_warnings,
    }
    json_write(out_dir / 'resolution_validation.json', validation)

    actions = Counter(item['action'] for item in enriched)
    summary = {
        'input_review_count': len(selected),
        'completed_count': len(enriched),
        'scheduled_batches': len(batches),
        'completed_batches': len(outcomes),
        'cached_batches': sum(outcome.get('cached', False) for outcome in outcomes),
        'failed_batches': sorted(failures),
        'resolution_actions': dict(sorted(actions.items())),
        'pass1_auto_locks': len(pass1_auto),
        'resolved_additional_locks': len(resolved_locks),
        'total_resolved_terms': len(all_locks),
        'remaining_human_review': len(remaining),
        'total_rejected': len(rejected),
        'validation_status': validation['status'],
        'formal_terms_sha256': sha256_file(args.terms),
        'usage_all_completed_batches': rp.sum_usage(outcomes),
        'usage_this_run': rp.sum_usage(
            [outcome for outcome in outcomes if not outcome.get('cached')]),
        'config_hash': config_hash, 'updated_at': rp.now_utc(),
    }
    json_write(out_dir / 'resolution_summary.json', summary)
    print('\n二审汇总:', json.dumps(summary, ensure_ascii=False, indent=1))
    return 1 if failures or validation['status'] != 'pass' else 0


if __name__ == '__main__':
    sys.exit(main())
