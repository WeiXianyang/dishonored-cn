# -*- coding: utf-8 -*-
"""冒烟测试：parse_int.py 与 parse_textsdb.py（用构造样例，不碰游戏目录）"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))
import parse_int
import parse_textsdb


def pickle_repr(value_bytes: bytes) -> str:
    """模拟 Python2 pickle 的 S'...' 字符串 repr（可打印 ASCII 字面，其余 \\xHH）"""
    out = []
    for b in value_bytes:
        if b == 0x5C:      # backslash
            out.append('\\\\')
        elif b == 0x27:    # single quote
            out.append("\\'")
        elif 0x20 <= b < 0x7F:
            out.append(chr(b))
        else:
            out.append('\\x%02x' % b)
    return ''.join(out)


def make_textsdb(path, pairs):
    """pairs: [(md5, str)] -> 写 pickle repr 风格文件"""
    with open(path, 'w', encoding='latin1') as f:
        f.write('(dp0\n')
        for i, (md5, val) in enumerate(pairs):
            b = val.encode('utf-16-le')
            f.write("S'%s'\np%d\nS'%s'\np%d\ns" % (md5, 2*i+1, pickle_repr(b), 2*i+2))
            f.write('\n')
        f.write('.')


def test_parse_int(tmp):
    p = os.path.join(tmp, 'Sample_MS.int')
    with open(p, 'wb') as f:
        f.write(b'\xff\xfe')
        f.write('[Sample1]\r\n'.encode('utf-16-le'))
        f.write('m_Name="示例文本"\r\n'.encode('utf-16-le'))
        f.write('[Sample2]\r\n'.encode('utf-16-le'))
        f.write('m_Name="第二段同名键"\r\n'.encode('utf-16-le'))
        f.write('m_InteractText="`GBA_Use` 解锁"\r\n'.encode('utf-16-le'))
    entries = parse_int.parse_int_file(p)
    assert len(entries) == 3, entries
    assert entries[0]['key'] == 'm_Name' and entries[0]['value'] == '示例文本'
    assert entries[0]['section'] == 'Sample1'
    # 同 key 不同 section 是不同条目
    assert entries[1]['section'] == 'Sample2' and entries[1]['value'] == '第二段同名键'
    assert entries[2]['section'] == 'Sample2' and entries[2]['value'] == '`GBA_Use` 解锁'
    print('[OK] parse_int: 3 entries, section 分区/同名键/内嵌标签正确')


def test_textsdb(tmp):
    p = os.path.join(tmp, 'texts.db')
    pairs = [
        ('523835FE72B2FEACD4E461F823894481', '对不起。<XX> 请离开这里。\n'),
        ('B92C278959A4D5408FE3CFE463A82A65', "He said 'hi' and \\ then left"),
        ('1289E82EE4626E155FC8F0D84C80AA56', '界面文本 with 中文混排'),
    ]
    make_textsdb(p, pairs)
    db = parse_textsdb.parse_textsdb(p)
    assert len(db) == 3, db
    assert db['523835FE72B2FEACD4E461F823894481'] == '对不起。<XX> 请离开这里。\n', repr(db)
    assert db['B92C278959A4D5408FE3CFE463A82A65'] == "He said 'hi' and \\ then left"
    assert db['1289E82EE4626E155FC8F0D84C80AA56'] == '界面文本 with 中文混排'
    print('[OK] parse_textsdb: 3 entries, 中文/引号/反斜杠/换行还原正确')


def test_textsdb_real_sample():
    """真实 texts.db 存在时：解析并验证 UTF-16 LE 解码、含 CJK"""
    PATH = r'C:\SteamLibrary\steamapps\common\Dishonored\Sub_Import\texts.db'
    if not os.path.exists(PATH):
        print('[SKIP] parse_textsdb 真实样本（游戏文件不在本机）')
        return
    db = parse_textsdb.parse_textsdb(PATH)
    assert len(db) > 9000, len(db)
    sample = next(iter(db.values()))
    assert any('\u4e00' <= c <= '\u9fff' for c in sample), repr(sample)
    print(f'[OK] parse_textsdb 真实样本: {len(db)} 条，示例: {sample[:50]!r}')


def main():
    tmp = tempfile.mkdtemp(prefix='dh_smoke_')
    test_parse_int(tmp)
    test_textsdb(tmp)
    test_textsdb_real_sample()
    print('\n全部冒烟测试通过 ✓')


if __name__ == '__main__':
    main()
