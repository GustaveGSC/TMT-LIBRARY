# 物料门禁增加品名/规格字段，交接 Codex

状态：待实现

## 背景

上一批（`handoff/2026-09-25-codex-rd-material-gate-backend.md`，已部署）实现的物料门禁只存了
`code/level/reason`。用户现在要求：命中门禁时要用**弹窗**展示，弹窗里必须显示这条门禁对应的
"名称（品名+规格）"，不能只显示物料编码。这个名称是**门禁记录本身登记的信息**（管理员新增门禁时
一并填写"这个编码对应的是什么东西"），不是从上传文件里解析出来的——所以不需要动
`compare_bom()`/`pdm2bom_process()`，只需要给 `MaterialGate` 加两个字段。

前端我自己实现（弹窗组件、维护弹窗表单加字段、首页入口改版），这份交接只需要你做后端。

## 需要实现

### 1. `MaterialGate` 模型加字段

`backend/database/models/rd/__init__.py`：

```python
name = db.Column(db.String(200), nullable=False)   # 品名，必填
spec = db.Column(db.String(300), nullable=True)     # 规格，选填（有些物料没有规格变体）
```

放在 `code` 和 `level` 之间还是随意，但 `to_dict()` 要把 `name`/`spec` 加进去（`spec` 为空时返回
`''`，不要返回 `None`，前端按字符串拼接显示）。

### 2. 迁移

新 revision，`down_revision = '20260925_01'`。`ALTER TABLE material_gate ADD COLUMN name ...`。
当前生产 `material_gate` 表是空的（这个功能刚上线还没人真正登记过门禁），所以不用纠结历史数据
回填，`name` 直接设 `nullable=False`（如果 alembic/MySQL 要求给一个 `server_default` 才能在非空表
上加非空列，给个 `server_default=''` 也无妨，反正表是空的）。

### 3. Service 校验

`backend/services/rd/material_gate.py` 的 `_validated()`：
- `name`：必填，参考现有 `_required_text` helper，`max_length=200`
- `spec`：选填，为空时存 `None`（或空字符串，跟 `reason` 那些字段的现有写法保持一致就行，别自己
  发明新规则）
- `create`/`update` 的参数、`MaterialGateRepository.create`/`update` 的签名相应加上 `name`/`spec`

### 4. `check()` / `check-file` 输出加字段

`MaterialGateService.check()` 目前返回 `{'code': gate.code, 'reason': gate.reason}`，加上
`'name': gate.name, 'spec': gate.spec or ''`。`check-file` 复用同一个 `check()`，不用改。

### 5. Routes

`create_material_gate`/`update_material_gate` 从 `request.get_json()` 里读 `name`/`spec` 就行，
service 层已经处理校验，routes 本身不用加逻辑。

## 契约要点

前端 `MaterialGateManageDialog.vue` 的新增/编辑表单会传 `{code, level, reason, name, spec}`；
`check`/`check-file` 返回的 `warn`/`block` 数组里每一项现在是
`{code, name, spec, reason}`（新增 `name`/`spec` 两个字段，`code`/`reason` 位置不变）。

## 不需要的改动

- 不要碰 `compare_bom()`/`pdm2bom_process()`，这次改动跟它们无关。
- 不要改前端。
- 不用给现有空表做数据回填脚本。

## 验证要求

- `backend/tests/test_rd_material_gate.py` 或就近位置补测试：
  - 创建门禁不传 `name` 应该报错（400/ValueError）
  - 创建门禁 `spec` 留空应该成功，`to_dict()`/`check()` 返回 `spec: ''`
  - `check()` 命中项包含正确的 `name`/`spec`
- 相关测试全绿，`pytest backend/tests/test_rd_material_gate.py backend/tests/test_rd_route_guards.py -q`
- `python -m compileall -q backend`、`git diff --check` 通过

## Claude 后续动作

收到交付后我会 review diff、备份数据库（这次只是加列，风险很低，但按惯例还是会备份）、部署
（scp + alembic upgrade head + reload gunicorn）、联调新的弹窗展示效果。
