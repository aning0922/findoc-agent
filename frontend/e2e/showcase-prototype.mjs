import { chromium } from 'playwright';
import { mkdir } from 'node:fs/promises';
const url = process.env.SHOWCASE_URL || 'http://127.0.0.1:5173/showcase.html';
const out = process.env.SHOWCASE_SCREENSHOTS || '/tmp/findoc-b02-revision';
await mkdir(out, { recursive: true });
const browser = await chromium.launch({headless:true, ...(process.env.CHROME_PATH ? {executablePath:process.env.CHROME_PATH} : {})});
for (const width of [1440,1280,390]) {
 const page = await browser.newPage({viewport:{width,height:900}}); const errors=[]; page.on('pageerror',e=>errors.push(e.message));
 await page.goto(url); await page.getByText('欢迎体验 FinDoc').waitFor(); if(await page.locator('.sidebar').count()) throw Error('login exposes underlying workspace'); if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)) throw Error(`login overflow ${width}`); await page.getByRole('button',{name:'进入演示工作台 →'}).scrollIntoViewIfNeeded(); await page.evaluate(()=>window.scrollTo(0,0)); await page.screenshot({path:`${out}/login-${width}.png`,fullPage:true});
 await page.getByRole('button',{name:'只读预览首页'}).click(); await page.getByText('研究概览').waitFor();
 await page.screenshot({path:`${out}/navy-${width}.png`,fullPage:true});
 if(width===1440){await page.getByRole('button',{name:'◐ Navy / Blue'}).click();await page.screenshot({path:`${out}/ink-1440.png`,fullPage:true});}
 if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)) throw Error(`overflow ${width}`);
 if(errors.length) throw Error(errors.join('; ')); console.log(`PASS screenshots ${width}`); await page.close();
}
const p=await browser.newPage({viewport:{width:1440,height:900}});await p.goto(url);await p.getByLabel('演示账号').fill('demo');await p.getByLabel('演示密码').fill('example');await p.getByRole('button',{name:'进入演示工作台 →'}).click();await p.getByText('研究概览').waitFor();
await p.getByLabel('搜索企业').fill('示例企业 A');await p.getByRole('button',{name:'开始研究'}).click();if(!(await p.locator('textarea').inputValue()).includes('示例企业 A'))throw Error('prefill');await p.getByLabel('研究模式').selectOption('深度研究');await p.getByText('证据：界面示意，未接入来源').waitFor();
await p.getByLabel('原型状态').selectOption('busy');await p.getByRole('button',{name:'模拟所有者接管'}).click();await p.getByRole('button',{name:'确认模拟接管'}).click();await p.getByText('正在模拟重置').waitFor();await p.getByText('研究概览').waitFor();await p.getByLabel('原型状态').selectOption('expired');await p.getByText('演示状态已结束').waitFor();await p.getByLabel('关闭').click();await p.getByLabel('原型状态').selectOption('taken');await p.getByText('演示空间已被接管').waitFor();console.log('PASS login, search, context, takeover, expired, taken');await browser.close();
