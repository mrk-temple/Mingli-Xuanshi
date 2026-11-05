# 命理玄师 Mingli XuanShi

## 源码版使用说明 · 2026-11-05

Python 3.12+：`python -m pip install -e ".[dev]"`，再运行 `python -m mingli`，访问 `http://127.0.0.1:8800`。

默认离线规则引擎；可选模型只参与解读。术数内容供文化研究与反思使用。个人盘面和聊天数据不会随源码发布。

本次检查：188 项测试通过；浏览器脚本语法检查通过。 详细范围见 [验证与后续工作](RELEASE_CHECK.md)。敏感信息规则见 [SECURITY.md](SECURITY.md)。

> 一个可以计算、解释、比较、记录、验证东西方术数的个人研究平台。
> 不是"一个会算命的 AI"。

## v0.4 · 白话阅读版（2026-10-10）

前端阅读顺序调整为 **问题 → 白话回答 → 现实建议 → 按需展开证据**。
首页/生成页按工作选择、关系沟通、传统命盘提供入口；问题示例、中文牌阵选项、
生成状态与重复提交保护帮助完成一次解读。结果页提供术语词典、四柱/五行图、
规则抽屉、流派分歧和原始引用，保留强制局限与免责。

确定性计算与规则结论独立产生。开启 AI 后，MiMo 等模型只编辑 `ReaderGuide`：
白话要点引用既有结论编号，现实行动建议单独标注；不回写盘面、不替换规则结论。
未知规则、悬空字段、无计算引用、无效白话引用、概率/强断言输出被拒绝。
塔罗/易经的白话必须具有反思框架，部分现况/未来断言由程序拦截；
这些校验不等于对模型语义的完整证明。调用或校验失败时显示离线指引与提示。
旧存档不用迁移，浏览时可临时提供离线指引，不改写原记录。

支持 MiMo（官方 OpenAI 兼容接口）。本地凭据可用设置中的 `api_key_file` 引用一个
含 `Mimo API Key : "..."` 行的文件，密钥无需复制进设置文件；亦可从设置页填写。
远程模型会接收本次问题、盘面与规则结论。默认仍离线；配置模型时手动选择 AI 白话解读。

验证：`python dev/check.py` 跑 ruff、mypy、pytest 与独立临时数据的离线应用冒烟。
源码与修改前备份/实际页面截图/真实 MiMo 样例验证见相邻 `命理玄师升级_20261010` 目录。

## 产品结构（三空间闭环）

```
① 术数生成 /generate        选问题/体系 → 输入 → 白话回答与现实建议 → 按需核对盘面
② 玄师对话 /chat            带着盘局与 AI 深度讨论（不重算，只解释）
③ 记录与研究 /research      我的记录 · 预测实验室 · 学习空间
⚙ 设置 /settings            AI 接入 · 外观 · 模型行为 · 本地数据
```

流程：**生成 → 对话 → 沉淀**。旧链接（/run/*、/history、/lab、/learn、/systems）自动重定向。

## 快速开始

```bash
# 依赖（Python ≥3.12）
pip install -e ".[dev]"

# 运行 Web 工作台
python -m mingli
# → http://127.0.0.1:8800

# 跑测试
pytest
```

## 架构总览

```
用户输入
  ↓ Validator（provider.validate_input，程序校验）
Deterministic Calculator（mingli/engines → xuan-shu/scripts 同一引擎）
  ↓ CalculationResult（结构化事实 + 引擎版本 + 输入快照）
Rule Retrieval（mingli/knowledge YAML，规则带 sourceLevel S/A/B/C/D）
  ↓ InterpretationResult（断语必带推理链+规则引用+计算引用）
Evidence Trace 校验（悬空引用 = 拒绝出报告）
  ↓ Report（事实节 / 解读节 / 体系局限【强制】/ 免责【强制】）
Session 持久化（data/sessions/*.json）→ 玄师对话（data/chats，只消费事实不回写）
→ 实验室（预测锁定→判定→统计）
```

### 目录

| 路径 | 内容 |
|---|---|
| `xuan-shu/` | 原 skill（**未改动**），`scripts/` 是唯一计算引擎来源 |
| `mingli/core/` | 数据模型 / Registry / Router / 知识库 / 安全门 / 报告 / 会话 / 实验 / LLM 插槽（含玄师对话 `chat_with_llm`） |
| `mingli/systems/` | 七个 SystemProvider + 未实现体系诚实登记表 |
| `mingli/engines/` | 对 xuan-shu/scripts 的 importlib 包装（不复制算法） |
| `mingli/knowledge/` | 结构化规则库（YAML，含流派冲突并列） |
| `mingli/web/` | FastAPI + Jinja2 SSR（三空间 IA · 观星・玄师设计系统） |
| `tests/` | 引擎确定性 / 边界日期 / seed 复现 / 非法输入 / 三空间集成 |

已上线体系（active）：

八字 · 六爻纳甲 · 大六壬 · 小六壬 · 梅花易数 · 易经义理 · Tarot(RWS)

诚实标注（见 `mingli/systems/registry_data.yaml`）：
- `knowledge-only`（有知识、暂无可靠算盘引擎）：紫微斗数
- `planned`（已规划未实现）：奇门 · 择日 · 风水 · 太乙 · 西洋占星 · Horary · Numerology · Lenormand · Runes · Geomancy · Jyotish

## 铁律 → 程序约束对照

| 原 skill prompt 规则 | 程序化落点 |
|---|---|
| 排盘必须脚本算 | `Provider.calculate()` 是唯一入口；Web 层不存在 LLM 排盘路径 |
| 事实与解读分离 | 报告渲染器强制两节分列；玄师对话只读 Session 事实，永不回写 CalculationResult |
| 断语带推理链与出处 | `Conclusion` 缺 reasoning/rules 即渲染失败；calcRefs 悬空即 ReportError |
| 体系局限必写 | 渲染器无条件注入五大未证假设段 |
| 免责必写 | 渲染器尾部硬编码 |
| 流派分歧不调和 | 规则库同主题多 tradition 并列 + disputes 字段展示 |
| 不做综合玄学分数 | 对照视图只有并排与收敛/分歧标注；白话编辑有输出侧校验，自由对话仍仅由提示词要求不输出概率/百分比 |

## 解释器配置

默认规则引擎（离线、确定性、可测试）。LLM 为可选插槽（玄师对话/综合分析/单盘解释），在
**设置页（/settings）** 配置：支持 MiMo、Anthropic 原生、DeepSeek 与任意 OpenAI 兼容端点
（Provider + Base URL + Model + Key），可一键「测试连接」；也可用环境变量：

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export MINGLI_INTERPRETER=llm   # 默认 rule-engine
export MINGLI_MODEL=claude-opus-4-8   # 可选
```

Key 在本机设置保存，或以 `api_key_file` 引用已有凭据文件（设置已 gitignore）。结构化单盘解读经 Evidence Trace 校验——
引用悬空整体拒绝；自由对话并无等价的逐句引用校验。平台只走远程 API，不运行任何本地部署模型；未配置 Key 时全部功能优雅降级，
确定性计算不受影响。

## 设计文档

产品设计以 [design.md](design.md) 为最高参考。原 skill 用法见 [xuan-shu/SKILL.md](xuan-shu/SKILL.md)。
