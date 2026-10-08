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


def cmd_verify(path: str) -> int:
    data = Path(path).read_text(encoding="utf-8")
    loaded = json.loads(data)
    canonical = report.dumps(loaded)
    recomputed = report.recompute(loaded)
    ok_serialize = (canonical == data)
    ok_summary = (recomputed == data)

    print("报告 schema :", loaded.get("schema"))
    print("  游戏数     :", loaded["summary"]["games"], " 中止:", loaded["summary"]["aborted"])
    print("  红方视角   :", loaded["summary"]["red_view"])
    print("  平均 ply   :", loaded["summary"]["mean_ply"])
    print("  纯文本占比 : Red=%s Black=%s" % (
        loaded["summary"]["sides"]["Red"]["text_only_ratio"],
        loaded["summary"]["sides"]["Black"]["text_only_ratio"]))
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


async def cmd_run(args) -> int:
    keys = providers.load_keys(args.api_file)
    all_cases = cases_mod.load()
    if args.only_category:
        all_cases = [c for c in all_cases if c.category in args.only_category]
    ordered = cases_mod.order(all_cases, args.seed)[: args.games or None]

    matchups = [("deepseek", "mimo")]
    if args.both_sides:
        matchups.append(("mimo", "deepseek"))

    print("局面 %d 个 / 对阵 %d 组 / 预计 %d 局" % (len(ordered), len(matchups), len(ordered) * len(matchups)))
    records = await runner.play_all(
        ordered, matchups, keys,
        max_turns=args.max_turns, temperature=runner.EVAL_TEMPERATURE)

    meta = {
        "commit": _git_commit(),
        "dirty": _diff_mode(["src", "prompts", "config", "tests/eval"]),
        "seed": args.seed,
        "temperature": runner.EVAL_TEMPERATURE,
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
    return 0


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
    ap.add_argument("--verify", metavar="PATH", default=None)
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
        if args.probe:
            return cmd_probe(args.api_file)
        return asyncio.run(cmd_run(args))
    except (providers.KeyConflict, providers.MissingKey) as e:
        # 这些是「配置不对」，不是「程序坏了」——打清晰信息，不抛栈
        print("\n%s\n" % e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())