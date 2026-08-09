# 《羞辱 1》Dishonored GOTY — 天邈汉化修复补丁 v1.4p

基于天邈汉化组《羞辱》年度版天邈汉化 **v1.4**（2015.12.30）的最小修补版。
在保留天邈译文风格与全部内容的**前提下**，仅订正翻译错误、术语冲突与占位符问题，**不引入第三版译文**。

> ⚠️ 公开发布需先取得天邈汉化组授权（已向其负责人提交授权申请，承诺无偿、非商业、完整署名致谢、修改清单全公开、收到异议立即下架）。

---

## 🔧 通用汉化修补工作流

本项目沉淀了一整套 **AI 辅助游戏汉化最小修补工作流**，任何 AI 工具均可使用——**不绑定特定平台**。

**使用方式**：将 [`LOCALIZATION_PIPELINE.md`](LOCALIZATION_PIPELINE.md) 全文复制粘贴给任意 AI（ChatGPT、Claude、Reasonix、Cursor 等），然后告诉 AI 你的项目信息即可开始。

### 8 阶段审校管线

```
Phase 0 环境 → Phase 1 提取对齐 → Phase 2 术语表 → Phase 3 AI校对
→ Phase 4 人工审核 → Phase 4.5 反方二审 → Phase 5 合并生成
→ Phase 6 打包 → Phase 7 验证
```

### 核心机制

| 机制 | 作用 |
|---|---|
| **术语作用域分离** | 硬锁（全局强制）vs 作用域候选（限定语境），防止子串污染 |
| **双层 AI 审校** | Medium 全量首审 + High 疑难复审，uncertain → Wiki 查证 → 人工 |
| **反方二审（Phase 4.5）** | 独立 Agent 隐藏首轮理由，只允许接受/回退/研究，禁止写第三版译文 |
| **错误疫苗库** | 已知错误类型固化回归测试，每轮 100% 通过才放行 |
| **最小 diff 写回** | UTF-16 LE+BOM+CRLF+键序不变，仅替换修改条目 |

### 如何使用

1. 打开 [`LOCALIZATION_PIPELINE.md`](LOCALIZATION_PIPELINE.md)
2. 全文复制
3. 粘贴给任意 AI 工具，并附上你的项目信息：

```
我正在修复 [游戏名] 的汉化。
英文源目录：[路径]
中文源目录：[路径]
请按照本文档的工作流，从 Phase 0 开始。
```

AI 会按 8 个阶段逐步引导你完成全部流程。

> 📖 完整工作流文档：[`LOCALIZATION_PIPELINE.md`](LOCALIZATION_PIPELINE.md)

---

## 补丁内容

- **6,352 条**修改明细（`changelog.json`：id / 英文 / 原译 / 新译 / 理由）
- 全程 8 个阶段审校：提取 → 术语表 → AI 全量校对 → 人工审核 → 反方二审 → 写回 → 打包 → 实机验证

## 双形态安装包

| 形态 | 说明 | 体积 |
|---|---|---|
| **Full**（5 分卷 zip） | 解压覆盖即玩，已含 151 个注入字幕 upk + 天邈手工修改的字体/UI upk | 4.31 GB |
| **Lite** | 安装脚本形态：备份 → 复制 .int → 复制字体/UI upk → 天邈 subimport 注入 → 还原脚本 | 73.4 MB |

Full 分卷（按 GitHub 2GB 限制拆分，需全部下载）：

```
Dishonored-CN-1.4p-Full-part1-Base.zip    1,526 MB   (76 文件：字幕 upk + 字体)
Dishonored-CN-1.4p-Full-part1-INT.zip       2.4 MB   (658 个 .int)
Dishonored-CN-1.4p-Full-part2-DLC05.zip   1,260 MB   (31 文件)
Dishonored-CN-1.4p-Full-part3-DLC06.zip     630 MB   (21 文件)
Dishonored-CN-1.4p-Full-part4-DLC07.zip     920 MB   (28 文件)
```

所有文件 SHA-256 见 `release-manifest.json`（也可 `git hash-object` 复核）。

---

## 工作量统计（Phase 1–7）

| 阶段 | 成果 |
|---|---|
| Phase 1 提取 | 31,583 条双语语料（.int + UPK 字幕 10,284/10,284 对齐，0 缺失） |
| Phase 2 术语表 | 618 条正式术语锁（Wiki 事实核查 20 项，冲突裁决 210 组） |
| Phase 3 AI 校对 | 31,583 条全量分类（100%），最终修补 6,398 条，33 条人工规则 |
| 术语安全整改 | 619 条旧术语全量复审 → 228 硬锁；修补量回调防过修 → 6,352 |
| Phase 4 人工审核 | 145 条人工项全部裁决（fix 70 / keep 75），人工项归零 |
| Phase 4.5 反方二审 | 5,251 条入审 → **keep 4,345 / fix 906**；uncertain 218 条全部定夺归零 |
| Phase 5 写回 | 196 个 .int（2,058 条）+ texts.db（4,085 条），幂等验证 0 二次修改 |
| Phase 6 打包 | Full 4.31GB（151 upk 注入）+ Lite 73.4MB，CRC 全过 |
| Phase 7 实机验证 | 修复 5 大漏项（365 .int、Startup/DishonoredGame/UI_Loading、subimport 改写、bat CRLF）；5,536 文件比对 0 异常；**主菜单/人名/字幕全中文实测通过** |

Phase 4.5 裁决明细：critical 1,822 → keep 1,661 / fix 161；high 2,652 → keep 2,112 / fix 540；
medium 714 → keep 512 / fix 202；low 63 → keep 60 / fix 3。

全部 6,352 条修改明细（含英文原文 / 天邈原译 / 修正译文 / 理由）见 [`changelog.json`](changelog.json)。

---

## 安装

> 📖 **完整图文教程（推荐先看）：[`安装教程-完整版.md`](安装教程-完整版.md)** —— 覆盖每一步操作、预期画面、常见问题排查。
> 以下为核心步骤速览。

### 准备工作

1. 游戏本体已通过 Steam 安装，并已成功启动过一次（进入主菜单即可）。
2. 找到**游戏根目录**：Steam 库 → 右键《羞辱 1》→「管理」→「浏览本地文件」。根目录的特征：里面有 `DishonoredGame`、`Binaries`、`Engine`、`DLC` 四个文件夹。
3. 预留磁盘空间：Full 约 4.3 GB，Lite 约 73 MB。
4. 大分卷解压建议用 **7-Zip / WinRAR**（7-Zip 官网 `https://www.7-zip.org`，免费）。

### Full（推荐，解压即用）

1. 下载**全部 5 个分卷** zip（缺一不可）：

   | 分卷 | 大小 |
   |---|---|
   | `Dishonored-CN-1.4p-Full-part1-Base.zip` | 1,526 MB |
   | `Dishonored-CN-1.4p-Full-part1-INT.zip` | 2.4 MB |
   | `Dishonored-CN-1.4p-Full-part2-DLC05.zip` | 1,260 MB |
   | `Dishonored-CN-1.4p-Full-part3-DLC06.zip` | 630 MB |
   | `Dishonored-CN-1.4p-Full-part4-DLC07.zip` | 920 MB |

2. **按顺序**把每个分卷解压到**游戏根目录**（解压目标选游戏根目录本身，不是里面的子文件夹）；提示「是否覆盖」时一律选**「全部覆盖 / Yes to All」**：
   先 `part1-Base` → `part1-INT` → `part2-DLC05` → `part3-DLC06` → `part4-DLC07`。
3. 启动游戏（Steam 库里点「开始游戏」），语言保持英文（INT）即可显示中文。
4. 验证：主菜单中文、对话字幕中文、人物姓名中文（皮耶罗/艾米丽）、加载提示中文。

### Lite（脚本自动安装）

1. 下载 `Dishonored-CN-1.4p-Lite.zip`（约 73 MB），解压到任意位置。
2. 把解压出的**全部内容**（`DishonoredGame`、`CNPatch`、`Sub_Import`、`安装.bat`、`还原.bat` 等）放进游戏根目录——与游戏根目录里已有的 `Binaries`、`Engine`、`DLC` **同一层**（提示覆盖时选「全部」）。**不要**放进 `DishonoredGame` 里面。
3. 双击 `安装.bat`，等待 5 步自动完成（约 4 分钟；其中第 4 步运行 `subimport.exe` 注入字幕约 3 分钟，**期间不要关闭任何窗口**）：
   - `[1/5]` 备份英文原版 658 个 `.int` 到 `_backup_int/`
   - `[2/5]` 复制汉化 `.int`
   - `[3/5]` 复制中文字体/UI upk
   - `[4/5]` `subimport.exe` 注入字幕（约 3 分钟）
   - `[5/5]` 重放天邈手工 upk（防止第 4 步把字体 upk 改回英文）
4. 最后显示 `Install finished.` 即完成，启动游戏验证（同 Full 第 4 点）。
5. 还原：双击 `还原.bat` 恢复英文 `.int`；彻底还原用 Steam「验证游戏文件完整性」。

> 注：`subimport.exe` 是天邈注入工具，需要 Python 2.7 运行库（已随包附带）；若被杀毒软件误报请「信任/允许」后重试。

### 常见问题速查（详见完整教程）

| 现象 | 原因与处理 |
|---|---|
| 中文全是方块 □ | 字体/UI upk 没装上：Full 检查是否解压了 `part1-Base`；Lite 重跑 `安装.bat` 确认第 3、5 步无 `[WARN]` |
| 人名/部分文字是英文 | `INT` 目录的 .int 没覆盖全：重新解压 `part1-INT.zip`（或重跑 Lite），确认 `.int` 为 658 个 |
| Steam 更新/校验后变英文 | 正常：Steam 会还原被修改的文件，重装补丁即可 |
| 启动崩溃 | 游戏路径不能含中文；必须从 Steam 库启动 |

---

## 致谢

- **天邈汉化组**（[其乐发布帖](https://keylol.com/t101091-1-1) / [Steam 群组](https://steamcommunity.com/groups/tianmiao) / [微博](https://weibo.com/disthaven)）：本补丁 95%+ 译文来自天邈 v1.4，仅订正约 4.7% 的翻译问题；未取得授权前不公开发布。
- 修改明细 `changelog.json` 全部公开可审计。

---

## 反馈与贡献

### 关于本补丁（作者的话）

本补丁只是在天邈汉化组 v1.4 基础上的**一点小小修补**：95%+ 的译文都是天邈的成果，我做的仅仅是其中约 4.7% 的订正。由于个人能力与精力有限，翻译与排版难免仍有疏漏，**恳请各位玩家批评指正**——每一条反馈我都会认真对待，尽快核实、修订。

### 反馈方式

- 在仓库 **Issues** 中提交问题，尽量包含：游戏版本（年度版 / GOTY）、问题位置（主菜单 / 某章字幕 / 某件物品说明）、截图或英文原文、以及您认为更合适的译文。
- 也可以直接在本页评论区留言。
- 我会**定期查看并逐一处理**每条反馈；确认为误译的，会尽快修复并更新发布包，再在更新说明中注明。

### 贡献代码（Pull Request）

如果您愿意直接动手改进，非常欢迎提交 PR：

- 请遵循本项目的**最小修补原则**：只订正错误，不重写天邈的译文风格；保持源文件格式不变（UTF-16 LE + BOM、键序、换行）。
- 每条修改请在 [`changelog.json`](changelog.json) 中登记（英文原文 / 原译 / 新译 / 理由），保持全程可审计。
- 拿不准的地方建议先开 Issue 讨论，避免返工；涉及大量改动前，也欢迎先与我沟通方向。

---

## 已知边界

- 补入的 419 个天邈原版 `.int`（未在本项目修补范围内翻译修正过）为原样保留，仅作为缺失文件补全，未做二次审查（修补范围原为 239 个 .int 文件）。
- 9 条写回边界：7 条英文独有字段、1 条天邈源缺引号畸形、1 条 `[Name]` 占位符（按决策保留英文）。
