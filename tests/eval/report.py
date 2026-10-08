"""报告聚合与确定性序列化。

硬性要求：**summary 必须是 raw 的纯函数**。
`--verify` 会用同一份 raw 重算 summary 并逐字节比对，
因此聚合层的确定性是可证明的，而不是口头保证。
"""
import json
from typing import Dict, List


def _round(x, nd=2):
    return round(float(x), nd) if x is not None else None


def _mean(vals: List[float]):
    vals = [v for v in vals if v is not None]
    return _round(sum(vals) / len(vals)) if vals else None


def summarize(records: List[Dict]) -> Dict:
    """从原始记录计算汇总。纯函数：同样的 raw 必得同样的 summary。"""
    played = [r for r in records if not r.get("aborted")]
    aborted = [r for r in records if r.get("aborted")]

    red_view = {"red_win": 0, "draw": 0, "black_win": 0, "unknown": 0}
    for r in played:
        res = r.get("result")
        if res == "red_win":
            red_view["red_win"] += 1
        elif res == "draw":
            red_view["draw"] += 1
        elif res == "black_win":
            red_view["black_win"] += 1
        else:
            red_view["unknown"] += 1

    def side_totals(side: str) -> Dict:
        calls = sum(r["stats"][side]["llm_calls"] for r in records)
        tool = sum(r["stats"][side]["tool_call_turns"] for r in records)
        content = sum(r["stats"][side]["content_only_turns"] for r in records)
        return {
            "llm_calls": calls,
            "tool_call_turns": tool,
            "content_only_turns": content,
            # 纯文本回合占比 = 正则兜底路径占比 = 非法走步的先行指标
            "text_only_ratio": _round(content / calls) if calls else None,
            "prompt_tokens": sum(r["stats"][side]["prompt_tokens"] for r in records),
            "completion_tokens": sum(r["stats"][side]["completion_tokens"] for r in records),
            "errors": sum(r["stats"][side]["errors"] for r in records),
        }

    by_category: Dict[str, Dict] = {}
    for cat in sorted({r["category"] for r in records}):
        sub = [r for r in records if r["category"] == cat]
        by_category[cat] = {
            "games": len(sub),
            "aborted": len([r for r in sub if r.get("aborted")]),
            "mean_ply": _mean([r["turn_count"] for r in sub]),
            "red_win": len([r for r in sub if r.get("result") == "red_win"]),
            "draw": len([r for r in sub if r.get("result") == "draw"]),
            "black_win": len([r for r in sub if r.get("result") == "black_win"]),
        }

    return {
        "games": len(records),
        "aborted": len(aborted),
        "red_view": red_view,
        "mean_ply": _mean([r["turn_count"] for r in records]),
        "mean_elapsed_sec": _mean([r["elapsed_sec"] for r in records]),
        "mean_tokens_per_turn": _round(
            (sum(r["stats"][s]["total_tokens"] for r in records for s in ("Red", "Black"))
             / max(1, sum(r["turn_count"] for r in records))), 1),
        "sides": {"Red": side_totals("Red"), "Black": side_totals("Black")},
        "by_category": by_category,
    }


def build(records: List[Dict], meta: Dict) -> Dict:
    """组装完整报告。meta 记录测的是什么——基线必须自述。"""
    return {
        "schema": "llm-xiangqi/eval-report@1",
        "meta": meta,
        "summary": summarize(records),
        "raw": records,
    }


def dumps(report: Dict) -> str:
    """确定性序列化：键排序、UTF-8 原样、末尾换行。"""
    return json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def recompute(report: Dict) -> str:
    """只用 raw 重算整份报告——用于 --verify。"""
    return dumps(build(report["raw"], report["meta"]))