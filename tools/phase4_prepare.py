# -*- coding: utf-8 -*-
"""为 Phase 3 人工项补齐发布版本、任务、地点和触发上下文。

该脚本只消费工作区内 Phase 1/3 产物，不读取游戏安装目录。输出包括：

* 可交给 ChatGPT 做 Phase 4 定向裁决的 corpus；
* 带结构化 ``game_context`` 的全量人工清单；
* 任务/触发上下文覆盖率清单。
"""
import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import phase3_attach_context as pac
import review_pipeline as rp


RELEASE_LABELS = {
    'base_game': '本体',
    'dunwall_city_trials': 'DLC：顿沃城审判',
    'knife_of_dunwall': 'DLC：顿沃之刃',
    'brigmore_witches': 'DLC：布里格莫尔女巫',
}

# 由 research/phase4-human-review-research.md 记录、可直接给终审模型使用的
# 少量裁决事实。这里只放会改变翻译 action 的事实，不把普通搜索命中当结论。
CURATED_EVIDENCE = {
    'int:DLC07_Brigmore_Void_FX.int:Tweaks.EmilyPaintingUse_01_twk:pInteractableTweaks DisTweaks_InteractableInterface:m_InteractText': [{
        'status': 'resolved',
        'finding': '非致命路线要求把“Her Face is My Smile”和另一幅画交换；Replace 指换画，不是把同一幅画放回。',
        'url': 'https://dishonored.fandom.com/wiki/Delilah_Copperspoon/Delilah%27s_Paintings',
    }],
    'int:DLC07_Twk_UI.int:Twk_DisDLC07MoviePlayerHUD DisTweaks_DLC07MoviePlayerHUD:m_InteractionTexts[44]': [{
        'status': 'resolved',
        'finding': 'Pull 是《布里格莫尔女巫》独有的隔空提起/操纵物体和身体的能力；中文名称继续服从天邈既有用法。',
        'url': 'https://dishonored.fandom.com/wiki/Pull',
    }],
    'int:Hub_Twk.int:wall_lever_01_signal_twk:pInteractableTweaks DisTweaks_InteractableInterface:m_Name': [{
        'status': 'resolved',
        'finding': '“忠诚派”任务中玩家使用信号弹发射器召回 Samuel，因此该控制对象确实对应信号弹。',
        'url': 'https://dishonored.fandom.com/wiki/The_Loyalists',
    }],
    'int:L_DLC05_OilRain_Script.INT:TheWorld:PersistentLevel.Main_Sequence.DisSeqAct_SetTutorialMessage_11 DisSeqAct_SetTutorialMessage:m_TutorialMessage': [{
        'status': 'resolved',
        'finding': 'Oil Drop 以手枪射击下落鲸油罐，并对整轮不漏掉任何罐子及准确率给奖励；PERFECT ROUND 对应无一漏射。',
        'url': 'https://dishonored.fandom.com/wiki/Oil_Drop',
    }],
    'int:L_DLC05_OilRain_Script.INT:TheWorld:PersistentLevel.Main_Sequence.DisSeqAct_ShowHUDMessage_7 DisSeqAct_ShowHUDMessage:m_Message': [{
        'status': 'resolved',
        'finding': 'Oil Drop 以手枪射击下落鲸油罐，并对整轮不漏掉任何罐子及准确率给奖励；PERFECT ROUND 对应无一漏射。',
        'url': 'https://dishonored.fandom.com/wiki/Oil_Drop',
    }],
    'int:L_TowerRtrn_Yard_Roof_Script.int:TheWorld:PersistentLevel.Main_Sequence.DisSeqAct_ShowLocationDiscovery_0 DisSeqAct_ShowLocationDiscovery:m_LocationName': [{
        'status': 'resolved',
        'finding': 'Return to the Tower 中 safe room 是摄政王在危险时躲避的安全室，不是存放保险箱的房间。',
        'url': 'https://dishonored.fandom.com/wiki/Return_to_the_Tower',
    }],
    'int:Overseer_Twk.int:ChairCampbell_interact_twk:pInteractableTweaks DisTweaks_InteractableInterface:m_InteractText': [{
        'status': 'resolved',
        'finding': "Heretic's Brand 同时指惩罚/烙印和施加它的工具；此交互对象是审讯室内给 Campbell 烙印的器具。",
        'url': 'https://dishonored.fandom.com/wiki/Heretic%27s_Brand',
    }],
    'upk:02DF332D8C3CD5C9757740467F1C2695': [{
        'status': 'resolved',
        'finding': 'Wiki 将“Doom of Pandyssia”明确解释为心脏对顿沃鼠疫的称呼，即源自潘迪希亚的灾祸。',
        'url': 'https://dishonored.fandom.com/wiki/Rat_Plague',
    }],
    'upk:A4C0BA714F6E314AD56C5C8D6FD5C6B3': [{
        'status': 'resolved',
        'finding': '该句被心脏语音页归在 The Void；主语是“行走于此者”，原译“一切都经过这里”颠倒了主客关系。',
        'url': 'https://dishonored.fandom.com/wiki/The_Heart/Quotes',
    }],
    'upk:B5CA2B1657A53B514B4EB4B98A9DC50D': [{
        'status': 'resolved',
        'finding': 'Game of Nancy 是世界观内纸牌游戏，通常 2–6 人游玩；应采用天邈语料里已有的“南希牌”而非泛称或人物扮演。',
        'url': 'https://dishonored.fandom.com/wiki/Game_of_Nancy',
    }],
    'upk:F5F46F995F2FAE02EF057E2935DCAD5B': [{
        'status': 'resolved',
        'finding': 'Skinflint 被 Wiki 明确列为 Game of Nancy 玩家；play Nancy for coin 是玩纸牌赌钱，Medium 的“扮娘们儿赚点钱”属于错解。',
        'url': 'https://dishonored.fandom.com/wiki/Game_of_Nancy',
    }],
    'upk:63AEFD9581B0486ACDB083A607906097': [{
        'status': 'resolved_context',
        'finding': '该句是猎犬酒馆女仆 Cecelia 对 Lydia 的抱怨；高混乱度下她希望只凭一点染疫迹象就让 Lydia 被带走，因此 go 不是已经死亡。',
        'url': 'https://dishonored.fandom.com/wiki/Cecelia',
    }],
    'upk:6DD737E10432026D23754F883492E522': [{
        'status': 'resolved',
        'finding': '英文资源 l_brothel_script 中连续出现四个逐渐拉长的 Haaaa 发声，分别接画商邦汀受电击后的“你真无情”“报应……这真是太好了”等台词；Wiki 也确认银色房间内需反复电击电椅上的邦汀。该音节是受电击时的喊叫/呻吟，不是反复笑声。',
        'url': 'https://dishonored.fandom.com/wiki/House_of_Pleasure',
    }],
    'upk:729628A6E5A0BB50C5DBAFF38416F54F': [{
        'status': 'resolved',
        'finding': 'Coriander of Morley 是高级督军办公室内 Overseer Sturgess 引述的一位作者；Coriander 是人名，不是“香菜”或书名。',
        'url': 'https://dishonored.fandom.com/wiki/Overseer_Sturgess',
    }],
    'upk:A273212B295549CC1330C8042380DBC5': [{
        'status': 'resolved',
        'finding': '中文 Wiki 的顿沃街道中英对照将 Framling Street 记作“弗雷姆林街”；该句是对女性平民使用心脏时触发的地点评论。',
        'url': 'https://dishonored.fandom.com/zh/wiki/%E9%A1%BF%E6%B2%83%E7%9A%84%E8%A1%97%E9%81%93',
    }],
    'upk:DD879C8CDFFA560874BC9A4990AAAFB2': [{
        'status': 'resolved',
        'finding': "Pair、Two Pair、Tall Towers、Captain's Quarters、Dunwall、Royal Dunwall、Lord Regent's Purse 是同一场牌局按强弱排列的牌型。",
        'url': 'https://dishonored.fandom.com/wiki/Dishonored_Tarot_Deck',
    }],
    'upk:D8BFC8820E50121A2FB3CE41F771D0CE': [{
        'status': 'context',
        'finding': '该句属于心脏语音；Wiki 收录原句但没有把诗性称呼 the deep ones 明确等同为某一种生物，不能仅凭页面强制改成“鲸鱼”。',
        'url': 'https://dishonored.fandom.com/wiki/The_Heart/Quotes',
    }],
    'upk:FE9EB03F69729247EB15A17CCCC53CBD': [{
        'status': 'resolved_context',
        'finding': '该完整句是心脏对 Havelock 的角色评论；破折与 after she? 是原配音文本自身的错乱/自我修正，不是字幕被截断。',
        'url': 'https://dishonored.fandom.com/wiki/The_Heart/Quotes',
    }],
    'int:Scoring.INT:TrickNames:Payback': [{
        'status': 'resolved_context',
        'finding': 'Back Home 的触发是抓起敌人投来的实弹手榴弹并扔回去杀死攻击者，确有“以其人之道还治其人之身”的含义。',
        'url': 'https://dishonored.fandom.com/wiki/Back_Home',
    }],
    'int:DLC06_ChapterNotes_twk.int:Timsh.ChapterNotes_Legal_Key DisAbstractItem:m_Description:cn_only': [{
        'status': 'resolved',
        'finding': '《顿沃之刃》任务 2“征用权”进入法制区前必须取得 Legal District Key；低混乱度钥匙位于帽子帮据点，高混乱度位于帽子帮成员 Chauncy 尸体旁。现译“帽子帮的人可能持有法制区的钥匙”与任务提示相符。',
        'url': 'https://dishonored.fandom.com/wiki/Eminent_Domain',
    }],
    'int:DLC06_ChapterNotes_twk.int:Timsh.ChapterNotes_Legal_Key DisAbstractItem:m_ItemName:cn_only': [{
        'status': 'resolved',
        'finding': 'Wiki 钥匙表直接列出 Legal District Key，任务为《顿沃之刃》任务 2“征用权”；现译“法制区钥匙”准确。',
        'url': 'https://dishonored.fandom.com/wiki/Keys',
    }],
}

# 资产名来自英文游戏包；任务名以用户指定的 Dishonored Wiki 任务目录核对。
MISSION_RULES = (
    # 本体
    (r'(^|_)(prison|prsnsewer)(_|$)', '任务 1：蒙冤入狱（Dishonored）', '寒脊监狱／监狱下水道'),
    (r'pub_fromprison', '任务间隙：猎犬酒馆（越狱后）', '猎犬酒馆'),
    (r'(^|_)(ovrsr|overseer)(_|$)|pub_fromovrsr', '任务 2：高级督军坎贝尔', '高级督军办公室／猎犬酒馆任务间隙'),
    (r'(streets1|streetsewer|brothel|artdealer|distillery2|pub_frombrothel)', '任务 3：欢愉之家', '瓶街／金猫／艺术商宅邸／下水道'),
    (r'(bridge_|l_bridge|pub_frombridge)', '任务 4：皇家医生', '考德温大桥／猎犬酒馆任务间隙'),
    (r'(boyle|boylestreet|pub_fromboyle)', '任务 5：波义耳夫人的最后聚会', '波义耳庄园及周边'),
    (r'(towerrtrn|tower_rtrn|pub_fromtwrreturn)', '任务 6：重返高塔', '顿沃塔／猎犬酒馆任务间隙'),
    (r'(^|_)tower(_|$)', '任务 6：重返高塔', '顿沃塔'),
    (r'(^|_)flooded|pub_fromflooded', '任务 7–8：淹没区／忠诚派', '淹没区；若为 pub_fromflooded 则在返回猎犬酒馆后'),
    (r'(^|_)isl_', '任务 9：指路明灯', '金斯帕罗岛'),
    (r'(^|_)startup($|_)', '本体多章节复用', '全局对白／心脏语音库'),
    # Dunwall City Trials
    (r'dlc05_oilrain', '挑战：油滴（Oil Drop）', '油滴射击挑战场地'),
    (r'dlc05_btm', '挑战：弯曲时间大屠杀（Bend Time Massacre）', '六轮解谜挑战场地'),
    (r'dlc05_arena', '挑战：后巷混战（Back Alley Brawl）', '混战竞技场'),
    (r'dlc05_atrain', '挑战：刺客奔袭（Assassin\'s Run）', '弩箭射击挑战路线'),
    (r'dlc05_chainkill', '挑战：连环杀戮（Kill Chain）', '连杀挑战场地'),
    (r'dlc05_(cntdwn|countdown)', '挑战：杀戮瀑布（Kill Cascade）', '限时击杀挑战场地'),
    (r'dlc05_(race|race_)', '挑战：列车跑者（Train Runner）', '竞速挑战路线'),
    # The Knife of Dunwall
    (r'dlc06_daudbase', '顿沃之刃：道德基地／章节间隙', '拉德肖水滨的捕鲸人基地'),
    (r'dlc06_slaughter', '顿沃之刃·任务 1：工业队长', '罗斯维尔屠宰场'),
    (r'dlc06_timsh', '顿沃之刃·任务 2：征用权', '提姆士庄园及法制区'),
    (r'dlc06_tower', '顿沃之刃·任务 3：突袭', '拉德肖水滨的捕鲸人基地'),
    # The Brigmore Witches
    (r'dlc07_baseintro', '布里格莫尔女巫·序章：选择你的目标', '捕鲸人基地'),
    (r'dlc07_coldridge', '布里格莫尔女巫·任务 1：营救丽兹', '寒脊监狱'),
    (r'dlc07_(draper|dwsewer)', '布里格莫尔女巫·任务 2：死亡鳗帮', '德雷珀区／纺织厂／下水道／河岸'),
    (r'dlc07_(brig|brigmore|void)', '布里格莫尔女巫·任务 3：黛利拉的杰作', '布里格莫尔庄园／虚空'),
)


def read_jsonl(path):
    with open(path, encoding='utf-8') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def clip(value, limit=700):
    value = str(value or '')
    return value if len(value) <= limit else value[:limit] + '…'


def compact_wiki_rows(rows):
    """去掉搜索尝试日志，只保留 High 能实际判断的证据。"""
    output = []
    for row in rows or []:
        output.append({
            'status': row.get('status', ''),
            'query': row.get('query', ''),
            'finding': row.get('finding', ''),
            'sources': [{
                'title': source.get('title', ''),
                'url': source.get('url', ''),
                'direct': source.get('direct', False),
                'evidence': clip(source.get('evidence', ''), 350),
                'page_excerpt': clip(source.get('page_excerpt', ''), 700),
            } for source in (row.get('sources') or [])[:3]],
        })
    return output


def mission_for_asset(asset):
    folded = str(asset or '').casefold()
    for pattern, mission, location in MISSION_RULES:
        if re.search(pattern, folded):
            return mission, location
    return '任务尚未由资产名唯一映射', '仅能定位到资源包'


def release_codes(entry):
    domain = entry.get('domain', {}) or {}
    values = list(domain.get('releases') or [])
    if not values and domain.get('primary_release'):
        values.append(domain['primary_release'])
    if not values and domain.get('release'):
        values.append(domain['release'])
    context = entry.get('context', {}) or {}
    values.extend(
        ref.get('release') for ref in context.get('references', [])
        if ref.get('release'))
    return list(dict.fromkeys(values))


def int_trigger(entry):
    context = entry.get('context', {}) or {}
    filename = str(context.get('file', ''))
    section = str(context.get('section', ''))
    key = str(context.get('key', ''))
    subkey = str(context.get('subkey', ''))
    field = subkey or key
    folded = f'{filename} {section} {field}'.casefold()
    if filename.casefold() == 'dishonorededitor.int':
        return ('开发者编辑器界面文案；正常零售版游玩不会触发。',
                '开发工具字符串，无法从零售版游戏画面核对正式中文术语。')
    if filename.casefold() == 'gfxui.int' and 'fontlib' in folded:
        return ('字体库资源重定向；不是玩家可见句子。',
                '需要核对汉化包资源清单，而不是游戏剧情或画面。')
    if 'chapternotes' in folded:
        return ('取得或更新章节笔记后，在日志/目标菜单查看名称或说明时显示。',
                '可定位到笔记资产，但精确拾取触发点需关卡脚本或实机验证。')
    if 'objective' in folded or 'dishonoredtask' in folded:
        return ('任务目标新增或更新时显示，并可在目标菜单中查看。',
                '目标文本可定位到任务；具体哪一个脚本节点更新需关卡脚本。')
    if 'store' in folded:
        return ('任务开始前购买“帮助/恩惠”项目时，在商店菜单显示。',
                '商店索引可定位项目；购买后实体落点由关卡脚本决定。')
    if 'interacttext' in field.casefold() or 'altinteracttext' in field.casefold():
        return ('准星对准可交互物件并满足互动条件时显示操作提示。',
                '物件资产名可定位用途；精确模型外观仍可能需要截图或实机。')
    if field.casefold() in {'m_name', 'm_itemname', 'm_pluralitemname'}:
        return ('准星指向物件、拾取物品或在日志/物品栏查看时显示名称。',
                '可定位到对象类；精确模型外观未包含在文本提取物中。')
    if field.casefold() in {'m_description', 'm_status'}:
        return ('在日志、物品栏、任务菜单或相应界面查看说明时显示。',
                '精确入口由对象类决定，文本资产未包含 UI 操作录像。')
    return ('加载该本地化字段的对应界面或对象时显示。',
            '字段能够定位，但资产连接关系未完整导出。')


def upk_trigger(entry):
    refs = entry.get('context', {}).get('references', []) or []
    paths = [str(ref.get('dialog_path', '')).casefold() for ref in refs]
    joined = ' '.join(paths)
    if 'heartgadget' in joined:
        return ('装备心脏并对准对应人物/地点使用时，或进入其归类的环境时播放。',
                '原始文本库能确认心脏语音类别，但当前提取未保存每个目标的运行时绑定。',
                'heart_comment')
    if 'dialogoneshot' in joined:
        return ('进入该地图的特定区域或满足一次性剧情条件后，播放场景对白。',
                '能定位到同一 DisConversation；精确 Kismet 条件未包含在本地化提取物中。',
                'scripted_one_shot')
    if any(token in joined for token in ('_shared', 'shared:', 'dialogtree.dlg_')):
        return ('NPC 进入相应 AI 状态时从共享语音库抽取；可能在多个章节复用。',
                '本地化引用不保存警觉、受击、抓取、发现尸体等具体 AI 事件名。',
                'shared_ai_bark')
    return ('关卡脚本或对话树调用该字幕时播放。',
            '能定位资源包和对话对象，但精确事件连接未包含在文本提取物中。',
            'scripted_dialogue')


def scene_dialogue(entry, corpus_groups, upk_orders, radius=5):
    if entry.get('layer') != 'upk':
        return []
    refs = entry.get('context', {}).get('references', []) or []
    if not refs:
        return []
    ref = refs[0]
    path = str(ref.get('dialog_path', '')).casefold()
    if 'dialogoneshot' not in path:
        return []
    upk = str(ref.get('upk', '')).casefold()
    group = list(corpus_groups.get((upk, path), []))
    position = {item['id']: index for index, item in enumerate(group)}
    order = upk_orders.get(upk, {})
    group.sort(key=lambda item: (
        order.get(item['id'][4:].upper(), 10 ** 12),
        position[item['id']]))
    target_index = next((i for i, item in enumerate(group)
                         if item['id'] == entry['id']), None)
    if target_index is None:
        return []
    start = max(0, target_index - radius)
    end = min(len(group), target_index + radius + 1)
    return [{
        'relation': ('target' if i == target_index else
                     'before' if i < target_index else 'after'),
        'object': ((item.get('context', {}).get('references') or [{}])[0]
                   .get('object', '')),
        'en': clip(item.get('en', '')),
        'cn': clip(item.get('cn', '')),
    } for i, item in enumerate(group[start:end], start)]


def build_corpus_groups(corpus):
    groups = defaultdict(list)
    for entry in corpus:
        if entry.get('layer') != 'upk':
            continue
        refs = entry.get('context', {}).get('references', []) or []
        if not refs:
            continue
        ref = refs[0]
        groups[(str(ref.get('upk', '')).casefold(),
                str(ref.get('dialog_path', '')).casefold())].append(entry)
    return groups


def build_game_context(entry):
    context = entry.get('context', {}) or {}
    releases = release_codes(entry)
    refs = context.get('references', []) or []
    if entry.get('layer') == 'int':
        asset_names = [context.get('file', '')]
        trigger, limitation = int_trigger(entry)
        trigger_kind = 'localized_field'
    else:
        asset_names = [ref.get('upk', '') for ref in refs]
        trigger, limitation, trigger_kind = upk_trigger(entry)

    asset_pairs = [(asset, mission_for_asset(asset)) for asset in asset_names]
    mapped = []
    for _asset, pair in asset_pairs:
        if pair not in mapped:
            mapped.append(pair)
    known = [pair for pair in mapped
             if pair[0] != '任务尚未由资产名唯一映射']
    missions = known or mapped or [('任务未知', '地点未知')]
    if len(missions) > 4:
        mission_label = '多章节复用（详见 asset_mappings）'
        location = '多个任务地点'
    else:
        mission_label = '；'.join(pair[0] for pair in missions)
        location = '；'.join(dict.fromkeys(pair[1] for pair in missions))

    technical = {}
    if entry.get('layer') == 'int':
        technical = {
            'file': context.get('file', ''),
            'section': context.get('section', ''),
            'field': context.get('subkey') or context.get('key', ''),
            'line': context.get('line'),
        }
    else:
        technical = {
            'reference_count': len(refs),
            'primary_upk': refs[0].get('upk', '') if refs else '',
            'dialog_path': refs[0].get('dialog_path', '') if refs else '',
            'object': refs[0].get('object', '') if refs else '',
            'kind': refs[0].get('kind', '') if refs else '',
        }
    return {
        'release_codes': releases,
        'release': '；'.join(RELEASE_LABELS.get(code, code) for code in releases)
                   or '版本未知',
        'mission': mission_label,
        'location': location,
        'trigger_kind': trigger_kind,
        'trigger': trigger,
        'remaining_context_limit': limitation,
        'technical_locator': technical,
        'asset_mappings': [
            {'asset': asset, 'mission': pair[0], 'location': pair[1]}
            for asset, pair in asset_pairs
        ][:20],
    }


def prepare(human_rows, corpus, enriched_by_id, upk_orders):
    corpus_by_id = {entry['id']: entry for entry in corpus}
    corpus_groups = build_corpus_groups(corpus)
    enriched_human = []
    review_corpus = []
    stats = Counter()
    for human in human_rows:
        identifier = human['id']
        source = corpus_by_id[identifier]
        game_context = build_game_context(source)
        research = dict(human.get('research_context') or {})
        research['wiki_research'] = compact_wiki_rows(
            research.get('wiki_research'))
        research['game_context'] = game_context
        if identifier in CURATED_EVIDENCE:
            research['curated_web_evidence'] = CURATED_EVIDENCE[identifier]
        scene = scene_dialogue(source, corpus_groups, upk_orders)
        if scene:
            research['scene_dialogue'] = scene
            stats['with_scene_dialogue'] += 1
        enriched = dict(human)
        enriched['research_context'] = research
        enriched['game_context'] = game_context
        enriched_human.append(enriched)
        stats[f'route:{human.get("route", "")}'] += 1
        stats[f'trigger:{game_context["trigger_kind"]}'] += 1
        if human.get('route') != 'human_after_high':
            continue
        base = dict(enriched_by_id[identifier])
        base['cn'] = human.get('candidate_cn', human.get('original_cn', ''))
        base['status'] = 'aligned'
        prior = dict(base.get('prior_review') or {})
        prior.update({
            'original_cn': human.get('original_cn', ''),
            'phase3_candidate_cn': human.get('candidate_cn', ''),
            'phase3_reason': human.get('reason', ''),
            'phase3_uncertain_reason': human.get('uncertain_reason', ''),
        })
        base['prior_review'] = prior
        base['research_context'] = research
        review_corpus.append(base)
    return enriched_human, review_corpus, dict(sorted(stats.items()))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--human-review', default='data/review/phase3-final/human_review.jsonl')
    parser.add_argument('--corpus', default='data/aligned/corpus.jsonl')
    parser.add_argument('--phase3-enriched', default='data/review/phase3-high/escalation_enriched.jsonl')
    parser.add_argument('--parts-dir', default='data/raw/upk_parts')
    parser.add_argument('--out-dir', default='data/review/phase4')
    args = parser.parse_args(argv)

    human = read_jsonl(args.human_review)
    corpus = read_jsonl(args.corpus)
    phase3 = {entry['id']: entry for entry in read_jsonl(args.phase3_enriched)}
    human_after_high = {entry['id'] for entry in human
                        if entry.get('route') == 'human_after_high'}
    missing = sorted(human_after_high - set(phase3))
    if missing:
        raise ValueError(f'Phase 3 enriched 缺少人工 ID: {missing[:5]}')
    enriched_human, review_corpus, stats = prepare(
        human, corpus, phase3, pac.load_upk_orders(args.parts_dir))
    out_dir = Path(args.out_dir)
    enriched_path = out_dir / 'human_enriched.jsonl'
    corpus_path = out_dir / 'review_corpus.jsonl'
    rp.atomic_write_jsonl(str(enriched_path), enriched_human)
    rp.atomic_write_jsonl(str(corpus_path), review_corpus)
    manifest = {
        'created_at': rp.now_utc(),
        'human_entries': len(enriched_human),
        'review_entries': len(review_corpus),
        'stats': stats,
        'hashes': {
            'source_human_review': rp.sha256_file(args.human_review),
            'source_corpus': rp.sha256_file(args.corpus),
            'phase3_enriched': rp.sha256_file(args.phase3_enriched),
            'human_enriched': rp.sha256_file(str(enriched_path)),
            'review_corpus': rp.sha256_file(str(corpus_path)),
        },
    }
    rp.atomic_write_json(str(out_dir / 'prepare_manifest.json'), manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
