"""Calibrate on one query split, freeze the threshold, then measure another."""
import sys
from pathlib import Path
from datetime import datetime, timezone
from time import perf_counter
import json

from local_retrieval import ROOT, LOCAL, read_json, fingerprint, load_model, encode, search
import psycopg
from pgvector.psycopg import register_vector

sys.path.insert(0, str(ROOT / 'backend'))
from app.relevance import calibrate_threshold, gate_candidates, summarize
from app.repository import OpportunityRepository
from app.infrastructure.config import Settings
from app.infrastructure.data_package import DatasetLoader


def main():
    benchmark_path = ROOT / 'examples/relevance-eval.sample.json'
    benchmark = read_json(benchmark_path)
    frozen_benchmark = fingerprint(benchmark)
    cases = benchmark['queries']
    assert len({case['id'] for case in cases}) == len(cases)
    assert len({case['query'] for case in cases}) == len(cases)
    assert {case['split'] for case in cases} == {'calibration', 'evaluation'}
    ids = benchmark['corpus_ids']
    assert all(set(case['relevant_ids']) <= set(ids) for case in cases)
    manifest = read_json(LOCAL / 'model-manifest.json')
    config = read_json(LOCAL / 'database.json')
    settings = Settings(database_url='', database_config_file=LOCAL / 'database.json', _env_file=None)
    repository = OpportunityRepository(DatasetLoader(settings), settings)
    with psycopg.connect(**config, connect_timeout=3) as conn:
        register_vector(conn)
        conn.execute('SET TRANSACTION READ ONLY')
        conn.execute("SELECT set_config('statement_timeout', '3000', true)")
        stored = conn.execute('''SELECT opportunity_id, evidence_version, search_text, model_id, model_revision
            FROM retrieval_demo.documents WHERE opportunity_id=ANY(%s) ORDER BY opportunity_id''', (ids,)).fetchall()
        assert {row[0] for row in stored} == set(ids), 'Run the initial retrieval experiment first'
        for identifier, version, _, model_id, revision in stored:
            assert model_id == manifest['model_id'] and revision == manifest['revision']
            assert repository.get_details(identifier).evidence_version == version, 'Stored embedding evidence is stale'
        corpus_fingerprint = fingerprint(stored)
        model_started = perf_counter()
        model = load_model(manifest)
        load_seconds = perf_counter() - model_started
        rows = []

        def measure(split):
            measured = []
            for case in cases:
                if case['split'] != split:
                    continue
                started = perf_counter()
                vector = encode(model, [case['query']])[0]
                encoding_seconds = perf_counter() - started
                hits = search(conn, vector, ids, manifest, len(ids))
                assert len(hits) == len(ids)
                measured.append({**case, 'hits': hits, 'query_embedding_seconds': round(encoding_seconds, 4)})
            return measured

        calibration = measure('calibration')
        threshold = calibrate_threshold([(hit['cosine_similarity'], hit['opportunity_id'] in case['relevant_ids'])
                                         for case in calibration for hit in case['hits']])
        print(f'Calibration finished. Frozen threshold: {threshold}', flush=True)
        # No evaluation score or label influences threshold selection.
        evaluation = measure('evaluation')
        rows = calibration + evaluation
    assert fingerprint(read_json(benchmark_path)) == frozen_benchmark, 'Benchmark changed during execution'
    metrics = {}
    for split, split_rows in [('calibration', calibration), ('evaluation', evaluation)]:
        metrics[split] = {'baseline_top_2': summarize(split_rows, None, baseline_top_k=2),
                          'gated': summarize(split_rows, threshold)}
    held_out = metrics['evaluation']['gated']
    acceptable = (threshold is not None and held_out['false_positive_candidates'] == 0
                  and held_out['positive_queries_with_relevant_hit'] == held_out['positive_queries'])
    for row in rows:
        row['accepted_ids'] = [hit['opportunity_id'] for hit in gate_candidates(row['hits'], threshold)]
    report = {
        'generated_at': datetime.now(timezone.utc).isoformat(), 'scope': benchmark['scope'],
        'model_id': manifest['model_id'], 'model_revision': manifest['revision'],
        'benchmark_sha256': frozen_benchmark, 'corpus_sha256': corpus_fingerprint,
        'threshold': threshold, 'calibration_rule': 'Zero false-positive candidates on calibration; midpoint above highest negative',
        'threshold_used_in_application': False, 'development_acceptance_check_passed': acceptable,
        'model_load_seconds': round(load_seconds, 3), 'metrics': metrics, 'results': rows,
        'limitations': ['Four opportunities only; held-out queries are not held-out topics or documents.',
                        'Manual labels by the implementer, not an independent relevance judgement.',
                        'No eligibility, structured constraints, negation handling or full API workflow was tested.',
                        'The score cutoff is tied to this model and corpus and is not a probability or universal threshold.'],
    }
    (ROOT / 'results/relevance-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# مراجعة بوابة الصلة الموضوعية', '',
             '١٩ أكتوبر ٢٠٢٦ — أربع فرص، و٣٢ طلبًا: ١٦ للمعايرة و١٦ للتقييم بعد تثبيت العتبة.', '',
             f'العتبة المقاسة: {threshold}. لم تُفعّل داخل API بعد.', '',
             '| مجموعة التقييم | الأسلوب | مرشحون غير مرتبطين | فرص مناسبة استُرجعت / متوقعة | طلبات خارج الموضوع رجعت نتائج |',
             '|---|---|---|---|---|']
    for split, label in [('calibration', 'المعايرة'), ('evaluation', 'التقييم المنفصل')]:
        for mode, mode_label in [('baseline_top_2', 'أقرب نتيجتين'), ('gated', 'بعد بوابة الصلة')]:
            values = metrics[split][mode]
            lines.append(f"| {label} | {mode_label} | {values['false_positive_candidates']} | {values['true_positive_candidates']} / {values['true_positive_candidates'] + values['missed_relevant_candidates']} | {values['negative_queries_with_any_hit']} / {values['negative_queries']} |")
    lines += ['', '## مراجعة الطلبات التي لم تحقق المطلوب', '']
    failures = []
    for row in evaluation:
        relevant, accepted = set(row['relevant_ids']), set(row['accepted_ids'])
        if accepted != relevant:
            failures.append(row['id'])
            lines.append(f"- {row['id']}: {row['query']} — المتوقع {sorted(relevant)}؛ المقبول {sorted(accepted)}.")
    if not failures:
        lines.append('تطابقت مجموعة المرشحين المقبولين مع التصنيفات اليدوية لكل طلب تقييم في هذه العينة.')
    lines += ['', '## القرار', '',
              'نجح شرط التجربة المحدود، ونحتفظ بالبوابة مرشحًا للربط بعد توسيع البيانات والتحقق من حدودها.' if acceptable else 'لم تتحقق شروط الربط. لا نفعّل العتبة في التطبيق؛ نراجع الأخطاء قبل اعتبارها حلًا للصلة.', '',
              'لم نعدّل العتبة أو التصنيفات بعد رؤية نتائج التقييم. نجاح أو فشل هذه العينة لا يعمم على الألف إعلان.', '',
              'المرشح الذي يجتاز الصلة ما زال يحتاج فحص القيود والأهلية والتسجيل. عدم بقاء مرشح لا يعني خلو مجموعة البيانات الكاملة من الفرص.', '',
              'المقارنة تخص العينة نفسها قبل البوابة وبعدها. لا تستخدم احتمالات قبول، ولا تدرب النموذج أو تستدعي API خارجيًا.', '',
              'التفاصيل في [التقرير الرقمي](relevance-report.json) و[طلبات التقييم](../examples/relevance-eval.sample.json).']
    (ROOT / 'results/relevance-review.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({'threshold': threshold, 'metrics': metrics, 'development_acceptance_check_passed': acceptable}, indent=2), flush=True)


if __name__ == '__main__':
    main()
