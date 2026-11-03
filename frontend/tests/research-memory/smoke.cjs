const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({headless:true, executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  for (const width of [1440,1280,390]) {
    const page = await browser.newPage({ viewport: { width, height: 900 } }); let items = [], ops = {}, unknown = true;
    await page.route('**/api/**', async route => {
      const req = route.request(), url = new URL(req.url()), method = req.method(), path = url.pathname;
      const json = (value, status=200) => route.fulfill({status, contentType:'application/json', body:JSON.stringify(value)});
      if (path === '/api/memories') return json({items:[]});
      if (path.startsWith('/api/research-memories/operations/')) return json(ops[path.split('/').pop()] || {}, ops[path.split('/').pop()] ? 200 : 404);
      if (path === '/api/research-memories' && method === 'GET') return json({items, memory_generation:1});
      if (path === '/api/research-memories' && method === 'POST') { const body=req.postDataJSON(), item={memory_id:'11111111-1111-4111-8111-111111111111', revision:1,type:body.type,text:body.text,source_status:'current',source_kind:'user_note', embedding_revision:1};items=[item];ops[body.operation_id]={operation_id:body.operation_id,memory_id:item.memory_id,revision:1,state:'completed'};if(unknown){unknown=false;return route.abort();}return json(ops[body.operation_id]); }
      if (path.startsWith('/api/research-memories/') && method === 'DELETE') {const b=req.postDataJSON();const id=items[0].memory_id;items=[];return json({operation_id:b.operation_id,memory_id:id,revision:2,state:'completed'});}
      return json({detail:'unexpected'},404);
    });
    await page.goto('http://127.0.0.1:5198/tests/research-memory/'); await page.getByText('研究记忆与偏好').click();
    await page.getByLabel('内容').fill('关注现金流'); await page.getByLabel('我确认保存这条研究记忆').check(); await page.getByRole('button',{name:'保存记忆'}).click();
    await page.getByText('操作结果待查证').waitFor(); await page.reload(); await page.getByText('研究记忆与偏好').click(); await page.getByRole('button',{name:'查询操作状态'}).click(); await page.getByText('关注现金流',{exact:true}).waitFor();
    await page.getByLabel('搜索研究记忆').fill('上次现金流还有哪些问题'); await page.getByRole('button',{name:'搜索',exact:true}).click(); await page.getByText('关注现金流',{exact:true}).waitFor();
    await page.screenshot({path:`/tmp/research-memory-${width}.png`, fullPage:true}); await page.getByRole('button',{name:'删除',exact:true}).first().click(); await page.getByRole('button',{name:'确认删除',exact:true}).click(); await page.getByText('没有找到研究记忆。').waitFor(); await page.close();
  }
  await browser.close(); console.log('PASS 1440/1280/390 create UNKNOWN reload recover search delete; fake API');
})().catch(e=>{console.error(e);process.exit(1)});
