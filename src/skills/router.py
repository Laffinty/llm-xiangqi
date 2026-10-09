"""Skill 路由（W-05 第一步）。

**路由是确定性的，不由模型自选**（`PLAN-SKILL-001` 裁决 `D-03`）：
引擎已经知道阶段、子力、是否被将军、是否接近重复——让模型自己挑 skill
等于花钱花延迟去重新推导引擎已知的事实。

`when` 用受限 DSL 表达，**不是表达式语言**：

```yaml
when:
  all:
    - field: board_phase
      op: eq
      value: endgame
```

只支持 `all` / `any` / `not` 与 `eq` / `ne` / `in` / `gt` / `gte` / `lt` / `lte` / `truthy`。
不执行任意表达式：写错只会**不匹配**，不会变成可执行代码。
"""
from typing import Any, Dict, List, Optional

from .registry import SkillRegistry, SkillSpec

OPS = {
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "in": lambda a, b: isinstance(b, (list, tuple, set)) and a in b,
    "gt": lambda a, b: a is not None and b is not None and a > b,
    "gte": lambda a, b: a is not None and b is not None and a >= b,
    "lt": lambda a, b: a is not None and b is not None and a < b,
    "lte": lambda a, b: a is not None and b is not None and a <= b,
    "truthy": lambda a, b: bool(a),
}

AND, OR, NOT, FIELD, OP, VALUE = "all", "any", "not", "field", "op", "value"


class RuleError(ValueError):
    """when 规则写错了。这是**配置错误**，应当在启动时暴露。"""


def evaluate(cond: Any, snapshot: Optional[Dict[str, Any]]) -> bool:
    """求值单条规则。`snapshot=None` 时只允许 `truthy`，其余一律 False。

    接受三种写法：
      {field: f, op: o, value: v}    单个谓词
      {all: [...]} / {any: [...]}    逻辑组合
      {not: {...}}                   取反
    """
    if not isinstance(cond, dict) or not cond:
        raise RuleError("规则必须是非空映射，收到 %r" % (cond,))

    if FIELD in cond and OP in cond:
        op = cond[OP]
        if op not in OPS:
            raise RuleError("未知操作符 %r，可选：%s" % (op, sorted(OPS)))
        path = cond.get(FIELD)
        if not isinstance(path, str) or not path:
            raise RuleError("field 必须是非空字符串")
        return bool(OPS[op](_lookup(snapshot, path), cond.get(VALUE)))

    if len(cond) != 1:
        raise RuleError("规则必须含 field+op，或只含 all/any/not 之一，收到 %r" % (cond,))
    (key, arg), = cond.items()

    if key in (AND, OR):
        if not isinstance(arg, list):
            raise RuleError("%s 的参数必须是列表" % key)
        results = (evaluate(c, snapshot) for c in arg)
        return all(results) if key == AND else any(results)

    if key == NOT:
        return not evaluate(arg, snapshot)

    raise RuleError("未知规则键: %r" % key)


def _lookup(snapshot: Optional[Dict[str, Any]], path: str) -> Any:
    """点号路径取值，如 `material.total`。缺路径返回 None 而不是 KeyError。"""
    cur: Any = snapshot or {}
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def matches(spec: SkillSpec, snapshot: Optional[Dict[str, Any]]) -> bool:
    """无 when 条件视为**始终激活**（常驻型技能）。"""
    if not spec.when:
        return True
    return all(evaluate(c, snapshot) for c in spec.when)


def resolve(registry: SkillRegistry,
            snapshot: Optional[Dict[str, Any]]) -> List[SkillSpec]:
    """确定本回合激活哪些 knowledge skill。返回顺序稳定（按 name）。"""
    active = [s for s in registry.skills.values()
              if s.is_knowledge and matches(s, snapshot)]
    return sorted(active, key=lambda s: s.name)


def validate_rules(registry: SkillRegistry) -> List[str]:
    """用空快照试跑全部规则，把写错的挑出来。启动时调用。"""
    problems = []
    for name, spec in sorted(registry.skills.items()):
        for cond in (spec.when or []):
            try:
                evaluate(cond, None)
            except RuleError as e:
                problems.append("%s: %s" % (name, e))
    return problems
