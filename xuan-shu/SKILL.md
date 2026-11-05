---
name: xuan-shu
description: >
  玄术全体系：命理推导（八字排盘/旺衰格局用神/大运流年岁运）+ 算卦（六爻纳甲/大六壬/小六壬/梅花易数/塔罗/易经卦解），排盘起卦起课抽牌由确定性脚本计算，断语必带批判标注与免责。当用户说"算一卦/帮我摇卦/六爻排盘""小六壬掐指一算/马前课""大六壬起一课""塔罗占卜/抽张塔罗牌""梅花易数起卦/报数起卦""排八字看大运/流年运势如何/看看我的命盘""这个卦怎么解"时使用；用户给公历生日、报数、铜钱摇卦结果或抽牌方式即可开始。不做：紫微斗数/奇门遁甲/风水/择日等未覆盖术数（如实说明不在范围）、把方法论做成 skill（转 skill-creator）。
---

# 玄术 Xuan Shu —— 命理推导与算卦全体系

本 skill 是易学体系的整合层：命理线（八字）移植自 yixue-mingli 同源 references（同一盘面断语应与其一致），占卜线新增六爻/大六壬/小六壬/塔罗四套体系并保留梅花易数。体系地图见 [references/systems-map.md](references/systems-map.md)，任何跨体系请求先读它。

## 铁律

1. **排盘/起卦/起课/抽牌结果必须由脚本计算**，禁止 LLM 心算替代；用户自报的四柱、卦象、课式也要与脚本输出核对，不一致以脚本为准并说明原因。
2. **事实与解读分离**：先原样复述脚本输出，再给断语；断语必须给出推理链（因何判据而断）与出处（哪条规则、哪个 reference）。
3. **批判必写**：每次报告必须含"体系局限"小节（未证假设 + 反证，见 [references/piping-guide.md](references/piping-guide.md)）；不用"必/定/绝"式断言，吉凶倾向用体系内规则语言（"多有/恐/倾向"）。
4. **免责必写**：报告结尾注明"仅供娱乐/文化参考"，不构成医疗、投资、法律建议。
5. **跨体系不乱嫁接**：六条线各自独立成章；多条线指向同一倾向才写"互证"，互相矛盾如实呈现（systems-map §4/§6）。

## 输入路由

| 输入 | 路径 | 依赖 |
|---|---|---|
| 公历生日/四柱 → 八字断命 | 主流程（阶段 0-4） | scripts/paipan.py（--gender 大运、--today 定位、--longitude 真太阳时） |
| 大运/流年/应期 | 主流程（阶段 3） | paipan.py --gender + references/shensha-suiyun.md + references/yingqi.md |
| 六爻（摇卦/报数/农历时间） | 占卜分支（阶段 5A） | scripts/liuyao.py + references/liuyao-guide.md |
| 大六壬起课 | 占卜分支（阶段 5B） | scripts/daliuren.py + references/daliuren-guide.md |
| 小六壬（农历三数/报三数） | 占卜分支（阶段 5C） | scripts/xiaoliuren.py + references/xiaoliuren-guide.md |
| 梅花易数（报数/农历时间） | 占卜分支（阶段 5D） | scripts/qigua.py + references/duangua-guide.md |
| 塔罗（抽牌） | 占卜分支（阶段 5E） | scripts/tarot.py + references/tarot-guide.md + tarot-meanings.md |
| 卦辞爻辞/易经义理 | 义理分支（阶段 6） | references/yijing-yili.md |
| 命理/术数概念问答 | 知识问答（阶段 7） | 各 references 摘取 |
| "到底准不准" | 批判质询（阶段 8） | references/piping-guide.md |
| 公历↔农历换算（起卦备数） | 阶段 5 前置 | scripts/lunar_convert.py（依赖 lunar_python） |
| 其他术数（紫微/奇门/风水/择日/占星） | 说明不在范围，不硬接 | systems-map §5 |

## 完整流程

### 阶段 0 · 收输入与路由

1. 问清三要素：**体系**（用户想用哪种：八字/六爻/六壬/小六壬/梅花/塔罗，未指定时按所问推荐——看运势走向推荐八字岁运，断一事成败推荐六爻或梅花，求速断推荐小六壬，求自省视角推荐塔罗）、**输入**（生日+时辰 / 摇卦结果 / 报数 / 农历时间 / 抽牌方式）、**所问事项**（可选但强烈建议，断卦取用神必需）。
2. 路由：八字 → 阶段 1；六爻 → 5A；大六壬 → 5B；小六壬 → 5C；梅花 → 5D；塔罗 → 5E；义理/概念 → 6/7；质询 → 8。

**质量门**：已确定体系、已拿到该体系的全部输入、已确认所问事项（断卦类必需），否则回到提问。

### 阶段 1 · 八字排盘与大运

```bash
python3 scripts/paipan.py 1985 8 11 15                    # 四柱/十神/藏干/五行统计/月令
python3 scripts/paipan.py 1985 8 11 15 --gender 男 --today 2026 8 11   # 加大运全表并定位当前
python3 scripts/paipan.py 1985 8 11 15 --gender 男 --longitude 116.4  # 出生地经度→真太阳时修正
```

- 脚本输出"距节气 N 小时"提醒（阈值 config.yaml `term_tolerance_days`）时，必须让用户复核时辰再继续。
- 用户自报四柱时跑脚本核对（立春/节气边界常错），不一致以脚本为准并说明差异原因。

**质量门**：脚本退出码 0 且输出完整（四柱/十神/藏干/五行统计/月令五项齐全）；排大运时含起运岁数与八步大运。

### 阶段 2 · 断命（调候 → 旺衰格局 → 用神 → 断律 → 仲裁）

1. **读 [references/tiaohou.md](references/tiaohou.md)**：先过调候关（寒暖燥湿偏颇时调候为急，弃扶抑须注明弃用之理）。
2. **读 [references/geju-yongshen.md](references/geju-yongshen.md)**：判旺衰（得令/得地/得势三问，两可明说）→ 定格局（月令取格、本气透干为真）→ 定用神（去病之神：旺取财官食伤、弱取印比、紧要一神、得令得用）。
3. **读 [references/mingli-program.md](references/mingli-program.md)** 第 3 节核对核心断律（官杀/伤官/财/印/比劫逐个过）。
4. 多律冲突时**读 [references/arbitration.md](references/arbitration.md)** 按五级仲裁收敛，注明仲裁路径。

**质量门**：旺衰/格局/用神各给出"依据哪条判据"；说不清的标"两可/存疑"，不许硬断。

### 阶段 3 · 岁运与应期

1. **读 [references/shensha-suiyun.md](references/shensha-suiyun.md)**：神煞配合身旺制化 → 岁运断法（大运看支、太岁看干、战冲和好四态、征太岁看救）→ 六亲/疾病/性情（注明文化参考性质）。
2. **读 [references/yingqi.md](references/yingqi.md)**：把岁运关系（合/冲/刑/神煞/用神当令）落成节气月应期表，格式"多有在 X 月（因 Y 关系、Z 支本气）应事"。
3. 命例参照可读 [references/lifan.md](references/lifan.md)（来源强度=弱，只作参照）。

**质量门**：每条岁运断语说明"行至何运何年、因喜忌如何而断"；应期断语带三要素推理链。

### 阶段 4 · 出报告（命理线）

按 [templates/report.md.template](templates/report.md.template) 生成：盘面 → 旺衰格局 → 核心断语 → 岁运 → **体系局限（必写）** → 免责声明。

**质量门**：五节齐全；"体系局限"小节不可省略（piping-guide §2 同八字异命反证必引）。

### 阶段 5 · 算卦（五分支，通用节奏：收输入 → 跑脚本 → 复述 → 读 guide → 断 → 出报告）

**5A 六爻纳甲**

```bash
python3 scripts/liuyao.py --coins 2 3 2 1 3 0 --date 2026 8 11   # 铜钱摇卦：6 次每爻报"背"的个数 0-3（自下而上）
python3 scripts/liuyao.py --numbers 3 7                          # 报数起卦（2 或 3 个数）
python3 scripts/liuyao.py --time 6 3 9 7                         # 农历时间起卦：年支序 月 日 时辰序
python3 scripts/liuyao.py --random --seed 42                     # 脚本模拟摇卦（真随机，--seed 可复现）
```

1. 收摇卦结果（用户自摇铜钱时按"背的个数"报 6 个数）或报数/时间；所问事项（取用神必需）。
2. 跑脚本 → 原样复述（卦名/宫/世应/六爻纳甲六亲六神/动变/旬空月破/旺衰/伏神）。
3. **读 [references/liuyao-guide.md](references/liuyao-guide.md)**：取用神 → 旺衰生克 → 原忌仇神 → 世应动变 → 综合断。
4. 按 [templates/divination-report.md.template](templates/divination-report.md.template) 出报告。

**质量门**：六爻全表复述完整；用神取法说明理由；每条断语带生克推理链。

**5B 大六壬**

```bash
python3 scripts/daliuren.py --datetime 2026 8 11 15     # 公历起课时间（日干支/占时/月将自动计算）
python3 scripts/daliuren.py --manual 甲子 午 亥         # 手工起课（古籍课例复算）：日干支 占时支 月将支
```

1. 收公历起课时间（或日干支+占时+月将）；所问事项。
2. 跑脚本 → 原样复述（天地盘/四课/课体/三传六亲/贵人十二天将/旬空）。
3. **读 [references/daliuren-guide.md](references/daliuren-guide.md)**：读课体 → 读三传 → 传干生克 → 贵神修饰 → 空亡旺衰修正。
4. 按 divination-report.md.template 出报告。

**质量门**：三传与课体复述完整；解读只用脚本输出要素（不自行加装神煞）；存疑处按 guide §7 口径说明。

**5C 小六壬**

```bash
python3 scripts/xiaoliuren.py --lunar 3 5 6            # 农历月 日 时辰序（子=1…亥=12）
python3 scripts/xiaoliuren.py --numbers 3 5 6          # 报三数（依次代月/日/时数）
python3 scripts/xiaoliuren.py --solar 2026 8 11 15     # 公历（依赖 lunar_python 转农历）
```

1. 收农历三数或报三数（公历先经 lunar_convert.py 换算；无 lunar_python 时让用户自报农历）。
2. 跑脚本 → 复述（月宫/日宫/断宫 + 属性 + 断辞）。
3. **读 [references/xiaoliuren-guide.md](references/xiaoliuren-guide.md)**：断宫定主调、月日宫看过程、按事项展开。
4. 简短报告（速断定位，附免责）。

**质量门**：三宫落位复述完整；结论带推理链；不把大小六壬混为一谈。

**5D 梅花易数**

```bash
python3 scripts/qigua.py --numbers 3 7                  # 报数起卦（2 或 3 个数）
python3 scripts/qigua.py --lunar 6 3 9 7                # 农历起卦：年支数 月 日 时辰数
```

1. 问起卦方式与所问事项 → 跑脚本 → 复述（本卦/互卦/变卦/动爻/体用/生克）。
2. **读 [references/duangua-guide.md](references/duangua-guide.md)** 断卦：体用深化、事项类别、旺衰、外应（仅卦象不明时参考并注明）。
3. 卦象不明（体用不分/外应冲突）如实标注。

**质量门**：卦象六项齐全；解读含推理链。

**5E 塔罗**

```bash
python3 scripts/tarot.py --spread single                # 单张
python3 scripts/tarot.py --spread three --seed 42       # 三张（过去-现在-未来），--seed 可复现
python3 scripts/tarot.py --spread celtic --no-reversals # 凯尔特十字（10 张），无逆位模式
```

1. 问牌阵（单张/三张/凯尔特十字）与所问事项 → 跑脚本 → 复述（位置/牌名/正逆位/关键词提示）。
2. **读 [references/tarot-guide.md](references/tarot-guide.md) + [references/tarot-meanings.md](references/tarot-meanings.md)**：五步解读（定基调→逐张读→牌间关系→合成结论→收尾）。
3. 逆位读作"能量受阻/内在化/提醒"，不读作"凶"；元素对应按 tarot-guide §5 版本声明（宝剑=金）。

**质量门**：抽牌结果原样复述；解读含"牌义 × 位置 × 事项 × 牌间关系"推理链；报告注明随机来源与免责。

### 阶段 6 · 义理解答（易经卦辞爻辞/概念）

**读 [references/yijing-yili.md](references/yijing-yili.md)**：

- 概念问答（阴阳/卦爻/时位/中正谦）→ 按第 2 节术语词典答，给出来源章节。
- 决策启发 → 按第 3 节规则表答，必须给出出处（卦/系辞章节）。
- 解卦辞爻辞 → 按第 4 节框架（先判位、再察时、后看谦）。

**质量门**：每条义理判断带出处；无出处即未完成。

### 阶段 7 · 术数概念问答

用神/格局/六亲/旬空/月将/体用等概念 → 从对应 references 摘取并保留溯源链接；涉及例外（伤官见官、同八字异命、克贼方向争议）如实给出承认与例外说明。

**质量门**：答案带出处；涉及例外必提。

### 阶段 8 · 批判质询

用户质疑体系有效性时（"八字/算卦到底准不准"）：**读 [references/piping-guide.md](references/piping-guide.md)**，先讲五大未证假设与同八字异命反证，再答；不替体系辩护，也不全盘否定其文化/心理价值。

**质量门**：必须引用至少一个对照案例（同八字异命），不许用"信则灵"式回应。

## 风格底线

- 事实（脚本/原文）与解读（断语）永远分节呈现。
- 语言谦和：不用"必/定/绝"；命理占卜内容只作参考与兴趣。
- 引原文前注意版本局限（三命通会缺卷十至十二、滴天髓缺任注命例、易经电子版缺字、六壬课例表克贼方向常被误标——daliuren-guide §7）。
- 随机环节（塔罗抽牌/模拟摇卦）说明随机来源与可复现性；数决定论前提未证（piping-guide §1）。
- 用户问未覆盖术数（紫微/奇门/风水/择日/西洋占星）时如实说不在范围，按 systems-map §5 转介相邻线。

## 资源文件索引（何时读）

| 文件 | 何时读 |
|---|---|
| [references/systems-map.md](references/systems-map.md) | 跨体系请求、用户问"会哪些算命"时必读 |
| [references/tiaohou.md](references/tiaohou.md) | 阶段 2 定用神前置：调候关 |
| [references/geju-yongshen.md](references/geju-yongshen.md) | 阶段 2 判格局/用神/旺衰时读 |
| [references/mingli-program.md](references/mingli-program.md) | 阶段 2 断命总程序与核心断律 |
| [references/arbitration.md](references/arbitration.md) | 阶段 2 多律冲突仲裁时读 |
| [references/shensha-suiyun.md](references/shensha-suiyun.md) | 阶段 3 岁运/六亲/疾病时读 |
| [references/yingqi.md](references/yingqi.md) | 阶段 3 应期断法（重点月份表） |
| [references/lifan.md](references/lifan.md) | 阶段 3 命例参照（来源强度=弱） |
| [references/piping-guide.md](references/piping-guide.md) | 阶段 8 必读；每次报告前过清单 |
| [references/liuyao-guide.md](references/liuyao-guide.md) | 阶段 5A 六爻断卦时读 |
| [references/daliuren-guide.md](references/daliuren-guide.md) | 阶段 5B 大六壬断课时读（含存疑清单） |
| [references/xiaoliuren-guide.md](references/xiaoliuren-guide.md) | 阶段 5C 小六壬断课时读 |
| [references/duangua-guide.md](references/duangua-guide.md) | 阶段 5D 梅花断卦时读 |
| [references/tarot-guide.md](references/tarot-guide.md) | 阶段 5E 塔罗解读流程与伦理 |
| [references/tarot-meanings.md](references/tarot-meanings.md) | 阶段 5E 牌义速查（78 张） |
| [references/yijing-yili.md](references/yijing-yili.md) | 阶段 6 义理解答时读 |
| [scripts/paipan.py](scripts/paipan.py) | 阶段 1 排盘+大运 |
| [scripts/liuyao.py](scripts/liuyao.py) | 阶段 5A 六爻装卦 |
| [scripts/daliuren.py](scripts/daliuren.py) | 阶段 5B 大六壬起课 |
| [scripts/xiaoliuren.py](scripts/xiaoliuren.py) | 阶段 5C 小六壬起课 |
| [scripts/qigua.py](scripts/qigua.py) | 阶段 5D 梅花起卦 |
| [scripts/tarot.py](scripts/tarot.py) | 阶段 5E 塔罗抽牌 |
| [scripts/lunar_convert.py](scripts/lunar_convert.py) | 阶段 5 前置：公历↔农历换算（依赖 lunar_python） |
| [scripts/common.py](scripts/common.py) | 被 liuyao/daliuren 引用的干支/节气公共库（不单独调用） |
| [templates/report.md.template](templates/report.md.template) | 阶段 4 命理报告底稿 |
| [templates/divination-report.md.template](templates/divination-report.md.template) | 阶段 5 占卜报告底稿 |
| [config.yaml](config.yaml) | 全程读取阈值（节气提醒/铜钱约定/小六壬算法/塔罗逆位） |
