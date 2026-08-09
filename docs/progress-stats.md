# 项目工作量统计（实时更新）

> 本文件汇总《耻辱 1》汉化补丁全流程的阶段性工作量，随每个 Phase 完成实时更新。
> 最终将摘入项目介绍 / README。数据来源：PLAN.md 阶段记录 + docs/ 各阶段报告 + data/review/ 实际产物。

最后更新：Phase 7 Full + Lite 实测全部通过（2026-08-09）

---

## 总览

| 阶段 | 状态 | 核心产出 / 修补数量 |
|---|---|---|
| Phase 0 / 0.6 | ✅ 完成 | 解析器 + 校对流水线（Codex/ChatGPT 登录复用） |
| Phase 1 | ✅ 完成 | 31,583 条双语语料 |
| Phase 2 | ✅ 完成 | 618 条正式术语锁 |
| Phase 3 | ✅ 完成 | 6,398 个修补（全量审校） |
| 术语安全整改 | ✅ 完成 | 6,352 个修补（防过修回调） |
| Phase 4 | ✅ 完成 | 6,468 个修补（人工项归零） |
| Phase 4.5 | ✅ 完成 | 5,251 条反方二审 → keep 4,345 / fix 906 / uncertain 218 全定夺 |
| Phase 5 | ✅ 完成 | patch/ 产物：196 .int（2,058 条）+ texts.db（4,085 条）+ 配套（37.7 MB） |
| Phase 6 | ✅ 完成 | release/ 双形态：Full 4.31GB（151 upk 注入 + 天邈 3 upk）+ Lite 73.4MB（680 文件）；SHA-256 清单 |
| Phase 7 | ✅ Full 与 Lite 实测均通过 | Full：修复 3 大漏项（.int 239→658、Startup/DishonoredGame/UI_Loading）；Lite：修复 subimport 改写 Startup + bat CRLF；全量 5,536 文件比对 0 异常；用户实机确认主菜单/人名/字幕全中文 |
| Phase 8 | ⏳ | GitHub 发布（前置：天邈授权） |

---

## Phase 1 — 双源文本提取

- 唯一语料：**31,583 条**（aligned 31,545 + 规范化 23 + 英文独有 12 + 中文独有 3）
- `.int` 文本叶子并集：21,299
- UPK 字幕对齐：**10,284 / 10,284**（0 缺失、0 哈希不符）
- texts.db 解析：10,284/10,284（值差异 0）
- 格式硬阻断：0；1,639 个源文件 SHA-256 前后一致
- 待办结构警告：38 条（带入 Phase 2/打包）

## Phase 2 — 术语表建设

- 候选 1,200 条：首审 24 批 + 二审 7 批 + Wiki 疑难 20 项，失败 0
- **正式术语锁 618 条**（51.50%）、明确排除 574 条（47.83%）、上下文分流 8 条
- 冲突/别名碰撞裁决 210 组；Wiki 事实核查 20 项

## Phase 3 — AI 校对流水线

- 全语料分类：31,583 / 31,583（100%）
- Medium：22,034/22,034（552/552 批，keep 15,976 / fix 6,058 / uncertain 200）
- High 升级复审：2,764/2,764（139/139 批）
- **最终接受修补 6,398 条**；High 明确回退 104；人工审核 145（0.459%）
- 33 条人工规则覆盖 127 个稳定 ID；2 条 P0 错译修复

## 术语安全整改（Phase 3 → 4 之间）

- 619 条旧术语全量复审 → 228 全局硬锁 + 388 作用域候选 + 3 移除，35 个译值纠错
- 受术语影响成品二审 1,207 条：keep 795 / fix 412（187 条恢复天邈原译）
- 成品修补量：6,468 → **6,352**

## Phase 4 — 人工审核

- 145 条人工项全部裁决：fix 70 / keep 75，**人工项降为 0**
- 二次独立验收纠正 8 条 + 修复 `Regent's Safe Room` 术语污染
- 全语料最终修补：**6,468 / 31,583**

## Phase 4.5 — 防过修稳定化 release gate

- 入审候选 5,251 条（= 6,352 − 1,012 已独立术语二审 − 89 非零售回退）
- 风险队列：critical 1,822 / high 2,652 / medium 714 / low 63（266 批）
- **最终裁决：keep（接受候选）4,345 条 / fix（回退天邈）906 条**
- uncertain 218 条全部定夺：本地规则库 ~100、上下文邻居 ~100、Fandom API 3、用户决策 2
- 错误疫苗 13/13 通过

### Phase 4.5 分队列明细

| 队列 | 条目 | 接受候选（修补） | 回退原译 |
|---|---|---|---|
| critical | 1,822 | 1,661 | 161 |
| high | 2,652 | 2,112 | 540 |
| medium | 714 | 512 | 202 |
| low | 63 | 60 | 3 |
| **合计** | **5,251** | **4,345** | **906** |

- 本会话（session-ai 后端）承担：3,644 条续跑 + 218 条 uncertain 定夺；codex 缓存 1,607 条
- 最终全队列 uncertain = 0，wiki_lookup_queue 清空

---

## Phase 5 — 合并生成（已完成 2026-08-09）

- 基底：`data/review/phase4-term-reviewed/accepted_fixes.jsonl`（6,352 条候选）叠加 Phase 4.5 裁决 → 6,352 条 decisions（`data/review/phase5_decisions.csv`）
- 产物 `patch/`（246 文件 / 37.7 MB）：
  - `DishonoredGame/Localization/INT/*.int`：196 个文件、**2,058 条修改**（UTF-16 LE + BOM + CRLF、键序保持源文件）
  - `Sub_Import/texts.db`：**4,085 条修改**（pickle0 格式，最小 diff，幂等验证字节一致）
  - `Sub_Import/dis.db`、`upklist.db`、`DishonoredGame/CookedPCConsole/DisFonts*.upk`：原样复制
  - `changelog.json`（6,352 条明细）、`hashes.json`（SHA-256）、`README.md`
- 验证：幂等重跑 .int 0 修改；9 条未写回边界（7 en_only + 1 天邈源畸形 + 1 [Name] 占位符）

## Phase 6 — 打包（已完成 2026-08-09）

- 双形态：Full（解压即玩）+ Lite（.int + 注入工具 + 安装/还原 bat）
- Full 151 字幕 upk 经天邈 subimport.exe 注入（texts.db = 天邈 + 修补 4,085 条）；内容级抽查英文残留 0
- 5 个分卷 zip（按 GitHub 2GB 限制）：Base / INT / DLC05 / DLC06 / DLC07；全部 CRC 校验通过
- Lite：680 文件 / 73.4 MB；SHA-256 清单 `release-manifest.json`

### Phase 7 静态验证 → 补全汉化（重大修正，2026-08-09）

实机首测发现三大漏项并全部修复：

| 漏项 | 影响 | 修复 |
|---|---|---|
| 365 个天邈汉化 `.int` 未纳入补丁（Phase 1 语料仅覆盖 239 个文件） | 英文原版上人物名/对话/任务/物品全为英文 | 补丁 .int 从 239 → **658 全量**（239 个含修补 + 419 个天邈原版） |
| `Startup.upk`（天邈手工修改引擎字体，subimport 注入版=英文原版） | 对话字幕中文方块（字形缺失） | 补丁纳入天邈版 `Startup.upk` |
| `DishonoredGame.upk` / `UI_Loading_SF_LOC_INT.upk`（天邈手工修改 Flash UI/字体） | 主菜单/UI 英文、加载提示方块 | 补丁纳入天邈版两文件 |

- 全量静态验证：天邈版 vs 测试副本 5,536 个文件比对 → 5,147 一致 + 389 预期差异（修补 .int + 注入 upk），**0 异常、0 多余**
- patch/ 现为 670 文件（658 .int + 6 upk + Sub_Import + 清单）；release 重建：Base 76 文件 / 1,526 MB、INT 658 文件 / 2.43 MB、Lite 680 文件 / 73.4 MB
- **注意**：365 个补入的 .int 为天邈原版（未经过 Phase 3/4.5 的修补审查，修补范围原为 239 个 .int；如需可列为后续 Phase 9 扩充审查）

### Phase 7 Lite 实测（2026-08-09）

在用户重装的干净英文原版上完成 Lite 全链路实测，又发现并修复 2 个 Lite 专属问题：

| 问题 | 根因 | 修复 |
|---|---|---|
| `Startup.upk` 安装后被改写回英文原版 | **subimport.exe 运行时会把 `Startup.upk` 重写为英文原版**（Full 包不跑 subimport 故不受影响；Lite 每次安装都触发） | upk 独立存放 `CNPatch/Upks/`（不再解压即覆盖），安装.bat 步骤 [5/5] 在 subimport 注入**之后**从 `CNPatch\Upks` 重新复制 6 个 upk 覆盖回去 |
| 安装.bat 报 `'cho' is not recognized` / `Install finished` 被拆成命令 / `if` 语句失败（exit 255） | bat 文件 **LF 换行**（write_file 默认）→ Windows cmd 批处理解析器错乱（echo 吞字符、if 解析失败） | bat 改为 **CRLF 换行**（build_lite.py 固化 to_crlf）+ echo 全部 ASCII |

- Lite 安装.bat 流程：`[1/5] 备份 .int → [2/5] 复制 658 .int → [3/5] 复制 6 upk → [4/5] subimport 注入（151/151）→ [5/5] 重放 upk`，实测 exit=0、注入 2 分 54 秒
- 安装后静态验证：**6 upk 全部 = 天邈版哈希**（Startup `b3e0dac4ec69`、DishonoredGame `74d1fec01048`、UI_Loading `938fbc4cbb84`）、`.int` 658 全 = 补丁版、`_backup_int` 备份 658 个成功
- **用户实机确认**：主菜单/UI、人物名、字幕全部正常中文，与 Full 一致
- 还原.bat 同样 CRLF 化（备份恢复链路可用）；release 已重建（Lite zip 内 安装.bat 已 CRLF、`CNPatch/Upks/Startup.upk` = 天邈版）

## 最终口径（Phase 4.5 后）

- 语料 31,583 条，覆盖 100%
- 有效修补：4,345（Phase 4.5 keep）+ 1,012（已独立术语二审）= **5,357 条左右**（精确值以 Phase 5 写回清单为准）
- 其余条目保留天邈原译；格式 / 术语 / 占位符验收 0 错误、0 警告
- 人工项 0、uncertain 0
