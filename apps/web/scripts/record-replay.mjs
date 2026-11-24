import {chromium} from '@playwright/test';
import {existsSync} from 'node:fs';
import {readFile, writeFile} from 'node:fs/promises';
import {resolve} from 'node:path';

const [baseURL,source,folder]=process.argv.slice(2);
const chrome='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const browser=await chromium.launch({executablePath:process.env.LUMIREAD_CHROME || (existsSync(chrome)?chrome:undefined),args:['--enable-unsafe-swiftshader']});
const ctx=await browser.newContext({baseURL,viewport:{width:1440,height:940},recordVideo:{dir:folder,size:{width:1440,height:940}}});
const phone=await browser.newContext({baseURL});
const page=await ctx.newPage();
const movie=page.video();
page.setDefaultTimeout(40000);
const linger=(ms=1300)=>page.waitForTimeout(ms);
try {
  await page.addInitScript(()=>{
    addEventListener('DOMContentLoaded',()=>{
      const label=document.createElement('div');
      label.textContent='LumiRead · '+new Date().toLocaleDateString('zh-CN')+' · 留存 iPhone 作业照重新在线批改';
      label.style.cssText='position:fixed;right:12px;bottom:8px;z-index:9999;padding:7px 12px;border-radius:5px;background:#162b23;color:white;font:15px system-ui;pointer-events:none';
      document.body.appendChild(label);
    });
  });
  const sid=(await (await ctx.request.post('/api/v1/sessions',{data:{}})).json()).session_id;
  const room='/api/v1/sessions/'+sid;
  const {code}=await (await ctx.request.post(room+'/invites',{data:{role:'glasses'}})).json();
  await phone.request.post(room+'/join',{data:{code}});
  await page.goto('/showcase?legacy=1&room='+sid);
  await page.getByRole('button',{name:'点镜片，试试三种戴法'}).waitFor();await linger(2200);
  await page.getByRole('button',{name:'点镜片，试试三种戴法'}).click();
  await page.getByRole('heading',{name:'三种佩戴方式',exact:true}).waitFor();await linger();
  await page.getByRole('button',{name:'夹片款',exact:true}).click();await linger();
  await page.getByRole('link',{name:'查看价格'}).click();
  await page.getByRole('link',{name:'进入学习助手'}).first().click();
  await page.getByRole('heading',{name:'学习观察手册'}).waitFor();await linger();
  const res=await phone.request.post(room+'/captures',{multipart:{photo:{name:'retained.jpg',mimeType:'image/jpeg',buffer:await readFile(source)},idem:crypto.randomUUID(),source:'upload',phone_confirmed:'false'}});
  if(!res.ok()) throw Error('Retained page upload failed: '+res.status());
  const {job_id}=await res.json();
  await page.getByRole('button',{name:'今日作业'}).click();
  const hints=page.locator('section').filter({has:page.locator(':scope > h4')}).filter({has:page.getByRole('button',{name:'收藏错题'})}).getByRole('button',{name:'小鹿分步讲解'}).first();
  await hints.waitFor({timeout:135000});
  const job=await (await ctx.request.get('/api/v1/jobs/'+job_id)).json();
  if(!job.request_id||!['OpenAI','DeepSeek'].includes(job.provider))throw Error('Missing live receipt.');
  await hints.scrollIntoViewIfNeeded();await linger();await hints.click();await linger();
  const next=page.getByRole('button',{name:/下一步|查看解析/}).first();
  if(await next.isVisible()){await next.click();await linger();}
  await page.getByRole('button',{name:'收藏错题'}).first().click();await linger();
  await page.getByRole('button',{name:'学习档案'}).click();
  await page.getByRole('heading',{name:'六维学习画像'}).waitFor();await linger(1900);
  const first=page.locator('form.practice').first();
  await first.scrollIntoViewIfNeeded();
  await first.locator('input').fill('0');
  await first.getByRole('button',{name:'提交答案'}).click();
  await page.locator('.practice-history article').first().waitFor();await linger(2200);
  await ctx.close();
  const video=resolve(folder,'LumiRead_Online_Replay.webm');
  await movie.saveAs(video);
  await movie.delete();
  await writeFile(resolve(folder,'replay.json'),JSON.stringify({date:new Date().toISOString(),input:'previously retained iPhone worksheet, re-uploaded',provider:job.provider,model:job.model,request_id:job.request_id,usage:job.usage,items:job.result.length,seconds:job.latency},null,2)+'\n');
} finally {await browser.close();}
