# 命理玄师（Mingli XuanShi）Design Specification

> 项目定位：一个“东西方术数研究与实验工作台”，而不是单纯的算命聊天机器人。
>
> 核心理念：**术数是可计算的，就交给确定性引擎；术数是解释性的，就交给规则化推理；术数存在争议，就显式展示争议；用户想验证，就提供小测试与实验记录。**

---

## 1. 产品愿景

### 1.1 一句话

**命理玄师 = 东方命理/术数 + 西方占星/占卜 + 可计算术数引擎 + 多体系对照 + 小型验证实验 + 可追溯解释。**

### 1.2 不做成什么

不要做成：

- “万能 AI 算命师”
- 只会生成玄学话术的 LLM
- 把所有术数揉成一个神秘的“综合分数”
- 用户换一个体系问同一个问题，系统一直找到符合用户期待的答案
- 对医疗、投资、法律、婚姻等重大事项做确定性预言

### 1.3 做成什么

用户进入后可以：

1. 输入出生资料，查看自己的东方/西方命盘。
2. 选择某个问题，让系统推荐合适的术数。
3. 自己摇卦、报数、抽牌，系统完成计算与解释。
4. 同一个问题用多个体系分别测试，然后做**独立结果对照**。
5. 创建“命理实验”，例如：
   - 记录一次预测；
   - 锁定预测时间；
   - 到期后输入真实结果；
   - 查看预测是否命中；
   - 区分“解释性命中”和“可验证预测”。
6. 学习某个术数：看概念、算法、案例、规则来源、争议点。
7. 查看自己的历史盘、卦、牌阵和实验记录。

---

# 2. 体系总地图

设计原则：不要把“术数”看成一张平面列表，而要分成不同的输入模型。

## 2.1 A 类：出生时刻型（Natal / Fate）

输入核心：出生日期 + 时间 + 地点。

### 东方

- 八字 / 四柱（BaZi）
- 紫微斗数（Zi Wei Dou Shu）
- 中国传统命理/干支体系
- 部分中国星命/宿曜传统
- 九星气学等东亚衍生体系（后期）

### 西方/印度

- 西洋占星
  - Natal Chart
  - Tropical Zodiac
  - Houses
  - Aspects
  - Transits
  - Progressions（后期）
  - Synastry / Composite（后期）
- 古典/希腊化占星（Hellenistic Astrology）
- 吠陀占星 / Jyotish
  - Rāśi
  - Nakshatra
  - Vimshottari Dasha 等（后期）
- 恒星/回归等分支（后期）

---

## 2.2 B 类：当下时刻型（Moment / Event）

输入核心：问题发生/起课的时间，有时还需要地点。

### 东方

- 六爻纳甲
- 大六壬
- 小六壬
- 奇门遁甲
- 梅花易数
- 太乙神数

### 西方

- Horary Astrology（卜卦占星）
- Electional Astrology（择时占星）
- Geomancy / Renaissance Geomancy（地占/西方土占）

---

## 2.3 C 类：随机抽取型（Randomized Symbolic Divination）

核心是：产生一个离散符号集合，再依据体系解释。

### 东方

- 六爻
- 梅花
- 灵签/签文（后期）
- 部分数术占法

### 西方

- Tarot
- Lenormand
- Runes / Elder Futhark
- Ogham（后期）
- Dice Divination（后期）
- Bibliomancy（书占，后期）
- Pendulum（摆锤，占测模块可实验化）

---

## 2.4 D 类：数字/姓名/人格符号型

- 中国姓名学
- 五格剖象等传统姓名体系（需明确流派）
- Western Numerology
  - Pythagorean
  - Chaldean
- Vedic Numerology（后期）
- 象数/数字起卦
- 日期数字实验

注意：不同流派公式不得混用。

---

## 2.5 E 类：形势/空间/身体观察型

### 东方

- 风水
- 阳宅
- 玄空等流派（后期）
- 面相
- 手相
- 体相
- 择日/黄历/通书

### 西方

- Palmistry / Chiromancy
- Western Physiognomy（历史文化研究）
- Geomancy
- 部分空间占测传统

此类系统必须区分：

> “传统解释体系” ≠ “现代科学证据”。

---

## 2.6 F 类：意识/梦境/象征解释型

- 梦占 / Dream Interpretation
- 象征学
- 神谕卡 / Oracle Cards
- Scrying / 水晶球等凝视术（后期）
- 自动书写等历史/文化系统（后期）

这些模块优先定位为**文化/象征解释工具**，不要设计成事实预测机器。

---

# 3. 产品第一阶段必须实现的体系

MVP 不追求“世界上所有术数全部上线”。

第一阶段建议：

### 东方核心

1. 八字
2. 易经 / 六十四卦
3. 六爻
4. 梅花易数
5. 小六壬
6. 大六壬
7. 奇门遁甲
8. 紫微斗数

### 西方核心

9. 西洋占星
10. Tarot
11. Lenormand
12. Numerology
13. Runes
14. Western Geomancy

### 第二阶段

15. 太乙神数
16. 风水
17. 择日
18. 面相
19. 手相
20. 吠陀占星
21. 其他东亚术数
22. Dream / Oracle / Bibliomancy 等实验模块

---

# 4. 系统必须采用“术数插件化”

每个术数都是一个独立 Provider / System Module。

建议抽象：

```ts
interface DivinationSystem {
  id: string
  name: string
  region: "east" | "west" | "cross-cultural"
  category: string[]

  inputSchema: InputSchema
  calculator: Calculator
  interpretation: InterpretationEngine
  knowledgeBase: KnowledgeBase

  recommendQuestion(question: Question): RecommendationScore
  validateInput(input: unknown): ValidationResult

  calculate(input: unknown): CalculationResult
  interpret(
    calculation: CalculationResult,
    question?: Question,
    context?: InterpretationContext
  ): InterpretationResult
}
```

原则：

- Calculator ≠ LLM
- Interpretation ≠ Calculation
- Source ≠ Model Memory
- System ≠ Cross-System Consensus

---

# 5. 统一数据模型

## 5.1 UserProfile

```ts
interface UserProfile {
  id: string
  name?: string

  birth?: {
    date: string
    time?: string
    timezone: string
    latitude?: number
    longitude?: number
    placeName?: string
  }

  preferences?: {
    language: "zh-CN" | "en"
    defaultSystems?: string[]
  }
}
```

## 5.2 Question

```ts
interface Question {
  id: string
  text: string
  category:
    | "career"
    | "relationship"
    | "finance"
    | "study"
    | "decision"
    | "timing"
    | "self"
    | "other"

  askedAt: string
  location?: Location
}
```

## 5.3 DivinationSession

```ts
interface DivinationSession {
  id: string
  systemId: string
  input: unknown

  calculation: {
    version: string
    engineVersion: string
    result: unknown
  }

  interpretation: {
    model?: string
    rules: string[]
    reasoning: string[]
    conclusion: string
  }

  uncertainty: {
    methodological: string[]
    input: string[]
    interpretation: string[]
  }

  createdAt: string
}
```

---

# 6. “术数计算层”是系统的核心资产

绝不能：

```text
用户生日
↓
LLM 自己脑算八字
↓
生成一个看起来很像的命盘
```

必须：

```text
用户输入
↓
Input Validator
↓
Deterministic Calculator
↓
Structured Result
↓
Rule Retrieval
↓
LLM Interpretation
↓
Evidence / Rule Trace
↓
Report
```

你之前 xuan-shu skill 中规定的：

- 排盘/起卦/抽牌由脚本计算
- 脚本结果先于断语
- 断语必须带推理链和出处

应该升级成程序层的硬约束。

---

# 7. 术数推荐器

用户无需知道该用什么。

输入：

> “我最近要不要换工作？”

Router 给出：

```text
问题类型：职业决策

推荐：
① 奇门遁甲 —— 行动/方向/时机
② 六爻 —— 某一具体事情成败
③ 塔罗 —— 主观状态/心理视角
④ 梅花易数 —— 快速象数判断
⑤ 西洋卜卦占星 —— 当前问题结构

不建议：
八字单独用于判断这一次具体事件。
```

推荐不是“哪个最准”，而是：

> **什么系统最匹配这个问题的信息结构。**

---

# 8. 多体系模式

必须禁止：

```text
八字说好
塔罗说好
奇门说好
所以 92 分，事情一定能成
```

正确模式：

```text
               同一个问题
                    │
       ┌────────────┼────────────┐
       ↓            ↓            ↓
     六爻          塔罗        卜卦占星
       │            │            │
   独立结果       独立结果      独立结果
       │            │            │
       └────────────┼────────────┘
                    ↓
              Cross-System View
                    │
          ┌─────────┴─────────┐
          ↓                   ↓
       收敛点               分歧点
```

系统只能说：

> “三个体系在‘短期存在反复’这一描述上出现相似方向。”

不能说：

> “三术一致，因此概率 93%。”

---

# 9. 最重要的创新：术数实验室

“命理玄师”不只是给结论，要能够帮助用户自己观察。

## 9.1 Prediction Record

用户创建：

```text
问题：
这次面试能否进入下一轮？

体系：
六爻

预测：
倾向有机会，但过程有反复。

预测窗口：
2026-09-01 ~ 2026-09-10

创建时间：
2026-08-24

状态：
待验证
```

到期后：

```text
真实结果：
进入下一轮，但晚了三天通知。

系统判定：
部分命中 / 模糊命中 / 未命中
```

## 9.2 实验指标

不要只计算“准/不准”。

可以记录：

- Exact Hit
- Partial Hit
- Direction Hit
- Timing Hit
- Miss
- Ambiguous
- No Outcome

长期后可以生成：

```text
你的六爻实验记录
n = 42

方向命中：61.9%
时间命中：28.6%
完全命中：19.0%
模糊命中：31.0%
未命中：23.8%
无法验证：7.1%
```

注意：

> 这些只是用户个人样本，不自动代表体系具有科学有效性。

---

# 10. “小测试”体系

首页可以有：

## 今日测试

### 测试 A：随机事件预测

生成一个未来短期可验证问题。

### 测试 B：二选一

例如：

```text
A / B 两个选择
→ 分别用系统独立分析
→ 用户先记录选择
→ 到期后反馈结果
```

### 测试 C：时间预测

例如：

```text
某事件最可能发生：
A. 3 天内
B. 1 周内
C. 1 月内
D. 无明显迹象
```

### 测试 D：盲测

系统记录预测，但先隐藏解释结果。

这样可以减少：

> “事后看解释觉得特别准”

带来的确认偏差。

---

# 11. 对比实验

一个非常值得做的功能：

## Same Question Lab

用户提出：

> “我今年是否适合换城市？”

系统自动选择：

- 八字岁运
- 奇门遁甲
- 六爻
- 塔罗
- 西洋占星

然后分别输出。

结果页不要只给一个结论，而给：

```text
                    收敛                 分歧

八字                ★★★                  -
奇门                ★★★                  ★
六爻                ★★                   ★★
Tarot               ★★                   ★
占星                ★★★                  -
```

再解释：

> 收敛来自什么？
> 分歧来自什么？
> 每个系统的输入和理论前提是否不同？

这会让程序从“玄学工具”提升到“术数研究工具”。

---

# 12. 知识库设计

每个体系至少有：

```text
system/
├── overview.md
├── history.md
├── terminology.md
├── calculation.md
├── rules.md
├── exceptions.md
├── examples/
├── sources.md
└── disputes.md
```

例如：

```text
systems/bazi/
systems/liuyao/
systems/meihua/
systems/qimen/
systems/daliuren/
systems/ziwei/
systems/tarot/
systems/astrology/
systems/lenormand/
systems/numerology/
systems/runes/
systems/geomancy/
```

任何规则必须能够回答：

> “你为什么这么解释？”

---

# 13. 来源等级

每条知识增加 sourceLevel：

```text
S      原典/经典文本
A      权威学术研究/可靠历史资料
B      主流流派教材/整理
C      当代实践者资料
D      网络经验
```

同一规则出现冲突时：

```text
不是让 LLM 自己选。
```

而是：

```text
展示：
A 派：……
B 派：……
本次采用：A 派
原因：系统配置 / 用户选择
```

---

# 14. “流派”必须是一等公民

不要设计成：

```text
八字 = 一个算法
```

而应该：

```text
BaZi
 ├── Tradition A
 ├── Tradition B
 ├── Tradition C
 └── Custom Profile
```

同样适用于：

- 紫微
- 奇门
- 六爻
- Tarot
- Western Astrology
- Jyotish

这样之后可以加入：

> “按照某流派重算一次”。

---

# 15. UI 信息架构

首页：

```text
命理玄师
────────────────────────
今天想研究什么？

[ 我的命盘 ]
[ 我有一个问题 ]
[ 起一卦 ]
[ 抽塔罗 ]
[ 测试一下 ]
[ 术数实验室 ]

──────── Explore ────────

东方术数
八字 · 六爻 · 梅花 · 奇门 · 六壬 · 紫微

西方术数
占星 · Tarot · Lenormand · Runes · Numerology

研究
多体系对照 · 历史记录 · 预测实验 · 命中统计
```

---

# 16. 命盘页面

分三层：

### Layer 1：原始结果

只显示计算结果。

### Layer 2：结构分析

系统解释：

```text
五行
十神
宫位
相位
牌阵关系
体用
```

### Layer 3：玄师解读

自然语言结论。

用户可以点击：

> “为什么这样判断？”

展开：

```text
结论
↓
规则
↓
计算数据
↓
来源
```

---

# 17. Agent 架构

不要让一个巨大 Agent 直接处理所有内容。

推荐：

```text
                   ┌───────────────┐
                   │  XuanShi Agent│
                   └───────┬───────┘
                           │
                    Intent Router
                           │
        ┌──────────┬───────┼────────┬──────────┐
        ↓          ↓       ↓        ↓          ↓
     Fate       Divination Astrology Research  Lab
        │          │       │        │          │
        ↓          ↓       ↓        ↓          ↓
     Systems     Systems Systems   KB       Experiments
        │          │       │
        └──────────┴───────┘
                   ↓
             Evidence Layer
                   ↓
              Report Engine
```

---

# 18. Agent 的核心 Loop

```text
UNDERSTAND
    ↓
CLASSIFY QUESTION
    ↓
CHOOSE SYSTEM
    ↓
VALIDATE INPUT
    ↓
CALCULATE
    ↓
RETRIEVE RULES
    ↓
INTERPRET
    ↓
CHECK CONTRADICTIONS
    ↓
CHECK SAFETY
    ↓
GENERATE REPORT
    ↓
OPTIONALLY CREATE EXPERIMENT
```

质量门：

```text
如果计算不存在 → 不解释

如果输入不完整 → 不起盘

如果规则不存在 → 标记“不足以判断”

如果体系内部有流派冲突 → 显示冲突

如果用户要求确定性 → 降低断言强度

如果涉及医疗/投资/法律 → 禁止给确定性预测
```

---

# 19. 安全与伦理

每个报告都需要：

> 本内容属于传统文化/象征性解释或娱乐性参考，不代表经科学验证的事实预测，也不构成医疗、投资、法律等专业建议。

对于：

- 自杀/死亡
- 严重疾病
- 怀孕/医疗
- 赌博
- 高风险金融投资
- 法律责任
- 暴力

不得将术数结果作为行动依据。

可以提供：

> 文化解释 + 风险提示 + 现实决策建议。

---

# 20. MVP 开发顺序

## Phase 0 —— 核心基础设施

- System Registry
- Question Model
- User Profile
- Session
- Calculation Engine Interface
- Knowledge Retrieval
- Report Renderer
- Experiment Database

## Phase 1 —— 把你现在的 xuan-shu 搬进去

直接复用：

- 八字
- 六爻
- 大六壬
- 小六壬
- 梅花
- Tarot
- 易经理解

并把 skill 中的质量门程序化。

## Phase 2 —— 加入强东方体系

- 奇门遁甲
- 紫微斗数
- 择日
- 风水

## Phase 3 —— 西方体系

- Western Astrology
- Horary Astrology
- Numerology
- Lenormand
- Runes
- Geomancy

## Phase 4 —— 研究实验室

- 盲测
- 预测记录
- 命中统计
- 多体系对照
- 用户实验档案
- 数据导出

## Phase 5 —— Knowledge Graph

建立：

```text
五行 ←→ Tarot Elements
星体 ←→ Tarot
卦象 ←→ 星体
数字 ←→ 数秘
```

但：

> 只做“比较/文化对应图谱”，不自动把跨体系对应关系当成同一理论事实。

---

# 21. 第一版成功标准

不是：

> “能算很多东西。”

而是：

### 计算可靠

同样输入，多次运行得到同样的结构化计算结果。

### 解释可追溯

每个关键结论都能回到：

```text
输入 → 计算 → 规则 → 推理 → 结论
```

### 体系不混淆

八字不会偷偷套塔罗规则。

### 支持实验

用户可以真实记录预测并在未来验证。

### 支持比较

不同体系可以并排研究，但不会伪造“统一答案”。

---

# 22. 设计哲学

命理玄师最重要的一条原则：

> **不追求证明玄术是真的，也不预设玄术是假的。**
>
> 它研究的是：
>
> 1. 这些系统如何计算；
> 2. 它们如何解释；
> 3. 它们为什么会得出不同答案；
> 4. 在真实事件记录中能观察到什么；
> 5. 哪些是传统文本，哪些是流派规则，哪些只是现代人的解释。

因此：

**命理玄师不是“AI 算命”。**

它更接近：

> **一个拥有东方与西方术数知识库、计算引擎、解释引擎和预测实验室的个人术数研究工作台。**
