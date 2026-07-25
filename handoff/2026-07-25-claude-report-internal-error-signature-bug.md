# 发现：C 批 report_internal_error() 调用签名不匹配，导致失败清理路径静默崩溃

日期：2026-07-25
发现方式：审查生产 gunicorn 日志时看到此前 resolve_all 门禁测试留下的一条历史错误：

```
File "/opt/tmt-library/backend/services/shipping/__init__.py", line 1032, in _run_staged_resolve
    report_internal_error(
TypeError: report_internal_error() got multiple values for argument 'context'
```

## 根因

`backend/error_handling.py` 里的真实签名：

```python
def report_internal_error(context: str) -> str:
    """记录当前异常的完整堆栈，返回可安全展示的短错误编号。"""
    error_id = secrets.token_hex(6)
    current_app.logger.exception('%s [error_id=%s]', context, error_id)
    return error_id
```

只接受一个位置参数 `context`（字符串）。内部用 `logger.exception()` 会自动从
`sys.exc_info()` 取当前正在处理的异常堆栈，不需要额外传入异常对象。

但 `backend/services/shipping/__init__.py` 的 `_run_staged_resolve()` 里三处调用都写成：

```python
report_internal_error(
    exc,
    context=f'...',
)
```

`exc` 被当成第一个位置参数填进了 `context` 形参，随后关键字参数 `context=...` 又想赋值给同一个
形参，Python 直接抛 `TypeError: got multiple values for argument 'context'`。三处调用（行号以
当前 master 为准）：

- 1006-1009：cutover 成功后，清理 staging 失败时；
- 1022-1025：cleanup_pending 场景下，更新任务诊断状态失败时；
- 1032-1035：**最终异常处理块里，cleanup_resolve_staging() 本身失败时**。

## 实际影响：解释了我之前报告里的"次生问题"

我在 `handoff/2026-07-25-claude-staging-cutover-gate-test-report.md` 里记录过：resolve_all 因全表
DELETE 超时失败后，`shipping_order_finished_staging`/`shipping_resolve_target` 两张表残留了约
69万+25万行，没有被立即清理，当时归因为"清理路径大概率撞上了同样的连接/资源问题"。

现在有了确切证据：`_run_staged_resolve()` 的 `except Exception:` 块（line 1027起）确实调用了
`cleanup_resolve_staging(task_id)`，如果这次清理本身也失败（大概率，因为紧跟在一次连接超时/断连
之后），进入 line 1030-1035 的 `except Exception as cleanup_exc:` 分支，**这里对
`report_internal_error()` 的调用本身就会因签名不匹配立即抛出新的 `TypeError`**，把原本应该继续
往外传播的 cleanup 失败异常替换成了一个新的、无关的 TypeError。这个新异常再往外传播，被路由层的
`except Exception: _finish_task(..., 'error', ...)` 兜底捕获，最终用户看到的还是标准的"任务执行
失败"提示，但服务端日志里记录的是这个签名错误，而不是真正导致 `cleanup_resolve_staging()` 失败的
根因——诊断信息被这个 bug 吃掉了。

## 影响范围

不影响数据安全性（本身发生在已经进入失败清理分支之后，不会导致 DELETE/INSERT 被重复执行或数据
损坏），但会让"清理失败"这类次生故障失去可观测性，且这三处如果被触发，本来应该记录一条带完整
堆栈的诊断日志，现在只会记录一条内容为"got multiple values for argument"的噪音日志，掩盖真实原因。

## 建议修复

三处调用改成只传一个位置/关键字参数：

```python
report_internal_error(
    context=f'清理重算暂存数据失败 task_id={task_id}',
)
```

`exc`/`cleanup_exc` 变量不需要传——`report_internal_error()` 在 `except` 块内部调用时，
`logger.exception()` 自动带出当前正在处理的异常堆栈。如果 Codex 认为需要在日志文案里体现具体
异常类型/消息，可以显式拼进 `context` 字符串（如 `f'...: {exc}'`），但不能作为独立参数传给
`report_internal_error()`。

补一个单元测试防止再退化：直接调用这三个分支对应的失败路径，断言不抛出 `TypeError`，日志里能看到
`error_id`。

这个连带 resolve_all 的 rename 型 cutover 重新设计一起修，不需要单独紧急发布——反正 resolve_all
入口现在已经被 fail-fast 503 挡住了，这条失败清理路径短期内不会被真实触发；但既然发现了就一并记录，
避免以后 C 批重新开放时又踩一次。
