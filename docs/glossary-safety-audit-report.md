# 天邈 1.4 术语表安全审计报告

日期：2026-08-07

## 结论

原正式术语表的主要问题不是某一个词译错，而是把“某个字段中的正确译法”提升成了“所有语境都必须套用的全局字符串规则”。这会产生三类系统性错误：

1. 短词命中更长复合词，例如 `Regent's Safe` 污染 `Regent's Safe Room`。
2. UI/物品标签命中普通句法，例如 `Assassin's Blade` 的武器名污染 `some assassin's blade`。
3. 同一英文跨 DLC 指代不同对象，例如 `Estate Key` 在提姆士豪宅和布里格莫尔庄园中不是同一把钥匙。

本轮用当前 ChatGPT/Codex 高推理 Agent 对原 619 条正式硬锁逐项独立复审，同时提供实际中英文本、天邈原译、Phase 4 当前译文、版本分布、大小写、复合词关系和既有 Wiki 证据。全量覆盖及已知高风险锚点均通过确定性验收。

## 审计结果

| 决策 | 数量 | 含义 |
|---|---:|---|
| `keep_global` | 219 | 当前译值正确，可跨语境硬锁 |
| `correct_global` | 9 | 纠正硬错后可跨语境硬锁 |
| `restrict_scope` | 388 | 译法只作为大小写、标签或任务上下文候选 |
| `remove` | 3 | 普通词、重复变体或无法形成单一全局中文 |

最终形成 228 条全局硬锁、388 条作用域候选、3 条移除项；35 个译值发生明确纠错（含 9 个全局项和 26 个受限项）。

典型全局纠错包括：

- `Wedding Band`：婚礼缎带 → 结婚戒指
- `Water Control Station`：水阀控制台 → 水流控制站
- `Dunwall Tower Waterlock`：顿沃高塔的水阀 → 顿沃高塔水闸
- `Stride's Cell`：斯特莱德的房间 → 斯特莱德的牢房
- `Brigmore Crypt`：布里格莫尔地窖 → 布里格莫尔地穴

典型作用域纠错包括：

- `Regent's Safe`：译值“摄政王的保险箱”仅限独立保险箱标签；不再污染 `Safe Room`。
- `Assassin's Blade`：武器标签可译“刺客之刃”，普通所有格短语由 Agent 按句判断。
- `Locker Key`：抽屉钥匙 → 储物柜钥匙，并限定具体钥匙语境。
- `Arc Mine Extra Charge`：电弧地雷过充 → 电弧地雷额外充能，并限定升级标签。

## 新执行机制

1. `glossary/terms.json` 只保存真正的全局硬锁。
2. `glossary/advisory_terms.json` 保存 `exact_case`、`label_only`、`context_only` 候选。
3. Medium Agent 只能把 `required_terms` 当硬约束；`term_candidates` 只是参考。
4. 只要候选文本新引入了硬锁或参考层的批准译值，`phase3_escalate.py` 就加入 `term_direct_application`，交给 High Agent 独立复核。
5. High Agent 可以否决术语表；最终结果以 `term_reviewed=true` 和必要的 `term_scope_overrides` 记录裁决。
6. `verify_phase3.py` 反向重算每个直接应用；缺少 Agent 二审标记即验收失败。

## 可追溯产物

- 全量可搜索报告：`data/review/glossary-audit/glossary_audit.html`
- CSV：`data/review/glossary-audit/glossary_audit.csv`
- 逐项 Agent 裁决：`data/review/glossary-audit/results.jsonl`
- 完整策略账本：`glossary/term_policies.json`
- 验收：`data/review/glossary-audit/verification.json`
- Wiki 定向核查：`research/glossary-audit-wiki-checks.md`

关键哈希：

- 审计结果：`dc12bfcffc9cd4346f30355f98c3b0bc456c1ee95988f5037a8dabd96f36a37d`
- 全局硬锁：`91a652674bc36067e54b0319e7f2482e636d7046a33d0a41d0c5243c0f1402c4`
- 作用域候选：`e2869cff2bce40983932ad862fe86edecca2703190a099db7b4ef48f16e9c110`

## Phase 4 成品回溯二审

已从现有 Phase 4 成品中筛出 1,207 条受术语表直接影响的结果，并由当前 ChatGPT/Codex High Agent 逐句独立复核：

| 项目 | 数量 |
|---|---:|
| 二审条目 | 1,207 |
| Agent `keep` | 795 |
| Agent `fix` | 412 |
| 相对第一轮发生改变 | 416 |
| 恢复天邈原译 | 187 |
| Wiki/本地证据定向覆盖 | 7 |
| 最终人工项 | 0 |

5 条 Agent uncertain 均已通过 Wiki、官方背景资料与本地语料解决。其中 `Distillery` 在“与大嘴巴见面”的目标中确认指酒厂建筑，撤销“酿酒区”；`Grand Admiral of the Fleet` 未发现官方中文标准支持“舰队大上将”，恢复天邈原译；`Bottle Street mess` 保持不擅自扩写具体交战方；4 个重复 `Skinflint's Post` 统一为“吝啬鬼的据点”。

二审后的全量成品位于 `data/review/phase4-term-reviewed/`：31,583 条全部覆盖，接受 6,352 个修补，0 条 uncertain。`verify_phase3.py` 对 6,352 个修补重新检查格式、术语和直接应用二审标记，结果为 0 错误、0 警告；完整术语安全回归套件 PASS。

回溯产物关键哈希：

- 二审语料：`84428cf3b213b77a486c49cc3f360ae3778481df35c9c1a469c97ffb35fcd556`
- 二审模型结果：`255470d90f415e53d126a3d95bdf137a45c2c4b5fdadb9ecfd5a7c451b0215c2`
- 最终结果：`04d02ec3032af675972f8bc0ee25d54c117382d5c17da7413323b65b4381e131`
- 最终接受修补：`0d0dac846d559bd677ffc56dab70f93d6f945b5ada7e33cbc6fb7648a4521424`
