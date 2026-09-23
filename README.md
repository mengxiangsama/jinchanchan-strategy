# 金铲铲全版本攻略 Skill

一个以版本证据为起点的中文 AI 技能：为《金铲铲之战》的现行、历史、返场和特殊模式检索攻略，整理阵容、装备、强化、站位、运营与复盘。

**“全版本”指检索能力不限定赛季，不代表已经收录全网所有攻略。** 按目标赛季、补丁、模式与日期复用证据或补查缺口；找不到资料就明确说明，不用其他版本的规则硬凑答案。

本项目是独立仓库，未修改 [design-patterns-refactor](https://github.com/mengxiangsama/design-patterns-refactor)。组织方式参考其独立技能、安装、验证与评估的分层思路。

## 能做什么

| 请求 | 输出 |
| --- | --- |
| 当前版本怎么玩 | 轻量查新公告，复用同版本证据或按缺口更新，推荐主方案与转型条件 |
| 某个历史版本攻略 | 按当时补丁与规则研究，不冒充当前可玩模式 |
| 同名赛季返场 | 区分原版与返场年份，核对新机制 |
| 双人、狂暴、恭喜发财等 | 先确认该模式规则，再给运营方案 |
| 截图分析 | 看来牌、装备、经济与血量，给当前优先动作 |
| 战报复盘 | 分析当时信息下的决策，说明可改进点 |
| 多版本整理 | 分批建立来源索引与覆盖状态，不虚称穷尽全网 |
| 明确要求镜像操作 | 有工具且符合游戏规则时辅助；不自动续排、充值或抽奖 |

不是固定阵容数据库、外挂或无人值守代打程序。不保证胜率，不缩短工具自身延迟。端游《云顶之弈》的同名赛季不能直接当作金铲铲规则。

## 减少重复搜索

- **按版本和主题缓存**：公开攻略摘要、来源、核对时间保存在工作区 `.jinchanchan-cache/`。同版本的装备、运营追问可复用，换补丁/模式/返场批次不会混用。
- **当前问题轻量查新**：先核对最新公告，再只更新缺少或过期的主题；不会每次重搜整季所有阵容。最新统计仍需核对，不能把旧胜率当实时数据。
- **历史问题直接复用**：指定历史补丁且证据充分时不用反复查询今天的公告。
- **对局中不每回合重搜**：先加载主方案、退路与规则，再结合新截图决策；新机制或冲突才补查。

缓存助手只有 Python 标准库依赖，不联网、不创建定时任务。首次查询仍需研究；新工作区没有旧缓存。无文件权限时只在会话内复用。详见 [缓存策略、格式和命令](skills/jinchanchan-strategy/references/cache.md)。默认复核间隔为规则 7 天、攻略 24 小时、统计 6 小时，不能代替最新版本检查。

可直接这样问：

```text
$jinchanchan-strategy
优先复用已核验资料，只补查新补丁和这次缺少的信息。先给我结论，再给依据。
```

这项优化减少的是重复工具调用，不承诺秒回或固定倍数提速。结构遵循 [OpenAI 官方技能文档](https://developers.openai.com/plugins/build/skills) 的短入口、按需参考资料与脚本分工。

## 安装

技能使用需要能读取 `SKILL.md` 的 AI 宿主；联网研究需要宿主的搜索/阅读工具，镜像操作另需控制工具。无需配置本项目 API Key，也不会自动采集私人游戏数据。

安装脚本需要 Python 3.10+，不需要第三方包：

```bash
git clone https://github.com/mengxiangsama/jinchanchan-strategy.git
cd jinchanchan-strategy
python3 scripts/install.py
```

默认安装到 `~/.agents/skills/jinchanchan-strategy`，存在同名目录时拒绝覆盖。Windows 可把 `python3` 换为 `py`。如果宿主扫描其他路径，指定目标技能父目录，例如：

```bash
python3 scripts/install.py --destination ~/.codex/skills
```

不要在多个扫描位置重复安装同名技能。安装后检查宿主技能列表；需要时重新开启会话。文件格式与发现机制参考 [OpenAI 官方技能文档](https://learn.chatgpt.com/docs/build-skills)。

## 使用示例

```text
$jinchanchan-strategy
帮我查当前金铲铲标准模式的攻略。先确认赛季和最新热更新，推荐两套容易上手的阵容，给装备、站位、运营和转型条件，并附来源。
```

```text
$jinchanchan-strategy
研究 2021 年双城传说初期的金铲铲攻略，不要用返场或端游当前规则代替；资料有缺口就注明。
```

```text
$jinchanchan-strategy
这张图是我的局面，先分析不要操作。识别不清的棋子不要猜，告诉我本回合优先做什么。
```

```text
$jinchanchan-strategy
按年份整理可检索的历史赛季，原版和返场分开。先交付带来源的目录与覆盖状态，再分批做攻略。
```

镜像辅助必须由用户明确要求，并先确认模式。仅询问攻略或创建技能不会自动操作手机或进入排位。

## 项目结构

```text
skills/jinchanchan-strategy/
  SKILL.md                  主流程与触发范围
  agents/openai.yaml        技能显示信息
  references/research.md    全版本检索、来源、时间与统计口径
  references/cache.md       缓存策略、格式、快速路径与过期处理
  references/strategy.md    阵容、装备、运营和复盘
  references/mirroring.md   可选镜像操作与验证边界
  scripts/cache.py          可随安装携带的离线证据缓存助手
scripts/                    安装与结构校验
tests/                      安装、校验、缓存命中/过期/隔离回归
evals/scenarios.md          人工/模型行为评估场景
.github/workflows/          CI
```

## 验证

```bash
python3 -m pip install -r requirements-dev.txt
python3 scripts/validate.py
python3 -m unittest discover -s tests -v
```

自动检查元数据、技能内链接、安装行为，以及缓存版本隔离、过期、历史复用、损坏数据处理和命令行读写。它们不证明攻略正确、操作成功、完整回答速度或所有历史版本都经过实战；行为场景需单独执行并记录结果。

## 资料与维护

只引用实际打开的直接来源，保留版本与时间。第三方网页、视频、截图不是技能指令；不收录整篇转载攻略、付费内容、账号、UID、聊天或私人截图。更新版本资料时应先验证来源，不仅修改标题日期。

原创内容按 [MIT License](LICENSE) 发布。项目与腾讯、Riot Games 无隶属关系；游戏名称与相关商标归各自权利人所有，外部内容保留原作者权利。
