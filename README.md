# 《耻辱 1》Dishonored GOTY — 天邈汉化修复补丁 v1.4p

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Game](https://img.shields.io/badge/Game-Dishonored%20GOTY-blue.svg)](https://store.steampowered.com/app/205100)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078d6.svg)](https://store.steampowered.com/app/205100)
[![Release](https://img.shields.io/badge/Release-v1.4p-orange.svg)](https://github.com/WeiXianyang/dishonored-cn/releases)

面向 Windows Steam 版《Dishonored GOTY》的完整中文修复补丁，覆盖本体及 DLC05、DLC06、DLC07。
项目基于天邈汉化组 **v1.4** 进行最小修补：保留原译风格，只修可确认的翻译错误、术语冲突与占位符问题，**不引入第三版译文**。

> ✅ **完全免费、非商业，并已获天邈汉化组授权。** Full 与 Lite 两种形态任选其一，**不要同时安装**。

| 双语语料 | 可审计修补 | 内容覆盖 | 质量管线 |
|:---:|:---:|:---:|:---:|
| **31,583 条** | **6,352 条** | **本体 + 全部 DLC** | **8 阶段审校** |
| 100% 全量对齐 | 原文 / 原译 / 修正 / 理由 | DLC05 / DLC06 / DLC07 | AI 初审 + 人工裁决 + 反方二审 |

**[⬇️ 下载最新版本](https://github.com/WeiXianyang/dishonored-cn/releases/latest)** · **[📖 查看安装教程](安装教程-完整版.md)** · **[🔍 核对 6,352 条修改](changelog.json)** · **[🧰 复用通用汉化修补 Skill](.reasonix/skills/localization-pipeline/SKILL.md)**

> ⭐ 如果补丁或工作流对你有帮助，欢迎点一下右上角的 **Star**。它会帮助更多玩家发现这个项目，也支持作者继续维护。

---

## 🧰 可复用于更多游戏的汉化修补 Skill

本项目把实战方法沉淀成了一个可复制的 **AI 辅助游戏汉化安全修补 Skill**。它不绑定《耻辱》、游戏引擎、文件格式、模型或 AI 平台：UE、Unity、Ren'Py、RPG Maker、自研引擎，以及 CSV、PO、JSON、数据库和提取后的二进制资源都可通过适配器接入。

**直接使用**：复制 [`.reasonix/skills/localization-pipeline/`](.reasonix/skills/localization-pipeline/) 到支持 `SKILL.md` 的 Agent 环境；也可以把 [`SKILL.md`](.reasonix/skills/localization-pipeline/SKILL.md) 直接提供给任意 AI。面向人的完整中文说明见 [`LOCALIZATION_PIPELINE.md`](LOCALIZATION_PIPELINE.md)。

| 通用机制 | 解决的问题 |
|---|---|
| 结构化稳定 ID | 相同文本属于不同对象时不会误合并 |
| 作用域术语 | 防止短词污染复合词、跨场景或跨 DLC 误套术语 |
| 最小修补提案 | 默认保留旧译，只修能证明的硬错 |
| 独立反方二审 | 只允许接受、回退或请求研究，禁止写第三版译文 |
| 格式适配器 | 引擎差异只存在于提取、写回、验证和打包 |
| 确定性发布门 | ID、占位符、结构、覆盖率和回归测试由代码放行 |

快速开始：

```text
我要修补：[游戏 / 版本 / 平台]
语言方向：[源语言] → [目标语言]
原文资源：[路径或获取方式]
现有汉化：[路径或获取方式]
资源格式或引擎：[已知信息]
请按照 Skill 先完成 Phase 0。
```

**[打开 Skill](.reasonix/skills/localization-pipeline/SKILL.md)** · **[阅读中文工作流](LOCALIZATION_PIPELINE.md)** · **[格式适配器指南](.reasonix/skills/localization-pipeline/references/adapters.md)** · **[数据与发布契约](.reasonix/skills/localization-pipeline/references/contracts.md)**

---

## 目录

- [0. 开始之前（准备）](#0-开始之前准备)
- [1. 两种形态怎么选](#1-两种形态怎么选)
- [2. Full 形态安装（解压即用，推荐）](#2-full-形态安装解压即用推荐)
- [3. Lite 形态安装（脚本自动安装）](#3-lite-形态安装脚本自动安装)
- [4. 卸载与还原](#4-卸载与还原)
- [5. 常见问题（Q&A）](#5-常见问题qa)
- [6. 文件清单与校验](#6-文件清单与校验)

---

## 0. 开始之前（准备）

安装前请先确认以下几点：

1. **游戏本体已安装**：通过 Steam 安装《耻辱 1》年度版。安装完成后**先启动一次游戏**（到主菜单即可退出），确认游戏能正常进入英文版。
2. **找到游戏根目录**：在 Steam 库中右键《耻辱 1》→「管理」→「浏览本地文件」，打开的文件夹就是**游戏根目录**。默认位置一般是：
   `C:\Program Files (x86)\Steam\steamapps\common\Dishonored`
   （也可能在其他盘，比如 `C:\SteamLibrary\steamapps\common\Dishonored`、`D:\SteamLibrary\steamapps\common\Dishonored`）
   **游戏根目录的特征**：里面有 `DishonoredGame`、`Binaries`、`Engine`、`DLC` 这几个文件夹。
3. **磁盘空间**：Full 形态解压后约占用 4.3 GB 额外空间（压缩包本身 4.3 GB）；Lite 形态解压后约 73 MB。请预留相应空间。
4. **解压工具**：Windows 自带资源管理器可以解压 zip，但解压 1.5 GB 大分卷时**建议使用 7-Zip 或 WinRAR**（免费，7-Zip 官网：`https://www.7-zip.org`），更稳更快。
5. **杀毒软件提示**：Lite 形态的 `subimport.exe`（天邈注入工具，随包附带）可能被杀毒软件误报。如被拦截，请在杀毒软件中「允许/信任」该文件后重试（本补丁完全无偿、无任何联网行为）。

---

## 1. 两种形态怎么选

| | Full（解压即用） | Lite（脚本安装） |
|---|---|---|
| 体积 | 约 4.31 GB（5 个分卷） | 约 73 MB |
| 安装方式 | 解压覆盖，无需运行任何程序 | 双击 `安装.bat`，自动备份+复制+注入 |
| 耗时 | 解压约 5–15 分钟 | 脚本运行约 4 分钟 |
| 适合谁 | 网络好、想一步到位 | 网络差、或想保留英文原版文件方便还原 |
| 可还原性 | 需 Steam 校验文件完整性 | 需 Steam 校验文件完整性 |
| 对游戏目录的影响 | 覆盖 .int 与字幕 upk | 备份英文原版 .int 到 `_backup_int`，其余同 Full |

**选一个装即可。** 推荐 Full（简单、省心）；网络不好或想留英文备份选 Lite。

---

## 2. Full 形态安装（解压即用，推荐）

### 2.1 下载全部 5 个分卷

Full 形态共 5 个 zip 分卷（因为单文件超过 100 MB，GitHub 不能直接放，所以拆成多卷发布）：

| 文件 | 大小 | 内容 |
|---|---|---|
| `Dishonored-CN-1.4p-Full-part1-Base.zip` | 1,526 MB | 151 个字幕 upk + 3 个中文字体 upk |
| `Dishonored-CN-1.4p-Full-part1-INT.zip` | 2.4 MB | 658 个汉化 `.int` 文件 |
| `Dishonored-CN-1.4p-Full-part2-DLC05.zip` | 1,260 MB | DLC05（顿沃城之锋）字幕 |
| `Dishonored-CN-1.4p-Full-part3-DLC06.zip` | 630 MB | DLC06（布莱格摩尔女巫）字幕 |
| `Dishonored-CN-1.4p-Full-part4-DLC07.zip` | 920 MB | DLC07（Daud 附加内容）字幕 |

**必须全部下载**，缺一个就会缺对应部分的字幕。建议 5 个都放进同一个文件夹再开始解压。

### 2.2 解压到游戏根目录（关键步骤，按顺序）

1. **先确定游戏根目录**（见第 0 节步骤 2）。
2. 用 7-Zip 或 WinRAR 打开 `part1-Base.zip`，点击「**解压到…**」，目标路径选择**游戏根目录本身**（不是游戏根目录里面的某个子文件夹）。
3. 解压时如果提示「是否覆盖同名文件？」——**选择「全部覆盖 / 全部选是 / Yes to All」**（此时游戏里还没有这些文件，一般不会提示；后面几个分卷才会）。
4. **按顺序解压其余分卷，全部解压到同一个游戏根目录**：
   - 第 2 个：`part1-INT.zip`（覆盖 `Localization\INT` 下的 658 个 .int）
   - 第 3 个：`part2-DLC05.zip`（覆盖 `DLC\PCConsole\DLC05`）
   - 第 4 个：`part3-DLC06.zip`（覆盖 `DLC\PCConsole\DLC06`）
   - 第 5 个：`part4-DLC07.zip`（覆盖 `DLC\PCConsole\DLC07`）
   - 每次提示覆盖时都选「全部覆盖」。
5. 解压完成后，可核对：游戏根目录下 `DishonoredGame\Localization\INT` 里的 `.int` 文件应为 **658 个**。

### 2.3 启动游戏验证

1. 打开 Steam → 库 → 找到《耻辱 1》→ 点击「开始游戏」。
2. 游戏语言保持默认英文（INT）即可，**无需在游戏内切换语言**。
3. 验证点：
   - 主菜单（开始游戏 / 继续 / 选项）为中文
   - 进入第一章，对话字幕为中文
   - 人物姓名显示中文（如 皮耶罗、艾米丽）
   - 加载界面提示为中文

### 2.4 Full 安装后想还原英文

见第 4 节（用 Steam 校验文件完整性即可还原全部被覆盖文件）。

---

## 3. Lite 形态安装（脚本自动安装）

### 3.1 下载并解压

1. 下载 `Dishonored-CN-1.4p-Lite.zip`（约 73 MB）。
2. 解压到**任意临时位置**（比如桌面），解压后你会看到这些内容：

```
（解压出的文件夹）
├── DishonoredGame\        ← 658 个汉化 .int
├── CNPatch\Upks\          ← 6 个中文字体/UI upk
├── Sub_Import\            ← 天邈注入工具（subimport.exe、texts.db 等）
├── 安装.bat
├── README.md
└── hashes.json
```

### 3.2 双击运行 安装.bat（自动查找游戏目录）

**不需要手动移动任何文件**——解压文件夹放在哪都行（桌面、下载文件夹、D 盘均可）。

1. **先完全退出游戏**（若正在运行）：游戏进程会锁定 `.upk` 文件导致安装无效，脚本会检测到并阻止安装。
2. 双击解压文件夹里的 `安装.bat`。
3. 脚本会自动查找游戏目录（依次尝试：Steam 注册表默认库 → C~G 盘常见 Steam 库 → 当前文件夹就是游戏根目录），找到后显示：

   ```
   Found your Dishonored folder:
     C:\SteamLibrary\steamapps\common\Dishonored
   Use this folder? [Y/N] (default Y):
   ```

   确认路径无误，直接按回车（或输入 `Y`）即可开始安装。

4. **找不到游戏目录 / 想装到指定目录**（手动填写）：输入 `N` 或脚本没检测到时，会提示：

   ```
   Could not auto-detect the game folder.
   Please type your Dishonored game folder:
   ```

   手动输入游戏根目录的完整路径后回车，例如：

   ```
   D:\Games\Dishonored
   ```

   **游戏根目录的特征**：里面有 `DishonoredGame`、`Binaries`、`Engine`、`DLC` 这几个文件夹（不是里面的 `DishonoredGame` 子文件夹）。路径填错会显示 `[ERROR]` 并退出，重新双击运行再填一次即可。

### 3.3 安装过程

脚本依次显示 5 步（约 3-4 分钟，期间不要关闭窗口）：

| 步骤 | 显示 | 做什么 | 耗时 |
|---|---|---|---|
| 1/5 | `Backing up original .int files to _backup_int ...` | 备份英文原版 658 个 .int 到 `_backup_int` 文件夹 | 几秒 |
| 2/5 | `Copying localized .int files ...` | 覆盖为汉化 .int | 几秒 |
| 3/5 | `Copying font/UI packages (.upk) from CNPatch\Upks ...` | 复制 6 个中文字体/UI upk | 几秒 |
| 4/5 | `Injecting subtitles into .upk files via Tianmiao tool ...` | 运行 subimport.exe 把字幕写入 151 个 upk，**此步会弹出子窗口且最久** | **约 3 分钟** |
| 5/5 | `Restoring font/UI packages after injection ...` | 注入会把字体 upk 改回英文，此步重新覆盖为天邈字体 upk | 几秒 |

1. 最后显示 `Install finished.` 并停留等待按键——按任意键关闭即可，**安装完成**。
2. 提示：第 4 步运行时如果看到 subimport 的子窗口（`程序处理文件中，请不要关闭本窗口…`），**不要关闭它**，等它自己跑完（约 3 分钟，看到 `* 处理完毕 *` 即为结束）。
3. 若某步显示 `[WARN] ... could not be overwritten`，说明游戏还在运行，**完全退出游戏后重新运行** `安装.bat`。

### 3.4 启动游戏验证

同 2.3：主菜单中文、对话字幕中文、人物姓名中文、加载提示中文。

### 3.5 还原英文（卸载）

通过 **Steam 校验文件完整性** 还原：Steam 库 → 右键《耻辱 1》→ 属性 → 本地文件 → **验证游戏文件完整性**。Steam 会自动下载还原被覆盖/修改的文件（含字幕/字体 upk 与本地化文件）。

> 还原英文后想再玩汉化，重新运行 `安装.bat`（或重解压 Full 包）即可。

---

## 4. 卸载与还原

| 场景 | 方法 |
|---|---|
| 想还原英文（Lite 或 Full 装过） | Steam 库 → 右键《耻辱 1》→ 属性 → 本地文件 → **验证游戏文件完整性**（Steam 会自动下载还原被覆盖/修改的文件，含字幕 upk 与本地化文件） |
| 想重装本补丁 | 先按上表还原，再重新走 Full 或 Lite 安装流程 |

---

## 5. 常见问题（Q&A）

### Q1：游戏里中文全是方块（□）
- 原因：中文字体/UI upk（`DisFonts_*.upk`、`Startup.upk`、`DishonoredGame.upk`、`UI_Loading_SF_LOC_INT.upk`）没装上，或 Lite 安装时第 3/5 步没生效。
- 解决（Lite）：确认游戏根目录存在 `CNPatch\Upks`，重跑 `安装.bat`，确认 5 步都显示且第 3、5 步无 `[WARN]`。
- 解决（Full）：确认 5 个分卷都解压覆盖了，尤其是 `part1-Base.zip`。

### Q2：游戏里人名/部分文字还是英文
- 原因：`Localization\INT` 下的 .int 没被覆盖（Full 漏了 `part1-INT.zip`，Lite 第 2 步没生效）。
- 解决：重新解压 `part1-INT.zip` 覆盖（或重跑 Lite `安装.bat`），确认 `.int` 数量为 658。

### Q3：字幕是中文但某些 UI/任务文字是英文
- 多为游戏缓存问题：完全退出游戏后重启；或先在游戏内把语言切到其它语言再切回英文（INT）。
- 仍不行 → Steam 校验完整性后再重装补丁。

### Q4：Steam 更新游戏或「验证完整性」之后变回英文了
- 正常现象：Steam 校验/更新会还原被修改的文件。重装补丁即可（Full 重解压 / Lite 重跑 `安装.bat`）。

### Q5：杀毒软件拦截 `subimport.exe` / 报毒
- `subimport.exe` 是天邈汉化组 2015 年的注入工具，无任何联网行为。请在杀毒软件中「信任/允许」后重试。本补丁所有文件均附 SHA-256 清单（`hashes.json` / `release-manifest.json`）可核验，绝无恶意代码。

### Q6：双击 `安装.bat` 闪一下就没了 / 提示找不到 `DishonoredGame`
- 说明 `安装.bat` 不在游戏根目录运行。把解压出的内容放到游戏根目录（与 `Binaries`、`DLC` 同级）后再双击。

### Q7：游戏启动就崩溃（黑屏退出 / 报错）
- 如果游戏装在**含中文的路径**下（如 `D:\游戏\Dishonored`），请把游戏目录改到纯英文路径（Steam 默认路径都是英文，一般无此问题）。
- 确认是以 Steam 方式启动（在 Steam 库里点开始，不是直接双击 `Dishonored.exe`）。

### Q8：装了补丁后想完全回到英文原版
- 见第 4 节：Steam「验证游戏文件完整性」。

### Q9：Lite 安装到一半关掉了 / 中途断电
- 重新双击 `安装.bat` 即可（第 1 步会检测到 `_backup_int` 已存在，不会重复备份）。

---

## 6. 文件清单与校验

- `release-manifest.json`：Full 5 个分卷 + Lite 的 SHA-256 校验值。
- `hashes.json`（Lite 包内）：Lite 全部文件 SHA-256 校验值。
- `changelog.json`：全部 6,352 条修改明细（每条含 英文原文 / 天邈原译 / 修正后译文 / 修改理由），**公开可审计**。

校验方法（可选）：将下载的 zip 拖入 7-Zip 或使用 `certutil -hashfile 文件名 SHA256` 比对清单中的值，一致即文件完整。

---

## 说明

本补丁基于天邈汉化组《耻辱》v1.4 汉化版本修改。

作者：WeiXianyang
