"""决策契约（`W-03`）。

把「合法走法」写成 JSON Schema 的 `enum`，让模型**物理上无法输出非法走步**，
从而消灭一整类「答案格式不可解析」的失败（见 `PLAN-SKILL-001` 的 `F-020` / `F-023`）。

三条供应商硬约束（实测，见 `F-012` / `F-013` / `F-014`）：
  C-1 `strict` 必须放在**函数定义内**，不能放 `response_format`（DeepSeek 返回 400）
  C-2 不得使用 `tool_choice: "required"`（DeepSeek 返回 400）
  C-3 降级路径必须存在且可单独评测

**它不是棋盘能力**：board_inspect 之类是「查询」，move_decision 是「答案出口」。
两者混在一个注册表里会让人误以为它可以被模型自由调用，故独立于 `src/mcp_tools/`。
"""

from typing import Any, Dict, List, Optional

DECISION_TOOL_NAME = "move_decision"

# 走法条数上限。legal_moves 用 enum 全量写入 schema；开局 44 种走法时
# schema 仍然很小，但极端局面（残局 40+）时需要防止 prompt 膨胀。
MAX_ENUM_MOVES = 120

SCHEMA_TEMPLATE = {
    "type": "function",
    "function": {
        "name": DECISION_TOOL_NAME,
        "strict": True,
        "description": (
            "输出你对当前局面的走步决策。move 必须是给定合法走步之一，不得自行编造。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "move": {"type": "string", "enum": []},
                "thought": {
                    "type": "string",
                    "description": "局面评估→对手意图→战略目标→选点理由",
                },
                "confidence": {
                    "type": "number",
                    "description": "0~1，对本步走法的把握程度",
                },
            },
            "required": ["move", "thought", "confidence"],
            "additionalProperties": False,
        },
    },
}


def build_tool(legal_moves: List[str]) -> Optional[Dict[str, Any]]:
    """构造决策工具定义。legal_moves 为空时返回 None（无路可走，交给引擎判定）。"""
    if not legal_moves:
        return None
    moves = list(dict.fromkeys(m.lower() for m in legal_moves))
    truncated = len(moves) > MAX_ENUM_MOVES
    if truncated:
        # 不静默截断：截掉一部分就等于把那些走法变成"非法"，与契约的承诺相反。
        raise ValueError(
            "legal_moves 数量 %d 超过 MAX_ENUM_MOVES=%d；"
            "此时必须退回降级路径，不能截断 enum" % (len(moves), MAX_ENUM_MOVES)
        )
    tool = {k: (dict(v) if isinstance(v, dict) else v)
            for k, v in SCHEMA_TEMPLATE.items()}
    fn = dict(tool["function"])
    fn["parameters"] = {k: (dict(v) if isinstance(v, dict) else v)
                        for k, v in SCHEMA_TEMPLATE["function"]["parameters"].items()}
    fn["parameters"]["properties"]["move"] = {"type": "string", "enum": moves}
    tool["function"] = fn
    return tool


def parse(response: Any, legal_moves: List[str]) -> Optional[Dict[str, Any]]:
    """从响应中取 move_decision 的调用结果。

    返回 {"move", "thought", "confidence", "source": "contract"} 或 None。
    任何一步不满足契约（没调用、参数缺字段、move 不在 enum 内）都返回 None，
    由调用方走降级路径 —— **不做修补**，修补等于把契约失败伪装成成功。
    """
    tool_calls = getattr(response, "tool_calls", None)
    if not tool_calls:
        return None
    legal = {m.lower() for m in legal_moves}

    for call in tool_calls:
        if call.get("name") != DECISION_TOOL_NAME:
            continue
        args = call.get("arguments") or {}
        if not isinstance(args, dict):
            return None
        move = args.get("move")
        if not isinstance(move, str):
            return None
        move = move.strip().lower()
        if move not in legal:              # enum 已被服务端强制，这里是双重保险
            return None
        thought = args.get("thought")
        conf = args.get("confidence")
        try:
            conf = float(conf) if conf is not None else None
        except (TypeError, ValueError):
            conf = None
        return {
            "move": move,
            "thought": thought if isinstance(thought, str) else None,
            "confidence": conf,
            "source": "contract",
        }
    return None


def validate_free_text(move: Optional[str], legal_moves: List[str]) -> Optional[str]:
    """降级路径用：校验模型自由文本里抽出来的走步是否合法。

    返回 None 表示合法，否则返回可操作的错误说明（`D-05` 要求错误必须可操作）。
    """
    if not move:
        return "未能从回答中提取到走步。必须给出形如 h2e2 的 4 字符 ICCS 坐标。"
    m = move.strip().lower()
    if len(m) != 4 or not m[0].isalpha() or not m[2].isalpha() \
            or not m[1].isdigit() or not m[3].isdigit():
        return "走步 '%s' 不是 4 字符 ICCS 坐标（字母+数字+字母+数字，如 h2e2）。" % move
    if m not in {x.lower() for x in legal_moves}:
        return "走步 '%s' 不在当前合法走步列表中（共 %d 种）。" % (move, len(legal_moves))
    return None