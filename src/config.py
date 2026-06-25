"""配置加载模块"""

from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any


def get_project_root() -> Path:
    """获取项目根目录"""
    return Path(__file__).parent.parent


def load_config() -> dict[str, Any]:
    """加载 config.json 配置"""
    config_path = get_project_root() / "data" / "config.json"
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_env() -> dict[str, str]:
    """加载 .env 文件"""
    env_path = get_project_root() / ".env"
    env_vars = {}
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    env_vars[key.strip()] = value.strip()
    return env_vars


def get_env_var(key: str, default: str = "") -> str:
    """获取环境变量，优先 .env 文件"""
    # 先检查系统环境变量
    value = os.environ.get(key)
    if value:
        return value
    # 再检查 .env 文件
    env_vars = load_env()
    return env_vars.get(key, default)


def get_categories(config: dict) -> dict:
    """获取分类配置"""
    return config.get("categories", {})


def get_sources(config: dict) -> dict:
    """获取信息源配置"""
    return config.get("sources", {})


def get_ai_config(config: dict) -> dict:
    """获取AI配置"""
    return config.get("ai", {})


def get_scoring_config(config: dict) -> dict:
    """获取评分配置"""
    return config.get("scoring", {})


def get_filtering_config(config: dict) -> dict:
    """获取过滤配置"""
    return config.get("filtering", {})


def get_output_config(config: dict) -> dict:
    """获取输出配置"""
    return config.get("output", {})
