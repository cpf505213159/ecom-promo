"""GMV 三层分解 + 品类结构（mix / within）+ 备货与缺货率换算。

核心是一个**恒等式**，不是模型：

    GMV = UV × CVR × AOV

因此同比增量可以精确拆成三项（链式顺序分解，不留残差）：

    ΔGMV = ΔUV·CVR₀·AOV₀        ← 客流效应
         + UV₁·ΔCVR·AOV₀        ← 转化效应
         + UV₁·CVR₁·ΔAOV        ← 客单效应

真实项目里报「误差 3% 以内」，误差不来自公式，而来自口径：
退款剔除、跨端 UV 去重、预售定金与尾款的时间归属。这一点在报告里单独说明。

再往下一层，把 CVR 与 AOV 的变化拆成「各品类自身变化（within）」与
「品类结构变化（mix）」——大促最常见的误判是把「结构升级」算成「运营提效」。
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def category_totals(df: pd.DataFrame) -> pd.DataFrame:
    """按年份 × 品类汇总。UV 用日均（不是 11 天加总），避免天数口径混淆。"""
    g = (df.groupby(["year", "category"])
         .agg(uv=("uv", "mean"), orders=("orders", "sum"), gmv=("gmv", "sum"), days=("date", "nunique"))
         .reset_index())
    g["cvr"] = g["orders"] / (g["uv"] * g["days"])
    g["aov"] = g["gmv"] / g["orders"]
    return g


def totals(df: pd.DataFrame) -> pd.DataFrame:
    """整体口径：UV 取日均，CVR = 订单 / (日均UV × 天数)，AOV = GMV / 订单。"""
    g = (df.groupby("year")
         .agg(uv=("uv", "mean"), orders=("orders", "sum"), gmv=("gmv", "sum"), days=("date", "nunique"))
         .reset_index())
    g["cvr"] = g["orders"] / (g["uv"] * g["days"])
    g["aov"] = g["gmv"] / g["orders"]
    return g


def decompose_total(df: pd.DataFrame) -> dict:
    """三层链式分解，返回各效应与闭合误差。"""
    t = totals(df).set_index("year")
    b, c = t.loc[2024], t.loc[2025]

    uv_effect = (c.uv - b.uv) * b.cvr * b.aov * b.days
    cvr_effect = c.uv * (c.cvr - b.cvr) * b.aov * c.days
    aov_effect = c.uv * c.cvr * (c.aov - b.aov) * c.days

    delta = c.gmv - b.gmv
    explained = uv_effect + cvr_effect + aov_effect
    return {
        "gmv_base": float(b.gmv),
        "gmv_cur": float(c.gmv),
        "gmv_delta": float(delta),
        "growth": float(delta / b.gmv),
        "uv_effect": float(uv_effect),
        "cvr_effect": float(cvr_effect),
        "aov_effect": float(aov_effect),
        "explained": float(explained),
        "closure_error": float(delta - explained),
        "closure_error_pct": float((delta - explained) / delta) if delta else 0.0,
        "uv_contrib": float(uv_effect / delta),
        "cvr_contrib": float(cvr_effect / delta),
        "aov_contrib": float(aov_effect / delta),
    }


def shift_share(df: pd.DataFrame) -> pd.DataFrame:
    """把 CVR 与 AOV 的总体变化拆成 mix（结构）与 within（自身）。

    权重口径：
      CVR 用 UV 份额加权（转化率的自然分母是流量）
      AOV 用订单份额加权（客单价的分母是订单）
    """
    g = category_totals(df)
    b = g[g.year == 2024].set_index("category")
    c = g[g.year == 2025].set_index("category")

    w_uv_b = b["uv"] / b["uv"].sum()
    w_uv_c = c["uv"] / c["uv"].sum()
    w_or_b = b["orders"] / b["orders"].sum()
    w_or_c = c["orders"] / c["orders"].sum()

    cvr_mix = float(((w_uv_c - w_uv_b) * b["cvr"]).sum())
    cvr_within = float((w_uv_c * (c["cvr"] - b["cvr"])).sum())
    aov_mix = float(((w_or_c - w_or_b) * b["aov"]).sum())
    aov_within = float((w_or_c * (c["aov"] - b["aov"])).sum())

    return pd.DataFrame([
        {"指标": "转化率 CVR", "总体变化": c["cvr"] @ w_uv_c - b["cvr"] @ w_uv_b,
         "结构效应 mix": cvr_mix, "自身效应 within": cvr_within},
        {"指标": "客单价 AOV", "总体变化": c["aov"] @ w_or_c - b["aov"] @ w_or_b,
         "结构效应 mix": aov_mix, "自身效应 within": aov_within},
    ])


def category_contribution(df: pd.DataFrame) -> pd.DataFrame:
    """各品类对 GMV 增量的贡献，以及它在总 UV 里的份额变化。"""
    g = category_totals(df)
    b = g[g.year == 2024].set_index("category")
    c = g[g.year == 2025].set_index("category")
    out = pd.DataFrame({
        "gmv_base": b["gmv"], "gmv_cur": c["gmv"],
        "uv_share_base": b["uv"] / b["uv"].sum(),
        "uv_share_cur": c["uv"] / c["uv"].sum(),
        "cvr_base": b["cvr"], "cvr_cur": c["cvr"],
        "aov_base": b["aov"], "aov_cur": c["aov"],
    })
    out["gmv_delta"] = out["gmv_cur"] - out["gmv_base"]
    out["contrib"] = out["gmv_delta"] / out["gmv_delta"].sum()
    out["uv_share_chg_pp"] = (out["uv_share_cur"] - out["uv_share_base"]) * 100
    return out.sort_values("gmv_delta", ascending=False)


def stockout_tradeoff(df: pd.DataFrame, cost_ratio: float = 0.6,
                      service_levels=(0.80, 0.88, 0.95)) -> pd.DataFrame:
    """备货与缺货率的换算（正态近似）。

    备货量 Q = μ·(1 + k·CV)，k 由目标缺货率反推（k = Φ⁻¹(1-缺货率)），
    缺货率 = 1 - Φ(k)。CV 取各品类日订单量的变异系数。
    """
    from math import erf, sqrt

    def norm_cdf(x: float) -> float:
        return 0.5 * (1 + erf(x / sqrt(2)))

    def norm_ppf(p: float) -> float:
        lo, hi = -6.0, 6.0
        for _ in range(200):
            mid = (lo + hi) / 2
            if norm_cdf(mid) < p:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    cur = df[df.year == 2025]
    daily = cur.groupby(["category", "date"])["orders"].sum().reset_index()
    stats = daily.groupby("category")["orders"].agg(["mean", "std"]).reset_index()
    stats["cv"] = (stats["std"] / stats["mean"]).fillna(0)

    aov = cur.groupby("category")["aov"].mean()

    rows = []
    for level in service_levels:
        stockout = 1 - level
        k = norm_ppf(1 - stockout)
        qty = stats["mean"] * (1 + k * stats["cv"])
        value = (qty * aov.reindex(stats["category"]).to_numpy() * cost_ratio).sum()
        rows.append({
            "目标服务水平": level,
            "缺货率": stockout,
            "安全系数 k": k,
            "备货量指数": float((qty / stats["mean"]).mean()),
            "库存金额（万元）": float(value / 1e4),
        })
    return pd.DataFrame(rows)
