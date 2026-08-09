# -*- coding: utf-8 -*-
import phase4_finalize as p4


def main():
    final = [
        {'id': 'voice', 'action': 'keep', 'new_text': '', 'uncertain': True,
         'route': 'human_after_high'},
        {'id': 'cn', 'action': 'keep', 'new_text': '', 'uncertain': True,
         'route': 'human_unpaired_cn_only'},
    ]
    accepted = []
    human = [
        {'id': 'voice', 'route': 'human_after_high', 'candidate_cn': '哈哈'},
        {'id': 'cn', 'route': 'human_unpaired_cn_only', 'candidate_cn': '钥匙'},
    ]
    enriched = [
        {'id': 'voice', 'candidate_cn': '哈哈',
         'game_context': {'mission': '欢愉之家'},
         'research_context': {'scene_dialogue': []}},
        {'id': 'cn', 'candidate_cn': '钥匙', 'game_context': {},
         'research_context': {}},
    ]
    model = [{
        'id': 'voice', 'action': 'keep', 'new_text': '', 'reason': '缺音频',
        'confidence': 0.5, 'uncertain': True,
        'uncertain_reason': '笑声或喊声取决于音频',
    }]
    output, fixes, remaining = p4.finalize_stage(
        final, accepted, human, enriched, model,
        resolutions={'cn': {'reason': 'Wiki 已确认'}})
    by_id = {row['id']: row for row in output}
    assert by_id['cn']['route'] == 'phase4_wiki_keep_cn_only'
    assert not by_id['cn']['uncertain']
    assert by_id['voice']['uncertain_reason'] == '笑声或喊声取决于音频'
    assert remaining[0]['game_context']['mission'] == '欢愉之家'
    assert not fixes
    print('phase4 finalization tests: PASS')


if __name__ == '__main__':
    main()
