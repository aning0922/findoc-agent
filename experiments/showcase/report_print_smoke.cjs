// NODE_PATH=<bundled node_modules> node experiments/showcase/report_print_smoke.cjs
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({headless:true, executablePath:process.env.REPORT_CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  const page = await browser.newPage();
  await page.goto('file://' + process.cwd() + '/output/pdf/showcase-report-synthetic.html');
  await page.pdf({path:'output/pdf/showcase-report-synthetic.pdf', format:'A4',printBackground:true,displayHeaderFooter:true,headerTemplate:'<span></span>',footerTemplate:'<div style="width:100%;text-align:center;font-size:9px">模拟数据 / 非真实 LLM · <span class="pageNumber"></span> / <span class="totalPages"></span></div>'});
  await browser.close();
})();
