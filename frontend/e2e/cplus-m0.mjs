import {chromium} from 'playwright';
import {mkdir,writeFile} from 'node:fs/promises';
const output=new URL('../../docs/cplus/evidence/M0-ui/',import.meta.url);await mkdir(output,{recursive:true});
const browser=await chromium.launch({channel:'chrome',headless:true});
const results=[];
try {
 for(const width of [1440,1280,390]){
  const page=await browser.newPage({viewport:{width,height:900}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:14541/cplus.html');await page.getByRole('heading',{name:'把企业资料，变成'}).waitFor();
  await page.screenshot({path:new URL(`home-${width}.png`,output).pathname,fullPage:true});
  await page.getByRole('button',{name:'查看企业画像 →'}).click();await page.getByRole('heading',{name:'企业 360° 研究画像'}).waitFor();await page.screenshot({path:new URL(`profile-${width}.png`,output).pathname,fullPage:true});
  await page.getByRole('button',{name:'三大报表 →'}).click();await page.getByRole('button',{name:'利润表',exact:true}).click();await page.getByText('归母净利润',{exact:true}).waitFor();
  await page.getByRole('button',{name:'前往体检 →'}).click();await page.getByRole('button',{name:'模拟体检执行 →'}).click();await page.getByRole('button',{name:'了解'}).click();await page.getByRole('button',{name:'查看相关资料 →'}).first().click();
  for(const [target,heading] of [['跨年经营变化','跨年度经营变化'],['同行对标','同行业公司对标'],['AI 研究助手','AI 批量研究矩阵'],['我的报告','报告与研究导出']]){
   if(width===390)await page.getByRole('button',{name:'打开导航'}).click();
   await page.getByRole('button',{name:target,exact:true}).click();await page.getByRole('heading',{name:heading}).waitFor();
   if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error(`overflow ${target} ${width}`);
  }
  await page.getByRole('button',{name:'导出示例报告 →'}).click();await page.getByRole('dialog').getByText('导出尚未接入后端',{exact:false}).waitFor();
  if(errors.length)throw Error(errors.join(';'));results.push({width,eight_view_path:true,page_errors:errors,horizontal_overflow:false});await page.close();
 }
 const result={tier:'UI_MOCK_NATIVE_REACT_REAL_CHROMIUM',business_backend_verified:false,provider_calls:0,human_approvals:0,results};
 await writeFile(new URL('result.json',output),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
} finally {await browser.close();}
