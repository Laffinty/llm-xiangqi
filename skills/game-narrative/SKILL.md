---
name: game-narrative
description: 对局主题：开局锁定一个棋风目标。仅在局面阶段判定为 opening 时激活（棋风开局选定，中局由 tempo 纪律接管）。
kind: knowledge
when:
  - field: board_phase
    op: eq
    value: opening
---
# 对局主题

**开局选定一种棋风，中局不换。** 选定后它就写在你的 `thought` 里，
后续每步「战略目标」一栏都应与之一致。

两端选不同棋风（一攻一守），对局才有张力。**双方同质化是最常见的无趣成因**——
都走「稳健」则谁也不施压，棋就闷了。

**棋风决定取向**，不是「每步都冒进」或「每步都保守」。四型定义与各型起手取向
详见 `references/style-notes.md`。

> `PLAN-SPECTACLE-001` `P-02` 新增。对应指标：`style_drift_count`。
> **激活说明**：仅开局激活，而非常驻。因常驻会给每个局面组合加约 460 字符，
> 与中局弃子/节奏 doctrine 叠加后超出 prompt 预算（见 `tests/test_skills.py`
> 的预算门禁注释）。代价是中局不再携带「锁定棋风」提醒。
> **已知盲区**：`style_drift_count` 测不出「双方是否同质」——两边用同一段棋风
> 文字时各自都不漂移，指标为 0，棋局却依然无趣。真正的解法是 `P-04`（挂起）。