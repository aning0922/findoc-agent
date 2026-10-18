import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import type { Company } from "./api.ts";
import { Icon } from "./Icon.tsx";
import type { IconName } from "./Icon.tsx";
import { pathFor, type Page } from './productRoutes.ts';
export type { Page } from './productRoutes.ts';
// oxlint-disable-next-line react/only-export-components
export { pathFor } from './productRoutes.ts';
const navigation: { page: Page; label: string; icon: IconName }[] = [
  { page: "home", label: "我的研究", icon: "research" },
  { page: "companies", label: "企业与资料", icon: "library" },
  { page: "reports", label: "报告", icon: "file" },
];
export function AppShell({
  page,
  company,
  companies,
  navigate,
  children,
  label,
  contextLocked = false,
}: {
  page: Page;
  company: string;
  companies: Company[];
  navigate: (page: Page, company: string) => void;
  children: ReactNode;
  label?: string;
  contextLocked?: boolean;
}) {
  const [resolvedLock, setResolvedLock] = useState<boolean | null>(null);
  useEffect(() => {
    const lock = () => { const q = new URLSearchParams(location.search); setResolvedLock(q.get('mode') === 'qa' ? q.has('run') : true); };
    window.addEventListener('findoc:fixed-context', lock);
    return () => window.removeEventListener('findoc:fixed-context', lock);
  }, []);
  const locked = resolvedLock ?? contextLocked;
  const globalPage = page === 'research' ? 'home' : ['overview', 'documents', 'analysis'].includes(page) ? 'companies' : page;
  const [drawerMode, setDrawerMode] = useState(() => window.innerWidth < 1100);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const sidebar = useRef<HTMLElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const media = window.matchMedia("(max-width: 1099px)");
    const change = () => { setDrawerMode(media.matches); setDrawerOpen(false); };
    media.addEventListener("change", change);
    return () => media.removeEventListener("change", change);
  }, []);
  useEffect(() => {
    if (!drawerOpen || !drawerMode) return;
    const returnFocus = trigger.current;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    sidebar.current?.querySelector<HTMLButtonElement>("button")?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); setDrawerOpen(false); }
      if (event.key !== "Tab") return;
      const controls = [...(sidebar.current?.querySelectorAll<HTMLElement>("a[href], button, select") ?? [])].filter(el => el.getClientRects().length);
      if (event.shiftKey && document.activeElement === controls[0]) { event.preventDefault(); controls.at(-1)?.focus(); }
      else if (!event.shiftKey && document.activeElement === controls.at(-1)) { event.preventDefault(); controls[0]?.focus(); }
    };
    document.addEventListener("keydown", keydown);
    return () => {
      document.removeEventListener("keydown", keydown);
      document.body.style.overflow = previousOverflow;
      returnFocus?.focus();
    };
  }, [drawerOpen, drawerMode]);
  return (
    <div className="findoc-app saas-app">
      <a className="skip-link" href="#main-content">
        跳到主要内容
      </a>
      {drawerOpen && drawerMode && <div className="nav-backdrop" onClick={() => setDrawerOpen(false)} />}
      <aside ref={sidebar} id="product-navigation" className={`sidebar ${drawerOpen && drawerMode ? "nav-drawer-open" : ""}`} role={drawerOpen && drawerMode ? "dialog" : undefined} aria-modal={drawerOpen && drawerMode || undefined} aria-label={drawerOpen && drawerMode ? "产品导航菜单" : undefined}>
        {drawerMode && <button className="nav-close" onClick={() => setDrawerOpen(false)}>关闭导航</button>}
        <a
          className="brand"
          href="/"
          onClick={(e) => {
            e.preventDefault();
            window.location.assign("/");
          }}
          aria-label="FinDoc Analyst 研究首页"
        >
          <span className="brand-mark">
            <Icon name="book" size={22} />
          </span>
          <span>
            <strong>
              FinDoc<span className="brand-dot">.</span>
            </strong>
            <small>ANALYST</small>
          </span>
          <span className="version">V1</span>
        </a>
        <div className="workspace-label">
          <span className="workspace-avatar">F</span>
          <div>
            <strong>我的研究空间</strong>
            <span>个人工作空间</span>
          </div>
        </div>
        <span className="nav-caption">工作空间</span>
        <nav aria-label="产品导航">
          {navigation.map((item) => (
            <a
              key={item.page}
              href={pathFor(item.page, company)}
              aria-current={item.page === globalPage ? "page" : undefined}
              title={item.label}
              aria-label={item.label}
              className={`nav-item ${item.page === globalPage ? "active" : ""}`}
              onClick={(e) => {
                e.preventDefault();
                setDrawerOpen(false);
                navigate(item.page, company);
              }}
            >
              <Icon name={item.icon} />
              <span className="nav-label">{item.label}</span>
              {item.page === globalPage && <span className="nav-active-dot" />}
            </a>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="research-principle">
            <Icon name="shield" size={20} />
            <strong>让每个结论都有据可查</strong>
            <p>
              回到原文，核对数据，
              <br />
              再形成你的研究结论。
            </p>
          </div>
          <div className="profile">
            <span className="profile-avatar">研</span>
            <div>
              <strong>本地研究者</strong>
              <span>单人研究空间</span>
            </div>
          </div>
        </div>
      </aside>
      <div className="app-body" inert={drawerOpen && drawerMode || undefined}>
        <header className="topbar">
          {drawerMode && <button ref={trigger} className="nav-toggle" aria-label="打开导航" aria-expanded={drawerOpen} aria-controls="product-navigation" onClick={() => setDrawerOpen(true)}>菜单</button>}
          <div className="breadcrumb">
            工作空间 <Icon name="chevron" size={13} />
            <span>{navigation.find((n) => n.page === globalPage)?.label}</span>
          </div>
          {locked || page === 'reports' ? <p className="context-lock">{page === 'reports' ? locked ? '报告范围来自保存时的研究' : '报告库 · 全部企业' : '当前研究范围固定'} · <a href="/companies">查看企业目录</a></p> : <label className="company-picker">
            {page === 'home' ? '企业筛选' : '当前企业'}
            <select
              aria-label="当前企业"
              value={company}
              onChange={(e) => navigate(page, e.target.value)}
            >
              <option value="">选择企业</option>
              {companies.map((c) => (
                <option key={c.company_id} value={c.company_id}>
                  {c.name} · {c.security_code}
                </option>
              ))}
            </select>
          </label>}
        </header>
        {label && (
          <div className="test-banner" role="status">
            {label}
          </div>
        )}
        <main id="main-content" className="saas-content" tabIndex={-1}>
          {children}
        </main>
        <footer className="app-footer">
          <span>FinDoc Analyst V1</span>
          <span>人民币 · 合并口径 · 原文可追溯</span>
        </footer>
      </div>
    </div>
  );
}
