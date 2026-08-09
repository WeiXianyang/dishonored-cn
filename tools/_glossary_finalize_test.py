# -*- coding: utf-8 -*-
"""Phase 2 最终化输出与审批门禁的回归测试。"""
import hashlib
import json
import tempfile
from pathlib import Path

from glossary_finalize import (
    POLICY_TOKEN, build_outputs, main as finalize_main, value_sha256,
)


def write_jsonl(path, rows):
    path.write_text(
        ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows),
        encoding='utf-8')


def main():
    resolved = [
        {
            'id': 'term:emily', 'en_term': 'Emily', 'cn_term': '艾米莉',
            'category': 'person', 'confidence': 1.0, 'reason': '标签一致',
            'evidence_ids': ['row:1'], 'source': 'high_resolution',
        },
        {
            'id': 'term:oil', 'en_term': 'Whale Oil', 'cn_term': '鲸油',
            'category': 'world_term', 'confidence': 0.99, 'reason': '语料一致',
            'evidence_ids': ['row:2'], 'source': 'medium_pass',
        },
    ]
    deferred = [{'id': 'term:fencer', 'en_term': 'Fencer'}]
    terms, evidence, deferred_output = build_outputs(
        resolved, deferred, {'resolved_terms': 'abc'})
    assert terms['_term_count'] == 2
    assert terms['_policy'] == POLICY_TOKEN
    assert terms['Emily'] == '艾米莉'
    assert terms['Whale Oil'] == '鲸油'
    assert 'Whale' not in terms
    assert len(evidence['items']) == 2
    assert deferred_output['items'] == deferred

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        formal_path = root / 'glossary' / 'terms.json'
        formal_path.parent.mkdir()
        old_terms = {'_note': 'unverified', 'Whale': '鲸油'}
        old_bytes = (
            json.dumps(old_terms, ensure_ascii=False, indent=1) + '\n'
        ).encode('utf-8')
        formal_path.write_bytes(old_bytes)
        old_sha = hashlib.sha256(old_bytes).hexdigest()

        full_resolved = [
            resolved[0],
            {
                'id': 'term:dishonored', 'en_term': 'Dishonored',
                'cn_term': '耻辱', 'category': 'title', 'confidence': 1.0,
                'reason': '章节标签一致', 'evidence_ids': ['row:3'],
                'source': 'high_resolution',
            },
            resolved[1],
        ]
        full_deferred = [{
            'id': 'term:fencer', 'en_term': 'Fencer', 'action': 'review',
            'cn_term': '', 'category': 'ability', 'confidence': 0.7,
            'reason': '两个系统实体', 'conflict': True,
            'conflict_reason': '语义分流', 'evidence_ids': ['row:4'],
        }]
        full_rejected = [{
            'id': 'term:whale', 'en_term': 'Whale', 'action': 'reject',
        }]
        decisions = [
            {
                'id': item['id'], 'en_term': item['en_term'],
                'action': 'lock', 'cn_term': item['cn_term'],
            }
            for item in full_resolved
        ] + [
            {
                'id': 'term:fencer', 'en_term': 'Fencer',
                'action': 'review', 'cn_term': '',
            },
            {
                'id': 'term:whale', 'en_term': 'Whale',
                'action': 'reject', 'cn_term': '',
            },
        ]
        resolved_path = root / 'resolved.jsonl'
        deferred_path = root / 'deferred.jsonl'
        rejected_path = root / 'rejected.jsonl'
        decisions_path = root / 'decisions.jsonl'
        validation_path = root / 'validation.json'
        preview_dir = root / 'preview'
        write_jsonl(resolved_path, full_resolved)
        write_jsonl(deferred_path, full_deferred)
        write_jsonl(rejected_path, full_rejected)
        write_jsonl(decisions_path, decisions)
        validation_path.write_text(json.dumps({
            'status': 'pass', 'candidate_count': 5,
            'resolved_term_count': 3,
            'remaining_human_review_count': 1,
            'rejected_count': 1,
            'formal_terms_sha256_before': old_sha,
            'formal_terms_sha256_after': old_sha,
        }), encoding='utf-8')
        common = [
            '--resolved', str(resolved_path),
            '--deferred', str(deferred_path),
            '--rejected', str(rejected_path),
            '--decisions', str(decisions_path),
            '--validation', str(validation_path),
            '--formal-terms', str(formal_path),
            '--preview-dir', str(preview_dir),
        ]

        assert finalize_main(common) == 0
        preview_terms = json.loads(
            (preview_dir / 'terms.preview.json').read_text(encoding='utf-8'))
        assert value_sha256(preview_terms) == hashlib.sha256(
            (preview_dir / 'terms.preview.json').read_bytes()).hexdigest()
        assert formal_path.read_bytes() == old_bytes

        assert finalize_main([*common, '--apply']) == 2
        assert formal_path.read_bytes() == old_bytes
        assert finalize_main([
            *common,
            '--apply',
            '--approve-policy', POLICY_TOKEN,
            '--approval-note', 'test approval',
            '--expected-formal-sha256', old_sha,
        ]) == 0
        assert json.loads(formal_path.read_text(encoding='utf-8')) == preview_terms
        assert (formal_path.parent / 'terms.pre-phase2.json').read_bytes() == old_bytes
        assert (formal_path.parent / 'terms_evidence.json').is_file()
        assert (formal_path.parent / 'deferred_context_terms.json').is_file()
        assert (formal_path.parent / 'phase2_decision.json').is_file()
    print('glossary finalization tests: PASS')


if __name__ == '__main__':
    main()
