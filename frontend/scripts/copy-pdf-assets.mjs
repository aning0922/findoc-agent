import { cp, mkdir } from 'node:fs/promises'
await mkdir('public/pdf-assets', { recursive: true })
for (const folder of ['cmaps', 'standard_fonts', 'wasm']) {
  await cp(`node_modules/pdfjs-dist/${folder}`, `public/pdf-assets/${folder}`, { recursive: true })
}
