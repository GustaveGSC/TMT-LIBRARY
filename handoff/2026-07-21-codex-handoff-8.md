# 交接说明 · Claude → Codex（第八轮，按风险分批：本批 P1+P2 三项）

日期：2026-07-21
依赖锁定审计（`eb01e02`）已合并，同步到服务器（不涉及运行时代码，未 reload）。这一批按你建议的顺序处理三项，Cookie/token 改造、P3 重构、Git 历史清理不在本批，分别单独排期。

---

## 任务一：P1 原始异常信息泄露

后端多处把原始异常文本直接返回给客户端，可能带出文件路径/SQL/存储细节。建议：服务端记录完整异常日志（含 traceback），返回给客户端的改成稳定的通用错误信息 + 一个追踪 ID（方便你在日志里定位对应请求）。范围排查一下大概涉及哪些文件（之前零散看到 `routes/product/resource.py` 的 `f'生成签名失败：{str(e)}'` 这类写法，估计不止一处），统一处理方式即可，不需要逐条列。

## 任务二：P1 数据库 readiness 健康检查

`/health` 目前只说明 Flask 进程存活，不检查数据库连接，无法区分"进程活着但库连不上"这种情况。建议区分 liveness（现在这个）和 readiness（新增，实际探测一次数据库连接，比如 `SELECT 1`），如果有部署/监控脚本依赖 `/health` 语义，确认一下改动会不会影响现有调用方（目前没有专门的监控系统，风险应该不大，但麻烦确认一下）。

## 任务三：P2 售后 SQL 拼接隐患

`backend/database/repository/aftersale/__init__.py` 里 `q_distinct(col)` 函数用 f-string 把 `col` 直接拼进 `SELECT DISTINCT {col} FROM ... ORDER BY {col}` 再传给 `sa.text()`。目前调用处 `col` 都是硬编码字符串，不接受外部输入，暂时不可利用，但这个模式本身危险——以后一旦复用来处理动态列名就会变成 SQL 注入点。改成白名单校验或者用 SQLAlchemy 列对象代替字符串拼接。

## 顺手清理（不算单独任务，跟手改一下）

- `backend/seed_permissions.py` 里的 `("product:delete", "删除产品记录")` 这条种子数据请删掉——产品决策已确认：**不支持删除成品记录**。前端这边未使用的 `canDeleteProduct`、权限码注释、文档示例代码我已经清理并部署（`.claude/claude.md`、`usePermission.js`）。如果生产数据库里已经有角色被授予了这个权限码，麻烦一并检查要不要清掉授权记录。

## 验证范围（照例）

`python -m pytest` + `python -m compileall -q backend` + `git diff --check`，独立 worktree/分支，部署我这边执行，完成后照例写交接文档。
