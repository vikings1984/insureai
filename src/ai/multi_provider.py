"""多 AI 提供商管理器

支持故障自动切换和负载均衡
借鉴 Horizon 的多 AI 提供商架构
"""

from __future__ import annotations
import json
import asyncio
from typing import Optional
from dataclasses import dataclass
from enum import Enum


class AIProvider(Enum):
    """AI 提供商枚举"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    ALI = "ali"
    LOCAL = "local"


@dataclass
class ProviderConfig:
    """提供商配置"""
    name: str
    provider: AIProvider
    model: str
    api_key_env: str
    base_url: str = ""
    priority: int = 1  # 优先级，数字越小优先级越高
    enabled: bool = True


class MultiProviderManager:
    """多 AI 提供商管理器"""

    # 默认提供商配置
    DEFAULT_PROVIDERS = {
        "openai": ProviderConfig(
            name="OpenAI",
            provider=AIProvider.OPENAI,
            model="gpt-4o",
            api_key_env="OPENAI_API_KEY",
            priority=1,
        ),
        "anthropic": ProviderConfig(
            name="Anthropic",
            provider=AIProvider.ANTHROPIC,
            model="claude-3-5-sonnet-20241022",
            api_key_env="ANTHROPIC_API_KEY",
            priority=2,
        ),
        "ali": ProviderConfig(
            name="阿里云",
            provider=AIProvider.ALI,
            model="qwen-max",
            api_key_env="DASHSCOPE_API_KEY",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            priority=3,
        ),
    }

    def __init__(self, config: dict):
        self.config = config
        self.ai_config = config.get("ai", {})
        
        # 初始化提供商列表
        self.providers: list[ProviderConfig] = []
        self._init_providers()
        
        # 统计信息
        self.stats = {p.name: {"success": 0, "fail": 0} for p in self.providers}

    def _init_providers(self):
        """初始化提供商列表"""
        # 主提供商
        primary = self.ai_config.get("provider", "openai")
        fallback = self.ai_config.get("fallback_providers", ["anthropic", "ali"])
        
        # 添加主提供商
        if primary in self.DEFAULT_PROVIDERS:
            cfg = self.DEFAULT_PROVIDERS[primary]
            # 允许配置覆盖
            cfg.model = self.ai_config.get("model", cfg.model)
            cfg.api_key_env = self.ai_config.get("api_key_env", cfg.api_key_env)
            cfg.base_url = self.ai_config.get("base_url", cfg.base_url)
            self.providers.append(cfg)
        
        # 添加备用提供商
        for name in fallback:
            if name in self.DEFAULT_PROVIDERS and name != primary:
                self.providers.append(self.DEFAULT_PROVIDERS[name])
        
        # 按优先级排序
        self.providers.sort(key=lambda x: x.priority)

    def _get_api_key(self, env_var: str) -> Optional[str]:
        """获取 API Key"""
        import os
        return os.getenv(env_var)

    async def call_with_fallback(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        """
        调用 AI，支持故障自动切换
        
        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词
            temperature: 温度参数
            max_tokens: 最大 token 数
            
        Returns:
            AI 响应文本
            
        Raises:
            Exception: 所有提供商都失败时抛出
        """
        last_error = None
        
        for provider in self.providers:
            if not provider.enabled:
                continue
                
            api_key = self._get_api_key(provider.api_key_env)
            if not api_key:
                print(f"[MultiProvider] {provider.name}: API Key 未配置，跳过")
                continue
            
            try:
                print(f"[MultiProvider] 尝试使用 {provider.name}...")
                
                if provider.provider == AIProvider.OPENAI or provider.provider == AIProvider.ALI:
                    result = await self._call_openai_compatible(
                        provider=provider,
                        api_key=api_key,
                        prompt=prompt,
                        system_prompt=system_prompt,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                elif provider.provider == AIProvider.ANTHROPIC:
                    result = await self._call_anthropic(
                        provider=provider,
                        api_key=api_key,
                        prompt=prompt,
                        system_prompt=system_prompt,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                else:
                    continue
                
                # 成功
                self.stats[provider.name]["success"] += 1
                print(f"[MultiProvider] {provider.name} 调用成功")
                return result
                
            except Exception as e:
                self.stats[provider.name]["fail"] += 1
                last_error = e
                print(f"[MultiProvider] {provider.name} 失败: {e}")
                continue
        
        # 所有提供商都失败
        raise Exception(f"所有 AI 提供商都失败。最后一个错误: {last_error}")

    async def _call_openai_compatible(
        self,
        provider: ProviderConfig,
        api_key: str,
        prompt: str,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """调用 OpenAI 兼容 API"""
        from openai import AsyncOpenAI
        
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=provider.base_url if provider.base_url else None,
        )
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        response = await client.chat.completions.create(
            model=provider.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        
        return response.choices[0].message.content

    async def _call_anthropic(
        self,
        provider: ProviderConfig,
        api_key: str,
        prompt: str,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """调用 Anthropic API"""
        from anthropic import AsyncAnthropic
        
        client = AsyncAnthropic(api_key=api_key)
        
        response = await client.messages.create(
            model=provider.model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
        )
        
        return response.content[0].text

    def get_stats(self) -> dict:
        """获取提供商统计信息"""
        return {
            "providers": [
                {
                    "name": p.name,
                    "enabled": p.enabled,
                    "success": self.stats[p.name]["success"],
                    "fail": self.stats[p.name]["fail"],
                    "success_rate": (
                        self.stats[p.name]["success"] / 
                        (self.stats[p.name]["success"] + self.stats[p.name]["fail"])
                        if (self.stats[p.name]["success"] + self.stats[p.name]["fail"]) > 0
                        else 0
                    ),
                }
                for p in self.providers
            ]
        }
