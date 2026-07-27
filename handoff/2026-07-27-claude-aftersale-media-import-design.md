# 售后图片/视频导入功能设计（交接 Codex，未实现）

> 2026-07-27 修订：吸收审查意见，修正 presign 并发 seq 冲突、replace 删除时序、confirm 信任
> 客户端输入、订单号/key 规范化、清理失败可追踪、media-flags 改 POST 六项问题。原始版本的
> OSS 直传/批量 flags/展开懒加载/不建外键方向审查确认无需改动。

## 需求回顾

1. 用户在本地新建以**售后订单号**命名的文件夹，内部放图片/视频，整体导入；导入时文件按订单号规则重新命名。
2. 导入**不要求**订单号已存在于当前售后订单目录（售后数据可能晚于媒体到达）；但如果该订单号**已经导入过媒体**，需要先让用户看到已有内容再确认是否继续（跳过/追加/替换）。
3. 售后数据表格里，有媒体的订单在展开行里能看到图片/视频。

## 数据模型（新表）

```
aftersale_case_media
  id BIGINT PK
  order_no VARCHAR(100) NOT NULL      # 不建 FK！导入时售后单可能还不存在，靠 order_no 字符串在查询时关联，
                                       # 而不是外键约束——否则订单不存在时无法导入，违反需求2
  file_type VARCHAR(20)               # image | video
  original_filename VARCHAR(300)      # 用户本地原始文件名，仅展示用途
  stored_filename VARCHAR(300)        # 重命名后的文件名（见命名规则）
  seq INT NOT NULL                    # 该订单内的序号，追加/替换都靠这列算下一个号，不解析文件名字符串
  oss_url VARCHAR(1000) NOT NULL
  storage_key VARCHAR(500) NOT NULL UNIQUE   # 唯一约束：防止两次 confirm 误写同一个 key 的重复行
  file_size BIGINT
  sort_order INT DEFAULT 0
  uploaded_by INT FK→user SET NULL nullable
  created_at DATETIME
  # 索引：ix_aftersale_case_media_order_no（列表页批量查 has_media、展开行按 order_no 查详情都靠它）

aftersale_media_upload_session        # presign 发号即预留，不再是"只发号不落记录"
  id BIGINT PK
  session_token VARCHAR(64) UNIQUE NOT NULL   # 不可伪造的令牌（如 secrets.token_urlsafe），confirm 必须携带
  order_no VARCHAR(100) NOT NULL
  mode VARCHAR(20) NOT NULL           # append | replace，presign 时定，confirm 必须一致，不接受 confirm 时改写
  storage_key VARCHAR(500) NOT NULL UNIQUE
  stored_filename VARCHAR(300) NOT NULL
  seq INT NOT NULL
  file_type VARCHAR(20) NOT NULL
  declared_ext VARCHAR(10) NOT NULL
  declared_file_size BIGINT NOT NULL
  status VARCHAR(20) NOT NULL DEFAULT 'pending'   # pending | confirmed | expired
  expires_at DATETIME NOT NULL        # presign 时设 created_at + 1小时（对齐 OSS 签名 URL 的 3600s 有效期）
  created_at DATETIME
  # 索引：ix_media_upload_session_token, ix_media_upload_session_order_no
  # 过期/未 confirm 的 pending 会话可定期清理（连带清理孤儿 OSS 对象，见下）

aftersale_media_cleanup_failure       # replace 删除旧 OSS 对象失败时的可追踪记录，不静默吞掉
  id BIGINT PK
  order_no VARCHAR(100) NOT NULL
  storage_key VARCHAR(500) NOT NULL
  error_message VARCHAR(500)
  created_at DATETIME
  resolved_at DATETIME NULL           # 人工/补偿任务处理后回填
```

不建 `order_no` → `aftersale_case.ecommerce_order_no` 外键的原因：需求 2 明确"无需判断导入的文件夹订单号是否存在于当前售后订单目录"。媒体表和工单表通过 `order_no` 字符串做运行时关联，工单后续导入/确认时自动"接上"已存在的媒体，不需要回填。

**`seq` 并发分配靠 `aftersale_media_upload_session` 表的写入去重**，不是靠内存计数或"读 MAX(seq) 再 +1"这种存在竞态的算法：presign 阶段为每个文件插入一条 session 行（`storage_key` 唯一约束天然防止两次 presign 分配到同一个 key），下一个可用 `seq` 通过 `SELECT MAX(seq) FROM (该订单已有 aftersale_case_media 的 seq 以及该订单当前 pending 状态的 upload_session 的 seq 取并集) + 1` 计算，并在**同一事务**里把新的 session 行插入，用数据库行锁/唯一约束保证并发两次 presign 请求不会拿到同一个 seq（比如对 order_no 加 `SELECT ... FOR UPDATE` 或依赖 `storage_key` 唯一约束在极端情况下让第二个请求重试）。具体锁粒度由 Codex 按 MySQL 隔离级别选型，但**不能是"纯 Python 里算好 seq 直接返回"这种无锁方案**。

## 存储

沿用 `backend/storage/client.py` 的 OSS 客户端和 `product_resource` 的**预签名直传**模式（浏览器直接 PUT 到 OSS，不经服务器中转）——这一点是硬要求，不是可选优化：售后视频文件可能不小，如果走服务器中转 multipart 上传，会撞上 CLAUDE.md 里记录的"单 worker + CPU 密集任务占用心跳导致 gunicorn 看门狗 SIGKILL"的坑（虽然文件传输本身不是 CPU 密集，但大文件走 Flask 请求体读取仍会长时间占用唯一的 sync worker，阻塞其他所有请求）。

OSS key 规则：`tmt-library/aftersale-media/{order_no}/{stored_filename}`，独立于 `resources/{yyyymm}/...` 前缀，按订单号直接定位，方便后续按订单清理。

## 命名规则

`stored_filename = "{order_no}_{seq:03d}.{ext}"`，`ext` 取原文件扩展名小写。

- `seq` 起始值：
  - 全新订单（该 order_no 之前无记录）→ 从 `001` 开始；
  - **追加**模式 → 从该订单当前最大 `seq` + 1 继续，见上一节"并发分配"约束；
  - **替换**模式 → **confirm 成功后**才清空旧序号语义，presign 阶段仍从 `001` 开始编号新一批（旧记录此时还没删，只是新记录会在 confirm 里替换掉它们，见下方"replace 时序修正"）。
- 同批次内即使原文件名重复，`seq` 天然去重，不会冲突。

**订单号/扩展名/OSS key 规范化（白名单）**：
- `order_no`：只接受 `[A-Za-z0-9_-]{1,100}`，拒绝任何路径分隔符（`/`、`\`）、`..`、空白、控制字符——这是文件夹名直接来自用户本地文件系统，必须当成不可信输入处理，否则可以拼出跳出 `aftersale-media/` 前缀的 OSS key。
- `ext`：只接受 `UPLOAD_EXT_MAP` 白名单里的固定集合（`png/jpg/jpeg/webp/mp4/mov/webm`），大小写归一化为小写，不接受用户传入的原始扩展名字符串直接拼接进 key。
- 拼出 `storage_key` 前用同一个校验函数处理 `order_no`，非法字符直接拒绝该订单整批导入（返回给前端提示"订单号包含非法字符"），不是静默过滤。

## 支持的文件类型

复用 `backend/routes/product/resource.py` 里 `UPLOAD_EXT_MAP` 的图片/视频子集：`png/jpg/jpeg/webp` + `mp4/mov/webm`。文件夹内其它类型文件（如 `.DS_Store`、`Thumbs.db`、文档）直接跳过，不阻塞整单导入，导入结果里提示"已跳过 N 个不支持的文件"。

大小限制：建议复用 `upload_validation.py` 里现成的额度校验逻辑（`parse_declared_size`），是否需要为售后视频单独定一个比 `RESOURCE_UPLOAD_LIMIT` 更大的上限，由 Codex 按实际售后视频文件大小评估。

**关于文件内容校验的边界（明确声明，不是遗漏）**：OSS 直传是浏览器直接 PUT 到 OSS，服务器完全不经手文件内容，因此**后端无法读取真实文件头做 magic number 校验**。当前设计只能校验：扩展名（白名单）、前端声明的 `Content-Type`（写入 presign 的 `required_headers`，OSS 侧按此存储但不代表内容真实性）、前端声明的文件大小（`declared_file_size`，与 OSS 侧实际对象大小可能不完全一致，因为声明值来自前端 `File.size`，OSS 会记录真实上传字节数，如果两者需要强一致，可在 confirm 时用 `bucket.head_object` 查真实 `Content-Length` 校验，见下）。如果"必须确认上传的确实是合法图片/视频而不是改了后缀的任意文件"是硬安全要求，需要接入 OSS 上传回调（OSS callback）或后置的异步内容校验任务；本设计**默认不做真实内容嗅探**，只做扩展名+声明大小的边界校验，Codex 如果认为这条业务线需要更强的校验，请在实现前单独提出，不要自行默默加回调机制。

## 后端接口设计

权限沿用 `aftersale:view`（查看）/ `aftersale:edit`（导入写入），复用 `make_blueprint_guard` 模式，不新开权限码。

### 1. 预检查 `POST /api/aftersale/media/precheck`
```json
{ "order_nos": ["202410210001", "202410210002"] }
```
返回每个 order_no 当前已有媒体的摘要，供前端弹窗展示冲突：
```json
{
  "202410210001": {
    "exists": true, "count": 3,
    "files": [{"id":1,"filename":"202410210001_001.jpg","file_type":"image","oss_url":"...","created_at":"..."}]
  },
  "202410210002": { "exists": false, "count": 0, "files": [] }
}
```
一次批量查询（`order_no IN (...)`），不要按订单循环查询——这批设计的核心风险点就是"文件夹套文件夹导入多个订单"，订单数可能是几十个，务必 O(1) 条 SQL。

### 2. 批量预签名 `POST /api/aftersale/media/presign`
```json
{
  "order_no": "202410210001",
  "mode": "append",
  "files": [{"ext":"jpg","file_size":123456,"original_filename":"IMG_0012.jpg"}, ...]
}
```
一次返回该订单**这一批全部文件**的 presign 列表（不要每个文件单独一次 HTTP 往返，做法比照 `product/resource.py::presign_upload`，但一次请求批量生成 N 个 `bucket.sign_url`）：
```json
{
  "session_token": "abc123...",
  "items": [{"storage_key":"...","stored_filename":"202410210001_004.jpg","presign_url":"...","required_headers":{...}}, ...]
}
```
**这一步必须落一条"预留"记录**（`aftersale_media_upload_session`，见数据模型），不能只是内存里算好 seq 就直接返回——否则同一订单并发发起两次导入，两次 presign 各自"算出"相同的下一个 seq，会导致 `storage_key` 冲突或 seq 重复。做法：
1. 校验 `order_no` 规范化通过、`mode` 合法、每个文件的 `ext` 在白名单、`file_size` 不超限；
2. 在一个事务里为这批文件分配连续 `seq`（结合当前已有 `aftersale_case_media` 记录和该订单尚未过期的 `pending` session 记录取 MAX，`storage_key` 唯一约束兜底冲突）；
3. 每个文件写一条 `status='pending'`、`expires_at=now()+1小时` 的 session 行；
4. 返回 `session_token`（整批共用一个 token，关联这批全部文件的 session 行）和逐文件的签名。

`confirm` 只能确认这个 `session_token` 名下的文件，不接受客户端凭空传一个 `storage_key` 就直接落库（见下）。

### 3. 确认写入 `POST /api/aftersale/media/confirm`
```json
{
  "session_token": "abc123...",
  "order_no": "202410210001",
  "mode": "replace",
  "uploaded_storage_keys": ["tmt-library/aftersale-media/202410210001/202410210001_001.jpg", ...]
}
```
**confirm 不信任客户端传回的任意 key/文件名/大小**，一律以 `session_token` 关联的 `aftersale_media_upload_session` 记录为准：
1. 用 `session_token` 查出这批 `status='pending'` 且未过期的 session 行，逐条核对 `order_no`/`mode` 与请求体一致，`uploaded_storage_keys` 必须是这批 session 行 `storage_key` 的子集（允许部分文件上传失败被前端剔除，不允许出现 session 之外的 key）；
2. （可选但建议）对每个 key 调 `bucket.head_object(key)` 核实对象确实存在且 `Content-Length` 与 session 里 `declared_file_size` 量级相符（不要求字节级完全相等，允许合理误差，因为分片上传等场景可能有细微差异），防止"声明上传成功但 OSS 上没有对象"或"声明大小与实际严重不符"的情况；
3. **`mode=replace` 的正确时序**（这是原方案的关键 bug，已修正）：
   - **先**在一个 DB 事务里插入新的 `aftersale_case_media` 行、把这批 session 行标记 `status='confirmed'`，**提交事务**；
   - 事务提交成功后，**再**查出该订单在本次新增之前的旧 `aftersale_case_media` 行（本次事务开始前就存在的那些），逐个尝试删除对应 OSS 对象；删除失败的记一条 `aftersale_media_cleanup_failure`（不静默吞掉，见下），同时仍然把该行从 `aftersale_case_media` 删除（DB 记录以"新数据已确认写入成功"为准，旧对象只是物理清理，清理失败不影响业务可用性，但要留痕方便后续人工/补偿任务处理）。
   - 这样即使"新记录落库"这一步本身失败（比如唯一约束冲突、DB 连接问题），旧媒体还在，不会出现"新数据没写进去、旧数据却已经被删"的数据丢失窗口。
4. `mode=append`：直接插入新行、标记 session 为 confirmed，不涉及删除。
5. 幂等性：`session_token` 一旦全部 confirmed，重复调用 confirm 应该识别为"已确认过"并直接返回当前结果（不是报错，也不是重复插入——`storage_key` 唯一约束会在重复插入时天然报错，service 层应该先查 session 状态短路掉）。

**过期/未确认的 session 清理**：定期任务（或每次 precheck/presign 请求时顺手清一批）把 `expires_at` 已过且仍是 `pending` 状态的 session 标记为 `expired`，对应的孤儿 OSS 对象可以异步批量清理，不强制要求这批就做，但 session 表要留着方便以后接一个清理脚本。

### 4. 列表页批量 has_media 标志
在 `AftersaleTable.vue` 现有的两阶段加载模式基础上新增第三个批量标志查询（不要塞进 Phase 1 主 SQL，避免主查询变复杂；也不要为每行单独查）：

`POST /api/aftersale/cases/media-flags`（用 POST + body 而不是 GET + 查询串，因为 order_nos 列表长度取决于页面大小，未来页面大小调大或导出场景批量查时容易撞上 URL 长度限制）
```json
{ "order_nos": ["202410210001", "202410210002", ...] }
```

返回 `{ "202410210001": 3, "202410210002": 0 }`（order_no → 媒体数量，用一条 `GROUP BY order_no` 的 `COUNT(*)` 语句按当前页 order_no 列表批量查），前端拿到后在展开箭头/图标上显示"有 N 张图片"提示，为 0 或订单不在返回结果里则不显示媒体入口。

### 5. 展开行详情 `GET /api/aftersale/cases/<order_no>/media`
只在用户真正点开某一行展开时按需请求（现有 AftersaleTable 展开行已经是这个模式：商家备注/买家留言/物料都是主数据自带，媒体作为新增区块单独懒加载即可），返回该订单全部媒体（url、file_type、original_filename、created_at），前端渲染缩略图网格。

### 6.（可选）删除单个媒体 `DELETE /api/aftersale/media/<id>`
供误传纠错，`aftersale:edit`，同时删 DB 行和 OSS 对象。

## 前端交互流程

### 入口
`AftersaleTable.vue`（或所在的"数据"Tab 工具栏）新增「导入售后图片」按钮，`aftersale:edit` 权限可见。

### 选择文件夹
```html
<input type="file" webkitdirectory multiple ref="folderInput" style="display:none" @change="onFolderSelected" />
```
`webkitdirectory` 允许用户选中**一个父文件夹**，浏览器会递归返回其下所有文件，每个 `File` 对象带 `webkitRelativePath`（如 `批次A/202410210001/IMG_0012.jpg`）。

分组规则（需要覆盖两种用户习惯）：
- **父文件夹套多个订单子文件夹**（批量场景，一次导入多个订单）：`webkitRelativePath` 至少 3 段，取**第二段**（父文件夹名之后的第一级子目录名）作为 order_no，深于两级的路径直接忽略（不递归到孙子目录，避免用户文件夹结构混乱导致误分组）。
- **直接选中单个订单文件夹**（该文件夹本身以订单号命名，内部就是图片，无子目录）：`webkitRelativePath` 只有 2 段，取**第一段**（即选中的文件夹名本身）作为 order_no。

前端按扩展名过滤出图片/视频文件，跳过其它类型并统计"已跳过 N 个文件"用于最终提示。

### 冲突确认弹窗
按分组结果调用 `precheck`，展示表格：订单号 | 已有 N 个文件（可展开看缩略图）| 本次待导入 M 个文件 | 操作（跳过 / 追加 / 替换，默认给未冲突订单直接标记为"追加"，冲突订单默认选中但需要用户至少看一眼）。提供"全部设为追加"/"全部设为替换"/"全部跳过冲突项"的批量快捷按钮，避免几十个订单要一个个点。

### 上传执行
逐订单（可并发几个订单，不要几十个订单全部并发炸掉单 worker）：
1. 调 `presign` 拿该订单这批文件的 `session_token` + 签名列表；
2. 前端用 `fetch(presign_url, {method:'PUT', headers: required_headers, body: file})` 直传 OSS（复用资料库现成的直传模式，不新造轮子）；
3. 收集实际上传成功的 `storage_key` 列表（允许部分文件失败），调 `confirm` 落库，传入 `session_token` + 成功的 key 列表；
4. 更新进度 UI（按订单/按文件的进度条，参考发货导入任务已有的进度组件风格）。

结束后汇总：成功 N 单、失败 M 单（列出失败 order_no，支持仅重试失败项）。

### 表格展示
- 列表主 SQL 不变，媒体数量通过 `media-flags` 批量接口在当前页数据加载完成后追加一次查询合并进 `items`（类似现有 reasons phase2，但更轻量，只是计数不是关联对象）。
- 展开行新增"售后图片/视频"区块，仅当该订单 `media_count > 0` 时渲染；点开展开行时才调用 `GET .../media` 懒加载详情（避免整页展开 20 行时炸 20 次请求——只有用户真正点开的行才请求）。
- 图片用网格缩略图 + 点击放大（`el-image` 自带 `preview-src-list` 即可，不需要新写图片查看器）；视频用可点击播放的卡片（点击后 `<video controls>` 内嵌播放或弹窗播放，参照资料库 `proxy-content`/预览的现成模式，能直接用 `oss_url` 的话不需要走代理）。

## 建议实施顺序

1. **第一批（后端）**：新表 + Alembic 迁移、precheck/presign/confirm 三个接口、media-flags 批量标志接口、展开行详情接口。本地 SQLite 单测覆盖：新订单导入、追加序号递增、替换清空旧数据+OSS对象、precheck 批量查询不产生 N+1。
2. **第二批（前端）**：文件夹选择 + 分组解析 + 冲突确认弹窗 + 批量上传执行 + 进度展示。
3. **第三批（前端）**：表格展开行媒体区块（依赖第一批的 media-flags/详情接口）。

三批可以合并成一次提交，也可以拆开分批走审查——按 Codex 的进度节奏自行判断，不强制拆分。

## 验收要求（部署前）

- 真实 MySQL 下验证：追加模式 seq 递增正确、并发两次对同一订单调用 presign 不会分配到相同 seq/storage_key（可写个并发测试模拟）、替换模式**先插入新记录提交成功后再删旧 OSS 对象**（可以人为在"插入新记录"这一步制造失败，验证旧数据仍然完好）、precheck/media-flags 批量查询在多订单场景下仍是常数条 SQL（不随订单数增长）。
- confirm 校验：用篡改过的 `storage_key`（不属于该 session）调用 confirm，应被拒绝；用已过期的 `session_token` 调用应被拒绝；订单号包含 `../` 或路径分隔符应在 presign 阶段就被拒绝。
- 真实 HTTP 走一遍完整流程：选择本地测试文件夹 → precheck → presign（拿到 session_token）→ 直传 OSS → confirm → 列表页展开行看到图片。
- 大文件（几十 MB 视频）直传验证不经过服务器 CPU 密集处理，确认不会触发 gunicorn 看门狗风险。
- `aftersale_media_cleanup_failure` 表在人为制造 OSS 删除失败（比如临时吊销该 key 的删除权限）时确实写入记录，不是静默吞异常。
