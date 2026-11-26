# Online Retail（UCI Machine Learning Repository, Dataset 352）

- 来源: https://archive.ics.uci.edu/static/public/352/online+retail.zip
- 许可: 公开数据集（UCI，引用 Chen, Sain & Guo, 2012），仅用于学习/演示，请遵循 UCI 使用条款。
- 内容: 一家英国在线零售商 2010-12-01 ~ 2011-12-09 的真实交易明细（541,909 行原始）。
- 字段: InvoiceNo(发票号)、StockCode(商品编码)、Description(商品名)、Quantity(数量)、InvoiceDate(时间)、UnitPrice(单价,英镑)、CustomerID(客户ID)、Country(国家)、Revenue=Quantity*UnitPrice。
- 本仓库样本: online_retail_orders_sample.csv 为剔除非注册客户、按时间排序后随机抽取的 60,000 行明细（random_state=42）。
