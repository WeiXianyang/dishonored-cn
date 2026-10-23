# 本体药剂提示资源标识回显修复

本次补齐 `Twk_Pawn_Corvo.int` 中科尔沃默认对象及 `_Release` 对象缺失的 8 个键鼠教程字段，覆盖首次获得生命／魔力药剂，以及低生命／低魔力时的使用提示。

## 根因与证据

- 游戏 `DefaultGame.ini` 的 `m_CampaignPawnTweak` 指向 `Twk_Pawn_Corvo.Twk_Pawn_Corvo_Release`，`m_DefaultPawnTweak` 指向 `Twk_Pawn_Corvo.Twk_Pawn_Corvo`。
- 两个对应本地化节均只有手柄药剂提示，缺少 `m_AcquiredElixirTutorialMessage_PC[0/1]` 和 `m_UseElixirTutorialMessage_PC[0/1]`。`Twk_Pawn_DefaultPlayer.int` 已有四条完整中文。
- 英文备份的 Corvo INT 同样缺少这些字段，DefaultPlayer 英文和 Startup UPK 中则存在 PC 默认提示。因此，没有证据支持“按键或道具标识符被翻译掉”；问题是具体玩家对象缺少本地化覆盖，与此前达德 DLC 的缺字段问题相同。
- `DefaultInput.ini` 将 `GBA_HealthElixir`、`GBA_ManaElixir` 绑定到两种药剂的消费命令，默认键为 R／T。补丁保留动态标识符，不写死按键。
- 2026-08-19 的修复仅覆盖 DLC06／DLC07（提交 `2c26955`），没有检查 Corvo。仅比较英文／中文 INT 既有键集合，无法发现继承自 UPK 默认对象、但未落到具体 INT 节的属性。

## 修改边界

两个 Corvo 节各增加以下四条，逐值复用 DefaultPlayer 现有译文：

```ini
m_AcquiredElixirTutorialMessage_PC[0]="按 `GBA_HealthElixir` 喝生命药剂。"
m_AcquiredElixirTutorialMessage_PC[1]="按 `GBA_ManaElixir` 喝精神药剂。"
m_UseElixirTutorialMessage_PC[0]="你的生命值过低。按 `GBA_HealthElixir` 喝生命药剂。"
m_UseElixirTutorialMessage_PC[1]="你的魔力值过低。按 `GBA_ManaElixir` 喝魔法药剂。"
```

独立二审确认：新增恰好 8 行；删除新增行后，与输入文件逐字节一致；UTF-16LE BOM、CRLF、所有已有字段及节名保持不变。

## 输入与产物

从 GitHub v1.4p 重新下载并冻结的输入：

| 文件 | 输入 SHA-256 |
|---|---|
| Lite | `c5cf78bb9080645d26928e72cfde61bf4082e2aa9d4f8869b13473791340ca79` |
| Full INT | `693f68a9f6f102896300d43ff7887b75d8528f1803b4acf60ce4b27b949db8ad` |
| Corvo INT | `f045cccc9e8bf6bf3474fec6ff9b8c0687735e3e8d937e9bfac4bb8bbb4a7a40` |

修复后 Corvo INT 为 5,038 字节，SHA-256 为 `6cb8696f54f6332f064d06c256c95bb2f1426646b79f4cce46016c542c9ae9c0`。最终安装包校验值见根目录及 `release/` 下内容一致的 `release-manifest.json`。

与线上输入包逐项比较：Full INT 只改动 Corvo 文件；Lite 只改动 Corvo 文件和 `hashes.json`。其余资源内容完全一致。Lite 校验清单同步目标文件哈希，并删除无法自洽的清单自身哈希。仓库 `release/` 内遗留的旧安装器与废弃还原脚本副本，已统一为实际线上 Lite 的同源构建结果。

## 验证与限制

- 三份本地交付包 CRC、清单哈希及文件数量通过；根目录与 `release/` 的 Lite 逐字节相同，Lite／Full 的 658 份 INT 逐字节相同。
- 检查 DefaultPlayer、Corvo 两节、DLC06／DLC07 各两节，共 7 节、112 个教程字段。
- 旧线上包被新验证器拒绝，明确报告 Corvo 缺少 PC 药剂提示。逐项删除 28 个 PC 字段均被拒绝；中文化标识符、大小写错误、写死按键、未闭合反引号、药剂按键错配及重复字段也被拒绝。另检查 Corvo PC 文案与 DefaultPlayer 精确一致。
- 本机原有游戏成功进入中文主菜单。修复文件已在备份原件后复制到本机游戏目录，并核对哈希；随后电脑控制被用户按 Esc 中止。**本次未完成修复后第一章拾取生命／魔力药剂的实机触发验收，不将静态校验等同于实机验收。**

复核命令（Python 标准库，无额外依赖）：

```text
python -m unittest discover -s tests -v
python tools/verify_player_prompts.py Dishonored-CN-1.4p-Lite.zip release/Dishonored-CN-1.4p-Full-part1-INT.zip
```

已安装 Lite 或 Full 的玩家均可退出游戏，下载最新 Full INT 分卷，解压覆盖到游戏根目录。其他分卷无需重装。需要恢复英文时使用 Steam“验证游戏文件完整性”；维护者的修复前安装包与本机原件保留在本次本地构建备份中。
