# Phase 2 天邈术语锁验收表

> 建立日期：2026-08-06  
> 输入：`data/aligned/corpus.jsonl`（Phase 1，31,583 条）  
> 目标：从真实中英语料中建立可追溯的天邈标准术语锁；未经用户确认，不覆盖正式 `glossary/terms.json`，不进入全量校对。

## 状态说明

| 标记 | 含义 |
|---|---|
| ⬜ | 未开始 |
| 🔄 | 进行中 |
| ✅ | 已通过，证据已落盘 |
| ⚠️ | 有记录的非阻断警告 |
| ❌ | 硬门槛失败 |

## 验收门槛

| ID | 类型 | 验收项 | 通过标准 | 证据 | 状态 |
|---|---|---|---|---|---|
| T0.1 | 硬 | Phase 1 输入固定 | 记录 corpus/schema/P0/旧术语表 SHA-256；输入 31,583 条且 ID 唯一 | `data/review/glossary/run_manifest.json` | ✅ |
| T0.2 | 硬 | 正式表保护 | 用户确认前不覆盖 `glossary/terms.json`；候选与建议写独立文件 | manifest + `resolution_validation.json` | ✅ |
| T1.1 | 硬 | 候选可复跑 | 候选来自英文专名形态、名称类字段或旧表种子；每项带稳定 ID、频次、来源和上下文 | `candidates.jsonl`、`candidate_summary.json` | ✅ |
| T1.2 | 硬 | 证据可追溯 | 每个建议译名必须引用真实 corpus ID；不得凭模型记忆发明“天邈译名” | `recommendations.jsonl`、`resolution_decisions.jsonl` | ✅ |
| T1.3 | 硬 | 噪声隔离 | 普通动词、句首大写、整句、代词和 UI 操作词不得自动锁定；被拒候选保留原因 | `resolved_rejected.jsonl`（574 条） | ✅ |
| T2.1 | 硬 | 冲突显式化 | 同一英文对应多个中文、同一实体存在拼写/冠词/复数变体时单列，不以最高频静默覆盖 | `conflicts.json`（210 组首轮冲突/别名警告） | ✅ |
| T2.2 | 硬 | 天邈底色优先 | 推荐值来自天邈现有译文；若必须在变体中裁决，展示频次、版本、上下文和理由 | `resolution.jsonl`、审阅 CSV | ✅ |
| T2.3 | 硬 | 旧种子复核 | 现有 6 条逐项复核；特别禁止错误泛化 `Whale → 鲸油` | `resolution_seed_audit.json` | ✅ |
| T3.1 | 硬 | 模型输出契约 | 当前 ChatGPT/Codex 只输出 schema 允许字段；ID 一一对应，失败批不进入完成态 | 24 个中档批 + 7 个高档批，0 失败 | ✅ |
| T3.2 | 硬 | 自动锁定阈值 | 只有高置信、证据一致、非普通词项进入“建议锁定”；冲突项经 Wiki 核实后仍须保持实体边界 | Wiki 叠加后 `resolved_terms.jsonl`（618 条） | ✅ |
| T3.3 | 硬 | 审阅规模可控 | 原始 20 项疑难全部查证；7 项转上下文分流、1 项定向定稿 | `phase2-wiki-term-research.md`、`phase3_context_queue.jsonl`（8 条，0.67%） | ✅ |
| T4.1 | 硬 | 格式与碰撞校验 | key 唯一、非空；不得包含整句换行/格式标签；过短/子串碰撞有警告 | `resolution_validation.json` | ✅ |
| T4.2 | 硬 | P0/核心覆盖 | Corvo、Daud、Emily、Outsider、Dunwall、Piero、Sokolov、Delilah、Billie Lurk 等核心实体均有结论 | `resolution_core_terms.json`（23 条） | ✅ |
| T4.3 | 硬 | 用户确认 | 用户审阅 Wiki 新增建议与上下文分流策略，确认/修改/拒绝；裁决可追溯 | 用户已确认“618 条采用、8 条不进全局锁”；`glossary/phase2_decision.json` | ✅ |
| T4.4 | 硬 | 正式术语锁生成 | 仅合并用户确认项；生成 `terms.json`、数量/哈希/变更说明并通过流水线加载测试 | 618 条已原子写入；正式态验证、Phase 1 回归和校对流水线契约测试全部通过 | ✅ |

## 放行规则

1. T4.3 之前，`glossary/terms.json` 保持现状，仅作为“待复核旧种子”，不能视作正式锁。
2. 模型可以分类和归纳证据，但不能用系列常识替代本地天邈语料。
3. 任何译名冲突都必须让用户看见；高频不自动等于正确。
4. 只有全部硬门槛通过，才进入 2 批真实校对冒烟。

## 当前放行结论（2026-08-06）

- 当前 ChatGPT/Codex 中档首审：1,200/1,200 条，24/24 批成功，0 失败。
- 高推理二审：305/305 条，7/7 批成功，0 失败。
- Wiki 核查前分区：606 条建议锁定、574 条排除、20 条疑难。
- Wiki 核查后分区：618 条建议锁定、574 条排除、8 条上下文分流/定向定稿。
- 推荐确认策略：采用 618 条建议；8 条不进入全局术语锁，保留为 Phase 3 上下文规则或定向审校项。
- `glossary/terms.json` 已按用户批准写入；T4.3、T4.4 均已通过，可以进入正式校对冒烟。
- 正式表 SHA-256：`38cc8bc47b84678e238fd1355761a2553708e0e1e6ca5f12445b4371fa875f0a`，与批准预览一致；独立验证已确认 618 条证据全部属于 Phase 1 的 31,583 个 corpus ID。
- Phase 2 前旧表已备份为 `glossary/terms.pre-phase2.json`，SHA-256 为 `7d024db2feec2f0c1b615017def353829286d86d9347521a0a87e9f4e17d7cd9`。
- `tools/glossary_finalize.py` 默认仅生成预览；正式写入必须同时提供用户批准策略、批准说明和当前旧表哈希，缺少任一参数即拒绝写入。
