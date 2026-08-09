# -*- coding: utf-8 -*-
"""对齐建库：把英文源与天邈中文合并为逐条对照语料 corpus.jsonl。

输入（命令行参数）：
    --en-int-dir   英文 .int 目录（Steam 校验还原后）
    --cn-int-dir   天邈中文 .int 目录（当前游戏 / 备份）
    --en-textsdb   英文 texts.db（从英文 upk 提取，可选）
    --cn-textsdb   天邈中文 texts.db（Sub_Import/texts.db）
    --dis-db       天邈 dis.db（对话树路径→哈希，提供说话人上下文）
    --out          输出 corpus.jsonl

对齐方式：
    int 层：按 (文件名, key) 对齐
    upk 层：texts.db 的 key 是 MD5(英文原串)，中英天然按 key 对齐；
            dis.db 提供 对话树路径（含说话人/关卡） 作为上下文。

输出 JSONL 每行：
    {"id", "layer": "int|upk", "context": {...}, "en", "cn",
     "tags": ["<XX/>"], "status": "aligned|en_only|cn_only"}
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import parse_int
import parse_textsdb


def load_int_map(directory):
    """{file: {完整条目身份: entry}}；重复 key/结构字段不会互相覆盖。"""
    out = {}
    for e in parse_int.parse_int_dir(directory):
        identity = parse_int.entry_identity(e)
        if identity in out.setdefault(e['file'], {}):
            raise ValueError(f"重复 INT identity: {e['file']} {identity}")
        out[e['file']][identity] = e
    return out

def load_dis_context(path):
    """dis.db 展开为 ``{MD5: 主 UPK/对话树/对象路径}``。

    使用真实 pickle 结构，兼容标量字幕与玩家选择列表；旧正则方案会漏掉
    153 个选择项哈希，并可能跨顶层对象误绑定上下文。
    """
    if not path:
        return {}
    from extract_upk_texts import load_dis_index
    _expected, contexts, _stats = load_dis_index(path)
    return {
        digest: (
            f"{refs[0]['upk']}:{refs[0]['dialog_path']}.{refs[0]['object']}"
            + (f"[{refs[0]['choice_index']}]"
               if refs[0]['choice_index'] is not None else ''))
        for digest, refs in contexts.items()
    }


def extract_tags(s):
    """提取 <XX.../> 之类的占位标签，用于校验修改时不破坏它们"""
    import re
    return re.findall(r'<[^>]*>', s)


def build(en_int, cn_int, en_tdb, cn_tdb, dis_db):
    import re
    corpus = []

    # ---- int 层 ----
    en_map = load_int_map(en_int)
    cn_map = load_int_map(cn_int)
    for fname, entries in cn_map.items():
        en_keys = en_map.get(fname, {})
        for identity, cn_entry in entries.items():
            en_entry = en_keys.get(identity)
            en_val = en_entry['value'] if en_entry else ''
            cn_val = cn_entry['value']
            if en_val:
                status = 'aligned'
            else:
                status = 'cn_only'
            selector = parse_int.entry_selector(cn_entry)
            corpus.append({
                'id': f"int:{fname}:{cn_entry['section']}:{selector}",
                'layer': 'int',
                'context': {
                    'file': fname,
                    'section': cn_entry['section'],
                    'key': cn_entry['key'],
                    'assignment_occurrence': cn_entry['assignment_occurrence'],
                    'subkey': cn_entry['subkey'],
                    'field_occurrence': cn_entry['field_occurrence'],
                    'style': cn_entry['style'],
                    'line': cn_entry['line'],
                },
                'en': en_val,
                'cn': cn_val,
                'tags': extract_tags(cn_val),
                'status': status,
            })
    # 英文有而中文没有的键（可能漏译）
    for fname, entries in en_map.items():
        cn_keys = cn_map.get(fname, {})
        for identity, en_entry in entries.items():
            if identity not in cn_keys:
                selector = parse_int.entry_selector(en_entry)
                corpus.append({
                    'id': f"int:{fname}:{en_entry['section']}:{selector}",
                    'layer': 'int',
                    'context': {
                        'file': fname,
                        'section': en_entry['section'],
                        'key': en_entry['key'],
                        'assignment_occurrence': en_entry['assignment_occurrence'],
                        'subkey': en_entry['subkey'],
                        'field_occurrence': en_entry['field_occurrence'],
                        'style': en_entry['style'],
                        'line': en_entry['line'],
                    },
                    'en': en_entry['value'],
                    'cn': '',
                    'tags': extract_tags(en_entry['value']),
                    'status': 'en_only',
                })

    # ---- upk 层 ----
    ctx = load_dis_context(dis_db)
    cn_db = parse_textsdb.parse_textsdb(cn_tdb) if cn_tdb else {}
    en_db = parse_textsdb.parse_textsdb(en_tdb) if en_tdb else {}
    for md5, cn_val in cn_db.items():
        corpus.append({
            'id': f'upk:{md5}',
            'layer': 'upk',
            'context': {'dialog_path': ctx.get(md5, '')},
            'en': en_db.get(md5, ''),
            'cn': cn_val,
            'tags': extract_tags(cn_val),
            'status': 'aligned' if md5 in en_db else 'cn_only',
        })
    for md5, en_val in en_db.items():
        if md5 not in cn_db:
            corpus.append({
                'id': f'upk:{md5}',
                'layer': 'upk',
                'context': {'dialog_path': ctx.get(md5, '')},
                'en': en_val,
                'cn': '',
                'tags': extract_tags(en_val),
                'status': 'en_only',
            })
    return corpus


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--en-int-dir', required=True)
    ap.add_argument('--cn-int-dir', required=True)
    ap.add_argument('--en-textsdb')
    ap.add_argument('--cn-textsdb')
    ap.add_argument('--dis-db')
    ap.add_argument('--out', default='data/aligned/corpus.jsonl')
    args = ap.parse_args()

    corpus = build(args.en_int_dir, args.cn_int_dir,
                   args.en_textsdb, args.cn_textsdb, args.dis_db)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        for c in corpus:
            f.write(json.dumps(c, ensure_ascii=False) + '\n')

    sys.stdout.reconfigure(encoding='utf-8')
    from collections import Counter
    cnt = Counter(c['layer'] for c in corpus)
    st = Counter(c['status'] for c in corpus)
    print(f'总条数: {len(corpus)}')
    print(f'  分层: {dict(cnt)}')
    print(f'  状态: {dict(st)}')
    print(f'输出 -> {args.out}')


if __name__ == '__main__':
    main()
