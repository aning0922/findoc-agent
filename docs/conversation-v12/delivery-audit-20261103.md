# FinDoc V1.2 Conversation & Memory 代码交付与状态审计

日期：2026-11-03（Asia/Taipei）。本轮范围仅为只读代码审计、复跑已有测试、修订状态文档及提交推送独立开发分支。未开发新功能、未改应用/测试/验证脚本/依赖/CI，未执行财务接受、真实provider请求、main合并或历史重写。

## Git事实与全部改动

- 当前仓库根：`/Users/aipuli/Documents/Projects/findoc-agent`。这是迁移后的原V1.2工作树；Git common directory仍属于原findoc-agent仓库，原main及UX工作树保留。
- 开发分支：`codex/conversation-memory-v12-20261102`。
- 审计/复跑产品HEAD：`77a2e18ff42173d7e555a594a092439c51b116ac`。
- fetch后的`origin/main`：`1f0a3d4131480ac0ea742772127afac3c892fc7c`。初始工作树干净，无待提交产品代码；领先17、落后0；目标远程开发分支初查不存在，17个提交均未被任何已fetch的origin远程引用包含，尚未交付该分支。
- 初始分支误跟踪origin/main；推送命令显式指定开发分支，使用`-u`修正跟踪，不推main、不force、不rebase或amend。
- 产品差异共91文件、10655新增行/17删除行，全部路径与原17提交见 [完整改动清单](delivery-audit-20261103-files.md)。本轮另新增审计报告、文件清单和机器可读验证摘要并更新状态索引/当前路径，仅修交接README末尾一个多余空行。
- 本机原始Git快照及完整patch存于忽略目录`data/conversation-v12-validation/delivery-git-audit-20261103/`，不提交runtime、PDF、依赖目录或凭据。

[开发分支](https://github.com/aning0922/findoc-agent/tree/codex/conversation-memory-v12-20261102) · [相对main全部差异](https://github.com/aning0922/findoc-agent/compare/main...codex/conversation-memory-v12-20261102)

最终审计文档提交不改变已复跑产品树。实际交付HEAD与远程核对结果由本次交付会话输出，远程CI状态另以GitHub Actions为准，不能把本地检查写成远程CI通过。

## 阶段判定

“已完成”指冻结合同下已实现并有相应工程证据；不等于真人业务验收或生产发布。

| 阶段 | 实际判定 | 实现与验收边界 |
| --- | --- | --- |
| A0 合同/设计 | 已完成 | 契约、架构、迁移、风险、桌面/移动状态和分工已冻结；每轮主表重建Graph的无saver调整有明确依据 |
| A1 持久化/幂等 | 已完成 | Conversation/Turn/operation、SQL互斥、claim fencing、不可变终态、只读GET及启动中断收口已接通；A1-01已修复关闭 |
| A2 多轮与工具 | 已完成（本版保守范围） | 规则指代解析+有限Graph，原文/确认事实/确定性比较已接通，范围不明先澄清。自由解释关闭，非通用自主规划器 |
| A3 前端 | 已完成（实现及已有自动化） | `/conversations`、事实选择、真实PDF、偏好管理、UNKNOWN/多标签恢复、390/1440均有实现与回归；旧深链保留 |
| A4 质量闸口 | **部分完成** | 新旧自动化与有限真实检索有证据；完整真人财务接受后再提问及部分端到端专项未完成，不能宣布P0发布闸口全过 |
| B1 长期偏好 | 已完成（有限枚举研究偏好） | 独立确认、CRUD、revision、operation回执、墓碑与跨会话fresh recall均接通；非自由文本/企业事实记忆库 |
| B2 上下文与召回 | 已完成（核心实现及后端覆盖） | 最近8轮/4096 token、摘要512、偏好256；结构摘要只取最多32旧轮、保留2版；25轮/重建/歧义屏障/删除竞态已有后端用例。长会话与进程重启的浏览器专项未做 |
| G 真实验证/交付 | **部分完成** | 旧3项代码finding已关闭，有实际provider/BGE/Milvus与只读案例；真人语义/财务核准仍pending，未部署或发布 |

## 正式接入核验

| 能力 | 实际调用链（产品快照） | 结论与限制 |
| --- | --- | --- |
| 正式装配 | `app/api/runtime_factory.py:324–335`构造Repository/Memory/Tools/Graph/Service并挂两个router | 正式handler是ConversationGraph；测试fake_handler不用于正式runtime |
| 多轮与上下文 | `app/conversations/graph.py:32–75` → `context.py:42` → resolve → tools | 从已提交Turn、当前偏好、结构摘要每轮重建；完整问题保留谓词/否定，仅支持有限指代语法 |
| 会话恢复 | `repository.py:499`启动封存running；`service.py:67`下一次明确发送；API GET直接查仓储 | 恢复历史和新轮；不续跑中断Graph节点、不自动重新收费；供应商端exactly-once不作保证 |
| 原文与引用 | `tools.py:55`调用RAGService.answer_selected，旧Result校验，再转换引用DTO | 是实际复用，版本化检索最终调用MilvusClient.search；不是只返回假文本 |
| 财务工具 | `tools.py:128/173/207`恢复local_operator事实、资格与完整来源，调用既有FinancialAnalysisService/Decimal；仓储finish内复验完整事实组 | 只读确认事实及比较；不自动ACCEPT/SAVE/RESUME。缺少有效明确选择时拒绝精确计算 |
| 偏好写入/召回 | runtime共享MemoryService；`graph.py:106`仅从用户原话产候选，前端明确动作才写；`context.py:42–75` fresh recall并进入原文工具背景 | 已跨会话接通，generation在调用前和提交时复验；偏好不改变来源授权或财务公式 |
| 删除与防复活 | `app/memory/repository.py:173–247` revision/墓碑/generation；context排除旧候选；summaries按generation与provenance复验 | 删除当前正文并阻止后续Memory注入；不撤回已发送给供应商的内容，也不改旧回答。删除会话仅detach偏好出处，保留明确偏好 |

## 实际测试与证据层次

当前复跑的产品树固定为77a2e18；报告与路径文档可在运行期间编辑，应用/前端/测试/脚本不改。所有重叠/重跑组不求和。

| 检查 | 本轮结果 | 层次与原始记录 |
| --- | --- | --- |
| 完整后端pytest | **1690 PASS / 1 SKIP / 0 FAIL**，1050.08秒，exit0 | `data/conversation-v12-validation/delivery-audit-20261103/`，`-q -rs -p no:cacheprovider`；QA核验旧隔离proof数据库/外键/对象SHA后作为回归fixture复用，未伪造真人记录 |
| CI范围Ruff | **两组均通过，exit0** | 同目录manifest及每命令exit |
| 前端单测 | **209 PASS / 25 SKIP / 0 FAIL**，exit0 | 当前77a2e18/Node24.19.0；`delivery-frontend-audit-20261103/`。25项缺私有D28精确载荷，无改断言或假造fixture |
| lint/build/audit | 均exit0，audit **0漏洞** | 同前端目录。保留既有Fast Refresh warning和>500kB chunk提示 |
| 新会话21浏览器 | **21 PASS / 0 FAIL / 0 SKIP / 0 flaky / 0 retry**，162.19秒，exit0、servers_stopped=true | 当前固定77a2e18；真实HTTP/SQLite/PDF及正式Graph，model/BGE/vector为显式替身；`delivery-browser-audit-20261103/` |
| 原controlled Agent浏览器 | **2 PASS / 0 FAIL / 0 SKIP**，2.9秒，exit0；端口关闭、临时runtime清理 | 当前77a2e18；原CI规格、单worker无retry，替身；`delivery-browser-audit-20261103/controlled-agent/` |

本轮新21的S4 proof再次观察到真实Graph context：未保存=[]；明确UI保存后新会话=cash_flow；明确删除后新会话及原会话=[]，generation3→4→5，写入仅POST/DELETE各一次。UNKNOWN/两标签/G02/G03/C09/两视口PDF关键proof均核对，未触现有preview服务。

本轮完整pytest没有排除local_data；唯一SKIP缺`data/day43_data_v2`，原-rs行保留。原日志显示旧工作树源位置，当前同名测试存在且产品树固定；5条既有SWIG warning及gRPC keepalive GOAWAY/too_many_pings诊断保留，未转成测试失败（最终exit0）。与旧1681相比新增9项来自此前G回归，本轮1690为当前固定产品树结果，不与旧组相加。

可随分支读取 [机器可读验证摘要](delivery-validation-20261103.json)：包含实际命令/退出码/计数、source tree IDs及原始日志SHA；PDF/runtime/凭据和完整私有原始档案保持本机忽略，不为推送伪造资产。摘要是本机观察记录，不是不可伪造的远程证明。

### 历史验证：本轮核验档案，不冒充当前复跑

- `a4-v12-final-21-01`：ad12570固定产品/测试21PASS、0失败/跳过/retry，实际HTTP/SQLite/PDF，模型/BGE/Milvus替身，human_acceptances=0。
- 旧浏览器：默认Agent2、QA12、reading4、report20、financial boundary18、来源失效1均通过；模拟财务接受明确标记。各组fresh经营种子旅程重复，不求和。
- 旧报告后端83PASS；旧完整后端1681PASS/1SKIP是运行期间共享树发生G变更的集成快照，旧G后相关284PASS另列，不冒充当时固定SHA全量。
- QA发现旧`--legacy-extra`归档实际复用了`results.json`：后置规格JSON覆盖种子JSON，独立`legacy-extra-results.json`并不存在。种子PASS仍有文本日志/journey proof，后置规格有JSON；不能宣称两份独立机器结果，更不能重建/改写原记录来补档。具体差异存`delivery-audit-20261103/archive-findings.json`。
- 历史g-live-01保留insufficient：Milvus观察挂错legacy入口，不能补造次数。g-live-02在新runtime取得2实际provider响应（配置deepseek-v4-flash，response.model实际deepseek-flash）、5BGE（含预热/索引）、4物理Milvus成功/0失败；两个原文quote、两个未确认计算拒绝、一次范围澄清；历史重读新增provider0，财务写0。
- 2026-11-03对正在使用的g-live-02预览runtime做SQLite只读观察：1会话、5轮（3completed/2refused）、财务接受回执0、已确认财务事实0、当前偏好1条。当前偏好计数不用于推断其操作者或宣布完整真人保存/删除旅程通过；当前语义复核仍无用户明确通过记录。原始观察存`delivery-git-audit-20261103/current-runtime-state.json`。
- g-live-02状态仍`observed_pending_human_review`，human_acceptances=0。本次审计**未重跑真实provider或真人业务**，真实模型执行不等于财务语义与业务准确率验收。

## 阻断与未完成项

1. A4/G真人业务验收：PDF原文语义、年份/单位/页码核对，以及用户明确接受/单独保存事实、选择当前披露版本再提问的正向旅程仍待用户。没有将simulated_test变成真人local_operator核准。
2. 尚缺新助手C12已确认财务Action的正向PDF UI、20+轮摘要浏览器专项、真实进程重启浏览器专项及完整辅助技术/触屏软键盘覆盖。已有后端用例不扩大为这些浏览器结论。
3. 私有数据导致显式skip，须准备对应原始冻结资产才可补测；不能以删除skip/改fixture获得全绿。
4. 正式runtime仍依赖有效模型配置、本地BGE/Milvus和单进程owner；本地单人demo不宣称认证、多租户或生产隔离。自由解释、OCR等仍在本版范围外。
5. GitHub推送和远程CI以交付时实际命令/远程SHA/Actions状态为准。本地检查不代替远程CI；无main合并、部署或发布。

本轮独立可见聊天分别负责架构阶段判定（Astra/high）、正式接线（GPT-6.1/high）、Memory（GPT-6.1/medium）、前端质量与浏览器（medium→high）、后端测试与档案（GPT-6.1/high，容量受限后切换GPT-6.1 Terra/high继续同一后台进程）。主控负责Git操作、证据汇总和唯一提交；源码审查没有伪装成各审查聊天独立跑过测试。
