"""Provider 构建、密钥加载与调用计量。

密钥来源优先级与冲突处理见 load_keys()——那里刻意不做「静默优先级」。

设计文档中记录的能力结论来自 2026-10-08 的真实探测，
证据记录在 docs/history/skill-mode-design.md 的 F-011 ~ F-016。
--probe 可随时复验连通性。
"""
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

from src.llm_adapters.base_adapter import BaseLLMAdapter, LLMResponse

# 2026-10-08 实测结论（证据见 docs/history/skill-mode-design.md F-011~F-016）。
# 这些不是文档摘抄，是探测结果。
# 与 config/agentX_config.yaml 保持一致。None = 不干预供应商默认。
THINKING: Optional[bool] = False

PROVIDERS: Dict[str, dict] = {
    "deepseek": {
        "model": "deepseek-flash",
        "base_url": "https://api.deepseek.com",
        "env": "DEEPSEEK_API_KEY",
        "supports_function_strict": True,
        "supports_response_format_json_schema": False,
        "supports_tool_choice_required": False,
    },
    "mimo": {
        "model": "mimo-v2.6-flash",
        "base_url": "https://api.xiaomimimo.com/v1",
        "env": "MIMO_API_KEY",
        "supports_function_strict": True,
        "supports_response_format_json_schema": True,
        "supports_tool_choice_required": None,  # 未测
    },
}

# api-standard §7.6 的三条硬约束，实现决策契约时不得违反
FORBIDDEN = {
    "strict_in_response_format": "DeepSeek 返回 400 This response_format type is unavailable now",
    "tool_choice_required": "DeepSeek 返回 400 Thinking mode does not support this tool_choice",
    "drop_reasoning_content": "两家均为 thinking model，多轮回送缺字段会报错",
}

# 文件里的一行形如：【Mimo】只能用 mimo-v2.6-flash，KEY 是 sk-xxxx
_LINE_RE = re.compile("【([\\w\\-]+)】.*?(sk-[A-Za-z0-9_\\-]+)")


class MissingKey(RuntimeError):
    pass


class KeyConflict(RuntimeError):
    """同一 provider 的环境变量与文件给出了不同的密钥。"""


def mask(k: str) -> str:
    return k[:9] + "***"


def _read_key_file(path: str) -> Dict[str, str]:
    p = Path(path)
    if not p.exists():
        raise MissingKey("api-file 不存在: %s" % p)
    out: Dict[str, str] = {}
    for line in p.read_bytes().decode("utf-8-sig").splitlines():
        m = _LINE_RE.search(line)
        if m:
            out[m.group(1).lower()] = m.group(2)
    return out


def load_keys(api_file: Optional[str] = None) -> Dict[str, str]:
    """读取密钥。

    来源规则（刻意设计成「冲突即报错」，绝不静默二选一）：
      - 给了 --api-file：文件为准；环境变量只补文件里没有的 provider。
      - 没给 --api-file：只用环境变量。
      - 两者对同一 provider 给出不同值 -> 抛 KeyConflict。

    静默优先级是个陷阱。本机 MIMO_API_KEY 环境变量里存的是一把已失效的旧
    key，而 TEST_API.txt 里是有效 key。谁优先都不对，必须让人来决定。
    """
    file_keys = _read_key_file(api_file) if api_file else {}

    env_keys = {}
    for name, meta in PROVIDERS.items():
        v = os.environ.get(meta["env"])
        if v and v.strip():
            env_keys[name] = v.strip()

    if not api_file:
        keys = dict(env_keys)
    else:
        keys = {}
        conflicts = []
        for name, meta in PROVIDERS.items():
            e, f = env_keys.get(name), file_keys.get(name)
            if f and e and e != f:
                conflicts.append("%s: 环境变量 %s=%s，与文件里的值不同"
                                 % (name, meta["env"], mask(e)))
            keys[name] = f or e
        if conflicts:
            raise KeyConflict(
                "密钥来源冲突，已中止，未发出任何请求：\n  "
                + "\n  ".join(conflicts)
                + "\n\n  二选一处理：\n"
                "    1) 清掉冲突的环境变量后重跑\n"
                "    2) 确认要用哪一把，改环境变量或改文件\n"
                "  不设默认优先级——「默认优先级」正是这个 bug 的成因。"
            )

    missing = [n for n in PROVIDERS if not keys.get(n)]
    if missing:
        raise MissingKey(
            "缺少密钥: %s。设置环境变量，或用 --api-file 指向密钥文件。" % ", ".join(missing)
        )
    return keys


def build_adapter(name: str, api_key: str, thinking: Optional[bool] = None) -> BaseLLMAdapter:
    """构造仓库既有的适配器实例（不新增 provider 分支）。

    thinking 传 None 表示沿用 THINKING 默认（与 config 一致）；
    显式传 True/False 用于 A/B 对照。
    """
    if thinking is None:
        thinking = THINKING
    meta = PROVIDERS[name]
    if name == "deepseek":
        from src.llm_adapters.deepseek_adapter import DeepSeekAdapter
        return DeepSeekAdapter(api_key=api_key, model=meta["model"],
                                base_url=meta["base_url"], thinking=thinking)
    if name == "mimo":
        from src.llm_adapters.mimo_adapter import MiMoAdapter
        return MiMoAdapter(api_key=api_key, model=meta["model"],
                           base_url=meta["base_url"], thinking=thinking)
    raise ValueError("unknown provider: %s" % name)


class InstrumentedAdapter(BaseLLMAdapter):
    """透明包装既有适配器，只做计量。

    不改变任何请求参数或响应内容——它必须对被测代码完全不可见，
    否则基线就不再是「现状」的基线。
    """

    def __init__(self, inner: BaseLLMAdapter):
        self.inner = inner
        self.model = inner.model
        self.base_url = inner.base_url
        self.temperature = getattr(inner, "temperature", 0.7)
        self.max_retries = getattr(inner, "max_retries", 3)
        self.reset_stats()

    def __getattr__(self, name):
        # 透明包装的完整定义：被测代码能读到的任何属性，包装层都得能读到。
        # 否则包装会静默改变被测行为——已经曾因此让 MiMo 误走
        # tool_choice 通道（它会忽视 required），从而把契约背去了（F-027）。
        if name == "inner":
            raise AttributeError(name)
        return getattr(self.inner, name)


    def reset_stats(self) -> None:
        self.llm_calls = 0
        self.tool_call_turns = 0
        self.content_only_turns = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self.errors = 0
        self.error_samples: List[str] = []

    async def chat(self, messages, tools=None, **kwargs) -> LLMResponse:
        self.llm_calls += 1
        try:
            resp = await self.inner.chat(messages, tools=tools, **kwargs)
        except Exception as e:
            self.errors += 1
            if len(self.error_samples) < 3:
                self.error_samples.append("%s: %s" % (type(e).__name__, str(e)[:160]))
            raise

        if resp.has_tool_calls():
            self.tool_call_turns += 1
        else:
            # 纯文本回复 = 走的是正则提取路径，是重试的先行指标
            self.content_only_turns += 1

        usage = getattr(resp.raw_response, "usage", None)
        if usage is not None:
            self.prompt_tokens += int(getattr(usage, "prompt_tokens", 0) or 0)
            self.completion_tokens += int(getattr(usage, "completion_tokens", 0) or 0)
            self.total_tokens += int(getattr(usage, "total_tokens", 0) or 0)
        return resp

    async def close(self):
        await self.inner.close()

    def stats(self) -> dict:
        return {
            "llm_calls": self.llm_calls,
            "tool_call_turns": self.tool_call_turns,
            "content_only_turns": self.content_only_turns,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "errors": self.errors,
            "error_samples": list(self.error_samples),
        }


async def probe(keys: Dict[str, str]) -> List[dict]:
    """复验两家连通性。

    keys 由调用方传入——不要在这里重读密钥来源，否则会丢掉 --api-file。
    """
    out = []
    for name, meta in PROVIDERS.items():
        adapter = build_adapter(name, keys[name])
        rec = {"provider": name, "model": meta["model"], "base_url": meta["base_url"]}
        try:
            r = await adapter.chat(
                [{"role": "user", "content": "只回答数字：1+1=？"}], max_tokens=32)
            rec["chat_ok"] = True
            rec["has_thought"] = bool(r.thought)
        except Exception as e:
            rec["chat_ok"] = False
            rec["error"] = "%s: %s" % (type(e).__name__, str(e)[:200])
        finally:
            try:
                await adapter.close()
            except Exception:
                pass
        rec["capabilities"] = {k: v for k, v in meta.items() if k.startswith("supports_")}
        out.append(rec)
    return out