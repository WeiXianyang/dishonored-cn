# -*- coding: utf-8 -*-
"""合并生成：把 review 修改提案应用到天邈中文源，产出 patch/ 目录。

输入：
    --reviews   data/review/*.json 目录（自动合并所有 batch_*.json）
    --decisions 人工裁决 CSV（可选，覆盖 AI 结果；格式见 docs/review.md）
    --cn-int    天邈中文 .int 目录
    --cn-textsdb 天邈 texts.db
    --out       输出目录（默认 patch/）

输出（保持原格式最小 diff）：
    patch/DishonoredGame/Localization/INT/*.int    UTF-16 LE + BOM + CRLF，键序不变
    patch/Sub_Import/texts.db                       pickle0 格式，值仅改动被修条目
    patch/changelog.json                            修改清单（id/en/cn/new/reason）
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import parse_int
import parse_textsdb

# ---------- 读取 review 结果 ----------

def load_reviews(reviews_dir):
    """合并所有 batch_*.json 与 decisions.csv -> {id: result}"""
    out = {}
    for fn in sorted(os.listdir(reviews_dir)):
        if not fn.startswith('batch_') or not fn.endswith('.json'):
            continue
        data = json.load(open(os.path.join(reviews_dir, fn), encoding='utf-8'))
        for item in data['items']:
            out[item['id']] = item
    return out


def load_decisions(path):
    """人工裁决 CSV：id,action,new_text,note（可选）"""
    out = {}
    if not path or not os.path.exists(path):
        return out
    import csv
    with open(path, encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            rid = row.get('id')
            if rid:
                out[rid] = {
                    'id': rid,
                    'action': row.get('action', 'keep'),
                    'new_text': row.get('new_text', ''),
                    'reason': '人工裁决: ' + row.get('note', ''),
                }
    return out


# ---------- .int 写回 ----------

def apply_int(src_dir, decisions, out_root, corpus_by_id=None):
    """按完整 INT identity 替换值；保留源编码、BOM、换行和其余字节。"""
    out_dir = os.path.join(out_root, 'DishonoredGame', 'Localization', 'INT')
    os.makedirs(out_dir, exist_ok=True)
    corpus_by_id = corpus_by_id or {}
    # 按文件收集修改: {file: {identity: new_text}}
    by_file = {}
    for rid, res in decisions.items():
        if not rid.startswith('int:') or res['action'] != 'fix' or not res.get('new_text'):
            continue
        c = corpus_by_id.get(rid)
        if not c:
            print(f'  [跳过] corpus 无此条目: {rid}')
            continue
        ctx = c.get('context', {})
        fname = ctx.get('file') or ''
        if not fname:
            print(f'  [跳过] corpus 条目无 file 上下文: {rid}')
            continue
        identity = parse_int.context_identity(ctx)
        by_file.setdefault(fname.replace('\\', '/'), {})[identity] = res['new_text']

    changed_files = 0
    changed_entries = 0
    src_abs = os.path.abspath(src_dir)
    for rel_name, edits in sorted(by_file.items()):
        path = os.path.abspath(os.path.join(src_abs, *rel_name.split('/')))
        if os.path.commonpath([src_abs, path]) != src_abs:
            raise ValueError(f'INT 相对路径越界: {rel_name}')
        if not os.path.isfile(path):
            print(f'  [跳过] INT 源文件不存在: {rel_name}')
            continue
        raw = open(path, 'rb').read()
        text, format_name = parse_int.decode_int_bytes(raw)
        rewritten, changed, unused = parse_int.replace_int_text(text, edits)
        if unused:
            for identity in sorted(unused):
                print(f'  [跳过] INT 条目未定位: {rel_name} {identity}')
        if not changed:
            continue
        out_path = os.path.join(out_dir, *rel_name.split('/'))
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, 'wb') as f:
            f.write(parse_int.encode_int_text(rewritten, format_name))
        changed_files += 1
        changed_entries += changed
    return changed_files, changed_entries


# ---------- texts.db 写回 ----------

def pickle_str_repr(value_bytes: bytes) -> str:
    """生成与 Python2 pickle 兼容的 S'...' 字符串 repr。"""
    def esc(b):
        if b == 0x5C:
            return '\\\\'
        if b == 0x27:      # 单引号
            return "\\'"
        if b == 0x0A:
            return '\\n'
        if b == 0x0D:
            return '\\r'
        if b == 0x09:
            return '\\t'
        if 0x20 <= b < 0x7F:
            return chr(b)
        return '\\x%02x' % b

    s = ''.join(esc(b) for b in value_bytes)
    return "S'%s'" % s


def apply_textsdb(src_db, decisions, out_root):
    """按 MD5 key 替换值；保持原文件字节格式（s 后无换行），
    未修改条目原样复制原始字节段（最小 diff）。"""
    import parse_textsdb as ptd
    text = open(src_db, 'rb').read().decode('latin1', errors='replace')
    # 每条原始段结构: S'KEY'\npA\nS'VAL'\npB\ns（s 后紧跟下一条 S 或 .，无换行）
    segments = []  # (key, seg_text)
    for m in ptd.PAIR.finditer(text):
        segments.append((m.group(2), m.group(0)))

    source_values = ptd.parse_textsdb(src_db)
    edits = {}
    for rid, res in decisions.items():
        if rid.startswith('upk:') and res['action'] == 'fix' and res.get('new_text'):
            # 天邈 texts.db 的 10,284 个值都包含供 UE3 FString 使用的末尾 NUL。
            # 语料/模型侧不暴露这个控制字符，写回时由工具统一补上。
            key = rid[4:]
            new_text = res['new_text'].rstrip('\x00')
            if source_values.get(key, '').endswith('\x00'):
                new_text += '\x00'
            edits[key] = new_text

    parts = ['(dp0']
    for key, seg in segments:
        if key in edits:
            new_repr = pickle_str_repr(edits[key].encode('utf-16-le'))
            # 替换原段第 3 行（S'值' 行），保留 KEY 行与 pN 行
            lines = seg.split('\n')
            assert len(lines) == 5 and lines[0].startswith("S'") and lines[4] == 's', seg
            lines[2] = new_repr
            seg = '\n'.join(lines)
        parts.append(seg)
    parts.append('.')

    out_path = os.path.join(out_root, 'Sub_Import', 'texts.db')
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'wb') as f:
        f.write(('\n'.join([parts[0]]) + '\n' + ''.join(parts[1:])).encode('latin1'))
    return len(edits)


# ---------- 变更清单 ----------

def build_changelog(decisions, corpus_by_id):
    changes = []
    for rid, res in sorted(decisions.items()):
        if res['action'] != 'fix':
            continue
        src = corpus_by_id.get(rid, {})
        old_text = src.get('cn', '')
        new_text = res.get('new_text', '')
        # Phase 4.5 反方二审回退时 new_text=original_cn，与语料库 cn 相同；
        # 实际未改变文本的条目不应进入 changelog
        if old_text == new_text:
            continue
        changes.append({
            'id': rid,
            'context': src.get('context', {}),
            'en': src.get('en', ''),
            'old': old_text,
            'new': new_text,
            'reason': res.get('reason', ''),
            'source': res.get('source', 'ai'),
        })
    return changes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reviews', default='data/review')
    ap.add_argument('--decisions')
    ap.add_argument('--cn-int', required=True, help='天邈中文 .int 目录')
    ap.add_argument('--cn-textsdb', required=True, help='天邈 texts.db')
    ap.add_argument('--corpus', default='data/aligned/corpus.jsonl')
    ap.add_argument('--out', default='patch')
    args = ap.parse_args()

    reviews = load_reviews(args.reviews)
    decisions = load_decisions(args.decisions)
    # 人工裁决优先，其余用 AI 结果
    merged = dict(reviews)
    merged.update(decisions)
    fixes = [r for r in merged.values() if r['action'] == 'fix']
    print(f'review 结果: {len(reviews)} 条, 人工裁决: {len(decisions)} 条, 共修改: {len(fixes)} 条')

    corpus_by_id = {}
    if os.path.exists(args.corpus):
        corpus_by_id = {json.loads(l)['id']: json.loads(l)
                        for l in open(args.corpus, encoding='utf-8')}

    nf, ne = apply_int(args.cn_int, merged, args.out, corpus_by_id)
    print(f'.int 写回: {nf} 个文件, {ne} 条修改')

    nt = apply_textsdb(args.cn_textsdb, merged, args.out)
    print(f'texts.db 写回: {nt} 条修改')

    changes = build_changelog(merged, corpus_by_id)
    ch_path = os.path.join(args.out, 'changelog.json')
    with open(ch_path, 'w', encoding='utf-8') as f:
        json.dump(changes, f, ensure_ascii=False, indent=1)
    print(f'变更清单 -> {ch_path} ({len(changes)} 条)')


if __name__ == '__main__':
    main()
