import test from 'node:test'
import assert from 'node:assert/strict'
import { verifiedHighlight } from '../src/evidence/geometry.ts'
import type { Viewport } from '../src/evidence/geometry.ts'
import type { Evidence, Reference } from '../src/evidence/contracts.ts'
function viewport(scale = 1, rotation = 0): Viewport {
  const point = (x: number, y: number) => {
    const a = x - 10, b = 820 - y
    if (rotation === 90) return [(800 - b) * scale, a * scale]
    if (rotation === 180) return [(600 - a) * scale, (800 - b) * scale]
    if (rotation === 270) return [b * scale, (600 - a) * scale]
    return [a * scale, b * scale]
  }
  return { viewBox: [10, 20, 610, 820], scale, rotation, width: (rotation % 180 ? 800 : 600) * scale,
    height: (rotation % 180 ? 600 : 800) * scale,
    convertToViewportPoint: point }
}
const ref: Reference = { evidence_id: 'e', physical_page: 8, bbox: [100, 200, 170, 220], raw_value: '1,234.50', raw_unit: '元', label: '营业收入', role: 'summary' }
const e: Evidence = { company_id: 'c', document_id: 'd', source_revision: 'r', evidence_id: 'e', physical_page: 8, text: '', layout: { strategy: 'text_geometry', rows: [[{ text: '1,234.50', bbox: ref.bbox }]] } }
const items = [{ str: '1,234.50', transform: [10, 0, 0, 10, 110, 605], width: 60, height: 10 }]
test('raw PDF points: crop offset, zoom and all quarter-turn rotations', () => {
  assert.deepEqual(verifiedHighlight(e, ref, viewport(), items), { left: 100, top: 200, width: 70, height: 20 })
  for (const rotation of [0, 90, 180, 270]) {
    const base = verifiedHighlight(e, ref, viewport(1, rotation), items)!
    const zoom = verifiedHighlight(e, ref, viewport(2, rotation), items)!
    assert.ok(base)
    assert.deepEqual(zoom, Object.fromEntries(Object.entries(base).map(([k, n]) => [k, n * 2])))
  }
})
test('no box, out-of-bounds, forged cell, wrong text, wrong page and unverified rotated ruled layout fall back', () => {
  for (const bad of [null, [100, 200, 200, 220], [100, 200, 700, 220], [NaN, 200, 170, 220]]) {
    assert.equal(verifiedHighlight(e, { ...ref, bbox: bad as Reference['bbox'] }, viewport(), items), null)
  }
  assert.equal(verifiedHighlight(e, ref, viewport(), [{ ...items[0], str: '999' }]), null)
  assert.equal(verifiedHighlight(e, { ...ref, physical_page: 9 }, viewport(), items), null)
  assert.equal(verifiedHighlight(e, ref, viewport(), [{ ...items[0], transform: [10, 0, 0, 10, 250, 605] }]), null)
  assert.equal(verifiedHighlight({ ...e, layout: { ...e.layout!, strategy: 'ruled' } }, ref, viewport(1, 90), items), null)
})

test('coordinate reproduction: center inside is insufficient when most of the amount extends beyond the box', () => {
  assert.equal(verifiedHighlight(e, ref, viewport(), [{ ...items[0], transform: [10, 0, 0, 10, 149, 605] }]), null)
})
