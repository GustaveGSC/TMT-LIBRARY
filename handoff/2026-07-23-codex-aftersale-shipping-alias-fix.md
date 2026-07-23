# 售后发货简称自动匹配故障修复交接

日期：2026-07-23

## 修复内容

提交：`30f7b02 fix(aftersale): restore shipping alias semantic fallback`

修复 `AftersaleRepository.match_shipping_alias()` 的同一根因链：

- 新增 `semantic=True` 参数，并由已有上游 `suggest_product(..., semantic=...)` 原样透传。
- 修复函数内引用未定义 `semantic` 导致语义分支始终失败的问题。
- 当关键词和语义均无候选时，显式返回 `(None, 0.0)`，不再访问空 `top_candidates[0]`。
- 语义模型分支异常不再 `except Exception: pass` 静默吞掉，改用 `report_internal_error('售后发货简称语义匹配失败')` 记录完整 traceback 和错误编号，同时保持关键词降级流程可用。

Web 现有调用传 `semantic=false` 时仍跳过服务端模型；明确启用语义的调用才执行语义兜底，没有改变调用方的开关语义。

## 测试

新增 `backend/tests/test_aftersale_shipping_alias.py`，覆盖：

1. 无关键词且禁用语义时安全返回无匹配；
2. 无关键词但启用语义时按向量相似度命中；
3. 关键词并列时按 seller remark 与简称名称覆盖度决胜；
4. 模型异常被记录并安全降级，不再抛未处理异常。

提交后全量：140 passed；`compileall`、`git diff --check` 通过。

## Claude 审查与部署

建议先独立审查、合并并部署本提交，再处理 RD cost 权限提交：

1. 上传 `backend/database/repository/aftersale/__init__.py`；
2. reload gunicorn；
3. 检查延迟日志、master PID、`/health`、`/ready`；
4. 用一条无关键词命中的售后物料触发建议流程，确认不再出现 `top_candidates[0] IndexError`；
5. 如生产服务端语义模型未安装/未加载，允许安全返回无匹配，但不应产生未处理 500。

无数据库迁移、无接口结构变化。
