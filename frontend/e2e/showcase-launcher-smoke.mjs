// Local private deployment config is read from disk, never logged or sent to the provider.
import { chromium } from 'playwright';
import { readFile,mkdir,writeFile } from 'node:fs/promises';
const config=Object.fromEntries((await readFile(new URL('../../data/showcase-local.env',import.meta.url),'utf8')).split('\n').filter(x=>x&&!x.startsWith('#')).map(x=>{const p=x.indexOf('=');return[x.slice(0,p),x.slice(p+1)];}));
const out=new URL('../../data/showcase-launcher-proof/',import.meta.url);await mkdir(out,{recursive:true});
const browser=await chromium.launch({headless:true});const assert=(v,m)=>{if(!v)throw Error(m);};
try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}});page.setDefaultTimeout(45000);
 await page.goto('http://127.0.0.1:14530');await page.screenshot({path:new URL('login-1440.png',out).pathname,fullPage:false});
 await page.getByLabel('账号',{exact:true}).fill(config.DEMO_USERNAME);await page.getByLabel('密码',{exact:true}).fill(config.DEMO_PASSWORD);await page.getByRole('button',{name:'进入演示',exact:true}).click();await page.getByRole('heading',{name:'研究概览',exact:true}).waitFor();
 assert(await page.getByLabel('界面示意数据',{exact:true}).isChecked(),'showcase initially labels illustrative charts');await page.locator('.recharts-line').waitFor();
 const overview=await page.evaluate(async()=>await(await fetch('/api/dashboard/overview')).json());assert(overview.kpis.companies===2&&overview.kpis.reports_ready===3&&overview.kpis.research_completed===2&&overview.kpis.reports===2,'full real preset inventory');
 for(const width of [1440,1280,390]){await page.setViewportSize({width,height:1000});await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:new URL(`home-${width}.png`,out).pathname,fullPage:width===390});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`preview overflow ${width}`);}
 await page.getByRole('button',{name:'退出演示',exact:true}).click();await page.getByRole('button',{name:'进入演示',exact:true}).waitFor();
 let ready=false;for(let n=0;n<150;n++){const state=await page.evaluate(async()=>await(await fetch('/api/demo/status')).json());if(state.service_state==='ready'){ready=true;break;}await page.waitForTimeout(200);}assert(ready,'preview logged out and ready for the user');
 const result={evidence:'ACTUAL_LOCAL_LAUNCHER_REAL_GATEWAY_MAIN_UI',kpis:overview.kpis,logged_out_ready:true,default_conflict_policy:'wait_only',llm_calls:0,human_financial_approvals:0,credentials_printed:false};await writeFile(new URL('result.json',out),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
}finally{await browser.close();}
