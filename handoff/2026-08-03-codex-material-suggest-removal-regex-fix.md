# 移除物料候选接口并补齐 MySQL 正则错误码，交接 Claude

日期：2026-08-03  
状态：代码完成、本地验证通过、**未部署**

## 变更

- 前端已撤销候选面板且全仓库无调用方，因此删除：
  - `GET /api/material/suggest`
  - `MaterialService.suggest()`
  - `MaterialRepository.suggest()`
  - 对应接口文档与测试
- 正则筛选功能保留不变。
- MySQL ICU 正则错误码范围由 `3690–3699` 修正为 `3685–3699`，并继续兼容旧错误码 1139。
- 新增回归测试：模拟 MySQL 3685，确认路由 rollback 后返回 HTTP 400
  `{success:false,message:"正则表达式无效"}`，不会成为 500。

## 验证

- Python 可接受的 `[[:nosuch:]]` 会进入数据库层；模拟 MySQL 3685 已验证被正确转换。
- Python 自身拒绝的 `[` 仍在查询前返回 400。
- 合法正则、默认 LIKE、旧 keyword 行为均由原有测试继续覆盖。
- 全量 pytest、compileall、diff check 通过。

## 部署

无数据库迁移。同步三个运行时代码文件并 reload 后，验证：

1. `GET /api/material/suggest` 返回 404（接口已正式撤销）。
2. `match_mode=regex&code=^14ME` 正常。
3. `match_mode=regex&code=[[:nosuch:]]` 返回 400，不写 500 traceback。
