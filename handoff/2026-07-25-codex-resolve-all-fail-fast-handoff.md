# resolve_all 临时 fail-fast 交接

日期：2026-07-25  
状态：后端补丁完成，未部署

## 背景

C 批门禁确认全量 staging 构建的数据安全性成立，但 692,003 行正式表的无条件 DELETE 超过
MySQL `read_timeout=30`，导致全量重建约九分钟后失败。rename 型 cutover 完成前，生产接口必须
立即关闭，不能只依赖前端禁用按钮。

## 改动

- `POST /api/shipping/resolve-all` 默认立即返回 HTTP 503：
  `全量重建正在维护优化，当前暂不可用`。
- 拦截点位于 UUID、任务、租约、线程和 staging 创建之前，不产生任何后台负载或数据库垃圾。
- 只有显式配置 `ALLOW_FULL_RESOLVE=true`（也接受 `1/yes/on`）才放行，供后续快照/staging
  门禁使用。
- `POST /api/shipping/resolve`（局部 stale 重算）、日常导入和任务查询/取消不受影响。

## 验证与部署

- 自动化测试覆盖默认关闭且不会调用 `_create_mutation_task`。
- 部署时不要在生产 `.env` 增加 `ALLOW_FULL_RESOLVE=true`；变量缺省即关闭。
- 与 Claude 已提交的前端禁用改动一起部署。后端需 reload，前端部署完整 `dist-web`。
- reload 后直接调用 `POST /api/shipping/resolve-all`，应立即得到标准 503，并确认
  `shipping_task`、target、staging 均没有新增记录。

