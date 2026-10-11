"""RK-06 守卫：渐进披露不得引入额外 LLM 往返。

**依据**（`docs/open-questions.md` RK-06，2026-11-11 实测）：

判据是 `llm_calls / decisions`。渐进披露若真产生「读 skill → 用 skill」两轮调用，
该比值必然 > 1.0。实测三份报告：

| 报告 | mean |
|---|---|
| `eval-baseline.json` | 1.00 |
| `eval-attack-baseline.json` | 1.01 |
| `eval-attack-before.json`（改造前） | 1.02 |

注意**改造前同样是 1.02**——那点超出来自 `max_retries` 重试，
与渐进披露无关，因此判为「已消解」。

**本测试的作用**：防止将来重构（新增一次摘要、二次校验、分步工具调用等）
悄悄引入往返——那会让 token 成本无声翻倍，而胜负指标看不出来。
"""
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

# 允许的上限：1.0 + 重试余量。实测最大值 1.05（来自 max_retries=3 的重试）。
MAX_CALLS_PER_DECISION = 1.1

REPORTS = [
    "docs/eval-baseline.json",
    "docs/eval-attack-baseline.json",
    "docs/eval-attack-before.json",
]


def _iter_reports():
    for rel in REPORTS:
        p = REPO / rel
        if p.exists():
            yield rel, json.loads(p.read_text(encoding="utf-8"))


def _ratios(doc):
    out = []
    for g in doc.get("raw", []):
        stats = g.get("stats", {})
        quality = g.get("move_quality", {})
        for side in ("Red", "Black"):
            calls = (stats.get(side) or {}).get("llm_calls")
            decisions = (quality.get(side) or {}).get("decisions")
            if calls and decisions:
                out.append((g.get("case_id"), side, calls / decisions))
    return out


def test_no_extra_llm_roundtrip():
    """每决策的 LLM 调用次数不得超过 1.1。"""
    offenders = []
    checked = 0
    for rel, doc in _iter_reports():
        for case_id, side, ratio in _ratios(doc):
            checked += 1
            if ratio > MAX_CALLS_PER_DECISION:
                offenders.append((rel, case_id, side, round(ratio, 3)))
    if checked == 0:
        pytest.skip("无可用评测报告")
    assert not offenders, (
        "检测到额外 LLM 往返（渐进披露回归）：%s" % offenders)


def test_baseline_is_exactly_one_call_per_decision():
    """改造前基线应**恰好** 1.00——它是判据的锚点。

    若这条也开始漂移，说明报告统计口径变了，RK-06 的结论需要重做。
    """
    p = REPO / REPORTS[0]
    if not p.exists():
        pytest.skip("基线报告不存在")
    ratios = _ratios(json.loads(p.read_text(encoding="utf-8")))
    if not ratios:
        pytest.skip("基线报告无 stats 字段")
    assert all(abs(r - 1.0) < 1e-9 for _, _, r in ratios), \
        "基线的 llm_calls/decisions 偏离 1.00：%s" % [
            (c, s, round(r, 3)) for c, s, r in ratios if abs(r - 1.0) >= 1e-9]