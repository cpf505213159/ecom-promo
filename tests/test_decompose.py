"""分解逻辑的单元测试。

重点测两件「错了不会报错、但结论会全错」的事：
1. 三层分解是否真正闭合（残差应为 0，不是「差不多」）
2. mix + within 是否等于总体变化（拆不干净说明权重用错了）
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.decompose import (  # noqa: E402
    category_totals,
    decompose_total,
    shift_share,
    stockout_tradeoff,
)
from src.gen import build  # noqa: E402


def _toy() -> pd.DataFrame:
    """构造一个两期两品类的极简数据，手算可验证。"""
    rows = []
    # 2024：A 100 UV × 10% × 50 元；B 100 UV × 20% × 20 元
    # 2025：A 200 UV × 10% × 50 元；B 100 UV × 20% × 20 元  → 只有客流变化
    for year, uv_a, uv_b in [(2024, 100, 100), (2025, 200, 100)]:
        for cat, uv, cvr, aov in [("A", uv_a, 0.10, 50.0), ("B", uv_b, 0.20, 20.0)]:
            rows.append({"year": year, "promo": "toy", "date": pd.Timestamp(f"{year}-11-01"),
                         "day_index": 0, "category": cat, "uv": uv, "cvr": cvr, "aov": aov})
    df = pd.DataFrame(rows)
    df["orders"] = df["uv"] * df["cvr"]
    df["gmv"] = df["orders"] * df["aov"]
    return df


def test_decomposition_closes() -> None:
    d = decompose_total(_toy())
    assert abs(d["closure_error"]) < 1e-9
    assert abs(d["uv_effect"] + d["cvr_effect"] + d["aov_effect"] - d["gmv_delta"]) < 1e-9


def test_pure_traffic_creates_fake_effects() -> None:
    """纯流量结构变化，会在总体层造出「假的」转化与客单效应。

    这是本项目最想固定住的性质：A 品类 UV 翻倍、各品类自身的 CVR/AOV 一点没变，
    但大盘 CVR 从 15% 掉到 13.3%、AOV 从 30 涨到 35——因为份额变了。
    如果只看三层分解就下结论，会把「结构」误判成「运营提效」。
    """
    d = decompose_total(_toy())
    assert abs(d["cvr_effect"]) > 1
    assert abs(d["aov_effect"]) > 1
    # 但恒等式仍然闭合：假效应不是算错，是分解层级的局限
    assert abs(d["closure_error"]) < 1e-9


def test_pure_traffic_is_structural() -> None:
    """再往下拆一层，这些「假效应」应该全部由 mix 解释，within 为 0。"""
    m = shift_share(_toy()).set_index("指标")
    for metric in ["转化率 CVR", "客单价 AOV"]:
        row = m.loc[metric]
        assert abs(row["自身效应 within"]) < 1e-9, metric
        assert abs(row["结构效应 mix"] - row["总体变化"]) < 1e-9, metric


def test_mix_and_within_add_up() -> None:
    df, _ = build()
    m = shift_share(df)
    for _, row in m.iterrows():
        assert abs(row["结构效应 mix"] + row["自身效应 within"] - row["总体变化"]) < 1e-9, row["指标"]


def test_category_totals_self_consistent() -> None:
    df, _ = build()
    g = category_totals(df)
    # cvr 与 orders/uv 自洽：orders ≈ uv*days*cvr
    for _, r in g.iterrows():
        assert abs(r["orders"] - r["uv"] * r["days"] * r["cvr"]) / max(r["orders"], 1) < 0.01


def test_stockout_monotonic() -> None:
    """服务水平越高，备货越多、缺货率越低。"""
    df, _ = build()
    s = stockout_tradeoff(df, service_levels=(0.80, 0.88, 0.95))
    assert s["缺货率"].is_monotonic_decreasing
    assert s["库存金额（万元）"].is_monotonic_increasing


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"✓ {name}")
