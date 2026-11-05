"""Registry 装配入口 —— 创建全局唯一 registry 并注册全部 Provider。"""
from __future__ import annotations

import os
from functools import lru_cache

from mingli.core.registry import SystemRegistry

_DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "registry_data.yaml")


@lru_cache(maxsize=1)
def get_registry() -> SystemRegistry:
    reg = SystemRegistry()
    # active 体系
    from mingli.systems.bazi import BaziProvider
    from mingli.systems.daliuren import DaliurenProvider
    from mingli.systems.liuyao import LiuyaoProvider
    from mingli.systems.meihua import MeihuaProvider
    from mingli.systems.tarot import TarotProvider
    from mingli.systems.xiaoliuren import XiaoliurenProvider
    from mingli.systems.yijing import YijingProvider

    for p in (BaziProvider(), LiuyaoProvider(), DaliurenProvider(),
              XiaoliurenProvider(), MeihuaProvider(), TarotProvider(), YijingProvider()):
        reg.register(p)

    # planned / knowledge-only 登记表（诚实呈现未实现体系）
    reg.load_planned_yaml(_DATA_FILE)
    return reg


def reset_registry_cache() -> None:
    """测试用。"""
    get_registry.cache_clear()
