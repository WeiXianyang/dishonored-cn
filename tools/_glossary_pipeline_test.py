# -*- coding: utf-8 -*-
"""Phase 2 术语模型契约的轻量回归测试。"""
from glossary_pipeline import routing_decision, validate_items


def candidate(term='Corvo', seed='', variants=None, cn='科尔沃'):
    variants = variants if variants is not None else [{'cn': cn, 'count': 2}]
    return {
        'id': 'term:test',
        'en_term': term,
        'seed_value': seed,
        'exact_cn_variants': variants,
        'contexts': [{'id': 'row:1', 'en': term, 'cn': cn}],
    }


def result(**updates):
    value = {
        'id': 'term:test',
        'action': 'lock',
        'cn_term': '科尔沃',
        'category': 'person',
        'confidence': 0.96,
        'reason': '直接名称字段一致。',
        'evidence_ids': ['row:1'],
        'conflict': False,
        'conflict_reason': '',
    }
    value.update(updates)
    return value


def must_fail(item, source):
    try:
        validate_items([item], ['term:test'], {'term:test': source})
    except ValueError:
        return
    raise AssertionError(f'本应失败: {item}')


def main():
    source = candidate()
    checked = validate_items([result()], ['term:test'], {'term:test': source})
    assert checked[0]['action'] == 'lock'

    must_fail(result(evidence_ids=['row:unknown']), source)
    must_fail(result(confidence=0.89), source)
    must_fail(result(category='generic'), source)
    must_fail(result(cn_term='科沃尔'), source)

    seeded = candidate(seed='科沃尔')
    must_fail(result(), seeded)

    conflicted = candidate(variants=[
        {'cn': '科尔沃', 'count': 2}, {'cn': '科沃尔', 'count': 1},
    ])
    must_fail(result(), conflicted)
    review = result(
        action='review', conflict=True, conflict_reason='存在两个直接译名。')
    validate_items([review], ['term:test'], {'term:test': conflicted})

    rejected = result(
        action='reject', cn_term='', category='noise', confidence=0.99,
        evidence_ids=[])
    validate_items([rejected], ['term:test'], {'term:test': source})

    whale = candidate(term='Whale', seed='鲸油', variants=[], cn='鲸油使帝国工业化')
    whale_lock = result(
        cn_term='鲸油', category='world_term', evidence_ids=['row:1'])
    must_fail(whale_lock, whale)

    assert routing_decision({**result(), 'row_count': 2})[0] == 'auto_lock'
    assert routing_decision({**result(), 'row_count': 1})[0] == 'human_review'
    assert routing_decision({**result(confidence=0.94), 'row_count': 2})[0] == 'human_review'
    assert routing_decision({**rejected, 'row_count': 20})[0] == 'reject'
    print('glossary pipeline contract tests: PASS')


if __name__ == '__main__':
    main()
