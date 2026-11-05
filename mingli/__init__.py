"""命理玄师 Mingli XuanShi —— 东西方术数研究与实验工作台。

架构铁律（源自 xuan-shu skill，升级为程序约束）：
- 排盘/起卦/抽牌一律由确定性引擎计算（mingli.engines 包装 xuan-shu/scripts）
- 事实与解读分离：CalculationResult 是事实，InterpretationResult 是体系内解读
- 断语必须带推理链与规则引用；报告强制"体系局限"与"免责声明"
- 跨体系只对照不融合
"""

__version__ = "0.1.0"
