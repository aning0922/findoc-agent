import { useRef, useState } from "react";
import { METRICS } from "../evidence/contracts.ts";
import type { Company, DataAccess, Fact, Report } from "./api.ts";
import { formatDecimal } from "./api.ts";
import { DocumentLibrary } from "./DocumentLibrary.tsx";
import { metrics, sides } from "./operatingResearch.ts";
import type {
  Disclosure,
  Side,
  Template,
  TemplateInput,
} from "./operatingResearch.ts";
import type { Config } from './researchDraft.ts';
export type { Config } from './researchDraft.ts';
export function ResearchCreation({
  stage,
  setStage,
  companies,
  scopeNotice,
  setScopeNotice,
  template,
  config,
  prepared,
  reports,
  access,
  errors,
  catalogBusy,
  catalogError,
  busy,
  ready,
  change: changeConfig,
  selectTemplate: changeTemplate,
  create,
  recheck,
  direction,
  setDirection,
}: {
  stage: number;
  setStage: (stage: number) => void;
  scopeNotice: string[];
  setScopeNotice: (value: string[]) => void;
  companies: Company[];
  template: Template;
  config: Record<Side, Config>;
  prepared: Record<
    Side,
    { key: string; disclosure: Disclosure; facts: Fact[] } | null
  >;
  reports: (Report & { selectable: boolean; reason: string | null })[];
  access: DataAccess;
  errors: Record<Side, string>;
  catalogBusy: boolean;
  catalogError: string;
  busy: boolean;
  ready: boolean;
  change: (side: Side, update: Partial<Config>) => void;
  selectTemplate: (value: Template) => void;
  create: () => void;
  recheck: () => void;
  direction: TemplateInput["direction"];
  setDirection: (value: TemplateInput["direction"]) => void;
}) {
  const [upload, setUpload] = useState("");
  const reportSelectors = useRef<Partial<Record<Side, HTMLSelectElement>>>({});
  const changedScope = scopeNotice, setChangedScope = setScopeNotice;
  function change(side: Side, update: Partial<Config>) {
    const rangeChanged = update.company !== undefined && update.company !== config[side].company || update.year !== undefined && update.year !== config[side].year;
    if (rangeChanged) {
      const affected = update.company !== undefined && template === 'company_period_change' || update.year !== undefined && template === 'company_same_period_comparison' ? sides : [side];
      const hadSelection = affected.some(s => config[s].document || Object.keys(config[s].versions).length);
      if (hadSelection) setChangedScope([...new Set([...changedScope, ...affected.map(s => `${name(config[s].company)} ${config[s].year} 年`)])]);
    }
    changeConfig(side, update);
  }
  function selectTemplate(value: Template) {
    if (value === template) return;
    if (sides.some(s => config[s].document)) setChangedScope(sides.map(s => `${name(config[s].company)} ${config[s].year} 年`));
    changeTemplate(value);
  }
  const name = (id: string) =>
    companies.find((c) => c.company_id === id)?.name || "未选择企业";
  const rangeReady =
    sides.every(
      (side) =>
        !!config[side].company &&
        /^\d{1,4}$/.test(config[side].year) &&
        Number(config[side].year) > 0,
    ) &&
    (template === "company_period_change"
      ? config.first.company === config.second.company &&
        Number(config.first.year) > Number(config.second.year)
      : config.first.company !== config.second.company &&
        config.first.year === config.second.year);
  const reportsReady = sides.every((side) => {
    const s = config[side],
      p = prepared[side];
    return (
      p?.key === `${s.company}:${s.document}` &&
      reports.some(
        (r) =>
          r.document_id === s.document &&
          r.company_id === s.company &&
          r.selectable,
      )
    );
  });
  function back(value: number) {
    recheck();
    setStage(value);
    setUpload("");
  }
  return (
    <section
      className="operating-card creation-flow"
      aria-label="企业与期间配置"
    >
      <ol className="creation-steps" aria-label="创建研究三阶段">
        {["研究范围", "准备财报", "确认来源"].map((title, i) => (
          <li key={title} aria-current={stage === i + 1 ? "step" : undefined}>
            {i + 1} · {title}
          </li>
        ))}
      </ol>
      {stage > 1 && (
        <div className="creation-summary">
          <div>
            <strong>研究范围</strong>
            <p>
              {template === "company_period_change" ? "两期变化" : "两企业比较"}{" "}
              ·{" "}
              {template === "company_period_change" ? `${name(config.first.company)} · ${config.first.year} / ${config.second.year} 年` : `${name(config.first.company)} / ${name(config.second.company)} · ${config.first.year} 年`}
            </p>
          </div>
          <button onClick={() => back(1)}>修改研究范围</button>
        </div>
      )}
      {stage > 2 && (
        <div className="creation-summary">
          <div>
            <strong>已选财报</strong>
            {[...new Set(sides.map(side => config[side].document))].map(id => <p key={id}>
              {reports.find(r => r.document_id === id)?.source_file || '来源待核验'} · 用于 {sides.filter(side => config[side].document === id).map(side => config[side].year).join(' / ')} 年数据
            </p>)}
          </div>
          <button onClick={() => back(2)}>修改财报</button>
        </div>
      )}
      <h2>
        {stage === 1
          ? "先确定要研究什么"
          : stage === 2
            ? "检查两组研究资料"
            : "确认六项指标的披露来源"}
      </h2>
      <p className="muted">
        {stage === 1
          ? "选择企业、研究方式和全年期间。"
          : stage === 2
            ? "选择能覆盖财务期间的年报。上一年度数据也可能披露于本年度报告。"
            : "披露来源需要你的明确选择；财务接受将在原文核对中单独完成。"}
      </p>
      {stage === 1 && (
        <div className="operating-templates" aria-label="经营研究模板">
          {(
            [
              [
                "company_period_change",
                "单企业两期间变化",
                "比较同一企业两年经营变化",
              ],
              [
                "company_same_period_comparison",
                "两企业同期间比较",
                "比较两家企业同一年表现",
              ],
            ] as const
          ).map(([value, title, detail]) => (
            <button
              key={value}
              aria-pressed={template === value}
              className={template === value ? "selected" : ""}
              onClick={() => selectTemplate(value)}
            >
              <strong>{title}</strong>
              <small>{detail}</small>
            </button>
          ))}
        </div>
      )}
      {changedScope.length > 0 && <p role="status" className="scope-change">已保留上传文件；{changedScope.join("、")} 的来源选择需重新确认。</p>}
      {catalogError && (
        <p role="alert">
          {catalogError}
          <button onClick={recheck}>重新读取资料</button>
        </p>
      )}
      <div className="operating-sides">
        {sides.map((side, index) => {
          const s = config[side],
            p =
              prepared[side]?.key === `${s.company}:${s.document}`
                ? prepared[side]
                : null;
          const shared = side === 'second' && s.company === config.first.company && !!s.document && s.document === config.first.document;
          const docs = reports.filter(
            (r) =>
              r.company_id === s.company &&
              [r.report_year, r.report_year - 1].includes(Number(s.year)),
          );
          const years = [
            ...new Set([
              Number(s.year) || new Date().getFullYear() - 1,
              new Date().getFullYear() - 1,
              new Date().getFullYear() - 2,
              ...reports
                .filter((r) => r.company_id === s.company)
                .flatMap((r) => [r.report_year, r.report_year - 1]),
            ]),
          ]
            .filter((y) => y > 0)
            .sort((a, b) => b - a);
          return (
            <div key={side} className="operating-side">
              <h3>
                {template === "company_period_change"
                  ? index === 0
                    ? "本期年度"
                    : "比较年度"
                  : index === 0
                    ? "企业 A"
                    : "企业 B"}
                {stage > 1 && ` · ${name(s.company)} · ${s.year} 年`}
              </h3>
              {stage === 1 && (
                <>
                  {(side === "first" || template !== "company_period_change") && <label>
                    企业
                    <select
                      aria-label={`${side} 企业`}
                      value={s.company}
                      disabled={
                        side === "second" &&
                        template === "company_period_change"
                      }
                      onChange={(e) =>
                        change(side, {
                          company: e.target.value,
                          document: "",
                          versions: {},
                          facts: {},
                        })
                      }
                    >
                      <option value="">选择企业</option>
                      {companies.map((c) => (
                        <option key={c.company_id} value={c.company_id}>
                          {c.name}
                        </option>
                      ))}
                    </select>
                  </label>}
                  {(side === "first" || template === "company_period_change") && <>
                  <label>
                    {template === "company_same_period_comparison" ? "共同年度" : "财务年度"}
                    <select
                      aria-label={`${side} 期间`}
                      value={s.year}
                      onChange={(e) =>
                        change(side, {
                          year: e.target.value,
                          document: "",
                          versions: {},
                          facts: {},
                        })
                      }
                    >
                      <option value="">选择年度</option>
                      {years.map((y) => (
                        <option key={y} value={y}>
                          {y} 全年
                        </option>
                      ))}
                    </select>
                  </label>
                  <details>
                    <summary>选择其他年度</summary>
                    <label>
                      财务年度
                      <input
                        aria-label={`${side} 自定义期间`}
                        inputMode="numeric"
                        maxLength={4}
                        value={s.year}
                        onChange={(e) => {
                          if (/^\d{0,4}$/.test(e.target.value))
                            change(side, {
                              year: e.target.value,
                              document: "",
                              versions: {},
                              facts: {},
                            });
                        }}
                      />
                    </label>
                  </details>
                  </>}
                </>
              )}
              {stage === 2 && (
                <>
                  <label hidden={shared}>
                    年报来源
                    <select
                      aria-label={`${side} 年报`}
                      ref={el => { if (el) reportSelectors.current[side] = el; }}
                      value={s.document}
                      onChange={(e) =>
                        change(side, {
                          document: e.target.value,
                          versions: {},
                          facts: {},
                        })
                      }
                    >
                      <option value="">明确选择年报</option>
                      {docs.map((d) => (
                        <option
                          key={d.document_id}
                          value={d.document_id}
                          disabled={!d.selectable}
                        >
                          {d.report_year} 年报 · {d.source_file}
                          {!d.selectable ? " · 当前不可用" : ""}
                        </option>
                      ))}
                    </select>
                  </label>
                  {!docs.some((d) => d.selectable) && (
                    <p className="operating-pending">
                      {catalogBusy
                        ? "正在读取财报…"
                        : "所选期间暂无可用财报，请就地上传。"}
                    </p>
                  )}
                  {docs
                    .filter((d) => !d.selectable)
                    .map((d) => (
                      <p key={d.document_id} role="status">
                        {d.report_year} 年报当前不可选择：
                        {d.reason || "资格待核验"}
                      </p>
                    ))}
                  {shared && <p>已共用本期年报，无需重复上传 · <button onClick={() => change(side, { document: '', versions: {}, facts: {} })}>更换来源</button></p>}
                  {!shared && side === 'second' && config.first.company === s.company && config.first.document && docs.some(d => d.document_id === config.first.document && d.selectable) && <button
                    disabled={s.document === config.first.document}
                    onClick={() => change(side, { document: config.first.document, versions: {}, facts: {} })}>
                    {s.document === config.first.document ? `已共用本期年报，无需重复上传` : `也用本期年报核对 ${s.year} 年`}
                  </button>}
                  {(side === 'first' || config.first.company !== s.company) && <button className={!docs.some(d => d.selectable) ? 'operating-primary' : undefined} onClick={() => setUpload(side)}>
                    {docs.some(d => d.selectable) ? '上传另一份财报' : '上传财报'}
                  </button>}
                  {side === 'second' && config.first.company === s.company && !docs.some(d => d.selectable) && <button className="operating-primary" onClick={() => setUpload(side)}>上传财报</button>}
                  {upload === side && <DocumentLibrary key={`${s.company}:${side}`} company={s.company} companies={companies} onReady={recheck} focusedPeriod={Number(s.year)} onContinue={() => { setUpload(''); recheck(); requestAnimationFrame(() => reportSelectors.current[side]?.focus()); }} />}

                  {s.document && (
                    <p role={errors[side] ? "alert" : "status"}>
                      {errors[side] ||
                        (p
                          ? `已准备 · ${p.disclosure.source.report_year} 年报，覆盖 ${s.year} 年财务期间待核对`
                          : "正在核验财报来源…")}
                    </p>
                  )}
                </>
              )}
              {stage === 3 &&
                (p ? (
                  <>
                    <p className="muted">
                      财务年度 {s.year} · 披露报告年度{" "}
                      {p.disclosure.source.report_year} · 合并口径
                    </p>
                    {p.disclosure.disclosure_versions.length === 1 && (
                      <button
                        onClick={() =>
                          change(side, {
                            versions: Object.fromEntries(
                              metrics.map((m) => [
                                m,
                                p.disclosure.disclosure_versions[0],
                              ]),
                            ),
                            facts: {},
                          })
                        }
                      >
                        {metrics.every(m => s.versions[m] === p.disclosure.disclosure_versions[0]) ? "已采用这组三项来源" : "采用这组三项来源"}
                      </button>
                    )}
                    {p.disclosure.disclosure_versions.length > 1 && (
                      <p className="operating-pending">
                        存在多个披露版本，请逐项选择。
                      </p>
                    )}
                    <a href={`/evidence?${new URLSearchParams({ company: s.company, document: s.document, revision: p.disclosure.source.source_revision })}`} target="_blank" rel="noreferrer">查看原年报 ↗</a>
                    {metrics.map((metric) => {
                      const fs = p.facts.filter(
                        (f) =>
                          access.eligible(f) &&
                          f.metric_key === metric &&
                          f.period === Number(s.year) &&
                          f.document_id === s.document &&
                          f.source_revision ===
                            p.disclosure.source.source_revision &&
                          f.disclosure_version === s.versions[metric],
                      );
                      return (
                        <div key={metric} className="operating-disclosure">
                          {p.disclosure.disclosure_versions.length > 1 ? <label>
                            {METRICS[metric]}
                            <select
                              aria-label={`${side} ${metric} 披露`}
                              value={s.versions[metric] || ""}
                              onChange={(e) =>
                                change(side, {
                                  versions: {
                                    ...s.versions,
                                    [metric]: e.target.value,
                                  },
                                  facts: { ...s.facts, [metric]: "" },
                                })
                              }
                            >
                              <option value="">明确选择版本</option>
                              {p.disclosure.disclosure_versions.map((v, i) => (
                                <option key={v} value={v}>
                                  {p.disclosure.source.report_year} 年报披露
                                  {p.disclosure.disclosure_versions.length > 1
                                    ? ` · 版本 ${i + 1} (${v.slice(-8)})`
                                    : ""}
                                </option>
                              ))}
                            </select>
                          </label> : <strong>{METRICS[metric]}</strong>}
                          {fs.length > 0 && (
                            <label>
                              已经确认的事实
                              <select
                                aria-label={`${side} ${metric} 事实`}
                                value={s.facts[metric] || ""}
                                onChange={(e) =>
                                  change(side, {
                                    facts: {
                                      ...s.facts,
                                      [metric]: e.target.value,
                                    },
                                  })
                                }
                              >
                                <option value="">
                                  稍后在任务中核验已入库事实
                                </option>
                                {fs.map((f) => (
                                  <option key={f.fact_id} value={f.fact_id}>
                                    {formatDecimal(f.value_cny_yuan)} 元 ·{" "}
                                    {f.confirmation_kind === "simulated_test"
                                      ? "模拟测试"
                                      : "已核准"}
                                  </option>
                                ))}
                              </select>
                            </label>
                          )}
                          {(p.disclosure.disclosure_versions.length > 1 || fs.length > 0) && <p className="muted">
                            {!s.versions[metric]
                              ? "尚未选择披露版本"
                              : !p.disclosure.disclosure_versions.includes(
                                    s.versions[metric],
                                  )
                                ? "披露已失效，请重新选择"
                                : fs.length
                                  ? "已入库事实当前有效，将按所选披露重新核验。"
                                  : "已准备 · 创建后核对原文并明确接受"}
                          </p>}
                        </div>
                      );
                    })}
                  </>
                ) : (
                  <p role="alert">
                    {errors[side] || "正在重新核验来源，完成后才可创建研究。"}
                  </p>
                ))}
            </div>
          );
        })}
      </div>
      <div className="operating-actions">
        {stage > 1 && <button onClick={() => back(stage - 1)}>上一步</button>}
        {stage === 1 && (
          <button
            className="operating-primary"
            disabled={!rangeReady}
            onClick={() => {
              recheck();
              setStage(2);
            }}
          >
            下一步：准备财报
          </button>
        )}
        {stage === 2 && (
          <button
            className="operating-primary"
            disabled={!reportsReady}
            onClick={() => {
              recheck();
              setStage(3);
              setUpload("");
            }}
          >
            下一步：确认来源
          </button>
        )}
        {stage === 3 && (
          <>
            <details>
              <summary>研究方向</summary>
              <label>
                研究方向
                <select
                  value={direction}
                  onChange={(e) =>
                    setDirection(e.target.value as TemplateInput["direction"])
                  }
                >
                  <option value="business_overview">主要业务概述</option>
                  <option value="products_and_operations">
                    产品与经营模式
                  </option>
                </select>
              </label>
            </details>
            <button
              className="operating-primary"
              disabled={!ready || busy}
              onClick={create}
            >
              {busy ? "正在提交或读回…" : "创建研究，开始核对数据"}
            </button>
          </>
        )}
      </div>
      {stage === 1 && !rangeReady && <p role="status">{!config.first.company || !config.second.company ? '请选择研究企业。' : !config.first.year || !config.second.year ? '请选择完整财务年度。' : template === 'company_period_change' ? '本期年度必须晚于比较年度。' : config.first.company === config.second.company ? '请选择两家不同的企业。' : '请选择两家企业的共同年度。'}</p>}
      {stage === 2 && !reportsReady && <p role="status">{sides.filter(side => !config[side].document || !prepared[side] || errors[side]).map(side => `${name(config[side].company)} ${config[side].year} 年：${errors[side] || (config[side].document ? '正在核验所选财报' : '尚未选择可用年报')}`).join('；') || '正在核验财报资格，请稍候。'}</p>}
      {stage === 3 && !ready && <p role="status">{sides.flatMap(side => metrics.filter(m => !prepared[side]?.disclosure.disclosure_versions.includes(config[side].versions[m])).map(m => `${config[side].year} 年${METRICS[m]}的来源尚未确认`)).join('；') || '所选来源或事实尚未通过当前资格核验，请重新检查资料。'}</p>}
      {stage === 3 && busy && <p role="status">正在提交并查询创建结果，请稍候。</p>}
    </section>
  );
}
