"""Skill 层验收（W-05 第一步）。

这一项的意义：**在搬 doctrine 之前，先把「激活是否正确」变成可断言的事实。**
否则 `W-05` 第二步做完，只能说「没退化」——那正是 `F-028` 暴露的不可靠判读。
"""
import pytest

from src.core.board_snapshot import build
from src.core.referee_engine import RefereeEngine
from src.skills import router
from src.skills.registry import SkillSpecError, load_skills

# L1 manifest 的 token 预算。Anthropic 的经验值是 ~100 token/skill。
# 这里按更保守的 200 兜底——超了就说明 description 写太长。
L1_TOKEN_BUDGET_PER_SKILL = 200
# L1 总额外开销上限（相对常驻）
L1_TOTAL_TOKEN_BUDGET = 1200


def snap(**kw):
    base = {"board_phase": "middlegame", "in_check": False,
            "repetition_warning": False, "material": {"total": 30}}
    base.update(kw)
    return base


# ------------------------------------------------------------------ 加载

def test_registry_loads_all_skills():
    reg = load_skills()
    assert len(reg) == 5, "应有 5 个 knowledge skill"
    assert all(s.is_knowledge for s in reg.skills.values())


def test_all_rules_are_wellformed():
    assert router.validate_rules(load_skills()) == [], "规则写错必须在启动时暴露"


def test_manifest_order_is_stable():
    """manifest 顺序变化会打掉 prompt 缓存前缀，且让 diff 变脏。"""
    reg = load_skills()
    assert reg.manifest() == sorted(reg.manifest())


# ------------------------------------------------------------------ 激活

def test_phase_skills_are_mutually_exclusive():
    reg = load_skills()
    for phase, expected in [
        ("opening", "opening-development"),
        ("middlegame", "middlegame-tactics"),
        ("endgame", "endgame-technique"),
    ]:
        active = [s.name for s in router.resolve(reg, snap(board_phase=phase))]
        assert active == [expected], "%s 激活了 %s" % (phase, active)


def test_check_defense_activates_regardless_of_phase():
    """被将军时，无论什么阶段都该激活应将知识。"""
    reg = load_skills()
    for phase in ("opening", "middlegame", "endgame"):
        active = [s.name for s in router.resolve(reg, snap(board_phase=phase, in_check=True))]
        assert "check-defense" in active, "%s 阶段被将军未激活 check-defense" % phase


def test_repetition_skill_activates_on_warning_only():
    reg = load_skills()
    assert "repetition-management" in [
        s.name for s in router.resolve(reg, snap(repetition_warning=True))]
    assert "repetition-management" not in [
        s.name for s in router.resolve(reg, snap(repetition_warning=False))]


def test_multiple_skills_can_coexist():
    reg = load_skills()
    active = [s.name for s in router.resolve(
        reg, snap(board_phase="endgame", in_check=True, repetition_warning=True))]
    assert active == ["check-defense", "endgame-technique", "repetition-management"]


def test_routing_is_deterministic():
    reg = load_skills()
    s = snap(board_phase="endgame", in_check=True)
    assert ([x.name for x in router.resolve(reg, s)]
            == [x.name for x in router.resolve(reg, s)])


# ------------------------------------------------------- 规则 DSL 的安全性

def test_dsl_rejects_malformed_rules():
    for bad in [{"field": "x"}, {"nope": 1}, {}, {"all": {}},
                {"field": "x", "op": "exec", "value": 1},
                {"field": 5, "op": "eq"}]:
        with pytest.raises(router.RuleError):
            router.evaluate(bad, snap())


def test_dsl_supports_logic_composition():
    reg = load_skills()
    cond = [{"all": [{"field": "board_phase", "op": "eq", "value": "endgame"},
                     {"not": {"field": "in_check", "op": "eq", "value": True}}]}]
    assert router.evaluate(cond[0], snap(board_phase="endgame"))
    assert not router.evaluate(cond[0], snap(board_phase="endgame", in_check=True))
    assert not router.evaluate(cond[0], snap(board_phase="opening"))


def test_missing_field_yields_none_not_crash():
    assert router.evaluate({"field": "nope.deep", "op": "eq", "value": 1}, snap()) is False


def test_snapshot_drives_the_same_routing_as_tests_expect():
    """用真实引擎快照验证一遍，避免只在手构 dict 上自洽。"""
    reg = load_skills()
    e = RefereeEngine("2b1k4/4a4/b4P3/9/9/9/9/B2K4p/9/5A3 w - - 0 1")
    s = build(e)
    assert s["board_phase"] == "endgame"
    assert [x.name for x in router.resolve(reg, s)] == ["endgame-technique"]


# ------------------------------------------------------------------ 预算

def _approx_tokens(text):
    """粗略 token 估算：CJK 约 1 字/token，ASCII 约 4 字符/token。

    估算而非精确计数——验收要的是「有没有数量级失控」，
    精确 token 只有真发一次请求才知道。
    """
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other = len(text) - cjk
    return int(cjk + other / 4)


def test_l1_manifest_fits_token_budget():
    reg = load_skills()
    text = reg.manifest_text()
    est = _approx_tokens(text)
    assert est <= L1_TOTAL_TOKEN_BUDGET, \
        "L1 manifest 约 %d token，超出 %d 预算；description 写太长" % (est, L1_TOTAL_TOKEN_BUDGET)


def test_each_skill_description_is_concise():
    reg = load_skills()
    for name, spec in sorted(reg.skills.items()):
        est = _approx_tokens(spec.description)
        assert est <= L1_TOKEN_BUDGET_PER_SKILL, "%s 的 description 约 %d token" % (name, est)


# ------------------------------------------------------------------ 内容

def test_bodies_are_migrated():
    """W-05 第二步后，SKILL.md 正文必须是真 doctrine，不能还停在占位符。"""
    reg = load_skills()
    for name, spec in sorted(reg.skills.items()):
        body = spec.path.read_text(encoding="utf-8")
        assert "正文尚未迁移" not in body, "%s 仍是占位正文" % name
        assert len(body) > 200, "%s 正文过短，疑似未真正迁移" % name

def test_migration_is_cheaper_than_always_on_prompt():
    """W-05 的全部价值：拆分后的常驻开销必须低于原全量常驻。

    否则拆分只是形式变化，不是测量改善。
    """
    from pathlib import Path
    from src.skills.activator import compose

    old = Path("prompts/agent_default.txt").read_text(encoding="utf-8")
    worst = None
    for phase in ("opening", "middlegame", "endgame"):
        for check in (False, True):
            for rep in (False, True):
                snap = {"board_phase": phase, "in_check": check,
                       "repetition_warning": rep}
                text, active = compose(snap, player_color="Red")
                if len(text) > len(old):
                    worst = (phase, check, rep, len(text), active)
    assert worst is None, "存在比原全量常驻更贵的组合: %s" % (worst,)


def test_missing_skill_dir_is_not_an_error():
    from pathlib import Path
    assert len(load_skills(Path("does-not-exist"))) == 0


def test_dir_name_must_match_skill_name(tmp_path):
    d = tmp_path / "wrong-name"
    d.mkdir()
    (d / "SKILL.md").write_text(
        "---\nname: actual-name\ndescription: d\nkind: knowledge\n---\nbody\n",
        encoding="utf-8")
    with pytest.raises(SkillSpecError):
        load_skills(tmp_path)
def test_activator_returns_activated_names():
    """组装函数必须回报激活名单，否则 harness 无法断言「激活了什么」。"""
    from src.skills.activator import compose
    text, active = compose(
        {"board_phase": "endgame", "in_check": True, "repetition_warning": False})
    assert active == ["check-defense", "endgame-technique"]
    assert "残局要领" in text, "激活的 skill 正文应出现在 prompt 里"
    assert "开局要领" not in text, "未激活的 skill 正文不应出现"


def test_composed_prompt_has_no_placeholder_leftover():
    from src.skills.activator import compose
    text, _ = compose({"board_phase": "opening"}, player_color="Black")
    assert "{PLAYER_COLOR}" not in text
    assert "Black" in text


def test_prompt_builder_composes_when_enabled():
    """端到端：开关打开时 build_game_prompt 用的是组装后的 prompt。"""
    from src.agents.prompt_builder import PromptBuilder
    from src.core.referee_engine import RefereeEngine
    from src.core.state_serializer import GameState, GamePhase, GameResult

    e = RefereeEngine("2b1k4/4a4/b4P3/9/9/9/9/B2K4p/9/5A3 w - - 0 1")
    d = GameState.from_engine(e, phase=GamePhase.RED_TO_MOVE,
                              result=GameResult.IN_PROGRESS).to_dict()

    on = PromptBuilder("legacy", use_skills=True)
    msg_on = on.build_game_prompt(d, player_color="Red")
    assert on.active_skills == ["endgame-technique"]
    assert "残局要领" in msg_on[0]["content"]

    off = PromptBuilder("legacy", use_skills=False)
    msg_off = off.build_game_prompt(d, player_color="Red")
    assert off.active_skills == []
    assert msg_off[0]["content"] == "legacy"
