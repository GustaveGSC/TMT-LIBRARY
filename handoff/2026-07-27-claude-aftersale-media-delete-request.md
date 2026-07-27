# 售后媒体导入：补充删除接口请求（交接 Codex）

## 背景

用户反馈已上线的售后媒体导入功能缺一个"清除/删除已导入文件"的方式。原设计文档里这项是标了
"6.（可选）"的删除接口，当时没有实现。前端这次已经把统一查看器（图片/视频同框左右切换）做好
并预留了删除按钮（`AftersaleMediaViewer.vue`），调用：

```
DELETE /api/aftersale/media/<id>
```

前端已经按这个契约写好调用代码，**目前后端还没有这个路由**，调用会 404。请补上。

## 需要实现

- 路由：`DELETE /api/aftersale/media/<int:media_id>`，权限 `aftersale:edit`。
- 逻辑：按 `id` 查 `AftersaleCaseMedia`，不存在返回 404/fail；存在则：
  1. 先删 DB 行（或者反过来也行，但要保证两步的失败处理和 `confirm_media` 里 replace 的思路一致：
     **不能因为 OSS 删除失败就让整个请求失败**——参考 `confirm_media` 里对旧对象删除失败时写入
     `AftersaleMediaCleanupFailure` 而不回滚的做法，这里应该也一样：DB 行删除成功后再尝试删
     OSS 对象，失败写入 `aftersale_media_cleanup_failure` 留痕，不影响这次删除操作本身返回成功。
  2. 返回 `Result.ok()`，不需要额外 data。
- 不需要新增表或迁移，复用现有三张表。
- 测试覆盖：正常删除（DB 行消失 + OSS 对象被删）、OSS 删除失败时仍返回成功但留痕、
  不存在的 id 返回失败、无 `aftersale:edit` 权限返回 403。

## 顺带确认（无需改动，只是希望文档同步）

`.claude/modules/api.md` 里补一行这个新接口即可，和其它五个接口保持同样的记录格式。
