# -*- coding: utf-8 -*-
"""解析天邈 texts.db —— Python2 pickle repr 格式。

格式样例：
    (dp0
    S'523835FE72B2FEACD4E461F823894481'     <- MD5(英文原串)，大写十六进制
    p1
    S'<UTF-16 LE 字节串的 repr>'             <- 值：中文（UTF-16 LE），repr 用 \\xHH 转义
    p2
    s
    ...

值解析：把 repr 字符串还原为原始字节（\\xHH / \\\\ / \\' / \\n 等转义按字节还原），
再按 UTF-16 LE 解码得到中文字幕。天邈 1.4 的每个值都以一个 ``NUL``
结尾（供注入后的 UE3 FString 使用）；本底层解析器原样保留该终止符，语料构建
阶段再将它拆为 ``cn`` 正文与 ``target_format.nul_terminated``。

命令行用法:
    python parse_textsdb.py texts.db [--out out.json]
"""
import argparse
import json
import re
import sys

# 32位大写 MD5 key + 紧随其后的 S'值'（pickle 可能用单引号或双引号包裹）
# 组: 1=key引号, 2=MD5, 3=值引号, 4=值内容
# 值部分: 非贪婪匹配任意（转义序列 \\X 或 非反斜杠字符），直到真正的结束引号+ pN s
PAIR = re.compile(
    r"S(['\"])([0-9A-F]{32})\1\s*p\d+\s*S(['\"])((?:[^\\]|\\.)*?)\3\s*p\d+\s*s"
)

_ESC = {
    '\\\\': 0x5C, "\\'": 0x27, '\\"': 0x22,
    '\\n': 0x0A, '\\r': 0x0D, '\\t': 0x09,
    '\\a': 0x07, '\\b': 0x08, '\\f': 0x0C, '\\v': 0x0B,
}


def unpack_repr(val_repr):
    """把 pickle 字符串 repr 还原为原始字节串。"""
    out = bytearray()
    i = 0
    n = len(val_repr)
    while i < n:
        c = val_repr[i]
        if c == '\\' and i + 3 < n and val_repr[i + 1] == 'x':
            out.append(int(val_repr[i + 2:i + 4], 16))
            i += 4
        elif c == '\\' and i + 1 < n and val_repr[i:i + 2] in _ESC:
            out.append(_ESC[val_repr[i:i + 2]])
            i += 2
        elif c == '\\' and i + 1 < n and val_repr[i + 1] == '0':
            out.append(0)
            i += 2
        else:
            # pickle repr 中可打印 ASCII 直接显示
            out.append(ord(c))
            i += 1
    return bytes(out)


def parse_textsdb(path):
    """返回 {md5_upper: 中文文本}"""
    text = open(path, 'rb').read().decode('latin1', errors='replace')
    out = {}
    for m in PAIR.finditer(text):
        key = m.group(2)
        raw = unpack_repr(m.group(4))
        try:
            val = raw.decode('utf-16-le')
        except UnicodeDecodeError:
            val = raw.decode('utf-16', errors='replace')
        out[key] = val
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('path', help='texts.db 路径')
    ap.add_argument('--out', help='输出 JSON 路径（缺省打印统计与样例）')
    args = ap.parse_args()

    db = parse_textsdb(args.path)
    sys.stdout.reconfigure(encoding='utf-8')
    if args.out:
        with open(args.out, 'w', encoding='utf-8') as f:
            json.dump(db, f, ensure_ascii=False, indent=1)
        print(f'{len(db)} entries -> {args.out}')
    else:
        print(f'总条数: {len(db)}')
        for i, (k, v) in enumerate(db.items()):
            if i >= 5:
                break
            print(f'  {k}  {v[:60]!r}')


if __name__ == '__main__':
    main()
