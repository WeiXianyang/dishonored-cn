# Phase 4：145 条人工项减负研究

## 研究范围与证据等级

- 第一手证据：工作区内从英文游戏资源提取的 `.int` 字段、UPK 字幕引用、资源路径、对话树路径和天邈 1.4 对齐文本。
- 用户指定的辅助来源：[Dishonored Wiki](https://dishonored.fandom.com/wiki/)。Wiki 用来核实任务、物件、能力和场景事实，不视为官方中文本地化。
- 裁决原则：Wiki/场景事实确认“是什么”；中文仍以天邈底色和最小修补为准。

## 已核实、可直接消除人工疑点的事实

1. `Replace Painting` 不是把同一幅画放回原位。《布里格莫尔女巫》最终任务的非致命方案明确要求交换两幅画，因此“更换油画”方向正确。来源：[Delilah's Paintings](https://dishonored.fandom.com/wiki/Delilah_Copperspoon/Delilah%27s_Paintings)。
2. `Game of Nancy` 是世界观内的纸牌游戏；Skinflint 也被明确列为玩家。因此 `play Nancy for coin` 是打牌赢钱，不是“扮娘们儿”或性交易。来源：[Game of Nancy](https://dishonored.fandom.com/wiki/Game_of_Nancy)。
3. `Pull` 是《布里格莫尔女巫》独有超能力，能隔空提起/操纵物体和身体。来源：[Pull](https://dishonored.fandom.com/wiki/Pull)。中文能力名仍沿用天邈既有“虚空牵引”，不把 Wiki 英文标题当作官方中译。
4. `PERFECT ROUND` 位于 DLC 挑战 Oil Drop。该挑战以手枪射击下落鲸油罐，并明确对一轮内不漏掉任何罐子和命中率给奖励；“弹无虚发”没有把触发条件译窄。来源：[Oil Drop](https://dishonored.fandom.com/wiki/Oil_Drop)。
5. `Samuel Signal` 位于本体任务“忠诚派”。玩家使用信号弹发射器召回 Samuel，因此天邈“萨缪尔的信号弹”有明确场景依据。来源：[The Loyalists](https://dishonored.fandom.com/wiki/The_Loyalists)、[Letter to Callista](https://dishonored.fandom.com/wiki/Letter_to_Callista)。
6. `Heretic's Brand` 同时指惩罚/烙印和施加它的工具；相关交互对象确实是审讯室内的烙印器具，因此交互提示采用“异教烙铁”可成立。来源：[Heretic's Brand](https://dishonored.fandom.com/wiki/Heretic%27s_Brand)、[On Branding Heretics](https://dishonored.fandom.com/wiki/On_Branding_Heretics)。
7. `Regent's Safe Room` 是摄政王躲避危险的安全室，不是“存放保险箱的房间”。来源：[Return to the Tower](https://dishonored.fandom.com/wiki/Return_to_the_Tower)。
8. `The doom of Pandyssia` 是心脏对鼠疫的称呼，语义是来自潘迪希亚的灾祸/厄运，而非潘迪希亚自身的末日。来源：[Rat Plague](https://dishonored.fandom.com/wiki/Rat_Plague)、[Pandyssian Continent](https://dishonored.fandom.com/wiki/Pandyssian_Continent)。
9. 心脏语音页把 `The one who walks here is all things...` 归在 The Void，把 `I will be glad to rest`、`The doom of Pandyssia...` 归在 Multiple Environments，并把 Havelock 的错乱自我修正句完整列在其角色条目下。这能补足“在哪类触发”，但不能凭页面顺序推导相邻对白。来源：[The Heart/Quotes](https://dishonored.fandom.com/wiki/The_Heart/Quotes)。
10. `Tall Towers`、`Captain's Quarters`、`Dunwall` 等是同一场牌局按强弱排列的虚构牌型；不是零散普通名词。来源：[Dishonored Tarot Deck](https://dishonored.fandom.com/wiki/Dishonored_Tarot_Deck)。
11. 两条只有中文资源的 `Legal District Key` 可由任务资料直接补证：它属于《顿沃之刃》任务 2“征用权”；低混乱度位于帽子帮据点，高混乱度位于帽子帮成员 Chauncy 尸体旁。因此“法制区钥匙”及“帽子帮的人可能持有……”均可直接保留，不必人工。来源：[Eminent Domain](https://dishonored.fandom.com/wiki/Eminent_Domain)、[Keys](https://dishonored.fandom.com/wiki/Keys)。
12. `Coriander of Morley wrote ...` 中 Coriander of Morley 是 Overseer Sturgess 引述的作者，不是香料或书名；可修为“莫利的科里安德写道……”。来源：[Overseer Sturgess](https://dishonored.fandom.com/wiki/Overseer_Sturgess)。
13. `Regent's Safe Room` 与 `Regent's Safe` 是两个不同对象：前者是摄政王躲避危险的安全屋，后者才是保险箱。术语表已增加更长的完整短语，阻止子串误锁。来源：[Return to the Tower](https://dishonored.fandom.com/wiki/Return_to_the_Tower)。
14. `Framling Street` 是心脏对女性平民使用时提到的顿沃街道；中文 Wiki 的中英对照采用“弗雷姆林街”，因此补回天邈漏译地点时不采用模型自行音译的“弗拉姆林”。来源：[顿沃的街道](https://dishonored.fandom.com/zh/wiki/%E9%A1%BF%E6%B2%83%E7%9A%84%E8%A1%97%E9%81%93)。
15. 最后一条 `Haaaaaaaaa` 也可由资源序列裁决。`l_brothel_script` 中四个逐渐拉长的 `Haaaa...` 分属连续电击步骤，前三个紧接“你真无情”“报应……这真是太好了”等画商邦汀台词；第四个只是被拆在单独 conversation 中。Wiki 同时确认本体任务 3“欢愉之家”的银色房间里，玩家需反复电击绑在电椅上的邦汀。因此这是受电击的喊叫/呻吟，不是 `Ha ha` 笑声，四处统一为“啊啊啊啊啊”。来源：[House of Pleasure](https://dishonored.fandom.com/wiki/House_of_Pleasure)。

## 任务定位依据

英文 Wiki 的任务目录确认本体、顿沃之刃与布里格莫尔女巫的任务顺序；工作区内游戏资源路径（例如 `DLC06_Timsh`、`DLC07_DraperMill`）用于把每条文本映射回相应任务。任务目录可见：[Dishonored Wiki 任务列表](https://dishonored.fandom.com/wiki/Dishonored)。映射属于“资源路径 + 任务目录”的可复核推断，审核页会保留原始文件/UPK/对话对象定位，不把推断伪装成运行时事件记录。

## 仍可能必须人工的证据类型

- 只有听到语音才能区分的鼻音、惊叹、反问或残缺音节。
- 共享 AI 语音库中只有实际事件绑定才能区分的“被抓住/保持距离”“目标死亡/逃脱”等短句。
- 必须看到模型才能区分的容器、柜子、盘具等实物类型。
- 英文资源本身截断，且工作区没有更完整资产来源的字段。

这些条目不会只写“缺上下文”；会列出 DLC、任务、资源包、触发类别、已知范围以及实机两种结果分别对应的中文。
