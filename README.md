# 《羞辱 1》Dishonored GOTY — 天邈汉化修复补丁 v1.4p

基于天邈汉化组《羞辱》年度版天邈汉化 **v1.4**（2015.12.30）的最小修补版。
在保留天邈译文风格与全部内容的**前提下**，仅订正翻译错误、术语冲突与占位符问题，**不引入第三版译文**。

> ⚠️ 本仓库当前为**私密**。公开发布需先取得天邈汉化组授权（已向其负责人提交授权申请，承诺无偿、非商业、完整署名致谢、修改清单全公开、收到异议立即下架）。

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

详细分阶段报告见 `docs/`（Phase 1–4.5 验收清单、术语决策、Wiki 研究、工作流规范、授权申请函等）。

---

## 安装

### Full（推荐，解压即用）

1. 备份游戏目录，或准备 Steam 干净副本；
2. 下载全部 5 个分卷 zip，**依次解压到游戏根目录覆盖**（part1-Base 先，然后 INT、DLC05、DLC06、DLC07）；
3. 启动游戏，语言选英文（INT）即可显示中文。

### Lite（安装脚本形态）

1. 将 `Dishonored-CN-1.4p-Lite.zip` 解压到游戏根目录；
2. 双击运行 `安装.bat`：
   - `[1/5]` 备份英文原版 658 个 `.int` 到 `_backup_int/`
   - `[2/5]` 复制补丁 `.int`
   - `[3/5]` 复制中文字体/UI upk
   - `[4/5]` 运行天邈 `subimport.exe` 注入字幕（约 3 分钟）
   - `[5/5]` 重放天邈手工 upk（防 subimport 改写）
3. 卸载：运行 `还原.bat`（恢复备份），或 Steam 验证文件完整性。

> 注：`subimport.exe` 需要 Python 2.7 运行库（已随包附带）。

---

## 致谢

- **天邈汉化组**（[其乐发布帖](https://keylol.com/t101091-1-1) / [Steam 群组](https://steamcommunity.com/groups/tianmiao) / [微博](https://weibo.com/disthaven)）：本补丁 95%+ 译文来自天邈 v1.4，仅订正约 4.7% 的翻译问题；未取得授权前不公开发布。
- 修改明细 `changelog.json` 全部公开可审计。

---

## 已知边界

- 补入的 419 个天邈原版 `.int`（未在本项目修补范围内翻译修正过）为原样保留，仅作为缺失文件补全，未做二次审查（修补范围原为 239 个 .int 文件）。
- 9 条写回边界：7 条英文独有字段、1 条天邈源缺引号畸形、1 条 `[Name]` 占位符（按决策保留英文）。
