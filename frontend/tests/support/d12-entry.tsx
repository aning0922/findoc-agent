// Only the Playwright test intercepts /src/main.tsx to load this entry.
// There is no URL, environment flag or production route that enables simulation.
import { createRoot } from "react-dom/client";
import FinancialProduct from "../../src/product/FinancialProduct.tsx";
import { json, reference, validateQuery, comparisonBody } from "../../src/product/api.ts";
import type { DataAccess, FactQuery } from "../../src/product/api.ts";
import "../../src/index.css";
const access: DataAccess = {
  compare: (a,b,period,rows,signal) => json("/__test__/company-comparison", signal, comparisonBody(a,b,period,rows)),
  comparisonEligible: c => !c.production_calculable && c.confirmation_kind === "simulated_test",
  label: "隔离 UI Harness · simulated_test 测试数据 · 无真人确认 / 非生产结果",
  eligible: (f) =>
    f.current_valid &&
    f.confirmation_kind === "simulated_test" &&
    !f.production_calculable &&
    f.calculable &&
    f.confirmation_status === "confirmed" &&
    f.integrity === "verified",
  query: async (company, signal) =>
    validateQuery(
      await json<FactQuery>(
        `/financial-facts?company_id=${company}&include_invalid=true`,
        signal,
      ),
      company,
    ),
  analyze: (company, metric, current, previous, signal) =>
    json("/__test__/analyses", signal, {
      schema_version: "financial-analysis-v1",
      company_id: company,
      metric_key: metric,
      current: reference(current),
      previous: reference(previous),
    }),
  analysisEligible: (a) =>
    !a.production_calculable && a.confirmation_kind === "simulated_test",
};
createRoot(document.getElementById("root")!).render(
  <FinancialProduct access={access} />,
);
