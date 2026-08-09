# -*- coding: utf-8 -*-
"""把 Phase 4 模型裁决转换成 Phase 3 High 可消费的覆盖结果。

Phase 4 的 ``keep`` 指“保留送审候选”，而 Phase 3 High 的 ``keep`` 指
“保留 Medium 基线”。两者语义不总相同，因此必须先还原目标中文，再相对
High 的输入基线生成 ``keep/fix``。脚本同时应用少量有明确 Wiki/语义证据的
二次人工验收修正。
"""
import argparse
import json

import review_pipeline as rp


MANUAL_DECISIONS = {
    'int:L_TowerRtrn_Yard_Roof_Script.int:TheWorld:PersistentLevel.Main_Sequence.DisSeqAct_ShowLocationDiscovery_0 DisSeqAct_ShowLocationDiscovery:m_LocationName': {
        'text': '摄政王的安全屋',
        'reason': "Wiki 已确认 Regent's Safe Room 是摄政王躲避危险的安全屋，不是保险箱房；回退天邈原译。",
    },
    'upk:1594718194A93469D34B488CE987885B': {
        'text': '我才不稀罕你给的狗屁东西。',
        'reason': "shit 在 I don't need shit from you 中泛指对方给的一切并带粗鲁语气；去掉具体指代错误，同时保留人物口吻。",
    },
    'upk:428E788B4D37CBC171209A6BDA446439': {
        'text': '这城市建立在伟人的尸骨之上。<XXXXXXXXXXXXXXXXXXXXXXXXXXXX/> ',
        'reason': '心脏语音及相邻句没有证据证明 the great ones 专指巨鲸；模型把它强改成巨鲸属于无依据具体化，按最小修补原则保留天邈。',
    },
    'upk:60AE65758477019DFF9ED6BC05DACB30': {
        'text': '当心点。退后。',
        'reason': 'Mind yourself 与紧接的 Step back 共同构成身体距离警告；“当心点。退后。”比“注意点”自然，也不误解为管教品行。',
    },
    'upk:63AEFD9581B0486ACDB083A607906097': {
        'text': '我倒不介意看着莉迪亚被赶走，<XXXXXXXXXXXXXXXXXXXXXXXX/> 只要有一点染疫的迹象就够了。<XXXXXXXXXXXXXXXXXXXXXXXX/> ',
        'reason': '该句是猎犬酒馆女仆 Cecelia 在高混乱度下抱怨 Lydia；一点染疫迹象足以让她被清走，go 不应硬译为已经死亡。',
    },
    'upk:6DD737E10432026D23754F883492E522': {
        'text': '啊啊啊啊啊',
        'reason': 'l_brothel_script 的连续资源序列显示它是银色房间内第四次电击画商邦汀时的拉长发声；前三个同类 Haaaa 已结合后续对白译为“啊啊啊啊啊”。Wiki 也确认玩家会反复电击电椅上的邦汀，因此不是笑声，按同组统一修补。',
    },
    'upk:936E21C95ECAC97B90D60450B58D4B59': {
        'text': '今晚再试也没用。<XXXXXXXXXXXXXXXXXXXX/> 让我们去找找看还有没有点白兰地。<XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX/> 烂摊子就留给波义耳他们去解决。<XXXXXXXXXXXXXXXXXXXXXXXXXXXXXX/> \n',
        'reason': '只修首句的硬错：them 的先行对象虽未导出，但中文可自然省略；后两句沿用天邈，避免无必要改写。',
    },
    'upk:A273212B295549CC1330C8042380DBC5': {
        'text': '她唯一想做的就是躺在弗雷姆林街中央，<XXXXXXXXXXXXXXXXXXXXXXXXXXXX/> 静候死亡。<XXXXXXXXXX/> ',
        'reason': 'Wiki 的顿沃街道中英对照将 Framling Street 记作“弗雷姆林街”；补回天邈漏掉的具名地点，并采用已核对译名。',
    },
}

EXTRA_HIGH_DECISIONS = {
    'upk:E49F229CD3A378B3572B1EC3E79A5781': {
        'text': '保持警惕，伙计们。<XXXXXXXXXXXXXXXX/> 这个刺客可能藏在任何地方。<XXXXXXXXXXXXXXXX/> 我们不能让他到达楼上摄政王的安全屋。<XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX/> ',
        'reason': "修正 could be anywhere 的同时，根据 Wiki 和完整术语 Regent's Safe Room 把误锁的“保险箱”恢复为“安全屋”。",
    },
}


def read_jsonl(path):
    with open(path, encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def unique(rows, label):
    output = {}
    for row in rows:
        identifier = row.get('id')
        if identifier in output:
            raise ValueError(f'{label} 存在重复 ID: {identifier}')
        output[identifier] = row
    return output


def result_for_text(identifier, text, baseline, reason, confidence=0.99,
                    uncertain=False, uncertain_reason=''):
    action = 'keep' if text == baseline else 'fix'
    return {
        'id': identifier,
        'action': action,
        'new_text': '' if action == 'keep' else text,
        'reason': reason,
        'confidence': confidence,
        'uncertain': uncertain,
        'uncertain_reason': uncertain_reason,
        '_old': baseline,
    }


def build_overrides(phase4_rows, human_rows, escalation_rows,
                    high_rows, manual=None, extra=None):
    phase4 = unique(phase4_rows, 'Phase 4 results')
    human = unique(human_rows, 'Phase 4 human')
    escalation = unique(escalation_rows, 'High escalation')
    high = unique(high_rows, 'High results')
    manual = MANUAL_DECISIONS if manual is None else manual
    extra = EXTRA_HIGH_DECISIONS if extra is None else extra

    reviewable = {
        identifier for identifier, row in human.items()
        if row.get('route') == 'human_after_high'
    }
    if set(phase4) != reviewable:
        raise ValueError(
            f'Phase 4 覆盖不完整: 缺少={sorted(reviewable-set(phase4))[:5]} '
            f'多出={sorted(set(phase4)-reviewable)[:5]}')
    unknown_manual = sorted(set(manual) - reviewable)
    if unknown_manual:
        raise ValueError(f'人工二次裁决含未知 ID: {unknown_manual[:5]}')

    output = []
    manual_applied = []
    for row in phase4_rows:
        identifier = row['id']
        baseline = escalation[identifier].get('cn', '')
        human_candidate = human[identifier].get('candidate_cn', '')
        desired = (row.get('new_text', '')
                   if row.get('action') == 'fix' else human_candidate)
        reason = row.get('reason', '')
        confidence = float(row.get('confidence', 0.0))
        uncertain = bool(row.get('uncertain'))
        uncertain_reason = row.get('uncertain_reason', '')
        if identifier in manual:
            desired = manual[identifier]['text']
            reason = manual[identifier]['reason']
            confidence = float(manual[identifier].get('confidence', 0.99))
            uncertain = False
            uncertain_reason = ''
            manual_applied.append(identifier)
        output.append(result_for_text(
            identifier, desired, baseline, reason, confidence,
            uncertain, uncertain_reason))

    for identifier, decision in extra.items():
        if identifier not in high or identifier not in escalation:
            raise ValueError(f'额外 High 裁决含未知 ID: {identifier}')
        output.append(result_for_text(
            identifier, decision['text'], escalation[identifier].get('cn', ''),
            decision['reason'], float(decision.get('confidence', 0.99))))

    unique(output, '最终 High overrides')
    stats = {
        'phase4_model_results': len(phase4_rows),
        'manual_secondary_decisions': len(manual_applied),
        'extra_high_corrections': len(extra),
        'output_overrides': len(output),
        'uncertain': sum(bool(row.get('uncertain')) for row in output),
        'actions': {
            action: sum(row.get('action') == action for row in output)
            for action in ('keep', 'fix')
        },
    }
    return output, stats


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase4-results', default='data/review/phase4/run/results.jsonl')
    parser.add_argument('--human-enriched', default='data/review/phase4-context/human_enriched.jsonl')
    parser.add_argument('--escalation', default='data/review/phase3-high/escalation_enriched.jsonl')
    parser.add_argument('--high-results', default='data/review/phase3-high/run/results.jsonl')
    parser.add_argument('--out', default='data/review/phase4/high_overrides.jsonl')
    parser.add_argument('--summary', default='data/review/phase4/override_summary.json')
    args = parser.parse_args(argv)

    rows, stats = build_overrides(
        read_jsonl(args.phase4_results), read_jsonl(args.human_enriched),
        read_jsonl(args.escalation), read_jsonl(args.high_results))
    rp.atomic_write_jsonl(args.out, rows)
    stats['hashes'] = {
        'phase4_results': rp.sha256_file(args.phase4_results),
        'human_enriched': rp.sha256_file(args.human_enriched),
        'escalation': rp.sha256_file(args.escalation),
        'high_results': rp.sha256_file(args.high_results),
        'overrides': rp.sha256_file(args.out),
    }
    rp.atomic_write_json(args.summary, stats)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
