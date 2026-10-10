"""P-03 的内容完整性守卫（`PLAN-SPECTACLE-001` §4）

**为什么需要这一份测试**：`PLAN-SPECTACLE-001` `S-03` 规定
「每条 doctrine 必须自带可数指标，否则不得写入」。

这条纪律的反面是：**已写入的条文可能被后来的重构静默删掉**——
SKILL.md 是纯文本，没有类型、没有断言，删掉一整段也不会有任何测试变红。
本文件把「长打规则」和「别把棋下闷」两条**钉成会红的断言**。

对应 `PLAN-SPECTACLE-001` §3.4 的实测证据：
`eval-after-w05/w05b` 出现 27~28 手**零吃子、零将军**的来回搬运，
`long_chase_turns` 从 0 升到 34/37。
"""
from pathlib import Path

import pytest

SKILLS = Path(__file__).resolve().parents[1] / "skills"


def body(name: str) -> str:
    """取 SKILL.md 的正文（frontmatter 之后）。"""
    raw = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
    parts = raw.split("---", 2)
    assert len(parts) >= 3, "%s 缺 frontmatter" % name
    return parts[2]


class TestRepetitionSkillContent:
    """`repetition-management` 必含的条文。"""

    @pytest.mark.parametrize("keyword,why", [
        ("闷摆", "实测头号观赏性杀手是闷摆，不是规则意义上的长打"),
        ("制造接触", "必须给出可执行的破局动作"),
        ("吃子", "循环首着若为吃子应予扣除——脱困的关键细则"),
        ("棋盘", "重复按棋盘判定，与谁走无关"),
    ])
    def test_contains(self, keyword, why):
        assert keyword in body("repetition-management"), \
            "repetition-management 丢失了「%s」——%s" % (keyword, why)

    def test_has_actionable_churn_breakaway(self):
        """必须给出**可执行的破局动作**，而不是只说「别闷」。

        对应 `S-03`：不可执行的条文等于散文。
        """
        text = body("repetition-management")
        for verb in ("制造接触", "兑子提速", "主动弃子"):
            assert verb in text, "缺少破局动作「%s」" % verb

    def test_does_not_say_may_lose(self):
        """回归守卫：不得把「单方长将立即判负」弱化成「可能判负」。

        旧文案写的是「连续将军在象棋中**可能**判负」——这会让模型
        以为长将至多和棋，因而放心走下去。
        """
        text = body("repetition-management") + body("check-defense")
        assert "可能判负" not in text, \
            "「可能判负」是弱化表述，会让模型误以为长将只是和棋手段"


class TestCheckDefenseSkillContent:
    def test_states_long_check_loses_immediately(self):
        assert "单方长将立即判负" in body("check-defense")

    def test_lists_allowed_moves_for_draw(self):
        assert "兑、献、拦、跟" in body("check-defense")

    def test_marks_prohibited_move_kinds(self):
        assert "禁止着法" in body("check-defense"), \
            "长杀/长捉属禁止着法——缺少它，模型仍可能用长捉换和棋"


class TestNoDuplicateRuleBlocks:
    """回归守卫：同一条长打规则不应在三处重复写。

    预算超标的根因是规则条款在 `base.md` / `check-defense` /
    `repetition-management` 里各写一遍。删重复不等于删信息——
    因此本测试锁定「规则正文只在 `check-defense`」这条分工。
    """

    def test_rule_body_lives_only_in_check_defense(self):
        rep = body("repetition-management")
        # repetition-management 允许以「见 check-defense」指引，但不得**成段复述**规则。
        # 断言按「禁止着法」整条是否成段出现来判定，而不是靠零散词元——
        # 指引句里出现「立即判负」是必要的交叉引用，不算复述。
        assert "禁止着法" not in rep, \
            "禁止着法条款应在 check-defense 单点维护，不要重复"
        assert "兑、献、拦、跟" not in rep, \
            "允许着法条款应在 check-defense 单点维护，不要重复"
        assert "check-defense" in rep, \
            "移走条款后必须留下指引，否则信息真的丢了"


class TestGameNarrativeActivation:
    """`game-narrative` 只在开局激活——这是预算约束下的刻意选择，需守住。"""

    def test_only_activates_in_opening(self):
        from src.skills import router
        from src.skills.registry import load_skills
        reg = load_skills()
        for phase in ("opening", "middlegame", "endgame"):
            active = [s.name for s in router.resolve(
                reg, {"board_phase": phase, "in_check": False,
                      "repetition_warning": False})]
            if phase == "opening":
                assert "game-narrative" in active
            else:
                assert "game-narrative" not in active, (
                    "%s 不该激活 game-narrative：常驻会给每个组合加约 460 字符"
                    % phase)

    def test_base_prompt_does_not_dangle_reference(self):
        """`base.md` 不得引用未激活时就不存在的 skill 名。

        回归：`game-narrative` 曾从常驻改为仅开局激活，而 base.md 仍指向它——
        中局/残局的 prompt 里就出现了指向不存在章节的指引。
        """
        from pathlib import Path
        from src.skills.activator import compose
        base = Path("prompts/base.md").read_text(encoding="utf-8")
        for phase in ("middlegame", "endgame"):
            text, active = compose(
                {"board_phase": phase, "in_check": False,
                 "repetition_warning": False}, player_color="Red")
            body = text.split("## 可用知识（按局面自动选择）", 1)[-1]
            for ref in ("game-narrative",):
                assert ref not in base or ref in active, (
                    "base.md 引用 %s，但 %s 阶段不激活它" % (ref, phase))
            assert "tempo-drama" not in body and "sac-culture" not in body, (
                "正文引用了已合并删除的 skill")


class TestMiddlegameContent:
    """合并后的中局 skill 必须同时保住「节奏」与「弃子」两块内容。

    合并是为省预算，但**不能丢 doctrine**——本测试守住这一点：
    合并时最容易发生的静默事故，是「以为另一份会覆盖」而实际删掉了内容。
    """

    @pytest.mark.parametrize("keyword,why", [
        ("闷摆", "实测头号观赏性杀手"),
        ("战术密度", "节奏判据必须可量化，否则退化为玄学"),
        ("0.30~0.34", "实测分布区间，给模型可参照的目标带"),
        ("弃子", "观赏性的主要来源"),
        ("须成立", "弃子三判据之一——防无脑送子"),
        ("须有选择", "弃子三判据之一——被迫弃子不算"),
    ])
    def test_contains(self, keyword, why):
        assert keyword in body("middlegame-tactics"), \
            "合并后丢失了「%s」——%s" % (keyword, why)

    def test_keeps_both_references(self):
        import os
        refs = os.listdir(os.path.join(
            str(SKILLS / "middlegame-tactics"), "references"))
        assert "move-values.md" in refs
        assert "sac-motifs.md" in refs, "弃子图式 references 应随合并一并保留"


class TestSpectacleMetricsRemainReachable:
    """`S-03` 的另一半：新写的条文必须真的对应 §3.1 的指标。

    若日后把 `long_chase_turns` 从指标表删掉，本测试转红——
    防止指标与 doctrine 单方面脱钩。
    """

    def test_churn_text_maps_to_long_chase_turns(self):
        from tests.eval.spectacle import SPECTACLE_GATES
        paths = [g[0] for g in SPECTACLE_GATES]
        assert "summary.total_long_chase_turns" in paths, \
            "长打指标被删除，但 SKILL 仍在教这件事——口径已脱钩"

    def test_repetition_skill_still_activates_on_warning(self):
        """内容大改后，激活条件不得被顺手改掉（`F-030` 激活一致性 1.0 是已验证成果）。"""
        from src.skills.registry import load_skills
        from src.skills import router
        spec = load_skills().get("repetition-management")
        assert spec is not None
        assert router.matches(spec, {"repetition_warning": True})
        assert not router.matches(spec, {"repetition_warning": False})