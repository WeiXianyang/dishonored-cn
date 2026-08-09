# -*- coding: utf-8 -*-
"""运行 Phase 2 契约测试、确定性预览与独立证据验证。"""
import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def run(*args):
    completed = subprocess.run(
        [sys.executable, *args], cwd=ROOT, check=False)
    if completed.returncode:
        raise SystemExit(completed.returncode)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--expect', choices=('preview', 'final'), default='preview')
    args = parser.parse_args(argv)
    run('tools/_glossary_pipeline_test.py')
    run('tools/_glossary_resolve_test.py')
    run('tools/_glossary_wiki_resolve_test.py')
    run('tools/_glossary_finalize_test.py')
    if args.expect == 'preview':
        run('tools/glossary_wiki_resolve.py')
        run('tools/glossary_finalize.py')
    run('tools/verify_phase2.py', '--expect', args.expect)
    print(f'Phase 2 test suite ({args.expect}): PASS')


if __name__ == '__main__':
    main()
