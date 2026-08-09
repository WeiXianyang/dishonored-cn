# -*- coding: utf-8 -*-
import phase4_prepare as p4


def main():
    int_entry = {
        'id': 'int:test', 'layer': 'int', 'domain': {'release': 'brigmore_witches'},
        'context': {'file': 'DLC07_DWSewer_Objectives.int',
                    'section': 'Task DishonoredTask', 'key': 'm_Description',
                    'line': 10},
    }
    ctx = p4.build_game_context(int_entry)
    assert ctx['release'] == 'DLC：布里格莫尔女巫'
    assert '死亡鳗帮' in ctx['mission']
    assert '任务目标' in ctx['trigger']

    upk_entry = {
        'id': 'upk:ABC', 'layer': 'upk',
        'domain': {'releases': ['base_game']},
        'context': {'references': [{
            'upk': 'startup', 'release': 'base_game',
            'dialog_path': 'dlg_heartgadget.dlg_heartgadget',
            'object': 'DisConv_Blurb_1', 'kind': 'subtitle'}]},
    }
    ctx = p4.build_game_context(upk_entry)
    assert ctx['trigger_kind'] == 'heart_comment'
    assert '心脏' in ctx['trigger']
    assert '多章节' in ctx['mission']

    shared = {
        'id': 'upk:DEF', 'layer': 'upk',
        'domain': {'releases': ['knife_of_dunwall']},
        'context': {'references': [{
            'upk': 'dlc06_timsh_estate_patrol',
            'release': 'knife_of_dunwall',
            'dialog_path': 'dlg_guard.dialogtree.dlg_guard_shared:disconversation_1',
            'object': 'DisConv_Blurb_1', 'kind': 'subtitle'}]},
    }
    ctx = p4.build_game_context(shared)
    assert ctx['trigger_kind'] == 'shared_ai_bark'
    assert '征用权' in ctx['mission']

    reused = {
        'id': 'upk:GHI', 'layer': 'upk',
        'domain': {'releases': ['base_game']},
        'context': {'references': [
            {'upk': 'l_artdealer_scripts', 'release': 'base_game',
             'dialog_path': 'dlg_guard_shared:disconversation_1'},
            {'upk': 'l_dlc05_arena_scripts', 'release': 'dunwall_city_trials',
             'dialog_path': 'dlg_guard_shared:disconversation_1'},
            {'upk': 'l_artdealer_scripts', 'release': 'base_game',
             'dialog_path': 'dlg_guard_shared:disconversation_1'},
        ]},
    }
    ctx = p4.build_game_context(reused)
    assert ctx['asset_mappings'][0]['asset'] == 'l_artdealer_scripts'
    assert '欢愉之家' in ctx['asset_mappings'][0]['mission']
    assert ctx['asset_mappings'][1]['asset'] == 'l_dlc05_arena_scripts'
    assert '后巷混战' in ctx['asset_mappings'][1]['mission']
    assert ctx['asset_mappings'][2] == ctx['asset_mappings'][0]
    print('phase4 prepare tests: PASS')


if __name__ == '__main__':
    main()
