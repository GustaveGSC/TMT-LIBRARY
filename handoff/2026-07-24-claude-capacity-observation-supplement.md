# 生产容量观测补充（响应 Codex 性能诊断报告第5节要求）

日期：2026-07-24
性质：只读观测，无代码变更。对应 `handoff/2026-07-24-codex-shipping-chart-performance-diagnosis.md` 第5节"服务器资源判断"里要求的采集项，先记一次基线，不代表一周观察窗口的完整结论。

## Gunicorn worker class 确认

```
ExecStart=/usr/local/bin/gunicorn -w 1 -b 127.0.0.1:8765 "app:create_app()" --timeout 1800
```

没有 `--worker-class` 参数，Gunicorn 默认就是 `sync`；没有 `--threads` 参数（对 sync worker 也不生效）。**确认是单 sync worker，不是 gthread/async，请求确实严格串行处理**，Codex报告里"应按最坏情况处理"的判断成立，可以作为定论，不需要再打问号。

## `vmstat 1 5`（本次采样，非持续监控）

```
procs -----------memory---------- ---swap-- -----io---- -system-- ------cpu-----
 r  b   swpd   free   buff  cache   si   so    bi    bo   in   cs us sy id wa st
 1  0 297668 115904      0 871176    0    5    56    14  533  201  2  1 97  0  0
 0  0 297668 115904      0 871244    0    0     0     0 1088 1923  1  1 99  0  0
 0  0 297668 115904      0 871244    0    0     0     0 1022 1855  1  0 99  0  0
```

`si/so`（换入/换出）在采样窗口内基本为0（只有首行 so:5 一次性小波动），说明**此刻不在持续换页**，`swpd`(297MB) 是历史累积的换出页，不代表当前系统在活跃 swap thrashing。这印证了 Codex 报告里"swap已用不等于当前持续换页"的判断——**不能仅凭 swap 已用量判断内存紧张到需要立即扩容**，这是一次性观测，不是一周窗口，如果要下最终结论还需要更长时间的持续监控（比如在导入大文件/售后图表被频繁访问的时段采样）。

## InnoDB buffer pool 状态（MySQL uptime 仅8.2小时，非一周窗口）

```
Innodb_buffer_pool_pages_total   = 8192   (× 16KB = 128MB，与配置一致)
Innodb_buffer_pool_pages_free    = 654    (约8%空闲)
Innodb_buffer_pool_pages_dirty   = 0
Innodb_buffer_pool_read_requests = 8,035,911
Innodb_buffer_pool_reads         = 108,000
Uptime                            = 29,421秒（约8.2小时）
```

计算出的缓存未命中率 ≈ 108000/8035911 ≈ **1.34%**（命中率约98.66%），在当前8小时窗口内看起来并不差，与"buffer pool远小于数据量所以命中率一定很差"的直觉不完全一致——可能是访问模式集中在近期数据（热点数据），或者OS page cache（vmstat显示cache约871MB）在InnoDB buffer pool之外又做了一层缓冲，两层叠加缓解了实际压力。**这个数字只是8小时窗口的快照，MySQL最近刚重启过（uptime短），不能代表长期稳定状态，Codex建议的"观察一周慢日志和buffer pool miss"仍然需要做，这次只是先给一个基线参考。**

## 进程内存占用（`ps aux`）

```
mysqld           RSS ≈ 350MB（占系统内存 20.9%）
gunicorn worker  RSS ≈ 164MB
gunicorn master  RSS ≈ 27MB
```

三者合计约541MB，加上OS/其他服务，与`free -h`里"已用835MB"基本吻合。

## 结论

这次快照没有发现"内存已经在崩溃边缘"的证据（无持续swap、buffer pool命中率尚可），支持Codex"先修SQL、再观察一周指标、不要现在就急着调buffer pool"的建议。已确认的是gunicorn worker class（单sync，最坏情况成立）。后续如果要下"要不要扩buffer pool/加内存"的最终结论，建议在Codex的SQL修复批次上线后，选一个业务高峰时段（比如有人在导入大文件、或售后/发货图表访问密集的时段）重新采一次同样的指标做对比。
