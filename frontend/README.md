# FinDoc Agent Web

React、TypeScript、Vite、PDF.js 与 Recharts 实现研究工作台。产品运行与接口配置见[根目录 README](../README.md)，架构与测试见[开发指南](../docs/development.md)。

```bash
nvm use
npm --prefix frontend ci
npm --prefix frontend run dev -- --host 127.0.0.1
```

开发服务器将 `/api` 代理至 `http://127.0.0.1:8000`；可用 `FINDOC_API_ORIGIN` 指定另一隔离后端。后端须单独启动。

```bash
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix frontend run build
npm --prefix frontend exec -- playwright install chromium
npm --prefix frontend run test:e2e
```

默认浏览器回归使用临时存储与替身依赖。其他历史浏览器套件需要各自的年报、运行快照和隔离装配，不属于默认公开测试基线。
