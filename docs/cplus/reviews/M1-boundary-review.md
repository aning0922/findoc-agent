# M1 boundary review — fixed 132fd7d

审查日期2026-11-03；固定HEAD `132fd7d8a8efd171fef4136c4ccdc1fd7da725ea`；分支 `codex/cplus-m1-boundary-review` 从clean建立。仅本文为写入交付，不改业务代码。审查retrieval_v2（4878→163b0c4）、root 1baad shared_budget/launcher/cookie/retiredGC、finance v3（9ea7→132fd）。**不审本人的DATA模块，不覆盖未来移动HEAD。** 未读.env、密码、真实账本、原开发DB；未启动真实PDF/BGE/provider，付费调用0，无新agent。

结论：未发现可证实P0；有两项P1级提交边界问题应修补后再宣称最终publication fence验收。第一项是finance叶子事务自身可复现的journal竞态；第二项是retrieval叶子事务与root guard的提交协议缺口，已用受控假时钟复现“外层拒绝但内层已提交”，不是声称未接线的生产认证已被突破。root的跨库guard仍属于明确待组装职责，不能以现有nullcontext fake测试宣称完成。

## P1-01 · 财务source journal检查发生在取得读锁之前

位置：`app/financial_statements_v3/service.py:35`，尤其44–50。`ATTACH ...mode=ro`后先查PRAGMA journal_mode，再BEGIN，再由guard实际读source。检查与SHARED lock取得之间存在窗口。

触发条件：另一个能合法维护该临时source DB的连接在PRAGMA之后、guard读取前将journal切到WAL。随后guard读取的是WAL快照，并不阻止别的连接提交source/company变更；本库仍提交使用旧身份的collection（相同tx用于receipt/trend）。本次没有声称正常HTTP能任意改PRAGMA；这是代码声称拒绝WAL的实际TOCTOU缺口，尤其运行环境/维护器可改journal时必须fail closed。

定点复现（独立`findoc-review-wal-race-*` temp；使用合成PDF及既有fake embed/index Harness，不接触真实财报）：

```python
original = service.guard

def racing_guard(db, contexts):
    # 此时tx已在未持source SHARED时检查过journal=delete。
    with sqlite3.connect(temp_documents) as writer:
        assert writer.execute('PRAGMA journal_mode=WAL').fetchone()[0] == 'wal'
    original(db, contexts)
    with sqlite3.connect(temp_documents, timeout=.1) as writer:
        writer.execute('UPDATE companies SET name=? WHERE company_id=?',
                       ('Changed during publication', synthetic_company))
        writer.commit()
service.guard = racing_guard
result = await service.collect(new_uuid, synthetic_doc, synthetic_revision)
```

实测输出：`journal_switch=wal, concurrent_write_committed=True, collection_published=True`；保存名仍“测试股份有限公司”，当前名已“Changed during publication”。没有执行财务确认。

最小补修（FINANCE owner）：BEGIN后对attached source做实际SELECT取得SHARED，再在同连接/事务内检查journal；若已WAL，回滚拒绝；若rollback journal，持SHARED直到inner main DB COMMIT完成。不要只移动一个PRAGMA到BEGIN之后而仍不实际读取。按现`research_memory.publication_guard`的先读后journal校验顺序处理；加一个上述mode切换定点回归即可。修后不能再返回成功collection，且若选择拒绝路径operation保留UNKNOWN。

## P1-02 · 外层guard退出检查不能撤销retrieval已提交对象

位置：`app/retrieval_v2/service.py:72`的tx和540–549的最终嵌套。结构是`with publication_guard: with self.tx(): INSERT ...`；内层sqlite context先COMMIT，外层guard才执行退出逻辑。当前tx没有`identity`/precommit同步回调。

触发条件：身份在最终authorize与guard入口时尚有效，但内层SQLite等待/写入期间越过expires_at；root若在guard退出处复查并抛错，已经无法回滚。持代际互斥锁可以防接管，却不能停止墙上时间。此项不能单靠“root guard finally再查一次身份”解决。

定点fake复现：独立`findoc-review-commit-expiry-*`目录，fake source records、无模型；identity expiry=101、fake clock入口100；tx wrapper在INSERT之后、原tx COMMIT之前置clock=102；外层guard在entry与exit都查expiry。实测**`outer_guard_error=expired-exit`，但`persisted_objects=1`、`operation_state=completed`**。这说明提交协议的失败效果，未把fake源证明成真实source验证。

最小补修（RETRIEVAL owner＋root）：给最终tx增加同步`before_commit`或身份/fence参数，由root在**内层COMMIT之前**检查当前lease/instance/principal/expiry；失败须回滚对象和completed更新，已reserve的UNKNOWN保留。外层持有来源读事务、内层precommit检查身份，两者职责不同。不要靠外层guard退出报错，也不要用nullcontext绕过。pre-provider guard（479–481）释放后调用provider的边界还需root的受预算provider callback自身检查捕获身份/时限；本审查未运行真实provider。

## Root必须落地的publication_guard(identity, fence)协议

现leaf已经把最终对象+operation完成写入放在外层guard内部，接口位置可复用。`fence`可能是context（selected_sources/parent_conversation_id/memory_generation），也可能只有enrollment/build/search的selected_sources；不能假设每种请求都有memory或parent。

1. 绑定当前runtime_root及捕获的workspace/instance/generation/principal/expiry。取得与接管/reset协调的真实身份栅栏；禁止根据浏览器自报identity构造；身份拒绝不得降级为历史数据读取。
2. 固定顺序进入documents、parse-v2（有OCR时）、research-memory（有记忆时）的**只读sqlite连接+显式BEGIN**。对每个相关DB实际SELECT以取得SHARED，随后检查journal支持；拒绝WAL等无法靠该锁阻止并发提交的模式。空BEGIN、提前GET、连接只读标志本身不等于SHARED持续持有。
3. documents事务内重查fast全部身份（workspace/doc/revision/SHA/attempt/parser/company/year/type/basis/period）、invalidated/status及仍存在的公司；OCR走原doc/SHA/attempt→revision和报告metadata hash，**不能要求legacy READY或把failed升READY**。parent conversation如有关联，应在同documents连接中检查workspace、未删除和被允许的关系，不能另开短事务检查完即关闭。
4. parse事务内读取指定artifact而非active/latest，核对原payload输出SHA/config/metadata/parser/选页及completed页面、行/bbox身份；artifact当前性的doc/metadata对比用第3步同一source快照。此时明确OCR只file_transcription_only/financial_authority=false。
5. memory事务读取workspace generation，若使用具体记忆还核对revision/撤销状态。可复用`ResearchMemoryService.publication_guard`，但它只保护memory库，不能代替source/parse/parent。固定加锁顺序，异常时全部rollback/close。
6. 所有上述读事务保持打开，`yield`让leaf执行inner cplus-research.db事务，并保持至其COMMIT返回。使用连接范围内的同步检查，不在锁内启动provider、BGE、parse retry或其他会写同库的异步服务。
7. **不要另开连接对cplus-research.db持SHARED再等它的inner COMMIT**：rollback journal下会阻塞自己的EXCLUSIVE提交。当前context/enrollment是同库immutable objects，可先按owner/hash读回；若后续引入可撤销context状态，应让同一个inner连接验证该状态，或增加明确precommit port，不设计自锁死的guard。
8. 按P1-02增加inner precommit身份检查；guard退出释放外部SHARED。快照字节应继续由既有不可变ObjectStore约束；sqlite读锁不能独自保护任意外部进程改PDF文件。root不能把持DB读锁写成“抵御所有磁盘外部篡改”。

建议root验收一条确定性并发用例：外层已经持source/parse/memory/parent读取锁后，另一连接提交metadata变更、parent删除、memory撤销应等待/失败；inner成功或回滚后才释放；单独覆盖WAL拒绝与inner过期回滚。现retrieval fake tests采用nullcontext，仅证明叶子状态机和provider次数，未证明此并发条件。

## 其余源码核查结论与限制

- Retrieval：operations在任何provider前reserve UNKNOWN；同owner/body重读既有operation、不再次调用；owner含trusted identity hash，root须使用稳定的原lease expires_at而非每个请求重新生成过期时间。provider只在answer的一处调用；异常保留UNKNOWN；returned interpretation保持ai_unreviewed/financial_authority=false。context验证OCR enrollment属于同owner且完整ref相等；精确verifier核对page/line/bbox/text子串和当前artifact身份。fast dense与lexical score独立，旧adapter仅真dense≥.55；未跑相关性评测，不把规则评分称语义支持。
- OCR支持范围：records要求整个artifact state=completed，partial artifact即便所选页完成也会拒绝；这是目前保守功能限制，不是权限升级漏洞。build先写FTS再最终receipt guard，最终guard失败可留下本代未发布索引，后续search会重读/核对源；不能把未完成op称build已发布，需root处理unknown展示。未发现因此绕过最终answer来源核验的复现。
- Finance：time union拒绝instant混duration/起止倒置；当前抽取只支持精确年度列，duration明确1/1–12/31，未知表格跳过/重复metric-time unsupported。Decimal归一和计算使用localcontext，基数<=0不给普通百分比；同值披露冲突要求显式选择。collection/review/receipt不可变，选中快照会重新extract并比对source/cells；确认owner root/expiry在COMMIT前再查，撤销是追加记录，trend重放检查receipt仍有效。owner对象本身不证明当前代/角色，root owner_authorizer和gateway仍须做真实权限；未签署真实财务。超出当前年度/合并/CNY提取范围，不能声称通用所有期间/币种可比性。
- Shared budget：helper为mode=ro，要求绝对无symlink、0600、同uid/单link、same Git common dir及owner工作树canonical data路径、cap字符串5和calls列；没有初始化/重置额度。launcher有provider时C+必须显式指定既有路径；禁用provider模式可不带账本。runtime再次校验C+既有ledger并使用guard wrapper。未打开真实ledger，也未把源码检查等同于真实费用核账。显式same-Git路径是受信root配置，不能推定自动识别“唯一历史账本”。
- Cookie：C+ active/pending名字与C分开，gateway capture读取controller选择的cookie；默认C路径保留。没有据此宣称完整跨端口浏览器隔离验收；cookie本身不按端口隔离，namespace才是该补丁的隔离机制。
- RetiredGC：仅control/active数字目录+controller退休marker；跳过current/seed、无marker、symlink、manifest不匹配、pid/pgid不合法或存活；正向退休记录来自_retire_record验证退出之后；PID复用拒绝信号，旧leader消失但group存活拒绝。路径/seed分离另由DemoConfig保障，launcher限定本项目data和controller名。GC在_reset_lock内，默认保留最近一代；不遍历cache/budget/原C根。没有发现经正常root配置的越界删除复现。恶意本地进程能改控制目录的TOCTOU、bind mount及伪造marker不在已证明防护范围，不能称抗本机任意文件系统攻击。

## 本轮实际验证与交付

- 两个inline临时fake复现：finance journal切换竞态、retrieval过期外层拒绝但inner已提交，输出见上。只在新建测试temp，未修改仓库其他文件或真实资料。
- 精选pytest：`tests/test_cplus_retired_gc.py::test_gc_refuses_current_live_identity_and_nested_symlink` + `tests/test_cplus_demo_namespace.py` → **2 passed / 0.25s**。GC只用owned synthetic temp和fake PID探针。
- 未重跑大套件、真实PDF/BGE/模型、真实共享账本、真实接管GC、未实现的root跨库guard。当前review不涵盖后续root assembly或DATA新版本。根README/STATE及热点均未改。
- 建议状态：**M1 boundary review：修补上述两项后复核；root真实publication guard验收仍PENDING**。没有建议用nullcontext，也没有替原owner修文件。
