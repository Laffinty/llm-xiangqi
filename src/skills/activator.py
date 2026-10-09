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


def compose(snapshot: Optional[Dict[str, Any]],
            player_color: Optional[str] = None) -> Tuple[str, List[str]]:
    """组装 (system_prompt, 激活的 skill 名)。

    返回激活名单是为了让 harness 能断言「激活了什么」，而不必反解字符串。
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
    return prompt, [s.name for s in active]
