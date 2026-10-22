"""Verify candidates by title using the same local encoder and fresh queries."""
import sys
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
    original = read_json(ROOT / 'examples/relevance-eval.sample.json')
    confirmation = read_json(ROOT / 'examples/relevance-confirmation.sample.json')
    manifest = read_json(LOCAL / 'model-manifest.json')
    config = read_json(LOCAL / 'database.json')
    original_hash, confirmation_hash = fingerprint(original), fingerprint(confirmation)
    ids = original['corpus_ids']
    assert len({case['query'] for case in original['queries'] + confirmation['queries']}) == 48
    assert len(confirmation['queries']) == 16
    settings = Settings(database_url='', database_config_file=LOCAL / 'database.json', _env_file=None)
    repo = OpportunityRepository(DatasetLoader(settings), settings)
    print('Checking source evidence and loading the existing offline model.', flush=True)
    details = {identifier: repo.get_details(identifier) for identifier in ids}
    started = perf_counter()
    model = load_model(manifest)
    print(f'Model loaded in {perf_counter() - started:.1f}s. Encoding four titles.', flush=True)
    titles = encode(model, [details[identifier].title for identifier in ids])
    results = []
    threshold = None
    with psycopg.connect(**config, connect_timeout=3) as conn:
        register_vector(conn)
        conn.execute('SET TRANSACTION READ ONLY')
        conn.execute("SELECT set_config('statement_timeout', '3000', true)")

        def measure(cases, split):
            rows = []
            for case in cases:
                vector = encode(model, [case['query']])[0]
                hits = search(conn, vector, ids, manifest, len(ids))
                assert len(hits) == len(ids)
                scores = {identifier: float(score) for identifier, score in zip(ids, titles @ vector, strict=True)}
                for hit in hits:
                    assert hit['evidence_version'] == details[hit['opportunity_id']].evidence_version
                    hit['retrieval_similarity'] = hit['cosine_similarity']
                    hit['cosine_similarity'] = scores[hit['opportunity_id']]
                # Verification ranks are independent from the full-text retrieval order.
                hits.sort(key=lambda hit: (-hit['cosine_similarity'], hit['opportunity_id']))
                rows.append({**case, 'split': split, 'hits': hits})
            print(f'{split}: {len(rows)} queries measured.', flush=True)
            return rows

        calibration = measure([case for case in original['queries'] if case['split'] == 'calibration'], 'calibration')
        threshold = calibrate_threshold([(hit['cosine_similarity'], hit['opportunity_id'] in case['relevant_ids'])
                                         for case in calibration for hit in case['hits']])
        print(f'Frozen title-only threshold: {threshold}', flush=True)
        diagnostic = measure([case for case in original['queries'] if case['split'] == 'evaluation'], 'diagnostic')
        fresh = measure(confirmation['queries'], 'fresh_evaluation')
    assert fingerprint(read_json(ROOT / 'examples/relevance-eval.sample.json')) == original_hash
    assert fingerprint(read_json(ROOT / 'examples/relevance-confirmation.sample.json')) == confirmation_hash
    metrics = {split: summarize(rows, threshold) for split, rows in [
        ('calibration', calibration), ('diagnostic', diagnostic), ('fresh_evaluation', fresh)]}
    acceptable = threshold is not None and all(values['false_positive_candidates'] == 0
                    and values['positive_queries_with_relevant_hit'] == values['positive_queries']
                    for values in [metrics['diagnostic'], metrics['fresh_evaluation']])
    for row in calibration + diagnostic + fresh:
        row['accepted_ids'] = [hit['opportunity_id'] for hit in gate_candidates(row['hits'], threshold)]
    report = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'scope': 'Four source-backed titles, 16 calibration queries, 16 previously viewed diagnostic queries, 16 fresh evaluation queries.',
        'model_id': manifest['model_id'], 'model_revision': manifest['revision'],
        'verification_view': 'title_only', 'threshold': threshold,
        'calibration_benchmark_sha256': original_hash, 'fresh_benchmark_sha256': confirmation_hash,
        'evidence_versions': {identifier: details[identifier].evidence_version for identifier in ids},
        'metrics': metrics, 'development_acceptance_check_passed': acceptable,
        'threshold_used_in_application': False, 'results': calibration + diagnostic + fresh,
        'limitations': ['All queries share the same four documents; this does not establish full-corpus quality.',
                        'Titles can omit useful activities; future corpora require recalibration and relevance validation.',
                        'No user constraints, negation, multi-intent planning, registration or eligibility were tested.'],
    }
    (ROOT / 'results/title-relevance-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# مراجعة تأكيد الصلة بعنوان الفرصة', '',
             '١٩ أكتوبر ٢٠٢٦ — تأكيد ثانٍ بالنموذج المحلي نفسه، دون تنزيل نموذج جديد.', '',
             'فشلت عتبة الوثيقة الكاملة في الحفاظ على جميع الطلبات المناسبة. جرّبنا تمثيل العنوان كوسيلة تحقق، مع ضبط العتبة من المعايرة فقط.', '',
             f'العتبة: {threshold}. عدد الطلبات: ٤٨، منها ١٦ للتحقق الجديد. لم نفعّلها داخل API.', '',
             '| المجموعة | مرشحون مناسبون / متوقعون | مرشحون غير مرتبطين | طلبات مناسبة لها نتيجة | طلبات خارج الموضوع لها نتيجة |',
             '|---|---|---|---|---|']
    for split, label in [('calibration', 'المعايرة'), ('diagnostic', 'تشخيص العينة السابقة'), ('fresh_evaluation', 'تحقق جديد')]:
        values = metrics[split]
        lines.append(f"| {label} | {values['true_positive_candidates']} / {values['true_positive_candidates'] + values['missed_relevant_candidates']} | {values['false_positive_candidates']} | {values['positive_queries_with_relevant_hit']} / {values['positive_queries']} | {values['negative_queries_with_any_hit']} / {values['negative_queries']} |")
    lines += ['', '## الحالات غير المطابقة للتصنيفات', '']
    failures = []
    for row in diagnostic + fresh:
        if set(row['accepted_ids']) != set(row['relevant_ids']):
            failures.append(row['id'])
            lines.append(f"- {row['id']}: {row['query']} — المتوقع {row['relevant_ids']}؛ المقبول {row['accepted_ids']}.")
    if not failures:
        lines.append('تطابق المرشحون المقبولون مع التصنيفات اليدوية في مجموعتي التشخيص والتحقق الجديد.')
    lines += ['', '## القرار', '',
              'نجح شرط التجربة المحدود. نبقي هذه البوابة خيارًا للربط مع تقييدها بنسخة النموذج والبيانات، وتوسيع التقييم قبل الإنتاج.' if acceptable else 'لم يتحقق شرط الربط؛ لا نعتمد البوابة حلًا عامًا ولا نفعّلها داخل التطبيق.', '',
              'مجموعة التشخيص كُشفت في التجربة السابقة؛ لذلك ليست اختبارًا مستقلًا. المجموعة الجديدة كُتبت قبل حساب درجات العناوين، ولم تُستخدم لتعديل العتبة.', '',
              'القبول هنا صلة موضوعية أولية فقط. يلزم التحقق من القيود والتسجيل والأهلية قبل التوصية.', '',
              'التفاصيل في [التقرير الرقمي](title-relevance-report.json)، والمقارنة الأولى في [مراجعة العتبة الأولية](relevance-review.md).']
    (ROOT / 'results/title-relevance-review.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({'threshold': threshold, 'metrics': metrics, 'development_acceptance_check_passed': acceptable}, indent=2), flush=True)


if __name__ == '__main__':
    main()
