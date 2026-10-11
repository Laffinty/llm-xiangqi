"""Skill 激活与 system prompt 组装（W-05 第二步）。

**渐进披露在这里落地**：
  L0 `prompts/base.md`      恒真事实（角色 / 坐标系 / 标注 / 禁止事项 / 思考框架）
  L1 skill frontmatter      常驻 manifest，一行一个
  L2 SKILL.md 正文          仅激活的 skill 载入
  L3 references/*.md        仅被 skill 正文显式引用时载入（本步不自动拼接）

组装顺序固定，保证 prompt 前缀稳定——前缀一变，prompt 缓存全失效。
"""
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .registry import SkillRegistry, load_skills
from .router import resolve

BASE_PROMPT = Path(__file__).resolve().parents[2] / "prompts" / "base.md"

_REGISTRY: Optional[SkillRegistry] = None


def registry(reload: bool = False) -> SkillRegistry:
    global _REGISTRY
    if _REGISTRY is None or reload:
        _REGISTRY = load_skills()
    return _REGISTRY


def skill_body(spec) -> str:
    """取 SKILL.md 的 frontmatter 之后正文。"""
    raw = spec.path.read_text(encoding="utf-8")
    parts = raw.split("---", 2)
    return parts[2].strip() if len(parts) >= 3 else ""


def base_prompt() -> str:
    if not BASE_PROMPT.exists():
        raise FileNotFoundError("缺少基础提示层: %s" % BASE_PROMPT)
    return BASE_PROMPT.read_text(encoding="utf-8").strip()


# 未指定棋风时的回退文案：保持「模型自选」这一旧行为，
# 而不是硬塞一种棋风——那会破坏未配置 play_style 的现有部署。
_STYLE_FALLBACK = (
    "自选一种并锁定：**进攻型**（激烈搏杀，善用弃子攻杀）／**稳健型**（子力协调，"
    "稳步推进）／**灵活型**（随机应变，善出奇招）／**防守反击型**（稳固阵型，诱敌深入）。"
)


def _style_text(play_style: Optional[str]) -> str:
    """把 config 的棋风 key 渲染成注入 base.md 的文本。

    **刻意不从 config_loader 导入 PLAY_STYLES**：activator 属于 skills 层，
    反向依赖 utils.config_loader 会形成层间循环。此处只做 key→文本映射，
    两处的 key 集合由 `tests/test_spectacle_content.py` 的守卫测试锁定一致。
    """
    table = {
        "aggressive": "进攻型：激烈搏杀，善用弃子攻杀，敢于冒险，主动制造接触。",
        "solid": "稳健型：注重子力协调，稳步推进，积小胜为大胜，不轻易弃子。",
        "flexible": "灵活型：随机应变，善出奇招，不拘泥于固定套路。",
        "counter": "防守反击型：先稳固阵型，诱敌深入，再伺机反扑。",
    }
    if play_style and play_style in table:
        return table[play_style]
    return _STYLE_FALLBACK


def compose(snapshot: Optional[Dict[str, Any]],
            player_color: Optional[str] = None,
            play_style: Optional[str] = None) -> Tuple[str, List[str]]:
    """组装 (system_prompt, 激活的 skill 名)。

    返回激活名单是为了让 harness 能断言「激活了什么」，而不必反解字符串。

    `play_style`（`P-04`）：config 指定的棋风。**必须在 prompt 组装之后、
    base.md 内容之前替换 `{PLAY_STYLE}`**——替换发生在组装之后，两个 agent
    才能拿到不同的棋风；若写在 base.md 里，两边会读到同一段文字而同质化
    （`T-03` 的根因）。
    未指定时替换为「自选一种」，保持旧行为不变。
    """
    reg = registry()
    if not len(reg):
        return base_prompt(), []

    active = resolve(reg, snapshot)
    parts = [base_prompt(), "## 可用知识（按局面自动选择）", reg.manifest_text()]
    for spec in active:
        parts.append("\n---\n\n%s" % skill_body(spec))

    prompt = "\n\n".join(parts)
    if player_color:
        prompt = prompt.replace("{PLAYER_COLOR}", player_color)
    prompt = prompt.replace("{PLAY_STYLE}", _style_text(play_style))
    return prompt, [s.name for s in active]
