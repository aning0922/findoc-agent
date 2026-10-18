# 开发与测试

完整应用使用 Python 3.11+、uv、Node.js 24 和 npm。以下命令均从仓库根目录执行，采用 macOS / Linux shell 写法。首次安装和启动见 [README](../README.md#快速开始)；仅浏览已有案例可运行[静态演示](../demo/README.md)。

## 模型与存储配置

将 [.env.example](../.env.example) 复制为 `.env`，填写模型接口信息：

| 配置项 | 用途 |
| --- | --- |
| `LLM_API_KEY` | 模型服务凭据。 |
| `LLM_MODEL` | 服务商提供的实际模型名称。 |
| `LLM_BASE_URL` | OpenAI 兼容 Chat Completions 接口的基础地址。 |
| `LLM_TIMEOUT_SECONDS` | 每次模型请求的超时时间，模板值为 30 秒。 |
| `FINDOC_RUNTIME_ROOT` | 通过启动终端设置的独立绝对路径，用于保存文档、索引和业务记录。 |

Agent 工具调用要求所选模型支持 `tools`。`--env-file .env` 由 Uvicorn 读取配置；应用启动时还会检查模型配置、预热 bge-m3 并初始化存储。

当前嵌入模型为 `BAAI/bge-m3`，索引使用运行目录中的 Milvus Lite。本地启动无需单独部署 Milvus 服务。HTTP 上传使用 PyMuPDF / pdfplumber 解析文本层 PDF；扫描件 OCR 不在该路径中。

已有 MinerU `content_list.json` 可由适配器读取。需要另行运行 MinerU 工具时，可用 `uv sync --frozen --extra mineru` 安装可选依赖；该依赖不会将 HTTP 上传自动切换为 MinerU 解析。

示例启动目录为 `$PWD/data/analyst-runtime`。此入口拒绝项目默认的 `data/runtime`，以便区分独立运行数据；名称中的 `analyst` 沿用工作台名称。重启后应使用同一路径，新增路径会得到空的企业与研究目录。

## 页面与 API 入口

前端默认地址为 `http://127.0.0.1:5173`，后端默认地址为 `http://127.0.0.1:8000`。

| 前端路径 | 用途 |
| --- | --- |
| `/` | 我的研究：新建企业或研究、查看待办与历史。 |
| `/companies` | 企业与资料；选择企业后查看年报和财务记录。 |
| `/evidence` | PDF 审阅、候选接受与财务事实保存。 |
| `/research?mode=qa` | 原文问答，无需先建立经营研究任务。 |
| `/research?mode=operating` | 单企业跨年或双企业同期经营研究。 |
| `/reports` | 草稿、已保存报告、版本选择与下载。 |
| `/legacy` | 兼容单文档 RAG / Agent 工作台。 |

API 文档位于后端 `/docs`。前端通过 Vite 将 `/api` 代理到后端，并去掉该前缀。例如，浏览器的 `/api/companies` 对应后端 `/companies`。

后端使用其他端口时，在启动前端的终端设置 `FINDOC_API_ORIGIN`：

```bash
FINDOC_API_ORIGIN=http://127.0.0.1:8001 npm --prefix frontend run dev -- --host 127.0.0.1
```

页面已提供企业创建、年报上传和数据核对入口；API 文档用于查看请求格式、调试或集成。

## 测试与 CI

### 基础验证

安装完整开发依赖后，下面的后端检查使用合成资料、临时存储和测试替身，不需要年报原文件或模型凭据：

```bash
uv sync --frozen
uv run pytest \
  tests/test_controlled_agent_app.py \
  tests/test_parse.py \
  tests/test_demo_pdf.py \
  tests/test_revenue_research_api.py \
  tests/test_runtime_revenue.py \
  tests/test_d26_calculation_intent.py \
  tests/test_d29_c1_focus_api.py -q
```

前端测试与构建：

```bash
npm --prefix frontend ci
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix frontend run build
```

运行受控浏览器回归前，先安装 Chromium：

```bash
npm --prefix frontend exec -- playwright install chromium
npm --prefix frontend run test:e2e
```

浏览器套件使用真实 FastAPI、Vite、Chromium 和临时 SQLite，模型与检索为测试替身。默认端口是后端 `18080`、前端 `14173`；已占用时测试会失败，可以通过 `FINDOC_E2E_API_PORT` 和 `FINDOC_E2E_WEB_PORT` 指定其他空闲端口。

[Quality 工作流](../.github/workflows/quality.yml)采用 Python 3.12、Node.js 24、Ubuntu 和 `checks` 依赖组，执行同一组后端检查、前端检查和浏览器回归。该依赖组不安装完整嵌入模型运行栈；运行应用时应使用默认 `uv sync --frozen`。

### 依赖外部资料的检查

公开版保留了历史测试源码，但完整后端测试集和其他浏览器套件还需要额外资料。因此，基础验证以上述命令和 CI 为准。

| 资料 | 准备方式 |
| --- | --- |
| 真实年报 PDF | 按 [sources.json](../product/validation/sources.json) 中的来源、路径和 SHA-256 准备；文件保存在被 Git 忽略的 `data/`。 |
| 财务字段基准 | [manual-benchmark.json](../product/validation/manual-benchmark.json) 与 [gold-summary-cells.json](../product/d26/gold-summary-cells.json) 已随源码提供。 |
| 历史审阅原件 | 25 项前端审阅测试在缺少原件时标记 `skipped`。有访问权限的维护者可用 `FINDOC_REVIEW_FIXTURES` 指向包含 `qa-real/` 和 `human-followup/` 的资料目录。 |
| 报告运行快照 | 对应集成测试通过 `FINDOC_REPORT_TEST_PROOF` 或 `FINDOC_MIGRATION_TEST_PROOF` 接收测试资料索引；索引及其数据库须按测试要求另行准备。 |

显式指定的历史审阅目录无效时，测试会报错，不会静默跳过。上述资料与真实模型效果不由受控 CI 代替验证。

`scripts/`、`experiments/` 和 `eval/` 还保留解析、评测及阶段性验证工具。运行前需检查其输入与输出目录；应用启动不依赖这些历史脚本。

## 常见启动问题

| 现象 | 检查项 |
| --- | --- |
| 后端提示缺少模型配置 | 检查 `.env` 中四个 `LLM_*` 字段，以及启动命令是否包含 `--env-file .env`。 |
| 首次启动较慢 | bge-m3 需要下载或加载；查看终端中的下载与初始化状态。 |
| 提示运行目录无效 | `FINDOC_RUNTIME_ROOT` 必须是绝对路径，且不能指向默认 `data/runtime`。 |
| 重启后看不到之前的资料 | 核对两次启动使用的运行目录是否相同。 |
| 前端无法读取资料 | 确认后端已启动，Vite 代理地址与后端端口一致。 |
| 原文问答拒绝计算增长率 | 先核对并保存财务事实，再使用财务分析或经营研究。 |

接口与模块职责见[系统架构](architecture.md)。公开源码的来源摘要和发布时验证数据保存在 [source-snapshot.json](source-snapshot.json)；该文件记录初始发布状态，后续 CI 结果以对应提交为准。
