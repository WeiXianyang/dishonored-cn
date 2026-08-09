# Phase 3 最终校准验收

> 验收日期：2026-08-06  
> 固定样本：`data/review/phase3-samples/calibration_corpus.jsonl`  
> 最终配置哈希：`ee85d83772220818589f276ed86c82b44f39600171f44325ffaac242dc5178374`

## 运行结果

- 5/5 批次、200/200 条成功，批次失败与重试均为 0。
- `fix=66`，`keep=134`，`uncertain=7`，不确定率 3.5%。
- 输入 166,184 tokens，输出 31,454 tokens，其中推理 11,745 tokens。
- 标签、换行、按键标识符、术语、ID 和 JSON 契约的硬违规均为 0。

## 人工门检

- 66 条 `fix` 和 7 条 `uncertain` 已全部逐条对照英文/旧译/新译/理由。
- 从 134 条 `keep` 中按 ID SHA-256 固定抽取 35 条审查，未发现高置信度的明显漏修。
- 66 条修补中有 2 条已主动标记 `uncertain`，不直接放行：`Gaffer's Tale` 长文与含 `ricker` 俚语的字幕。
- 剩余 64 条确定性修补中发现 1 条语气过重的误改：
  - `upk:F0F6BD40ADBECE02CA08FDAB2DADB869`：旧译“您是怎么从那些最聪明的人中脱颖而出的”虽不贴字，但在下属恭维 Timsh 的语境中成立；新译“你觉得自己凭什么算得上”显得质疑。该条路由 High 复审，不直接放行。
- 确定性修补误改率为 `1/64 = 1.56%`，低于 5% 放行红线。
- 样本修改率为 33%，高于“原则上 30%”但低于 35% 停止红线。该固定集有意过采样 8 条缺译、两条 P0、已知规范化异常和长文，不代表全语料的自然修改率。

## 校准中修复的流水线问题

1. 取消“只要旧中文含正式译名就反向锁死”的规则，避免把长文里的普通词“帮助”误当成 `Favor` 界面术语。
2. 英文术语采用最长非重叠匹配，避免 `Blood Ox Heart` 再叠加 `Heart`，将“血牛之心”逼成“血牛之心脏”。
3. 新增“无依据补句”、“UPK 片段语义”、“术语自然嵌入”、“等义不改”和“孤立台词不擅定时态”防线。
4. High 复审范围扩展为所有低置信决策（包括 `keep`）。校准集中 `0.87–0.94` 的保留项已证明这一路由能承接边界案例。

## 疑难取证演练

- 7 条 `uncertain` 已按性质分流；事实/术语型疑点先查用户指定的 Dishonored Fandom，中英文社区 Wiki 均通过 MediaWiki API 留下可追溯页面证据。本地对话语境问题不伪装成 Wiki 问题。
- `gaffer`：Wiki 原文中的 `forward-gaffer`、中文 Wiki 的“顺位领班/叉鱼人”与天邈 DLC 已有“工头/鱼叉手”交叉证明它是捕鲸岗位，不是“老人”或“教练”。
- `thick lung`：英文心脏语录确认原句，中文 Wiki 对应译为“肺部肿胀”；天邈“肺炎/肺病”两个复本将进入统一修补。
- `ricker`：中英文 Wiki 均无直接释义，自动取证正确降级为 `context_hits`；但本地 5 个独立字幕哈希全部固定使用 `slit your ricker`，足以在翻译层面裁决为“割喉/割开喉咙”，同时保留“虚构词源不可考”的记录。
- 自动取证不会把搜索标题当作事实：正式状态区分 `direct_evidence`、`context_hits`、`no_match`、`lookup_error`；页面正文片段由缓存后的 Wiki wikitext 提取。人工结合多源作出的结论另标 `resolved`，High prompt 明确按证据等级使用。
- 已核实结论固化为 6 条带预期命中数的展开规则，覆盖 28 个 corpus ID：`gaffer=7`、`ricker=5`、`thick lung=2`、`Midrow Substation=7`、`Butterfly Case=6`、`Chain Gauntlet=1`。任一规则命中数漂移都会阻止继续运行。
- 校准合并演练产出 31 条研究记录、28 个唯一 ID，其中 `resolved=28`、自动直接证据 1 条、自动上下文命中 2 条；resolved 冲突为 0，27 条 High 预览全部附加本地邻句，3 条相关疑难同时附加研究记录。

## 全量首审滚动补证

- Medium 全量运行期间新出现的事实型疑点继续执行 Fandom 优先核查，再以本地同组文本交叉验证；没有可靠中文 Wiki 对应名时坚持天邈底色，不自行创造专名。
- 规则最终扩为 33 条、精确覆盖 127 个 corpus ID。除原有 24 条外，新增画名 `Morley Withdraws` 2、画家 Jonathon Hedgerow 1、Bannerman 2、Dead Counter 既有称呼 1、City Watch dead-counters 2、The Eels 帮派简称 1、Boo 人物身份 1、Earl 人物身份 1、habber weed 既有译法 1；两条社区 P0 回归继续作为精确英文规则注入 High。
- `choffer` 的确切词源仍不可考，规则只裁定其为泛化辱称并保留天邈“杂鱼/蠢货”；`Key Notes` 已确认是开启暗格的空白录音带，但因无可靠中文正式名，本轮保留“关键笔记”。这两项明确区分“功能语义已解锁”与“词源/双关仍不可考”。
- `research/phase3_manual_rules.json` 的每条规则都声明 `expected_count`；最终规则哈希为 `046484d4702e9dc859709d06fed50e22a441af2d5db0268bff94dd4737a9cadc`，展开输出 127 行且无规则重叠，展开结果哈希为 `c29bd1bb4caa88fe8ee7951f19092d07e69cd6e18a3b07b46c4e134a17a904eb`。

## 放行结论

最终 Medium 首审配置通过校准，并已完成 31,583 条 corpus 全量分类、22,034 条 Medium 审校与 2,764 条 High 复审。最终 6,398 条修补进入接受清单，145 条进入 Phase 4 人工审核；独立验收为 PASS。
