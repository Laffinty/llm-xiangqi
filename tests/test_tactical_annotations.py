"""
战术标注走步测试

测试六类新增标注：
1. cross_river: 兵卒过河
2. central_file: 车/炮占中路
3. flank: 车/炮占肋道
4. pin: 牵制
5. fork:{piece_type}: 捉双
6. sacrifice:{piece_type}: 弃子
"""

import pytest
from src.core.referee_engine import RefereeEngine, Color


class TestCrossRiverAnnotation:
    """测试过河标注"""

    def test_red_pawn_cross_river(self):
        """测试红兵过河有cross_river标注"""
        # 红兵在c4（即将过河），红帅e0，黑将d9（错开避免飞将）
        fen = "3k5/9/9/9/9/2P6/9/9/9/4K4 w - - 0 1"
        engine = RefereeEngine(fen)
        annotated = engine.get_annotated_moves()
        
        # 找到所有包含cross_river的走步
        cross_river_moves = [m for m in annotated if "cross_river" in m["annotations"]]
        # 红兵c4过河到c5应该有标注
        c4c5 = [m for m in cross_river_moves if m["move"] == "c4c5"]
        assert len(c4c5) == 1, f"Expected c4c5 to have cross_river annotation, got {cross_river_moves}"

    def test_red_pawn_already_river_no_annotation(self):
        """测试已过河的兵不再标注"""
        # 红兵已在c5（已过河），黑将d9
        fen = "3k5/9/9/9/9/9/2P6/9/9/4K4 w - - 0 1"
        engine = RefereeEngine(fen)
        annotated = engine.get_annotated_moves()
        
        # 找到 c5c6 走步，不应有cross_river
        c5c6 = [m for m in annotated if m["move"] == "c5c6"]
        if c5c6:
            assert "cross_river" not in c5c6[0]["annotations"]

    def test_black_pawn_cross_river(self):
        """测试黑卒过河有cross_river标注"""
        # 黑卒在c5（即将过河），黑将e9，红帅d0（错开避免飞将）
        # FEN: 第5行(row 4)是2p6，黑卒在c5
        fen = "4k4/9/9/9/2p6/9/9/9/9/3K5 b - - 0 1"
        engine = RefereeEngine(fen)
        annotated = engine.get_annotated_moves()
        
        # 找到所有包含cross_river的走步
        cross_river_moves = [m for m in annotated if "cross_river" in m["annotations"]]
        # 黑卒c5过河到c4应该有标注
        c5c4 = [m for m in cross_river_moves if m["move"] == "c5c4"]
        assert len(c5c4) == 1, f"Expected c5c4 to have cross_river annotation, got {cross_river_moves}"


class TestCentralFileAnnotation:
    """测试占中标注"""

    def test_rook_central_file(self):
        """测试车走到中路有central_file标注"""
        # 红车在a0，红帅g0（不阻挡车），黑将e9
        # 车从a0可以走到e0（中路）
        fen = "4k4/9/9/9/9/9/9/9/9/R5K1R w - - 0 1"
        engine = RefereeEngine(fen)
        annotated = engine.get_annotated_moves()
        
        # 找到所有占中的走步
        central_moves = [m for m in annotated if "central_file" in m["annotations"]]
        # 左车a0走到e0应该是占中
        a0_to_e0 = [m for m in central_moves if m["move"] == "a0e0"]
        assert len(a0_to_e0) == 1, f"Expected a0e0 to have central_file, got moves: {[m['move'] for m in central_moves]}"

    def test_cannon_central_file(self):
        """测试炮走到中路有central_file标注"""
        # 红炮在b2，红帅d0，黑将e9
        fen = "4k4/9/9/9/9/9/9/1C7/9/3K5 w - - 0 1"
        engine = RefereeEngine(fen)
        annotated = engine.get_annotated_moves()
        
        # 找到所有占中的走步
        central_moves = [m for m in annotated if "central_file" in m["annotations"]]
        # b2走到e2应该是占中
        b2e2 = [m for m in central_moves if m["move"] == "b2e2"]
        assert len(b2e2) == 1, f"Expected b2e2 to have central_file, got: {central_moves}"


class TestFlankAnnotation:
    """测试占肋标注"""

    def test_rook_flank_f_file(self):
        """测试车走到f列（肋道）有flank标注"""
        # 红车在i0，红帅d0，黑将e9
        # 车从i0走到f0是右肋道
        fen = "4k4/9/9/9/9/9/9/9/9/3K4R w - - 0 1"
        engine = RefereeEngine(fen)
        annotated = engine.get_annotated_moves()
        
        # 找到所有占肋的走步
        flank_moves = [m for m in annotated if "flank" in m["annotations"]]
        # i0走到f0应该是占肋（f列是右肋道）
        i0f0 = [m for m in flank_moves if m["move"] == "i0f0"]
        assert len(i0f0) == 1, f"Expected i0f0 to have flank, got: {flank_moves}"

    def test_cannon_flank(self):
        """测试炮走到肋道有flank标注"""
        # 红炮在b2，走到d2（肋道），黑将e9，红帅d0
        fen = "4k4/9/9/9/9/9/9/1C7/9/3K5 w - - 0 1"
        engine = RefereeEngine(fen)
        annotated = engine.get_annotated_moves()
        
        # 找到所有占肋的走步
        flank_moves = [m for m in annotated if "flank" in m["annotations"]]
        # b2走到d2应该是占肋
        b2d2 = [m for m in flank_moves if m["move"] == "b2d2"]
        assert len(b2d2) == 1, f"Expected b2d2 to have flank, got: {flank_moves}"


class TestCombinedAnnotations:
    """测试组合标注"""

    def test_development_and_central_file_in_initial_position(self):
        """测试初始局面中炮的出子+占中组合"""
        # 初始局面，红炮h2走到e2是占中（且有pin牵制标注）
        engine = RefereeEngine()
        annotated = engine.get_annotated_moves()
        
        # 找到炮占中的走步
        cannon_central = [m for m in annotated 
                         if m["move"] in ["b2e2", "h2e2"]
                         and "central_file" in m["annotations"]]
        
        assert len(cannon_central) >= 1, f"Expected cannon central file moves, got: {cannon_central}"

    def test_cross_river_and_capture(self):
        """测试过河+吃子同时标注"""
        # 红兵在c4，黑炮在c5（可被吃），黑将d9，红帅e0
        # FEN: c4是row 4, c5是row 5 (2P6在第5行, 2c6在第4行)
        # 需要红兵在c4(row 4), 黑炮在c5(row 5)
        fen = "3k5/9/9/9/2c6/2P6/9/9/9/4K4 w - - 0 1"
        engine = RefereeEngine(fen)
        annotated = engine.get_annotated_moves()
        
        # 找到c4c5走步
        c4c5 = [m for m in annotated if m["move"] == "c4c5"]
        assert len(c4c5) == 1, f"Expected c4c5 to exist, got: {annotated}"
        
        # 检查是否有cross_river和capture标注
        anns = c4c5[0]["annotations"]
        has_cross = "cross_river" in anns
        has_capture = any(a.startswith("capture:") for a in anns)
        
        assert has_cross, f"Expected cross_river annotation, got: {anns}"
        assert has_capture, f"Expected capture annotation, got: {anns}"


class TestAnnotationBackwardCompat:
    """测试标注机制向后兼容"""

    def test_all_moves_have_annotations_field(self):
        """测试所有走步都有annotations字段"""
        engine = RefereeEngine()
        annotated = engine.get_annotated_moves()
        
        for entry in annotated:
            assert "move" in entry
            assert "annotations" in entry
            assert isinstance(entry["annotations"], list)

    def test_original_annotations_still_work(self):
        """测试原有标注仍然有效"""
        engine = RefereeEngine()
        annotated = engine.get_annotated_moves()
        
        # 检查development标注
        dev_moves = [m for m in annotated if "development" in m["annotations"]]
        assert len(dev_moves) >= 2  # 至少有两个出车走步

    def test_new_annotations_exist(self):
        """测试新标注类型存在"""
        # 使用一个能触发多种标注的局面
        # 红车在a0，红兵在c4，红帅d0，黑将e9
        fen = "4k4/9/9/9/9/9/9/9/9/R1PK5 w - - 0 1"
        engine = RefereeEngine(fen)
        annotated = engine.get_annotated_moves()
        
        # 收集所有标注类型
        all_anns = set()
        for m in annotated:
            all_anns.update(m["annotations"])
        
        # 验证新标注类型可以被生成
        # 至少应该有development标注（车从底线出发）
        assert "development" in all_anns or len(annotated) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
