"""W-01 反向守卫：消息序列必须符合供应商协议。

这些断言守的是「协议会不会悄悄退化」。之前它们不存在，所以 assistant
从不写回、tool 结果被伪装成 user 消息、连续 user 消息都没人发现。

对应契约：docs/api-standard.md §3.4 (R-1/R-2/R-3) 与 §4.2 的 Anthropic 转换。
"""
import pytest

from src.agents.prompt_builder import PromptBuilder
from src.llm_adapters.anthropic_base_adapter import AnthropicCompatibleAdapter


def _assistant_with_tool_calls(*calls):
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": cid,
                "type": "function",
                "function": {"name": name, "arguments": "{}"},
            }
            for cid, name in calls
        ],
    }


def _assert_no_consecutive_user(messages):
    roles = [m.get("role") for m in messages]
    for a, b in zip(roles, roles[1:]):
        assert not (a == "user" and b == "user"), (
            "连续 user 消息在 Anthropic Messages API 下非法 (R-3): %s" % roles
        )


# ---------------------------------------------------------------- R-1 / R-2

def test_tool_results_are_tied_back_to_calls_by_id():
    """工具结果必须带 tool_call_id，且数量与 assistant 的 tool_calls 一致。"""
    pb = PromptBuilder("sys")
    pb.add_tool_exchange(
        _assistant_with_tool_calls(("call_a", "evaluate_position"),
                                   ("call_b", "query_opening_book")),
        [
            {"id": "call_a", "tool": "evaluate_position", "content": '{"score": 12}'},
            {"id": "call_b", "tool": "query_opening_book", "content": '{"moves": []}'},
        ],
    )
    msgs = pb.build_messages("sys", user_content="局面")

    assistant = [m for m in msgs if m.get("role") == "assistant"][0]
    tools = [m for m in msgs if m.get("role") == "tool"]

    assert len(tools) == len(assistant["tool_calls"]), "tool 消息数必须等于 tool_calls 数"
    assert [t["tool_call_id"] for t in tools] == [tc["id"] for tc in assistant["tool_calls"]]
    assert msgs[0]["role"] == "system"
    # the user turn precedes the exchange -- it is the turn the exchange belongs to
    assert msgs[1]["role"] == "user"
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "tool", "tool"]
    _assert_no_consecutive_user(msgs)


def test_continuation_does_not_append_user_message():
    """继续生成时不得追加新 user 消息 —— 否则每轮工具调用都产生连续 user。"""
    pb = PromptBuilder("sys")
    pb.add_tool_exchange(
        _assistant_with_tool_calls(("call_a", "t")),
        [{"id": "call_a", "tool": "t", "content": "{}"}],
    )
    msgs = pb.build_messages("sys", user_content=None)

    assert [m["role"] for m in msgs] == ["system", "assistant", "tool"]
    _assert_no_consecutive_user(msgs)


# ------------------------------------------------------------------- R-3

def test_correction_is_merged_into_user_turn_not_appended():
    """纠错反馈并入本轮 user 消息，而不是单独追加一条 user。"""
    pb = PromptBuilder("sys")
    pb.correction = "【系统纠错】未找到合法走步，h2e2 / b0c2"
    msgs = pb.build_messages("sys", user_content="# 当前局面")

    users = [m for m in msgs if m["role"] == "user"]
    assert len(users) == 1, "纠错后应仍只有一条 user 消息"
    assert "系统纠错" in users[0]["content"]
    _assert_no_consecutive_user(msgs)


def test_base_agent_registers_correction_on_the_builder_not_as_history():
    """BaseAgent.add_correction_feedback 必须挂起，不能直接 append user 消息。"""
    from src.agents.llm_agent import LLMAgent
    from src.agents.base_agent import AgentConfig
    from src.llm_adapters.base_adapter import LLMResponse

    class _Adapter:
        model = "fake"
        base_url = "fake"

        async def chat(self, *a, **kw):
            return LLMResponse(content="")

        async def close(self):
            pass

    agent = LLMAgent(AgentConfig(name="a", color="Red", description="",
                                 llm_adapter=_Adapter(), system_prompt="sys"))

    agent.add_correction_feedback( "未找到合法走步", ["h2e2"])

    assert agent.prompt_builder.history == [], "纠错不得进 history"
    assert agent.prompt_builder.correction
    msgs = agent.prompt_builder.build_messages("sys", user_content="局面")
    _assert_no_consecutive_user(msgs)


def test_reset_clears_everything():
    """reset 必须清干净：否则历史跨回合无限累积。"""
    pb = PromptBuilder("sys")
    pb.add_tool_exchange(
        _assistant_with_tool_calls(("call_a", "t")),
        [{"id": "call_a", "tool": "t", "content": "{}"}],
    )
    pb.add_assistant_note("反思")
    pb.correction = "纠错"
    pb.add_to_history("assistant", "历史")

    pb.clear_history()
    msgs = pb.build_messages("sys", user_content="局面")
    assert [m["role"] for m in msgs] == ["system", "user"]
    assert pb.tool_exchanges == [] and pb.assistant_notes == []
    assert pb.correction is None


# ------------------------------------------------- Anthropic 块转换的等价约束

def _to_anthropic(messages):
    """复刻 AnthropicCompatibleAdapter 的转换，验证协议形状。

    直接跑真实适配器需要 anthropic SDK 与网络；这里只验证转换规则。
    """
    out, pending = [], []

    def flush():
        if pending:
            out.append({"role": "user", "content": list(pending)})
            pending.clear()

    # the real adapter extracts system before converting; mirror that
    messages = [m for m in messages if m.get("role") != "system"]
    for msg in messages:
        role = msg.get("role")
        if role == "tool":
            pending.append({"type": "tool_result",
                           "tool_use_id": msg.get("tool_call_id", ""),
                           "content": msg.get("content", "")})
            continue
        flush()
        if role == "assistant" and msg.get("tool_calls"):
            blocks = []
            if msg.get("content"):
                blocks.append({"type": "text", "text": msg["content"]})
            for tc in msg["tool_calls"]:
                fn = tc.get("function", {})
                blocks.append({"type": "tool_use", "id": tc.get("id", ""),
                               "name": fn.get("name", ""), "input": fn.get("arguments", {})})
            out.append({"role": "assistant", "content": blocks})
            continue
        out.append({"role": role, "content": [{"type": "text", "text": msg.get("content", "")}]})
    flush()
    return out


def test_anthropic_parallel_tool_results_merge_into_one_user_message():
    """Anthropic 没有 role:"tool"；并行结果必须合并成一条 user 消息。"""
    pb = PromptBuilder("sys")
    pb.add_tool_exchange(
        _assistant_with_tool_calls(("call_a", "t1"), ("call_b", "t2")),
        [
            {"id": "call_a", "tool": "t1", "content": "{}"},
            {"id": "call_b", "tool": "t2", "content": "{}"},
        ],
    )
    msgs = _to_anthropic(pb.build_messages("sys", user_content="局面"))

    roles = [m["role"] for m in msgs]
    assert roles == ["user", "assistant", "user"], roles

    results = msgs[2]["content"]
    assert len(results) == 2
    assert [r["tool_use_id"] for r in results] == ["call_a", "call_b"]
    assert msgs[1]["content"][0]["type"] == "tool_use"
    _assert_no_consecutive_user(msgs)


def test_anthropic_sequence_never_has_consecutive_user():
    pb = PromptBuilder("sys")
    for i in range(2):
        pb.add_tool_exchange(
            _assistant_with_tool_calls(("call_%d" % i, "t")),
            [{"id": "call_%d" % i, "tool": "t", "content": "{}"}],
        )
    msgs = _to_anthropic(pb.build_messages("sys", user_content="局面"))
    _assert_no_consecutive_user(msgs)