# -*- coding: utf-8 -*-
"""运行术语作用域、二次 Agent 路由和最终反向验收测试。"""
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TESTS = [
    'tools/_glossary_audit_test.py',
    'tools/_glossary_audit_finalize_test.py',
    'tools/_review_pipeline_test.py',
    'tools/_phase3_escalate_test.py',
    'tools/_phase3_finalize_test.py',
    'tools/_term_review_retrofit_test.py',
    'tools/_release_gate_test.py',
    'tools/_release_gate_regression_test.py',
    'tools/_verify_phase3_test.py',
]


def main():
    modules = [
        'tools/glossary_audit.py', 'tools/glossary_audit_finalize.py',
        'tools/glossary_audit_report.py', 'tools/review_pipeline.py',
        'tools/phase3_escalate.py', 'tools/phase3_finalize.py',
        'tools/term_review_prepare.py', 'tools/term_review_finalize.py',
        'tools/release_gate.py',
        'tools/release_gate_regression.py',
        'tools/verify_glossary_audit.py', 'tools/verify_phase3.py',
    ]
    commands = [[sys.executable, '-m', 'py_compile', *modules]] + [
        [sys.executable, path] for path in TESTS]
    commands.extend([
        [sys.executable, 'tools/verify_phase2.py', '--expect', 'final'],
        [sys.executable, 'tools/verify_glossary_audit.py'],
    ])
    for command in commands:
        completed = subprocess.run(command, cwd=ROOT, check=False)
        if completed.returncode:
            return completed.returncode
    print('term safety test suite: PASS')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
