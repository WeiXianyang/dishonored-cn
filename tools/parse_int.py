# -*- coding: utf-8 -*-
"""解析 UE3 本地化 .int 文件（UTF-16 LE + BOM）。

格式：每行形如  key="value"（键名通常保留英文原名，值已被汉化）。
命令行用法:
    python parse_int.py <file.int>            # 打印条目
    python parse_int.py <dir> --out out.json  # 递归解析整个目录
"""
import argparse
import json
import os
import re
import sys

KEY_VALUE = re.compile(r'^([A-Za-z0-9_.]+)\s*=\s*"(.*)"\s*$', re.S)
SECTION = re.compile(r'^\[(.+)\]$')


def parse_int_file(path):
    """返回 [{file, section, key, value, line}]

    .int 为 UE3 本地化格式：`[对象名 类名]` section 头 + `key="value"` 行。
    同名 key 可出现在不同 section（不同游戏对象），因此 key 必须与 section
    组合才唯一。section 为空串表示文件内未显式分区。"""
    base = os.path.basename(path)
    data = open(path, 'rb').read()
    # 兼容 UTF-16 LE/BE 与 UTF-8（UE3 标准为 UTF-16 LE，部分文件为 UTF-8 无 BOM）
    if data[:2] in (b'\xff\xfe', b'\xfe\xff'):
        text = data.decode('utf-16')
    else:
        text = data.decode('utf-8-sig', errors='replace')
    entries = []
    section = ''
    for lineno, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        m = SECTION.match(line)
        if m:
            section = m.group(1).strip()
            continue
        m = KEY_VALUE.match(line)
        if m:
            entries.append({
                'file': base,
                'section': section,
                'key': m.group(1),
                'value': m.group(2),
                'line': lineno,
            })
    return entries


def parse_int_dir(root):
    out = []
    for dirpath, _dirs, files in os.walk(root):
        for fn in sorted(files):
            if fn.lower().endswith('.int'):
                out.extend(parse_int_file(os.path.join(dirpath, fn)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path', help='.int 文件或目录')
    ap.add_argument('--out', help='输出 JSON 路径（缺省打印到 stdout）')
    args = ap.parse_args()

    if os.path.isdir(args.path):
        entries = parse_int_dir(args.path)
    else:
        entries = parse_int_file(args.path)

    sys.stdout.reconfigure(encoding='utf-8')
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            json.dump(entries, f, ensure_ascii=False, indent=1)
        print(f'{len(entries)} entries -> {args.out}')
    else:
        for e in entries:
            print(f"{e['file']}:{e['line']}  {e['key']} = {e['value'][:80]!r}")


if __name__ == '__main__':
    main()
