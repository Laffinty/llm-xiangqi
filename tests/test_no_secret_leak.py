"""密钥泄露守卫（常驻 CI）。

**为什么需要这个测试**：`.gitignore` 只能防止**未跟踪**文件被 `git add`，
**挡不住**已经被跟踪的文件——一旦 `git add -f` 或 `git add` 发生在规则生效之前，
文件就已在索引里，之后改 `.gitignore` 完全无效。

而且 git 历史里删不掉密钥：补救需要改写整个历史 + 通知所有克隆者。
因此这里做**内容级**扫描，不依赖 `.gitignore`。

三层防护：
  1. `.gitignore` —— 拦住未跟踪文件（防新增）
  2. 本测试 —— 拦住已跟踪文件里的密钥字面量（防漏网）
  3. 人工纪律 —— 密钥不写进任何会被提交的文件
"""
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

# 本项目实际的密钥格式：sk- 后跟长串。DeepSeek / MiMo / OpenAI 等都用这个形态。
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{16,}"),          # sk-xxx（足够长才算，避免误伤短串）
    re.compile(r"AIza[0-9A-Za-z_-]{20,}"),        # Google API key
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),    # GitHub token
]

# 这些目录天然不该出现在 git 里，或其内容已在专项校验下
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "node_modules",
             ".worktree-before", "web_3d_client/node_modules"}

# 允许出现密钥形态字符串的文件：它们自己就在校验密钥，绝不能把样本密钥写进来
ALLOW_SELF = {Path(__file__).resolve()}

SKIP_SUFFIX = {".pyc", ".pyo", ".so", ".png", ".jpg", ".jpeg", ".gif",
               ".ico", ".woff", ".woff2", ".ttf", ".eot", ".map", ".lock"}


def _iter_tracked_text_files():
    """只扫描 **git 已跟踪** 的文本文件——这正是 .gitignore 挡不住的那一层。"""
    try:
        out = subprocess.run(
            ["git", "ls-files"], cwd=str(REPO), capture_output=True,
            text=True, timeout=30, check=True).stdout
    except Exception as exc:  # pragma: no cover
        pytest.skip("git 不可用，跳过：%s" % exc)
    for rel in out.splitlines():
        rel = rel.strip()
        if not rel:
            continue
        p = (REPO / rel).resolve()
        if p in ALLOW_SELF:
            continue
        parts = set(p.relative_to(REPO).parts)
        if parts & SKIP_DIRS:
            continue
        if p.suffix.lower() in SKIP_SUFFIX:
            continue
        if not p.is_file():
            continue
        yield p


def test_no_secret_literal_in_tracked_files():
    """已跟踪文件里不得出现密钥字面量。"""
    hits = []
    for p in _iter_tracked_text_files():
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # 二进制或非 UTF-8，跳过
        for pat in SECRET_PATTERNS:
            for m in pat.finditer(text):
                hits.append((p.relative_to(REPO), m.group(0)[:12] + "…"))
    assert not hits, "已跟踪文件中发现密钥字面量：%s" % hits


def test_gitignore_covers_known_key_files():
    """`.gitignore` 必须覆盖本项目实际使用的密钥文件命名。"""
    for name in ("TEST_API.txt", "api.txt"):
        r = subprocess.run(["git", "check-ignore", "-q", name], cwd=str(REPO))
        assert r.returncode == 0, "%s 未被 .gitignore 覆盖" % name


def test_no_key_file_is_tracked():
    """仓库里不得跟踪任何**密钥载体**文件。

    判定按**扩展名与内容形态**，不按文件名是否含 "api"——
    否则 `docs/api-standard.md`（协议文档）这类正常文件会被误判。
    """
    try:
        out = subprocess.run(
            ["git", "ls-files"], cwd=str(REPO), capture_output=True,
            text=True, timeout=30, check=True).stdout
    except Exception as exc:  # pragma: no cover
        pytest.skip("git 不可用，跳过：%s" % exc)

    # 密钥载体：.pem / .key / .secret / credentials.json / .env*
    carrier_ext = {".pem", ".key", ".secret", ".p12", ".pfx"}
    bad = []
    for rel in out.splitlines():
        rel = rel.strip()
        if not rel:
            continue
        name = Path(rel).name
        lower = name.lower()
        ext = Path(lower).suffix
        if ext in carrier_ext:
            bad.append(rel)
        elif lower in ("credentials.json", ".env", ".secrets"):
            bad.append(rel)
        elif lower.endswith(".env"):
            bad.append(rel)
        elif "secret" in lower and ext in ("", ".txt", ".json", ".yaml", ".yml"):
            bad.append(rel)
    assert not bad, "仓库跟踪了疑似密钥载体：%s" % bad