"""Regrade saved responses/traces offline; makes no embedding or LLM calls."""
import argparse
from collections import Counter,defaultdict
import hashlib
import importlib
import json
from pathlib import Path
from statistics import mean

from .run import CaseSpans,run_graders,grade_failures,verify_manifest
from app.schemas import DiscoveryResponse


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',required=True,type=Path)
    parser.add_argument('--cases',default=Path(__file__).parent/'cases/dev.jsonl',type=Path)
    parser.add_argument('--graders',default='evals.catalog_graders')
    args=parser.parse_args()
    verify_manifest(args.cases)
    rows=[json.loads(l) for l in args.run.read_text(encoding='utf8').splitlines() if l.strip()]
    cases={c['case_id']:c for c in (json.loads(l) for l in args.cases.read_text(encoding='utf8').splitlines() if l.strip())}
    trace_file=args.run.parent/'traces.jsonl' if args.run.name=='results.jsonl' else args.run.with_suffix('.traces.jsonl')
    traces=defaultdict(list)
    for line in trace_file.read_text(encoding='utf8').splitlines():
        event=json.loads(line);traces[event['case_id']].append((event['name'],event['attributes']))
    module=importlib.import_module(args.graders)
    records=[];scores=defaultdict(list);failures=defaultdict(list);outcomes=Counter()
    for row in rows:
        response=DiscoveryResponse.model_validate(row['response'])
        grades,errors=run_graders(module.GRADERS,cases[row['case_id']],response,CaseSpans(traces[row['case_id']]))
        failed=grade_failures(grades,cases[row['case_id']],module.CRITICAL_METRICS)
        fatal=row['outcome'] if row['outcome'] in {'ERROR','TIMEOUT','PROTOCOL ERROR'} else None
        outcome='GRADER ERROR' if errors else fatal or ('FAIL' if failed else 'PASS')
        records.append({**row,'original_outcome':row['outcome'],'outcome':outcome,
            'grades':[g.__dict__ for g in grades],'grader_errors':errors})
        outcomes[outcome]+=1
        for grade in grades:
            scores[grade.metric].append(grade.score)
        for grade in failed:failures[grade.metric].append(row['case_id'])
    output=args.run.with_suffix('.rescored.jsonl');summary_file=args.run.with_suffix('.rescored.summary.json')
    if output.exists() or summary_file.exists():raise SystemExit('Preserve prior offline rescoring artifacts')
    output.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records),encoding='utf8')
    summary={'cases':len(records),'outcomes':dict(outcomes),'metrics':{k:{'mean':mean(v),'n':len(v),'failing_cases':failures[k]} for k,v in scores.items()},
        'original_run':str(args.run),'original_run_sha256':hashlib.sha256(args.run.read_bytes()).hexdigest(),
        'traces_sha256':hashlib.sha256(trace_file.read_bytes()).hexdigest(),
        'graders_sha256':hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest(),
        'cases_sha256':hashlib.sha256(args.cases.read_bytes()).hexdigest(),
        'new_model_calls':0,'holdout_evaluated':False,'production_approval':False,
        'reason':'Independent original-source availability audit added after trace review; no labels or system decisions changed'}
    summary_file.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'outcomes':dict(outcomes),'new_model_calls':0,'report':str(summary_file)},ensure_ascii=False))
    if any(k!='PASS' and v for k,v in outcomes.items()):raise SystemExit(2)


if __name__=='__main__':main()
