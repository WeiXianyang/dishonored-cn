# Phase 4：145 条人工项减负与最终验收

> 完成日期：2026-08-06  
> 范围：只处理工作区内语料、模型结果和研究产物；未读取或改动当前游戏目录。  
> 结论：**145 条全部裁决，人工待审 0 条，PASS。**

## 1. 最终结果

| 项目 | 结果 |
|---|---:|
| Phase 3 人工项 | 145 |
| 有英文源、由当前 ChatGPT/Codex 定向复审 | 143 / 143 |
| 只有中文、由 Wiki 直接补证 | 2 / 2 |
| 最终修补 | 70 |
| 最终保留天邈 | 75 |
| 最终仍需人工 | **0** |
| 全语料最终修补 | 6,468 / 31,583 |
| 全语料最终保留 | 25,115 / 31,583 |

Phase 4 模型初判为 `keep=99`、`fix=44`、`uncertain=1`。随后进行独立二次验收：没有把模型的“自信”当作证据，逐项检查任务定位、同场对白、格式、术语与天邈最小修补原则；其中 8 条改用人工证据裁决，并额外修复 1 条已流入 Phase 3 成果的 Safe Room 术语污染。

## 2. 上下文补全

每条原人工项均新增以下结构化信息：

- 本体、顿沃城审判、顿沃之刃或布里格莫尔女巫；
- 任务/章节和可推断地点；
- 交互字段、任务日志、心脏评论、一次性剧情对白或共享 AI 语音等触发类型；
- 原文件/UPK、对话路径、对象和字段等技术定位；
- 当前提取物仍缺少的运行时条件；
- 43 条一次性对白的同场景原文。

任务映射由英文资源名与 Wiki 任务目录共同确认。资产名能证明任务范围，但没有导出的 Kismet 连接不会被伪装成精确运行时触发记录。

## 3. 网络与资源证据解决的代表项

1. `Regent's Safe Room`：重返高塔中的摄政王安全屋，不是保险箱房。术语表新增完整长词条“摄政王的安全屋”，并同时纠正地点名与警卫对白。来源：[Return to the Tower](https://dishonored.fandom.com/wiki/Return_to_the_Tower)。
2. 两条 `Legal District Key` CN-only：属于《顿沃之刃》任务 2“征用权”；低混乱度在帽子帮据点，高混乱度在帽子帮成员 Chauncy 尸体旁。由此保留“法制区钥匙”和“帽子帮的人可能持有……”。来源：[Eminent Domain](https://dishonored.fandom.com/wiki/Eminent_Domain)、[Keys](https://dishonored.fandom.com/wiki/Keys)。
3. `Game of Nancy` / Skinflint：确认是纸牌游戏及玩家，采用天邈语料已有“南希牌”，修复“扮娘们儿赚点钱”等错译。来源：[Game of Nancy](https://dishonored.fandom.com/wiki/Game_of_Nancy)。
4. `Coriander of Morley`：是高级督军办公室中 Overseer Sturgess 引述的作者，不是“莫利香菜”或书名；修为“莫利的科里安德”。来源：[Overseer Sturgess](https://dishonored.fandom.com/wiki/Overseer_Sturgess)。
5. `Framling Street`：中文 Wiki 的中英对照为“弗雷姆林街”，补回天邈漏掉的地点，并否决模型自行音译的“弗拉姆林街”。来源：[顿沃的街道](https://dishonored.fandom.com/zh/wiki/%E9%A1%BF%E6%B2%83%E7%9A%84%E8%A1%97%E9%81%93)。
6. `Haaaaaaaaa`：最初是唯一剩余项。继续检查 `l_brothel_script` 后发现它属于银色房间电击画商邦汀的连续四次发声；前三次紧接“你真无情”“报应……这真是太好了”等台词，第四次只是被拆入独立 conversation。Wiki 同时确认玩家需反复电击电椅上的邦汀。因此它不是 `Ha ha` 笑声，四处统一为“啊啊啊啊啊”。来源：[House of Pleasure](https://dishonored.fandom.com/wiki/House_of_Pleasure)。

完整研究笔记见 `research/phase4-human-review-research.md`。

## 4. 二次验收拦截的模型问题

- 否决把 `the great ones` 无证据具体化成“巨鲸”，保留天邈“伟人”；
- 将 `Mind yourself. Step back.` 从生硬的“注意点”整理为“当心点。退后。”；
- 保留 `I don't need shit from you` 的粗鲁语气，不采用过度弱化的“我什么都不需要你给”；
- `No use trying them tonight` 只修首句硬错，后两句回用天邈，避免模型顺手重写；
- `seeing Lydia go` 结合 Cecelia、Lydia 和鼠疫语境改为“被赶走”，不硬译成死亡或含混的“消失”；
- 纠正模型自造的 Framling Street 音译；
- 统一最后一个电击发声；
- 回退错误的“保险箱式安全室”。

这些决定全部固化在 `tools/phase4_build_overrides.py`，可由稳定 ID 重算，不依赖手工编辑最终 JSONL。

## 5. 最终验收

`data/review/phase4-final/verification.json` 结果为 `pass`：

- 31,583 / 31,583 个 corpus ID 完整覆盖；
- 6,468 / 6,468 个修补与 accepted 集合一致；
- 6,468 / 6,468 个修补通过标签、按键标识、变量和换行校验；
- 6,468 / 6,468 个修补通过 619 条正式术语校验；
- 最终 `uncertain=0`，人工清单 0 条；
- 两条 P0 回归继续通过；
- 错误 0，警告 0。

## 6. 交付物

- `data/review/phase4-final/final_results.jsonl`：31,583 条最终决定；
- `data/review/phase4-final/accepted_fixes.jsonl`：6,468 条可进入写回的修补；
- `data/review/phase4-final/human_review.jsonl`：空文件，表示无遗留人工项；
- `data/review/phase4-final/human_review.csv` / `.html`：0 条最终审核表；
- `data/review/phase4-final/effective_high_results.jsonl`：含 Phase 4 覆盖的有效 High 全集；
- `data/review/phase4-final/summary.json`：最终统计和哈希；
- `data/review/phase4-final/verification.json`：独立验收结果；
- `data/review/phase4/high_overrides.jsonl`：143 条 Phase 4 决策及 1 条关联 Safe Room 纠错；
- `data/review/phase4/override_summary.json`：二次验收统计与输入/输出哈希。

Phase 4 到此结束。下一步可进入工作区内的文本写回与补丁打包；在获得明确指示前不接触用户当前正在玩的游戏目录。
