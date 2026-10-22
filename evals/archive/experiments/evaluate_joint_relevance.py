"""Calibrate an evidence-bound CrossEncoder, then test fresh queries/candidates."""
import csv
import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from time import perf_counter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.topic_verifier import build_candidate, calibrate_policy, verify_topics
from local_reranker import LocalReranker


def read(name):
    return json.loads((ROOT / name).read_text(encoding='utf-8-sig'))


def digest(value):
    return 'sha256:' + hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                               separators=(',', ':')).encode('utf-8')).hexdigest()


def metrics(rows):
    tp = fp = fn = covered = positives = negative_hits = negatives = uncertain = 0
    for row in rows:
        relevant = set(row['relevant_ids'])
        accepted = {r['opportunity_id'] for r in row['decisions'] if r['decision'] == 'related'}
        tp += len(accepted & relevant)
        fp += len(accepted - relevant)
        fn += len(relevant - accepted)
        uncertain += sum(r['decision'] == 'insufficient_evidence' for r in row['decisions'])
        positives += bool(relevant)
        covered += bool(accepted & relevant)
        negatives += not bool(relevant)
        negative_hits += bool(accepted) and not bool(relevant)
    return {'queries': len(rows), 'true_positive_candidates': tp, 'false_positive_candidates': fp,
            'missed_relevant_candidates': fn, 'candidate_precision': tp / (tp + fp) if tp + fp else None,
            'candidate_recall': tp / (tp + fn) if tp + fn else None, 'positive_queries': positives,
            'positive_queries_with_relevant_hit': covered, 'negative_queries': negatives,
            'negative_queries_with_any_hit': negative_hits, 'uncertain_candidate_decisions': uncertain}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-inputs', action='store_true', help='Validate source excerpts and benchmark without loading weights')
    args = parser.parse_args()
    paths = ['examples/relevance-eval.sample.json', 'examples/relevance-confirmation.sample.json',
             'examples/reranker-eval.sample.json', 'results/indexed-documents.json']
    inputs = {path: read(path) for path in paths}
    frozen = {path: digest(value) for path, value in inputs.items()}
    benchmark = inputs[paths[2]]
    raw_path = ROOT / 'data/raw/raw_opportunities.csv'
    assert hashlib.sha256(raw_path.read_bytes()).hexdigest() == benchmark['raw_sha256']
    with raw_path.open(encoding='utf-8-sig', newline='') as stream:
        sources = {row['source_id']: row for row in csv.DictReader(stream)}
    original = []
    for doc in inputs[paths[3]]:
        excerpts = [dict(role='title' if part['role'] == 'title' else 'activity',
                         source_id=part['source_id'], quote=part['text']) for part in doc['text_parts']
                    if part['role'] in {'title', 'activity_description'}]
        linked = sorted({e['source_id'] for e in excerpts})
        original.append(build_candidate(doc['opportunity_id'], {s: sources[s] for s in linked}, linked, excerpts))
    added = [build_candidate(item['opportunity_id'], {s: sources[s] for s in item['source_ids']},
                             item['source_ids'], item['excerpts']) for item in benchmark['added_candidates']]
    all_candidates = original + added
    assert len(all_candidates) == 8 and len({c.opportunity_id for c in all_candidates}) == 8
    fresh = benchmark['fresh_queries']
    prior = inputs[paths[0]]['queries'] + inputs[paths[1]]['queries']
    assert len({q['query'] for q in prior + fresh}) == len(prior) + len(fresh)
    assert all(set(q['relevant_ids']) <= {c.opportunity_id for c in all_candidates} for q in fresh)
    if args.check_inputs:
        print(f'Validated {len(all_candidates)} source-backed candidates and {len(prior) + len(fresh)} distinct queries; no model loaded.')
        return
    print('Source quotations validated. Loading SHA256-verified offline reranker.', flush=True)
    started = perf_counter()
    scorer = LocalReranker()
    load_seconds = perf_counter() - started
    print(f'Reranker loaded in {load_seconds:.1f}s.', flush=True)
    calibration_cases = [q for q in inputs[paths[0]]['queries'] if q['split'] == 'calibration']
    calibration_scores = []
    score_cache = {}
    for i, case in enumerate(calibration_cases, 1):
        scores = scorer([(case['query'], c.passage) for c in original])
        score_cache[case['id']] = scores
        calibration_scores.extend((score, c.opportunity_id in case['relevant_ids'])
                                  for c, score in zip(original, scores, strict=True))
        if i % 4 == 0:
            print(f'Calibration: {i}/{len(calibration_cases)} queries.', flush=True)
    policy = calibrate_policy(calibration_scores)
    print(f'Frozen policy: {asdict(policy)}', flush=True)

    def measure(cases, candidates, split, cached=False):
        rows = []
        versions = {c.opportunity_id: c.topic_evidence_version for c in candidates}
        for i, case in enumerate(cases, 1):
            started = perf_counter()
            callback = (lambda pairs: score_cache[case['id']]) if cached else scorer
            decisions = verify_topics(case['query'], candidates, versions, policy, callback)
            rows.append({**case, 'split': split, 'decisions': decisions,
                         'score_source': 'calibration_cache' if cached else 'live_local_inference',
                         'verification_seconds': round(perf_counter() - started, 4)})
            if i % 4 == 0 or i == len(cases):
                print(f'{split}: {i}/{len(cases)} queries.', flush=True)
        return rows

    calibration = measure(calibration_cases, original, 'calibration', cached=True)
    diagnostic = measure([q for q in prior if q not in calibration_cases], original, 'diagnostic')
    # Only the frozen policy is applied below; fresh labels never select cutoffs.
    evaluation = measure(fresh, all_candidates, 'fresh_evaluation')
    for path in paths:
        assert digest(read(path)) == frozen[path], 'Evaluation input changed during execution'
    measured = {split: metrics(rows) for split, rows in [
        ('calibration', calibration), ('diagnostic', diagnostic), ('fresh_evaluation', evaluation)]}
    fresh_metrics = measured['fresh_evaluation']
    passed = policy.accept_at is not None and fresh_metrics['false_positive_candidates'] == 0 and (
        fresh_metrics['positive_queries_with_relevant_hit'] == fresh_metrics['positive_queries'])
    report = {'generated_at': datetime.now(timezone.utc).isoformat(),
              'scope': benchmark['scope'], 'model_id': scorer.manifest['model_id'],
              'model_revision': scorer.manifest['revision'], 'weights_sha256': scorer.manifest['weights_sha256'],
              'policy': asdict(policy), 'score_kind': 'sigmoid_cross_encoder_logit_not_probability',
              'model_load_seconds': round(load_seconds, 3), 'batch_size': 2, 'max_pair_tokens': 512,
              'benchmark_fingerprints': frozen, 'metrics': measured,
              'fresh_development_acceptance_passed': passed, 'enabled_in_application': False,
              'candidate_topic_versions': {c.opportunity_id: c.topic_evidence_version for c in all_candidates},
              'results': calibration + diagnostic + evaluation,
              'limitations': ['Manual labels and excerpts by the implementer, not independently adjudicated.',
                              'All eight candidates are scored; retrieval candidate recall is not measured.',
                              'Four added IDs are experiment-only source candidates, not production opportunity groups.',
                              'CrossEncoder gives a score, not a generated explanation or a proof of relevance.',
                              'Topic evidence hashes are distinct from the Details API evidence_version.',
                              'No eligibility, registration, constraints, negation or full-corpus readiness is established.']}
    (ROOT / 'results/joint-relevance-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# مراجعة فاحص الطلب ونشاط الفرصة', '', '١٩ أكتوبر ٢٠٢٦ — تجربة محلية مستقلة عن API.', '',
             f"النموذج: {report['model_id']}، نسخة `{report['model_revision']}`. نقرأ الطلب وعنوان الفرصة ونشاطها معًا، بمقاطع مطابقة للمصدر.", '',
             f"حد القبول: {policy.accept_at}، وحد الرفض: {policy.reject_below}. ما بينهما غير مؤكد؛ الدرجة ليست احتمالًا.", '',
             '| المجموعة | مرشحون صحيحون / متوقعون | إضافات خاطئة | طلبات مناسبة لها نتيجة | طلبات خارج الموضوع لها نتيجة | أحكام غير مؤكدة |',
             '|---|---|---|---|---|---|']
    for split, label in [('calibration', 'معايرة: أربع فرص'), ('diagnostic', 'تشخيص سابق: أربع فرص'), ('fresh_evaluation', 'اختبار جديد: ثماني فرص')]:
        m = measured[split]
        lines.append(f"| {label} | {m['true_positive_candidates']} / {m['true_positive_candidates'] + m['missed_relevant_candidates']} | {m['false_positive_candidates']} | {m['positive_queries_with_relevant_hit']} / {m['positive_queries']} | {m['negative_queries_with_any_hit']} / {m['negative_queries']} | {m['uncertain_candidate_decisions']} |")
    lines += ['', '## أخطاء الاختبار الجديد', '']
    errors = 0
    for row in evaluation:
        accepted = {r['opportunity_id'] for r in row['decisions'] if r['decision'] == 'related'}
        if accepted != set(row['relevant_ids']):
            errors += 1
            lines.append(f"- {row['id']}: {row['query']} — المتوقع {row['relevant_ids']}؛ المقبول {sorted(accepted)}.")
    if not errors:
        lines.append('تطابقت النتائج المقبولة مع التصنيفات اليدوية لكل طلب جديد في هذه العينة.')
    timings = sorted(row['verification_seconds'] for row in evaluation)
    lines += ['', '## القرار', '',
              'اجتاز معيار العينة الجديدة المحدود؛ يبقى مرشحًا لتجربة ربط البحث، مع توسيع التقييم قبل الاعتماد.' if passed else 'لم يجتز معيار العينة الجديدة؛ لا نفعّله في التطبيق ولا نعدل العتبة باستخدام أخطاء الاختبار.', '',
              f"زمن فحص ثمانية مرشحين: وسيط {median(timings):.2f} ثانية، وأقصى {max(timings):.2f} ثانية على هذا الجهاز بعد تحميل النموذج.", '',
              'المقاطع المرفقة هي مدخلات موثقة للفحص، وليست تفسيرًا سببيًا من النموذج. لا نؤكد الأهلية أو التسجيل. نفحص جميع المرشحين الثمانية، ولا نقيس جودة مرحلة الاسترجاع هنا.', '',
              'التفاصيل والبصمات وكل الدرجات في [التقرير الرقمي](joint-relevance-report.json). لم نفعّل الفاحص داخل API.']
    (ROOT / 'results/joint-relevance-review.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({'policy': asdict(policy), 'metrics': measured, 'passed': passed}, indent=2), flush=True)


if __name__ == '__main__':
    main()
