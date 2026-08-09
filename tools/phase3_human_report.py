# -*- coding: utf-8 -*-
"""把 Phase 3 最终人工清单渲染为可离线查看的 HTML 对照表。"""
import argparse
import html
import json
from pathlib import Path

import review_pipeline as rp


def read_jsonl(path):
    with open(path, encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def esc(value):
    return html.escape(str(value or ''))


def text_block(value):
    return esc(value).replace('\r\n', '\n').replace('\r', '\n').replace('\n', '<br>')


def render_report(rows, summary=None, title='Dishonored Phase 3 人工审核'):
    table_rows = []
    for index, row in enumerate(rows, 1):
        context = json.dumps(row.get('context', {}), ensure_ascii=False, indent=1)
        research = row.get('research_context', {}) or {}
        wiki = research.get('wiki_research', []) or []
        neighbors = research.get('local_neighbors', []) or []
        curated = research.get('curated_web_evidence', []) or []
        scene = research.get('scene_dialogue', []) or []
        game = row.get('game_context') or research.get('game_context') or {}
        evidence_parts = []
        if curated:
            evidence_parts.append(
                '<h4>定向网络核查</h4><pre>' + esc(json.dumps(
                    curated, ensure_ascii=False, indent=2)) + '</pre>')
        if wiki:
            evidence_parts.append(
                '<h4>Wiki 核查</h4><pre>' + esc(json.dumps(
                    wiki, ensure_ascii=False, indent=2)) + '</pre>')
        if neighbors:
            evidence_parts.append(
                '<h4>本地上下文</h4><pre>' + esc(json.dumps(
                    neighbors, ensure_ascii=False, indent=2)) + '</pre>')
        if scene:
            evidence_parts.append(
                '<h4>同场景对白</h4><pre>' + esc(json.dumps(
                    scene, ensure_ascii=False, indent=2)) + '</pre>')
        evidence = ''.join(evidence_parts) or '<span class="muted">无附加证据</span>'
        history = {
            'medium': row.get('medium'),
            'high': row.get('high'),
        }
        game_card = (f'''<div class="game"><b>{esc(game.get('release'))}</b><br>
任务：{esc(game.get('mission'))}<br>地点：{esc(game.get('location'))}<br>
触发：{esc(game.get('trigger'))}<br><span class="limit">仍缺：{esc(game.get('remaining_context_limit'))}</span></div>'''
                     if game else '<span class="muted">未生成结构化场景定位</span>')
        table_rows.append(f'''<tr>
<td class="num">{index}</td>
<td class="identity"><code>{esc(row.get('id'))}</code><br><span class="route">{esc(row.get('route'))}</span>{game_card}<details><summary>技术定位</summary><pre>{esc(context)}</pre><pre>{esc(json.dumps(game.get('technical_locator', {}), ensure_ascii=False, indent=2))}</pre></details></td>
<td>{text_block(row.get('en'))}</td>
<td class="old">{text_block(row.get('original_cn'))}</td>
<td class="candidate">{text_block(row.get('candidate_cn'))}</td>
<td><b>{text_block(row.get('uncertain_reason'))}</b><br><span class="muted">{text_block(row.get('reason'))}</span><details><summary>证据</summary>{evidence}</details><details><summary>Medium / High 历史</summary><pre>{esc(json.dumps(history, ensure_ascii=False, indent=2))}</pre></details></td>
</tr>''')
    summary = summary or {}
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}（{len(rows)} 条）</title>
<style>
body{{font-family:system-ui,"Microsoft YaHei",sans-serif;margin:20px;background:#f5f5f3;color:#222}}
h1{{font-size:22px}} .meta{{background:#fff;border:1px solid #ccc;padding:12px;margin-bottom:16px}}
table{{border-collapse:collapse;width:100%;background:#fff;table-layout:fixed}}
th,td{{border:1px solid #c9c9c9;padding:8px;vertical-align:top;font-size:13px;overflow-wrap:anywhere}}
th{{background:#252525;color:#fff;position:sticky;top:0}} .num{{width:34px}} .identity{{width:230px}}
.old{{background:#fff4f2}} .candidate{{background:#f0fff4}} .route{{color:#785600}} .muted{{color:#666}}
.game{{margin-top:8px;padding:7px;background:#eef5ff;border-left:3px solid #4f78a8;line-height:1.55}} .limit{{color:#713b00}}
pre{{white-space:pre-wrap;font-size:11px;background:#f4f4f4;padding:6px;max-height:280px;overflow:auto}}
details{{margin-top:7px}} code{{font-size:11px}}
</style></head><body>
<h1>{esc(title)}</h1>
<div class="meta"><b>待裁决：{len(rows)} 条</b><br>
原则：只有 Wiki、本地上下文和 High 仍无法裁决的条目才会出现在此。
请在同目录 <code>human_review.csv</code> 的 <code>decision</code>、<code>decided_text</code>、<code>note</code> 列填写裁决。<br>
总结：<code>{esc(json.dumps(summary, ensure_ascii=False))}</code></div>
<table><thead><tr><th>#</th><th>ID / 路由</th><th>英文</th><th>天邈原译</th><th>当前候选</th><th>疑点 / 证据</th></tr></thead>
<tbody>{''.join(table_rows)}</tbody></table></body></html>'''


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--human-review', required=True)
    parser.add_argument('--summary')
    parser.add_argument('--out', required=True)
    parser.add_argument('--title', default='Dishonored Phase 3 人工审核')
    args = parser.parse_args(argv)
    rows = read_jsonl(args.human_review)
    summary = (json.loads(Path(args.summary).read_text(encoding='utf-8'))
               if args.summary else {})
    rendered = render_report(rows, summary, args.title)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(rendered, encoding='utf-8', newline='\n')
    print(json.dumps({
        'status': 'pass', 'rows': len(rows), 'out': str(out.resolve()),
        'sha256': rp.sha256_file(str(out)),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
