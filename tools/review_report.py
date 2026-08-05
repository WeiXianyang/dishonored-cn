# -*- coding: utf-8 -*-
"""生成人工审核报告（Phase 4）：不确定条目 + AI 修改提案 -> HTML + 裁决 CSV 模板。

用法：
    python tools/review_report.py --reviews data/review --corpus data/aligned/corpus.jsonl
输出：
    data/review/review_report.html   三栏对照审核页
    data/review/decisions.csv        裁决表（用户填写后传给 apply_patch.py --decisions）
"""
import argparse
import csv
import html
import json
import os
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reviews', default='data/review')
    ap.add_argument('--corpus', default='data/aligned/corpus.jsonl')
    ap.add_argument('--all-fixes', action='store_true',
                    help='不只列 uncertain，也列出全部 fix 条目')
    args = ap.parse_args()

    # 读取 review 结果
    items = []
    for fn in sorted(os.listdir(args.reviews)):
        if not fn.startswith('batch_') or not fn.endswith('.json'):
            continue
        data = json.load(open(os.path.join(args.reviews, fn), encoding='utf-8'))
        items.extend(data['items'])

    corpus = {}
    if os.path.exists(args.corpus):
        for line in open(args.corpus, encoding='utf-8'):
            c = json.loads(line)
            corpus[c['id']] = c

    # 筛出需要人工看的：uncertain 优先，可选全部 fix
    todo = [r for r in items if r.get('uncertain')]
    if args.all_fixes:
        seen = {r['id'] for r in todo}
        todo += [r for r in items if r['action'] == 'fix' and r['id'] not in seen]
    todo.sort(key=lambda r: r['id'])

    sys.stdout.reconfigure(encoding='utf-8')
    rows = []
    for r in todo:
        src = corpus.get(r['id'], {})
        rows.append({
            'id': r['id'],
            'context': ' | '.join(f'{k}={v}' for k, v in src.get('context', {}).items() if v),
            'en': src.get('en', ''),
            'cn_old': src.get('cn', ''),
            'cn_new': r.get('new_text', '') if r['action'] == 'fix' else '（保持原样）',
            'reason': r.get('reason', ''),
            'uncertain': '⚠' if r.get('uncertain') else '',
            'ureason': r.get('uncertain_reason', ''),
        })

    # HTML
    trs = []
    for r in rows:
        def esc(x):
            return html.escape(str(x))
        uncertain_mark = ''
        if r['uncertain']:
            uncertain_mark = f'<br><b>⚠ 待定</b> {esc(r["ureason"])}'
        trs.append(
            f'<tr><td class="id">{esc(r["id"])}<br><span class="ctx">{esc(r["context"])}</span></td>'
            f'<td>{esc(r["en"])}</td>'
            f'<td class="old">{esc(r["cn_old"])}</td>'
            f'<td class="new">{esc(r["cn_new"])}<br><span class="rs">{esc(r["reason"])}</span>'
            f'{uncertain_mark}</td></tr>'
        )
    h = f"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>人工审核报告（{len(rows)} 条）</title>
<style>
body{{font-family:system-ui,sans-serif;margin:24px;background:#f7f7f7}}
table{{border-collapse:collapse;width:100%;background:#fff}}
th,td{{border:1px solid #ccc;padding:8px;vertical-align:top;text-align:left;font-size:13px}}
th{{background:#333;color:#fff}}
.id{{width:200px;word-break:break-all}}.ctx{{color:#888;font-size:11px}}
.old{{color:#a33}}.new{{color:#2a6}} .rs{{color:#888;font-size:11px}}
h1{{font-size:18px}}
</style></head><body>
<h1>人工审核报告 — 共 {len(rows)} 条待裁决（uncertain 优先）</h1>
<p>对照英文原文，在天邈译文与 AI 建议之间裁决。裁决后填写 <code>data/review/decisions.csv</code>，运行 <code>tools/apply_patch.py --decisions data/review/decisions.csv</code>。</p>
<table><tr><th>id / 上下文</th><th>英文原文</th><th>天邈译文（现）</th><th>AI 建议</th></tr>
{''.join(trs)}
</table></body></html>"""
    out_html = os.path.join(args.reviews, 'review_report.html')
    with open(out_html, 'w', encoding='utf-8') as f:
        f.write(h)
    print(f'审核报告 -> {out_html}（{len(rows)} 条）')

    # decisions.csv 模板
    out_csv = os.path.join(args.reviews, 'decisions.csv')
    with open(out_csv, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['id', 'action', 'new_text', 'note'])
        for r in rows:
            w.writerow([r['id'], 'keep', '', ''])
    print(f'裁决模板 -> {out_csv}')


if __name__ == '__main__':
    main()
