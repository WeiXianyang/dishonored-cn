# Phase 1 双源提取与对齐验收表

> 建立日期：2026-08-06  
> 英文源（只读）：`C:\SteamLibrary\steamapps\common\Dishonored`  
> 天邈 1.4 中文源（只读）：`C:\SteamLibrary\steamapps\common\Dishonored-备份`  
> 目标：生成可追溯、可复跑、可安全交给 AI 校对的完整中英对齐语料；未通过硬门槛时不得进入全量翻译。

> **验收结果（2026-08-06）：全部硬门槛通过。** 总语料 31,583 条，UPK 英文恢复 10,284/10,284，格式硬阻断 0，测试全绿，执行前后 1,639 个相关源文件 SHA-256 完全一致。详见 `docs/phase1-extraction-report.md`。

## 状态说明

| 标记 | 含义 |
|---|---|
| ⬜ | 未开始 |
| 🔄 | 进行中 |
| ✅ | 已通过，证据已落盘 |
| ⚠️ | 软警告；允许继续，但必须记录原因和处理方案 |
| ❌ | 硬门槛失败；禁止进入下一阶段 |

## 总验收门槛

| ID | 类型 | 验收项 | 通过标准 | 证据产物 | 状态 |
|---|---|---|---|---|---|
| G0.1 | 硬 | 双源身份固定 | 路径存在；英文侧抽检为英文，中文侧抽检为天邈中文；记录版本说明、文件数和关键资源哈希 | `data/raw/manifests/source_summary.json` | ✅ |
| G0.2 | 硬 | 源目录零改动 | 执行前后相关文件清单与 SHA-256 完全一致；工具只读源目录 | `data/raw/manifests/source_integrity_before.json`、`source_integrity_after.json` | ✅ |
| G0.3 | 硬 | 可复跑配置 | 所有源路径、工具版本、脚本 commit/工作树状态和运行时间进入 manifest；不写入秘密 | `data/raw/manifests/phase1_run.json` | ✅ |
| G1.1 | 硬 | `.int` 三类语法全支持 | 能解析 `key="value"`、`key=value`、`key=(m_Name="...",...)`；重复 key/重复结构字段不互相覆盖 | `data/raw/manifests/test_results.txt` | ✅ |
| G1.2 | 硬 | `.int` 物理文件全盘点 | 英文、中文各 658 个物理 `.int` 均有状态；不得再把“无外层引号”误记为无文本 | `data/raw/int_file_inventory.json` | ✅ |
| G1.3 | 硬 | `.int` 稳定 ID 唯一 | 每个文本叶子 ID 唯一；重复 ID 为 0；ID 可反向定位文件、section、赋值 key、结构字段和出现序号 | `data/raw/int_parse_stats.json` | ✅ |
| G1.4 | 硬 | `.int` 最小写回 | 合成样本覆盖三类语法；仅替换目标值，BOM、编码、换行、其余字节和结构不变 | `data/raw/manifests/test_results.txt` | ✅ |
| G2.1 | 硬 | `.int` 中英对齐 | 按文件相对路径 + section + key + 出现序号 + 结构字段对齐；所有 `en_only/cn_only` 均列明 | `data/aligned/int_corpus.jsonl`、`int_alignment_issues.json` | ✅ |
| G2.2 | 硬 | `.int` 覆盖可解释 | 英中条目总数、成功对齐数、空值数、仅单侧数全部统计；无“静默丢弃” | `data/aligned/int_coverage.json` | ✅ |
| G2.3 | 硬 | `.int` 抽样正确 | 分层抽样至少 50 条，覆盖本体、DLC05、DLC06、DLC07、UI、书籍/记录、结构体文本；定位与中英配对无误 | `data/aligned/int_sample_review.csv`、`int_sample_validation.json` | ✅ |
| G3.1 | 硬 | 天邈字幕库完整 | `texts.db` 无损解析 10,284/10,284 条；0 修改重建与源文件字节一致 | `data/raw/manifests/test_results.txt` | ✅ |
| G3.2 | 硬 | 对话路径上下文 | `dis.db` 可解析路径映射；无上下文条目单独统计，不伪造说话人或关卡 | `data/raw/dis_context.json`、覆盖统计 | ✅ |
| G3.3 | 硬 | 英文 UPK 字幕恢复 | 为每个天邈 MD5 条目恢复或明确标记英文源；恢复方法、文件来源和匹配规则可复跑 | `data/raw/upk_en_texts.json`、`upk_extraction_manifest.json` | ✅ |
| G3.4 | 硬 | UPK 中英对齐 | 10,284 个中文条目全部进入语料；英文缺失、哈希不符、路径缺失分别列清单，不能混为一类 | `data/aligned/upk_corpus.jsonl`、`upk_alignment_issues.json` | ✅ |
| G3.5 | 硬 | DLC 独立覆盖 | 本体、The Knife of Dunwall、The Brigmore Witches 分开统计总数、英文恢复数、中文非空数、疑似英文残留数 | `data/aligned/dlc_coverage.json` | ✅ |
| G4.1 | 硬 | 总语料契约 | `corpus.jsonl` 每行满足 schema；ID 唯一；`layer/context/en/cn/tags/status` 完整；条目数等于 INT + UPK 分层之和 | `data/aligned/corpus.jsonl`、`corpus_summary.json` | ✅ |
| G4.2 | 硬 | 格式标记保全 | 反引号标签、`<.../>`、换行转义、数字/变量占位符已提取；中英异常差异进入阻断清单 | `data/aligned/format_issues.json` | ✅ |
| G4.3 | 硬 | P0 反馈可追溯 | 两个本地 ID 均进入最终语料并带英文、旧译和上下文：`281290178F077DFEF82116B3B2F373B3`、`9EF2CA8AAC46376916E50EE7AC2E73BB` | `data/aligned/regression_cases.json` | ✅ |
| G4.4 | 软 | 长文本专项标签 | Books/Notes/Letters/Audiographs/任务日志等能单独筛选，供后续提高上下文与人工抽检比例 | `corpus_summary.json` 分类统计 | ✅ |
| G5.1 | 硬 | 自动化测试全绿 | 解析、写回、texts.db 往返、构建语料、校对契约和端到端测试返回码均为 0 | `data/raw/manifests/test_results.txt` | ✅ |
| G5.2 | 硬 | 运行后源完整性复核 | G0.2 的执行后哈希与执行前一致；如有任何变化立即停止并报告 | `source_integrity_after.json`、`source_integrity_comparison.json` | ✅ |
| G5.3 | 硬 | Phase 1 报告 | 汇总数量、覆盖率、异常、风险、未解决项和 Phase 2 输入；不得只报“脚本成功” | `docs/phase1-extraction-report.md` | ✅ |

## 放行规则

1. 所有“硬”项必须为 ✅；任何 ❌ 都阻止进入全量 AI 校对。
2. ⚠️ 必须有具体条目清单、原因、影响和下一步，不接受只给数量。
3. 英文 UPK 字幕若不能全部恢复，Phase 1 可以形成“部分技术成果”，但目标不得标记完成；需继续换提取路线或明确请求人工/外部输入。
4. 进入 Phase 2 前，先由用户查看 `phase1-extraction-report.md`、P0 回归项和至少 50 条抽样表。
5. Phase 1 只生成中间数据，不改两个游戏目录，不生成可安装补丁，不执行公开发布。

## Phase 1 完成定义

当且仅当 G0.1–G5.3 的全部硬门槛通过，且用户可从报告追溯任一语料条目回源文件时，Phase 1 才算完成。完成后下一目标是：确认天邈术语锁，并用 2–5 个真实批次校准当前 ChatGPT/Codex 的最小修补质量。
