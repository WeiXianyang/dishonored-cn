# -*- coding: utf-8 -*-
"""生成 patch/ 校验哈希清单。"""
import os, hashlib, json

hashes = {}
root = 'patch'
for dirpath, _, files in os.walk(root):
    for f in files:
        p = os.path.join(dirpath, f)
        rel = os.path.relpath(p, root).replace(os.sep, '/')
        hashes[rel] = hashlib.sha256(open(p, 'rb').read()).hexdigest()

json.dump({'generated': 'Phase 5 写回产物', 'entries': hashes},
          open('patch/hashes.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('patch 文件数:', len(hashes))
total = sum(os.path.getsize(os.path.join(root, rel.replace('/', os.sep))) for rel in hashes)
print('patch 总大小:', round(total / 1024 / 1024, 2), 'MB')
for rel in sorted(hashes):
    print(' ', rel, hashes[rel][:12])
