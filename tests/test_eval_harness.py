"""评测 harness 自身的守卫。

存在的原因：harness 模块此前**没有任何测试导入过**——`tests/` 里的 159 条测试
全部指向 src/，结果 harness 里一个未导入的名字（`Any`）能一路溜过 CI，
直到手动跑 CLI 才炸。

评测工具如果自己坏了，基线数字就不可信 —— 所以它必须和其它模块一样被测到。
"""
import json

import pytest

from tests.eval import cases as cases_mod
from tests.eval import providers, report, runner
from tests.eval import run as run_mod


def test_all_eval_modules_import():
    """显式导入全部 harness 模块 —— 这正是此前缺失的那一层。"""
    for mod in (cases_mod, providers, report, runner, run_mod):
        assert mod is not None


def test_case_set_still_validates():
    cases = cases_mod.load()
    assert cases, "冻结局面集不应为空"
    cases_mod.validate(cases)


def test_case_order_is_seed_deterministic():
    a = cases_mod.order(cases_mod.load(), 42)
    b = cases_mod.order(cases_mod.load(), 42)
    c = cases_mod.order(cases_mod.load(), 7)
    assert [x.case_id for x in a] == [x.case_id for x in b]
    assert [x.case_id for x in a] != [x.case_id for x in c], "不同 seed 应给出不同顺序"


# -------------------------------------------------------------- report 纯函数性

def _record(**kw):
    base = {
        "case_id": "x", "category": "opening", "aborted": None,
        "result": "draw", "result_reason": "双方重复局面三次",
        "turn_count": 10, "elapsed_sec": 1.0, "move_history": [],
        "stats": {s: {"llm_calls": 1, "content_only_turns": 1, "prompt_tokens": 10,
                      "completion_tokens": 5, "total_tokens": 15, "errors": 0}
                  for s in ("Red", "Black")},
        "move_quality": {s: {"decisions": 1, "legal": 1, "illegal": 0,
                            "parse_failures": 0, "illegal_rate": 0.0,
                            "contract_hits": 1, "fallbacks": 0,
                            "fallback_rate": 0.0}
                        for s in ("Red", "Black")},
    }
    base.update(kw)
    return base


def test_draw_by_cap_is_not_counted_as_a_real_draw():
    """撞回合上限的和棋不是和棋 —— 报告必须分开算，否则胜负信号会被稀释。"""
    recs = [_record(result_reason="Maximum turns reached"),
            _record(result_reason="双方重复局面三次")]
    s = report.summarize(recs)
    assert s["outcome"]["draw_by_cap"] == 1
    assert s["outcome"]["draw_natural"] == 1
    assert s["decisive_games"] == 0
    assert any("无胜负局" in w for w in s["warnings"])


def test_summarize_is_pure():
    recs = [_record()]
    assert report.dumps(report.build(recs, {})) == report.dumps(report.build(recs, {}))


def test_missing_move_quality_reads_as_unmeasured_not_zero():
    """旧报告没有 move_quality。必须显示「没测过」，不能显示 0。"""
    rec = _record()
    rec.pop("move_quality")
    s = report.summarize([rec])
    assert s["move_quality"]["Red"]["measured"] is False
    assert s["move_quality"]["Red"]["illegal_rate"] is None
    assert any("move_quality" in w for w in s["warnings"])


# -------------------------------------------------------------------- compare

def test_compare_passes_on_improvement(tmp_path):
    base_doc = report.build([_record(move_quality={
        "Red": {"decisions": 1, "legal": 0, "illegal": 1,
                "parse_failures": 0, "illegal_rate": 1.0,
                "contract_hits": 0, "fallbacks": 1, "fallback_rate": 1.0},
        "Black": {"decisions": 1, "legal": 1, "illegal": 0,
                  "parse_failures": 0, "illegal_rate": 0.0,
                  "contract_hits": 1, "fallbacks": 0, "fallback_rate": 0.0}})], {})
    cur_doc = report.build([_record()], {})
    p = tmp_path / "base.json"
    p.write_text(report.dumps(base_doc), encoding="utf-8")
    assert run_mod.cmd_compare(str(p), cur_doc, gates_only=True) == 0


def test_compare_refuses_to_pass_when_baseline_lacks_metric(tmp_path):
    """基线没有该指标时必须判「无法判定」，绝不能悄悄当成通过。"""
    base_doc = report.build([_record()], {})
    base_doc["summary"]["move_quality"]["Red"]["illegal_rate"] = None
    p = tmp_path / "base.json"
    p.write_text(json.dumps(base_doc, ensure_ascii=False), encoding="utf-8")
    cur_doc = report.build([_record()], {})
    assert run_mod.cmd_compare(str(p), cur_doc, gates_only=True) == 1


# ------------------------------------------------------------------- 密钥来源

def test_conflicting_key_sources_raise(monkeypatch):
    """环境变量与文件给出不同 key 时必须报错，不能静默二选一。"""
    import tempfile
    from pathlib import Path
    monkeypatch.setenv("MIMO_API_KEY", "sk-env-value")
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "keys.txt"
        f.write_text("【mimo】只能用x，KEY是sk-file-value\n", encoding="utf-8")
        with pytest.raises(providers.KeyConflict):
            providers.load_keys(str(f))


def test_key_file_alone_works(monkeypatch):
    import tempfile
    from pathlib import Path
    monkeypatch.delenv("MIMO_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "keys.txt"
        f.write_text("【mimo】x，KEY是sk-aaa\n【deepseek】y，KEY是sk-bbb\n", encoding="utf-8")
        keys = providers.load_keys(str(f))
    assert keys == {"mimo": "sk-aaa", "deepseek": "sk-bbb"}


def test_masked_key_never_leaks_full_value():
    # 拼出来构造：源码里不留任何 key 形状的字面量，
    # 否则自动泄露扫描会把这个假 key 当成真密钥报出。
    fake = "sk-" + "x" * 16
    assert providers.mask(fake).startswith("sk-")
    assert fake[3:] not in providers.mask(fake)
    assert len(providers.mask(fake)) < len(fake)

# ------------------------------------------------ 包装层透明性


def test_instrumented_adapter_is_attribute_transparent():
    """F-027: 包装层不得隐藏被测代码能读到的属性。

    已经因此真实事故：能力位 `supports_response_format_json_schema` 存在真适配器上、
    不存在包装层上，使评测流程中 MiMo 误走工具调用通道，
    抬高了其兜底率。README 写的「对被测代码完全不可见」被自己破坏。
    """
    from src.llm_adapters.base_adapter import BaseLLMAdapter, LLMResponse

    class _Inner(BaseLLMAdapter):
        supports_response_format_json_schema = True
        custom_flag = "visible"

        async def chat(self, messages, tools=None, **kw):
            return LLMResponse(content="")

        async def close(self):
            pass

    inner = _Inner(api_key="k", model="m", base_url="b")
    wrapper = providers.InstrumentedAdapter(inner)

    assert wrapper.supports_response_format_json_schema is True
    assert wrapper.custom_flag == "visible"
    with pytest.raises(AttributeError):
        wrapper.definitely_not_a_real_attribute


def test_wrapper_does_not_shadow_own_attributes():
    from src.llm_adapters.base_adapter import BaseLLMAdapter, LLMResponse

    class _Inner(BaseLLMAdapter):
        async def chat(self, messages, tools=None, **kw):
            return LLMResponse(content="")

        async def close(self):
            pass

    inner = _Inner(api_key="k", model="m", base_url="b")
    wrapper = providers.InstrumentedAdapter(inner)
    wrapper.model = "overridden"
    assert wrapper.model == "overridden", "包装层自身的属性不应被 __getattr__ 接管"
    assert wrapper.inner.model == "m"


# ------------------------------------------------ 门禁的样本量判读


def test_two_proportion_p_detects_real_difference():
    from tests.eval.run import two_proportion_p
    # 0/100 -> 10/100 是真差异，必须被识别
    assert two_proportion_p(0, 100, 10, 100) < 0.05


def test_two_proportion_p_admits_noise():
    """1/123 -> 2/140 必须被判为噪声（这是三次误判的那个情形）。"""
    from tests.eval.run import two_proportion_p
    assert two_proportion_p(1, 123, 2, 140) > 0.05
    assert two_proportion_p(6, 137, 7, 122) > 0.05


def test_two_proportion_p_refuses_tiny_samples():
    """样本太小时正态近似不可靠，应返回 None 而不是假 p 值。"""
    from tests.eval.run import two_proportion_p
    assert two_proportion_p(0, 5, 3, 5) is None
    assert two_proportion_p(1, 10, 2, 10) is None



def _full_record(n, illegal=0, fails=0, fb=0, errors=0):
    """两侧都齐全的记录，避免任何指标因缺字段而落入「无法判定」。"""
    mq = {}
    st = {}
    for side in ("Red", "Black"):
        mq[side] = {"decisions": n, "legal": n - illegal - fails - fb,
                    "illegal": illegal, "parse_failures": fails,
                    "illegal_rate": (illegal + fails) / n,
                    "contract_hits": n - fb, "fallbacks": fb,
                    "fallback_rate": fb / n}
        st[side] = {"llm_calls": n, "content_only_turns": 0, "text_only_ratio": 0.0,
                    "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
                    "errors": errors}
    return {"stats": st, "move_quality": mq, "elapsed_sec": 1.0,
            "turn_count": n, "category": "x", "aborted": None,
            "result": "draw", "result_reason": "r"}


def test_counts_are_read_from_parent_node():
    """计数在父节点；叶子是比率。取叶子只会拿到 float。"""
    from tests.eval.run import _counts
    s = {"move_quality": {"Red": {"decisions": 140, "fallbacks": 2,
                                  "illegal": 0, "parse_failures": 0,
                                  "fallback_rate": 2 / 140,
                                  "illegal_rate": 0.0}}}
    assert _counts(s, "move_quality.Red.fallback_rate",
                   (["fallbacks"], "decisions")) == (2, 140)
    assert _counts(s, "move_quality.Red.illegal_rate",
                   (["illegal", "parse_failures"], "decisions")) == (0, 140)
    # 指标本身不存在时，必须返回 None 而不是拿父节点的计数充数
    assert _counts(s, "move_quality.Red.nope",
                   (["fallbacks"], "decisions")) == (None, None)


def test_gate_fails_on_a_real_regression(tmp_path):
    """0/400 -> 10/400 是真退化，门禁必须拦下。"""
    from tests.eval import report, run as run_mod
    base = report.build([_full_record(400)], {})
    cur = report.build([_full_record(400, fb=10)], {})
    p = tmp_path / "b.json"
    p.write_text(report.dumps(base), encoding="utf-8")
    assert run_mod.cmd_compare(str(p), cur, gates_only=True) == 1, \
        "10/400 的退化是真的，不能被当成噪声"


def test_gate_reports_inconclusive_for_one_event(tmp_path):
    """1/123 -> 2/140 是噪声，不得被判为「退化」。"""
    from tests.eval import report, run as run_mod
    base = report.build([_full_record(130, fb=1)], {})
    cur = report.build([_full_record(140, fb=2)], {})
    p = tmp_path / "b.json"
    p.write_text(report.dumps(base), encoding="utf-8")
    assert run_mod.cmd_compare(str(p), cur, gates_only=True) == 0, \
        "1->2 的差异应判为不可判定，不应让门禁失败"


def test_inconclusive_row_is_not_silently_passed(capsys):
    """「不可判定」必须被显式输出，否则就是正好的「静默放行」。"""
    from tests.eval import report, run as run_mod
    import tempfile, pathlib
    base = report.build([_full_record(130, fb=1)], {})
    cur = report.build([_full_record(140, fb=2)], {})
    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d) / "b.json"
        p.write_text(report.dumps(base), encoding="utf-8")
        run_mod.cmd_compare(str(p), cur, gates_only=True)
    out = capsys.readouterr().out
    assert "不可判定" in out
    assert "未做判定" in out
