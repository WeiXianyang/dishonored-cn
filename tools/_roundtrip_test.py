# -*- coding: utf-8 -*-
"""真实 texts.db 全量往返验证：0 修改重建后与原文件字节级一致"""
import hashlib
import os
import pickle
import sys

sys.path.insert(0, 'tools')
import parse_textsdb
from apply_patch import apply_textsdb, pickle_str_repr

SRC = r'C:\SteamLibrary\steamapps\common\Dishonored\Sub_Import\texts.db'
if not os.path.exists(SRC):
    print('[SKIP] 游戏 texts.db 不在本机')
    sys.exit(0)

orig = open(SRC, 'rb').read()
print(f'原文件: {len(orig)} bytes, md5={hashlib.md5(orig).hexdigest()}')

# 0 修改重建
apply_textsdb(SRC, {}, '_roundtrip')
out = open('_roundtrip/Sub_Import/texts.db', 'rb').read()
print(f'重建文件: {len(out)} bytes, md5={hashlib.md5(out).hexdigest()}')

if orig == out:
    print('✓ 字节级完全一致（0 修改时输出 == 输入）')
else:
    # 找第一处差异
    n = min(len(orig), len(out))
    for i in range(n):
        if orig[i] != out[i]:
            print(f'✗ 首处差异 @ {i}: 原={orig[max(0,i-30):i+30]!r}')
            print(f'                重建={out[max(0,i-30):i+30]!r}')
            break
    else:
        print(f'✗ 长度不同: 原 {len(orig)} vs 重建 {len(out)}')

# Python3 pickle 兼容性（encoding=bytes）
with open('_roundtrip/Sub_Import/texts.db', 'rb') as f:
    d = pickle.load(f, encoding='bytes')
print(f'✓ pickle.load: {len(d)} 条（expect 10284）')

# 与 parse_textsdb 交叉验证
p1 = parse_textsdb.parse_textsdb(SRC)
p2 = parse_textsdb.parse_textsdb('_roundtrip/Sub_Import/texts.db')
diff_keys = [k for k in p1 if p1[k] != p2.get(k)]
print(f'✓ parse 交叉: 源 {len(p1)} 条 vs 重建 {len(p2)} 条, 值差异 {len(diff_keys)} 条')
