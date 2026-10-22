"""Small live integration check, separate from future full-corpus quality evals."""
from datetime import datetime,timezone
import json
from pathlib import Path
import time
import httpx

ROOT=Path(__file__).resolve().parents[2]
BASE='http://127.0.0.1:8000'


def main():
    checks=[]
    with httpx.Client(timeout=100,trust_env=False) as client:
        cases=[('free-online','أبي فرص Excel مجانية عن بعد',{},None),
            ('saved-additions','أبي أتعلم بناء وكلاء ذكاء اصطناعي',{},None),
            ('profile-conflict','أبي فرص Excel عن بعد',{'delivery_modes':['in_person']},None),
            ('resolve-query-conflict','أبي فرص Excel عن بعد',{'delivery_modes':['in_person']},'query')]
        for name,query,constraints,resolution in cases:
            body={'request_id':'local-rag-'+name,'query':query,'profile':{},'constraints':constraints}
            if resolution:body['constraint_resolution']=resolution
            started=time.monotonic();reply=client.post(BASE+'/api/v1/discover',json=body);data=reply.json()
            passed=reply.status_code==200
            details=[]
            if name=='profile-conflict':passed=passed and data['status']=='needs_info' and data['constraint_conflict']
            else:
                passed=passed and data['status']=='ok' and 1<=len(data['recommendations'])<=3
                for rec in data['recommendations']:
                    dr=client.get(BASE+'/api/v1/opportunities/'+rec['opportunity_id']);d=dr.json();details.append(d)
                    passed=passed and dr.status_code==200 and d['evidence_version']==rec['evidence_version'] and d['source_ids']==rec['source_ids']
                    if name=='free-online':passed=passed and d['cost']==0 and d['delivery_mode']=='online'
                    if name=='resolve-query-conflict':passed=passed and d['delivery_mode']=='online'
                if name=='saved-additions':passed=passed and any(r['opportunity_id'].startswith('OPP-REAL-') for r in data['recommendations'])
            checks.append({'case':name,'passed':bool(passed),'http_status':reply.status_code,
                'seconds':round(time.monotonic()-started,3),'response':data,'details':details})
            print(json.dumps({'case':name,'passed':bool(passed),'status':data.get('status'),'seconds':checks[-1]['seconds']},ensure_ascii=False),flush=True)
            if not passed:break
    report={'tested_at':datetime.now(timezone.utc).isoformat(),'checks':checks,'passed':len(checks)==4 and all(c['passed'] for c in checks),'quality_benchmark':False}
    (ROOT/'evals/runs/checks/local-rag-api-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    if not report['passed']:raise SystemExit(1)


if __name__=='__main__':main()
