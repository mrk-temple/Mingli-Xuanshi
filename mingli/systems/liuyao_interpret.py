"""六爻解读 —— 取用神 + 旺衰生克（规则版，依据 liuyao-guide.md）。"""
from __future__ import annotations

from typing import Any

from mingli.core.interpret.rules import build_conclusion
from mingli.core.knowledge import KnowledgeBase
from mingli.core.models import (
    CalculationResult,
    Conclusion,
    InterpretationResult,
    Question,
    RuleRef,
)

# 用神表（liuyao-guide §2）
_YONGSHEN_TABLE = {
    "finance": "妻财",
    "career": "官鬼",
    "study": "父母",
    "relationship": "官鬼",  # 女测感情；男测感情取妻财——两可标注
}

# 原忌仇神表（liuyao-guide §5）
_YUAN_SHEN = {"父母": "官鬼", "兄弟": "父母", "子孙": "兄弟", "妻财": "子孙", "官鬼": "妻财"}
_JI_SHEN = {"父母": "妻财", "兄弟": "官鬼", "子孙": "父母", "妻财": "兄弟", "官鬼": "子孙"}

_WANGSHUAI_ORDER = ["旺", "相", "休", "囚", "死"]

_LIMITS = [
    "装卦确定，但取用神与吉凶推断是规则+裁量（增删卜易惯例）",
    "占筮有效性前提：随机起数→所问之事的关联未被论证（数决定论）",
    "流派分歧已按主流显式选择：字=阴背=阳、变爻六亲以本卦宫为'我'、六神按日干",
]


def interpret_liuyao(
    calculation: CalculationResult,
    question: Question | None,
    knowledge: KnowledgeBase,
) -> InterpretationResult:
    data = calculation.data
    ben = data["benGua"]
    conclusions: list[Conclusion] = []
    uncertainty: list[str] = []

    # ── 复述事实已在报告层完成；这里做规则读法 ──
    # 1. 定用神
    yongshen: str | None = None
    ys_reason = ""
    if question is not None and question.category in _YONGSHEN_TABLE:
        yongshen = _YONGSHEN_TABLE[question.category]
        ys_reason = f"所问为{question.category}类事项，按 liuyao-guide §2 用神表取「{yongshen}」"
        if question.category == "relationship":
            uncertainty.append("感情类用神分性别惯例：男测取妻财、女测取官鬼——本报告默认取官鬼，请按实际校正")
    else:
        # 无明确事项 → 以世爻为观察点并如实说明
        uncertainty.append("未确认所问事项，无法取用神（一卦一问、不动无占）；以下以世爻为观察点")

    target_lines = [yao for yao in ben["lines"] if (yongshen and yao["liuqin"] == yongshen) or (not yongshen and yao["role"] == "世")]
    if not target_lines and yongshen and data.get("fuShen"):
        fu = next((f for f in data["fuShen"] if f["liuqin"] == yongshen), None)
        if fu:
            uncertainty.append(f"本卦无{yongshen}爻，用神伏藏（伏神在第{fu['position']}爻），主此事不显于表面")

    for line in target_lines[:1]:  # 取第一处用神（两现问题标不确定）
        same_qin = [yao for yao in ben["lines"] if yao["liuqin"] == line["liuqin"]]
        if len(same_qin) > 1:
            uncertainty.append(f"用神两现（{len(same_qin)}处{line['liuqin']}爻），取舍依'舍其闲爻取被冲被合/动爻/临世应'惯例，须结合事项裁定")
        ws = line["wangShuai"]
        rank = _WANGSHUAI_ORDER.index(ws)
        marks = "、".join(line["marks"]) if line["marks"] else "无空破标记"
        claim = (f"用神{line['liuqin']}爻（第{line['position']}爻 {line['najia']}）"
                 f"对月建处「{ws}」地，标记：{marks}")
        reasoning = [
            f"月建{data['yueJian']['zhi']}（{data['yueJian']['wuxing']}）：该爻五行{line['zhiWuxing']}，旺相休囚死判为「{ws}」",
            f"起卦日{data['dayGanZhi']}" + ("，爻值日辰以旺论" if "值日辰" in line["marks"] else "，日辰为第二基准"),
        ]
        if "旬空" in line["marks"]:
            reasoning.append("爻落旬空：主'暂不应/虚而不实'，出空填实后方应——是状态标注不是必凶")
        if "月破" in line["marks"]:
            reasoning.append("爻逢月破：当月无力事有阻，出月后复起；值日辰合扶可解")
        verdict_hint = "倾向有力" if rank <= 1 else ("偏弱" if rank <= 3 else "受制明显")
        reasoning.append(f"综合判定：用神{verdict_hint}")
        pol = "positive" if rank <= 1 else ("neutral" if rank == 2 else "negative")
        conclusions.append(build_conclusion(
            claim=claim,
            reasoning=reasoning,
            rules=[RuleRef(
                ruleId="liuyao/yongshen-wangshuai",
                source="《增删卜易》旺衰章 / references/liuyao-guide.md §3",
                sourceLevel="B")],
            calc_refs=[f"benGua.lines[{line['position'] - 1}]"],
            polarity=pol,
        ))

        # 原神忌神
        yuan = _YUAN_SHEN.get(line["liuqin"])
        ji = _JI_SHEN.get(line["liuqin"])
        yuan_lines = [yao for yao in ben["lines"] if yao["liuqin"] == yuan]
        ji_lines = [yao for yao in ben["lines"] if yao["liuqin"] == ji]
        conclusions.append(build_conclusion(
            claim=f"原神「{yuan}」{'在卦（' + str(len(yuan_lines)) + '处）' if yuan_lines else '不上卦'}，"
                  f"忌神「{ji}」{'在卦（' + str(len(ji_lines)) + '处）' if ji_lines else '不上卦'}",
            reasoning=[
                f"生克链：{'→'.join([line['liuqin'], yuan or '—', ji or '—'])}（原神生用神、忌神克用神）",
                ("原神在卦且旺则用神有救" if yuan_lines else "原神不上卦：用神孤弱时无救援"),
                ("忌神在卦：看其是否动而克用——静而衰不足为患" if ji_lines else "忌神不上卦：用神少一重克制"),
            ],
            rules=[RuleRef(
                ruleId="liuyao/yuanji-choushen",
                source="《增删卜易》原忌仇神 / references/liuyao-guide.md §5",
                sourceLevel="B")],
            calc_refs=["benGua.lines"],
        ))

    # 2. 世应关系
    shi_line = next(yao for yao in ben["lines"] if yao["role"] == "世")
    ying_line = next(yao for yao in ben["lines"] if yao["role"] == "应")
    common = load_common()
    rel = _relation(shi_line["zhiWuxing"], ying_line["zhiWuxing"], common.SHENG, common.KE)
    rel_pol = {"应生世": "positive", "比和": "neutral", "应克世": "negative", "世生应": "negative",
               "世克应": "neutral"}.get(rel, "neutral")
    conclusions.append(build_conclusion(
        claim=f"世爻（第{shi_line['position']}爻）与应爻（第{ying_line['position']}爻）呈「{rel}」关系",
        reasoning=[
            f"世爻五行{shi_line['zhiWuxing']}，应爻五行{ying_line['zhiWuxing']}",
            "世应生克定事之顺逆：应生世吉、世生应耗、应克世逆、比和则平（liuyao-guide §4）",
        ],
        rules=[RuleRef(
            ruleId="liuyao/shiying",
            source="六爻通行断法 / references/liuyao-guide.md §4",
            sourceLevel="B")],
        calc_refs=[f"benGua.lines[{shi_line['position'] - 1}]", f"benGua.lines[{ying_line['position'] - 1}]"],
        polarity=rel_pol,
    ))

    # 3. 动变
    moving_lines = [yao for yao in ben["lines"] if yao["moving"]]
    if moving_lines:
        for ml in moving_lines[:2]:
            bian = ml.get("bianYao")
            bian_txt = f"，化出{bian['ganZhi']}（{bian['liuqin']}）" if bian else ""
            bian_pol = "neutral"
            if bian:
                bian_pol = "positive" if _is_sheng(bian["liuqin"], ml["liuqin"]) else "negative"
            conclusions.append(build_conclusion(
                claim=f"第{ml['position']}爻动（{ml['najia']}，{ml['liuqin']}）{bian_txt}",
                reasoning=[
                    "动爻为事之机：动爻对用神/世爻的生克是断卦重点（liuyao-guide §4）",
                    (f"变爻以本卦宫为'我'定六亲：回头{'生' if _is_sheng(bian['liuqin'], ml['liuqin']) else '克'}动爻"
                     if bian else ""),
                ],
                rules=[RuleRef(
                    ruleId="liuyao/dongbian",
                    source="《增删卜易》动变章 / references/liuyao-guide.md §4",
                    sourceLevel="B")],
                calc_refs=[f"benGua.lines[{ml['position'] - 1}]"],
                polarity=bian_pol,
            ))
    else:
        uncertainty.append("无动爻（静卦）：以月建日辰与用神关系为主判断")

    return InterpretationResult(
        systemId="liuyao",
        summary=(f"{ben['name']}（{ben['palace']}宫）变{data['bianGua']['name']}。"
                 + (ys_reason + "。" if ys_reason else "")
                 + "以上为体系内规则语言，非事实断言。"),
        conclusions=conclusions,
        uncertainty=uncertainty,
        limitations=_LIMITS,
        interpreter="rule-engine",
    )


def _relation(wx_a: str, wx_b: str, SHENG: dict, KE: dict) -> str:
    if wx_a == wx_b:
        return "比和"
    if SHENG.get(wx_b) == wx_a:
        return "应生世"
    if SHENG.get(wx_a) == wx_b:
        return "世生应"
    if KE.get(wx_b) == wx_a:
        return "应克世"
    return "世克应"


def _is_sheng(a: str, b: str) -> bool:
    from mingli.engines.loader import load_engine
    return load_engine("common").SHENG.get(a) == b


def load_common():
    from mingli.engines.loader import load_engine
    return load_engine("common")


def _unused(*a: Any) -> None:  # 占位：保持导入整洁
    pass
