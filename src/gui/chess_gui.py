"""
中国象棋3D图形界面

使用pyglet实现3D渲染，独立线程运行
"""

import os

os.environ["PYGLET_HEADLESS"] = "False"
os.environ["PYGLET_DEBUG_GL"] = "0"
os.environ["PYGLET_SHADOW_WINDOW"] = "False"

import threading
import math
from typing import Optional
from ctypes import c_float

import pyglet
from pyglet import gl
from pyglet.gl import glu
from pyglet.window import mouse

from .chess_board_renderer import ChessBoardRenderer
from .piece_renderer import PieceRenderer, PIECE_LABELS
from .camera_controller import CameraController

INITIAL_FEN = "rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR"


class ChessGUI:
    """中国象棋3D图形界面"""

    def __init__(
        self,
        fen: str = INITIAL_FEN,
        red_agent_name: str = "红方AI",
        black_agent_name: str = "黑方AI",
    ):
        self.fen = fen
        self.batch = pyglet.graphics.Batch()

        self.red_agent_name = red_agent_name
        self.black_agent_name = black_agent_name

        self.board_renderer = ChessBoardRenderer()
        self.piece_renderer = PieceRenderer()
        self.camera = CameraController(distance=18, elevation=55, azimuth=45)

        self.pieces = {}
        self._parse_fen(fen)

        self.animating_piece = None
        self.animation_duration = 0.3

        self.window: Optional[pyglet.window.Window] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

        self._lock = threading.RLock()
        self._queue_lock = threading.Lock()  # 专门的队列锁，保护_move_queue
        self._move_queue: list = []
        self._ready = threading.Event()
        self._init_error: Optional[str] = None

    def _parse_fen(self, fen: str):
        """解析FEN格式的棋盘状态"""
        self.pieces.clear()

        parts = fen.split()
        position = parts[0]

        rows = position.split("/")
        for row_idx, row in enumerate(rows):
            col_idx = 0
            for char in row:
                if char.isdigit():
                    col_idx += int(char)
                else:
                    z = row_idx
                    x = col_idx
                    self.pieces[(x, z)] = char
                    col_idx += 1

    def _sync_pieces_from_fen(self):
        """从 self.fen 同步 self.pieces（单一数据源）"""
        if self.fen:
            self._parse_fen(self.fen)

    def _validate_state(self) -> bool:
        """校验 pieces 与 fen 一致性"""
        if not self.fen:
            return True

        expected_pieces = {}
        parts = self.fen.split()
        position = parts[0]
        rows = position.split("/")
        for row_idx, row in enumerate(rows):
            col_idx = 0
            for char in row:
                if char.isdigit():
                    col_idx += int(char)
                else:
                    expected_pieces[(col_idx, row_idx)] = char
                    col_idx += 1

        return self.pieces == expected_pieces

    def _iccs_to_coords(self, iccs_move: str) -> tuple:
        """将ICCS坐标转换为棋盘坐标

        ICCS坐标系：a1是黑方底角（数组z=0），i10是红方顶角（数组z=9）
        ICCS行号1-10 对应 棋盘数组索引0-9
        """
        if len(iccs_move) != 4:
            return None

        col1, row1 = iccs_move[0].lower(), int(iccs_move[1])
        col2, row2 = iccs_move[2].lower(), int(iccs_move[3])

        x1, z1 = ord(col1) - ord("a"), row1 - 1
        x2, z2 = ord(col2) - ord("a"), row2 - 1

        return (x1, z1), (x2, z2)

    def update(
        self,
        move: Optional[str] = None,
        fen: Optional[str] = None,
        is_game_over: bool = False,
    ):
        """更新棋盘状态（线程安全）- fen作为唯一数据源"""
        # 使用队列锁保护队列操作（快速路径）
        if not self._ready.is_set():
            with self._queue_lock:
                self._move_queue.append((move, fen, is_game_over))
            return

        with self._lock:
            if self.animating_piece:
                with self._queue_lock:
                    self._move_queue.append((move, fen, is_game_over))
                return

            if is_game_over:
                self._move_queue.clear()
                if fen:
                    self.fen = fen
                    self._sync_pieces_from_fen()
                return

            if move and fen:
                coords = self._iccs_to_coords(move)
                if coords:
                    from_pos, to_pos = coords
                    moving_char = self.pieces.get(from_pos)

                    if moving_char:
                        captured = self.pieces.get(to_pos)

                        self.animating_piece = {
                            "from": from_pos,
                            "to": to_pos,
                            "char": moving_char,
                            "captured": captured,
                            "progress": 0,
                            "target_fen": fen,
                        }
                    else:
                        self.fen = fen
                        self._sync_pieces_from_fen()
                else:
                    self.fen = fen
                    self._sync_pieces_from_fen()
            elif fen:
                self.fen = fen
                self._sync_pieces_from_fen()

    def _setup_lighting(self):
        """设置OpenGL光照与材质"""
        gl.glEnable(gl.GL_LIGHTING)
        gl.glEnable(gl.GL_LIGHT0)
        gl.glEnable(gl.GL_LIGHT1)
        gl.glEnable(gl.GL_NORMALIZE)
        gl.glEnable(gl.GL_COLOR_MATERIAL)
        gl.glColorMaterial(gl.GL_FRONT_AND_BACK, gl.GL_AMBIENT_AND_DIFFUSE)

        # 削弱镜面反射，符合木头质地
        gl.glMaterialfv(gl.GL_FRONT, gl.GL_SPECULAR, (c_float * 4)(0.1, 0.1, 0.1, 1.0))
        gl.glMateriali(gl.GL_FRONT, gl.GL_SHININESS, 16)

        gl.glLightfv(gl.GL_LIGHT0, gl.GL_POSITION, (c_float * 4)(4.0, 15.0, 4.5, 1.0))
        gl.glLightfv(gl.GL_LIGHT0, gl.GL_AMBIENT, (c_float * 4)(0.5, 0.5, 0.5, 1.0))
        gl.glLightfv(gl.GL_LIGHT0, gl.GL_DIFFUSE, (c_float * 4)(0.9, 0.85, 0.8, 1.0))
        gl.glLightfv(gl.GL_LIGHT0, gl.GL_SPECULAR, (c_float * 4)(0.2, 0.2, 0.2, 1.0))

        gl.glLightfv(gl.GL_LIGHT1, gl.GL_POSITION, (c_float * 4)(4.5, 10.0, 5.0, 1.0))
        gl.glLightfv(gl.GL_LIGHT1, gl.GL_AMBIENT, (c_float * 4)(0.3, 0.3, 0.3, 1.0))
        gl.glLightfv(gl.GL_LIGHT1, gl.GL_DIFFUSE, (c_float * 4)(0.6, 0.6, 0.6, 1.0))

        gl.glEnable(gl.GL_DEPTH_TEST)
        gl.glDepthFunc(gl.GL_LEQUAL)
        gl.glShadeModel(gl.GL_SMOOTH)
        gl.glClearColor(0.15, 0.12, 0.1, 1.0)

    def _draw_agent_labels(self):
        """绘制AI名称标签"""
        # 切换到正交投影用于绘制2D文字
        gl.glMatrixMode(gl.GL_PROJECTION)
        gl.glPushMatrix()
        gl.glLoadIdentity()
        glu.gluOrtho2D(0, self.window.width, 0, self.window.height)

        gl.glMatrixMode(gl.GL_MODELVIEW)
        gl.glPushMatrix()
        gl.glLoadIdentity()

        # 禁用光照和深度测试
        gl.glDisable(gl.GL_LIGHTING)
        gl.glDisable(gl.GL_DEPTH_TEST)

        # 绘制红方AI名称阴影（右上角）
        shadow_label = pyglet.text.Label(
            self.red_agent_name,
            font_name="Microsoft YaHei",
            font_size=16,
            color=(0, 0, 0, 255),
            x=self.window.width - 9,
            y=self.window.height - 19,
            anchor_x="right",
            anchor_y="top",
        )
        shadow_label.draw()

        red_label = pyglet.text.Label(
            self.red_agent_name,
            font_name="Microsoft YaHei",
            font_size=16,
            color=(220, 40, 40, 255),
            x=self.window.width - 10,
            y=self.window.height - 20,
            anchor_x="right",
            anchor_y="top",
        )
        red_label.draw()

        # 绘制黑方AI名称阴影
        shadow_label2 = pyglet.text.Label(
            self.black_agent_name,
            font_name="Microsoft YaHei",
            font_size=16,
            color=(0, 0, 0, 255),
            x=self.window.width - 9,
            y=self.window.height - 44,
            anchor_x="right",
            anchor_y="top",
        )
        shadow_label2.draw()

        black_label = pyglet.text.Label(
            self.black_agent_name,
            font_name="Microsoft YaHei",
            font_size=16,
            color=(255, 255, 255, 255),
            x=self.window.width - 10,
            y=self.window.height - 45,
            anchor_x="right",
            anchor_y="top",
        )
        black_label.draw()

        # 恢复状态
        gl.glEnable(gl.GL_DEPTH_TEST)
        gl.glEnable(gl.GL_LIGHTING)

        gl.glPopMatrix()
        gl.glMatrixMode(gl.GL_PROJECTION)
        gl.glPopMatrix()
        gl.glMatrixMode(gl.GL_MODELVIEW)

    def on_draw(self):
        """绘制回调"""
        if not self.window:
            return
        self.window.clear()

        gl.glMatrixMode(gl.GL_PROJECTION)
        gl.glLoadIdentity()
        glu.gluPerspective(45, self.window.width / self.window.height, 0.1, 100.0)

        gl.glMatrixMode(gl.GL_MODELVIEW)
        gl.glLoadIdentity()

        eye, target, up = self.camera.get_view_matrix()
        glu.gluLookAt(
            eye[0],
            eye[1],
            eye[2],
            target[0],
            target[1],
            target[2],
            up[0],
            up[1],
            up[2],
        )

        self._setup_lighting()

        gl.glPolygonMode(gl.GL_FRONT_AND_BACK, gl.GL_FILL)
        self.board_renderer.render()

        gl.glColor4f(1.0, 1.0, 1.0, 1.0)

        anim_pos = None
        anim_from = None
        anim_to = None
        captured_char = None

        with self._lock:
            pieces_snapshot = dict(self.pieces)
            if self.animating_piece:
                prog = min(1.0, self.animating_piece["progress"])
                from_x = int(self.animating_piece["from"][0])
                from_z = int(self.animating_piece["from"][1])
                to_x = int(self.animating_piece["to"][0])
                to_z = int(self.animating_piece["to"][1])

                curr_x = from_x + (to_x - from_x) * prog
                curr_z = from_z + (to_z - from_z) * prog
                anim_pos = (curr_x, curr_z, self.animating_piece["char"])
                anim_from = (from_x, from_z)
                anim_to = (to_x, to_z)
                captured_char = self.animating_piece.get("captured")

        board_y = self.board_renderer.board_thickness

        for (x, z), char in pieces_snapshot.items():
            ix, iz = int(x), int(z)
            if anim_from and ix == anim_from[0] and iz == anim_from[1]:
                continue
            if anim_to and ix == anim_to[0] and iz == anim_to[1]:
                continue

            gl.glPushMatrix()
            gl.glTranslatef(x, board_y, z)
            self.piece_renderer.render_piece(char)
            gl.glPopMatrix()

        if anim_pos:
            gl.glPushMatrix()
            gl.glTranslatef(anim_pos[0], board_y, anim_pos[1])
            self.piece_renderer.render_piece(anim_pos[2])
            gl.glPopMatrix()

        if anim_to and captured_char:
            with self._lock:
                if self.animating_piece and self.animating_piece["progress"] > 0.5:
                    alpha = 1.0 - (self.animating_piece["progress"] - 0.5) * 2
                    gl.glColor4f(1.0, 1.0, 1.0, alpha)
                    gl.glPushMatrix()
                    gl.glTranslatef(anim_to[0], board_y, anim_to[1])
                    self.piece_renderer.render_piece(captured_char)
                    gl.glPopMatrix()
                    gl.glColor4f(1.0, 1.0, 1.0, 1.0)

        self._draw_agent_labels()

    def on_mouse_press(self, x, y, button, modifiers):
        """鼠标按下"""
        if button == mouse.LEFT:
            self.camera.start_drag(x, y)

    def on_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
        """鼠标拖拽"""
        if buttons & mouse.LEFT:
            self.camera.drag(x, y)

    def on_mouse_release(self, x, y, button, modifiers):
        """鼠标释放"""
        if button == mouse.LEFT:
            self.camera.end_drag()

    def on_mouse_scroll(self, x, y, scroll_x, scroll_y):
        """鼠标滚轮"""
        self.camera.zoom(scroll_y)

    def update_animation(self, dt):
        """更新动画（主线程调用，线程安全）"""
        if not self._running or not self.window:
            return

        with self._lock:
            if self.animating_piece:
                self.animating_piece["progress"] += dt / self.animation_duration
                if self.animating_piece["progress"] >= 1.0:
                    target_fen = self.animating_piece.get("target_fen")
                    self.animating_piece = None

                    if target_fen:
                        self.fen = target_fen
                        self._sync_pieces_from_fen()

                    if self._move_queue:
                        move, fen, is_over = self._move_queue.pop(0)
                        self.update(move=move, fen=fen, is_game_over=is_over)

    def run(self):
        """运行GUI（主循环）"""
        if self._running:
            return

        self._running = True

        try:
            display = pyglet.display.get_display()
            screen = display.get_screens()[0]
            template = pyglet.gl.Config(
                double_buffer=True,
                depth_size=24,
                sample_buffers=1,
                samples=4,
            )
            config = screen.get_best_config(template)
        except Exception:
            config = None

        try:
            if config:
                self.window = pyglet.window.Window(
                    width=1024,
                    height=768,
                    caption="中国象棋 - LLM Battle",
                    resizable=True,
                    config=config,
                )
            else:
                self.window = pyglet.window.Window(
                    width=1024,
                    height=768,
                    caption="中国象棋 - LLM Battle",
                    resizable=True,
                )

            self.window.on_draw = self.on_draw
            self.window.on_mouse_press = self.on_mouse_press
            self.window.on_mouse_drag = self.on_mouse_drag
            self.window.on_mouse_release = self.on_mouse_release
            self.window.on_mouse_scroll = self.on_mouse_scroll

            self.window.switch_to()

            self.board_renderer.init_gl()
            self.piece_renderer.init_gl()

            self._ready.set()

            if self._move_queue:
                move, fen, is_over = self._move_queue.pop(0)
                self.update(move=move, fen=fen, is_game_over=is_over)

            pyglet.clock.schedule_interval(self.update_animation, 1 / 60.0)

            pyglet.app.run()

        except Exception as e:
            self._init_error = str(e)
            self._ready.set()
        finally:
            self._running = False

    def start(self):
        """在新线程中启动GUI"""
        if self._thread and self._thread.is_alive():
            return

        self._thread = threading.Thread(target=self.run, daemon=True)
        self._thread.start()

    def wait_ready(self, timeout: float = 10.0) -> bool:
        """等待GUI初始化完成

        Args:
            timeout: 超时时间（秒）

        Returns:
            True表示GUI已就绪，False表示超时或初始化失败
        """
        return self._ready.wait(timeout=timeout) and self._init_error is None

    def is_ready(self) -> bool:
        """检查GUI是否已就绪"""
        return self._ready.is_set() and self._init_error is None

    def stop(self):
        """停止GUI"""
        self._running = False
        if self.window:
            self.window.close()
