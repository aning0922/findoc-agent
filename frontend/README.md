# FinDoc Agent Web

前端使用 React、TypeScript 和 Vite，结合 PDF.js 展示原文，使用 Recharts 展示财务变化。主导航为“我的研究”“企业与资料”和“报告”。

## 本地开发

需要 Node.js 24。下面的命令均从仓库根目录执行；使用 nvm 时，可先运行 `nvm install` 和 `nvm use`。

```bash
npm --prefix frontend ci
npm --prefix frontend run dev -- --host 127.0.0.1
```

默认访问地址为 [http://127.0.0.1:5173/](http://127.0.0.1:5173/)。后端需按[根目录 README](../README.md#快速开始) 单独启动。

Vite 将 `/api` 代理到 `http://127.0.0.1:8000` 并移除此前缀。后端使用其他地址时，可在启动前设置 `FINDOC_API_ORIGIN`。前端使用该环境变量进行开发代理，不读取模型凭据。

`npm ci` 会从锁定的 PDF.js 包复制字体、CMap 和 wasm 资源；worker 随构建发布，阅读器不依赖外部 CDN。

## 检查与构建

```bash
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix frontend run build
npm --prefix frontend exec -- playwright install chromium
npm --prefix frontend run test:e2e
```

`test:e2e` 还需要仓库根目录的 Python 测试环境，默认使用 `.venv/bin/python`。它自行启动临时后端和 Vite，使用替身模型、检索与临时 SQLite，不需要启动应用服务或提供模型凭据。

25 项历史审阅单测需要私有原件，缺少时会显示跳过。资料配置、端口覆盖和其他集成套件的前提见[开发与测试](../docs/development.md#测试与-ci)。

构建产物位于 `frontend/dist/`。部署完整前端时，需要提供 `/api` 反向代理，并让前端页面路由回退到 `index.html`。静态历史演示另见 [demo/README.md](../demo/README.md)。
