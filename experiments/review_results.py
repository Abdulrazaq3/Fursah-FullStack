"""Write an Arabic review of an actual completed experiment report."""
import json
from pathlib import Path
from statistics import mean
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]


def main():
    output = ROOT / 'results'
    report = json.loads((output / 'retrieval-report.json').read_text(encoding='utf-8'))
    positive = [row for row in report['results'] if row['recall_at_2'] is not None]
    negative = [row for row in report['results'] if row['recall_at_2'] is None]
    assert report['counts']['queries'] == len(report['results']) == 8
    assert len(positive) == 6 and len(negative) == 2
    score = report['macro_recall_at_2_positive_queries']
    assert abs(score - mean(row['recall_at_2'] for row in positive)) < 1e-8
    lines = [
        '# مراجعة أول تجربة استرجاع محلية', '',
        f"وقت إنشاء التقرير بتوقيت الرياض: {datetime.fromisoformat(report['generated_at']).astimezone(ZoneInfo('Asia/Riyadh')).isoformat()}", '',
        'هذه نتائج تشغيل فعلي على أربع فرص يدوية وثمانية طلبات. الاسترجاع هنا يختبر الصلة بالموضوع؛ أهلية المستخدم والتسجيل والقيود لم تُفحص.', '',
        f'**متوسط Recall@2 للطلبات الستة ذات النتائج المتوقعة: {score:.1%}.**', '',
        'هذا المقياس يحسب نسبة الفرص الصحيحة التي ظهرت ضمن أول نتيجتين لكل طلب، ثم يأخذ المتوسط. ليس دقة توصيات النظام الكامل.', '',
        '| الطلب | أول نتيجتين: معرّف الفرصة والتشابه | Recall@2 |',
        '|---|---|---|',
    ]
    for row in report['results']:
        hits = '؛ '.join(f"{hit['opportunity_id']} ({hit['cosine_similarity']:.3f})" for hit in row['hits'])
        recall = f"{row['recall_at_2']:.0%}" if row['recall_at_2'] is not None else 'لا ينطبق'
        query = row['query'].replace('|', '\\|')
        lines.append(f'| {query} | {hits} | {recall} |')
    timings = report['timings_seconds']
    lines += [
        '', '## السرعة المقاسة', '',
        f"- تحميل النموذج من القرص والتحقق من البصمة: {timings['model_load']:.3f} ثانية.",
        f"- تحويل الفرص الأربع إلى متجهات: {timings['document_embedding']:.3f} ثانية.",
        f"- حفظ العينة والمتجهات: {timings['storage']:.3f} ثانية.",
        f"- متوسط تحويل الطلب إلى متجه بعد تحميل النموذج: {mean(row['query_embedding_seconds'] for row in report['results']):.3f} ثانية.",
        f"- متوسط البحث في قاعدة البيانات: {1000 * mean(row['database_search_seconds'] for row in report['results']):.3f} مللي ثانية.",
        '', 'هذه قياسات متتابعة على هذا الجهاز لعينة صغيرة؛ ليست اختبار ضغط أو زمن استجابة خدمة كاملة.', '',
        '## الأخطاء والقرار التالي', '',
    ]
    failures = [row['case_id'] for row in positive if row['recall_at_2'] < 1]
    if failures:
        lines.append('طلبات فقدت فرصة متوقعة ضمن أول نتيجتين: ' + '، '.join(failures) + '. نراجع النص المفهرس وترتيب النتائج قبل توسيع التجربة.')
    else:
        lines.append('ظهرت جميع الفرص المتوقعة ضمن أول نتيجتين للطلبات الستة. نبقي هذه التركيبة خط أساس للتجارب التالية، ونوسع البيانات وحالات التقييم قبل اعتماد جودة الاسترجاع.')
    lines += [
        '',
        'الطلبان عن الطبخ والإسعافات لا يملكان فرصًا ذات صلة في العينة، ومع ذلك أعاد Top-K جيرانًا. هذه النتائج لا تصلح توصيات. نحتاج فحص صلة وسياسة امتناع أو طلب توضيح؛ لم نختبرهما في هذه التجربة، ولم نحدد عتبة تشابه من ثمانية أمثلة فقط.', '',
        'درجات التشابه ليست احتمالات قبول. مقارنة بحث قاعدة البيانات بالحساب المحلي نجحت ضمن هامش الخطأ المسجل في التقرير.', '',
        'بعد مراجعة الاسترجاع نربط القيود المنظمة والأدلة، ونختبر التسجيل والأهلية ونقص المعلومات قبل عرض توصية للمستخدم.', '',
        f"النموذج: {report['configuration']['embedding_model']}؛ النسخة: `{report['configuration']['model_revision']}`؛ الأبعاد: {report['configuration']['dimensions']}.", '',
        'التفاصيل القابلة للمراجعة في [التقرير الرقمي](retrieval-report.json) و[وثائق البحث](indexed-documents.json).',
    ]
    (output / 'retrieval-review.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('Measured-results review written to results/retrieval-review.md')


if __name__ == '__main__':
    main()
