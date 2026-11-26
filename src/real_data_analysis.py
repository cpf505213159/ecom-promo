# -*- coding: utf-8 -*-
import json, pathlib, sys
try:
    import json, pathlib, pandas as pd
    ROOT=pathlib.Path(__file__).resolve().parents[1]; m={}
    o=pd.read_csv(ROOT/"data/real/online_retail_orders_sample.csv",parse_dates=["InvoiceDate"])
    o=o[o.Quantity>0]; o["month"]=o.InvoiceDate.dt.to_period("M").astype(str)
    inv=o.groupby("InvoiceNo").Revenue.sum()
    m["gmv"]=round(float(o.Revenue.sum()),2); m["orders"]=int(o.InvoiceNo.nunique()); m["aov"]=round(float(inv.mean()),2)
    mon=o.groupby("month").Revenue.sum()
    m["monthly_revenue"]={k:round(float(v),2) for k,v in mon.items()}
    m["top_country_share"]=round(float(o.groupby("Country").Revenue.sum().sort_values(ascending=False).iloc[0]/o.Revenue.sum()),4)
    print(json.dumps(m,ensure_ascii=False,indent=2))
    _root=pathlib.Path(__file__).resolve().parents[1]
    (_root/'outputs').mkdir(exist_ok=True)
    (_root/'reports').mkdir(exist_ok=True)
    (_root/'outputs/real_metrics.json').write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8')
    NOTES='''# 真实公开数据集分析概览\n\n本仓库附带真实公开数据集（见 data/real/SOURCES.md），运行 `python src/real_data_analysis.py` 复现以下真实数据统计：\n\n```json\n'+json.dumps(m,ensure_ascii=False,indent=2)+'\n```\n\n> data/ 与 outputs/metrics.json 的主结果为脱敏/仿真案例，用于稳定演示方法；本文件使用公开真实数据集验证方法可运行。'''
    (_root/'reports/real-data-notes.md').write_text(NOTES,encoding='utf-8')
    print(json.dumps(m,ensure_ascii=False,indent=2))
except Exception as e:
    print('REAL_ANALYSIS_ERROR', type(e).__name__, e); sys.exit(1)
