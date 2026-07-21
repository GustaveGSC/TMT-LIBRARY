# 依赖锁定审计合并记录

日期：2026-07-21
分支：`codex/backend-dependency-lock-audit`（`eb01e02`），fast-forward 合并，68 passed。

## 审查结论

- 修复了一个真实的约束冲突：`gunicorn==26.0.0`、`packaging==26.2`（服务器实际安装版本）超出了 `requirements.txt` 里声明的范围（`<24.0.0`/`<26.0`），扩大到 `<27.0.0`/`<27.0` 覆盖实际版本
- 移除死依赖 `xlwt`（`requirements.txt` 和锁文件都删了），保留真实在用的 `xlrd==1.2.0`
- 新增 `test_production_lock_covers_and_satisfies_all_direct_requirements`：程序化校验每条声明依赖的版本约束都被锁文件里对应的精确版本满足，这个测试要是早有，上面那个 gunicorn/packaging 范围冲突根本不会发生

## 部署

只涉及 `requirements.txt`/锁文件/测试文件，不涉及运行时代码，**不需要 reload**。已把两个 manifest 文件 scp 同步到服务器对应路径（md5 核对一致），供下次真正重装依赖时使用。

## 下一批（已确认顺序）

1. P1 原始异常信息泄露
2. P1 数据库 readiness 健康检查
3. P2 售后 SQL 拼接隐患
4. `product:delete` 产品决策确认

Cookie/token 改造、P3 重构、Git 历史清理分别单独排期，不进这一批。
