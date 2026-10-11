"""`P-04` 守卫：棋风硬绑定 —— 红黑必须拿到**不同**棋风。

**为什么这是硬需求**：两个 agent 读到**同一段**棋风文字时，可能选到同一种
取向，棋就变成「各走各的、无人施压」（`T-03` 的失效模式）。
把棋风放在 **config 层**（由部署方指定）而非 skill 正文（模型自选），
是消除该盲区的唯一手段。

对应 §7 盲区 1：`style_drift_count` 只能测「个体是否摇摆」，
**测不出「双方是否同质」** —— 本文件补的正是那一层。
"""
from pathlib import Path

import pytest

from src.skills.activator import _STYLE_FALLBACK, _style_text, compose

REPO = Path(__file__).resolve().parents[1]

SNAP = {
    "board_phase": "opening",
    "in_check": False,
    "repetition_warning": False,
    "material": {"total": 32},
}


def _style_of(prompt: str) -> str:
    """从组装结果里提取注入的棋风文本行。"""
    for line in prompt.splitlines():
        if line.startswith("**你的棋风："):
            return line.strip("*：").strip("*")
    return ""


class TestPlaceholderAlwaysReplaced:
    def test_no_placeholder_leaks_for_any_style(self):
        for style in (None, "aggressive", "solid", "flexible", "counter"):
            prompt, _ = compose(dict(SNAP), "Red", style)
            assert "{PLAY_STYLE}" not in prompt, \
                "棋风 %r 时占位符泄漏到最终 prompt" % style

    def test_unknown_style_falls_back(self):
        """未知 key 不应让 {PLAY_STYLE} 原样透出——静默降级到「自选」。"""
        assert _style_text("nonsense") == _STYLE_FALLBACK

    def test_fallback_mentions_all_four(self):
        for name in ("进攻型", "稳健型", "灵活型", "防守反击型"):
            assert name in _STYLE_FALLBACK, "回退文案缺 %s" % name


class TestRedBlackDiffer:
    """核心承诺：红黑拿到不同棋风。"""

    def test_styles_differ_in_prompt(self):
        red, _ = compose(dict(SNAP), "Red", "aggressive")
        blk, _ = compose(dict(SNAP), "Black", "counter")
        assert _style_of(red) != _style_of(blk), \
            "红黑棋风相同 —— `T-03` 的失效模式会重现"

    def test_real_configs_are_configured_differently(self):
        """仓库里的两份配置必须真的配了不同棋风。

        这条比单元测试更重要：配置写错（比如两边都抄成 aggressive）
        单元测试照样通过，但部署后就同质化了。
        """
        import yaml
        styles = {}
        for name in ("agent1_config.yaml", "agent2_config.yaml"):
            data = yaml.safe_load((REPO / "config" / name).read_text(encoding="utf-8"))
            styles[name] = data.get("agent", {}).get("play_style")
        assert all(styles.values()), "两份配置都必须显式指定 play_style：%s" % styles
        assert len(set(styles.values())) == 2, \
            "红黑 play_style 相同（%s），`T-03` 风险仍在" % styles

    def test_config_values_are_valid_keys(self):
        from src.utils.config_loader import PLAY_STYLES
        import yaml
        for name in ("agent1_config.yaml", "agent2_config.yaml"):
            data = yaml.safe_load((REPO / "config" / name).read_text(encoding="utf-8"))
            style = data.get("agent", {}).get("play_style")
            assert style in PLAY_STYLES, "%s: 非法棋风 %r" % (name, style)


class TestStyleTableConsistency:
    """`activator._style_text` 与 `config_loader.PLAY_STYLES` 必须一致。

    两者**故意不共用常量**（activator 不能反向依赖 utils.config_loader，
    会形成层间循环），代价是可能漂移——本测试就是防漂移的。
    """

    def test_same_key_set(self):
        from src.utils.config_loader import PLAY_STYLES
        table_keys = set(_all_style_keys())
        assert table_keys == set(PLAY_STYLES), \
            "两处棋风 key 集合不一致：%s vs %s" % (table_keys, set(PLAY_STYLES))

    def test_same_text_per_key(self):
        from src.utils.config_loader import PLAY_STYLES
        for key in PLAY_STYLES:
            assert _style_text(key) == PLAY_STYLES[key], \
                "key %r 的文案两处不一致：%r vs %r" % (
                    key, _style_text(key), PLAY_STYLES[key])


def _all_style_keys():
    """从 activator 源码里取出 _style_text 的 key 集合。"""
    import inspect
    from src.skills import activator
    src = inspect.getsource(activator._style_text)
    start = src.index("table = {")
    end = src.index("}", start)
    body = src[start + len("table = {"):end]
    return [seg.split(":")[0].strip().strip('"')
            for seg in body.split(",") if seg.strip()]


class TestBackwardCompatibility:
    def test_none_style_keeps_old_behavior(self):
        """未配置 play_style 时必须回退到「自选」，而不是硬塞一种。"""
        prompt, _ = compose(dict(SNAP), "Red", None)
        assert _STYLE_FALLBACK[:6] in prompt

    def test_compose_signature_backward_compatible(self):
        """两参调用必须仍可用——eval harness 里有大量 compose(snap, color)。"""
        import inspect
        params = inspect.signature(compose).parameters
        assert list(params)[:2] == ["snapshot", "player_color"]
        assert params["play_style"].default is None