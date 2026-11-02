# A0 测试基线

范围：独立 worktree main@1f0a3d4，尚未修改业务代码。Python 使用目标主仓库已安装的 Python 3.12 环境；导入工作目录为本工作树。Node 检查使用 v24.19.0。

- 初次 `pytest -q --disable-warnings --maxfail=3`：328 passed、3 failed（全是独立工作树缺少 data/30d-foundation 的真实PDF，按 maxfail=3 停止；不能宣称全套通过）。
- 随后从旧工作树只读复制四份原始 PDF 到新工作树的 Git 忽略数据目录，逐份对照 product/validation/sources.json 的 SHA256 完全一致，原始文件未修改。
- `pytest -q -m 'not local_data' --disable-warnings --maxfail=3`：645 passed、20 deselected、3 errors，343.32秒；3个setup错误均因缺product/validation/d21-real-research.json，maxfail=3停止。不是业务断言失败，也不能宣布完整全套通过。D22/23/24需后续隔离新鲜proof重跑。
- 后端开发聊天选定旧契约集：196 passed、0 failed、5条SWIG弃用警告（迁移、来源、问答、确认事实、任务、禁止重试）。与上述645可能重叠，不求和。
- 前端 `npm test`：184 passed、25 skipped、0 failed。
- 前端 lint：通过，保留原 tests/support/d14-chart-boundaries.tsx Fast Refresh 警告。
- 前端 TypeScript/build：通过，保留原 >500kB chunk 提示。
- 初次 npm ci 使用环境默认 Node20 且 --ignore-scripts，产生 engine 警告；实际复制 PDF assets、测试、lint、build 均已改用项目所需 Node24，未改变 lockfile。
- npm 安装审计提示 1 high 漏洞；未擅自升级依赖，本轮尚未完成风险归因。

以上均为现有工程基线，不构成 V1.2 功能验收。

## 依赖修补

主控依据Vite官方公告 https://github.com/vitejs/vite/security/advisories/GHSA-rq7h-c2jc-7f22 与registry实际版本，将前端Vite从8.2.2最窄升级并精确固定8.2.4；只改变vite的package/lock记录，未做全量audit fix。升级后npm audit：0漏洞。新功能完成后的build与浏览器回归仍需执行。
