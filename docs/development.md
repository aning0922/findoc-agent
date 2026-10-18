# 开发与测试

使用 Python 3.11+、uv 和 Node.js 24。安装与正式启动命令见[README](../README.md#快速开始)。模型凭据写入被忽略的 `.env`；通过 `FINDOC_RUNTIME_ROOT` 指定独立绝对路径，避免把演示数据和已有研究混在一起。

## 入口

| 入口 | 用途 |
| --- | --- |
| `/` | 研究首页与历史入口。 |
| `/companies` | 企业与资料。 |
| `/evidence` | 原文审阅、接受与财务事实保存。 |
| `/research` | 原文问答及经营研究。 |
| `/reports` | 报告草稿、保存版本与下载。 |
| `/legacy` | 原有单文档 RAG / Agent 工作台。 |
| 后端 `/docs` | API 输入合同与调试入口。 |

## 自包含检查

以下检查使用临时数据或合成资料，不需要个人数据库、年报原文件或真实模型调用：

```bash
uv sync --frozen
uv run pytest tests/test_parse.py tests/test_demo_pdf.py tests/test_revenue_research_api.py tests/test_runtime_revenue.py tests/test_d26_calculation_intent.py tests/test_d29_c1_focus_api.py -q
nvm use
npm --prefix frontend ci
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix frontend run build
npm --prefix frontend exec -- playwright install chromium
npm --prefix frontend run test:e2e
```

默认前端检查中有 25 项精确历史审阅回归依赖私有 Run/Report 原件，缺少资料时明确标记 skipped，其他检查正常执行。具有原件访问权限的维护者可以设置 `FINDOC_REVIEW_FIXTURES` 为包含 `qa-real/` 和 `human-followup/` 的目录；显式指定无效目录会报错，不会静默跳过。公开版未使用模拟数据冒充这些历史原件。

受控浏览器脚本创建临时 SQLite，使用替身模型和检索，运行真实 FastAPI、Vite 与 Chromium。后端 `/health` 和浏览器目录核对用于确认连接到本次服务；测试后回收临时进程。它验证交互合同，不代表真实模型准确率。

CI 使用锁文件中的 `checks` 依赖组运行受控验证，不下载嵌入模型或访问真实模型接口；本地完整运行仍使用默认 `uv sync --frozen`。

## 真实资料与历史测试

`product/validation/sources.json` 保留四份公开年报的来源 URL、固定 SHA-256 和本地路径。需要真实 PDF 的测试应另行获取原文件并校验，PDF 不进入 Git。`manual-benchmark.json` 与 `product/d26/gold-summary-cells.json` 是固定财务字段基准，不构成新的人工接受记录。

公开版保留历史测试与工具源码，但不包含旧运行数据库、完整浏览器 trace、内部命令日志或历史报告运行快照。依赖这些数据的测试不是无条件可执行的公开基线；例如报告历史回归需要显式准备隔离运行快照，再通过 `FINDOC_REPORT_TEST_PROOF` / `FINDOC_MIGRATION_TEST_PROOF` 指向自己的测试资料。不要直接运行历史脚本去访问他人的数据路径。

`scripts/`、`experiments/` 和 `eval/` 保留工程验证与评测代码。正式产品入口为 `app.api.runtime_factory:create_isolated_runtime_app_from_env`，无需运行逐阶段验证脚本。

## 公开版来源

此仓库以一次独立源码快照发布。正式应用与前端源码继承已整合产品主线，完整开发历史在私有归档保留；公开 Git 历史不会包含已排除的附件。`docs/source-snapshot.json` 记录来源版本与代码文件摘要。

静态演示运行方法见[演示说明](../demo/README.md)。公开源码与静态历史展示使用不同入口，演示不会创建任务、接受事实或执行模型。
