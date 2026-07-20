# 项目问题梳理 · Claude → Codex

日期：2026-07-20
本文件只做问题上报，不包含修复。分工仍按 [AGENTS.md](../AGENTS.md)：`backend/` 由 Codex 处理，我（Claude）会处理前端/构建产物相关部分。

---

## 1. Git 仓库体积膨胀（`.git` 已达 1.6GB）—— 优先级高

扫描历史 blob，体积大头是被反复整份提交的二进制构建产物：

| 文件 | 单个体积 | 出现次数（部分） |
|---|---|---|
| `electron/resources/python-backend/backend.exe` | ~40MB | 至少 4 个不同历史版本 |
| `dist-web/ffmpeg/ffmpeg-core.wasm` | ~32MB | |
| `src/assets/maps/china-city.json` / 打包后的 bundle | ~3.4MB | 前端+构建产物各一份 |
| `dist-web/assets/index-*.js` | ~1MB/个 | 每次构建 hash 变化都整份重存，重复多次 |

**问题**：这些文件每次改动 Git 都当作全新 blob 存储（二进制不走 delta 压缩），仓库会持续膨胀，clone/fetch 越来越慢。

**涉及双方**：
- `backend.exe` 是 `electron/resources/python-backend/` 下的产物，来源于 `npm run build:python`（打包脚本在 `scripts/`）——这个具体是前端构建流程产出还是后端打包脚本产出，需要 Codex 确认一下 `backend.exe` 的生成方式，因为它名字上像是后端的编译产物但存在 `electron/resources/` 下。
- 建议方案（需要双方达成一致，我不会单方面改）：
  1. `backend.exe`、`ffmpeg-core.wasm` 这类大且很少变化的二进制，改用 Git LFS，或者干脆不进 git（打包时从 OSS/CI 产物拉取）
  2. `dist-web/` 是否还要继续整体提交到 git，还是改成只在部署时生成、不进版本库——这个之前 AGENTS.md 里默认沿用"现有仓库约定"，但现在看体积代价已经比较明显，值得重新评估

这一条我不会擅自处理（清理 git 历史是高风险操作，需要你本人确认），先报上来。

---

## 2. 版本号文档不一致

`package.json` 当前是 `1.2.0`，但 `.claude/CLAUDE.md` 里写的"当前版本"是 `1.1.5`（且仓库里同时存在 `release1.1.5/` 和 `release1.2.0/` 两个目录，说明 1.2.0 已经发布过）。文档没跟上实际版本号。我会顺手把 `.claude/CLAUDE.md` 更新到 1.2.0，但如果版本号变更是 Codex 那边触发的（比如后端有对应版本兼容逻辑），麻烦确认一下 1.2.0 是否是最终版本号，还是中间试验状态。

---

## 3. 完全没有自动化测试

`package.json` 没有 `test` 脚本，仓库里没有 `tests/` 目录，也没有 pytest/vitest 配置文件。这意味着：
- 后端目前靠"性能规范里那几条陷阱清单"人工记忆规避风险，没有任何测试兜底
- 双 agent 并行开发时，回归全靠人工过一遍，容易漏

不要求现在就补全测试体系（成本较高），但建议后续新增/改动高风险函数（`get_chart_data`、`get_cross_filter_options`、`auto_match`、涉及 `shipping_order_finished` 索引 hint 的查询）时，至少写最基本的冒烟测试，防止无意中改回 N+1 或漏加 hint。这个决定权在 Codex，我这边前端同理会考虑逐步补关键流程测试。

---

## 4. `requirements.txt` 全部用 `>=`，没有锁版本

```
flask>=3.0.0
flask-sqlalchemy>=3.1.0
...
onnxruntime>=1.18.0
tokenizers>=0.19.0
```

没有 `requirements-lock.txt`（或 `pip freeze` 产物）。服务器重新 `pip install` 时可能因为依赖版本漂移导致行为和本地不一致，尤其 `onnxruntime`/`tokenizers` 这类经常有 breaking change 的包，风险相对高。建议 Codex 评估是否要补一份锁定版本的 lock 文件，至少生产环境部署用锁定版本、开发环境可以用范围版本。

---

## 5. `backend/services/shipping/__init__.py` 里三处清理逻辑的静默吞异常

全仓库扫到 28 处 `except ... : pass`，大部分是"语义匹配/日志写入失败不影响主流程"的**有意为之的降级设计**（代码里也有注释说明，比如 `aftersale/__init__.py` 里那几处），这些没问题，不用动。

唯一想单独指出的是 `backend/services/shipping/__init__.py` 第 649 / 726 / 811 行附近：这三处是在**导入失败后的 rollback + 删除批次**这段清理逻辑外面又包了一层 `except Exception: pass`。如果清理本身又失败（比如 `delete_batch` 抛错），会完全静默，没有任何日志，可能留下不一致的 batch 记录且没人知道。建议至少加一行 `logger.warning(...)`，具体怎么处理交给 Codex 判断。

---

## 6.（已知问题，简单重提）`api.md` 仍是路由索引，不是结构化契约

上次交接已经提过，这里不重复展开，等下次有新接口时按补充后的模板走即可，不用现在专门花时间重写所有存量条目。

---

以上 6 条里，**第 1 条（git 体积）和第 4 条（依赖锁定）建议优先处理**，其余可以按 Codex 的节奏排期。有不同意见或者觉得优先级该调整的，直接在这份文件下面追加说明即可。
