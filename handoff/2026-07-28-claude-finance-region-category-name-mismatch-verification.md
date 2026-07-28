# 财务端"全球区域"人工映射对齐：生产验证通过并已上线

日期：2026-07-28

## 结论

Codex 的实现（8d64dd5）审查通过：把"地域/全球区域/品牌"的财务映射识别收敛成
`_finance_mapping_field_for_category()` 单一函数，`get_chart_options`、`get_chart_data`
分组与筛选、`get_finance_map_breakdown` 三处调用点全部改用该函数，不再各自维护一份硬编码
判断。测试新增了"全球区域"命名场景的覆盖（chart-options 的 value_kind、chart-data 的
tag_names 筛选、地图批量细分），同时保留了发货端仍走标签 id 的验证。已合并部署，真实 HTTP
验证通过。

## 部署

无迁移，同步 `database/repository/shipping/__init__.py` 一个文件，MD5 核对一致，
`systemctl reload gunicorn`，master PID 未变，无崩溃重启，`/health`/`/ready` 正常。

## 真实 HTTP 验证

`GET /api/shipping/chart-options?source=finance`：

| 分类 | category_id | value_kind |
|---|---|---|
| 全球区域 | 3 | `name`（修复前是 `id`，本次验证已生效） |
| 品牌 | 2 | `name`（上一轮已修复，本次确认未回归） |
| 学习桌尺寸 | 1 | `id`（非财务映射维度，保持不变） |
| 学习桌台面材料 | 4 | `id`（非财务映射维度，保持不变） |

## 当前状态

财务端"地域/品牌"筛选选项与实际维度数据不一致的问题（用户最初反馈的"左侧筛选里的品牌内容和
维度里的品牌不对等"）已完整解决，两个维度均已对齐真实客户映射数据，无已知遗留问题。
