# 采购三方勾稽报告

面向真实数据复核的中型数据工程工具，包含六个可独立调用的业务模块。规则、失败原因与证据字段见 docs/DATA-DICTIONARY.md，陷阱和测试映射见 docs/DEPTH.md。

## 启动

docker compose up --build

浏览器访问 http://localhost:18218。测试：docker compose exec -T app pytest -q

## 模块

- M1 单据采信：页面 /documents，接口 /api/documents/import
- M2 主数据映射：页面 /master，接口 /api/master/resolve
- M3 数量勾稽：页面 /quantity，接口 /api/quantity/match
- M4 税额核验：页面 /tax，接口 /api/tax/check
- M5 多对多匹配：页面 /matching，接口 /api/matches/solve
- M6 差异批次：页面 /batches，接口 /api/reconcile

## 运行规则

同一输入内容生成相同运行标识，重复执行复用已有批次。隔离记录包含原因码、原始行号与原值；业务导出只保留一份证据清单。

## 关账后税额更正

月结关账后收到供应商发票更正单时，原批次审计数字保持不变，更正税额差额进入差异批次：

1. `POST /api/batches/closed` 登记关账快照（税额、含税额、按业务键的明细）。
2. `POST /api/documents/corrections/accept` 采信更正单：引用批次不存在或原税额与关账快照不一致即隔离。
3. `POST /api/tax/adjustment-delta` 计算新旧税额带符号差额（调低为负，Decimal 半入到分）。
4. `POST /api/batches/corrections` 将差额以 TAX_ADJUSTMENT 入差异批次并关联原批次；重跑同一张更正单不重复入账。
5. `GET /api/batches/corrections` 与 /batches 页面的“税额更正追溯”面板可从调整查到对应原批次。

样例：`sample_data/tax_corrections.json`。

