"""
LLM adapter modules.

采用 PEP 562 惰性导出：``from src.llm_adapters import DeepSeekAdapter`` 或
``import src.llm_adapters`` 都不会连带导入 openai / anthropic 等第三方 SDK。

原因：``base_adapter`` 是纯 Python（零第三方依赖），但此前的 eager re-export
会让任何 ``import src.agents.prompt_builder`` 都要求先装好 openai，
导致纯文本模块无法在裸环境导入，测试也无法 collect。
"""

from typing import TYPE_CHECKING, Any

_LAZY_EXPORTS = {
    "BaseLLMAdapter": "base_adapter",
    "LLMResponse": "base_adapter",
    "ToolCall": "base_adapter",
    "OpenAICompatibleAdapter": "openai_base_adapter",
    "AnthropicCompatibleAdapter": "anthropic_base_adapter",
    "DeepSeekAdapter": "deepseek_adapter",
    "MiMoAdapter": "mimo_adapter",
    "MiniMaxAdapter": "minimax_adapter",
}

__all__ = list(_LAZY_EXPORTS)

if TYPE_CHECKING:  # pragma: no cover - 仅供类型检查器，不在运行时执行
    from .anthropic_base_adapter import AnthropicCompatibleAdapter
    from .base_adapter import BaseLLMAdapter, LLMResponse, ToolCall
    from .deepseek_adapter import DeepSeekAdapter
    from .mimo_adapter import MiMoAdapter
    from .minimax_adapter import MiniMaxAdapter
    from .openai_base_adapter import OpenAICompatibleAdapter


def __getattr__(name: str) -> Any:
    """按需解析导出，避免模块级导入第三方 SDK。"""
    module_name = _LAZY_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    from importlib import import_module

    module = import_module(f".{module_name}", __name__)
    value = getattr(module, name)
    globals()[name] = value  # 缓存，后续访问不再走 __getattr__
    return value


def __dir__() -> list:
    return sorted(set(globals()) | set(__all__))
