// Optional local Playwright verification. Run from the project root.
// The fixed sample-positive expectations apply on 21 October 2026; use the
// explicitly labelled classroom clock for reproducible later runs.
const { chromium } = require('../../.local/browser-check/node_modules/playwright');
const fs = require('node:fs');
const path = require('node:path');
const runId=process.env.FURSAH_PILOT_CHECK_ID || 'manual-'+Date.now();
if(!/^[a-zA-Z0-9_-]+$/.test(runId)) throw Error('Invalid check ID');
const ui=process.env.FURSAH_PILOT_UI_URL || 'http://127.0.0.1:5173/';
const api=process.env.FURSAH_PILOT_API_URL || 'http://127.0.0.1:8001';
(async () => {
  const browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
  const context = await browser.newContext({viewport:{width:1440,height:1050}});
  const page = await context.newPage();
  const errors=[]; page.on('pageerror',e=>errors.push(String(e)));
  const checks=[];
  const output = path.resolve(__dirname,'../runs/checks/discovery-pilot-'+runId+'-browser.json');
  if(fs.existsSync(output)) throw Error('Do not overwrite a completed verification artifact');
  async function search(query) {
    await page.locator('#fursah-query').fill(query);
    const pending=page.waitForResponse(r=>r.url().endsWith('/api/v1/discover')&&r.request().method()==='POST',{timeout:100000});
    await page.getByRole('button',{name:'اكتشف الفرص',exact:true}).click();
    const r=await pending; const body=await r.json();
    await page.locator('.skeleton').first().waitFor({state:'hidden',timeout:3000});
    return {http_status:r.status(),request:r.request().postDataJSON(),response:body};
  }
  try {
    for(let i=0;i<120;i++){try{const h=await fetch(api+'/health');if(h.ok) break;}catch{}if(i===119)throw Error('Pilot startup timeout');await new Promise(r=>setTimeout(r,1000));} await page.goto(ui);
    await page.locator('#fursah-query').waitFor(); const initial=await page.locator('#fursah-query').count();
    checks.push({case:'initial-ui',passed:initial===1});
    const positive=await search('أبي فرص تحليل البيانات باستخدام Excel');
    console.log('positive',positive.http_status,positive.response.status,positive.response.error_code);
    checks.push({case:'live-excel',...positive,passed:positive.http_status===200&&positive.response.status==='ok'});
    if(positive.response.status!=='ok') throw Error('First broken boundary: positive discovery '+JSON.stringify(positive));
    if(positive.response.recommendations.length!==1 || positive.response.recommendations[0].opportunity_id!=='OPP-DEMO-004') throw Error('Unexpected positive candidate');
    await page.getByText('الأهلية: غير مؤكدة',{exact:false}).first().waitFor();
    if(await page.locator('.opp__score').count()) throw Error('Model score rendered as percentage');
    await page.screenshot({path:'.local/pilot-excel-preview.png',fullPage:true});
    const detailPending=page.waitForResponse(r=>r.url().includes('/api/v1/opportunities/OPP-DEMO-004'));
    await page.getByRole('button',{name:'عرض التفاصيل',exact:true}).click();
    const detailResponse=await detailPending; const details=await detailResponse.json();
    checks.push({case:'recommendation-to-details',http_status:detailResponse.status(),response:details,
      passed:detailResponse.status()===200&&details.evidence_version===positive.response.recommendations[0].evidence_version});
    await page.screenshot({path:'.local/pilot-excel-details.png',fullPage:true});
    await page.reload();
    const negative=await search('أبي فرص كتابة الشعر');
    checks.push({case:'unrelated-topic-no-forced-results',...negative,passed:negative.response.status==='no_match'});
    if(negative.response.status!=='no_match') throw Error('Unrelated query unexpectedly passed');
    const unsupported=await search('أبي ورشة الأسبوع الجاي');
    checks.push({case:'unsupported-query-visible-error',...unsupported,passed:unsupported.response.status==='error'&&unsupported.response.error_code==='FURSAH_QUERY_UNSUPPORTED'});
    await page.getByRole('alert').waitFor();
    await page.evaluate(()=>localStorage.setItem('fursah.profile.v1',JSON.stringify({version:3,profile:{user_id:null,education_level:null,field_of_study:null,city:null,interests:[],skills:null},constraints:{location_preference:null,opportunity_types:[],delivery_modes:['in_person'],available_from:null,available_to:null,max_duration_days:null,max_budget_sar:0}})));
    await page.reload();
    const saved=await page.evaluate(()=>localStorage.getItem('fursah.profile.v1'));
    const conflict=await search('أبي ورشة ترجمة مجانية وعن بعد بالكامل');
    checks.push({case:'real-query-profile-conflict',...conflict,passed:conflict.response.status==='needs_info'&&conflict.response.constraint_conflict});
    if(conflict.response.status!=='needs_info') throw Error('Expected a conflict');
    const overridePending=page.waitForResponse(r=>r.url().endsWith('/api/v1/discover')&&r.request().method()==='POST',{timeout:100000});
    await page.getByRole('button',{name:'استخدم قيود نص البحث هذه المرة',exact:true}).click();
    const resolved=await overridePending; const resolution=await resolved.json();
    const after=await page.evaluate(()=>localStorage.getItem('fursah.profile.v1'));
    checks.push({case:'temporary-query-override',http_status:resolved.status(),request:resolved.request().postDataJSON(),response:resolution,
      passed:resolution.status==='no_match'&&saved===after&&resolved.request().postDataJSON().constraint_resolution==='query',profile_unchanged:saved===after});
    await page.screenshot({path:'.local/pilot-expired-or-unknown.png',fullPage:true});
    checks.push({case:'no-browser-script-errors',passed:errors.length===0,errors});
  } catch(e) { checks.push({case:'verification-stopped',passed:false,error:String(e)}); process.exitCode=1; }
  finally {
    fs.writeFileSync(output,JSON.stringify({run:runId,tested_at:new Date().toISOString(),scope:'Live local models, existing PostgreSQL, actual browser clicks; integration checks, not a fresh held-out relevance benchmark.',checks},null,2)+'\n');
    await browser.close();
  }
  console.log(checks.map(c=>({case:c.case,passed:c.passed})))
  if(checks.some(c=>!c.passed)) process.exitCode=1;
})();
