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
GATES = [
    ("move_quality.Red.illegal_rate", "非法走步率(红)", "down"),
    ("move_quality.Black.illegal_rate", "非法走步率(黑)", "down"),
    ("sides.Red.text_only_ratio", "正则兜底占比(红)", "down"),
    ("sides.Black.text_only_ratio", "正则兜底占比(黑)", "down"),
    ("sides.Red.errors", "调用错误(红)", "down"),
    ("sides.Black.errors", "调用错误(黑)", "down"),
]
# 仅记录不设门禁：成本与速度变化是取舍，不是回归
INFO = [
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


def cmd_compare(baseline_path: str, current, gates_only: bool = False) -> int:
    """把本次结果与基线逐项对比，并按门禁方向判定通过与否。

    基线里没有的指标一律显示 n/a 并判为「无法判定」——
    把「没测过」显示成「通过」是这份工具最不该犯的错。
    """
    base = json.loads(Path(baseline_path).read_text(encoding="utf-8"))["summary"]
    cur = current["summary"]

    print("基线: %s" % baseline_path)
    print("本次: %s  commit=%s  thinking=%s" % (
        current["meta"].get("label", "-"), current["meta"].get("commit"),
        current["meta"].get("thinking")))
    print()
    print("%-22s %-10s %-10s %-10s %s" % ("指标", "基线", "本次", "Δ", "判定"))

    verdicts = []
    rows = GATES + ([("__info__", n, "info") for n in INFO] if not gates_only else [])
    for path, name, direction in rows:
        if direction == "info":
            b, c = _dig(base, path), _dig(cur, path)
            delta = None if (b is None or c is None) else round(c - b, 3)
            print("%-22s %-10s %-10s %-10s %s" % (
                name, b, c, delta, "参考"))
            continue
        b, c = _dig(base, path), _dig(cur, path)
        if b is None or c is None:
            print("%-22s %-10s %-10s %-10s %s" % (name, b, c, "-", "无法判定"))
            verdicts.append((name, False, "基线或本次缺该指标（多半是基线早于该指标存在）"))
            continue
        delta = round(c - b, 4)
        ok = c <= b if direction == "down" else c >= b
        print("%-22s %-10s %-10s %-10s %s" % (name, b, c, delta, "通过" if ok else "退化"))
        if not ok:
            verdicts.append((name, False, "%s %s -> %s" % (name, b, c)))

    print()
    if verdicts:
        print("门禁未通过：")
        for name, _, why in verdicts:
            print("  - %s：%s" % (name, why))
        return 1
    print("门禁全部通过（或对基线缺失的指标判为无法判定时需人工确认）")
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
    ap.add_argument("--cases-only", action="store_true")
    ap.add_argument("--probe", action="store_true")
    args = ap.parse_args(argv)

    try:
        if args.cases_only:
            cs = cases_mod.load()
            print("%d 个局面全部复验通过" % len(cs))
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