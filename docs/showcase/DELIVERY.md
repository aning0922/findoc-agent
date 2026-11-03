# 本地交付说明草案（2026-11-03）

当前交付是独立集成工作树中的本地演示入口、静态预置资料与研究流程。最终reset、完整seed后的浏览器UI及本地常驻启动/退出尚待root验证；本文不作为这些项目的通过声明。README由root维护。

## 本机启动

在集成checkout使用已有依赖运行，不自动安装包或模型：

```sh
.venv/bin/python scripts/run_showcase_local.py --init-config
.venv/bin/python scripts/run_showcase_local.py --check
.venv/bin/python scripts/run_showcase_local.py
```

首次init生成被Git忽略、600权限的data/showcase-local.env；本人在本机文件查看账号与随机密码，不复制到聊天/Git/ZIP。重复init拒绝覆盖。默认仅127.0.0.1:14530，wait_only，模型关闭。页面示意图保留水印，不等于财务核准。

Root显式启用真实模型时，将同仓库原checkout的600且Git忽略的.env作为 `--llm-config /本机路径/.env` 传入；不复制密钥。路径所属Git根及common-dir必须真实匹配集成树，拒绝任意其他仓库或链接。只读取四个LLM白名单键，拒绝非已验证DeepSeek flash配置。DEMO登录配置仍只能在当前集成树data内。现存5元共享账本必须在本集成树data/showcase-cost-control/provider-budget.db；不重建或重置。Ctrl+C停止本次启动的进程组，详细参数与强杀限制见reviews/M5-local-launcher-handoff.md。

## 已有证据及范围

根据root的EVIDENCE.md和E03-seed-handoff记录：已验证演示目录为美的/格力2024/2025四份。新静态seed实际库存为3官方READY年报（格力2024/2025、美的2025）和美的2025物理第9页派生扫描样本；不是四份全部READY，也不是原生扫描披露年报。OCR派生输入仍legacy_source_verified=false，不授予财务资格。

E03 manifest SHA为 `efc10a4b48584747130af71ec82171a4e5f766fc53eb1ea92c21fe319e7b3ff4`。28个manifest文件、约65.7MB；含2真实completed研究job、2报告共3revision、1示例会话、2演示note及68行/54候选格OCR产物。complete_product_seed=true只表示静态库存条件满足。构建、源SHA不变、物化副本service读取和历史archive来源复验已有记录；不等于最终浏览器/reset验收。历史archive不继承旧lease授权，capabilities全部false；没有财务receipt/acceptance/factset。

真实研究已留存单/多Agent、报告版本与实际PDF证据。5zk9mqeo记录4/7次尝试及约14.17s/26.27s；ybr4pane的实际main UI研究阶段约9.554s/16.480s、三宽无溢出。ybr runner在额外扫描上传时因测试Origin缺失失败，completed=false必须保留；后续补材料是停止环境内真实Vision/BGE in-process ASGI，不能改称原runner整体通过。详见EVIDENCE.md、evidence/M3-research/retained-failures.json和evidence/E03-full-seed-verification.json。

共享预算记录截至ybr为44次真实provider调用，保守预留0.803322元/5元，实际账单扣费not_observed。该数值是已存时点，不是当前余额、发票费用或剩余调用额度；新调用由root统一预算proxy记录。多Agent不保证更好，固定15题尚不能据此宣布通过率；eval目录提供题集、有限intent执行器和只读已存结果汇总。

## 待完成与使用限制

最终完整seed重置/跨代回归、最后UIQA及launcher真实启动/退出由root另验。本人财务ACCEPT、SAVE、RESUME及扩展财务独立核准尚为human_pending，代理不代办；无回执不输出已核准图表或金额。打印链接需服务和权限，点击打印不等于文件下载成功。登录配置、原PDF、数据库和模型缓存不纳入源码公开包。
