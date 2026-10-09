"""评测 CLI。

    # 跑基线
    python -m tests.eval.run --games 1 --seed 42 --out docs/eval-baseline.json
    # 复验报告自洽性（raw -> summary 是纯函数）
    python -m tests.eval.run --verify docs/eval-baseline.json
    # 只复验冻结局面集
    python -m tests.eval.run --cases-only
    # 复验两家连通性
    python -m tests.eval.run --probe --api-file C:\\path\\to\\TEST_API.txt
"""
import argparse
import math
import asyncio
import json
import subprocess
import sys
from pathlib import Path

from . import cases as cases_mod
from . import providers, report, runner


def _git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=10).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _diff_mode(extra_args) -> bool:
    """是否存在未提交改动——报告必须自述测的是不是脏工作区。"""
    try:
        r = subprocess.run(["git", "status", "--porcelain", "--"] + extra_args,
                           capture_output=True, text=True, timeout=10)
        return bool(r.stdout.strip())
    except Exception:
        return False


# 门禁：这些指标**不允许变差**。方向已在 W-xx 各条的反向守卫里写死。
#
# 四元组：(取值路径, 显示名, 方向, 计数来源)
# 计数来源为 (分子路径列表, 分母路径)。给出后判定会做**两比例 z 检验**：
# 差异在当前样本量下与噪声不可区分时，判「不可判定」而不是「退化」。
# 这解决的是同一个问题第三次触发 —— 低 N 指标上给出过于确定的结论（见 §11.3）。
GATES = [
    ("move_quality.Red.illegal_rate", "非法走步率(红)", "down",
     (["illegal", "parse_failures"], "decisions")),
    ("move_quality.Black.illegal_rate", "非法走步率(黑)", "down",
     (["illegal", "parse_failures"], "decisions")),
    ("move_quality.Red.fallback_rate", "正则兜底率(红)", "down",
     (["fallbacks"], "decisions")),
    ("move_quality.Black.fallback_rate", "正则兜底率(黑)", "down",
     (["fallbacks"], "decisions")),
    ("sides.Red.errors", "调用错误(红)", "down", (["errors"], "llm_calls")),
    ("sides.Black.errors", "调用错误(黑)", "down", (["errors"], "llm_calls")),
    # 方案 B（W-07）：激活一致性必须为 1.0。它不是比率相决，
    # 而是是否是“每一回合的实际激活都等于局面提示的应激活”——
    # 不适用显著性判断：任一回合不匹配就是接线断了。
    ("activation.Red.consistency", "激活一致性(红)", "exact", None),
    ("activation.Black.consistency", "激活一致性(黑)", "exact", None),
]

# 绝对上限门禁（不与基线比，只看是否越界）。
# 用于补上「一致性 1.0 也可能空转」的盲区（W-08）。
CEILINGS = [
    ("activation.Red.empty_rate", "空激活率(红)", 0.05),
    ("activation.Black.empty_rate", "空激活率(黑)", 0.05),
]

# 差异小于该 p 值才算「可判定的变化」；否则一律判「不可判定」
SIGNIFICANCE = 0.05

# 仅记录不设门禁：成本与速度变化是取舍，不是回归
INFO = [
    ("sides.Red.text_only_ratio", "工具调用占比(红)"),
    ("sides.Black.text_only_ratio", "工具调用占比(黑)"),
    ("mean_tokens_per_turn", "每手 token"),
    ("mean_elapsed_sec", "每局秒数"),
    ("mean_ply", "平均 ply"),
]


def _dig(d, path):
    cur = d
    for k in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def _counts(summary, path, spec):
    """取出 (分子, 分母)。

    spec = (分子键列表, 分母键)。计数在**指标的父节点**里：
    路径 `move_quality.Red.fallback_rate` 的计数在 `move_quality.Red` 下，
    叶子本身只是比率，直接去 dig 叶子会拿到 float。
    """
    if not spec:
        return None, None
    nums, denom_key = spec
    parts = path.split(".")
    if len(parts) < 2:
        return None, None
    node = _dig(summary, ".".join(parts[:-1]))
    if not isinstance(node, dict):
        return None, None
    if parts[-1] not in node:
        return None, None          # 指标本身不存在，不能拿父节点的计数充当它
    total = node.get(denom_key)
    if total is None:
        return None, None
    num = sum(int(node.get(k) or 0) for k in nums)
    return num, int(total)


def two_proportion_p(x1, n1, x2, n2):
    """两比例 z 检验的双侧 p 值（合并方差正态近似）。

    样本极小时近似不可靠，此时返回 None，调用方按「无法判定」处理——
    这正是我们要的行为：小样本下宁可说不知道。
    """
    if None in (x1, n1, x2, n2) or n1 <= 0 or n2 <= 0:
        return None
    if min(n1, n2) < 20:
        return None                      # 样本太小，不做判定
    p1, p2 = x1 / n1, x2 / n2
    p = (x1 + x2) / (n1 + n2)
    se = (p * (1 - p) * (1 / n1 + 1 / n2)) ** 0.5
    if se == 0:
        return None
    z = abs(p1 - p2) / se
    return math.erfc(z / math.sqrt(2))


def cmd_compare(baseline_path: str, current, gates_only: bool = False) -> int:
    """把本次结果与基线逐项对比，并按门禁方向判定。

    两条不可退让的原则：
      1. 基线里没有的指标判「无法判定」，绝不显示成「通过」；
      2. 计数类指标先做显著性检验，**差异与噪声不可区分时判「不可判定」**，
         而不是给一个「退化」——低 N 下「退化 1 次 / 分母 122」不是退化。
    """
    base = json.loads(Path(baseline_path).read_text(encoding="utf-8"))["summary"]
    cur = current["summary"]

    print("基线: %s" % baseline_path)
    print("本次: %s  commit=%s  thinking=%s" % (
        current["meta"].get("label", "-"), current["meta"].get("commit"),
        current["meta"].get("thinking")))
    print()
    print("%-20s %-13s %-13s %-9s %-6s %s"
          % ("指标", "基线", "本次", "Δ", "p", "判定"))

    verdicts = []
    inconclusive = []
    # 先审绝对上限：它不依赖基线，也不参与信量性判定
    for path, name, cap in CEILINGS:
        v = _dig(cur, path)
        if v is None:
            print("%-20s %-16s %-16s %-9s %-6s %s"
                  % (name, "-", "-", "-", "≤%.2f" % cap, "无数据"))
            inconclusive.append((name, None, "空激活率未采集"))
            continue
        ok = v <= cap
        print("%-20s %-16s %-16s %-9s %-6s %s"
              % (name, "上限 %.2f" % cap, v, "-", "-",
                 "通过" if ok else "超上限"))
        if not ok:
            verdicts.append((name, False, "%s %s > 上限 %.2f" % (name, v, cap)))

    rows = list(GATES) + ([(p, l, "info", None) for p, l in INFO] if not gates_only else [])
    for row in rows:
        path, name, direction = row[0], row[1], row[2]
        spec = row[3] if len(row) > 3 else None

        if direction == "info":
            b, c = _dig(base, path), _dig(cur, path)
            delta = None if (b is None or c is None) else round(c - b, 3)
            print("%-20s %-13s %-13s %-9s %-6s %s"
                  % (name, b, c, delta, "-", "参考"))
            continue

        b, c = _dig(base, path), _dig(cur, path)
        if b is None or c is None:
            print("%-20s %-13s %-13s %-9s %-6s %s" % (name, b, c, "-", "-", "无法判定"))
            verdicts.append((name, False, "基线或本次缺该指标（多半是基线早于该指标存在）"))
            continue

        bn, bd = _counts(base, path, spec)
        cn, cd = _counts(cur, path, spec)
        bs = "%s [%d/%d]" % (b, bn, bd) if None not in (bn, bd) else str(b)
        cs = "%s [%d/%d]" % (c, cn, cd) if None not in (cn, cd) else str(c)
        counts = "[%d/%d -> %d/%d]" % (bn, bd, cn, cd) if None not in (bn, bd, cn, cd) else ""

        pv = two_proportion_p(bn, bd, cn, cd) if spec else None
        if spec and pv is not None and pv >= SIGNIFICANCE:
            # 差异与噪声不可区分 —— 不给「退化」，也不给「通过」
            print("%-20s %-16s %-16s %-9s %-6s %s"
                  % (name, bs, cs, round(c - b, 4), round(pv, 3), "不可判定"))
            inconclusive.append((name, pv, counts.strip()))
            continue

        delta = round(c - b, 4)
        if direction == "exact":
            ok = (c == 1.0) if c is not None else None
        else:
            ok = c <= b if direction == "down" else c >= b

        # 判定矩阵（别写错：显著退化必须失败，不能因为“有 spec”就放过）
        if ok is None:
            verdict = "不可判定"
            inconclusive.append((name, None, "无数据"))
        elif spec and pv is None:
            verdict = "通过" if ok else "不可判定"
            if not ok:
                inconclusive.append((name, None, counts.strip()))
        else:
            verdict = "通过" if ok else "退化"
            if not ok:
                verdicts.append((name, False, "%s %s -> %s%s"
                                 % (name, bs, cs, counts)))

        print("%-20s %-16s %-16s %-9s %-6s %s"
              % (name, bs, cs, delta,
                 round(pv, 3) if pv is not None else "-", verdict))

    print()
    if inconclusive:
        print("以下指标的差异与噪声无法区分，**未做判定**（不是通过，也不是退化）：")
        for name, p, counts in inconclusive:
            ptxt = "p=%.3f" % p if p is not None else "样本不足"
            print("  - %s：%s %s" % (name, ptxt, counts))
        print()
    if verdicts:
        print("门禁未通过：")
        for name, _, why in verdicts:
            print("  - %s：%s" % (name, why))
        return 1
    print("门禁全部通过（另有上述「不可判定」项需人工确认）")
    return 0


def cmd_verify(path: str) -> int:
    data = Path(path).read_text(encoding="utf-8")
    loaded = json.loads(data)
    canonical = report.dumps(loaded)
    recomputed = report.recompute(loaded)
    ok_serialize = (canonical == data)
    ok_summary = (recomputed == data)

    s = loaded["summary"]
    print("报告 schema :", loaded.get("schema"))
    print("  游戏数     :", s["games"], " 分出胜负:", s["decisive_games"])
    print("  结果分布   :", s["outcome"])
    print("  平均 ply   :", s["mean_ply"])
    print("  纯文本占比 : Red=%s Black=%s" % (
        s["sides"]["Red"]["text_only_ratio"],
        s["sides"]["Black"]["text_only_ratio"]))
    for w in s.get("warnings", []):
        print("  ! " + w)
    print()
    print("[%s] 序列化确定性（文件内容 == 规范化输出）" % ("OK" if ok_serialize else "FAIL"))
    print("[%s] 汇总纯函数性（raw 重算 == 文件内容）" % ("OK" if ok_summary else "FAIL"))

    # 局面集仍然有效吗
    try:
        cases_mod.load()
        print("[OK] 冻结局面集复验通过（%d 个）" % len(cases_mod.load()))
    except AssertionError as e:
        print("[FAIL] 冻结局面集失效:", e)
        return 1

    return 0 if (ok_serialize and ok_summary) else 1


def cmd_probe(api_file: str) -> int:
    keys = providers.load_keys(api_file)
    results = asyncio.run(providers.probe(keys))
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if all(r.get("chat_ok") for r in results) else 1


def cmd_restate(path: str, notes) -> int:
    """从既有 raw 重算报告。不联网、不重跑对局。"""
    src = json.loads(Path(path).read_text(encoding="utf-8"))
    meta = dict(src["meta"])
    # 只记首次重算时的来源 schema。否则第二次 restate 会把它覆盖成当前
    # schema，文件随之改变——restate 就不是幂等的了。
    meta.setdefault("restated_from_schema", src.get("schema", "unknown"))
    if notes:
        meta["notes"] = list(meta.get("notes", [])) + list(notes)
    doc = report.build(src["raw"], meta)
    Path(path).write_text(report.dumps(doc), encoding="utf-8")
    print("已按新格式重算 %s" % path)
    print(json.dumps(doc["summary"]["outcome"], ensure_ascii=False, indent=2))
    for w in doc["summary"]["warnings"]:
        print("  ! " + w)
    return 0


async def cmd_run(args) -> int:
    keys = providers.load_keys(args.api_file)
    all_cases = cases_mod.load()
    if args.only_category:
        all_cases = [c for c in all_cases if c.category in args.only_category]
    ordered = cases_mod.order(all_cases, args.seed)[: args.games or None]

    matchups = [("deepseek", "mimo")]
    if args.both_sides:
        matchups.append(("mimo", "deepseek"))

    # git 状态必须在开跑【之前】采集。若在跑完之后才取，
    # 期间发生的任何提交都会让报告声称自己来自一个它没跑过的 commit。
    git_state = {"commit": _git_commit(),
                 "dirty": _diff_mode(["src", "prompts", "config", "tests/eval"])}

    print("局面 %d 个 / 对阵 %d 组 / 预计 %d 局" % (len(ordered), len(matchups), len(ordered) * len(matchups)))
    if args.thinking is not None:
        print("thinking 覆盖: %s" % ("ON" if args.thinking else "OFF"))
    records = await runner.play_all(
        ordered, matchups, keys,
        max_turns=args.max_turns, temperature=runner.EVAL_TEMPERATURE,
        thinking=args.thinking)

    meta = {
        "commit": git_state["commit"],
        "dirty": git_state["dirty"],
        "seed": args.seed,
        "temperature": runner.EVAL_TEMPERATURE,
        "thinking": providers.THINKING if args.thinking is None else args.thinking,
        "max_turns": args.max_turns,
        "matchups": ["%s vs %s" % m for m in matchups],
        "case_ids": [c.case_id for c in ordered],
        "models": {n: providers.PROVIDERS[n]["model"] for n in providers.PROVIDERS},
        # 记录用的哪套局面集：不记得就无法归因
        "cases_file": cases_mod.describe(args.cases_file),
        "note": "temperature=0 为评测设定，非仓库默认；use_tools 取自 config（当前 false）",
    }
    doc = report.build(records, meta)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report.dumps(doc), encoding="utf-8")
    print("\n-> %s" % out)
    print(json.dumps(doc["summary"], ensure_ascii=False, indent=2))
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tests.eval.run")
    ap.add_argument("--games", type=int, default=1, help="局面数上限")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="docs/eval-baseline.json")
    ap.add_argument("--max-turns", type=int, default=60)
    ap.add_argument("--api-file", default=None,
                    help="含【name】...sk-xxx 的文件；默认只读环境变量")
    ap.add_argument("--only-category", nargs="*", default=None)
    ap.add_argument("--both-sides", action="store_true", help="正反两个方向都跑")
    ap.add_argument("--thinking", type=lambda v: v.lower() in ("1", "true", "on"),
                    default=None, choices=[True, False],
                    help="覆盖 thinking 开关（默认沿用 config）。用于 A/B："
                         "--thinking true / --thinking false")
    ap.add_argument("--compare", metavar="BASELINE", default=None,
                    help="跑局后与基线逐项对比并按门禁方向判定")
    ap.add_argument("--gates-only", action="store_true",
                    help="--compare 时只显示门禁项，不显示成本参考项")
    ap.add_argument("--verify", metavar="PATH", default=None)
    ap.add_argument("--restate", metavar="PATH", default=None,
                    help="用既有 raw 重算报告（不联网、不重跑对局）。"
                         "报告格式演进后用它替代重跑。")
    ap.add_argument("--restate-note", action="append", default=None,
                    help="追加到 meta.notes 的说明，可多次")
    ap.add_argument("--cases-file", default=None,
                    help="局面集文件；默认 cases.json（冻结集）。"
                         "cases_real.json 为真实对局集，"
                         "**对比必须用同一套局面集**")
    ap.add_argument("--cases-only", action="store_true")
    ap.add_argument("--probe", action="store_true")
    args = ap.parse_args(argv)

    try:
        if args.cases_only:
            cs = cases_mod.load(args.cases_file)
            print("[%s] %d 个局面全部复验通过"
                  % (cases_mod.describe(args.cases_file), len(cs)))
            for c in cs:
                print("  %-22s %-14s moves=%-3d" % (c.case_id, c.category, c["legal_moves"]))
            return 0
        if args.verify:
            return cmd_verify(args.verify)
        if args.restate:
            return cmd_restate(args.restate, args.restate_note)
        if args.probe:
            return cmd_probe(args.api_file)
        doc = asyncio.run(cmd_run(args))
        if args.compare:
            doc["meta"]["label"] = args.out
            print()
            print("=" * 70)
            print("\u4e0e\u57fa\u7ebf\u5bf9\u6bd4")
            return cmd_compare(args.compare, doc, gates_only=args.gates_only)
        return 0
    except (providers.KeyConflict, providers.MissingKey) as e:
        # 这些是「配置不对」，不是「程序坏了」——打清晰信息，不抛栈
        print("\n%s\n" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())