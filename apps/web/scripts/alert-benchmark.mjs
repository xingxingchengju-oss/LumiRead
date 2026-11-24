import {chromium} from '@playwright/test';
import {readFile,writeFile} from 'node:fs/promises';
import {existsSync} from 'node:fs';
import {resolve} from 'node:path';

const root=resolve('../..'),info=JSON.parse(await readFile(resolve(root,'var/server.json')));
if(info.mode!=='lan')throw Error('Start make demo for the LAN-interface benchmark.');
const chrome='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const browser=await chromium.launch({executablePath:process.env.LUMIREAD_CHROME || (existsSync(chrome)?chrome:undefined)});
try {
  const parent=await browser.newContext({baseURL:new URL(info.parent).origin});
  const cam=await browser.newContext({baseURL:new URL(info.phone).origin,ignoreHTTPSErrors:true});
  const sid=(await(await parent.request.post('/api/v1/sessions',{data:{}})).json()).session_id;
  const room='/api/v1/sessions/'+sid;
  const {code}=await(await parent.request.post(room+'/invites',{data:{role:'glasses'}})).json();
  if(!(await cam.request.post(room+'/join',{data:{code}})).ok())throw Error('Camera pairing failed');
  const page=await parent.newPage();await page.goto('/app');
  await page.getByRole('heading',{name:'学习观察手册'}).waitFor();
  const samples=[];
  async function send(value) {
    const s={metric:'reading_seconds',unit:'s',method:'demo-clock-300x-v1',input_mode:'accelerated',value_kind:'simulated',quality:'ok',value,observed_at:new Date().toISOString()};
    const r=await cam.request.post(room+'/telemetry/batch',{data:{samples:[s]}});
    if(!r.ok())throw Error('Batch rejected '+r.status());
    return r.json();
  }
  for(let i=0;i<30;i++){
    const receipt=page.waitForResponse(r=>r.url().includes('/alerts/')&&r.url().endsWith('/seen')&&r.status()===204,{timeout:12000});
    const {active_alerts}=await send(2700);
    const seen=await receipt;
    if(!seen.url().endsWith('/'+active_alerts[0].id+'/seen'))throw Error('Receipt mismatch.');
    samples.push(active_alerts[0].id);
    await send(0);
  }
  await writeFile(resolve(root,'var/qa/bench-room.json'),JSON.stringify({session:sid,alerts:samples}));
} finally {await browser.close();}
