// Verify one real browser -> Gemini -> full catalog -> reranker -> details flow.
const {chromium}=require('../../.local/browser-check/node_modules/playwright');
const fs=require('node:fs');
const output=process.argv[2]||'evals/runs/checks/local-rag-browser-check.json';
if(fs.existsSync(output))throw Error('Preserve existing verification; choose a new output path');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const report={tested_at:new Date().toISOString(),scope:'Full local catalog integration, not a quality benchmark',checks:[]};
 try{
  await page.goto('http://127.0.0.1:5173/');
  await page.locator('#fursah-query').fill('أبي فرص تحليل البيانات باستخدام Excel');
  const pending=page.waitForResponse(r=>r.url().endsWith('/api/v1/discover')&&r.request().method()==='POST',{timeout:100000});
  const started=Date.now();await page.getByRole('button',{name:'اكتشف الفرص',exact:true}).click();
  const res=await pending,body=await res.json(),rec=body.recommendations?.[0];
  let passed=res.status()===200&&body.status==='ok'&&body.recommendations.length<=3&&rec?.opportunity_id.startsWith('OPP-CSV-');
  report.checks.push({case:'browser-search-uses-full-local-catalog',passed,http_status:res.status(),seconds:(Date.now()-started)/1000,response:body});
  if(!passed)throw Error('Search failed: '+body.status+' / '+(body.error_code||''));
  const detailPending=page.waitForResponse(r=>r.url().includes('/api/v1/opportunities/'+rec.opportunity_id));
  await page.getByRole('button',{name:'عرض التفاصيل',exact:true}).first().click();
  const dr=await detailPending,d=await dr.json();
  passed=dr.status()===200&&d.evidence_version===rec.evidence_version&&JSON.stringify(d.source_ids)===JSON.stringify(rec.source_ids);
  report.checks.push({case:'details-same-source-and-version',passed,response:d});
  if(!passed)throw Error('Details evidence mismatch');
  const trace=fs.readFileSync('.local/discovery-pilot-trace.jsonl','utf8').trim().split(/\r?\n/).map(l=>JSON.parse(l)).filter(e=>e.request_id===body.request_id);
  passed=trace.some(e=>e.step==='active_request_plan_checked'&&e.outcome==='resolved')&&trace.some(e=>e.step==='local_catalog_retrieved_and_reranked');
  report.checks.push({case:'active-gemini-plan-and-local-rerank-traced',passed});
  if(!passed)throw Error('Missing active-plan/rerank trace');
  report.checks.push({case:'no-browser-errors',passed:errors.length===0,errors});
  await page.screenshot({path:'.local/local-rag-details.png',fullPage:true});
 }catch(e){report.checks.push({case:'verification-stopped',passed:false,error:String(e)});process.exitCode=1;}
 finally{fs.writeFileSync(output,JSON.stringify(report,null,2)+'\n',{flag:'wx'});await browser.close();}
 console.log(JSON.stringify({checks:report.checks.map(({case:name,passed})=>({case:name,passed}))}));
})();
