# 耻辱1 汉化补丁 — Phase 5 写回产物

> 基于天邈汉化组 Dishonored GOTY 中文补丁 v1.4（用户提供备份）的最小修补版。
> 所有修改经过 Phase 1–4.5 全流程审校与 release gate 反方二审。

## 内容

```
DishonoredGame/Localization/INT/*.int     196 个 .int（UTF-16 LE + BOM，键序与格式保持源文件）
DishonoredGame/CookedPCConsole/DisFonts*.upk   中文字体（原样）
Sub_Import/texts.db                       新字幕库（仅修改被修条目，pickle0 格式）
Sub_Import/dis.db / upklist.db            注入工具索引（原样）
changelog.json                            修改清单（6,352 条：id/en/old/new/reason）
hashes.json                               全部文件 SHA-256 校验清单
```

## 修改规模

- 入审候选：5,251 条（critical 1,822 / high 2,652 / medium 714 / low 63）
- 接受候选（修补成立）：4,345 条；回退天邈原译：906 条；uncertain 218 条全部定夺归零
- 实际写回：.int 2,058 条（196 文件）+ texts.db 4,085 条 = 6,143 条值修改
- 未写回边界（9 条）：
  - 7 条 en_only（天邈中文 .int 无对应字段，如 DLC05 Expert Mode 描述、Steam 断线提示）
  - 1 条天邈源缺引号畸形（DLC07_Twk_Store InWorldStore m_StoreItems[4] m_Description）
  - 1 条占位符 [Name]（按用户决策保留英文原样，已写入 texts.db 侧对应条目或 .int 可定位处）

## 安装

1. 备份原游戏目录（或使用 Steam 验证文件完整性还原）。
2. 将 `DishonoredGame/` 下内容覆盖到游戏 `DishonoredGame/` 对应位置。
3. 运行天邈注入工具 `Sub_Import/subimport.exe`（将 texts.db 写入字幕 upk；需 Python27 运行库，已含于 Sub_Import）。

## 卸载

用备份还原 `DishonoredGame/Localization/INT/*.int` 与被注入的 upk；或 Steam 校验完整性。

## 校验

- 所有文件 SHA-256 见 `hashes.json`。
- .int 保持源编码/换行/键序（最小 diff）；texts.db 仅修改被修条目。
- 变更明细（每条：id/英文/旧中文/新中文/理由）见 `changelog.json`。
