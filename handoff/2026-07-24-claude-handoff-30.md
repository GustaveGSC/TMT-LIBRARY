# Codex → Claude 交接：财务导入工作流 A 批后端

日期：2026-07-24

提交：`7c77fd6 fix(shipping): invalidate options after customer mapping`

## 后端变更

- `POST /api/shipping/finance-customer-aliases/mapping` 保存成功后立即调用
  `_invalidate_chart_options_cache()`。
- 接口路径、请求体、响应结构和权限均未变化。
- 保存客户映射不会触发 `resolve_all` 或任何成品组合重算。

## 自动化验证

- API 测试确认：
  - `shipping:view` 仍为 403；
  - `shipping:edit` 保存成功；
  - 每次成功保存只触发一次 chart-options 缓存失效；
  - 保存路径不会调用 `resolve_all`。
- 数据测试确认：
  - 将已有客户从 `pending` 改为 `export`；
  - 下一次 `chart-data` 查询立即把该客户计入外贸结果；
  - 全程没有重算派生组合。
- 全量后端 pytest、compileall、git diff --check 均通过。

## 部署

- 无数据库迁移；
- 同步 2 个运行时 Python 文件后 reload；
- 实测保存映射后重新请求 chart-options，国家/品牌筛选项应立即刷新。

## Claude 前端衔接

现在可以完成 A 批前端：

1. “外贸客户匹配”改为“客户匹配”；
2. 增加“保存后立即生效，无需重建成品组合”说明；
3. “刷新全局数据”改为“重建全部成品组合（高级）”；
4. 将其移到数据配置/高级操作区域，不再作为日常导入流程顶部常驻动作。

注意文案应精确区分：

- 修改客户四态、国家、品牌：保存立即生效；
- 重导历史数据补客户简称：B 批上线前，既有订单派生 alias 仍可能需要重建；
- 新导入订单：导入过程已自动生成派生组合。
