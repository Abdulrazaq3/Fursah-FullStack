// Optional Playwright check, run from repository root with the classroom pilot running.
const {chromium}=require('../../.local/browser-check/node_modules/playwright');
const fs=require('node:fs');
const checkId=process.env.FURSAH_PILOT_CHECK_ID||'manual-'+Date.now();
if(!/^[a-zA-Z0-9_-]+$/.test(checkId))throw Error('Invalid check ID');
const api=process.env.FURSAH_PILOT_API_URL||'http://127.0.0.1:8001';
const ui=process.env.FURSAH_PILOT_UI_URL||'http://127.0.0.1:5173/';
(async()=>{
 const output='evals/runs/checks/query-alternatives-'+checkId+'-browser.json';
 if(fs.existsSync(output))throw Error('Preserve completed verification');
 const b=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 const context=await b.newContext({viewport:{width:1440,height:1050}});
 const p=await context.newPage();const errors=[];p.on('pageerror',e=>errors.push(String(e)));
 const checks=[];
 async function search(query){
  await p.locator('#fursah-query').fill(query);
  const pending=p.waitForResponse(r=>r.url().endsWith('/api/v1/discover')&&r.request().method()==='POST',{timeout:100000});
  const start=Date.now();await p.getByRole('button',{name:'اكتشف الفرص',exact:true}).click();
  const res=await pending;const body=await res.json();
  await p.locator('.skeleton').first().waitFor({state:'hidden',timeout:5000});
  return {request:res.request().postDataJSON(),http_status:res.status(),response:body,seconds:(Date.now()-start)/1000};
 }
 try{
  for(let i=0;i<120;i++){try{if((await fetch(api+'/health')).ok)break;}catch{}if(i===119)throw Error('Startup timeout');await new Promise(r=>setTimeout(r,1000));}
  await p.goto(ui);await p.locator('#fursah-query').waitFor();
  for(const [name,query] of [['practical-tool-alternatives','أدور على فرصة لتعلم إكسل أو SQL بشكل عملي'],['explicit-learning-by-trying','أريد تجربة Excel أو Flutter ضمن فرصة للتعلم']]){
   const result=await search(query);
   const passed=result.http_status===200&&result.response.status==='ok'&&result.response.recommendations.length===1&&result.response.recommendations[0].opportunity_id==='OPP-DEMO-004';
   checks.push({case:name,passed,...result});console.log(name,result.http_status,result.response.status,result.seconds);
   if(!passed)throw Error('First broken boundary: '+JSON.stringify(result));
   if(await p.locator('.opp__score').count())throw Error('Unexpected suitability percentage');
   await p.getByText('الأهلية: غير مؤكدة',{exact:false}).first().waitFor();
  }
  await p.screenshot({path:'.local/alternatives-v31-preview.png',fullPage:true});
  const detail=p.waitForResponse(r=>r.url().includes('/api/v1/opportunities/OPP-DEMO-004'));
  await p.getByRole('button',{name:'عرض التفاصيل',exact:true}).click();
  const dr=await detail;const d=await dr.json();
  const last=checks.at(-1).response.recommendations[0];
  checks.push({case:'details-keep-evidence-version-and-source-ids',passed:dr.status()===200&&d.evidence_version===last.evidence_version&&JSON.stringify(d.source_ids)===JSON.stringify(last.source_ids),http_status:dr.status(),response:d});
  await p.reload();
  const and=await search('أبحث عن فرصة واحدة أتعلم فيها Excel وSQL معا');
  checks.push({case:'both-tools-required-is-not-an-alternative',passed:and.http_status===200&&and.response.status==='no_match',...and});
  if(and.response.status!=='no_match')throw Error('AND was weakened');
  await p.evaluate(()=>localStorage.setItem('fursah.profile.v1',JSON.stringify({version:3,profile:{user_id:null,education_level:null,field_of_study:null,city:null,interests:[],skills:null},constraints:{location_preference:null,opportunity_types:[],delivery_modes:[],available_from:null,available_to:null,max_duration_days:null,max_budget_sar:0}})));
  await p.reload();
  const saved=await p.evaluate(()=>localStorage.getItem('fursah.profile.v1'));
  const budget=await search('أريد تجربة Excel أو Flutter ضمن فرصة للتعلم');
  checks.push({case:'unknown-cost-cannot-pass-zero-budget',passed:budget.http_status===200&&budget.response.status==='no_match'&&budget.response.missing_fields.length===0,...budget});
  checks.push({case:'profile-preserved',passed:saved===await p.evaluate(()=>localStorage.getItem('fursah.profile.v1'))});
  checks.push({case:'no-unhandled-browser-errors',passed:errors.length===0,errors});
 }catch(e){checks.push({case:'verification-stopped',passed:false,error:String(e)});process.exitCode=1;}
 finally{
  fs.writeFileSync(output,JSON.stringify({tested_at:new Date().toISOString(),scope:'Actual browser clicks through FastAPI, local BGE-M3 and reranker, PostgreSQL and evidence-bound response; local four-record pilot, live request time.',checks},null,2)+'\n');
  await b.close();
 }
 console.log(checks.map(c=>({case:c.case,passed:c.passed})));
 if(checks.some(c=>!c.passed))process.exitCode=1;
})();
