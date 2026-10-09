# -*- coding: utf-8 -*-
"""Report layer: distinguish real draws from turn-cap truncations, and let the
report state its own limits instead of leaving them for the reader to infer."""
from pathlib import Path
import json
from typing import Dict, List

# game_controller.GameEndReasons
CAP_REASONS = ("Maximum turns reached", "Stalemate", "�϶�Ŀ���")


def _round(x, nd=2):
    return round(float(x), nd) if x is not None else None


def _mean(vals: List[float]):
    vals = [v for v in vals if v is not None]
    return _round(sum(vals) / len(vals)) if vals else None


def classify(record: Dict) -> str:
    """把一局归类。cap = 被回合上限截断，不是真结果。"""
    res = record.get("result")
    reason = record.get("result_reason") or ""
    if record.get("aborted"):
        return "aborted"
    if res == "red_win":
        return "red_win"
    if res == "black_win":
        return "black_win"
    if res == "draw":
        if any(cap in reason for cap in CAP_REASONS):
            return "draw_by_cap"
        return "draw_natural"
    return "unknown"


def _move_quality(records: List[Dict], side: str) -> Dict:
    """汇总走步质量。

    旧报告（schema@2 首版）没有 move_quality 字段，返回 None 值而非 0，
    以免把「没测过」显示成「测出来是 0」。
    """
    present = [r for r in records if r.get("move_quality", {}).get(side)]
    if not present:
        return {"decisions": None, "illegal": None, "parse_failures": None,
                "illegal_rate": None, "measured": False}
    legal = sum(r["move_quality"][side]["legal"] for r in present)
    illegal = sum(r["move_quality"][side]["illegal"] for r in present)
    fails = sum(r["move_quality"][side]["parse_failures"] for r in present)
    total = legal + illegal + fails
    out = {
        "decisions": total,
        "legal": legal,
        "illegal": illegal,
        "parse_failures": fails,
        "illegal_rate": round((illegal + fails) / total, 4) if total else None,
        "measured": True,
    }
    if any("fallback_rate" in r["move_quality"][side] for r in present):
        fb = sum(r["move_quality"][side].get("fallbacks", 0) for r in present)
        hits = sum(r["move_quality"][side].get("contract_hits", 0) for r in present)
        out["fallbacks"] = fb
        out["contract_hits"] = hits
        out["fallback_rate"] = round(fb / total, 4) if total else None
    else:
        out["fallbacks"] = None
        out["contract_hits"] = None
        out["fallback_rate"] = None
    return out


def summarize(records: List[Dict]) -> Dict:
    """从原始记录计算汇总。纯函数：同样的 raw 必得同样的 summary。"""
    kinds = [classify(r) for r in records]
    counts = {k: kinds.count(k) for k in
              ("red_win", "black_win", "draw_natural", "draw_by_cap", "aborted", "unknown")}

    def side_totals(side: str) -> Dict:
        calls = sum(r["stats"][side]["llm_calls"] for r in records)
        content = sum(r["stats"][side]["content_only_turns"] for r in records)
        return {
            "llm_calls": calls,
            "content_only_turns": content,
            # 纯文本回合占比 = 正则兜底路径占比 = 非法走步的先行指标
            "text_only_ratio": _round(content / calls) if calls else None,
            "prompt_tokens": sum(r["stats"][side]["prompt_tokens"] for r in records),
            "completion_tokens": sum(r["stats"][side]["completion_tokens"] for r in records),
            "errors": sum(r["stats"][side]["errors"] for r in records),
        }

    by_category: Dict[str, Dict] = {}
    for cat in sorted({r["category"] for r in records}):
        sub = [r for r, k in zip(records, kinds) if r["category"] == cat]
        sub_k = [k for r, k in zip(records, kinds) if r["category"] == cat]
        by_category[cat] = {
            "games": len(sub),
            "red_win": sub_k.count("red_win"),
            "black_win": sub_k.count("black_win"),
            "draw_natural": sub_k.count("draw_natural"),
            "draw_by_cap": sub_k.count("draw_by_cap"),
            "aborted": sub_k.count("aborted"),
            "mean_ply": _mean([r["turn_count"] for r in sub]),
        }

    summary = {
        "games": len(records),
        "outcome": counts,
        "decisive_games": counts["red_win"] + counts["black_win"],
        "mean_ply": _mean([r["turn_count"] for r in records]),
        "mean_elapsed_sec": _mean([r["elapsed_sec"] for r in records]),
        "mean_tokens_per_turn": _round(
            (sum(r["stats"][s]["total_tokens"] for r in records for s in ("Red", "Black"))
             / max(1, sum(r["turn_count"] for r in records))), 1),
        "sides": {"Red": side_totals("Red"), "Black": side_totals("Black")},
        "move_quality": {"Red": _move_quality(records, "Red"),
                         "Black": _move_quality(records, "Black")},
        "by_category": by_category,
        "result_reasons": sorted({r.get("result_reason") or "" for r in records}),
    }
    summary["warnings"] = _warnings(summary)
    return summary


def _warnings(s: Dict) -> List[str]:
    """报告必须自己说清它测不出什么，而不是让读的人脑补。"""
    w = []
    if s["games"] and s["decisive_games"] == 0:
        w.append("本批无胜负局：胜负指标不可观测，不能据此比较棋力。"
                 "可用指标为 token 成本 / 耗时 / 走步合法率 / text_only_ratio。")
    if s["outcome"]["draw_by_cap"]:
        w.append("%d 局被回合上限截断，属未完成对局，不计入和棋判断。"
                 % s["outcome"]["draw_by_cap"])
    if s["sides"]["Red"]["text_only_ratio"] == 1.0 and s["sides"]["Black"]["text_only_ratio"] == 1.0:
        w.append("双方 text_only_ratio 均为 1.0：从未发生工具调用。注意该指标测的是"
                 "**传输方式**而非**决策路径**——W-03 之后 response_format 通道"
                 "同样不产生 tool_calls，判断走没走正则请看 move_quality.*.fallback_rate。")
    fb = [s["move_quality"][x].get("fallback_rate") for x in ("Red", "Black")]
    if all(v is not None for v in fb):
        w.append("决策来源：红方兜底率 %s、黑方兜底率 %s（0 = 全部走契约）。"
                 % (fb[0], fb[1]))
    if not s["move_quality"]["Red"]["measured"]:
        w.append("本批未采集 move_quality（非法走步率）：该指标在这份报告采集时尚不存在，"
                 "不能与后续报告比较，需重新采集基线。")
    return w


def build(records: List[Dict], meta: Dict) -> Dict:
    """组装完整报告。meta 记录测的是什么——基线必须自述。

    caveats 按插入顺序追加并去重（保序，不排序）——
    排序会让 --restate 与 --verify 走出不同结果，那正是确定性守卫要抓的。
    """
    meta = dict(meta)
    caveats = list(meta.get("caveats", []))
    summary = summarize(records)
    for w in summary["warnings"]:
        if w not in caveats:
            caveats.append(w)
    meta["caveats"] = caveats
    return {"schema": "llm-xiangqi/eval-report@2", "meta": meta,
            "summary": summary, "raw": records}


def dumps(report: Dict) -> str:
    """确定性序列化：键排序、UTF-8 原样、末尾换行。"""
    return json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def recompute(report: Dict) -> str:
    """只用 raw 重算整份报告——用于 --verify。"""
    return dumps(build(report["raw"], report["meta"]))