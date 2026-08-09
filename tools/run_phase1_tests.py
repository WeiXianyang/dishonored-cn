# -*- coding: utf-8 -*-
"""运行 Phase 1 验收测试并把完整输出写入 manifest 证据。"""
import argparse
import datetime as dt
import hashlib
import json
import subprocess
import sys
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--project-root', default=Path(__file__).resolve().parent.parent)
    ap.add_argument(
        '--cn-textsdb',
        help='可选；显式授权真实 texts.db 往返测试。默认不访问游戏目录。')
    args = ap.parse_args()
    project = Path(args.project_root).resolve()
    python = sys.executable
    tools = project / 'tools'
    commands = [
        [python, '-m', 'py_compile', *map(str, sorted(tools.glob('*.py')))],
        [python, str(tools / '_smoke_test.py')],
        [python, str(tools / '_e2e_test.py')],
        [python, str(tools / '_review_pipeline_test.py')],
        [python, str(tools / 'phase1_finalize.py'), '--project-root', str(project)],
    ]
    if args.cn_textsdb:
        commands.insert(-1, [
            python, str(tools / '_roundtrip_test.py'),
            '--src', args.cn_textsdb,
        ])
    lines = [
        'Phase 1 acceptance test results',
        f'timestamp={dt.datetime.now(dt.timezone.utc).astimezone().isoformat()}',
        f'python={sys.version}',
        '',
    ]
    if not args.cn_textsdb:
        lines.extend([
            'real_textsdb_roundtrip=SKIP (未显式传入 --cn-textsdb；不访问游戏目录)',
            '',
        ])
    failed = 0
    for command in commands:
        display = subprocess.list2cmdline(command)
        result = subprocess.run(
            command, cwd=project, capture_output=True, text=True,
            encoding='utf-8', errors='replace', check=False)
        lines.extend([
            f'$ {display}',
            f'exit_code={result.returncode}',
            result.stdout.rstrip(),
            result.stderr.rstrip(),
            '',
        ])
        if result.returncode:
            failed += 1

    # 对 10,284 个英文结果做独立全量哈希复验。
    en_path = project / 'data' / 'raw' / 'upk_en_texts.json'
    en_db = json.load(open(en_path, encoding='utf-8'))
    bad_hashes = [
        digest for digest, text in en_db.items()
        if hashlib.md5(text.encode('utf-16-le')).hexdigest().upper() != digest
    ]
    hash_ok = len(en_db) == 10284 and not bad_hashes
    lines.extend([
        '$ independent UPK MD5(UTF-16LE) verification',
        f'exit_code={0 if hash_ok else 1}',
        f'entries={len(en_db)} bad_hashes={len(bad_hashes)}',
        '',
    ])
    if not hash_ok:
        failed += 1

    lines.extend([
        f'command_count={len(commands) + 1}',
        f'failed={failed}',
        f'overall={"PASS" if failed == 0 else "FAIL"}',
        '',
    ])
    output = project / 'data' / 'raw' / 'manifests' / 'test_results.txt'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text('\n'.join(lines), encoding='utf-8', newline='\n')
    print(f'{output}: {"PASS" if failed == 0 else "FAIL"}')
    if failed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
