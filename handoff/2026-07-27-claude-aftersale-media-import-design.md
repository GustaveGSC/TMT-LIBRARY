# 售后图片/视频导入功能设计（交接 Codex，未实现）

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
  oss_url VARCHAR(1000) NOT NULL
  storage_key VARCHAR(500) NOT NULL
  file_size BIGINT
  sort_order INT DEFAULT 0
  uploaded_by INT FK→user SET NULL nullable
  created_at DATETIME
  # 索引：ix_aftersale_case_media_order_no（列表页批量查 has_media、展开行按 order_no 查详情都靠它）
```

不建 `order_no` → `aftersale_case.ecommerce_order_no` 外键的原因：需求 2 明确"无需判断导入的文件夹订单号是否存在于当前售后订单目录"。媒体表和工单表通过 `order_no` 字符串做运行时关联，工单后续导入/确认时自动"接上"已存在的媒体，不需要回填。

## 存储

沿用 `backend/storage/client.py` 的 OSS 客户端和 `product_resource` 的**预签名直传**模式（浏览器直接 PUT 到 OSS，不经服务器中转）——这一点是硬要求，不是可选优化：售后视频文件可能不小，如果走服务器中转 multipart 上传，会撞上 CLAUDE.md 里记录的"单 worker + CPU 密集任务占用心跳导致 gunicorn 看门狗 SIGKILL"的坑（虽然文件传输本身不是 CPU 密集，但大文件走 Flask 请求体读取仍会长时间占用唯一的 sync worker，阻塞其他所有请求）。

OSS key 规则：`tmt-library/aftersale-media/{order_no}/{stored_filename}`，独立于 `resources/{yyyymm}/...` 前缀，按订单号直接定位，方便后续按订单清理。

## 命名规则

`stored_filename = "{order_no}_{seq:03d}.{ext}"`，`ext` 取原文件扩展名小写。

- `seq` 起始值：
  - 全新订单（该 order_no 之前无记录）→ 从 `001` 开始；
  - **追加**模式 → 从该订单当前最大 `seq` + 1 继续（需要解析已有 `stored_filename` 或额外存一列 `seq INT`，建议直接加 `seq` 列而不是解析文件名字符串，更稳）；
  - **替换**模式 → 先删除该订单旧记录（DB 行 + 对应 OSS 对象），再从 `001` 开始。
- 同批次内即使原文件名重复，`seq` 天然去重，不会冲突。

## 支持的文件类型

复用 `backend/routes/product/resource.py` 里 `UPLOAD_EXT_MAP` 的图片/视频子集：`png/jpg/jpeg/webp` + `mp4/mov/webm`。文件夹内其它类型文件（如 `.DS_Store`、`Thumbs.db`、文档）直接跳过，不阻塞整单导入，导入结果里提示"已跳过 N 个不支持的文件"。

大小限制：建议复用 `upload_validation.py` 里现成的额度校验逻辑（`parse_declared_size`），是否需要为售后视频单独定一个比 `RESOURCE_UPLOAD_LIMIT` 更大的上限，由 Codex 按实际售后视频文件大小评估。

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
{ "items": [{"presign_url":"...","storage_key":"...","stored_filename":"202410210001_004.jpg","required_headers":{...}}, ...] }
```
`seq` 在这一步就要算好并占用（避免同一订单并发两次导入时 seq 冲突），但**不要在这一步写 DB 记录或删除旧数据**——只是发号+签名。真正落库放在下一步，这样即使用户上传到一半放弃，也不会产生"数据库有记录但 OSS 没文件"的悬空行；顶多留下几个孤儿 OSS 对象（无展示副作用，可以不做强制清理，Codex 视情况决定是否需要一个后续清理脚本）。

### 3. 确认写入 `POST /api/aftersale/media/confirm`
```json
{
  "order_no": "202410210001",
  "mode": "replace",
  "uploaded": [{"storage_key":"...","stored_filename":"...","original_filename":"...","file_type":"image","file_size":123456,"seq":1}, ...]
}
```
- `mode=replace`：先删除该 `order_no` 现有的全部 `aftersale_case_media` 行**以及对应 OSS 对象**（`bucket.delete_object`，逐个 try，不要因单个删除失败整体回滚——旧文件删不掉不影响新数据可用），再插入新行；整个"删旧+插新"包在一个 DB 事务里。
- `mode=append`：直接插入新行。
- 幂等性：如果这一步网络失败，前端应允许用同一批 `storage_key` 重新调用（不会产生副作用之外的重复写入前提是前端不重复提交——不强制做 storage_key 唯一约束，简单场景足够，除非 Codex 认为有必要加）。

### 4. 列表页批量 has_media 标志
在 `AftersaleTable.vue` 现有的两阶段加载模式基础上新增第三个批量标志查询（不要塞进 Phase 1 主 SQL，避免主查询变复杂；也不要为每行单独查）：

`GET /api/aftersale/cases/media-flags?order_nos=xxx,yyy,zzz`

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
1. 调 `presign` 拿该订单这批文件的签名列表；
2. 前端用 `fetch(presign_url, {method:'PUT', headers: required_headers, body: file})` 直传 OSS（复用资料库现成的直传模式，不新造轮子）；
3. 全部上传成功后调 `confirm` 落库；
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

- 真实 MySQL 下验证：追加模式 seq 递增正确、替换模式旧 OSS 对象确实被删除（不是只删 DB 行）、precheck/media-flags 批量查询在多订单场景下仍是常数条 SQL（不随订单数增长）。
- 真实 HTTP 走一遍完整流程：选择本地测试文件夹 → precheck → presign → 直传 OSS → confirm → 列表页展开行看到图片。
- 大文件（几十 MB 视频）直传验证不经过服务器 CPU 密集处理，确认不会触发 gunicorn 看门狗风险。
