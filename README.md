<div align="center">

# FinDoc Agent

**面向财报研究的 Agent 应用 · 让每个结论都有据可查**

从年报 PDF 到财务分析、原文问答与研究报告，连接数据、证据和判断。

![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![React](https://img.shields.io/badge/React-19-149ECA?style=flat-square&logo=react&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=flat-square&logo=typescript&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![Status](https://img.shields.io/badge/Status-Active_Development-2563EB?style=flat-square)

[功能概览](#功能概览) · [工作流程](#工作流程) · [快速开始](#快速开始) · [技术架构](#技术架构) · [项目文档](#项目文档)

</div>

---

FinDoc Agent 是一个面向中文企业年报的 Agent 应用，结合 **RAG、受控工具调用、LangGraph 工作流与人工确认**，将资料管理、财务核对、多文档问答和报告整理连接起来。产品工作台沿用 FinDoc Analyst 名称，用户可以从指标或引用回到原始 PDF，核对金额、单位、披露年度与来源版本，再形成研究结论。

项目围绕三项原则构建：**财务数据经人工确认后用于分析，模型解释保留待审状态，研究结果与证据按版本保存。**

![FinDoc Analyst 研究工作台](docs/images/home-1440.png)

<sub>正式 React 组件读取已保存历史的验收截图，保留隔离提示。截图来源与状态见[界面说明](docs/project-status.md#界面截图)。</sub>

## 功能概览

| 功能模块 | 核心能力 |
| --- | --- |
| **企业概览** | 按企业组织年报、财务期间与披露版本，集中查看营业收入、归母净利润和经营活动现金流量净额。 |
| **财报资料库** | PDF 上传与处理状态、企业及年度绑定、版本化原文读取，以及可追踪的来源纠错。 |
| **财务分析** | 财务候选审阅与确认、事实持久化、单企业跨年分析、双企业同期比较，以及可回到原文的图表。 |
| **AI 研究** | 在显式选定的报告范围内问答；通过有限研究模板结合财务分析与经营原文，保存任务、人工等待状态和研究结果。 |
| **研究报告** | 从已完成研究生成结构化草稿，编辑标题与结论，保存不可变版本，读取历史并导出指定版本的 Markdown。 |

### 从数字回到原文

PDF.js 阅读器支持物理页定位、缩放、引用切换与经校验的金额区域高亮。引用同时绑定文档、来源版本和页码；来源发生变化时，系统撤下过期展示。没有可靠坐标时保留原页与原文，供用户核对。

<details>
<summary><strong>查看经营研究与财务变化</strong></summary>

![经营研究与三项财务变化](docs/images/midea-1440.png)

<sub>冻结历史阅读：三项财务变化、原始金额、精确差额与证据入口。模型解释的语义审阅状态独立保留。</sub>

</details>

### 将事实、计算和解释分开

- **财务事实**：保留原始金额、单位、规范化数值、合并口径、披露版本与接受凭证。
- **确定性分析**：由服务端使用 Decimal 计算差额、同比或同期相对差异；缺失期间、口径冲突和无效基数有明确状态。
- **AI 解释**：回答附带经校验的引用，证据不足时拒答；经营解释保留人工语义复核状态。
- **报告版本**：保存事实、分析、原文和用户编辑的独立快照；历史读取与导出复用已保存结果，不重复执行模型或财务计算。

## 工作流程

```text
企业与年报 PDF
      │
      ▼
解析与索引 ──→ 来源版本、物理页与原文证据
      │
      ├── 财务候选 → 原文核对 → 人工确认 → 财务事实 → 跨年 / 同期分析
      │
      └── 选定报告 → 向量检索 → 引用校验 → 多文档问答 / 经营研究
                                                    │
                                                    ▼
                                      结构化草稿 → 保存版本 → Markdown 导出
```

财务研究任务在缺少已确认事实时进入人工等待。用户完成审阅后显式继续执行；任务在限定的步骤、工具、检索和模型调用预算内运行。来源变化或接受撤销会影响结果的当前可用状态，已保存的历史快照仍保留用于审计。

## 本地只读演示

不配置模型也可以先体验已保存研究、可信问答、报告版本和下载路线：

```bash
python3 demo/serve.py --port 14406
```

在仓库根目录执行后，打开 [http://127.0.0.1:14406/projects/findoc/](http://127.0.0.1:14406/projects/findoc/)。这是独立的静态历史阅读器，不运行模型或写入业务数据；完整 React 工作台按下方步骤启动。

## 快速开始

### 1. 准备环境

- Python **3.11+** 与 `uv`
- Node.js **24** 与 npm；仓库提供 `.nvmrc`
- 可用的 OpenAI 兼容模型接口凭据
- 本地磁盘空间，用于 bge-m3 模型缓存、PDF、SQLite 与 Milvus Lite

`main` 提供当前产品的公开源码快照、测试与静态演示。完整开发历史和内部验收附件保留在私有归档。从主分支安装：

```bash
git clone https://github.com/aning0922/findoc-agent.git
cd findoc-agent
uv sync --frozen
nvm use
npm --prefix frontend ci
```

首次启动会加载 `BAAI/bge-m3`；未缓存时需要下载模型。HTTP 上传使用 PyMuPDF / pdfplumber 解析路径。读取现有 MinerU JSON 无需安装完整 MinerU；需要离线运行 MinerU 工具时可执行 `uv sync --frozen --extra mineru`。

### 2. 配置模型

```bash
cp -n .env.example .env
```

在 `.env` 中填写以下配置。模型名称与接口地址使用所选服务商提供的实际值：

```dotenv
LLM_API_KEY=your-api-key
LLM_MODEL=your-model-name
LLM_BASE_URL=https://your-provider.example/v1
LLM_TIMEOUT_SECONDS=30
```

运行时使用以上 `LLM_*` 配置；`.env.example` 中其余兼容示例项不是当前启动的必填项。`.env` 已被 Git 忽略。

### 3. 启动后端

在仓库根目录执行，使用独立的数据目录：

```bash
export FINDOC_RUNTIME_ROOT="$PWD/data/analyst-runtime"
uv run uvicorn app.api.runtime_factory:create_isolated_runtime_app_from_env \
  --factory \
  --env-file .env \
  --host 127.0.0.1 \
  --port 8000
```

`FINDOC_RUNTIME_ROOT` 必须为绝对路径。首次启动会初始化本地存储并预热向量模型；后续使用同一路径读取已有资料与历史。保持单进程运行，避免开发热重载中断文档处理任务。

### 4. 启动前端

另开终端，在仓库根目录执行：

```bash
nvm use
npm --prefix frontend run dev -- --host 127.0.0.1
```

| 入口 | 地址 |
| --- | --- |
| 我的研究 | [http://127.0.0.1:5173/](http://127.0.0.1:5173/) |
| 企业与资料 | [http://127.0.0.1:5173/companies](http://127.0.0.1:5173/companies) |
| 原文审阅与财务确认 | [http://127.0.0.1:5173/evidence](http://127.0.0.1:5173/evidence) |
| AI 研究工作台 | [http://127.0.0.1:5173/research](http://127.0.0.1:5173/research) |
| 研究报告 | [http://127.0.0.1:5173/reports](http://127.0.0.1:5173/reports) |
| API 文档 | [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) |

Vite 将 `/api` 请求代理到本地 `8000` 端口。已有单文档 RAG / Agent 工作台保留在 `/legacy`。

### 5. 导入第一份资料

新数据目录不预置企业和年报。可先通过 API 文档中的 `POST /companies` 建立企业，再用 `POST /report-documents` 上传 PDF 并绑定企业、报告年度与会计口径。文档进入 `ready` 后，在原文审阅页核对财务候选，显式接受并保存事实，再开展财务分析与研究。

如需先体验单文档上传和问答，可生成一份完全虚构的中文示例 PDF，再从 `/legacy` 上传：

```bash
uv run python scripts/generate_demo_pdf.py
```

默认输出到 `artifacts/demo/synthetic_finance_demo.pdf`；已有同名文件时生成新文件名。该资料用于解析与基础问答演示，完整财务研究需使用符合支持范围的年报。

## 技术架构

| 层次 | 技术与职责 |
| --- | --- |
| Web 界面 | React 19、TypeScript、Vite、Recharts、PDF.js；企业工作空间、分析图表与原文阅读。 |
| API 与业务合同 | FastAPI、Pydantic；严格输入校验、来源范围控制与结果状态。 |
| 文档处理 | PyMuPDF、pdfplumber、MinerU 输出适配；正文、表格、页码和布局信息。 |
| 检索与问答 | bge-m3、Milvus Lite、中文分块、引用校验与证据不足拒答。 |
| 研究执行 | 受控工具调用、LangGraph 持久工作流、人工等待与执行预算。 |
| 财务与报告 | Decimal 计算、人工确认事实、结构化报告、不可变版本与 Markdown 导出。 |
| 本地存储 | SQLite 保存业务记录、事实、研究和报告；文件存储保存 PDF；Milvus Lite 保存检索索引。 |
| 工程验证 | pytest、Ruff、mypy、前端单元测试与 Playwright 浏览器回归。 |

```text
app/
├── api/           # HTTP 路由、DTO 与运行时装配
├── companies/     # 企业、报告元数据与数据库迁移
├── documents/     # 上传、解析、来源版本与原文证据
├── rag/           # 分块、向量索引、检索与可信问答
├── agent/         # 工具执行、财务确认、事实与确定性分析
├── research/      # 研究模板、任务状态与持久化
├── reports/       # 报告构建、版本仓储与导出
└── chat/          # 单文档聊天与 SSE 适配
frontend/          # 产品界面、PDF 阅读器与浏览器测试
docs/              # 架构、开发指南、功能状态与界面截图
demo/              # 无需模型的静态历史演示
product/           # 公开报告 schema 与固定测试资料清单
tests/             # 后端测试
scripts/           # 验证、数据准备与运行工具
eval/              # 检索、RAG 和 Agent 评测资产
data/              # 本地运行数据，Git 忽略
```

## 开发与验证

完成依赖安装后，可运行基础检查：

```bash
# 文档解析与合成资料
uv run pytest tests/test_parse.py tests/test_demo_pdf.py -q

# 前端单元测试、静态检查与构建
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix frontend run build

# 受控浏览器回归
npm --prefix frontend exec -- playwright install chromium
npm --prefix frontend run test:e2e
```

受控浏览器回归使用隔离存储与模型、检索替身，覆盖真实浏览器和 API 交互。公开版保留应用源码、自包含测试和公开资料清单；历史运行数据库、内部验收记录与浏览器 trace 不随源码分发。部分历史集成测试需要另外准备年报或运行快照，复现范围见[开发与测试](docs/development.md)。原始财报 PDF、模型缓存和密钥不随仓库分发。

## 当前范围

当前版本面向**本地单人研究**，已实现企业资料、三项核心财务指标、原文查证、研究任务和报告版本导出的主要模块，持续完善完整业务验收与使用体验。

- 财务抽取支持营业收入、归母净利润、经营活动现金流量净额；现有规则主要针对已验证的中文文本层年报版式。
- 财务确认、财务计算与经营解释的状态分别记录。已有自动化及真实模型验证记录，已有四报十二项事实的本人接受、三项真实研究、三份报告六个版本及重启下载验证；新问答和经营解释的人工语义审阅仍待完成。
- 当前使用本地单工作空间，尚未提供多人身份认证、生产级权限体系或分布式任务调度。文档处理采用进程内任务，进程中断后的自动续跑尚未实现。
- 研究报告可按指定保存版本导出 Markdown；导出前重新核验来源和事实资格。文件中的 PDF 链接依赖原 FinDoc Agent 服务及对应原文件。

## 项目文档

| 文档 | 内容 |
| --- | --- |
| [系统架构](docs/architecture.md) | 模块职责、受控 Agent、检索与财务事实的边界。 |
| [开发与测试](docs/development.md) | 独立环境、启动入口、测试命令与外部资料要求。 |
| [功能状态与截图](docs/project-status.md) | 已有能力、历史验证、截图来源与当前限制。 |
| [静态演示](demo/README.md) | 已保存研究、问答、报告版本与下载路线。 |


---

<div align="center">

<strong>回到原文，核对数据，再形成研究结论。</strong>

</div>
