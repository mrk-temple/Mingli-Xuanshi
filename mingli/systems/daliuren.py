"""大六壬 Provider —— 六壬线（moment 类）。"""
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
from mingli.engines import daliuren as dlr_engine
from mingli.engines.loader import engine_version
from mingli.systems.base import InputError

ENGINE = "xuan-shu/scripts/daliuren.py"


class DaliurenProvider:
    id = "daliuren"
    name = "大六壬"
    region = "east"
    category = ["moment"]
    status = "active"
    strengths = "天地盘/四课/三传断一事之起因过程结局，课体定事之性质（三式之一）"
    limitations = ("确定性到'三传'为止；断课只用脚本输出要素（不自行加装神煞/年命）；"
                   "九宗门歧义已按通行规则实现并标注存疑清单")

    def input_schema(self) -> dict[str, Any]:
        return {
            "fields": [
                {"name": "mode", "label": "起课方式", "type": "select",
                 "options": ["datetime", "manual"], "required": True},
                {"name": "datetimeInput", "label": "公历起课时间（年 月 日 时）", "type": "int-list",
                 "required": False},
                {"name": "dayGanZhi", "label": "日干支（手工模式，如 甲子）", "type": "text", "required": False},
                {"name": "hourZhi", "label": "占时支（手工模式，如 午）", "type": "text", "required": False},
                {"name": "yueJiangZhi", "label": "月将支（手工模式，如 亥）", "type": "text", "required": False},
            ]
        }

    def validate_input(self, input_data: dict[str, Any]) -> list[str]:
        errs = []
        mode = input_data.get("mode")
        if mode not in ("datetime", "manual"):
            errs.append("mode 须为 datetime/manual")
            return errs
        if mode == "datetime":
            dt = input_data.get("datetimeInput") or []
            if len(dt) != 4:
                errs.append("公历起课需要 年 月 日 时 四个数")
        else:
            if not all(input_data.get(k) for k in ("dayGanZhi", "hourZhi", "yueJiangZhi")):
                errs.append("手工起课需要 日干支 + 占时支 + 月将支")
        return errs

    def calculate(self, input_data: dict[str, Any]) -> CalculationResult:
        if self.validate_input(input_data):
            raise InputError("；".join(self.validate_input(input_data)))
        try:
            data = dlr_engine.daliuren_calculate(
                datetime_input=input_data.get("datetimeInput"),
                manual=(input_data["dayGanZhi"], input_data["hourZhi"], input_data["yueJiangZhi"])
                if input_data.get("mode") == "manual" else None,
            )
        except ValueError as e:
            raise InputError(str(e)) from e
        return CalculationResult(
            systemId=self.id,
            engine=ENGINE,
            engineVersion=engine_version("daliuren"),
            inputSnapshot={"mode": input_data["mode"], **{
                k: v for k, v in input_data.items()
                if k in ("datetimeInput", "dayGanZhi", "hourZhi", "yueJiangZhi")}},
            data=data,
            rawText="",
            warnings=[data["note"]] if data.get("note") else [],
        )

    def interpret(
        self,
        calculation: CalculationResult,
        question: Question | None,
        knowledge: KnowledgeBase,
    ) -> InterpretationResult:
        data = calculation.data
        conclusions: list[Conclusion] = []
        uncertainty: list[str] = []

        # 课体主题（daliuren-guide §3）
        conclusions.append(build_conclusion(
            claim=f"课体为「{data['keTi']}」——定事之性质",
            reasoning=[
                "九宗门发传由四课克贼关系确定（脚本计算），课体主题见 daliuren-guide §3 表",
                "课体定'事之性质'，三传定'事之走向'：两者合读",
            ],
            rules=[RuleRef(
                ruleId="daliuren/keti-theme",
                source="《六壬大全》卷五 / references/daliuren-guide.md §3",
                sourceLevel="B")],
            calc_refs=["keTi"],
            polarity="neutral",
        ))

        # 三传读法
        sc = data.get("sanChuan") or []
        if sc:
            chain_txt = "、".join(f"{c['label']}{c['zhi']}({c['wuxing']}·{c['liuqin']})" for c in sc)
            sheng_chain = _chuan_relation(sc)
            chuan_pol = _chuan_polarity(sheng_chain)
            conclusions.append(build_conclusion(
                claim=f"三传：{chain_txt}。{sheng_chain}",
                reasoning=[
                    "初传看起因、中传看过程、末传看结果（daliuren-guide §2）",
                    f"三传六亲以日干{data['dayGanZhi'][0]}（{data['dayGanWuxing']}）为'我'：父母=文书庇荫、兄弟=同辈分耗、子孙=喜悦制鬼、妻财=财物利益、官鬼=压力官非",
                    "传生干吉、传克干凶、初传克日主事发即不利；空亡旺衰再修正",
                ],
                rules=[RuleRef(
                    ruleId="daliuren/sanchuan",
                    source="《六壬大全》三传断法 / references/daliuren-guide.md §2",
                    sourceLevel="B")],
                calc_refs=["sanChuan"],
                polarity=chuan_pol,
            ))
            empty = data.get("xunKong") or []
            kong_hits = [c["label"] for c in sc if c["zhi"] in empty]
            if kong_hits:
                uncertainty.append(f"{'、'.join(kong_hits)}落旬空：主虚、暂不应，出空填实方应")
        else:
            uncertainty.append("三传未定（课式特殊）：如实说明，不硬断")

        if data.get("note"):
            uncertainty.append(f"流派注记：{data['note']}")

        return InterpretationResult(
            systemId="daliuren",
            summary=f"{data['dayGanZhi']}日{data['zhanShi']}时，月将{data['yueJiang']['name']}。课体「{data['keTi']}」。体系内规则语言。",
            conclusions=conclusions,
            uncertainty=uncertainty,
            limitations=[
                "断课只用脚本输出要素，不自行加装神煞/年命（细节繁复不在本引擎范围）",
                "涉害计数、八专中末传、返吟驿马取法、贵人昼夜分界均按主流选择实现，存疑清单见 daliuren-guide §7",
                "常见流传课例表'克/贼'方向常有误标——以标准定义与《六壬大全》原文为准",
            ],
            interpreter="rule-engine",
        )

    def recommend_for(self, question: Question) -> float:
        from mingli.core.router import classify_question
        cls = classify_question(question.text)
        score = 0.0
        if cls.hasTiming or cls.horizon == "near-term" or cls.category == "decision":
            score += 0.4
        if any(w in question.text for w in ("方向", "行动", "时机", "何时")):
            score += 0.2
        return max(0.0, min(1.0, score))


def _chuan_polarity(relation_txt: str) -> str:
    """三传关系 → 主极性（对照引擎用）。只对明确的顺生/逆克定型，其余中性。"""
    if "顺生" in relation_txt:
        return "positive"
    if "逆克" in relation_txt or "阻滞" in relation_txt:
        return "negative"
    return "neutral"


def _chuan_relation(chuan: list[dict]) -> str:
    """三传顺生/逆克等关系描述。"""
    if len(chuan) < 3:
        return ""
    wxs = [c["wuxing"] for c in chuan]
    from mingli.engines.loader import load_engine
    SHENG = load_engine("common").SHENG
    KE = load_engine("common").KE
    if SHENG[wxs[0]] == wxs[1] and SHENG[wxs[1]] == wxs[2]:
        return "三传顺生：初生中、中生末，主顺畅"
    if KE[wxs[0]] == wxs[1] and KE[wxs[1]] == wxs[2]:
        return "三传递克：主阻滞连环"
    qins = [c["liuqin"] for c in chuan]
    if all(q != "官鬼" for q in qins):
        return "三传不见官鬼克日：压力不重"
    if qins[0] == "官鬼":
        return "初传官鬼：事发即有压力，看中末有无子孙制鬼"
    return "三传生克交错：逐传导读"


class _Unused:
    pass
