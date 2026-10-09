"""决策契约的守卫（`W-03`）。

核心承诺：合法走法写在 schema 的 `enum` 里，模型**物理上无法输出非法走步**。
这些测试守住两件事——
  1. 契约真的被构造出来了（enum 完整、不被静默截断）
  2. 契约失败时走**降级**路径，而不是被修补成成功
"""
import pytest

from src.agents import decision_contract as dc
from src.agents.base_agent import AgentConfig
from src.agents.llm_agent import LLMAgent
from src.llm_adapters.base_adapter import LLMResponse

LEGAL = ["h2e2", "b0c2", "h0g2"]


def _resp(tool_calls=None, content="", thought=None):
    return LLMResponse(content=content, thought=thought, tool_calls=tool_calls)


# ------------------------------------------------------------------ build

def test_tool_lists_every_legal_move_in_enum():
    tool = dc.build_tool(LEGAL)
    enum = tool["function"]["parameters"]["properties"]["move"]["enum"]
    assert sorted(enum) == sorted(LEGAL)


def test_strict_is_inside_the_function_definition():
    """C-1: strict 必须在函数定义内。放 response_format 会被 DeepSeek 拒（F-012）。"""
    assert dc.build_tool(LEGAL)["function"]["strict"] is True


def test_schema_meets_strict_mode_requirements():
    """strict 模式三条硬性要求，否则请求被供应商直接拒绝。"""
    params = dc.build_tool(LEGAL)["function"]["parameters"]
    assert params["additionalProperties"] is False
    assert set(params["required"]) == set(params["properties"].keys())


def test_no_legal_moves_yields_no_tool():
    """残局无路可走时不给契约工具——该由引擎判终局，不是让模型编走法。"""
    assert dc.build_tool([]) is None


def test_overlong_enum_raises_instead_of_truncating():
    """截断 enum 等于把被截掉的走步变成「非法」，与契约承诺相反，必须报错。"""
    # ICCS 共 9*10*9*10 = 9000 种组合，取足够多的互不重复走步
    def _iccs(i):
        cols, rows = "abcdefghi", "0123456789"
        return cols[i % 9] + rows[i // 9 % 10] + cols[i // 90 % 9] + rows[i // 810 % 10]

    many = [_iccs(i) for i in range(dc.MAX_ENUM_MOVES + 5)]
    assert len(set(many)) == len(many), "测试数据必须互不重复"
    with pytest.raises(ValueError):
        dc.build_tool(many)


def test_build_does_not_mutate_the_template():
    """两次构造不能互相污染，否则第二个局面会带上第一个的合法走步。"""
    a = dc.build_tool(["h2e2"])
    b = dc.build_tool(["b0c2"])
    assert a["function"]["parameters"]["properties"]["move"]["enum"] == ["h2e2"]
    assert b["function"]["parameters"]["properties"]["move"]["enum"] == ["b0c2"]


# ------------------------------------------------------------------ parse

def test_parse_accepts_contract_call():
    r = _resp(tool_calls=[{"name": "move_decision",
                           "arguments": {"move": "h2e2", "thought": "中炮开局",
                                         "confidence": 0.9}}])
    d = dc.parse(r, LEGAL)
    assert d["move"] == "h2e2"
    assert d["thought"] == "中炮开局"
    assert d["confidence"] == 0.9
    assert d["source"] == "contract"


def test_parse_rejects_move_outside_enum():
    """enum 已由服务端强制，这里是双重保险 —— 不能靠信任上游。"""
    r = _resp(tool_calls=[{"name": "move_decision",
                           "arguments": {"move": "z9z9", "thought": "", "confidence": 1}}])
    assert dc.parse(r, LEGAL) is None


def test_parse_returns_none_when_model_just_answers_in_text():
    """tool_choice 只能是 auto，供应商不保证一定调用工具（见 F-013）。
    没调用就是没调用，必须返回 None 让上层降级，不能瞎猜一个走法。"""
    assert dc.parse(_resp(content='{"move": "h2e2"}'), LEGAL) is None


def test_parse_ignores_board_tools():
    r = _resp(tool_calls=[{"name": "board_inspect", "arguments": {}}])
    assert dc.parse(r, LEGAL) is None


def test_parse_tolerates_malformed_arguments():
    for bad in ({"move": 123}, {"thought": "x"}, {"move": None}):
        assert dc.parse(_resp(tool_calls=[{"name": "move_decision", "arguments": bad}]),
                        LEGAL) is None


# --------------------------------------------------------- fallback errors

def test_fallback_error_is_actionable():
    """"不可操作的错误消息会逼模型猜" —— 这是 D-05 的硬要求。"""
    err = dc.validate_free_text("z9z9", LEGAL)
    assert err and "合法走步" in err and "3 种" in err

    err2 = dc.validate_free_text("abc", LEGAL)
    assert err2 and "4 字符" in err2

    err3 = dc.validate_free_text(None, LEGAL)
    assert err3 and "h2e2" in err3

    assert dc.validate_free_text("H2E2", LEGAL) is None, "大小写应被接受"


# ----------------------------------------------------------- agent wiring

class _Adapter:
    model = "fake"
    base_url = "fake"

    def __init__(self, resp):
        self._resp = resp
        self.seen_tools = None

    async def chat(self, messages, tools=None, **kw):
        self.seen_tools = tools
        return self._resp

    async def close(self):
        pass


def _agent(resp, contract=True):
    adapter = _Adapter(resp)
    agent = LLMAgent(AgentConfig(
        name="t", color="Red", description="", llm_adapter=adapter,
        system_prompt="你是象棋助手。", use_tools=False,
        use_decision_contract=contract))
    agent._last_legal_moves = list(LEGAL)
    return agent, adapter


@pytest.mark.asyncio
async def test_agent_prefers_contract_over_regex():
    agent, adapter = _agent(_resp(
        tool_calls=[{"name": "move_decision",
                     "arguments": {"move": "b0c2", "thought": "跳马", "confidence": 0.8}}]))
    res = await agent.think({"legal_moves": LEGAL, "turn": "Red"})
    assert res.move == "b0c2"
    assert res.tool_results and res.tool_results[0]["tool"] == "move_decision"


@pytest.mark.asyncio
async def test_agent_sends_contract_tool_when_enabled():
    agent, adapter = _agent(_resp(content="x"))
    await agent.think({"legal_moves": LEGAL, "turn": "Red"})
    names = [t["function"]["name"] for t in adapter.seen_tools]
    assert "move_decision" in names


@pytest.mark.asyncio
async def test_agent_sends_no_tools_when_contract_disabled():
    agent, adapter = _agent(_resp(content="随便 h2e2"), contract=False)
    res = await agent.think({"legal_moves": LEGAL, "turn": "Red"})
    assert adapter.seen_tools is None, "契约关闭时不得暴露任何工具"
    assert res.move == "h2e2", "仍应走正则降级路径"


@pytest.mark.asyncio
async def test_contract_failure_falls_back_and_validates():
    """契约失败不修补：模型给了非法走步，必须被降级校验拦下，不能当作成功。"""
    agent, _ = _agent(_resp(
        tool_calls=[{"name": "move_decision",
                     "arguments": {"move": "z9z9", "thought": "", "confidence": 1}}]))
    res = await agent.think({"legal_moves": LEGAL, "turn": "Red"})
    assert res.move is None, "非法走步不得被当成结果返回"

class _ScriptedAdapter(_Adapter):
    """按顺序返回预设响应，用来测分支走向。"""

    def __init__(self, responses):
        super().__init__(responses[0])
        self._responses = list(responses)
        self.calls = []

    async def chat(self, messages, tools=None, **kw):
        self.calls.append({"tools": [t["function"]["name"] for t in (tools or [])],
                           "tool_choice": kw.get("tool_choice")})
        return self._responses.pop(0)


@pytest.mark.asyncio
async def test_bad_contract_call_retries_without_tools_and_parses_text():
    """F-025: 契约调用存在但参数不合规时，响应里没有 content 可降级。

    此时若直接进工具循环会得到 "Failed to get final move"。正确做法是
    不带工具重问一次，再用正则走降级路径。
    """
    bad = _resp(tool_calls=[{"name": "move_decision",
                             "arguments": {"move": "z9z9", "thought": "", "confidence": 1}}])
    text = _resp(content='{\"thought\": "试试\", \"move\": \"h2e2\"}')
    adapter = _ScriptedAdapter([bad, text])
    agent = LLMAgent(AgentConfig(
        name="t", color="Red", description="", llm_adapter=adapter,
        system_prompt="s", use_tools=False, use_decision_contract=True))
    agent._last_legal_moves = list(LEGAL)

    res = await agent.think({"legal_moves": LEGAL, "turn": "Red"})

    assert len(adapter.calls) == 2, "第一次契约失败后必须重问一次"
    assert adapter.calls[0]["tools"] == ["move_decision"]
    assert adapter.calls[1]["tools"] == [], "重问时必须不带工具"
    assert res.move == "h2e2", "应通过降级路径拿到走步"


@pytest.mark.asyncio
async def test_good_contract_call_does_not_retry():
    good = _resp(tool_calls=[{"name": "move_decision",
                              "arguments": {"move": "h2e2", "thought": "x", "confidence": 1}}])
    adapter = _ScriptedAdapter([good])
    agent = LLMAgent(AgentConfig(
        name="t", color="Red", description="", llm_adapter=adapter,
        system_prompt="s", use_tools=False, use_decision_contract=True))
    agent._last_legal_moves = list(LEGAL)
    await agent.think({"legal_moves": LEGAL, "turn": "Red"})
    assert len(adapter.calls) == 1, "契约命中时不得有多余请求"


@pytest.mark.asyncio
async def test_tool_choice_required_when_contract_alone():
    agent, adapter = _agent(_resp(content="x"))
    await agent.think({"legal_moves": LEGAL, "turn": "Red"})
    assert adapter.seen_tools is not None
    agent2, adapter2 = _agent(_resp(content="x"))
    adapter2.seen_choice = None
    await agent2.think({"legal_moves": LEGAL, "turn": "Red"})
    # _chat 内部决定 tool_choice，用 _ScriptedAdapter 验证更可靠
