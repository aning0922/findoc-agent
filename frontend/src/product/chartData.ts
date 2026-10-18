import type { DataAccess, Fact } from "./api.ts";

// Rendering only. Neither coordinates nor scale ever leave this adapter for business arithmetic.
export type ChartSlot = { label: string; company: string; fact: Fact | null; reason?: string };
export type ChartPoint = ChartSlot & { id: string; coordinate: number | null; reason: string };
function decimalParts(value: string) {
  if (!/^-?\d+(\.\d+)?$/.test(value)) return null;
  const [whole, fraction = ""] = value.replace(/^-/, "").split(".");
  const all = whole + fraction, first = all.search(/[1-9]/);
  return { negative: value.startsWith("-"), digits: first < 0 ? "0" : all.slice(first), exponent: first < 0 ? 0 : whole.length - first - 1 };
}
export function chartIdentity(f: Fact): string {
  return JSON.stringify([f.fact_id, f.fact_set_id, f.source_revision, f.disclosure_version]);
}
export function chartData(slots: ChartSlot[], access: Pick<DataAccess, "eligible">) {
  const valid = slots.map(s => s.fact && access.eligible(s.fact) ? s.fact : null);
  const parts = valid.map(f => f ? decimalParts(f.value_cny_yuan) : null);
  const nonzero = parts.filter(p => p && p.digits !== "0");
  const largest = nonzero.length ? Math.max(...nonzero.map(p => p!.exponent)) : 8;
  // Typical annual reports use 亿元. Exceptional magnitudes use an explicit scientific unit.
  const scale = largest > 14 || largest < -4 ? largest : 8;
  const seen = new Set<string>();
  const points: ChartPoint[] = slots.map((s, i) => {
    const fact = valid[i], p = parts[i];
    const id = fact ? chartIdentity(fact) : `missing/${i}`;
    let coordinate: number | null = null;
    let reason = s.reason || "未选择或缺少有效事实";
    if (fact && p && !seen.has(id)) {
      seen.add(id);
      // Limit the mantissa before conversion; even a 10,000-digit Decimal cannot overflow geometry.
      const significant = p.digits.slice(0, 16);
      const n = Number(`${p.negative ? "-" : ""}${significant}e${p.exponent - scale - significant.length + 1}`);
      if (Number.isFinite(n) && (p.digits === "0" || (n !== 0 && p.exponent >= largest - 12))) {
        coordinate = Object.is(n, -0) ? 0 : n;
        reason = "";
      } else reason = "金额低于当前绘图分辨率；请查精确值与原文（未补零）";
    } else if (fact) reason = "金额或事实身份异常，未绘制";
    return { ...s, fact, id, coordinate, reason };
  });
  return { points, scale, unit: scale === 8 ? "亿元" : `10^${scale} 元` };
}
