# 深度登记 采购三方勾稽报告

- 规模：中型
- 核心规则：采购、分批验收和合并发票按货号与税率分组，数量和金额使用 Decimal 守恒。
- 使用者与工作流：应付会计导入三类单据，映射主数据，核对数量税额，多对多匹配并导出差异。

## 功能模块

| 模块 | 使用者动作 | 入口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 单据采信 | 导入三类单据并隔离冲突 | POST /api/documents/import | `app/modules/m1_documents/parser.py` `app/modules/m1_documents/money.py` | `tests/test_m1_documents.py` |
| M2 主数据映射 | 归一货号与旧字段 | POST /api/master/resolve | `app/modules/m2_master/aliases.py` `app/modules/m2_master/evolve.py` | `tests/test_m2_master.py` |
| M3 数量勾稽 | 统一包装单位并核对未到量 | POST /api/quantity/match | `app/modules/m3_quantity/units.py` `app/modules/m3_quantity/match.py` | `tests/test_m3_quantity.py` |
| M4 税额核验 | 重算净额、税额与含税额 | POST /api/tax/check | `app/modules/m4_tax/calculate.py` `app/modules/m4_tax/verify.py` | `tests/test_m4_tax.py` |
| M5 多对多匹配 | 在相同货号税率内组合匹配 | POST /api/matches/solve | `app/modules/m5_matching/candidates.py` `app/modules/m5_matching/solver.py` | `tests/test_m5_matching.py` |
| M6 差异批次 | 核对金额守恒并导出差异 | POST /api/reconcile | `app/modules/m6_batches/compare.py` `app/modules/m6_batches/exporter.py` | `tests/test_m6_batches.py` |

## 陷阱登记

| TRAP | 现象 | 朴素实现会怎样 | 本项目处理 | 处理位置 | 测试 |
|---|---|---|---|---|---|
| TRAP-05 | 单据缺少字段 | 静默补空进入匹配 | 隔离并保留行号 | `app/modules/m1_documents/parser.py` | `tests/test_m1_documents.py::test_missing_field_quarantined` |
| TRAP-06 | 金额带千分位 | 直接转换失败 | 清理分隔符后使用 Decimal | `app/modules/m1_documents/money.py` | `tests/test_m1_documents.py::test_thousands_amount_uses_decimal` |
| TRAP-07 | 空值哨兵 | 被当作零金额 | 空值集合统一拒绝 | `app/modules/m1_documents/money.py` | `tests/test_m1_documents.py::test_missing_field_quarantined` |
| TRAP-08 | 供应商编码前导零 | 转整数后主数据失配 | 编码始终按字符串保形 | `app/modules/m2_master/aliases.py` | `tests/test_m2_master.py::test_supplier_code_preserves_leading_zero` |
| TRAP-10 | 税额浮点尾差 | 分项和总额差一分 | Decimal 半入到分 | `app/modules/m4_tax/calculate.py` | `tests/test_m4_tax.py::test_half_up_to_cent` |
| TRAP-14 | 重复单号值冲突 | 后写覆盖金额 | 单独隔离冲突版本 | `app/modules/m1_documents/parser.py` | `tests/test_m1_documents.py::test_conflicting_duplicate_detected` |
| TRAP-17 | 旧列名仍在使用 | 新版读取报错 | 受控字段迁移并报告冲突 | `app/modules/m2_master/evolve.py` | `tests/test_m2_master.py::test_old_columns_migrate` |
| TRAP-19 | 组合候选顺序变化 | 匹配结果随输入顺序变化 | 按差额、数量与编号稳定择一 | `app/modules/m5_matching/solver.py` | `tests/test_m5_matching.py::test_choice_is_order_independent` |
| TRAP-23 | 相邻税率边界 | 不同税率金额互相抵消 | 货号与税率共同分组 | `app/modules/m4_tax/verify.py` | `tests/test_m4_tax.py::test_different_tax_rates_never_offset` |
| TRAP-26 | 同批重复执行 | 重复新增对账结果 | 输入摘要作为运行唯一键 | `app/store.py` | `tests/test_m6_batches.py::test_idempotent_record` |
| TRAP-27 | 关账后更正单改旧账 | 重开批次导致审计数字变化 | 关账快照只追加不覆写，差额进差异批次 | `app/store.py` `app/modules/m6_batches/corrections.py` | `tests/test_corrections.py::test_closed_batch_snapshot_never_rewritten` |
| TRAP-28 | 更正单原值与关账数不符 | 采信后差额失真 | 原值与关账快照逐键比对，不符按 CLOSED_BATCH_MISMATCH 隔离 | `app/modules/m1_documents/corrections.py` | `tests/test_corrections.py::test_old_tax_must_match_closing_snapshot` |
| TRAP-29 | 重跑同一张更正单 | 税额差额重复入账 | correction_no 唯一约束 + 已入账跳过 | `app/store.py` `app/modules/m6_batches/corrections.py` | `tests/test_corrections.py::test_rerun_same_correction_does_not_double_post` |
| TRAP-30 | 调低税额取绝对值 | 少缴税款方向反转 | 差额带符号（调低为负），Decimal 半入到分 | `app/modules/m4_tax/adjustment.py` | `tests/test_corrections.py::test_downward_tax_delta_is_signed` |
| TRAP-31 | 调整找不到原批次 | 差异无法解释来源 | source_run_id 关联关账批次并在追溯面板展示 | `app/modules/m6_batches/corrections.py` | `tests/test_corrections.py::test_trace_finds_original_batch` |

## 对账规则

- 采购数量 = 净验收数量 + 未到数量。
- 净验收含税额 = 已开票含税额 + 未开票金额 + 已解释差异。
- 不同税率的行不可相互抵消。

## 关账后税额更正流程

1. M1 单据采信 `POST /api/documents/corrections/accept`：校验更正单字段、引用的关账批次是否存在、原税额是否等于关账快照；失败保留行号与原因码（UNKNOWN_REFERENCE / CLOSED_BATCH_MISMATCH）。
2. M4 税额核验 `POST /api/tax/adjustment-delta`：按 Decimal 半入到分计算带符号差额（new_tax − old_tax），调低为负。
3. M6 差异批次 `POST /api/batches/corrections`：差额以 TAX_ADJUSTMENT 原因码入差异批次并关联 source_run_id；原关账批次快照不变。`GET /api/batches/corrections` 按原批次追溯调整。
4. 幂等：输入摘要决定 run_id，correction_no 唯一约束保证重跑不重复入账。
5. 关账批次登记：`POST /api/batches/closed` 冻结税额、含税额与按 business_key 的明细快照。

## 已知不覆盖

- 不处理外币汇兑，样例与输出均为人民币。

