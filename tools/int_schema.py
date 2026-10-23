# -*- coding: utf-8 -*-
"""解析 UE3 本地化 ``.int`` 文件，并保留可安全写回的条目身份。

Dishonored 的 INT 文件不只有 ``key="value"``：核心 UI、能力说明和
DLC 统计还大量使用 ``key=value`` 与
``key=(m_Name="...",m_Description="...")``。本模块把三种格式统一展开为
可对齐的文本条目，同时记录赋值/字段出现序号，以免重复 key 或结构体内的
重复字段互相覆盖。

命令行用法::

    python parse_int.py <file.int>
    python parse_int.py <dir> --out out.json
"""
import argparse
import json
import os
import re
import sys

SECTION = re.compile(r'^\[(.+)\]$')
ASSIGNMENT = re.compile(r'^\s*([^\s=]+)\s*=\s*(.*)$', re.S)
STRUCT_FIELD = re.compile(r'([A-Za-z0-9_.\[\]-]+)\s*=\s*"')


def decode_int_bytes(data):
    """返回 ``(text_without_bom, format_name)``。"""
    if data.startswith(b'\xff\xfe'):
        return data[2:].decode('utf-16-le'), 'utf-16-le-bom'
    if data.startswith(b'\xfe\xff'):
        return data[2:].decode('utf-16-be'), 'utf-16-be-bom'
    if data.startswith(b'\xef\xbb\xbf'):
        return data[3:].decode('utf-8'), 'utf-8-bom'
    return data.decode('utf-8', errors='replace'), 'utf-8'


def encode_int_text(text, format_name):
    """按 :func:`decode_int_bytes` 返回的格式编码，保留原 BOM 约定。"""
    if format_name == 'utf-16-le-bom':
        return b'\xff\xfe' + text.encode('utf-16-le')
    if format_name == 'utf-16-be-bom':
        return b'\xfe\xff' + text.encode('utf-16-be')
    if format_name == 'utf-8-bom':
        return b'\xef\xbb\xbf' + text.encode('utf-8')
    return text.encode('utf-8')


def _closing_quote(rhs, start):
    """找结构体字段字符串的结束引号。

    UE3 数据中既有 ``\\"``，也偶有未转义的英文引号。只有后面紧跟
    ``,``、``)`` 或字符串结尾的引号才视为结构字段边界。
    """
    i = start
    while i < len(rhs):
        if rhs[i] == '\\':
            i += 2
            continue
        if rhs[i] == '"':
            j = i + 1
            while j < len(rhs) and rhs[j].isspace():
                j += 1
            if j == len(rhs) or rhs[j] in ',)':
                return i
        i += 1
    return None


def parse_assignment_line(line):
    """解析单行赋值。

    返回 ``(base_key, values)``；``values`` 的每项含 ``value/style/subkey``
    以及值在原行中的 ``start/end`` 字符偏移。非赋值行返回 ``None``。
    """
    m = ASSIGNMENT.match(line)
    if not m:
        return None
    key = m.group(1)
    raw_rhs = m.group(2)
    rhs = raw_rhs.rstrip()
    rhs_start = m.start(2)

    # 外层引号包裹的普通文本。内部未转义引号仍属于文本本身；取首尾即可。
    if len(rhs) >= 2 and rhs.startswith('"') and rhs.endswith('"'):
        return key, [{
            'value': rhs[1:-1],
            'style': 'quoted',
            'subkey': '',
            'field_occurrence': 0,
            'start': rhs_start + 1,
            'end': rhs_start + len(rhs) - 1,
        }]

    # 结构体赋值：每个命名字符串字段独立成为一条可审校文本。
    fields = []
    field_seen = {}
    pos = 0
    while True:
        fm = STRUCT_FIELD.search(rhs, pos)
        if not fm:
            break
        value_start = fm.end()
        value_end = _closing_quote(rhs, value_start)
        if value_end is None:
            break
        field = fm.group(1)
        occurrence = field_seen.get(field, 0)
        field_seen[field] = occurrence + 1
        fields.append({
            'value': rhs[value_start:value_end],
            'style': 'struct_field',
            'subkey': field,
            'field_occurrence': occurrence,
            'start': rhs_start + value_start,
            'end': rhs_start + value_end,
        })
        pos = value_end + 1
    if fields:
        return key, fields

    # 无外层引号的普通本地化值（RPG.int、Settings.int 等）。
    return key, [{
        'value': rhs,
        'style': 'unquoted',
        'subkey': '',
        'field_occurrence': 0,
        'start': rhs_start,
        'end': rhs_start + len(rhs),
    }]


def entry_identity(entry):
    """用于中英对齐/写回的无歧义身份元组。"""
    return (
        entry.get('section', ''),
        entry.get('key', ''),
        int(entry.get('assignment_occurrence', 0)),
        entry.get('subkey', ''),
        int(entry.get('field_occurrence', 0)),
    )


def context_identity(context):
    """从 corpus context 还原 :func:`entry_identity`。"""
    return entry_identity(context)


def entry_selector(entry):
    """生成适合稳定 ID 的单文件条目选择器。"""
    selector = entry.get('key', '')
    assignment_occurrence = int(entry.get('assignment_occurrence', 0))
    if assignment_occurrence:
        selector += f'#{assignment_occurrence}'
    subkey = entry.get('subkey', '')
    if subkey:
        selector += f'::{subkey}'
        field_occurrence = int(entry.get('field_occurrence', 0))
        if field_occurrence:
            selector += f'#{field_occurrence}'
    return selector


def parse_int_text(text, file_name):
    """解析已解码文本，返回条目列表。"""
    entries = []
    section = ''
    assignment_seen = {}
    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        sm = SECTION.match(stripped)
        if sm:
            section = sm.group(1).strip()
            continue
        parsed = parse_assignment_line(line)
        if not parsed:
            continue
        key, values = parsed
        seen_key = (section, key)
        assignment_occurrence = assignment_seen.get(seen_key, 0)
        assignment_seen[seen_key] = assignment_occurrence + 1
        for value in values:
            entries.append({
                'file': file_name.replace('\\', '/'),
                'section': section,
                'key': key,
                'assignment_occurrence': assignment_occurrence,
                'subkey': value['subkey'],
                'field_occurrence': value['field_occurrence'],
                'style': value['style'],
                'value': value['value'],
                'line': lineno,
            })
    return entries


def parse_int_file(path, root=None):
    """解析单个 INT；提供 ``root`` 时 ``file`` 保存相对路径。"""
    data = open(path, 'rb').read()
    text, _format_name = decode_int_bytes(data)
    file_name = os.path.relpath(path, root) if root else os.path.basename(path)
    return parse_int_text(text, file_name)


def parse_int_dir(root):
    out = []
    for dirpath, dirs, files in os.walk(root):
        dirs.sort()
        for fn in sorted(files):
            if fn.lower().endswith('.int'):
                out.extend(parse_int_file(os.path.join(dirpath, fn), root=root))
    return out


def replace_int_text(text, edits):
    """按 identity→new_text 替换已解码 INT，返回 ``(text, changed, unused)``。"""
    remaining = dict(edits)
    changed = 0
    section = ''
    assignment_seen = {}
    out_lines = []
    for line in text.splitlines(keepends=True):
        content = line.rstrip('\r\n')
        eol = line[len(content):]
        stripped = content.strip()
        sm = SECTION.match(stripped)
        if sm:
            section = sm.group(1).strip()
            out_lines.append(line)
            continue
        parsed = parse_assignment_line(content)
        if not parsed:
            out_lines.append(line)
            continue
        key, values = parsed
        seen_key = (section, key)
        assignment_occurrence = assignment_seen.get(seen_key, 0)
        assignment_seen[seen_key] = assignment_occurrence + 1
        replacements = []
        for value in values:
            ident = (
                section, key, assignment_occurrence,
                value['subkey'], value['field_occurrence'],
            )
            if ident in remaining:
                replacements.append((value['start'], value['end'], remaining.pop(ident)))
        for start, end, new_text in sorted(replacements, reverse=True):
            if content[start:end] != new_text:
                content = content[:start] + new_text + content[end:]
                changed += 1
        out_lines.append(content + eol)
    return ''.join(out_lines), changed, remaining


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
        for entry in entries:
            selector = entry_selector(entry)
            print(f"{entry['file']}:{entry['line']}  {selector} = {entry['value'][:80]!r}")


if __name__ == '__main__':
    main()
