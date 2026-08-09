# -*- coding: utf-8 -*-
import phase3_human_report as phr


def main():
    rows = [{
        'id': 'upk:<test>', 'route': 'human_after_high',
        'context': {'file': 'A&B'}, 'en': 'A < B\nnext',
        'original_cn': '旧译', 'candidate_cn': '新译',
        'reason': '理由', 'uncertain_reason': '疑点',
        'research_context': {
            'wiki_research': [{'finding': '证据'}],
            'local_neighbors': [{'en': 'near'}],
        },
        'medium': {'action': 'fix'}, 'high': {'uncertain': True},
    }]
    rendered = phr.render_report(rows, {'accepted_fixes': 10})
    assert 'upk:&lt;test&gt;' in rendered
    assert 'A &lt; B<br>next' in rendered
    assert 'Wiki 核查' in rendered and '本地上下文' in rendered
    assert '待裁决：1 条' in rendered
    print('phase3 human report tests: PASS')


if __name__ == '__main__':
    main()
