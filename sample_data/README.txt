样例数据覆盖正常记录、空值、重复业务键、相同键值冲突、边界值和截断输入。

tax_corrections.json：关账后供应商发票更正单样例。先经 POST /api/batches/closed 登记 run_id 为 procurematch-rules-1-closed01 的关账快照，再提交更正单；两条更正均为税额调低，差额以负值进入差异批次。
