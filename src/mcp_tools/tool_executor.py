"""
MCP工具执行器

统一管理和执行各种MCP工具，支持动态加载
"""

from typing import Dict, Any, Callable, Optional, List, Type
import asyncio
import importlib
import importlib.util
import inspect
import threading
from pathlib import Path

from .base_tool import BaseTool, ToolResult
from .opening_book import OpeningBookTool
from .evaluate_position import EvaluatePositionTool
from .validate_move import ValidateMoveTool
from ..utils.logger import get_logger

logger = get_logger("mcp_tools.executor")


class ToolExecutor:
    """MCP工具执行器

    管理并执行各种MCP工具，支持动态加载和发现
    """

    _instance: Optional["ToolExecutor"] = None
    _lock = threading.Lock()

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._tools: Dict[str, BaseTool] = {}
        self._tool_schemas: List[Dict[str, Any]] = []
        self._register_builtin_tools()
        self._auto_discover_tools()

    @classmethod
    def get_instance(cls, config: Optional[Dict[str, Any]] = None) -> "ToolExecutor":
        """获取单例实例（线程安全）"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(config)
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """重置单例（用于测试）"""
        cls._instance = None

    def _register_builtin_tools(self):
        """注册内置工具"""
        pikafish_config = self.config.get("pikafish", {})

        self.register_tool(OpeningBookTool())
        self.register_tool(ValidateMoveTool())
        self.register_tool(
            EvaluatePositionTool(
                engine_path=pikafish_config.get("path", "engines/pikafish.exe"),
                default_depth=pikafish_config.get("depth", 15),
                threads=pikafish_config.get("threads", 1),
            )
        )

    def _auto_discover_tools(self):
        """自动发现外部工具"""
        tools_dir = self.config.get("tools_dir")
        if not tools_dir:
            return

        tools_path = Path(tools_dir)
        if not tools_path.exists():
            return

        for py_file in tools_path.glob("**/*.py"):
            if py_file.name.startswith("_"):
                continue
            self._load_tool_from_file(py_file)

    def _load_tool_from_file(self, file_path: Path):
        """从文件加载工具"""
        try:
            module_name = f"mcp_tools_external.{file_path.stem}"
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if (
                        issubclass(obj, BaseTool)
                        and obj is not BaseTool
                        and not name.startswith("_")
                    ):
                        try:
                            tool_instance = obj()  # type: ignore[call-arg]
                            self.register_tool(tool_instance)
                        except TypeError:
                            logger.warning(
                                f"Cannot instantiate tool {name}: missing required arguments"
                            )
                        except Exception as e:
                            logger.warning(f"Failed to instantiate tool {name}: {e}")
        except Exception as e:
            logger.warning(f"Failed to load tool from {file_path}: {e}")

    def register_tool(self, tool: BaseTool):
        """注册工具实例"""
        self._tools[tool.name] = tool
        self._tool_schemas.append(tool.get_schema())

    def unregister_tool(self, name: str) -> bool:
        """注销工具"""
        if name in self._tools:
            del self._tools[name]
            self._tool_schemas = [
                s
                for s in self._tool_schemas
                if s.get("function", {}).get("name") != name
            ]
            return True
        return False

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """获取工具实例"""
        return self._tools.get(name)

    def get_available_tools(self) -> List[str]:
        """获取可用工具名称列表"""
        return list(self._tools.keys())

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """获取所有工具的JSON Schema（供LLM调用）"""
        return self._tool_schemas

    async def execute(
        self, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """执行工具

        Args:
            tool_name: 工具名称
            arguments: 工具参数

        Returns:
            工具执行结果字典
        """
        tool = self._tools.get(tool_name)
        if not tool:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}

        if not tool.enabled:
            return {"success": False, "error": f"Tool {tool_name} is disabled"}

        validation_error = tool.validate_arguments(**arguments)
        if validation_error:
            return {"success": False, "error": validation_error}

        try:
            result = await tool.execute(**arguments)
            return result.to_dict()
        except Exception as e:
            return {"success": False, "error": str(e)}

    def set_tool_enabled(self, name: str, enabled: bool) -> bool:
        """设置工具启用状态"""
        tool = self._tools.get(name)
        if tool:
            tool.set_enabled(enabled)
            return True
        return False

    def reload_tools(self, config: Optional[Dict[str, Any]] = None):
        """重新加载所有工具"""
        if config:
            self.config = config
        self._tools.clear()
        self._tool_schemas.clear()
        self._register_builtin_tools()
        self._auto_discover_tools()
