"""Skill 注册表（W-05 第一步）。

只负责 **L1 元数据**：每个 skill 的 `name` / `description` / `when`。
L1 常驻 system prompt，成本约 ~100 token/项。

**刻意不做的事**：这里不读 SKILL.md 正文。正文（L2）只在被激活时才载入，
由 `PromptBuilder` 按需拼接——渐进披露的 L1/L2 分界（见 `PLAN-SKILL-001` §4.1）。

frontmatter 用 `yaml.safe_load` 解析，不使用 `eval`/自定义 tag——
`when` 条件将在 `router.py` 里用受限 DSL 求值，不执行任意表达式。
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"

REQUIRED_FIELDS = ("name", "description", "kind")


class SkillSpecError(ValueError):
    """skill 定义不合规。**启动时即失败**，不等到对局中途。"""


@dataclass
class SkillSpec:
    name: str
    description: str
    kind: str                       # knowledge | action
    when: Optional[List[Dict[str, Any]]] = None
    path: Optional[Path] = None
    # 供 W-06 填 action 类技能的 schema；knowledge 类为 None
    schema: Optional[Dict[str, Any]] = None

    @property
    def is_knowledge(self) -> bool:
        return self.kind == "knowledge"

    def manifest_line(self) -> str:
        """L1 的一行摘要，进 system prompt。"""
        return "- %s: %s" % (self.name, self.description)


@dataclass
class SkillRegistry:
    skills: Dict[str, SkillSpec] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.skills)

    def get(self, name: str) -> Optional[SkillSpec]:
        return self.skills.get(name)

    def manifest(self) -> List[str]:
        """全部 L1 元数据，顺序稳定（按 name 排序，便于 diff 与缓存命中）。"""
        return [self.skills[k].manifest_line() for k in sorted(self.skills)]

    def manifest_text(self) -> str:
        return "\n".join(self.manifest())


def _parse_skill_file(path: Path) -> SkillSpec:
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---"):
        raise SkillSpecError("%s: 缺少 YAML frontmatter" % path.name)
    parts = raw.split("---", 2)
    if len(parts) < 3:
        raise SkillSpecError("%s: frontmatter 未闭合" % path.name)

    meta = yaml.safe_load(parts[1]) or {}
    if not isinstance(meta, dict):
        raise SkillSpecError("%s: frontmatter 必须是映射" % path.name)

    missing = [f for f in REQUIRED_FIELDS if not meta.get(f)]
    if missing:
        raise SkillSpecError("%s: 缺少必填字段 %s" % (path.name, missing))

    kind = meta.get("kind")
    if kind not in ("knowledge", "action"):
        raise SkillSpecError("%s: kind 必须是 knowledge 或 action，收到 %r" % (path.name, kind))

    name = str(meta["name"])
    if path.parent.name != name:
        raise SkillSpecError(
            "%s: 目录名 %r 与 name %r 不一致（同名是规范要求）" % (path.name, path.parent.name, name))

    return SkillSpec(
        name=name,
        description=str(meta["description"]),
        kind=kind,
        when=meta.get("when"),
        path=path,
        schema=meta.get("schema"),
    )


def load_skills(skills_dir: Optional[Path] = None) -> SkillRegistry:
    """扫描目录加载全部 SKILL.md。无 skill 时返回空注册表（不是错误）。"""
    root = Path(skills_dir) if skills_dir else SKILLS_DIR
    registry = SkillRegistry()
    if not root.exists():
        return registry

    for path in sorted(root.glob("*/SKILL.md")):
        spec = _parse_skill_file(path)
        if spec.name in registry.skills:
            raise SkillSpecError("重复的 skill 名: %s" % spec.name)
        registry.skills[spec.name] = spec
    return registry
