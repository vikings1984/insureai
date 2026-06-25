"""采集器基类与注册"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.models import NewsItem


class BaseCollector(ABC):
    """采集器基类"""

    name: str = "base"

    @abstractmethod
    async def fetch(self, config: dict) -> list["NewsItem"]:
        """从信息源抓取内容，返回 NewsItem 列表"""
        ...

    def is_enabled(self, config: dict) -> bool:
        """检查该采集器是否启用"""
        return True


# 采集器注册表
_COLLECTORS: dict[str, type[BaseCollector]] = {}


def register_collector(name: str):
    """注册采集器装饰器"""
    def wrapper(cls: type[BaseCollector]):
        cls.name = name
        _COLLECTORS[name] = cls
        return cls
    return wrapper


def get_collector(name: str) -> type[BaseCollector]:
    """获取采集器类"""
    return _COLLECTORS[name]


def get_all_collectors() -> dict[str, type[BaseCollector]]:
    """获取所有已注册采集器"""
    return _COLLECTORS.copy()
