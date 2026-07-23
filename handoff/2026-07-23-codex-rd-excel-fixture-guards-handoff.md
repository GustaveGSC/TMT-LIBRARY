# RD Excel 纯逻辑 fixture 护栏交接

日期：2026-07-23

## 本批范围

本批只新增 `backend/tests/test_rd_excel_logic.py`，没有修改运行时代码、接口、数据库或前端。

新增四组无生产依赖的 fixture：

1. `_compare_bom`：用临时生成的 before/after BOM 验证通用变更生成“取消 + 新增”两行、版本 A01 → A02、规格版本同步和父件图号。
2. ECR round-trip：调用 `_build_ecr_xlsx` 生成内存工作簿，再由 `_parse_ecr_rows_xlsx` 解析，精确核对表单字段和明细字段。
3. ECN 工作簿：调用 `_build_ecn_xlsx` 后重新打开，核对基本信息、勾选文本和明细列布局。
4. PDM 构建器：验证 `_ptb_build_erp_data` 的固定值/列映射，以及 `_ptb_build_bom_data` 的三级父子关系、数量转换和无效数量回退。

fixture 使用 `tmp_path`、`io.BytesIO` 和内存/临时 openpyxl 工作簿，不读取生产模板、不访问数据库或网络。

## 提交

- `57ac4c2 test(rd): characterize Excel transformation logic`

分支：`codex/rd-excel-fixture-guards`

## 验证结果

- `python -m pytest backend/tests/test_rd_excel_logic.py -q`：4 passed
- `python -m pytest backend/tests -q`：135 passed
- `python -m compileall -q backend`：通过
- `python -m alembic -c alembic.ini heads`：`20260721_04 (head)`
- `git diff --check`：通过

## 审查提示

- PDM 当前规则不是所有单据类型都强制覆盖：当“工单单据类型”或“请购单单据类型”源列存在时保留源值，只有源列不存在时才填 5101/3101；“工作中心”和“生产部门”则无论源列是否存在都固定为 1001/100802。测试锁定了这一现有差异。
- ECR 现有生成/解析语义中，数量变更文本由生成器写入第 10 列，解析后体现在 `substitution`，`change_kind` 为空。测试按现状记录，没有在护栏批次顺手调整契约。
- 本批纯测试，无需部署或 reload；合并后跑全量测试即可。

## 下一步建议

护栏就绪后，可以进入审计第 3 批，但仍应分成两个独立运行时代码批次：

1. 先抽 PDM 转 BOM 纯逻辑到 `services/rd/pdm_to_bom.py`，范围较小，由本批 PDM fixture 保护。
2. 稳定部署后，再抽 ECR/ECN/BOM 到 `services/rd/change_documents.py`；该部分体积和格式逻辑更大，不与 PDM 同批。

两批均先只移动纯函数，路由暂留原 Blueprint，URL、方法、上传校验和错误映射不得变化。
