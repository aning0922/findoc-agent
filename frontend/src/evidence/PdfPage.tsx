import { useEffect, useRef, useState } from 'react'
import { GlobalWorkerOptions, getDocument } from 'pdfjs-dist'
import type { PDFDocumentProxy } from 'pdfjs-dist'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import { verifiedHighlight } from './geometry.ts'
import type { Rect, TextItem } from './geometry.ts'
import type { Evidence, Reference, Source } from './contracts.ts'
GlobalWorkerOptions.workerSrc = workerUrl
interface Rendered { key: string; box: Rect | null; label: string | null; width: number; height: number }
export function PdfPage({ bytes, source, page, zoom, evidence, reference, locationToken, onFatal, onPage, onZoom }: {
  bytes: Uint8Array; source: Source; page: number; zoom: number | 'fit'; evidence: Evidence | null
  reference: Reference | null; locationToken: number; onFatal: (error: string) => void
  onPage: (page: number) => void; onZoom: (zoom: number | 'fit') => void
}) {
  const container = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(600)
  const [loaded, setLoaded] = useState<{ bytes: Uint8Array; doc: PDFDocumentProxy } | null>(null)
  const [rendered, setRendered] = useState<Rendered | null>(null)
  const pdf = loaded?.bytes === bytes ? loaded.doc : null
  const renderKey = JSON.stringify([pdf?.fingerprints[0], page, zoom, width, evidence?.evidence_id, reference])
  const loading = !pdf || rendered?.key !== renderKey
  const box = !loading ? rendered.box : null
  const handledLocation = useRef(0)
  useEffect(() => {
    if (loading || handledLocation.current === locationToken) return
    handledLocation.current = locationToken
    container.current?.scrollTo({ top: box ? Math.max(0, box.top - 110) : 0, left: box ? Math.max(0, box.left - width / 2) : 0 })
  }, [locationToken, loading, box, width])
  const stage = useRef<HTMLDivElement>(null)
  const fatal = useRef(onFatal)
  useEffect(() => { fatal.current = onFatal }, [onFatal])
  useEffect(() => {
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(200, entry.contentRect.width - 32)))
    if (container.current) observer.observe(container.current)
    return () => observer.disconnect()
  }, [])
  useEffect(() => {
    let active = true
    const task = getDocument({ data: bytes.slice(), cMapUrl: '/pdf-assets/cmaps/', cMapPacked: true,
      standardFontDataUrl: '/pdf-assets/standard_fonts/', wasmUrl: '/pdf-assets/wasm/' })
    void task.promise.then(doc => {
      if (!active) return
      if (doc.numPages !== source.physical_pages) throw new Error('PDF 物理页数与来源不匹配。')
      setLoaded({ bytes, doc })
    }).catch(error => { if (active) fatal.current(`PDF 加载失败：${error.message}`) })
    return () => { active = false; void task.destroy() }
  }, [bytes, source.physical_pages])
  useEffect(() => {
    if (!pdf) return
    let active = true
    let cancel: (() => void) | undefined
    // Each render has a detached canvas; a cancelled/late task never paints a new
    // page's canvas. Render identity also hides old pixels before effects run.
    const canvas = document.createElement('canvas')
    void (async () => {
      const p = await pdf.getPage(page)
      if (!active) return
      const base = p.getViewport({ scale: 1 })
      const viewport = p.getViewport({ scale: zoom === 'fit' ? width / base.width : zoom })
      const ratio = Math.min(window.devicePixelRatio || 1, 2)
      canvas.width = Math.ceil(viewport.width * ratio); canvas.height = Math.ceil(viewport.height * ratio)
      canvas.style.width = `${viewport.width}px`; canvas.style.height = `${viewport.height}px`
      canvas.setAttribute('aria-label', `PDF 物理第 ${page} 页`); canvas.setAttribute('role', 'img')
      const task = p.render({ canvas, viewport, transform: [ratio, 0, 0, ratio, 0, 0] })
      cancel = () => task.cancel()
      const [text, labels] = await Promise.all([p.getTextContent(), pdf.getPageLabels(), task.promise])
      if (!active) return
      const highlight = evidence && reference && evidence.physical_page === page
        ? verifiedHighlight(evidence, reference, viewport, text.items.filter(t => 'str' in t) as TextItem[]) : null
      stage.current?.replaceChildren(canvas)
      setRendered({ key: renderKey, width: viewport.width, height: viewport.height, box: highlight, label: labels?.[page - 1] ?? null })
      if (highlight) requestAnimationFrame(() => {
        if (active) container.current?.scrollTo({ top: Math.max(0, highlight.top - 110), left: Math.max(0, highlight.left - width / 2) })
      })
      else container.current?.scrollTo({ top: 0, left: 0 })
    })().catch(error => { if (active && error.name !== 'RenderingCancelledException') fatal.current(`PDF 页面渲染失败：${error.message}`) })
    return () => { active = false; cancel?.(); canvas.remove() }
  }, [pdf, page, zoom, width, evidence, reference, renderKey])
  return <>
    <div className="pdf-location" role="status">物理第 {page} / {source.physical_pages} 页
      {!loading && rendered.label && rendered.label !== String(page) && ` · PDF 页标签 ${rendered.label}`}
      <span>{loading ? '正在渲染 PDF…' : box ? '金额区域已核验' : evidence?.physical_page === page ? '仅物理页与片段定位（无可验证金额坐标）' : '自由阅读 · 可返回引用位置'}</span>
    </div>
    <div className="pdf-scroll" ref={container} tabIndex={0} aria-label="PDF 阅读区域" onKeyDown={event => {
      let target: number | undefined
      if (event.key === 'PageDown') target = Math.min(source.physical_pages, page + 1)
      if (event.key === 'PageUp') target = Math.max(1, page - 1)
      if (event.key === 'Home') target = 1
      if (event.key === 'End') target = source.physical_pages
      if (target !== undefined) { event.preventDefault(); onPage(target) }
      if (['+', '=', '-'].includes(event.key)) { event.preventDefault(); onZoom(Math.min(2, Math.max(0.5, (zoom === 'fit' ? 1 : zoom) + (event.key === '-' ? -0.25 : 0.25)))) }
      if (event.key === '0') { event.preventDefault(); onZoom('fit') }
    }}>
      {loading && <p className="pdf-loading" role="status">正在加载真实页面…</p>}
      <div className="pdf-sheet" style={{ width: rendered?.width || 1, height: rendered?.height || 1, visibility: loading ? 'hidden' : 'visible' }}>
        <div ref={stage} />
        {box && <div className="pdf-highlight" data-testid="amount-highlight" aria-label={`原文金额 ${reference?.raw_value?.trim()}`} style={box} />}
      </div>
    </div>
  </>
}
