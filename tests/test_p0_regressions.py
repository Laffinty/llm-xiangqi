"""
P0 级缺陷回归测试

对应 docs/optimization-plan.md 中的 P0-1 ~ P0-5。
每条测试都锁定一个曾经"声明存在但实际失效"的行为，
防止后续重构把这些坑重新挖开。
"""

import subprocess
import sys

import pytest

from src.core.game_controller import GameController
from src.core.referee_engine import INITIAL_FEN, PieceType, RefereeEngine
from src.core.state_serializer import GamePhase, GameResult, GameState


# ---------------------------------------------------------------------------
# P0-1  game.py 顶层导入 GUI 导致整个应用无法启动
# ---------------------------------------------------------------------------

class TestP0_1_LazyGuiImport:
    """原生 3D GUI 是可选展示层，不应是应用硬依赖。"""

    def test_import_game_succeeds_without_touching_gui(self):
        """import game 不应连带导入 pyglet（GUI 仅在实际启用时才需要）"""
        code = (
            "import sys, game;"
            "assert 'pyglet' not in sys.modules, 'pyglet was imported eagerly';"
            "print('ok')"
        )
        r = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert r.returncode == 0, f"import game 失败: {r.stderr}"
        assert "ok" in r.stdout

    def test_gui_package_import_does_not_require_pyglet(self):
        """import src.gui 不应因缺少 pyglet 而炸掉"""
        code = (
            "import sys, src.gui;"
            "assert 'pyglet' not in sys.modules, 'pyglet was imported eagerly';"
            "print('ok')"
        )
        r = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert r.returncode == 0, f"import src.gui 失败: {r.stderr}"

    def test_gui_lazy_export_raises_for_unknown_attribute(self):
        import src.gui as gui_pkg

        with pytest.raises(AttributeError):
            _ = gui_pkg.NoSuchExport


# ---------------------------------------------------------------------------
# P0-2  GameState 的 phase / result / last_move 恒为缺省
# ---------------------------------------------------------------------------

class TestP0_2_GameStatePassthrough:
    """LLM 必须能看到当前阶段与上一步，否则 prompt 里的「对手意图推测」无据可依。"""

    def test_initial_state_carries_real_phase(self):
        controller = GameController(referee_engine=RefereeEngine())
        state = controller.get_current_state()
        assert state.phase == GamePhase.RED_TO_MOVE
        assert state.result == GameResult.IN_PROGRESS
        assert state.last_move is None
        assert state.last_move_by is None

    def test_last_move_and_phase_after_one_ply(self):
        controller = GameController(referee_engine=RefereeEngine())
        result = controller.apply_move("Agent1", "h2e2")
        assert result.success

        state = controller.get_current_state()
        assert state.last_move == "h2e2"
        assert state.last_move_by == "Agent1"
        assert state.phase == GamePhase.BLACK_TO_MOVE
        assert state.turn == "Black"

    def test_to_dict_exposes_passthrough_fields(self):
        controller = GameController(referee_engine=RefereeEngine())
        controller.apply_move("Agent1", "h2e2")

        d = controller.get_current_state().to_dict()
        assert d["phase"] == "black_to_move"
        assert d["last_move"] == "h2e2"
        assert d["last_move_by"] == "Agent1"
        assert d["result"] == "in_progress"

    def test_prompt_contains_last_move_section(self):
        """prompt 中的「上一步走步」段落此前永不渲染"""
        from src.agents.prompt_builder import PromptBuilder

        controller = GameController(referee_engine=RefereeEngine())
        controller.apply_move("Agent1", "h2e2")

        builder = PromptBuilder("你是一位象棋大师。")
        messages = builder.build_game_prompt(
            controller.get_current_state().to_dict(), player_color="Red"
        )
        user_content = messages[-1]["content"]
        assert "上一步走步" in user_content
        assert "h2e2" in user_content
        assert "Agent1" in user_content

    def test_reset_clears_last_move(self):
        controller = GameController(referee_engine=RefereeEngine())
        controller.apply_move("Agent1", "h2e2")
        controller.reset()

        state = controller.get_current_state()
        assert state.last_move is None
        assert state.last_move_by is None
        assert state.phase == GamePhase.RED_TO_MOVE

    def test_from_engine_backward_compatible(self):
        """from_engine(engine) 单参数调用仍应可用（main.py demo 依赖）"""
        engine = RefereeEngine()
        state = GameState.from_engine(engine)
        assert state.turn == "Red"
        assert state.fen == INITIAL_FEN
        assert state.phase == GamePhase.NOT_STARTED

    def test_last_move_tracks_engine_history(self):
        """last_move 取自引擎 move_history，与引擎保持一致"""
        controller = GameController(referee_engine=RefereeEngine())
        controller.apply_move("Agent1", "h2e2")
        controller.apply_move("Agent2", "h7e7")

        state = controller.get_current_state()
        assert state.last_move == "h7e7"
        assert state.last_move_by == "Agent2"
        assert state.game_history == ["h2e2", "h7e7"]
        assert state.phase == GamePhase.RED_TO_MOVE


# ---------------------------------------------------------------------------
# P0-3  终局推送给 3D 界面的永远是开局局面
# ---------------------------------------------------------------------------

class TestP0_3_FinalFenPropagation:
    """run_game() 必须返回终局 FEN，否则棋盘不会跳到终局画面。"""

    @pytest.mark.asyncio
    async def test_run_game_returns_final_fen_and_turn(self):
        from src.core.game_controller import LLMAgentGameController

        class ScriptedAgent:
            """按固定走步序列行动的假 Agent"""

            def __init__(self, name, color, moves):
                self.config = type(
                    "Cfg", (), {"name": name, "color": color, "llm_adapter": type("A", (), {"model": "fake"})()}
                )()
                self.moves = list(moves)

            def add_correction_feedback(self, *a, **kw):
                pass
            def reset(self):
                # play_turn resets conversation history every turn (R-3);
                # reset() is part of the agent contract.
                pass


            async def think(self, state):
                from src.agents.base_agent import AgentResult

                move = self.moves.pop(0) if self.moves else None
                return AgentResult(success=True, move=move, thought="t")

        controller = LLMAgentGameController(
            red_agent=ScriptedAgent("R", "Red", ["h2e2", "b0c2", "h0g2", "i0g2", "c3c4"]),
            black_agent=ScriptedAgent("B", "Black", ["i7e7", "b9c7", "h9g7", "i9g7", "c6c4"]),
            max_turns=2,  # 2 回合后主动结束，避免走到终局
        )

        result = await controller.run_game(verbose=False)

        assert "final_fen" in result, "run_game 必须返回 final_fen"
        assert "turn" in result, "run_game 必须返回 turn"
        assert "phase" in result
        # 终局 FEN 必须与引擎当前 FEN 一致，且不是开局 FEN
        assert result["final_fen"] == controller.referee.current_fen
        assert result["final_fen"] != INITIAL_FEN
        assert result["turn"] == controller.get_current_turn()

    def test_final_fen_is_not_initial_fen_after_moves(self):
        """回归：此前 final_fen 键缺失导致回退到开局 FEN"""
        controller = GameController(referee_engine=RefereeEngine())
        controller.apply_move("A", "h2e2")
        info = controller.get_game_info()

        assert controller.referee.current_fen != INITIAL_FEN
        assert info["last_move"] == "h2e2"


# ---------------------------------------------------------------------------
# P0-4  语义标注的棋子名全部退化成英文
# ---------------------------------------------------------------------------

class TestP0_4_AnnotationLocalization:
    """prompt 教 LLM 读「抽车/吃车」，引擎就必须真的产出中文标签。"""

    @pytest.fixture
    def builder(self):
        from src.agents.prompt_builder import PromptBuilder

        return PromptBuilder("你是一位象棋大师。")

    @pytest.mark.parametrize("piece_type", list(PieceType))
    def test_capture_annotation_is_chinese(self, builder, piece_type):
        got = builder._format_annotation("capture:%s" % piece_type.value)
        assert got == "吃" + builder._PIECE_TYPE_CN[piece_type.value]
        assert got.isascii() is False, "标注退化成英文了: %r" % got

    @pytest.mark.parametrize("piece_type", list(PieceType))
    def test_fork_annotation_is_chinese(self, builder, piece_type):
        got = builder._format_annotation("fork:%s" % piece_type.value)
        assert got == "抽" + builder._PIECE_TYPE_CN[piece_type.value]

    @pytest.mark.parametrize("piece_type", list(PieceType))
    def test_sacrifice_annotation_is_chinese(self, builder, piece_type):
        got = builder._format_annotation("sacrifice:%s" % piece_type.value)
        assert got == "弃" + builder._PIECE_TYPE_CN[piece_type.value]

    def test_mapping_keys_match_piece_type_values(self):
        """映射表键必须与 PieceType.value 完全一致"""
        from src.agents.prompt_builder import PromptBuilder

        assert set(PromptBuilder._PIECE_TYPE_CN) == {p.value for p in PieceType}

    def test_known_annotations_still_work(self):
        from src.agents.prompt_builder import PromptBuilder

        b = PromptBuilder("x")
        assert b._format_annotation("check") == "将军"
        assert b._format_annotation("repetition_warning") == "重复!"
        assert b._format_annotation("development") == "出车"
        assert b._format_annotation("cross_river") == "过河"
        assert b._format_annotation("central_file") == "占中"
        assert b._format_annotation("flank") == "占肋"
        assert b._format_annotation("pin") == "牵制"

    def test_engine_produces_annotations_prompt_can_translate(self):
        """端到端：引擎产出的标注必须全部能被翻译成中文"""
        from src.agents.prompt_builder import PromptBuilder

        engine = RefereeEngine()
        builder = PromptBuilder("x")
        untranslated = []
        for entry in engine.get_annotated_moves():
            for ann in entry["annotations"]:
                rendered = builder._format_annotation(ann)
                if rendered == ann:
                    untranslated.append(ann)
        assert not untranslated, "无法翻译的标注: %s" % sorted(set(untranslated))


# ---------------------------------------------------------------------------
# P0-5  纯文本模块强依赖 HTTP SDK
# ---------------------------------------------------------------------------

class TestP0_5_LazyPackageExports:
    """核心与提示词层必须能在没有第三方 SDK 的裸环境导入。"""

    def test_prompt_builder_import_does_not_load_openai(self):
        code = (
            "import sys, src.agents.prompt_builder;"
            "assert 'openai' not in sys.modules;"
            "print('ok')"
        )
        r = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert r.returncode == 0, f"prompt_builder 仍依赖 openai: {r.stderr}"

    def test_core_engine_import_has_no_third_party_deps(self):
        code = (
            "import sys, src.core.referee_engine;"
            "third = [m for m in ('openai','fastapi','pyglet','uvicorn') if m in sys.modules];"
            "assert not third, third;"
            "print('ok')"
        )
        r = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert r.returncode == 0, f"core 引入了第三方依赖: {r.stderr}"

    def test_web_3d_package_import_does_not_load_fastapi(self):
        code = (
            "import sys, src.web_3d;"
            "assert 'fastapi' not in sys.modules;"
            "print('ok')"
        )
        r = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert r.returncode == 0, f"web_3d 仍连带导入 fastapi: {r.stderr}"

    def test_lazy_export_resolves_real_classes(self):
        """惰性导出不能破坏既有导入方式"""
        from src.llm_adapters import DeepSeekAdapter, LLMResponse
        from src.llm_adapters.base_adapter import BaseLLMAdapter

        assert issubclass(DeepSeekAdapter, BaseLLMAdapter)
        assert LLMResponse(content="x").content == "x"

    def test_lazy_export_raises_for_unknown_attribute(self):
        import src.llm_adapters as la
        import src.web_3d as web

        with pytest.raises(AttributeError):
            _ = la.NoSuchExport
        with pytest.raises(AttributeError):
            _ = web.NoSuchExport

    @pytest.mark.parametrize(
        "module_name,attr",
        [
            ("src.llm_adapters", "BaseLLMAdapter"),
            ("src.llm_adapters", "DeepSeekAdapter"),
            ("src.web_3d", "WebSocketManager"),
        ],
    )
    def test_dir_includes_lazy_exports(self, module_name, attr):
        import importlib

        mod = importlib.import_module(module_name)
        assert attr in dir(mod)
