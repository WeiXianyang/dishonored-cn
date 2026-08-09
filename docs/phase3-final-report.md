# Phase 3 全量 AI 校对最终报告

> 完成日期：2026-08-06  
> 范围：只处理工作区语料与审校产物；未读取、改动或写回游戏目录。  
> 结论：**PASS，Phase 3 完成；进入 Phase 4 人工审核。**

## 1. 最终规模

| 项目 | 结果 |
|---|---:|
| Phase 1 corpus | 31,583 |
| Medium 模型审校 | 22,034 / 22,034 |
| 双方空值自动保留 | 9,547 |
| 无英文源非空 CN-only | 2 |
| High 升级复审 | 2,764 / 2,764 |
| 最终接受修补 | 6,398 |
| 最终保留天邈 | 25,185 |
| High 明确回退天邈原译 | 104 |
| 人工审核 | 145（0.459%） |
| 最终覆盖率 | 100% |

最终修补率为 `6,398 / 31,583 = 20.26%`；人工占比远低于 5% 目标。Phase 3 只生成提案，没有把任何文本写回游戏文件。

## 2. Medium 与 High 运行

### Medium 首审

- 552/552 批、22,034/22,034 条、失败批次 0。
- `keep=15,976`，`fix=6,058`，`uncertain=200`。
- 配置哈希：`1ded551952cac0d33203060acb3c87c8921fb11d5f81cf18e33f9bd3c9112877`。
- 三个异常批次均在完整审计下恢复；最终用原配置重新验证所有缓存并汇总。

### High 终审

- 升级 2,764 条：低置信 1,665、激进改写 502、旧术语范围风险 383、重复决策冲突 320、格式问题 5、Medium 不确定 200、研究裁决 127；同一条可有多个原因。
- 139/139 批、2,764/2,764 条、失败批次 0。
- High 原始输出 `keep=1,953`、`fix=811`、`uncertain=143`。
- 三个批次因 ID 集合不精确触发确定性重试，第二次均通过；尝试次数与首版错误保存在批次元数据中。
- High 配置哈希：`45b0b626cb79f06f51d2655bd67d8a0543437f7d211ae3870413d7347c2e458e`。

## 3. Fandom 优先取证

- Medium 的 200 条不确定项全部进入分流：57 个去重 Fandom 查询覆盖 65 个 ID，另有 74 条本地语境项、61 条纯语言 High 项。
- Fandom 自动证据：`direct_evidence=36`、`context_hits=27`、`no_match=2`；没有把页面标题或无搜索结果当成事实结论。
- 人工裁决规则最终为 33 条，精确展开到 127 个稳定 ID；规则命中数漂移或重叠会阻止运行。
- 独立验证确认 127/127 条已裁决规则全部落实，已裁决项没有重新流入人工清单。

新增明确修补包括：`Morley Withdraws → 莫利撤退`、Jonathon Hedgerow 画家署名、Bannerman 的社会性“败落”、Dead Counter 既有称呼、The Eels 帮派简称、Boo 与 Earl 的人物身份。证据不足的 `the Sight`、`deep ones`、`departed` 等仍保持不确定，不强造专名。

## 4. 术语与格式防线

- 正式术语仍为 618 条。Phase 3 发现并纠正唯一冲突硬锁：`Control Room Hallway: 控制室的门厅 → 控制室走廊`；最终术语哈希为 `6b407222cd691e63e77a589583b962d1b87223dc89b95dd9be2e33c7d6729252`。
- 单词型 Title Case 术语改为大小写敏感命中，避免把 UI 名 `Favor` 误套到小写普通短语 `in favor of`；383 个受旧规则影响的候选全部进入 High。
- 格式校验覆盖尖括号标签、成对按键反引号、英文源未成对运行时标记、`§...§` 与 `$...$` 具名变量、转义换行和真实换行；`keep` 与 `fix` 都执行校验。
- 最终 6,398 个修补逐条通过格式和术语硬校验，硬违规 0。

## 5. P0 回归

- `upk:281290178F077DFEF82116B3B2F373B3`：最终为“记住我们的事业／出手务必精准／我们指望你了”，删除“追求真相”和“我们取决于你”。
- `upk:9EF2CA8AAC46376916E50EE7AC2E73BB`：最终为“我被困住了！”，删除“我中陷阱了”。
- 两项稳定 ID 与原 UPK 时序标签均通过独立验证。

## 6. 独立验收

`data/review/phase3-final/verification.json` 结果为 `pass`：

- corpus 与最终结果均为 31,583 个唯一 ID，未知、重复、缺失均为 0；
- accepted fixes 集合与最终 `action=fix` 集合完全一致；
- human review 集合与最终 `uncertain=true` 集合完全一致；
- 6,398/6,398 修补通过格式校验；
- 6,398/6,398 修补通过正式术语校验；
- 127/127 已裁决研究条目通过动作回归；
- P0 两项通过；错误 0、警告 0。

Phase 1 工作区离线验收、Phase 2 正式验收、Phase 3 全部离线测试、Python 编译和 `git diff --check` 同时通过。真实游戏 `texts.db` 往返测试未在本轮重跑，因为用户已切换游戏目录且明确要求后续不再访问；既有 Phase 0/1 真实往返证据保留不变。

## 7. 交付物

- `data/review/phase3-final/final_results.jsonl`：31,583 条最终决策。
- `data/review/phase3-final/accepted_fixes.jsonl`：6,398 条可进入后续合并的修补。
- `data/review/phase3-final/human_review.jsonl`：145 条完整人工上下文。
- `data/review/phase3-final/human_review.csv`：可填写 `decision / decided_text / note` 的表格。
- `data/review/phase3-final/human_review.html`：浏览器三栏审核入口。
- `data/review/phase3-final/effective_high_results.jsonl`：含 1 条术语冲突定向复审覆盖的有效 High 全集。
- `data/review/phase3-final/summary.json`：最终统计与产物哈希。
- `data/review/phase3-final/verification.json`：独立验收结果与哈希。

## 8. 下一阶段边界

Phase 4 只需裁决 145 条人工项；在这些裁决合并前，不应进入最终写回和打包。Phase 5 才会依据稳定 ID 把批准修补写入新的 `.int` 与 `texts.db` 产物，仍应在工作区或明确授权的副本中操作。
