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
    """{file: {(section, key): (value, line)}}（同文件同 section 同 key 取最后一行）"""
    out = {}
    for e in parse_int.parse_int_dir(directory):
        out.setdefault(e['file'], {})[(e['section'], e['key'])] = (e['value'], e['line'])
    return out


def load_dis_context(path):
    """dis.db: 对话树路径 -> {叶子名: MD5}；展开为 {MD5: 对话树路径}"""
    import re
    if not path:
        return {}
    text = open(path, 'rb').read().decode('latin1', errors='replace')
    ctx = {}
    # 结构: S'<路径>' pN (dpM S'<叶名>' pX S'<MD5>' pY s ...)
    path_re = re.compile(r"S'([^']+)'\s*p\d+\s*\(dp")
    leaf_re = re.compile(r"S'([^']+)'\s*p\d+\s*S'([0-9A-F]{32})'\s*p\d+\s*s")
    for m in path_re.finditer(text):
        seg = text[m.end():m.end() + 200000]
        for lm in leaf_re.finditer(seg):
            ctx[lm.group(2)] = f"{m.group(1)}.{lm.group(1)}"
    return ctx


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
    for fname, keys in cn_map.items():
        en_keys = en_map.get(fname, {})
        for (section, key), (cn_val, line) in keys.items():
            en_val = en_keys.get((section, key), ('', 0))[0]
            if en_val:
                status = 'aligned'
            else:
                status = 'cn_only'
            corpus.append({
                'id': f'int:{fname}:{section}:{key}',
                'layer': 'int',
                'context': {'file': fname, 'section': section, 'key': key, 'line': line},
                'en': en_val,
                'cn': cn_val,
                'tags': extract_tags(cn_val),
                'status': status,
            })
    # 英文有而中文没有的键（可能漏译）
    for fname, keys in en_map.items():
        cn_keys = cn_map.get(fname, {})
        for (section, key), (en_val, line) in keys.items():
            if (section, key) not in cn_keys:
                corpus.append({
                    'id': f'int:{fname}:{section}:{key}',
                    'layer': 'int',
                    'context': {'file': fname, 'section': section, 'key': key, 'line': line},
                    'en': en_val,
                    'cn': '',
                    'tags': extract_tags(en_val),
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
