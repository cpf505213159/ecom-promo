"""两期大促的品类级流量与成交数据（同构数据，含真值参数）。

数据结构对齐生产表：一行 = 一个品类 × 一天，字段是当日去重 UV、下单转化率、客单价。
两期分别是 2024 与 2025 的双 11 周期（11-01 ~ 11-11）。

生成时埋入四个可分解的效应，方便后面验证「归因能不能拆对」：
    1. 客流效应：整体 UV 增长，且各品类增速不同（结构变化）
    2. 转化效应：大促期间 CVR 抬升，抬升幅度按品类不同
    3. 客单效应：凑单导致 AOV 抬升
    4. 结构效应：某几个品类 UV 占比明显变化（新品/新流量入口）

真实数据里拿不到「真值」，这里可以——所以能回答「三层分解能不能把增幅拆干净」。
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 20251112
CATEGORIES = ["女装", "男装", "美妆", "食品", "母婴", "数码", "家居", "运动"]
N_DAYS = 11

# 基线（2024 双 11 周期，日均）
BASE_UV = np.array([820_000, 610_000, 540_000, 700_000, 320_000, 260_000, 300_000, 240_000])
BASE_CVR = np.array([0.031, 0.028, 0.038, 0.052, 0.041, 0.012, 0.019, 0.026])
BASE_AOV = np.array([186, 168, 232, 96, 214, 1_450, 320, 178])

# 2025 的变化（这是「真值」，分解要能还原它）
UV_GROWTH = np.array([0.12, 0.08, 0.35, 0.18, 0.05, 0.62, 0.15, 0.22])   # 数码与美妆靠新品拉动
CVR_LIFT = np.array([0.004, 0.003, 0.009, 0.006, 0.004, 0.002, 0.003, 0.005])
AOV_LIFT = np.array([22, 18, 31, 9, 26, 210, 38, 20])


def build(seed: int = SEED) -> tuple[pd.DataFrame, dict]:
    rng = np.random.default_rng(seed)
    rows = []

    for year, tag in [(2024, "base"), (2025, "cur")]:
        # 大促日内节奏：11-10/11-11 是峰值，前面逐日抬升
        day_factor = np.array([0.72, 0.78, 0.82, 0.85, 0.88, 0.95, 1.02, 1.05, 1.10, 1.35, 1.48])

        for i, cat in enumerate(CATEGORIES):
            uv = BASE_UV[i] * (1 + (UV_GROWTH[i] if tag == "cur" else 0))
            cvr = BASE_CVR[i] + (CVR_LIFT[i] if tag == "cur" else 0)
            aov = BASE_AOV[i] + (AOV_LIFT[i] if tag == "cur" else 0)

            for d in range(N_DAYS):
                noise = rng.lognormal(0, 0.05)
                rows.append({
                    "year": year,
                    "promo": "双11",
                    "date": pd.Timestamp(f"{year}-11-{d+1:02d}"),
                    "day_index": d,
                    "category": cat,
                    "uv": round(uv * day_factor[d] * noise, 0),
                    "cvr": round(cvr * (0.94 + 0.12 * day_factor[d] / 1.48), 5),
                    "aov": round(aov * (0.97 + 0.06 * day_factor[d] / 1.48), 2),
                })

    df = pd.DataFrame(rows)
    df["orders"] = np.round(df["uv"] * df["cvr"], 0)
    df["gmv"] = np.round(df["orders"] * df["aov"], 2)

    truth = {
        "seed": SEED,
        "categories": CATEGORIES,
        "uv_growth": UV_GROWTH.tolist(),
        "cvr_lift": CVR_LIFT.tolist(),
        "aov_lift": AOV_LIFT.tolist(),
        "note": "uv_growth 是各品类 UV 同比增速，也是结构变化的来源",
    }
    return df, truth


def save(df: pd.DataFrame, truth: dict, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / "promo_category_daily.csv", index=False, encoding="utf-8")
    (out / "ground_truth.json").write_text(
        json.dumps(truth, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    df, truth = build()
    save(df, truth, root / "outputs")
    g = df.groupby("year")["gmv"].sum()
    print(f"{len(df)} 行｜2024 GMV {g[2024]:,.0f}｜2025 GMV {g[2025]:,.0f}"
          f"｜同比 {g[2025]/g[2024]-1:+.1%}")
