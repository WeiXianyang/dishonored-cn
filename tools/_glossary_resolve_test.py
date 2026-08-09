# -*- coding: utf-8 -*-
"""高推理术语裁决契约测试。"""
from glossary_resolve import validate_resolution


def main():
    candidate = {
        'id': 'term:test', 'en_term': 'Emily',
        'contexts': [
            {'id': 'row:1', 'cn': '艾米莉'},
            {'id': 'row:2', 'cn': '艾米丽'},
        ],
    }
    valid = {
        'id': 'term:test', 'action': 'lock', 'cn_term': '艾米莉',
        'category': 'person', 'confidence': 0.98,
        'reason': '直接名称字段多数支持此写法。',
        'evidence_ids': ['row:1'], 'conflict': False, 'conflict_reason': '',
    }
    validate_resolution([valid], ['term:test'], {'term:test': candidate})
    for changes in (
        {'confidence': 0.94},
        {'evidence_ids': ['row:2']},
        {'conflict': True, 'conflict_reason': '尚未解决'},
    ):
        value = {**valid, **changes}
        try:
            validate_resolution([value], ['term:test'], {'term:test': candidate})
        except ValueError:
            continue
        raise AssertionError(f'本应失败: {changes}')
    print('glossary resolution contract tests: PASS')


if __name__ == '__main__':
    main()
