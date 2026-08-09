# -*- coding: utf-8 -*-
import tempfile

import phase3_fandom_research as pfr


def fake_requester(api_url, query, result_limit, timeout):
    if query.casefold() == 'midrow substation':
        return [{
            'pageid': 7,
            'title': 'Kaldwin\'s Bridge' if '/zh/' not in api_url else '考德温大桥',
            'snippet': '<span class="searchmatch">Midrow</span> Substation',
            'wordcount': 100,
            'timestamp': '2026-01-01T00:00:00Z',
        }]
    return []


def fake_page_requester(api_url, pageid, timeout):
    if '/zh/' in api_url:
        return '===中街变电站=== Midrow Substation 控制着大桥的电力。'
    return 'The Midrow Substation controls the bridge power.'


def main():
    variants = pfr.query_variants(
        'Midrow Substation 的世界观所指及既有译名')
    assert 'Midrow Substation' in variants, variants
    ricker = pfr.query_variants(
        "You'll be thankful when Slackjaw's boys slit your ricker")
    assert any(value.casefold() == 'ricker' for value in ricker), ricker

    groups = [{
        'query': 'Midrow Substation 的世界观所指及既有译名',
        'ids': ['midrow-a', 'midrow-b'],
    }, {
        'query': '没有结果的虚构词',
        'ids': ['missing'],
    }]
    with tempfile.TemporaryDirectory() as cache_dir:
        rows = pfr.run(
            groups, cache_dir, requester=fake_requester,
            page_requester=fake_page_requester,
            throttle=0, sleep_fn=lambda _seconds: None)
        assert [row['id'] for row in rows] == [
            'midrow-a', 'midrow-b', 'missing']
        assert rows[0]['status'] == rows[1]['status'] == 'direct_evidence'
        assert 'Midrow Substation' in rows[0]['sources'][0]['page_excerpt']
        assert rows[2]['status'] == 'no_match'

        # 第二次运行必须命中逐查询缓存，不能再调用网络函数。
        def fail_requester(*_args):
            raise AssertionError('不应发起网络请求')

        cached = pfr.research_group(
            groups[0], cache_dir, requester=fail_requester,
            page_requester=fail_requester,
            throttle=0, sleep_fn=lambda _seconds: None)
        assert cached[0]['lookup_stats']['network_calls'] == 0
        assert cached[0]['lookup_stats']['cache_hits'] > 0
        assert cached[0]['lookup_stats']['page_network_calls'] == 0
        assert cached[0]['lookup_stats']['page_cache_hits'] > 0
    print('phase3 fandom research tests: PASS')


if __name__ == '__main__':
    main()
