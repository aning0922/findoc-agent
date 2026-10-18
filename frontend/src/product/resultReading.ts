import { compactYi, formatDecimal } from './api.ts';

function sign(value: string | null) {
  if (value === null || !/^-?\d+(\.\d+)?$/.test(value)) return null;
  if (!/[1-9]/.test(value)) return 0;
  return value.startsWith('-') ? -1 : 1;
}
// Presentation only: every delta and percentage comes from the validated server result.
export function resultReading(input: { absolute: string | null; percentage: string | null;
  current: string | null; base: string | null; currentLabel: string; baseLabel: string;
  currentYear: number; baseYear: number; comparison: boolean }) {
  const delta = sign(input.absolute), base = sign(input.base), current = sign(input.current);
  const direction = delta === null ? '差额无定义' : delta === 0 ? '持平' : delta > 0 ? '增加' : '减少';
  const unusual = base !== null && base <= 0 || base !== null && current !== null && base * current < 0;
  const crossing = base !== null && current !== null && base * current < 0;
  const period = input.comparison ? `${input.currentYear} 年 · ${input.currentLabel} 相对 ${input.baseLabel}` : `${input.currentYear} 年较 ${input.baseYear} 年`;
  const kind = input.comparison ? `以 ${input.baseLabel} 为比较基准` : input.currentYear === input.baseYear + 1 ? '同比' : '跨年比较';
  const rate = input.percentage === null ? '变化率无定义' : unusual ? `变化率 ${input.percentage}%` : delta === 0 ? '持平 · 0%' : `${direction} ${input.percentage.replace(/^-/, '')}%`;
  const amount = input.absolute === null ? '差额无定义' : delta === 0 ? '差额 0 元' : `${direction} ${compactYi(input.absolute.replace(/^-/, '')).replace('≈ ', '')} 亿元${compactYi(input.absolute).includes('≈') ? '（约）' : ''}`;
  const note = crossing ? '两期数值跨越零点；变化率按服务端有符号基数口径展示。' : base === 0 ? '比较基数为零，变化率无定义。' : base === -1 ? '比较基数为负；变化率符号不代表金额增减方向。' : '';
  return { period, kind, rate, amount, note, exact: input.absolute === null ? '无定义' : `${formatDecimal(input.absolute)} 元` };
}
