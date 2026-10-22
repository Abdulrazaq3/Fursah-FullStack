// Read-only browser verification of the latest real eval in Phoenix.
const {chromium}=require('../../.local/browser-check/node_modules/playwright');
const fs=require('node:fs');
const path=require('node:path');
const assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../..');
const latest=JSON.parse(fs.readFileSync(path.join(root,'evals/runs/latest.json'),'utf8'));
const runDir=path.join(root,'evals/runs',latest.run_dir);
const rows=fs.readFileSync(path.join(runDir,'results.jsonl'),'utf8').trim().split('\n').map(JSON.parse);

(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 const page=await browser.newPage({viewport:{width:1800,height:1100}});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto(latest.phoenix_url);
  await page.getByRole('link').filter({hasText:latest.phoenix_project}).click();
  await page.getByRole('link',{name:'eval.case',exact:true}).first().waitFor();
  assert((await page.locator('body').innerText()).includes('case_outcome'));
  const projectUrl=page.url();
  await page.screenshot({path:path.join(runDir,'phoenix-project.png'),fullPage:true});
  const sample=rows.find(r=>r.outcome==='FAIL')||rows[0];
  await page.locator(`a[href*="/${sample.trace_id}?"]`).click();
  await page.getByText('fursah.understanding',{exact:true}).first().waitFor({timeout:45000});
  const text=await page.locator('body').innerText();
  assert(text.includes('fursah.rerank'),'Missing reranking stage in trace tree');
  assert(text.includes('case_outcome'),'Missing evaluation annotations');
  await page.screenshot({path:path.join(runDir,'phoenix-trace.png'),fullPage:true});
  const report={verified:true,project_url:projectUrl,trace_url:page.url(),case_id:sample.case_id,
    checks:['project visible','case roots visible','evaluation annotations visible','understanding and rerank visible'],page_errors:errors};
  assert.equal(errors.length,0);
  fs.writeFileSync(path.join(runDir,'phoenix-browser-verification.json'),JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify(report,null,2));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
