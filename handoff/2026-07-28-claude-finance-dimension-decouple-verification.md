# 财务维度从通用标签体系解耦：生产验证通过并已上线

日期：2026-07-28

## 结论

Codex 的实现（43b1e92）审查通过：新增 `product_tag_category.finance_dimension_field`
（迁移 `20260728_03`，回填"全球区域/地域"→`country`、"品牌"→`brand`），运行时代码不再依赖
分类名字符串判断，`get_chart_options` 按 source 完全分流可见性，新增
`map_dimension_category_id` 供前端稳定识别世界地图维度。已合并部署，前端配合改动（世界地图
判断改用 id、标签维度配置页过滤掉这两个分类）已一并完成、构建部署，真实 HTTP 验证通过。

## 部署

涉及 schema 迁移：
1. 迁移前完整 mysqldump 备份（`/tmp/tmt_db_backup_20260728_pre_finance_dim.sql.gz`，48MB，
   `Dump completed` 尾部确认完整）。
2. 同步 3 个后端文件（model、repository、迁移脚本），MD5 核对一致。
3. `alembic upgrade head` → `20260728_03 (head)`，无报错。
4. `systemctl reload gunicorn`，master PID 未变，无崩溃重启，`/health`/`/ready` 正常。
5. 前端 `npm run build:web` → 部署 → 线上 `index.html` hash 核对一致。

## 真实 HTTP 验证

**迁移回填**（直接查库）：`全球区域`(id=3)→`finance_dimension_field='country'`，
`品牌`(id=2)→`'brand'`，其余分类为 `NULL`。

**`get_chart_options` 按 source 分流**：

| source | 返回的 tag_dimensions | map_dimension_category_id |
|---|---|---|
| finance | 全球区域、品牌、学习桌尺寸、学习桌台面材料（4个，含财务维度） | 3 |
| shipping | 学习桌尺寸、学习桌台面材料（2个，财务维度已排除） | null |

**`/api/product/tags/categories/`**：`全球区域`/`品牌` 正确带
`finance_dimension_field`，其余分类为 `null`，`TagDimensionConfig.vue` 据此过滤后这两个
分类不会出现在"标签分析维度"配置页。

## 当前状态

用户提出的两个架构问题（世界地图因改名失效、财务维度可被通用开关误关且发货端不该出现这两个
维度）均已从根因解决，无已知遗留问题。建议用户实际在浏览器里确认：财务视图切到"全球区域"
维度地图正常显示、发货视图维度列表已看不到这两项、标签分析维度配置页也已看不到这两个分类。
