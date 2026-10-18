import type { Box, Evidence, Reference } from './contracts.ts'
export interface Viewport {
  viewBox: number[]; width: number; height: number; scale: number; rotation: number
  convertToViewportPoint(x: number, y: number): number[]
}
export interface TextItem { str: string; transform: number[]; width: number; height: number }
export interface Rect { left: number; top: number; width: number; height: number }
export function amountText(text: string): string { return text.replace(/[\s,，]/g, '') }
export function validBox(box: unknown): box is Box {
  return Array.isArray(box) && box.length === 4 && box.every(x => typeof x === 'number' && Number.isFinite(x))
    && box[0] >= 0 && box[1] >= 0 && box[2] > box[0] && box[3] > box[1]
}
function rect(viewport: Viewport, box: number[]): Rect {
  const r = [...viewport.convertToViewportPoint(box[0], box[1]), ...viewport.convertToViewportPoint(box[2], box[3])]
  return { left: Math.min(r[0], r[2]), top: Math.min(r[1], r[3]), width: Math.abs(r[2] - r[0]), height: Math.abs(r[3] - r[1]) }
}
/** D7 points use top-left page coordinates. PDF.js expects PDF bottom-left user space.
 * Convert using crop viewBox (including its offset); PDF.js handles zoom/userUnit/rotation.
 * A box is usable only if it is a persisted amount cell AND actual PDF text falls inside it.
 * We never search text to invent or move a box. Uncertain transforms fail closed. */
export function verifiedHighlight(e: Evidence, ref: Reference, viewport: Viewport, items: TextItem[]): Rect | null {
  if (!validBox(ref.bbox) || !ref.raw_value || ref.evidence_id !== e.evidence_id || ref.physical_page !== e.physical_page) return null
  const box = ref.bbox
  if (!e.layout?.rows.flat().some(c => validBox(c.bbox) && c.bbox.every((n, i) => n === box[i])
    && c.text !== null && amountText(c.text) === amountText(ref.raw_value!))) return null
  const [x0, y0, x1, y1] = viewport.viewBox
  if (box[2] > x1 - x0 || box[3] > y1 - y0) return null
  // pdfplumber geometry is defined in the rotated page space. Fail closed for native
  // rotated ruled layouts; PyMuPDF text_geometry uses unrotated crop coordinates.
  if (e.layout.strategy === 'ruled' && viewport.rotation % 360 !== 0) return null
  const highlight = rect(viewport, [x0 + box[0], y1 - box[3], x0 + box[2], y1 - box[1]])
  if (![highlight.left, highlight.top, highlight.width, highlight.height].every(Number.isFinite)
    || highlight.left < -0.1 || highlight.top < -0.1 || highlight.left + highlight.width > viewport.width + 0.1
    || highlight.top + highlight.height > viewport.height + 0.1) return null
  const matches = items.filter(item => {
    const t = item.transform
    // Only axis-aligned PDF text is verified here; arbitrary slanted/vertical glyphs fall back.
    if (t.length !== 6 || t[1] !== 0 || t[2] !== 0 || t[0] <= 0 || t[3] <= 0) return false
    const native = rect(viewport, [t[4], t[5], t[4] + item.width, t[5] + item.height * 0.65])
    const centerX = native.left + native.width / 2, centerY = native.top + native.height / 2
    const overlapWidth = Math.max(0, Math.min(native.left + native.width, highlight.left + highlight.width) - Math.max(native.left, highlight.left))
    const overlapHeight = Math.max(0, Math.min(native.top + native.height, highlight.top + highlight.height) - Math.max(native.top, highlight.top))
    return native.width > 0 && native.height > 0 && overlapWidth * overlapHeight >= native.width * native.height * 0.8
      && centerX >= highlight.left && centerX <= highlight.left + highlight.width
      && centerY >= highlight.top && centerY <= highlight.top + highlight.height
      && native.width <= highlight.width + viewport.scale * 2
  })
  return matches.length && amountText(matches.map(t => t.str).join('')) === amountText(ref.raw_value) ? highlight : null
}
