# -*- coding: utf-8 -*-
"""静态校验 patch/ 产物（Phase 7 的自动化部分）。

检查：
  1. .int 层：编码/可解析/条目数与天邈源一致/键序一致/占位标签完整/
     实际修改 id 集合 == changelog 预期（int: 前缀）
  2. texts.db 层：可解析/条目数与天邈源一致/修改集合 == 预期（upk: 前缀）
  3. 残留英文抽检（提示，不阻断）
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
import parse_int
import parse_textsdb


def verify_int(src_dir, patch_dir):
    """返回 (changed_ids, warnings)。changed_ids 为 'int:file:section:key' 形式的实际修改。"""
    ok, warn = [], []
    src = {}
    for e in parse_int.parse_int_dir(src_dir):
        src.setdefault(e['file'], {})[parse_int.entry_identity(e)] = e
    patch_files = {}
    for e in parse_int.parse_int_dir(patch_dir):
        patch_files.setdefault(e['file'], {})[parse_int.entry_identity(e)] = e

    changed_ids = []
    for fname, keys in src.items():
        if fname not in patch_files:
            warn.append(f'{fname}: 补丁中缺失（未修改文件未打包，属正常）')
            continue
        pk = patch_files[fname]
        if set(keys) != set(pk):
            diff = set(keys) ^ set(pk)
            warn.append(f'{fname}: 键集合不一致 ±{len(diff)} 个')
        for identity, src_entry in keys.items():
            patch_entry = pk.get(identity)
            if src_entry['value'] != (patch_entry or {}).get('value'):
                selector = parse_int.entry_selector(src_entry)
                changed_ids.append(f"int:{fname}:{src_entry['section']}:{selector}")
                if re.findall(r'<[^>]*>', src_entry['value']) != re.findall(r'<[^>]*>', (patch_entry or {}).get('value', '')):
                    warn.append(f"{fname}:{src_entry['section']}:{selector} 占位标签被改动")
        ok.append((fname, len(keys), len(pk)))
    return changed_ids, warn


def verify_textsdb(src_db, patch_db, expected_edits):
    """返回 (src, patch, changed_ids, issues)。changed_ids 为 MD5 key 列表。"""
    src = parse_textsdb.parse_textsdb(src_db)
    patch = parse_textsdb.parse_textsdb(patch_db)
    issues = []
    if set(src) != set(patch):
        issues.append(f'texts.db 键集合不一致: 源 {len(src)} vs 补丁 {len(patch)}')
    changed = [k for k in src if src[k] != patch.get(k)]
    if expected_edits is not None:
        exp = {e[4:] for e in expected_edits if e.startswith('upk:')}
        got = set(changed)
        if exp != got:
            issues.append(f'texts.db 修改集合与预期不一致: 预期 {len(exp)} 实改 {len(got)}, '
                          f'多改 {len(got - exp)} 少改 {len(exp - got)}')
    return src, patch, changed, issues


def residual_english(items, threshold=0.6, min_len=8):
    """抽检：值中 ASCII 字母占比高的条目（可能是漏翻的英文）"""
    hits = []
    for c in items:
        v = c.get('cn') or ''
        if len(v) < min_len:
            continue
        letters = [ch for ch in v if ch.isascii() and ch.isalpha()]
        if letters and len(letters) / len(v) > threshold:
            hits.append((c.get('id'), v))
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src-int', required=True, help='天邈中文 .int 目录')
    ap.add_argument('--src-textsdb', required=True, help='天邈 texts.db')
    ap.add_argument('--patch', default='patch', help='patch 输出目录')
    ap.add_argument('--corpus', default='data/aligned/corpus.jsonl')
    args = ap.parse_args()

    sys.stdout.reconfigure(encoding='utf-8')
    patch_int = os.path.join(args.patch, 'DishonoredGame', 'Localization', 'INT')
    patch_tdb = os.path.join(args.patch, 'Sub_Import', 'texts.db')

    expected_edits = None
    ch_path = os.path.join(args.patch, 'changelog.json')
    if os.path.exists(ch_path):
        ch = json.load(open(ch_path, encoding='utf-8'))
        expected_edits = [c['id'] for c in ch]
        print(f'changelog 预期修改: {len(expected_edits)} 条')

    print('== .int 层 ==')
    changed_int, warn_int = verify_int(args.src_int, patch_int)
    print(f'  实际修改 {len(changed_int)} 条')
    for w in warn_int[:20]:
        print(f'  [警告] {w}')
    if expected_edits is not None:
        exp_int = {e for e in expected_edits if e.startswith('int:')}
        got_int = set(changed_int)
        if exp_int != got_int:
            print(f'  [问题] .int 修改集合与预期不一致: 预期 {len(exp_int)} 实改 {len(got_int)}, '
                  f'多改 {len(got_int - exp_int)} 少改 {len(exp_int - got_int)}')

    print('== texts.db 层 ==')
    src, patch, changed_upk, issues = verify_textsdb(
        args.src_textsdb, patch_tdb, expected_edits)
    print(f'  源 {len(src)} 条, 补丁 {len(patch)} 条, 实际修改 {len(changed_upk)} 条')
    for i in issues[:20]:
        print(f'  [问题] {i}')

    if args.corpus and os.path.exists(args.corpus):
        corpus = [json.loads(l) for l in open(args.corpus, encoding='utf-8')]
        hits = residual_english(corpus)
        print(f'== 残留英文抽检（ASCII 占比>60%，仅提示）==')
        for hid, v in hits[:10]:
            print(f'  {hid}: {v[:60]!r}')
        print(f'  共 {len(hits)} 条潜在残留')

    has_issue = bool(warn_int) or bool(issues)
    print('\n校验完成。' if not has_issue else '\n校验完成（有警告，见上）。')


if __name__ == '__main__':
    main()
