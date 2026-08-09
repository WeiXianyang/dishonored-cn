# -*- coding: utf-8 -*-
"""完成 Phase 4：消化 Wiki 已证实的 cn_only 项并生成最终人工清单。"""
import argparse
import json
from collections import Counter
from pathlib import Path

import phase3_finalize as pf
import review_pipeline as rp


CN_ONLY_RESOLUTIONS = {
    'int:DLC06_ChapterNotes_twk.int:Timsh.ChapterNotes_Legal_Key DisAbstractItem:m_Description:cn_only': {
        'reason': '虽未在英文安装资源中找到同字段，但《征用权》任务资料确认 Legal District Key 在低混乱度位于帽子帮据点、高混乱度位于帽子帮成员 Chauncy 尸体旁；天邈“帽子帮的人可能持有法制区的钥匙”与触发和路线均吻合，保留。',
        'url': 'https://dishonored.fandom.com/wiki/Eminent_Domain',
    },
    'int:DLC06_ChapterNotes_twk.int:Timsh.ChapterNotes_Legal_Key DisAbstractItem:m_ItemName:cn_only': {
        'reason': 'Wiki 钥匙表直接列出《顿沃之刃》任务 2“征用权”的 Legal District Key；天邈“法制区钥匙”准确，保留。',
        'url': 'https://dishonored.fandom.com/wiki/Keys',
    },
}


def read_jsonl(path):
    with open(path, encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def index(rows, label):
    output = {}
    for row in rows:
        identifier = row.get('id')
        if identifier in output:
            raise ValueError(f'{label} 存在重复 ID: {identifier}')
        output[identifier] = row
    return output


def finalize_stage(final_rows, accepted_rows, human_rows, enriched_rows,
                   phase4_rows, resolutions=None):
    resolutions = CN_ONLY_RESOLUTIONS if resolutions is None else resolutions
    final = index(final_rows, 'stage final')
    human = index(human_rows, 'stage human')
    enriched = index(enriched_rows, 'enriched human')
    phase4 = index(phase4_rows, 'phase4 results')

    for identifier, decision in resolutions.items():
        if identifier not in final or identifier not in human:
            raise ValueError(f'cn_only 裁决目标未进入 stage 人工清单: {identifier}')
        if human[identifier].get('route') != 'human_unpaired_cn_only':
            raise ValueError(f'cn_only 裁决目标路由异常: {identifier}')
        final[identifier].update({
            'action': 'keep', 'new_text': '', 'reason': decision['reason'],
            'confidence': float(decision.get('confidence', 0.99)),
            'uncertain': False, 'uncertain_reason': '',
            'route': 'phase4_wiki_keep_cn_only',
        })
        del human[identifier]

    survivors = []
    for row in human_rows:
        identifier = row['id']
        if identifier not in human:
            continue
        item = dict(row)
        source = enriched.get(identifier, {})
        item['game_context'] = source.get('game_context', {})
        item['research_context'] = source.get(
            'research_context', item.get('research_context', {}))
        model = phase4.get(identifier)
        if model:
            desired = (model.get('new_text', '') if model.get('action') == 'fix'
                       else source.get('candidate_cn', item.get('candidate_cn', '')))
            item.update({
                'candidate_cn': desired,
                'reason': model.get('reason', ''),
                'uncertain_reason': model.get('uncertain_reason', ''),
                'phase4': model,
            })
            final[identifier].update({
                'reason': model.get('reason', ''),
                'confidence': float(model.get('confidence', 0.0)),
                'uncertain_reason': model.get('uncertain_reason', ''),
            })
        survivors.append(item)

    ordered_final = [final[row['id']] for row in final_rows]
    uncertain = {row['id'] for row in ordered_final if row.get('uncertain')}
    if uncertain != {row['id'] for row in survivors}:
        raise ValueError('Phase 4 人工清单与 final uncertain 集合不一致')
    return ordered_final, list(accepted_rows), survivors


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage-dir', required=True)
    parser.add_argument('--human-enriched', default='data/review/phase4-context/human_enriched.jsonl')
    parser.add_argument('--phase4-results', default='data/review/phase4/run/results.jsonl')
    parser.add_argument('--high-overrides', default='data/review/phase4/high_overrides.jsonl')
    parser.add_argument('--out-dir', default='data/review/phase4-final')
    args = parser.parse_args(argv)

    stage = Path(args.stage_dir)
    final_rows, accepted_rows, human_rows = finalize_stage(
        read_jsonl(stage / 'final_results.jsonl'),
        read_jsonl(stage / 'accepted_fixes.jsonl'),
        read_jsonl(stage / 'human_review.jsonl'),
        read_jsonl(args.human_enriched), read_jsonl(args.phase4_results))
    effective_high = read_jsonl(stage / 'effective_high_results.jsonl')

    out = Path(args.out_dir)
    final_path = out / 'final_results.jsonl'
    accepted_path = out / 'accepted_fixes.jsonl'
    human_path = out / 'human_review.jsonl'
    high_path = out / 'effective_high_results.jsonl'
    rp.atomic_write_jsonl(str(final_path), final_rows)
    rp.atomic_write_jsonl(str(accepted_path), accepted_rows)
    rp.atomic_write_jsonl(str(human_path), human_rows)
    rp.atomic_write_jsonl(str(high_path), effective_high)

    csv_rows = []
    for item in human_rows:
        game = item.get('game_context', {}) or {}
        csv_rows.append({
            'id': item['id'], 'route': item.get('route', ''),
            'release': game.get('release', ''),
            'mission': game.get('mission', ''),
            'location': game.get('location', ''),
            'trigger': game.get('trigger', ''),
            'remaining_context_limit': game.get('remaining_context_limit', ''),
            'technical_locator': json.dumps(
                game.get('technical_locator', {}), ensure_ascii=False),
            'en': item.get('en', ''),
            'original_cn': item.get('original_cn', ''),
            'candidate_cn': item.get('candidate_cn', ''),
            'reason': item.get('reason', ''),
            'uncertain_reason': item.get('uncertain_reason', ''),
            'decision': '', 'decided_text': '', 'note': '',
        })
    pf.atomic_write_csv(str(out / 'human_review.csv'), [
        'id', 'route', 'release', 'mission', 'location', 'trigger',
        'remaining_context_limit', 'technical_locator', 'en', 'original_cn',
        'candidate_cn', 'reason', 'uncertain_reason', 'decision',
        'decided_text', 'note',
    ], csv_rows)

    stage_summary = json.loads((stage / 'summary.json').read_text(encoding='utf-8'))
    summary = dict(stage_summary)
    summary.update({
        'created_at': rp.now_utc(),
        'actions': dict(Counter(row['action'] for row in final_rows)),
        'accepted_fixes': len(accepted_rows),
        'human_review': len(human_rows),
        'routes': dict(sorted(Counter(
            row.get('route', '') for row in final_rows).items())),
        'phase4': {
            'source_human_review': len(read_jsonl(args.human_enriched)),
            'model_reviewed': len(read_jsonl(args.phase4_results)),
            'wiki_resolved_cn_only': len(CN_ONLY_RESOLUTIONS),
            'remaining_human': len(human_rows),
        },
    })
    summary['hashes'] = dict(summary.get('hashes', {}), **{
        'phase4_high_overrides': rp.sha256_file(args.high_overrides),
        'final_results': rp.sha256_file(str(final_path)),
        'accepted_fixes': rp.sha256_file(str(accepted_path)),
        'human_review': rp.sha256_file(str(human_path)),
        'effective_high_results': rp.sha256_file(str(high_path)),
    })
    rp.atomic_write_json(str(out / 'summary.json'), summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
