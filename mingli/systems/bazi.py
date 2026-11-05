"""八字 Provider —— 命理线（natal 类）。"""
from __future__ import annotations

import datetime
from typing import Any

from mingli.core.knowledge import KnowledgeBase
from mingli.core.models import (
    CalculationResult,
    InterpretationResult,
    Question,
)
from mingli.engines import bazi
from mingli.engines.loader import engine_version
from mingli.systems.base import InputError

ENGINE = "xuan-shu/scripts/paipan.py"


class BaziProvider:
    id = "bazi"
    name = "八字 / 四柱"
    region = "east"
    category = ["natal"]
    status = "active"
    strengths = "看长期命局框架：性格倾向、大运流年、人生阶段节奏（出生时刻型）"
    limitations = ("旺衰/格局/用神是规则+裁量，非纯计算；女命断语与出身贵贱断法属时代局限；"
                   "同八字异命反证成立（三命通会），断语均为体系内规则语言")

    def input_schema(self) -> dict[str, Any]:
        return {
            "fields": [
                {"name": "year", "label": "出生年", "type": "int", "required": True, "min": 1900, "max": 2100},
                {"name": "month", "label": "月", "type": "int", "required": True, "min": 1, "max": 12},
                {"name": "day", "label": "日", "type": "int", "required": True, "min": 1, "max": 31},
                {"name": "hour", "label": "时（24小时制）", "type": "int", "required": False, "min": 0, "max": 23},
                {"name": "gender", "label": "性别（排大运必需）", "type": "select",
                 "options": ["男", "女"], "required": False},
                {"name": "longitude", "label": "出生地经度（可选，真太阳时修正）", "type": "float",
                 "required": False},
            ]
        }

    def validate_input(self, input_data: dict[str, Any]) -> list[str]:
        errs = []
        y = input_data.get("year")
        if not isinstance(y, int) or not 1900 <= y <= 2100:
            errs.append("年份须为 1900-2100 的整数")
            y = None
        m = input_data.get("month")
        if not isinstance(m, int) or not 1 <= m <= 12:
            errs.append("月份须为 1-12")
            m = None
        d = input_data.get("day")
        if not isinstance(d, int) or not 1 <= d <= 31:
            errs.append("日期须为 1-31")
            d = None
        elif m is not None:
            # 真实日历校验：2 月 30 日这类不存在的日期在范围检查下会漏过
            try:
                datetime.date(y or 2000, m, d)
            except ValueError:
                errs.append(f"日期不存在：{y}-{m:02d}-{d:02d}")
        h = input_data.get("hour", 12)
        if h is not None and (not isinstance(h, int) or not 0 <= h <= 23):
            errs.append("小时须为 0-23")
        g = input_data.get("gender")
        if g is not None and g not in ("男", "女"):
            errs.append("性别须为 男/女")
        return errs

    def calculate(self, input_data: dict[str, Any]) -> CalculationResult:
        if self.validate_input(input_data):
            raise InputError("；".join(self.validate_input(input_data)))
        today = input_data.get("today")
        try:
            data = bazi.bazi_calculate(
                year=input_data["year"],
                month=input_data["month"],
                day=input_data["day"],
                # 0 点（子时）是合法输入，不可用 or 兜底——falsy 会把子时换成午时
                hour=input_data["hour"] if input_data.get("hour") is not None else 12,
                gender=input_data.get("gender"),
                today=tuple(today) if today else None,
                longitude=input_data.get("longitude"),
            )
        except ValueError as e:
            raise InputError(str(e)) from e
        return CalculationResult(
            systemId=self.id,
            engine=ENGINE,
            engineVersion=engine_version("paipan"),
            inputSnapshot={"y": input_data["year"], "m": input_data["month"],
                           "d": input_data["day"],
                           "h": input_data["hour"] if input_data.get("hour") is not None else 12,
                           "gender": input_data.get("gender"),
                           "longitude": input_data.get("longitude")},
            data=data,
            rawText="",
            warnings=data.get("warnings", []),
        )

    def interpret(
        self,
        calculation: CalculationResult,
        question: Question | None,
        knowledge: KnowledgeBase,
    ) -> InterpretationResult:
        from mingli.systems.bazi_interpret import interpret_bazi
        return interpret_bazi(calculation, question, knowledge)

    def recommend_for(self, question: Question) -> float:
        from mingli.core.router import classify_question
        cls = classify_question(question.text)
        score = 0.0
        if "natal" and (cls.category == "self" or cls.horizon == "long-term"):
            score += 0.6
        if cls.hasTiming or cls.category == "timing":
            score += 0.3
        if cls.category in ("career", "relationship", "finance", "study"):
            score += 0.2
        if cls.category in ("decision",) and cls.horizon == "near-term":
            score -= 0.4   # 具体一事不宜单用八字——诚实降分
        return max(0.0, min(1.0, score))
