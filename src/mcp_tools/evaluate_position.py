"""
局面评估工具

调用Pikafish引擎评估当前局面
"""

from typing import Any, Dict, Optional
import asyncio
import subprocess
from pathlib import Path

from .base_tool import BaseTool, ToolResult
from ..utils.logger import get_logger

logger = get_logger("mcp_tools.evaluate_position")


class EvaluatePositionTool(BaseTool):
    """局面评估工具 - 调用Pikafish引擎"""

    DEFAULT_DEPTH = 15
    DEFAULT_PATH = "engines/pikafish.exe"

    def __init__(
        self,
        name: str = "evaluate_position",
        description: str = "",
        engine_path: Optional[str] = None,
        default_depth: int = DEFAULT_DEPTH,
        threads: int = 1,
    ):
        if not description:
            description = "调用引擎评估当前局面，返回评分和最佳走步推荐"
        super().__init__(name, description)
        self._engine_path = engine_path or self.DEFAULT_PATH
        self._default_depth = default_depth
        self._threads = threads
        self._enabled = True

    def _get_parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "fen": {"type": "string", "description": "当前局面FEN字符串"},
                "depth": {
                    "type": "integer",
                    "description": f"搜索深度(1-20)，默认{self._default_depth}",
                    "default": self._default_depth,
                },
            },
            "required": ["fen"],
        }

    def set_engine_path(self, path: str):
        """设置引擎路径"""
        self._engine_path = path

    def set_enabled(self, enabled: bool):
        """设置是否启用（引擎不可用时禁用）"""
        self._enabled = enabled

    def _check_engine_available(self) -> bool:
        """检查引擎是否可用"""
        engine_path = Path(self._engine_path)
        return engine_path.exists()

    async def execute(self, **kwargs) -> ToolResult:
        """执行局面评估"""
        fen = kwargs.get("fen", "")
        depth = kwargs.get("depth", self._default_depth)

        if not fen:
            return ToolResult(success=False, error="缺少fen参数")

        depth = max(1, min(20, int(depth)))

        if not self._check_engine_available():
            return ToolResult(
                success=True,
                data={
                    "fen": fen,
                    "evaluation": None,
                    "best_move": None,
                    "depth": depth,
                    "available": False,
                    "message": f"引擎不可用，请安装Pikafish到 {self._engine_path}",
                },
            )

        try:
            result = await self._run_engine_analysis(fen, depth)
            return ToolResult(success=True, data=result)
        except Exception as e:
            return ToolResult(success=False, error=f"引擎分析失败: {str(e)}")

    async def _run_engine_analysis(self, fen: str, depth: int) -> Dict[str, Any]:
        """运行引擎分析"""
        engine_path = Path(self._engine_path)

        process = await asyncio.create_subprocess_exec(
            str(engine_path),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        commands = [
            "uci",
            f"setoption name Threads value {self._threads}",
            f"position fen {fen}",
            f"go depth {depth}",
        ]

        stdin_data = "\n".join(commands) + "\nquit\n"
        stdout, stderr = await asyncio.wait_for(
            process.communicate(stdin_data.encode()), timeout=60
        )

        output = stdout.decode("utf-8", errors="ignore")
        stderr_output = stderr.decode("utf-8", errors="ignore")

        if stderr_output.strip():
            logger.debug(f"Engine stderr: {stderr_output[:500]}")

        return self._parse_engine_output(fen, depth, output)

    def _parse_engine_output(self, fen: str, depth: int, output: str) -> Dict[str, Any]:
        """解析引擎输出"""
        result = {
            "fen": fen,
            "depth": depth,
            "evaluation": None,
            "best_move": None,
            "pv": None,
            "available": True,
        }

        lines = output.strip().split("\n")

        for line in reversed(lines):
            if line.startswith("info") and f"depth {depth}" in line:
                score_cp = None
                if "score cp" in line:
                    try:
                        idx = line.index("score cp") + 9
                        parts = line[idx:].split()
                        score_cp = int(parts[0])
                        result["evaluation"] = score_cp / 100.0
                    except (ValueError, IndexError):
                        pass
                elif "score mate" in line:
                    try:
                        idx = line.index("score mate") + 11
                        parts = line[idx:].split()
                        mate_in = int(parts[0])
                        result["evaluation"] = 100.0 if mate_in > 0 else -100.0
                        result["mate_in"] = abs(mate_in)
                    except (ValueError, IndexError):
                        pass

                if " pv " in line:
                    try:
                        idx = line.index(" pv ") + 4
                        pv = line[idx:].split()
                        if pv:
                            result["best_move"] = pv[0]
                            result["pv"] = pv[:5]
                    except (ValueError, IndexError):
                        pass
                break

        for line in reversed(lines):
            if line.startswith("bestmove"):
                parts = line.split()
                if len(parts) >= 2:
                    result["best_move"] = parts[1]
                break

        return result

    def validate_arguments(self, **kwargs) -> Optional[str]:
        """验证参数"""
        if not kwargs.get("fen"):
            return "缺少必需参数: fen"

        depth = kwargs.get("depth", self._default_depth)
        if not isinstance(depth, int) or depth < 1 or depth > 20:
            return "depth必须在1-20之间"

        return None
