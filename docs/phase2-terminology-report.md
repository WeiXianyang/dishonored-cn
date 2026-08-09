# Phase 2 天邈术语锁报告

> 日期：2026-08-06  
> 状态：**已获用户确认并完成正式术语锁；Phase 2 全部硬门槛通过。**  
> 输入：`data/aligned/corpus.jsonl`（31,583 条，SHA-256 `4bd6a092df173c301c825d943c2eeeca8df62693e394b9b4f0a74fa62747830c`）

## 1. 结论

Phase 2 已从真实天邈 1.4 中英语料提取 1,200 个高优先候选，并用当前 ChatGPT/Codex 完成两轮结构化审校：

| 轮次 | 模型档位 | 条目 | 批次 | 失败 | 作用 |
|---|---:|---:|---:|---:|---|
| 首审 | `gpt-5.6-sol` / medium | 1,200 | 24 | 0 | 判断术语/噪声，显式拦截冲突与低证据项 |
| 二审 | `gpt-5.6-sol` / high | 305 | 7 | 0 | 比较完整上下文，裁决明显错字、孤立变体和低频具名实体 |
| 疑难核查 | Dishonored Fandom Wiki + 本地语料 | 20 | 逐项 | 0 | 确认实体、系统和功能边界，再用天邈证据定中文 |

最终分区：

| 结论 | 数量 | 占候选 | 处理 |
|---|---:|---:|---|
| 已进入术语锁 | 618 | 51.50% | 已写入正式表并通过正式态验证 |
| 明确排除 | 574 | 47.83% | 普通词、句首误抓、任务句、语义多义词等不进全局锁 |
| 上下文分流/定向定稿 | 8 | 0.67% | 不进全局锁，Phase 3 按具体条目处理 |

自动验收为 `pass`：1,200 个最终结论 ID 唯一且分区完备；618 个建议键值非空、无换行/格式标签；23 个核心/旧种子项全部有结论；正式 `glossary/terms.json` 前后 SHA-256 均为 `7d024db2feec2f0c1b615017def353829286d86d9347521a0a87e9f4e17d7cd9`。

用户确认后，审批门禁已把 618 条预览原子写入正式 `terms.json`。正式表 SHA-256 为 `38cc8bc47b84678e238fd1355761a2553708e0e1e6ca5f12445b4371fa875f0a`，与批准预览完全一致；验证器直接读取 Phase 1 的 31,583 个 corpus ID，确认全部术语证据均可回源，未知证据数为 0。Phase 2 前旧表以原字节保存在 `glossary/terms.pre-phase2.json`。

## 2. 旧种子审计

原有 6 条只是 Phase 0 的占位种子，不能视作正确答案。最终结论如下：

| 英文 | 旧值 | 建议 | 结论 |
|---|---|---|---|
| `Corvo` | 科尔沃 | 科尔沃 | 保留 |
| `Daud` | 道德 | 道德 | 保留天邈底色 |
| `Outsider` | 界外魔 | 界外魔 | 保留 |
| `Dishonored` | 羞辱 | **耻辱** | 替换；游戏内章节/任务字段支持“耻辱” |
| `Emily` | 艾米丽 | **艾米莉** | 替换；14 个直接人物标签全部为“艾米莉” |
| `Whale` | 鲸油 | **删除此键** | 普通动物名；`Whale Oil → 鲸油` 另建正确复合词锁 |

对应硬回归全部通过：`Emily→艾米莉`、`Dishonored→耻辱`、`Whale` 拒绝、`Whale Oil→鲸油`。

## 3. 核心术语示例

| 英文 | 建议天邈译名 | 证据结论 |
|---|---|---|
| `Corvo` | 科尔沃 | 人物标签及对白一致 |
| `Daud` | 道德 | 天邈人物标签稳定；不按其他译名重命名 |
| `Emily` | 艾米莉 | 旧种子纠正 |
| `The Outsider` / `Outsider` | 界外魔 | 直接标签一致 |
| `Dunwall` | 顿沃 | 多层语料稳定切分 |
| `Piero` | 皮耶罗 | 多个目标标签一致 |
| `Sokolov` | 索科洛夫 | 多个目标标签一致 |
| `Delilah` | 黛莉拉 | 本体/DLC 标签一致 |
| `Billie Lurk` | 比利·勒克 | 完整人物标签一致 |
| `Granny Rags` | 拉格斯奶奶 | 16:1，舍弃孤立“拉格斯老奶奶” |
| `Pandyssia` | 潘迪希恩 | 跨本体与 DLC 复现；舍弃三个低频不稳定写法 |
| `Blink` | 闪烁瞬移 | 能力/教程/任务字段占优势；舍弃局部内部选项“时停闪现” |
| `Whale Oil` | 鲸油 | 复合世界观术语；不得泛化到 `Whale` |

完整结论及 corpus 证据 ID 见 `data/review/glossary/resolution/resolution_core_terms.json`。

## 4. Wiki 疑难核查结果

用户指定的 Dishonored Fandom Wiki 是社区 Wiki，不是 Bethesda/Arkane 官方站；本轮只用它确认英文实体、系统归属和功能，不从 Wiki 引入中文译名。逐项证据与链接见 `docs/phase2-wiki-term-research.md`。

12 项由 Wiki 事实与天邈内部组件证据共同解开，可新增到待批准术语锁：

| 英文 | 建议值 | 核查结论 |
|---|---|---|
| `Archer Urn` | 射手金瓮 | 是家族 Urn 传家宝；修正“射手水壶” |
| `Boyle Cameo` | 波义耳浮雕 | 同一阁楼奖品；不臆定“贝”材质 |
| `Captain's Post` | 队长哨所 | 是警卫哨所；修正“队长的站子” |
| `Carmine Cameo` | 卡尔米浮雕 | 沿用天邈家族音译和 Cameo 类型词 |
| `Drawbridge Cell Door` | 吊桥牢房门 | Wiki 明确北塔有 holding cell |
| `HIGH OVERSEER JOHN CLAVERING` | 至高督军 约翰·克拉文鹰 | 本地大道名反复支持天邈既有音译 |
| `Hole in the Fence` | 围栏的缺口 | 同一庄园恩惠/潜入缺口 |
| `Lady Emily` | 艾米莉小姐 | 同一人物；采用天邈主流礼貌称谓 |
| `Light As A Shadow` | 轻如暗影 | 两个 DLC 是同一护符 |
| `Overpowering` | 拼剑压制 | Wiki 功能明确为拼剑僵持优势 |
| `Swift Stalker` | 迅捷飞影 | 条件是收起武器加速，不是潜行状态 |
| `Whale Oil Tank Receptacle` | 鲸油罐供电器 | 是承接油罐的供电接口，不是填充器 |

另有 7 项被 Wiki 反向证实为真实多义/多系统边界，因此从全局锁排除并进入 Phase 3 分流：`Drawbridge Control`、`Fencer`、`Hatter`、`Heretic's Brand`、`Jump`、`Scavenger`、`Vengeance`。`Hearty Crew` 是唯一仍需定向定稿项；Wiki 只确认它提高召唤刺客伤害，不能替中文二选一。

## 5. 产物

| 文件 | 内容 |
|---|---|
| `data/review/glossary/candidates.jsonl` | 1,200 个候选、频次、版本、上下文 |
| `data/review/glossary/recommendations.jsonl` | 中档首审完整结果 |
| `data/review/glossary/conflicts.json` | 210 组首轮译名冲突/英文别名碰撞 |
| `data/review/glossary/resolution/resolution_decisions.jsonl` | 1,200 条最终分区结论 |
| `data/review/glossary/resolution/resolved_terms.jsonl` | Wiki 核查前的 606 条模型建议及证据（保留原始历史） |
| `data/review/glossary/resolution/resolved_rejected.jsonl` | 574 条排除项及理由 |
| `data/review/glossary/resolution/remaining_human_review.csv` | Wiki 核查前的 20 条可筛选疑难表（保留原始历史） |
| `data/review/glossary/resolution/resolution_seed_audit.json` | 6 个旧种子最终审计 |
| `data/review/glossary/resolution/resolution_validation.json` | 数量、格式、核心覆盖、回归和正式表保护验收 |
| `docs/phase2-wiki-term-research.md` | 20 项 Wiki 事实、页面链接和逐项建议 |
| `docs/phase2-wiki-decisions.json` | 可复跑的 12 lock / 7 exclude / 1 defer 机器决策 |
| `data/review/glossary/wiki_resolution/` | Wiki 叠加后的 618/574/8 完整分区与 Phase 3 队列 |
| `data/review/glossary/finalization_preview/terms.preview.json` | 用户批准的 618 条正式表预览；内容与正式表一致 |
| `data/review/glossary/finalization_preview/terms_evidence.preview.json` | 拟随正式表保存的证据索引 |
| `tools/glossary_wiki_resolve.py` | 确保 20 项完整覆盖、引用指定 Wiki 并确定性重建分区 |
| `tools/glossary_finalize.py` | 必须同时满足策略令牌、批准说明、旧表哈希才能正式写入 |
| `tools/verify_phase2.py` | 独立核对预览/正式状态、数量、哈希及 corpus 证据 |
| `glossary/terms.json` | 已批准并生效的 618 条正式术语锁 |
| `glossary/terms_evidence.json` | 每条正式术语的本地语料证据与 Wiki 引用 |
| `glossary/deferred_context_terms.json` | 8 条不进入全局锁的 Phase 3 分流/定向项 |
| `glossary/phase2_decision.json` | 用户批准说明、策略、前后哈希和输入哈希 |
| `glossary/terms.pre-phase2.json` | 正式化前旧术语表的字节级备份 |

## 6. 用户确认与放行记录

用户已于 2026-08-06 确认以下策略：

1. 接受 Wiki 叠加后的 618 条建议，作为天邈术语锁；
2. 接受 574 条排除；
3. 7 条上下文分流项和 `Hearty Crew` 不进全局锁，带入 Phase 3；
4. 用审计结果替换旧种子：`Dishonored→耻辱`、`Emily→艾米莉`、删除 `Whale→鲸油`，并保留正确的 `Whale Oil→鲸油`。

正式 `glossary/terms.json`、证据、延后项、批准记录和旧表备份均已生成。`python tools/run_phase2_tests.py --expect final`、Phase 1 全套回归及校对流水线离线契约测试全部通过，可以进入 Phase 3 校对冒烟。

最终化工具仍默认仅生成预览；即使误传 `--apply`，缺少批准策略、批准说明或精确旧表哈希也会以退出码 2 拒绝。正式化记录证明本次写入使用了用户批准策略和精确旧表哈希。
