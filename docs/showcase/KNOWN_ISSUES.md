# 已知限制与验收缺口 · 2026-11-03

当前完整功能候选已集成；以下未因界面存在、单测数量或历史资料而视为关闭。早期过程记录保留在[历史快照](KNOWN_ISSUES_HISTORY.md)，其“当前待完成”文字属于当时状态，以本文与 STATE 为准。

## 必须如实保留的验证缺口

1. **human_pending**：真实财务 ACCEPT → SAVE → RESUME 及 v2 人工核准没有由本人执行。真实 PDF 候选／review、旧任务进入等待本人已验证；核准图、比率、变化信号正向仅 fake fixture。代理未自动创建财务签核。
2. **固定评测 partial**：15 题中只 5 条真实 intent 观察，10 skipped；5 条均未满足完整层级。2 次模型提案校验成功，3 次规则回退。单／双 Agent 同问题真实运行不证明多 Agent 更优，不外推覆盖率或语义质量。
3. **旧报告回归 fixture 缺失**：较宽回归 141 PASS／57 setup ERROR，后者依赖缺失 `product/validation/d21-real-research.json`。不是业务断言失败，也不能算跳过即通过；未伪造旧已完成研究证明。最终独立 23 项离线检查另记。

## 产品与环境的有限范围

- 官方目录仅美的／格力 2024／2025，3 份预置 READY。发布日期／更正状态未知为 null；不宣称全市场实时搜索。下载失败可手动上传。
- 真实 OCR 为 macOS Apple Vision revision 3，在公开美的 2025 物理第 9 页派生单页扫描执行，68 行／54 候选格，17 候选行／9 列。不是完整原生扫描年报；版式格网有人工复核要求。OCR v2 不自动提升旧来源、Milvus RAG 或财务资格。Linux／其他引擎未验。
- 首页真实 KPI 与历史库存分开于虚构示意财务曲线；没有当前本人核准事实时，实际核准财务图为空。示意开关及水印必须保留。
- 当前是 loopback 本地候选，依赖 Node24／Python 已装依赖与 BGE 模型缓存。Git 不含 PDF、DB、权重或配套 seed 二进制；配套 seed bundle 另交付，不是 clone 即有数据。launcher 进程退出后本地入口不继续运行。
- 阶段事件为持久事件轮询及 SSE 快照重放，不是逐 token 输出；不提供私有思维链。模型解释待人工审阅，引用精确匹配不等于语义正确。
- provider 预算是按验证价格的保守预留，不是实际账单；真实总费用未观测。账本跨代共享，演示 reset 不能补额度。收尾不再重复付费验证。

## 独立审查保留的 P2

- Dashboard KPI 使用有限列表做聚合，超过 archive20／report100 窗口可能低估；旧任务缺排序时间可能被 v2／archive 记录挤出最近列表。当前 2 项／2 报告种子不触发，不影响财务资格。
- 历史报告读取时权限拒绝和来源不可用的区分、报告草稿提交与研究记忆 guard 的边界、重复财务读取的失败关闭仍在先前 M3 审查范围内；当前隔离演示未复现跨用户读取或其他 P0/P1，不因此宣称生产授权模型完备。
- 原生 PyMuPDF 缺独立硬进程 deadline；巨型／恶意文件处理边缘未扩张为生产容灾项目。OCR 有执行期限，不将其当作所有 native 解析超时证明。
- 构建 chunk >500KiB、现有 React fast-refresh／effect／ref lint 提示、PyMuPDF SWIG 弃用和 BGE 退出 semaphore 提示保留；不为求职候选无限调优。

## 已关闭且保留失败证据

M1 Cookie Path 与 owner grant 慢 body 两个旧 P0 经独立 Astra 实际 HTTP／Chromium 复核关闭。手机 OCR 网格外溢、首页／登录全局 CSS 覆盖、模型返回多工具调用、unsupported 表页终止、长 JSON 截断、研究 deep-link 被 URL 规范化丢失均已修并跑对应真实路径。ybr4pane 整 runner 仍为 FAIL（研究阶段完成后，额外 seed 上传缺 Origin）；seed 后补为停止环境内真实 Vision／BGE in-process ASGI。后来完整 UI `06nyuff2` 独立 PASS，不能倒改旧 runner。

没有公开部署、main 合并、force push、覆盖开发者真实数据库或代签财务。原 PDF／私有测试集／V1.2 独立分支保留。普通独立分支研发权限已覆盖本轮集成，不增加像素确认或逐任务审批。
