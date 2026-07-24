# Claude 部署记录：财务导入工作流 A 批（后端 + 前端）

日期：2026-07-24

## 后端（对应 handoff-30）

- 提交：`7c77fd6 fix(shipping): invalidate options after customer mapping`
- 无数据库迁移。同步 `database/repository/shipping/__init__.py`、`routes/shipping/__init__.py` 两个文件，
  MD5 校验一致，`systemctl reload gunicorn`，master PID 未变，`/health`/`/ready` 正常。
- 本地全量 pytest + compileall 通过后才上传。

## 前端

- 提交：`fab331d feat(frontend): 财务导入工作流A批前端`
- 变更：
  1. "外贸客户匹配"→"客户匹配"（`FinanceCustomerMapping.vue` 标题、`page-data-mgmt.vue` tab 标签）；
  2. 客户匹配页说明区分两种场景："修改分类/国家/品牌保存后立即生效" vs "重导历史数据补客户简称仍需
     手动重建"（B 批上线前的过渡期文案，B 批完成增量 resolve 后需要再调整）；
  3. "刷新全局数据"→"重建全部成品组合（高级）"，从顶部常驻按钮移到"数据配置→高级操作"新增 tab，
     不再是日常导入流程引导路径的一部分；
  4. 更新 `task-conflict-409.spec.js` 选择器匹配新入口位置和文案。
- 验证：`npm run build:web` 通过；46 个 Playwright 用例全绿（含更新后的 409 冲突回归）。
- 部署：`tar`+`scp`+服务器端覆盖，线上 `index.html` 引用的 JS hash 与本地构建比对一致
  （`index-Cv62vaIP.js`）后删除 `.old` 备份。

## 待续

B 批（差异检测与增量 resolve）由 Codex 进行中。B 批完成后需要再回来把 `FinanceCustomerMapping.vue`
里"重导历史数据仍需手动重建"这句过渡期提示去掉或改写，因为那时候重导会自动增量 resolve 受影响订单。
