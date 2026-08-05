# -*- coding: utf-8 -*-
"""端到端冒烟测试：构造迷你中英文数据 -> apply_patch -> verify -> review_report"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))
import parse_int
import parse_textsdb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def pickle_repr(value_bytes: bytes) -> str:
    out = []
    for b in value_bytes:
        if b == 0x5C:
            out.append('\\\\')
        elif b == 0x27:
            out.append("\\'")
        elif 0x20 <= b < 0x7F:
            out.append(chr(b))
        else:
            out.append('\\x%02x' % b)
    return ''.join(out)


def make_int(path, section, pairs):
    with open(path, 'wb') as f:
        f.write(b'\xff\xfe')
        f.write(f'[{section}]\r\n'.encode('utf-16-le'))
        for k, v in pairs:
            f.write(f'{k}="{v}"\r\n'.encode('utf-16-le'))


def make_textsdb(path, pairs):
    # 注意：必须用二进制模式写（Windows 文本模式会把 \n 变 \r\n，破坏 pickle 格式）
    with open(path, 'wb') as f:
        f.write(b'(dp0\n')
        for i, (md5, val) in enumerate(pairs):
            b = val.encode('utf-16-le')
            f.write(("S'%s'\np%d\nS'%s'\np%d\ns" % (md5, 2*i+1, pickle_repr(b), 2*i+2)).encode('latin1'))
        f.write(b'.')


def run(script, *args):
    r = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', script), *args],
                       capture_output=True, text=True, encoding='utf-8')
    print('$', script, *args)
    print(r.stdout.strip())
    if r.returncode != 0:
        print('STDERR:', r.stderr[-2000:])
        raise SystemExit(f'{script} 失败 rc={r.returncode}')
    return r.stdout


def main():
    tmp = tempfile.mkdtemp(prefix='dh_e2e_')
    # ---- 构造天邈中文源 ----
    cn_int = os.path.join(tmp, 'cn', 'INT')
    os.makedirs(cn_int)
    make_int(os.path.join(cn_int, 'A_MS.int'), 'SecA', [
        ('m_Name', '示例文本'),
        ('m_Tip', '按 `GBA_Use` 使用'),
        ('m_Unchanged', '这行不改'),
    ])
    make_int(os.path.join(cn_int, 'B_MS.int'), 'SecB', [
        ('m_Desc', '旧翻译有错误的内容'),
    ])
    cn_tdb = os.path.join(tmp, 'cn', 'texts.db')
    make_textsdb(cn_tdb, [
        ('11111111111111111111111111111111', '第一句字幕 旧翻译'),
        ('22222222222222222222222222222222', '第二句字幕 保持'),
    ])

    # ---- corpus（含 en/cn 对照）----
    corpus = os.path.join(tmp, 'corpus.jsonl')
    with open(corpus, 'w', encoding='utf-8') as f:
        rows = [
            {'id': 'int:A_MS.int:SecA:m_Name', 'layer': 'int', 'context': {'file': 'A_MS.int', 'section': 'SecA', 'key': 'm_Name'},
             'en': 'Sample text', 'cn': '示例文本', 'tags': [], 'status': 'aligned'},
            {'id': 'int:A_MS.int:SecA:m_Tip', 'layer': 'int', 'context': {'file': 'A_MS.int', 'section': 'SecA', 'key': 'm_Tip'},
             'en': 'Press `GBA_Use` to use', 'cn': '按 `GBA_Use` 使用', 'tags': [], 'status': 'aligned'},
            {'id': 'int:A_MS.int:SecA:m_Unchanged', 'layer': 'int', 'context': {'file': 'A_MS.int', 'section': 'SecA', 'key': 'm_Unchanged'},
             'en': 'This stays', 'cn': '这行不改', 'tags': [], 'status': 'aligned'},
            {'id': 'int:B_MS.int:SecB:m_Desc', 'layer': 'int', 'context': {'file': 'B_MS.int', 'section': 'SecB', 'key': 'm_Desc'},
             'en': 'The content had wrong translation', 'cn': '旧翻译有错误的内容', 'tags': [], 'status': 'aligned'},
            {'id': 'upk:11111111111111111111111111111111', 'layer': 'upk', 'context': {'dialog_path': 'dlg_test.piero.DisConv_1'},
             'en': 'First subtitle old translation', 'cn': '第一句字幕 旧翻译', 'tags': [], 'status': 'aligned'},
            {'id': 'upk:22222222222222222222222222222222', 'layer': 'upk', 'context': {'dialog_path': 'dlg_test.piero.DisConv_2'},
             'en': 'Second subtitle stays', 'cn': '第二句字幕 保持', 'tags': [], 'status': 'aligned'},
        ]
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')

    # ---- review 结果（模拟 AI 输出）----
    review_dir = os.path.join(tmp, 'review')
    os.makedirs(review_dir)
    with open(os.path.join(review_dir, 'batch_0000.json'), 'w', encoding='utf-8') as f:
        json.dump({'batch': 0, 'items': [
            {'id': 'int:A_MS.int:SecA:m_Name', 'action': 'keep', 'new_text': '', 'reason': '无', 'confidence': 0.9, 'uncertain': False, 'uncertain_reason': ''},
            {'id': 'int:A_MS.int:SecA:m_Tip', 'action': 'fix', 'new_text': '按 `GBA_Use` 键使用', 'reason': '原文 Press ... to use，补“键”更通顺', 'confidence': 0.8, 'uncertain': False, 'uncertain_reason': ''},
            {'id': 'int:A_MS.int:SecA:m_Unchanged', 'action': 'keep', 'new_text': '', 'reason': '无', 'confidence': 0.9, 'uncertain': False, 'uncertain_reason': ''},
            {'id': 'int:B_MS.int:SecB:m_Desc', 'action': 'fix', 'new_text': '内容曾翻译错误', 'reason': '语义偏离', 'confidence': 0.7, 'uncertain': True, 'uncertain_reason': '两种改法皆可，需人工确认'},
            {'id': 'upk:11111111111111111111111111111111', 'action': 'fix', 'new_text': '第一句字幕 新翻译', 'reason': '机翻腔', 'confidence': 0.85, 'uncertain': False, 'uncertain_reason': ''},
            {'id': 'upk:22222222222222222222222222222222', 'action': 'keep', 'new_text': '', 'reason': '无', 'confidence': 0.9, 'uncertain': False, 'uncertain_reason': ''},
        ]}, f, ensure_ascii=False, indent=1)

    # ---- 执行链路 ----
    run('apply_patch.py', '--reviews', review_dir, '--corpus', corpus,
        '--cn-int', cn_int, '--cn-textsdb', cn_tdb, '--out', os.path.join(tmp, 'patch'))
    run('verify.py', '--src-int', cn_int, '--src-textsdb', cn_tdb,
        '--patch', os.path.join(tmp, 'patch'), '--corpus', corpus)
    run('review_report.py', '--reviews', review_dir, '--corpus', corpus)

    # ---- 断言 ----
    patch_int = os.path.join(tmp, 'patch', 'DishonoredGame', 'Localization', 'INT')
    a = parse_int.parse_int_file(os.path.join(patch_int, 'A_MS.int'))
    by_key = {e['key']: e['value'] for e in a}
    assert by_key['m_Name'] == '示例文本', by_key
    assert by_key['m_Tip'] == '按 `GBA_Use` 键使用', by_key
    assert by_key['m_Unchanged'] == '这行不改', by_key
    assert os.path.exists(os.path.join(patch_int, 'B_MS.int'))

    tdb = parse_textsdb.parse_textsdb(os.path.join(tmp, 'patch', 'Sub_Import', 'texts.db'))
    assert tdb['11111111111111111111111111111111'] == '第一句字幕 新翻译'
    assert tdb['22222222222222222222222222222222'] == '第二句字幕 保持'

    assert os.path.exists(os.path.join(tmp, 'patch', 'changelog.json'))
    assert os.path.exists(os.path.join(review_dir, 'review_report.html'))
    assert os.path.exists(os.path.join(review_dir, 'decisions.csv'))

    # texts.db 重新加载兼容性：用 pickle 库加载生成的 db
    # （天邈工具为 Python2，S 字符串按字节处理；Python3 需 encoding='bytes'）
    import pickle
    with open(os.path.join(tmp, 'patch', 'Sub_Import', 'texts.db'), 'rb') as f:
        loaded = pickle.load(f, encoding='bytes')
    assert loaded[b'11111111111111111111111111111111'] == '第一句字幕 新翻译'.encode('utf-16-le')

    print('\n端到端冒烟测试通过 ✓')
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    main()
