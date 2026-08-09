# -*- coding: utf-8 -*-
import phase4_build_overrides as p4


def review(identifier, action='keep', text='', uncertain=False):
    return {
        'id': identifier, 'action': action, 'new_text': text,
        'reason': '裁决', 'confidence': 0.9, 'uncertain': uncertain,
        'uncertain_reason': '需要音频' if uncertain else '',
    }


def main():
    phase4 = [review('same'), review('candidate'), review('changed', 'fix', '新修补')]
    human = [
        {'id': 'same', 'route': 'human_after_high', 'candidate_cn': '基线'},
        {'id': 'candidate', 'route': 'human_after_high', 'candidate_cn': 'High 候选'},
        {'id': 'changed', 'route': 'human_after_high', 'candidate_cn': '旧候选'},
        {'id': 'cn-only', 'route': 'human_unpaired_cn_only', 'candidate_cn': '中文'},
    ]
    escalation = [
        {'id': 'same', 'cn': '基线'}, {'id': 'candidate', 'cn': 'Medium 基线'},
        {'id': 'changed', 'cn': '旧候选'}, {'id': 'extra', 'cn': '错误基线'},
    ]
    high = [review(row['id']) for row in escalation]
    rows, stats = p4.build_overrides(
        phase4, human, escalation, high,
        manual={'same': {'text': '人工修正', 'reason': '证据'}},
        extra={'extra': {'text': '额外修正', 'reason': '术语纠错'}})
    by_id = {row['id']: row for row in rows}
    assert by_id['same']['action'] == 'fix'
    assert by_id['same']['new_text'] == '人工修正'
    assert by_id['candidate']['action'] == 'fix'
    assert by_id['candidate']['new_text'] == 'High 候选'
    assert by_id['changed']['new_text'] == '新修补'
    assert by_id['extra']['new_text'] == '额外修正'
    assert stats['output_overrides'] == 4
    assert stats['manual_secondary_decisions'] == 1
    print('phase4 override tests: PASS')


if __name__ == '__main__':
    main()
