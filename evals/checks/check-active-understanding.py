"""Three bounded real API probes of the new grounded request reader; no browsing."""
import asyncio
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from app.active_understanding import analyze_request,build_active_plan
from app.infrastructure.dependencies import get_app_dependencies
from app.schemas import DiscoveryRequest


async def main():
    deps=get_app_dependencies()
    cases=[('simple','أبي فرص تحليل البيانات باستخدام Excel',{},'resolved'),
        ('free-online','أبي فرص Excel مجانية عن بعد',{},'resolved'),
        ('conflict','أبي فرص Excel عن بعد',{'delivery_modes':['in_person']},'constraint_conflict')]
    results=[]
    for name,query,constraints,expected in cases:
        req=DiscoveryRequest(request_id='active-check-'+name,query=query,profile={},constraints=constraints)
        try:
            proposed=await analyze_request(req,deps)
            plan=build_active_plan(req,proposed)
            results.append({'case':name,'query':query,'passed':plan['status']==expected,
                'status':plan['status'],'proposal':proposed.model_dump(mode='json'),
                'effective_constraints':plan['effective_constraints'],'review_reasons':plan['review_reasons']})
        except Exception as exc:
            results.append({'case':name,'passed':False,'error_type':type(exc).__name__})
        print(json.dumps({k:v for k,v in results[-1].items() if k not in {'proposal','query'}},ensure_ascii=False),flush=True)
    (ROOT/'evals/runs/checks/active-understanding-live-check.json').write_text(json.dumps({'checks':results,
        'passed':all(r['passed'] for r in results),'corpus_quality_approval':False},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    if not all(r['passed'] for r in results):raise SystemExit(1)


if __name__=='__main__':asyncio.run(main())
