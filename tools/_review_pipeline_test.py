# -*- coding: utf-8 -*-
"""Phase 0.6 离线测试：不访问游戏目录、不调用真实模型。"""
import json
import os
import shutil
import sys
import tempfile
import threading

sys.path.insert(0, os.path.dirname(__file__))
import review_pipeline as rp


def sample_batch():
    return [
        {
            'id': 'int:Sample.int:Section:m_Tip',
            'layer': 'int',
            'context': {'file': 'Sample.int', 'section': 'Section', 'key': 'm_Tip'},
            'en': 'Press `GBA_Use` to speak to Corvo.\nNow.',
            'cn': '按 `GBA_Use` 与科尔沃交谈。\n现在。',
            'tags': [],
            'status': 'aligned',
        },
        {
            'id': 'upk:11111111111111111111111111111111',
            'layer': 'upk',
            'context': {'dialog_path': 'dlg_test.corvo.line_1'},
            'en': 'The door is locked.',
            'cn': '门锁上了。',
            'tags': [],
            'status': 'aligned',
        },
    ]


def response_json(second_reason='无'):
    return json.dumps({'items': [
        {
            'id': 'int:Sample.int:Section:m_Tip',
            'action': 'keep',
            'new_text': '',
            'reason': '无',
            'confidence': 0.99,
            'uncertain': False,
            'uncertain_reason': '',
        },
        {
            'id': 'upk:11111111111111111111111111111111',
            'action': 'keep',
            'new_text': '',
            'reason': second_reason,
            'confidence': 0.95,
            'uncertain': False,
            'uncertain_reason': '',
        },
    ]}, ensure_ascii=False)


def settings():
    return {
        'backend': 'codex',
        'model': 'test-model',
        'reasoning_effort': 'medium',
        'schema_path': rp.DEFAULT_SCHEMA,
        'timeout': 10,
        'codex_command': 'codex',
    }


def test_contract():
    batch = sample_batch()
    ids = [entry['id'] for entry in batch]
    parsed = rp.parse_response(response_json(), ids)
    assert len(parsed) == 2
    assert parsed[0]['confidence'] == 0.99

    duplicate = json.loads(response_json())
    duplicate['items'][1]['id'] = duplicate['items'][0]['id']
    try:
        rp.parse_response(json.dumps(duplicate, ensure_ascii=False), ids)
    except ValueError as exc:
        assert '重复 id' in str(exc)
    else:
        raise AssertionError('重复 id 未被拒绝')

    invalid = json.loads(response_json())
    invalid['items'][0]['confidence'] = 1.5
    try:
        rp.parse_response(json.dumps(invalid, ensure_ascii=False), ids)
    except ValueError as exc:
        assert 'confidence' in str(exc)
    else:
        raise AssertionError('非法 confidence 未被拒绝')
    print('[OK] 严格 JSON/id/字段契约')


def test_placeholder_and_terms():
    item = {
        'action': 'fix',
        '_old': '按 `GBA_Use` 与科尔沃交谈。\n现在。',
        'new_text': '按 `GBA_Use` 和科尔沃交谈。\n现在。',
    }
    assert rp.check_placeholders(item)
    term_entry = {'en': 'Speak with Corvo', 'cn': item['_old']}
    assert rp.check_terms(
        item, {'Corvo': '科尔沃'}, term_entry) is None
    item['new_text'] = '与主角交谈。现在。'
    assert not rp.check_placeholders(item)
    assert '科尔沃' in rp.check_terms(
        item, {'Corvo': '科尔沃'}, term_entry)

    # 中文术语值也可能只是普通词；英文未命中对应术语时
    # 不得因“帮助”或“城市警卫”的表面命中而阻止正常顺句。
    ordinary = {
        'id': 'upk:ordinary', 'en': 'Once I helped Nina establish the business.',
        'cn': '一旦我帮助妮娜建立起生意。',
    }
    ordinary_fix = {
        'id': 'upk:ordinary', 'action': 'fix',
        'new_text': '帮妮娜把生意安顿好后。',
    }
    assert rp.check_terms(
        ordinary_fix, {'Favor': '帮助'}, ordinary) is None
    officer = {
        'id': 'upk:officer', 'en': 'a lowly watch officer',
        'cn': '一个低阶城市警卫官',
    }
    officer_fix = {
        'id': 'upk:officer', 'action': 'fix',
        'new_text': '一个卑微的警卫官',
    }
    assert rp.check_terms(officer_fix, {
        'City Guard': '城市警卫', 'City Watch': '城市警卫',
        'Watch Officer': '警卫官',
    }, officer) is None

    nested = {
        'id': 'int:nested', 'en': 'Blood Ox Heart', 'cn': '血牛之心',
    }
    nested_terms = {'Blood Ox Heart': '血牛之心', 'Heart': '心脏'}
    assert rp.required_term_pairs(nested, nested_terms) == [
        ('Blood Ox Heart', '血牛之心')]
    assert rp.check_terms({
        'id': 'int:nested', 'action': 'keep', 'new_text': '',
    }, nested_terms, nested) is None
    separate = dict(nested, en='Blood Ox Heart and Heart')
    assert rp.required_term_pairs(separate, nested_terms) == [
        ('Blood Ox Heart', '血牛之心'), ('Heart', '心脏')]

    safe_room = {
        'id': 'int:safe-room', 'en': "Regent's Safe Room",
        'cn': '摄政王的安全屋',
    }
    safe_room_terms = {
        "Regent's Safe": '摄政王的保险箱',
        "Regent's Safe Room": '摄政王的安全屋',
    }
    assert rp.required_term_pairs(safe_room, safe_room_terms) == [
        ("Regent's Safe Room", '摄政王的安全屋')]
    assert rp.check_terms({
        'id': 'int:safe-room', 'action': 'fix',
        'new_text': '摄政王的保险箱室',
    }, safe_room_terms, safe_room) is not None

    # 因直接术语应用而升级的条目，二审必须把术语当作
    # 待核实候选，而不是继续当作无法推翻的硬约束。
    scoped = {
        'id': 'upk:scoped', 'layer': 'upk',
        'context': {'references': []},
        'en': "some assassin's blade",
        'cn': '某个刺客的刺客之刃', 'status': 'aligned',
        'escalation': {'reasons': ['term_direct_application']},
        'term_review': {
            'mode': 'agent_secondary_review',
            'candidates': [{
                'en': "Assassin's Blade", 'cn': '刺客之刃',
                'old_contains_approved': False,
                'candidate_contains_approved': True,
            }],
        },
    }
    modeled = rp.model_entries(
        [scoped], {"Assassin's Blade": '刺客之刃'})[0]
    assert modeled['required_terms'] == []
    assert modeled['term_candidates'] == scoped['term_review']['candidates']
    reviewed = [{
        'id': 'upk:scoped', 'action': 'fix',
        'new_text': '某个刺客的刀', 'reason': '普通所有格短语',
        'confidence': 0.99, 'uncertain': False, 'uncertain_reason': '',
    }]
    assert rp.validate_hard_rules(
        reviewed, [scoped], {"Assassin's Blade": '刺客之刃'})[0][
            'new_text'] == '某个刺客的刀'

    # 受限作用域术语只能作为参考候选：独立物品标签可提示，普通句子
    # 中的子串不得重新变成可直接套用的标签译名。
    advisory = [{
        'id': 'term:safe', 'en_term': "Regent's Safe",
        'cn_term': '摄政王的保险箱', 'scope': 'label_only',
        'confidence': 0.99, 'reason': '仅独立保险箱标签成立',
        'evidence_ids': ['safe-label'], 'risk_tags': ['substring_collision'],
    }]
    safe_label = {
        'id': 'safe-label', 'layer': 'int', 'status': 'aligned',
        'context': {'subkey': 'm_targetname'},
        'en': "Regent's Safe", 'cn': '摄政王的保险箱',
    }
    safe_sentence = {
        'id': 'safe-room', 'layer': 'upk', 'status': 'aligned',
        'context': {'references': []},
        'en': "Reach the Regent's safe room", 'cn': '到达摄政王的安全屋',
    }
    label_model = rp.model_entries([safe_label], {}, advisory)[0]
    sentence_model = rp.model_entries([safe_sentence], {}, advisory)[0]
    assert label_model['required_terms'] == []
    assert label_model['term_candidates'][0]['cn'] == '摄政王的保险箱'
    assert 'term_candidates' not in sentence_model

    normalized = {
        'id': 'int:ui', 'layer': 'int',
        'context': {'file': 'UI.int', 'section': 'HUD', 'key': 'm_Tip'},
        'en': 'Hold `GBA_Block` near Corvo',
        'cn': '按住 `GBA_block` 靠近主角', 'status': 'aligned_normalized',
    }
    corrected = {
        'id': 'int:ui', 'action': 'fix',
        'new_text': '在科尔沃附近按住 `GBA_Block`', 'reason': '修复',
        'confidence': 0.99, 'uncertain': False, 'uncertain_reason': '',
    }
    checked = rp.validate_hard_rules(
        [corrected], [normalized], {'Corvo': '科尔沃'})
    assert checked[0]['new_text'].endswith('`GBA_Block`')
    keep = dict(corrected, action='keep', new_text='')
    try:
        rp.validate_hard_rules([keep], [normalized], {'Corvo': '科尔沃'})
    except ValueError as exc:
        assert '英文命中术语' in str(exc)
    else:
        raise AssertionError('源文命中术语而旧译缺失时不得 keep')

    missing = dict(normalized, id='int:missing', en='Missing text', cn='',
                   status='en_only')
    missing_keep = dict(corrected, id='int:missing', action='keep', new_text='')
    try:
        rp.validate_hard_rules([missing_keep], [missing], {})
    except ValueError as exc:
        assert 'en_only' in str(exc)
    else:
        raise AssertionError('非空 en_only 必须生成补译')

    variables = {
        'id': 'int:variables', 'en': 'Kill §Victim§ with $Weapon$.',
        'cn': '使用$Weapon$杀死§Victim§。', 'status': 'aligned',
    }
    reordered = {
        'id': 'int:variables', 'action': 'fix',
        'new_text': '杀死§Victim§，使用$Weapon$。',
    }
    assert rp.check_placeholders(reordered, variables)
    missing_variable = dict(reordered, action='keep', new_text='')
    variables['cn'] = '杀死目标。'
    assert not rp.check_placeholders(missing_variable, variables)

    runtime = {
        'id': 'int:runtime', 'en': 'You need `k needed',
        'cn': '需要 `k', 'status': 'aligned',
    }
    assert rp.check_placeholders({
        'id': 'int:runtime', 'action': 'fix', 'new_text': '仍需要 `k',
    }, runtime)
    corrupt_target = {
        'id': 'int:corrupt', 'en': 'Key Required',
        'cn': '需要`k ', 'status': 'aligned',
    }
    assert rp.check_placeholders({
        'id': 'int:corrupt', 'action': 'fix', 'new_text': '需要钥匙',
    }, corrupt_target)
    assert not rp.check_placeholders({
        'id': 'int:corrupt', 'action': 'keep', 'new_text': '',
    }, corrupt_target)

    case_terms = {
        'Favor': '帮助', 'Heart': '心脏', 'Dunwall Tower': '丹沃尔塔'}
    lower_common = {'en': "I'm not in favor of it.", 'cn': '我不赞成。'}
    assert rp.required_term_pairs(lower_common, case_terms) == []
    assert rp.required_term_pairs(
        lower_common, case_terms, case_sensitive_single_terms=False
    ) == [('Favor', '帮助')]
    assert rp.required_term_pairs(
        {'en': 'Favor and Heart', 'cn': ''}, case_terms
    ) == [('Favor', '帮助'), ('Heart', '心脏')]
    assert rp.required_term_pairs(
        {'en': 'Return to dunwall tower', 'cn': ''}, case_terms
    ) == [('Dunwall Tower', '丹沃尔塔')]
    print('[OK] 占位符/换行/术语硬校验')


def test_batch_grouping_and_context():
    corpus = [
        {
            'id': 'int:a1', 'layer': 'int',
            'context': {'file': 'A.int', 'section': 'S', 'key': 'K1'},
            'domain': {'release': 'base_game'}, 'en': 'A', 'cn': '甲',
            'status': 'aligned',
        },
        {
            'id': 'int:b1', 'layer': 'int',
            'context': {'file': 'B.int', 'section': 'S', 'key': 'K1'},
            'domain': {'release': 'base_game'}, 'en': 'B', 'cn': '乙',
            'status': 'aligned',
        },
        {
            'id': 'upk:1', 'layer': 'upk',
            'context': {'references': [{
                'release': 'base_game', 'upk': 'l_pub_script',
                'dialog_path': 'dlg:test:disconversation_1',
                'object': 'Line_1', 'kind': 'subtitle'}]},
            'domain': {'primary_release': 'base_game'},
            'en': 'Hello Corvo', 'cn': '你好，科尔沃', 'status': 'aligned',
        },
    ]
    batches = rp.build_batches(corpus, 1)
    assert [[item['id'] for item in batch] for batch in batches] == [
        ['int:a1'], ['int:b1'], ['upk:1']]
    entries = rp.model_entries(batches[-1], {'Corvo': '科尔沃'})
    assert 'l_pub_script' in entries[0]['context']
    assert entries[0]['required_terms'] == [{'en': 'Corvo', 'cn': '科尔沃'}]
    assert 'references' not in entries[0]['context'] or \
        len(entries[0]['context']) < 1000

    enriched = dict(batches[-1][0])
    enriched.update({
        'prior_review': {'medium_action': 'fix'},
        'escalation': {'reasons': ['medium_uncertain']},
        'research_context': {'wiki_research': {'status': 'resolved'}},
    })
    modeled = rp.model_entries([enriched], {'Corvo': '科尔沃'})[0]
    assert modeled['prior_review']['medium_action'] == 'fix'
    assert modeled['escalation']['reasons'] == ['medium_uncertain']
    assert modeled['research_context']['wiki_research']['status'] == 'resolved'

    # 大分组的尾数必须继续填入后续分组，不得单独浪费一批。
    packed = []
    for index in range(41):
        packed.append({
            'id': f'int:a{index}', 'layer': 'int',
            'context': {'file': 'A.int', 'section': 'S', 'key': str(index)},
            'en': str(index), 'cn': str(index), 'status': 'aligned',
        })
    packed.append({
        'id': 'int:b0', 'layer': 'int',
        'context': {'file': 'B.int', 'section': 'S', 'key': '0'},
        'en': 'b', 'cn': 'b', 'status': 'aligned',
    })
    packed_batches = rp.build_batches(packed, 40)
    assert [len(batch) for batch in packed_batches] == [40, 2]
    assert packed_batches[1][-1]['id'] == 'int:b0'
    char_limited = rp.build_batches(packed[:3], 40, max_batch_chars=1)
    assert [len(batch) for batch in char_limited] == [1, 1, 1]
    print('[OK] INT/UPK 真实语境分组与紧凑输入')


def test_retry_classification():
    assert not rp.is_retryable_error(
        "The 'gpt-5.6' model is not supported when using Codex with a ChatGPT account.")
    assert not rp.is_retryable_error(
        "The 'gpt-5.6-sol' model requires a newer version of Codex.")
    assert not rp.is_retryable_error('找不到 Codex CLI: codex')
    assert not rp.is_retryable_error(
        "You've hit your usage limit. Try again at Aug 8th, 2026 12:14 PM.")
    assert rp.is_retryable_error('HTTP 429: rate limit exceeded')
    assert rp.is_retryable_error('temporary connection reset')
    print('[OK] 永久错误与临时错误分类')


def test_wiki_lookup_queue():
    corpus = sample_batch()
    uncertain = [{
        'id': corpus[0]['id'],
        'action': 'keep',
        'new_text': '',
        'confidence': 0.61,
        'uncertain_reason': '[WIKI_LOOKUP: Corvo identity] 需要确认人物身份。',
    }, {
        'id': corpus[1]['id'],
        'action': 'keep',
        'new_text': '',
        'confidence': 0.7,
        'uncertain_reason': '需要更多语境。',
    }]
    queue = rp.build_wiki_lookup_items(uncertain, corpus)
    assert len(queue) == 2
    assert queue[0]['suggested_wiki_query'] == 'Corvo identity'
    assert queue[0]['en'] == corpus[0]['en']
    assert queue[0]['research_status'] == 'pending'
    assert queue[1]['suggested_wiki_query'] == corpus[1]['en']
    print('[OK] 不确定项先进入 Dishonored Wiki 查证队列')


def test_api_backend_contract():
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({
                'choices': [{'message': {'content': response_json()}}],
                'usage': {'prompt_tokens': 12, 'completion_tokens': 4},
            }).encode('utf-8')

    original = rp.urllib.request.urlopen

    def fake_urlopen(request, timeout):
        captured['body'] = json.loads(request.data.decode('utf-8'))
        captured['timeout'] = timeout
        return FakeResponse()

    rp.urllib.request.urlopen = fake_urlopen
    try:
        content, meta = rp.call_api('system', 'user', {
            'api_base': 'https://example.invalid/v1',
            'api_key': 'secret-for-test',
            'model': 'test-api-model',
            'temperature': 0.2,
            'max_tokens': 100,
            'timeout': 9,
        })
    finally:
        rp.urllib.request.urlopen = original

    assert json.loads(content)['items']
    assert captured['body']['model'] == 'test-api-model'
    assert captured['body']['response_format'] == {'type': 'json_object'}
    assert captured['timeout'] == 9
    assert meta['usage']['prompt_tokens'] == 12
    print('[OK] OpenAI 兼容 API 备用后端契约')


def test_atomic_cache_and_stale(tmp):
    batch = sample_batch()
    calls = []

    def caller(_system, _user, _settings):
        calls.append('called')
        return response_json(), {'usage': {'input_tokens': 10, 'output_tokens': 5}}

    first = rp.review_batch(
        batch, 'system', '{terms}\n{entries}', {'Corvo': '科尔沃'}, 0,
        tmp, settings(), 'config-a', caller=caller, max_retries=1,
        sleep_fn=lambda _seconds: None)
    assert first and not first['cached'] and len(calls) == 1
    result_path = os.path.join(tmp, 'batch_0000.json')
    assert os.path.exists(result_path)
    assert os.path.exists(os.path.join(tmp, 'requests', 'batch_0000.json'))

    def must_not_run(*_args):
        raise AssertionError('有效缓存不应再次调用模型')

    cached = rp.review_batch(
        batch, 'system', '{terms}\n{entries}', {'Corvo': '科尔沃'}, 0,
        tmp, settings(), 'config-a', caller=must_not_run, max_retries=1,
        sleep_fn=lambda _seconds: None)
    assert cached and cached['cached']

    refreshed = rp.review_batch(
        batch, 'system', '{terms}\n{entries}', {'Corvo': '科尔沃'}, 0,
        tmp, settings(), 'config-b', caller=caller, max_retries=1,
        sleep_fn=lambda _seconds: None)
    assert refreshed and not refreshed['cached'] and len(calls) == 2
    stale = [name for name in os.listdir(tmp) if '.stale-' in name]
    assert stale, os.listdir(tmp)
    print('[OK] 原子落盘/缓存复验/配置过期归档')


def test_hard_failure(tmp):
    batch = sample_batch()
    bad = json.loads(response_json())
    bad['items'][0].update({
        'action': 'fix',
        'new_text': '和主角交谈。现在。',
        'reason': '错误模拟',
        'confidence': 0.9,
    })

    def caller(_system, _user, _settings):
        return json.dumps(bad, ensure_ascii=False), {}

    outcome = rp.review_batch(
        batch, 'system', '{terms}\n{entries}', {'Corvo': '科尔沃'}, 1,
        tmp, settings(), 'config-a', caller=caller, max_retries=1,
        sleep_fn=lambda _seconds: None)
    assert outcome is None
    assert not os.path.exists(os.path.join(tmp, 'batch_0001.json'))
    assert os.path.exists(os.path.join(tmp, 'failures', 'batch_0001.json'))
    print('[OK] 硬校验失败不落完成态')


def test_retry_feedback(tmp):
    batch = sample_batch()
    prompts = []
    bad = json.loads(response_json())
    bad['items'][0].update({
        'action': 'fix', 'new_text': '遗漏按键和换行。',
        'reason': '第一次错误', 'confidence': 0.9,
    })

    def caller(_system, user, _settings):
        prompts.append(user)
        content = (json.dumps(bad, ensure_ascii=False)
                   if len(prompts) == 1 else response_json())
        return content, {'usage': {'input_tokens': 1}}

    retry_dir = os.path.join(tmp, 'retry')
    outcome = rp.review_batch(
        batch, 'system', '{terms}\n{entries}', {'Corvo': '科尔沃'}, 2,
        retry_dir, settings(), 'config-retry', caller=caller,
        max_retries=2, sleep_fn=lambda _seconds: None)
    assert outcome is not None and not outcome['cached']
    assert outcome['meta']['attempts'] == 2
    assert len(outcome['meta']['retry_errors']) == 1
    assert 'retry_feedback' not in prompts[0]
    assert '上一版输出未通过确定性校验' in prompts[1]
    assert '占位符/换行不一致' in prompts[1]
    print('[OK] 校验错误反馈给下一次完整批次重试')


def test_terminal_error_stops_run(tmp):
    calls = []
    stop_event = threading.Event()

    def caller(_system, _user, _settings):
        calls.append(1)
        raise RuntimeError(
            "You've hit your usage limit. Try again at Aug 8th, 2026 12:14 PM.")

    outcome = rp.review_batch(
        sample_batch(), 'system', '{terms}\n{entries}', {}, 3,
        os.path.join(tmp, 'usage-limit'), settings(), 'config-limit',
        caller=caller, max_retries=3, sleep_fn=lambda _seconds: None,
        stop_event=stop_event)
    assert outcome is None
    assert len(calls) == 1
    assert stop_event.is_set()
    print('[OK] 额度用尽立即终止并发批次')


def main():
    tmp = tempfile.mkdtemp(prefix='dh_review_pipeline_test_')
    try:
        test_contract()
        test_placeholder_and_terms()
        test_batch_grouping_and_context()
        test_retry_classification()
        test_wiki_lookup_queue()
        test_api_backend_contract()
        test_atomic_cache_and_stale(tmp)
        test_hard_failure(tmp)
        test_retry_feedback(tmp)
        test_terminal_error_stops_run(tmp)
        print('\nPhase 0.6 离线测试全部通过 ✓')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    main()
