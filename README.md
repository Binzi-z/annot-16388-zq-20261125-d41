# 跨版本脱敏的歧义边界证书

纯 Python 3.12 标准库、离线运行的脱敏复核工具。它不依赖“第一次字符串匹配”，而是枚举短字符串的**全部最小成本对齐**，并在大规模语料上用对齐格标记计算“必定 / 可能继承密级”的区间与可复核见证。

## 运行

在原生 Windows 上使用 Python 3.12：

```powershell
py -3.12 review.py test
py -3.12 scale_demo.py
```

也可以：

```powershell
py -3.12 -m desens_review scenarios --out artifacts\short
py -3.12 -m desens_review enumerate --source aa --target a
py -3.12 -m desens_review generate-corpus --root artifacts\corpus
py -3.12 -m desens_review update-one --root artifacts\corpus --doc DOC-0007 --paragraph 0
py -3.12 -m desens_review verify-corpus --root artifacts\corpus
```

`scale_demo.py` 会生成短字符串证书、**500 个独立文档 × 每文档 100 段 = 50,000 个合成段落**，更新 `DOC-0007`，随后全量重算并核对标记。结果写入：

- `artifacts/short/*.json` / `*.md`：每个边界和全部最小对齐；
- `artifacts/corpus/cases/*.json`：独立文档输入；
- `artifacts/corpus/markers/*.markers.json`：全量对齐标记；
- `artifacts/corpus/manifest.json`：逐文档与总清单哈希；
- `artifacts/scale_check.json`：本地处理量、更新结果、全量复核和计时。

## 对齐模型

默认模型是 `transport`（保留/重排模型）：

- 输出原子必须是 `insert`，或唯一链接到一个来源原子；
- 来源原子必须是 `delete`，或唯一链接到一个输出原子；
- 相同文本的保留链接成本为 `0`，允许跨越其他链接，因此移动不会被误判成删除后新增；
- 不同文本的替换链接成本为 `1`；
- 删除来源、插入输出的成本均为 `1`；
- 复制在单个对齐中表现为“一个副本保留、另一个副本插入”；在全部最优对齐中，每个副本都可能是保留副本；
- 拆开的片段由多个可分离链接表示，并额外汇总从首个链接到末个链接的完整 hull 区间。

设来源、输出原子数为 `n,m`，相同文本的最大一一匹配数为 `K`，则最小成本为：

```text
C* = max(n, m) - K
```

重复文本会产生多个 occurrence 匹配，因此必须枚举或用经过路径计数验证的候选边集合处理。工具也保留经典、保序的 Levenshtein 模型，可用 `--alignment-model ordered` 或 `ReviewCase(alignment_model="ordered")` 调用；该模型用于对照“不能穿越”的严格顺序约束。

## 密级、降密与发布判定

密级水位为：

```text
PUBLIC=0 < INTERNAL=1 < CONFIDENTIAL=2 < SECRET=3
```

- 来源区间用稳定的 `source_id` 标识；相同可见文本但不同 `source_id` 仍是不同来源。
- 每条最小对齐给出一个输出原子的来源/水位。
- `may_level = max` 跨全部最优对齐的候选水位；`must_level = min`。
- `may_level > PUBLIC` 即“可能敏感”，发布结论为 `BLOCK_POSSIBLE_SENSITIVE`。
- `must_intervals` 合并所有最优对齐下均敏感的连续原子；`may_intervals` 合并至少一个最优对齐下敏感的连续原子。
- `hull_intervals` 报告被拆开的来源片段在输出中的完整左右边界、逐块 `pieces`、支持对齐数，以及正/反对齐编号。

显式降密 `Downgrade(decl_id, source_id, watermark, ...)` 只对：

1. `source_id` 完全相同的来源；
2. 不高于声明 `watermark` 的水位上限；

生效。撤销的代理降密保留审计记录但效果为 `revoked_no_effect`。一个来源的有效降密不会洗掉另一个冲突来源的密级。

## 见证与自检

每个可能区间都附带：

- `positive_witness`：包含高密级来源链接的最小成本对齐；
- `negative_witness`：同一区间原子上的公开/插入/低水位替代，或必定区间左/右外侧的反证；
- 每个见证的操作序列、左右字符边界、图式、经过边的对齐数量；
- 独立验证器：检查索引、原子消费唯一性/顺序、成本、是否确为最小成本。

短字符串测试对 `"".."aaa"` 的所有组合，把格标记/见证与完整枚举逐一对照，并断言：

```text
lattice.total_paths == len(enumerate_*_alignments(...))
sum(through_count for choices on target j) == total_paths
```

## 已覆盖的指定场景

`desens_review/scenarios.py` 中包含：

- `copied_fragment`：`a -> aa`，恰好 2 个最小对齐，两个输出副本均为可能敏感；
- `repeated_source_conflict`：`aa -> a`，两个相同区间分别来自 `SECRET` 与 `PUBLIC` 来源，恰好 2 个最小对齐并报告来源密级冲突；
- `classified_watermark_conflict`：同样的重复区间分别来自 `SECRET` 与 `CONFIDENTIAL`，提供高水位正见证和较低水位反见证，但两者都仍敏感，因此禁止发布；
- `moved_fragment`：`ab -> ba`，transport 模型为 0 成本穿越对齐，输出 `a` 的 `[1,2)` 为必定继承，并给出左侧公开原子的反证；
- `split_fragment`：`abc -> axbyc`，逐块边界为 `[0,1)`、`[2,3)`、`[4,5)`，完整 hull 为 `[0,5)`；
- `scoped_downgrade_watermark`：只把 `S-DECLARED` 降到 `INTERNAL`，`S-OTHER` 仍为 `SECRET`；
- `proxy_downgrade_active` / `proxy_downgrade_revoked`：代理降密生效时放行，撤销后恢复阻断并生成正/反见证。

## 五万段与增量一致性

默认配置为 `500 × 100 = 50,000`。每段都是独立 `ReviewCase`，文档之间不共享对齐状态。更新 `DOC-0007` 时只重新处理该文档的 100 段，返回：

- 本地段落数、来源/输出原子数、候选格数、标记边数；
- 统计是否等于逐标记 rollup；
- 新的 manifest 聚合哈希。

随后 `verify_corpus` 会重新计算全部 50,000 段，逐文档比较存储标记、哈希、统计和总清单。最近一次标准库测试结果：

```text
Ran 19 tests ... OK
documents_checked: 500
paragraphs_checked: 50000
errors: []
```

最近一次完整运行的聚合哈希（更新 `DOC-0007` 后）：

```text
4b913df1747833b841e535047cebba359644570b118a0022b739d41d235dc771
```

## 代码布局

```text
review.py                     Windows 友好入口
scale_demo.py                 短证书 + 50k 段增量/全量核对
desens_review/model.py        数据模型、字符/token 偏移
desens_review/align.py        保序 Levenshtein 全最优格与枚举
desens_review/transport.py    允许移动穿越的最小匹配格与枚举
desens_review/review.py       must/may 区间、降密、冲突、见证
desens_review/scenarios.py    指定短字符串场景
desens_review/corpus.py       合成 50k 段、manifest、增量更新、全量复核
desens_review/report.py       JSON/Markdown 证书
tests/                        unittest 标准库测试
```
