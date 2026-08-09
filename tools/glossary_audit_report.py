# -*- coding: utf-8 -*-
"""生成可搜索的术语全量审计 HTML/CSV 报告。"""
from __future__ import annotations

import argparse
import csv
import html
import json
from collections import Counter
from pathlib import Path

import phase3_finalize as pf
import review_pipeline as rp


def read_jsonl(path):
    with open(path, encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def render(entries, results):
    entry_by_id = {row['id']: row for row in entries}
    rows = []
    for item in results:
        entry = entry_by_id[item['id']]
        rows.append({
            'en_term': entry['en_term'], 'current_cn': entry['current_cn'],
            'decision': item['decision'], 'scope': item['scope'],
            'proposed_cn': item['proposed_cn'],
            'confidence': f"{float(item['confidence']):.2f}",
            'occurrences': entry.get('stats', {}).get('occurrences', 0),
            'releases': ', '.join(entry.get('stats', {}).get('releases', {})),
            'reason': item['reason'],
            'risk_tags': ', '.join(item.get('risk_tags', [])),
            'evidence_ids': '\n'.join(item.get('evidence_ids', [])),
        })
    rows.sort(key=lambda row: row['en_term'].casefold())
    counts = Counter(row['decision'] for row in rows)
    cards = ''.join(
        f'<div class="card"><b>{html.escape(label)}</b><span>{value}</span></div>'
        for label, value in [
            ('术语总数', len(rows)), ('保留全局硬锁', counts['keep_global']),
            ('纠正后全局硬锁', counts['correct_global']),
            ('降为作用域候选', counts['restrict_scope']),
            ('移除', counts['remove']),
        ])
    body_rows = []
    for row in rows:
        search = ' '.join(str(value) for value in row.values()).casefold()
        body_rows.append(
            '<tr class="' + html.escape(row['decision']) + '" data-search="' +
            html.escape(search, quote=True) + '">' + ''.join(
                f'<td class="{key}">{html.escape(str(row[key]))}</td>'
                for key in ('en_term', 'current_cn', 'decision', 'scope',
                            'proposed_cn', 'confidence', 'occurrences',
                            'releases', 'reason', 'risk_tags')) + '</tr>')
    document = f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dishonored 天邈 1.4 术语表全量审计</title>
<style>
body{{font:14px/1.55 system-ui,"Microsoft YaHei",sans-serif;margin:24px;background:#f6f7f9;color:#20242a}}
h1{{margin:0 0 8px}} .note{{color:#59636e;max-width:1000px}}
.cards{{display:flex;gap:12px;flex-wrap:wrap;margin:18px 0}} .card{{background:white;border:1px solid #dfe3e8;border-radius:8px;padding:10px 14px;min-width:135px}}
.card b,.card span{{display:block}} .card span{{font-size:24px}}
input{{width:min(620px,95%);padding:10px 12px;border:1px solid #aeb7c2;border-radius:6px;margin-bottom:12px}}
.wrap{{overflow:auto;background:white;border:1px solid #dfe3e8;border-radius:8px}}
table{{border-collapse:collapse;width:100%;min-width:1450px}} th,td{{padding:8px 10px;border-bottom:1px solid #edf0f3;text-align:left;vertical-align:top}}
th{{position:sticky;top:0;background:#eef1f4;z-index:1}} td.reason{{min-width:360px}} td.risk_tags{{min-width:220px}}
tr.correct_global{{background:#fff1e8}} tr.restrict_scope{{background:#fffbea}} tr.remove{{background:#ffecec}}
.legend{{margin:8px 0 14px;color:#59636e}}
</style></head><body>
<h1>Dishonored 天邈 1.4 术语表全量审计</h1>
<p class="note">每一项都由独立 Agent 同时检查英文含义、天邈原译、实际出现语境、DLC 分布、大小写和复合词碰撞。全局硬锁只保留跨语境安全的专名；其余译法仅作为有作用域的参考，直接采用时仍必须经过第二个 Agent。</p>
<div class="cards">{cards}</div>
<input id="q" placeholder="搜索英文、中文、决策、理由或风险……">
<div class="legend">浅橙＝纠错；浅黄＝降级为作用域候选；浅红＝移除。</div>
<div class="wrap"><table><thead><tr>
<th>英文</th><th>原批准译值</th><th>决策</th><th>作用域</th><th>新译值</th><th>置信度</th><th>出现次数</th><th>版本</th><th>理由</th><th>风险</th>
</tr></thead><tbody>{''.join(body_rows)}</tbody></table></div>
<script>const q=document.querySelector('#q');q.addEventListener('input',()=>{{const v=q.value.toLowerCase();document.querySelectorAll('tbody tr').forEach(r=>r.hidden=!r.dataset.search.includes(v))}});</script>
</body></html>'''
    return rows, document


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--audit-corpus',
                        default='data/review/glossary-audit/audit_corpus.jsonl')
    parser.add_argument('--results',
                        default='data/review/glossary-audit/results.jsonl')
    parser.add_argument('--html',
                        default='data/review/glossary-audit/glossary_audit.html')
    parser.add_argument('--csv',
                        default='data/review/glossary-audit/glossary_audit.csv')
    args = parser.parse_args(argv)
    rows, document = render(read_jsonl(args.audit_corpus), read_jsonl(args.results))
    Path(args.html).parent.mkdir(parents=True, exist_ok=True)
    Path(args.html).write_text(document, encoding='utf-8', newline='\n')
    pf.atomic_write_csv(args.csv, list(rows[0]) if rows else [
        'en_term', 'current_cn', 'decision', 'scope', 'proposed_cn',
        'confidence', 'occurrences', 'releases', 'reason', 'risk_tags',
        'evidence_ids'], rows)
    print(json.dumps({
        'rows': len(rows), 'html': str(Path(args.html).resolve()),
        'csv': str(Path(args.csv).resolve()),
        'hashes': {'html': rp.sha256_file(args.html),
                   'csv': rp.sha256_file(args.csv)},
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
