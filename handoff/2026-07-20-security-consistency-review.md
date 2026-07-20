# 安全与前后端一致性筛查 · Claude → Codex

日期：2026-07-20
这次是安全和一致性层面的具体问题点，都是找到的实际代码位置，不是臆测。只做上报，不修复。全部属于 `backend/` 范围，由 Codex 处理；第 3 条涉及前端 token 存储方式，我会一并关注但目前判断不需要马上改。

---

## 1. `aftersale/__init__.py` 里存在 SQL 拼接的危险模式（目前不可利用，但是隐患）

**位置**：`backend/database/repository/aftersale/__init__.py:690-693`

`q_distinct(col)` 用 f-string 把 `col` 直接拼进 `SELECT DISTINCT {col} FROM ... ORDER BY {col}` 再传给 `sa.text()`。当前调用处（697-700行）`col` 都是硬编码字符串，不接受外部输入，实际暂时不可被注入。但这是危险模式——以后一旦这个函数被复用来处理动态列名（比如某个新功能想让前端传字段名做筛选），会立刻变成 SQL 注入点。建议加白名单校验或改成参数化写法，防止未来"复用踩坑"。

## 2. CORS 配置依赖环境变量，本身未见问题但要留意生产配置

**位置**：`backend/app.py:50-54`

`CORS(app, origins=_cors_origins)`，默认值 `["http://localhost:5173", "file://"]`，没设 `supports_credentials=True`，代码本身没问题。风险点在于 `origins` 完全依赖环境变量 `CORS_ORIGINS`，如果生产环境不小心配成 `*` 或包含通配符会有风险。这是配置管理层面要注意的点，不是代码缺陷，提醒一下确保生产环境变量配置正确。

## 3. 前端 token 明文存 localStorage（现状说明，非要求立即改）

**位置**：`src/api/http.js:19, 33-35`

token 存 `localStorage.getItem('tmt_token')`，不是 httpOnly cookie，一旦有 XSS 就能被脚本窃取，代码里没有额外缓解措施（CSP 等）。这是很多前端项目的常见做法，改动成本较高（要重构鉴权机制），先记录现状，不建议现在动。

## 4. 权限码前后端不一致：`product:delete` 前端有定义，后端没有对应保护

**位置**：前端 `src/composables/usePermission.js:37` 定义了 `canDeleteProduct = can('product:delete')`，但后端全局搜索没有任何路由用 `'product:delete'` 做权限校验，也没有对应的产品删除接口。

**说明**：要么是产品删除功能前端已经预留了权限判断但后端接口还没做，要么是这个权限码已经废弃但前端没清理。麻烦 Codex 确认一下产品删除功能的实际状态，如果后端确实没有删除接口，这是个前后端预期不一致的地方，我这边可以把前端相应的权限判断也理清楚。

## 5. 接口权限校验：未发现遗漏

蓝图级统一走 `before_request(make_blueprint_guard(...))`，抽查的几个上传/关联接口都有覆盖，这条没问题，列出来只是说明已检查过。

## 6. 文件上传缺少大小限制，`upload_cover_image` 缺少类型白名单校验

- **`backend/routes/product/resource.py:231-258` `presign_upload`**：只校验扩展名在 `UPLOAD_EXT_MAP` 白名单内，没有文件大小限制。因为是 OSS 预签名直传（服务器不经手），没有 `MAX_CONTENT_LENGTH` 或大小上限校验，存在超大文件被直传导致 OSS 存储/流量被滥用的风险。

- **`backend/routes/product/finished.py:156-177` `upload_cover_image`**：只用正则 `data:image/(\w+);base64,(.+)` 校验格式，`ext` 直接取自客户端声明的 MIME 子类型，没有校验是否在图片类型白名单内（png/jpg/webp 等），也没有校验 `img_bytes` 大小。理论上可以上传任意扩展名（比如 `.svg`、`.html`）到 OSS，且没有大小限制。

**建议**：这两处优先级不算最高（不是暴露给公网匿名用户，需要登录+权限才能调用），但既然是"内部系统对外挂了 web 端"，建议至少加个文件大小上限（比如 10MB）和白名单校验 `ext` 而不是直接信任客户端声明的 MIME 类型。

---

以上 6 条，**第1条（SQL拼接隐患）和第6条（上传缺校验）建议优先看一下**，第4条需要 Codex 确认业务状态后回复，其余记录在案即可。
