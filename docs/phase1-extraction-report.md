# Phase 1 双源提取与对齐报告

> 完成日期：2026-08-06  
> 英文源：`C:\SteamLibrary\steamapps\common\Dishonored`  
> 天邈 1.4 中文源：`C:\SteamLibrary\steamapps\common\Dishonored-备份`  
> 结论：**Phase 1 的全部硬门槛通过，可以作为 Phase 2 术语锁与校准批输入。**

## 1. 最终结果

| 层 | 英文侧 | 天邈中文侧 | 对齐结果 |
|---|---:|---:|---:|
| `.int` 物理文件 | 658 | 658 | 各 657 个有文本；`ExampleGame.int` 双侧均为空文件 |
| `.int` 文本叶子 | 21,296 | 21,287 | 精确 21,261；确定性规范化 23；英文独有 12；中文独有 3；并集 21,299 |
| UPK 字幕文件 | 151 | 151 | 全部成功解压、读取与回源 |
| UPK 字幕 | 10,284 个唯一英文哈希 | `texts.db` 10,284 条 | **10,284/10,284 全量对齐，0 缺失、0 哈希不符** |
| 总语料 | — | — | **31,583 行 / 31,583 个唯一 ID / 0 重复** |

总语料状态为：`aligned=31,545`、`aligned_normalized=23`、`en_only=12`、`cn_only=3`。其中 2,492 条已标记为长文本，8,543 条带有需要写回保全的格式标记。

## 2. 源身份与零改动证明

- 中文目录包含 `DGOTYCNv1.4.exe`、`Sub_Import.bat`、`汉化说明.rtf`，三者的大小与 SHA-256 已写入 `source_summary.json`，可追溯为用户提供的天邈 1.4 备份。
- 英文 `.int` 的 11,750 条非空原文中 CJK 行数为 0；中文 `.int` 有 11,401 行含 CJK，中文 UPK 字幕有 10,249 行含 CJK。
- 执行前后对 **1,639 个相关文件**重新计算 SHA-256；manifest 均为：
  `dcc36fc595da70afaaa64c4b821e6d325413cadf87c13aeb281351623fa6abaa`
- 比对结果 `same=true`。提取器只写本项目的 `data/`，两个游戏目录没有任何变化。

## 3. `.int` 层修正

旧解析器只接受 `key="value"`，因此把 13 个使用无外层引号或结构体赋值的文件误判成“无文本”。新解析器覆盖：

1. `key="value"`；
2. `key=value`；
3. `key=(m_Name="...",m_Description="...",...)`；
4. 重复 key、重复结构字段及其出现序号。

真实数据得到英文 21,296、中文 21,287 个叶子，重复 identity 和重复语料 ID 都为 0。合成与端到端测试证明，替换时可保留 BOM、编码、CRLF、赋值结构和其余字节。

### 需要带入 Phase 2/打包阶段的 38 条结构警告

- **23 条标识符变形**：6 条 section 大小写变化、7 条 key 大小写变化、10 条 section 中英文标点/宽度变化（典型为 `Tutorial.` 被改成 `Tutorial。`）。它们通过一对一规范化完成语料对齐，但原中文文件中的标识符变化可能导致 UE3 运行时查找失败，不能忽略。
- **英文独有 12 条**：8 条非空文本、4 条原本即为空。其中包括 Steam 排行榜断线提示、DLC05 Expert Mode 描述和 DLC07 Arc Mine 描述；属于天邈漏字段候选。
- **中文独有 3 条**：`DLC06_ChapterNotes_twk.int` 的 Legal District Key 三个字段，其中 2 条非空、1 条为空；保留并列入版本差异清单。

完整坐标与原文在 `data/aligned/int_alignment_issues.json`，没有静默丢弃。

## 4. UPK 英文字幕恢复方法

本次没有依赖网络字幕表，也没有用模糊字符串扫描。方法来自对天邈 1.4 自带 `Sub_Import/library.zip:batch.pyo` 的字节码复原：

1. 用 `upklist.db` 固定 151 个字幕 UPK；
2. 用真实 Python 2 pickle 结构解析 `dis.db`，取得 UPK → 对话树 → 对象 → 哈希；
3. 在系统临时目录运行随包 `decompress.exe`，逐文件解压，完成即清理；
4. 按天邈注入器相同的 UE3 Name/Import/Export/Property 结构读取 `DisConv_Blurb.m_Text` 和玩家选择 `m_ChoiceText`；
5. 对每条英文执行 `MD5(英文文本的 UTF-16LE 字节，不含终止符)`，与 `texts.db/dis.db` key 强校验。

`dis.db` 共含 107,913 次字幕引用：107,721 个标量引用、192 个玩家选项引用，去重后恰好是 10,284 个哈希。最终每个哈希都恢复出英文，且独立全量复算 MD5 后坏哈希为 0。

天邈 `texts.db` 的每个中文值都带一个 UE3 FString 所需的末尾 NUL。语料中已将它从正文剥离并记录为 `target_format.nul_terminated=true`；写回工具会按源格式补回，避免让模型处理不可见控制字符。零修改重建结果与源文件完全相同：

- 大小：4,374,337 字节；
- MD5：`6932bc1f8554942a08787bb88d8f8b27`；
- 解析：10,284/10,284，值差异 0。

## 5. DLC 覆盖

按唯一哈希的互斥主版本统计：

| 版本 | 唯一字幕 | 英文恢复 | 中文非空 | 去除格式标记后的疑似英文残留 |
|---|---:|---:|---:|---:|
| 本体 | 6,184 | 6,184 | 6,184 | 0 |
| Dunwall City Trials | 1,097 | 1,097 | 1,097 | 0 |
| The Knife of Dunwall | 1,171 | 1,171 | 1,171 | 0 |
| The Brigmore Witches | 1,832 | 1,832 | 1,832 | 0 |

共享台词可能被多个版本引用，故 `dlc_coverage.json` 另提供允许重复的 referenced 统计。

## 6. 玩家反馈 P0 回归

两条已公开反馈均已在本地英文 UPK、天邈 `texts.db` 和对话树中闭环：

| ID | 英文原文 | 天邈旧译问题 | Phase 2 方向 |
|---|---|---|---|
| `281290178F077DFEF82116B3B2F373B3` | `We're counting on you.` | `我们取决于你。`，把 count on 错译为“取决于” | 必修；保留整句口型标签 |
| `9EF2CA8AAC46376916E50EE7AC2E73BB` | `I'm trapped!` | `我中陷阱了！`，误解 trapped | 必修；候选“我被困住了！” |

`regression_cases.json` 保存完整英文、旧译、UPK、对话树和对象名；后续每轮校对、写回与游戏实测都必须回归这两个 ID。

## 7. 格式与测试验收

- `corpus.jsonl` 全部 31,583 行通过 `tools/corpus_schema.json` 契约检查；ID 唯一。
- 目标侧共提取 25,497 次格式 token；UPK 终止符被独立建模；格式硬阻断为 0。
- 中英文 token/换行差异共 6,896 条，作为后续模型提示和布局审查信息，不被误判为源损坏；写回硬约束始终以旧中文 token/换行为准。
- `.int` 稳定分层抽样 50/50 可回源，覆盖本体、DLC05、DLC06、DLC07、长文本与结构体。这里只验证中英配对，不代表旧译质量正确。
- 7 组验收均返回 0：全工具编译、解析冒烟、端到端写回/验证、Codex 校对契约、真实 `texts.db` 往返、最终语料验收、10,284 条独立 MD5 复算。

## 8. 主要产物

| 产物 | 用途 |
|---|---|
| `data/aligned/corpus.jsonl` | Phase 2 唯一总语料输入 |
| `data/aligned/corpus_summary.json` | 总数、状态、版本和格式统计 |
| `data/aligned/int_alignment_issues.json` | 23 + 12 + 3 条 INT 结构差异 |
| `data/raw/dis_context.json` | 10,284 个哈希的全部 UPK/对话树/对象上下文 |
| `data/raw/upk_en_texts.json` | 10,284 条经 MD5 验证的英文字幕 |
| `data/aligned/upk_alignment_issues.json` | UPK 缺失/不符清单；本轮为空 |
| `data/aligned/format_issues.json` | 格式 token、换行差异与硬阻断 |
| `data/aligned/regression_cases.json` | 两条玩家反馈 P0 回归 |
| `data/raw/manifests/test_results.txt` | 完整测试命令、输出与返回码 |
| `data/raw/manifests/source_integrity_comparison.json` | 源目录执行前后 SHA-256 比对 |

这些文件属于可由双源重建的大型中间产物，按 `.gitignore` 不提交；提取器、schema、报告和验收表进入仓库。

## 9. Phase 2 输入与放行条件

Phase 1 技术目标已完成。进入全量 AI 校对前仍按原计划执行：

1. 用户查看本报告、P0 和抽样表；
2. 从 31,583 条中提取并确认天邈术语锁；
3. 先跑 2 批冒烟，再扩到 5 批校准；
4. 人工检查全部 `fix/uncertain`，并随机抽查 `keep`；
5. 优先处理两个 P0、8 个非空 `en_only` 和 23 个标识符变形的结构策略。

公开发布仍受天邈 1.4 二次修改授权约束；这不阻碍本地研究和校对，但在 GitHub 公开发包前必须另行确认。
