# Dishonored 天邈汉化 1.4 修补计划（智能体分步）

> 目标：基于天邈汉化组 1.4 版（翻译最全但有机翻/错翻），用 AI 半自动做**最小化修补**，保留天邈底色，推出新版本汉化包，尽量解压即用，最后发布到 GitHub。

---

## 0. 侦察结论（已在本机确认的事实）

| 项 | 结论 |
|---|---|
| 英文源目录 | `C:\SteamLibrary\steamapps\common\Dishonored`（已只读抽检，文本为英文） |
| 天邈中文目录 | `C:\SteamLibrary\steamapps\common\Dishonored-备份`（已只读抽检，含天邈中文 `.int`、`Sub_Import/texts.db` 与中文 upk） |
| 汉化机制 | **两层**：① 外部本地化文件覆盖；② 工具注入 `.upk` 内嵌字幕 |
| 层①外部文本 | `DishonoredGame\Localization\INT\*.int`，双侧各 **658 个物理文件**（657 个有条目，`ExampleGame.int` 为空）；英文 **21,296**、中文 **21,287** 个文本叶子，中文非空 11,744。语法包括引号、无外层引号和结构体字段；稳定身份含相对文件、section、key、重复出现序号、结构字段与字段出现序号。 |
| 层②upk 字幕 | `Sub_Import\` 目录：`texts.db`（**10,284 条** 中文字幕，MD5哈希→UTF-16中文 映射）、`dis.db`（对话树路径→哈希索引）、`upklist.db`（**151 个**需注入的 upk）、`subimport.exe`+`decompress.exe`（天邈注入工具，Python2.7 打包） |
| 覆盖范围 | 468 个 upk 被天邈修改（含中文字体 `DisFonts_*_SF.upk`）；151 个字幕 upk 合计 **4.5 GB**（全量），被改 upk 合计 2.5 GB |
| 安装残留 | 根目录 `DGOTYCNv1.4.exe`（天邈安装器）、`Sub_Import.bat`、空壳 `汉化说明.rtf` |
| 双源状态 | 两份目录均已就绪；各发现 658 个物理 `.int` 文件。Phase 0 的 645 是解析器实际纳入语料的文件数，Phase 1 需为其余文件给出跳过原因。 |

**核心推论**
- 中英文源均可直接从各自目录提取，无需 Steam 校验或改动任一游戏目录。
- "解压即用"只对外部 `.int` 天然成立；upk 字幕要么接受大体积全量覆盖，要么用注入工具（替代方案）。
- 天邈的 `texts.db/dis.db/upklist.db/subimport.exe` 本身就是一套完整的 upk 文本提取+注入管线，修补后可复用其机制。

## 0.5 执行状态（实时更新）

- **已确认**：英文源使用现成的独立英文目录；主校对模型改为当前 ChatGPT/Codex 模型，通过本机 ChatGPT 登录调用，不再依赖 DeepSeek API key。OpenAI 兼容 API 后端仅保留为备用。
- **双源目录已确认**：英文源为 `C:\SteamLibrary\steamapps\common\Dishonored`，天邈 1.4 中文源为 `C:\SteamLibrary\steamapps\common\Dishonored-备份`；本轮仅做了只读存在性、文件数与文本抽检，没有改动游戏文件。
- **当前进度（2026-08-06）**：**Phase 0 与 Phase 0.6 全部完成**。Phase 0 的首个 commit 为 `6a6050f`；Phase 0.6 已把 `review_pipeline.py` 改为默认 Codex/ChatGPT、兼容 API 备用，加入 JSON Schema、批次快照、配置/输入哈希、原子落盘、缓存复验、过期归档、失败记录与 token 汇总。本项目使用隔离的 `codex-cli 0.146.1`（全局 0.141.0 未改动），已在无 API key 条件下通过 ChatGPT 登录真实跑通合成批次，第二次运行命中缓存且不新增 token。离线契约测试与原有端到端打包测试均通过。
- **反馈落实**：以 3DM 分发版本及小黑盒等中文社区为核心；两条明确逐句错译已在本地英文 UPK、天邈 `texts.db` 与对话树闭环，并固化为 P0 回归：`We're counting on you. → 我们取决于你`（`281290178F077DFEF82116B3B2F373B3`）、`I'm trapped! → 我中陷阱了！`（`9EF2CA8AAC46376916E50EE7AC2E73BB`）。
- **反馈报告已完成并获用户放行**：`docs/tianmiao-1.4-feedback-research.md`；Phase 1 已启动。
- **Phase 1 已完成（2026-08-06）**：验收表全部硬门槛通过。生成 31,583 条唯一语料；`.int` 并集 21,299 条；英文 UPK 字幕恢复 10,284/10,284、0 缺失、0 哈希不符；格式硬阻断 0；测试全绿；执行前后 1,639 个相关源文件 SHA-256 完全一致。报告：`docs/phase1-extraction-report.md`。
- **Phase 2 已完成（2026-08-06）**：从 31,583 条语料提取 1,200 个候选；当前 ChatGPT/Codex 完成 24 个 medium 首审批与 7 个 high 二审批，0 失败。用户确认 618 条正式术语锁、574 条排除、8 条 Phase 3 上下文/定向项。Phase 3 后续以寒脊监狱同关卡证据纠正了唯一冲突锁 `Control Room Hallway: 控制室的门厅 → 控制室走廊`，术语总数仍为 618，最终有效表哈希 `6b407222…29252`；该覆盖已写入批准记录和证据文件，Phase 2 正式验证继续 PASS。报告：`docs/phase2-terminology-report.md`、`docs/phase2-wiki-term-research.md`。
- **Phase 3 已完成（2026-08-06）**：31,583 条全部分类；Medium 完成 22,034/22,034（552/552 批），High 完成 2,764/2,764（139/139 批），最终失败 0。Fandom 优先分流全部 200 条 Medium 不确定项，33 条人工裁决规则覆盖 127 个稳定 ID。最终接受 6,398 个修补，145 条进入人工审核（0.459%），104 条 High 明确回退到天邈原译；两条 P0 均修复。独立验收复核 31,583 ID、6,398 个格式/术语约束和 127 条研究裁决，结果 0 错误、0 警告。报告：`docs/phase3-final-report.md`。
- **术语安全整改已完成（2026-08-07）**：针对 `Regent's Safe` 子串污染 `Regent's Safe Room` 暴露的系统性问题，当前 ChatGPT/Codex High Agent 已全量复审 619/619 条旧术语，拆分为 228 条全局硬锁、388 条带作用域参考候选和 3 条移除项，并纠正 35 个译值。随后对 Phase 4 成品中 1,207 条受术语影响的结果逐句独立二审：795 条保留、412 条修正，二审相对第一轮实际改变 416 条，其中 187 条恢复天邈原译；5 条 uncertain 经 Wiki/本地证据全部解决，最终人工项 0。当前成品为 6,352 条修补；31,583 条覆盖、格式、术语及二审标记验收均为 0 错误、0 警告。以后凡直接采用硬锁或参考术语译值，必须有 `term_reviewed=true`，否则验收失败。报告：`docs/glossary-safety-audit-report.md`。
- **Phase 4.5 防过修稳定化已完成（2026-08-09）**：正式打包前新增统一 release gate。6,352 条候选修补中，1,012 条玩家相关结果已有独立术语二审，89 条非零售开发者编辑器文本确定性回退，其余 5,251 条全部进入隐藏首轮理由的反方 Agent 二审；二审只能接受候选、完整回退天邈或请求多源研究，代码硬拒绝第三版译文。风险队列为 critical 1,822、high 2,652、medium 714、low 63；13 条错误疫苗 13/13 通过。ChatGPT/Codex 额度 08-07 用尽后，本会话 AI（session 后端）续跑全部剩余 3,644 条（subagent 并行），最终裁决 **keep 4,345 / fix 906**；218 条 uncertain 全部定夺（本地规则库/对话邻居 ~200、Fandom API 3、用户决策 2），全队列 uncertain=0。设计文档：`docs/safe-localization-workflow.md`。
- **Phase 5 合并生成已完成（2026-08-09）**：以 `data/review/phase4-term-reviewed/accepted_fixes.jsonl`（6,352）为基底，叠加 Phase 4.5 裁决（keep 保留候选、fix 回退原译）构造 6,352 条 decisions，`tools/apply_patch.py` 写回生成 `patch/`：196 个 `.int`（2,058 条修改，UTF-16 LE+BOM+CRLF 与键序保持源文件）、新 `texts.db`（4,085 条修改，pickle0 最小 diff）、原样复制 `dis.db`/`upklist.db`/中文字体 upk、`changelog.json`（6,352 条明细）、`hashes.json`（SHA-256 校验清单）、`README.md`。幂等验证通过（patch 作为源重跑 0 修改）；9 条未写回边界已记录（7 en_only 无中文源字段 + 1 天邈源畸形缺引号 + 1 [Name] 占位符保留英文原样）。工作统计：`docs/progress-stats.md`（实时更新）。
- **Phase 6 打包已完成（2026-08-09）**：双形态发布。Full 151 字幕 upk 经天邈 `subimport.exe` 注入（texts.db = 天邈 + 修补 4,085 条），5 分卷 zip 全 CRC 通过；Lite = .int + 注入工具 + 安装/还原 bat。SHA-256 清单 `release-manifest.json`。
- **Phase 7 静态验证 → 实机首测三大漏项修复（2026-08-09）**：在英文原版实测发现并全部修复：① **365 个天邈汉化 `.int` 未纳入补丁**（Phase 1 语料仅覆盖 239 个 .int 文件，英文原版上人物名/对话/任务/物品全英文）→ 补丁 .int 扩为 **658 全量**（239 个含修补 + 419 个天邈原版）；② **`Startup.upk` 天邈手工修改引擎字体**（subimport 注入版=英文原版，字幕中文方块根因）→ 补入天邈版；③ **`DishonoredGame.upk` / `UI_Loading_SF_LOC_INT.upk` 天邈手工修改 Flash UI/字体** → 补入天邈版。全量静态验证：天邈版 vs 测试副本 5,536 文件比对 → 5,147 一致 + 389 预期差异（修补 .int + 注入 upk），0 异常、0 多余。patch/ 现 670 文件；release 重建：Base 76 文件 1,526 MB、INT 658 文件 2.43 MB、Lite 680 文件 73.4 MB。**注意**：365 个补入 .int 为天邈原版（未经过 Phase 3/4.5 修补审查，可列为后续扩充审查项）。
- **Phase 7 Lite 实测（2026-08-09，用户实机确认通过）**：Lite 全链路实测又发现并修复 2 个 Lite 专属问题：① **subimport.exe 运行时会把 `Startup.upk` 重写为英文原版**（Full 不跑 subimport 故无此问题）→ upk 独立存放 `CNPatch/Upks/`，安装.bat 在 subimport 注入后（[5/5]）重新复制 6 upk 覆盖；② **bat 文件 LF 换行导致 cmd 解析错乱**（`'cho' is not recognized`、if 语句失败、exit 255）→ bat 改 CRLF + echo 全 ASCII（build_lite.py 固化）。安装后静态验证：6 upk 全 = 天邈哈希、.int 658 全 = 补丁版、备份 658 成功；用户实机确认主菜单/UI、人物名、字幕全部正常中文，与 Full 一致。
- **Phase 4 已完成（2026-08-06）**：为 145 条人工项补齐本体/DLC、任务、地点、触发类型、技术定位及 43 条同场景对白；当前 ChatGPT/Codex 对 143 条有英文源项目作定向终审，另以 Dishonored Wiki 直接裁决 2 条 CN-only。二次独立验收纠正 8 条模型过度/欠修，并修复 `Regent's Safe Room` 被子串术语误锁为“保险箱室”的问题，正式术语增至 619 条。145 条最终为 `fix=70`、`keep=75`，人工项降为 0；全量接受修补 6,468 条，31,583 条覆盖、格式与术语验收 0 错误、0 警告。报告：`docs/phase4-human-review-report.md`。

---

## 1. 总体架构

```
英文源文本 ──┐
            ├──► 对齐语料库(JSONL) ──► 术语表 ──► AI 校对流水线 ──► 修改提案(JSON)
天邈中文本 ──┘                             ▲                              │
                                          │                              ▼
                                 人工审核(仅不确定项) ◄── 不确定条目 + AI 理由
                                          │
                                          ▼
                              合并 → 生成新文本 → 打包 → 验证 → GitHub 发布
```

**质量原则（写进所有 AI prompt）**
1. 天邈译文是基线，**最大限度保留底色**（措辞习惯、语气、专有名词、排版）。
2. 只修「硬问题」：错译、漏译、语义偏离、机翻痕迹、错别字、标点/长度失控、占位符破坏。
3. 专有名词以天邈为底色；术语分为全局硬锁与限定场景候选。任何直接套用结果都必须由独立 Agent 结合完整复合词、实体类型、任务与 DLC 语境二次复核，允许有证据地否决术语表。
4. AI 无法确定 → 标记 `uncertain` 并给理由，进人工审核；人工占比应极低（<5%）。

---

## 2. 阶段分解

### Phase 0 — 环境与仓库（≈0.5h）
- 在 `C:\Users\wxy\Desktop\耻辱1代汉化补丁` 初始化 git 仓库，建目录骨架：
  ```
  tools/           # 提取、对齐、校对、打包脚本
  data/raw/        # 提取出的原始文本（不入库或 gitignore）
  data/aligned/    # 对齐语料
  data/review/     # 人工审核产物
  glossary/        # 术语表
  prompt/          # AI prompt 模板
  patch/           # 打包输出
  docs/            # 说明、变更日志
  ```
- 确认 Python 3.11 环境与 Codex CLI；本机使用 ChatGPT 登录。API key 仅在启用备用 OpenAI 兼容后端时需要。

### Phase 0.6 — Codex 校对后端改造（不依赖游戏数据，可立即完成）

**目标**：保留现有批处理、校验和断点续跑能力，把模型调用层从“必须使用第三方 API”改为“默认使用当前 ChatGPT/Codex，兼容 API 作为备用”。

1. **后端抽象**
   - 为 `review_pipeline.py` 增加 `--backend codex|api`（默认 `codex`）。
   - `api` 后端保留现有 `LLM_API_BASE/KEY/MODEL` 行为，避免破坏已经验证的实现。
   - `codex` 后端通过 `codex exec` 复用本机 ChatGPT 登录；不读取、不要求、不写入 API key。
2. **模型与推理配置**
   - 默认模型：`gpt-5.6-sol`（本机 ChatGPT 登录实际支持的完整模型 ID；API 别名 `gpt-5.6` 不用于 Codex CLI）；默认推理强度使用均衡档。
   - 流水线优先使用 `tools/.codex-cli/` 中的项目本地固定版本，避免升级或覆盖用户的全局 Codex CLI；该依赖目录不入 Git。
   - 当前固定的项目本地 CLI 为 `@openai/codex@0.146.1`；重新搭建环境时运行 `npm install --prefix tools/.codex-cli --no-save --no-package-lock @openai/codex@0.146.1`。
   - 第一轮全量校对使用 Medium；疑难/低置信度复审使用 High，避免所有条目都消耗高推理额度。
   - 模型、推理强度、Codex CLI 版本、prompt 哈希、术语表哈希和语料哈希写入 `run_manifest.json`，保证结果可追溯。
3. **严格结构化输出**
   - 新增 `tools/review_schema.json`，用 `codex exec --output-schema` 强制输出 `{items:[...]}`。
   - 每批生成稳定输入快照 `data/review/requests/batch_XXXX.json`；模型只读输入并返回结构化结果。
   - 继续执行 id 集合、字段类型、占位符、反引号标签和术语锁定检查；任一硬校验失败则整批不落为完成态。
4. **安全与断点**
   - Codex 子任务使用只读沙箱；仅由流水线本身写入结果文件。
   - 每批先写临时结果，通过验证后原子落盘为 `batch_XXXX.json`；进程中断不会留下“看似完成”的半批结果。
   - 批次完成依据同时包含输入哈希和配置哈希；语料、prompt、术语表或模型配置变化时，旧批次自动标记过期，禁止误跳过。
5. **额度与重试**
   - Codex 后端默认并发数为 1；确认稳定后最多提高到 2，不沿用 API 后端的并发 4。
   - 临时错误最多重试 3 次并指数退避；遇到账户额度/速率限制时安全停止，保留进度，等待恢复后继续。
6. **Phase 0.6 验收标准**
   - 现有 API 后端测试保持通过。
   - 使用合成语料验证 batch 生成、schema、id/标签/术语检查、失败重试、过期检测和断点续跑。
   - 在没有 `LLM_API_KEY` 的环境中，Codex 后端能通过 ChatGPT 登录完成一批并生成合法结果。

### Phase 1 — 双源文本提取（≈1–2h）
**1a. 冻结并校验双源（只读）**
- 对现有中文备份目录生成文件清单和哈希，不覆盖、不移动游戏文件；重点记录：
  - `DishonoredGame\Localization\INT\*`（中文 .int）
  - `Sub_Import\*`（texts.db 等，中文 upk 字幕源）
  - `CookedPCConsole\DisFonts_*_SF.upk`（中文字体，必须随补丁分发）
  - 根目录 `DGOTYCNv1.4.exe`、`Sub_Import.bat`、`汉化说明.rtf`
- **校验**：英文源和中文源的文件数、相对路径与哈希清单均落入 `data/raw/manifests/`（不入库），后续所有提取只读源文件。

**1b. 使用已确认的英文源**
- 直接读取 `C:\SteamLibrary\steamapps\common\Dishonored`；无需 Steam 校验、联网下载或运行天邈安装器。

**1c. 提取英文文本**
- 英文 `.int`：按三类赋值语法解析，产出带完整稳定身份的文本叶子清单。
- 英文 upk 字幕：**已验证并全量完成**——移植天邈 `batch.pyo` 的 UE3 对象/属性读取逻辑，按 `dis.db` 坐标提取；`texts.db` key 已证实为 `MD5(英文 UTF-16LE 字节)`，10,284 条全部强校验通过。

**1d. 提取中文本**
- 中文 `.int`：从 `C:\SteamLibrary\steamapps\common\Dishonored-备份` 解析。
- 中文 upk 字幕：解析 `texts.db`（GBK 解码 + UTF-16 值）+ `dis.db`（路径→哈希）+ `upklist.db`，产出条目。

**1e. 对齐建库** → `data/aligned/corpus.jsonl`
- `.int` 按相对文件 + section + key + 出现序号 + 结构字段对齐；UPK 按哈希并保留全部 UPK/对话树/对象引用。
- 记录上下文：所在文件/关卡、说话人（dis.db 路径含 `dlg_xxx` 说话人信息）、相邻台词。
- **校验**：中英条目数一致（±允许未翻译原文条目）；抽样 50 条人工比对对齐正确性。

### Phase 2 — 术语表建设（≈1–2h，人工确认 1 次）
- **模型阶段已完成**：从真实中英语料提取 1,200 个高优先候选；每项带稳定 ID、频次、版本、名称字段证据和 corpus 上下文。
- **两级模型审校已完成**：medium 首审 24 批、high 冲突裁决 7 批，全部结构化输出与证据硬校验通过，0 失败。
- **最终建议**：618 条进入术语锁、574 条普通词/噪声排除、7 条真实语义边界不做全局映射、`Hearty Crew` 定向延后，共 8 条带入 Phase 3。
- **旧种子已查错但未写入正式表**：`Emily` 应为“艾米莉”，`Dishonored` 应为“耻辱”，错误的 `Whale→鲸油` 应删除；正确复合词为 `Whale Oil→鲸油`。
- **用户确认已完成**：618 条正式术语表已生成并通过加载/证据/哈希验证；8 条不进全局锁并已注入 Phase 3 上下文队列。Phase 3 可从 2 批真实校对冒烟开始。

### Phase 3 — AI 校对流水线（核心，长时间分批执行）
**3a. 流水线脚本 `tools/review_pipeline.py`**
- 输入：`corpus.jsonl` + `terms.json` + `prompt/template.md`
- 分批（每批 30–40 条；`.int` 按文件、upk 字幕按关卡/对话路径聚合，尽量保留语境）。
- 默认调用 Codex 后端并复用 ChatGPT 登录；每批独立落盘，支持安全停止、恢复、限速和失败重试。
- 输出每条：
  ```json
  { "id": "INT:Bridge_MS.int:12", "action": "keep|fix",
    "new_text": "...", "reason": "...", "confidence": 0.0~1.0,
    "uncertain": false, "uncertain_reason": "..." }
  ```
- 判据：语义是否偏离原文 / 是否机翻腔 / 错别字 / 长度与格式是否失控 / 专有名词是否与术语表冲突。**`action=keep` 默认值**——不确定就不动，宁缺毋滥。

**3b. 分级试跑与质量门槛**

1. **冒烟批**：先跑 2 批，确认结构化输出、中文编码、标签和断点均正确。
2. **校准批**：扩至 5 批（约 150–200 条，混合 UI 与字幕）；人工检查所有 `fix/uncertain`，并随机抽查至少 20 条 `keep`。
3. **放行标准**：试跑误改率不高于 5%；未出现术语/占位符破坏；修改率原则上低于 30%。不达标则先调 prompt/批次语境，再从干净试跑批重跑。
4. **全量首轮**：按稳定配置依次处理全部 aligned 条目；每 500 条输出滚动统计。若修改率超过 35%、不确定率超过 10% 或连续两批失败，自动暂停排查。
5. **疑难复审**：所有 `uncertain=true` 条目先写入 `wiki_lookup_queue.json`。涉及人物、地点、物件、能力、派系或世界观事实时，编排层先查询用户指定的 [Dishonored Wiki](https://dishonored.fandom.com/wiki/) 补足英文实体语境；Wiki 是社区资料，只用于事实核实，不能覆盖本地天邈中文证据。随后仅对仍不确定、低置信度 `fix`、长度预警和规则冲突候选使用 High 推理强度复审；复审仍不能确定才进入人工审核，绝不自动强改。

**3c. 使用额度**：不再预估 DeepSeek API 成本。Codex 后端使用 ChatGPT/Codex 套餐额度；流水线记录批次数和 token 使用（若 CLI 返回），额度不足时断点停止。若以后启用 API 备用后端，再按当时实际模型定价单独估算。

**3d. 质量自检（流水线内置）**
- 修改率统计（预期 <30% 被改，其余 keep）；
- 术语应用扫描：重算硬锁与作用域候选的直接套用；凡缺少独立 Agent 二审标记即拒绝验收，二审可记录作用域例外并否决不适用术语；
- 占位符/标签一致性检查（`` `GBA_Use` `` 等内嵌标签不得丢失）；
- 长度越界预警（UE3 文本框宽度限制）。
- 每批 id 必须一一对应且无重复、无遗漏；批次摘要与最终汇总条数必须和输入一致。
- 生成 `run_manifest.json`、`summary.json` 和异常清单，确保任一修改都能追溯到模型配置、prompt 和源条目。

### Phase 4 — 人工审核（占比极低）
- `uncertain=true` 或 `confidence` 低于阈值的条目 → 生成 `data/review/review_report.html`（英文原句 / 天邈译文 / AI 建议 / AI 理由，三栏对照）。
- 用户逐条裁决：接受 / 采用 AI / 保留天邈 / 手写。
- 裁决结果合并回流水线输出。

### Phase 4.5 — 防过修稳定化（正式打包前硬门）

- 冻结 Phase 4 候选、语料、术语和配置哈希；不得直接改游戏目录。
- 所有尚未独立复核的语义修补进入反方 Agent；隐藏首轮理由和置信度。
- 执行单写入规则：只允许接受、完整回退、请求研究；第三版译文整批失败。
- 本地语料、Dishonored Wiki、官方资料和游戏脚本/实机证据按等级注入，搜索命中不自动等于裁决。
- 原译与候选都不可靠时进入重新提案，新候选重新走完整二审。
- 所有最终 `fix` 必须含 `release_gate_reviewed=true`；未解决项、格式错误或缺少证据时禁止进入 Phase 5。
- 错误疫苗 critical 检出率必须为 100%，分层抽检错误修改率不超过 1%。

### Phase 5 — 合并生成（≈0.5–1h）
- `.int` 层：按 `file+key` 应用修改，**保持 UTF-16 LE + BOM + CRLF + 键序不变**（最小 diff）。
- upk 层：生成**新 `texts.db`**（同样的哈希→中文格式）；若哈希=MD5(英文)成立，则仅替换修改条目的值，未修改条目保持原值（同样最小 diff）。
- 生成 `patch/` 目录：新 `.int` 文件 + 新 `texts.db` + 新 `dis.db`/`upklist.db` + 中文字体 upk + 说明文档。

### Phase 6 — 打包（已完成 2026-08-09，决策 D2=C 双形态）
- **形态 A（Full，真·解压即用，4.24GB）**：151 个字幕 upk 用天邈 subimport.exe 注入新 texts.db（全部 151/151 变化），按 upklist 原始路径含 DLC05/06/07 子目录；分 6 卷 zip（GitHub 单文件 ≤2GB）：
  `part1-Base`(1,500MB) + `part1-INT`(1.9MB) + `part2-DLC05`(1,260MB) + `part3-DLC06`(630MB) + `part4-DLC07`(921MB) + `Lite`(26.8MB)。
- **形态 B（Lite，26.8MB）**：.int（解压即用）+ Sub_Import 注入工具 + `安装.bat`/`还原.bat`（备份→覆盖→注入，复刻天邈原机制）。
- 验证：注入前后 151/151 upk 哈希变化；内容级抽查 2 个 upk（L_Pub_Night_Audio、L_DLC05_Race_Script）解压后含修补新文本、无英文残留；二次注入仅 10 upk 字节变（subimport 重压不幂等，内容正确，无碍）；全部 zip CRC 校验。
- 产物：`release/`（README.md + release-manifest.json SHA-256 清单 + 6 个 zip）。

### Phase 7 — 验证（≈1h + 用户配合）
- **静态校验（自动化）**：编码/结构/条目数；新包与天邈原版的差异清单与预期一致；哈希校验通过；注入工具试运行于**副本** upk 后 diff 比对。
- **动态验证（用户配合）**：把包解压/安装到**另一份干净副本**（Steam 可再装一份或复制目录），启动游戏：主菜单中文 → 进第一章 → 触发数段对话字幕 → UI/任务/物品/书页抽查；无乱码、无残留英文、无崩溃。
- 回归：确认所有修补条目在游戏内位置正确显示。

### Phase 8 — 发布 GitHub（≈0.5–1h）
- 新建仓库（公开或私有先本地推），目录：`patch/` 发布包 + `docs/` + 变更日志 + 致谢天邈。
- Release 上传压缩包 + SHA256 清单 + 截图。
- **合规**：天邈文本再分发的授权问题——注明"基于天邈汉化 1.4 修补"，若需可先与天邈组沟通或按其社区惯例署名致谢（决策点 D3）。

---

## 3. 智能体职责划分

| 智能体/工具 | 职责 |
|---|---|
| 提取脚本（tools/*.py） | .int 解析、texts.db/dis.db 解析、MD5 验证、对齐建库 |
| LLM 校对智能体（Codex/ChatGPT） | 逐批对照校对，输出结构化提案，标记不确定项；默认复用 ChatGPT 登录 |
| Codex（本环境） | 全流程编排：写脚本、跑流水线、抽检质量、生成审核报告、打包验证 |
| 用户 | 3 次关键人工节点：①术语表确认 ②不确定条目裁决 ③游戏内实测 |

---

## 4. 决策点清单（需用户拍板）

| # | 决策 | 选项 | 推荐 |
|---|---|---|---|
| D1 | 英文源获取方式 | 已有独立英文目录 / Steam 校验恢复 / 网络获取 | **独立英文目录（已落实）**——后续只读提取，不碰游戏状态 |
| D2 | 打包形态 | A. 全量 upk 解压即用(≈4.5GB) / B. 轻量+一键安装(几十MB) / C. 两者都出 | C（A 保体验、B 保体积） |
| D3 | GitHub 发布 | 获得天邈授权后公开 / 授权前仅私有研究 | **先联系并取得许可**——官方 1.4 发布说明明确要求基于其汉化包修改需联系汉化组；仅署名致谢不足以替代授权 |
| D4 | LLM 执行后端 | 当前 ChatGPT/Codex / OpenAI 兼容 API | **当前 ChatGPT/Codex（已定）**——本机 ChatGPT 登录，默认 `gpt-5.6-sol`；API 后端仅作为可选备用，不再等待 DeepSeek key |

---

## 5. 风险与备选

| 风险 | 影响 | 对策 |
|---|---|---|
| texts.db 哈希≠MD5(英文原串) | 英文字幕提取受阻 | 退回"还原英文→直接提取→恢复"流程；或网络找英文字幕表 |
| upk 体积导致包过大 | 解压即用方案受限 | 出双形态包；或仅字幕相关 upk 全量、其余注入 |
| 误改任一游戏源目录 | 游戏不可玩或污染基线 | Phase 1 仅只读扫描；所有中间产物写入工作区，并以提取前后哈希确认源目录未变 |
| 注入工具在修补后的 texts.db 上行为差异 | 字幕错位 | 先在副本 upk 上试运行并 diff；保留天邈原 db 做对照 |
| AI 过度改写破坏"天邈底色" | 社区不认 | prompt 强约束 + 默认 keep + 修改率红线 + 变更日志可追溯 |
| ChatGPT/Codex 套餐额度或速率限制 | 全量校对中途暂停 | 单并发、批次落盘、指数退避；额度恢复后从下一未完成批继续 |
| 模型/提示词变化导致前后批次标准漂移 | 校对口径不一致 | 固化运行清单与哈希；配置变化时旧批次标记过期；疑难项统一二次复审 |
| Codex 输出结构或条目集合不合约 | 批次结果缺失/错位 | JSON Schema + id 全集校验；失败批不提交完成态并自动重试 |
| 二次修改/再分发未获授权 | 公开发布被投诉或下架 | 本地研究可继续；GitHub 公开发布前联系天邈并保存许可，按许可范围署名、分发或仅发布差分工具 |

---

## 6. 里程碑

1. **M0.6（Codex 后端完成）**：无 API key 完成合成批次，结构/校验/断点测试全部通过
2. **M1（提取完成，已达成）**：31,583 条 corpus.jsonl 中英对齐及全部 Phase 1 硬门槛通过 → 进入术语表
3. **M1.5（试跑放行）**：2–5 批校准样本通过误改率、术语、占位符和修改率门槛
4. **M2（校对完成，已达成）**：全部条目出修改提案，修改率/自检达标 → 145 条人工审核
5. **M3（打包完成）**：patch/ 产物通过静态校验 → 用户实测
6. **M4（发布）**：GitHub 仓库 + Release 上线
