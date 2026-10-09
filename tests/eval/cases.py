"""冻结局面集加载与校验。

cases.json 中的每个 FEN 都由真实引擎走子生成（见文件内 _note），
本模块在加载时会用 RefereeEngine 复验一遍，确保集子不会悄悄腐化。
"""
import json
from pathlib import Path
from typing import List, Dict

from src.core.referee_engine import RefereeEngine

CASES_PATH = Path(__file__).parent / "cases.json"

# GameController 硬编码 phase=RED_TO_MOVE，因此只取红方走棋的局面。
# 这是仓库既有行为（见 history/optimization-plan.md P1-6），本 harness 不依赖也不修复它。
RED_TO_MOVE = "red"


class Case(dict):
    """id / category / fen / legal_moves / note"""

    @property
    def case_id(self) -> str:
        return self["id"]

    @property
    def category(self) -> str:
        return self["category"]

    @property
    def fen(self) -> str:
        return self["fen"]


def validate(cases: List[Dict]) -> None:
    """用真实引擎复验全部局面。任何一条不成立即抛错。"""
    seen = set()
    for c in cases:
        assert c["id"] not in seen, "duplicate case id: %s" % c["id"]
        seen.add(c["id"])
        engine = RefereeEngine(c["fen"])
        legal = engine.get_legal_moves()
        assert legal, "%s: 无合法走法" % c["id"]
        assert len(legal) == c["legal_moves"], (
            "%s: legal_moves 漂移 %d -> %d" % (c["id"], c["legal_moves"], len(legal))
        )
        assert engine.get_current_turn().lower().startswith("r"), (
            "%s: 非红方走棋局面，与 GameController 的硬编码 phase 冲突" % c["id"]
        )


REAL_PATH = Path(__file__).parent / "cases_real.json"


def describe(path: Path = None) -> str:
    """报告里要记下用的是哪套局面集——不记就无法归因。"""
    p = Path(path) if path else CASES_PATH
    return p.name if p.exists() else str(p)


def load(path: Path = None) -> List[Case]:
    path = Path(path) if path else CASES_PATH
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = [Case(c) for c in data["cases"]]
    validate(cases)
    return cases


def order(cases: List[Case], seed: int) -> List[Case]:
    """按 seed 派生一个确定性排列。不用 random 模块，保证跨版本可复现。"""
    return sorted(cases, key=lambda c: (hash_str("%d:%s" % (seed, c.case_id)), c.case_id))


def hash_str(s: str) -> int:
    """稳定的字符串散列（hash() 带随机化，不可用）。"""
    h = 2166136261
    for ch in s.encode("utf-8"):
        h = ((h ^ ch) * 16777619) & 0xFFFFFFFF
    return h