"""Independent offline availability audit of original source text, not parsed facts.

This supplements component trace-consistency grades. It uses the newest source
publication, literal closure/cancellation and explicit dates, with a full-day
margin for date-only boundaries. No model calls or runtime parser imports.
"""
from datetime import date,datetime,timedelta
import re
import unicodedata

MONTHS={'يناير':1,'فبراير':2,'مارس':3,'ابريل':4,'مايو':5,'يونيو':6,
    'يوليو':7,'اغسطس':8,'سبتمبر':9,'اكتوبر':10,'نوفمبر':11,'ديسمبر':12}
DATE=r'(\d{1,2})\s+('+'|'.join(MONTHS)+r')\s+(\d{4})'
CLOSURES=[r'اغلق التسجيل لاكتمال المقاعد',r'باب التقديم مغلق حاليا',r'التسجيل مغلق حاليا',
    r'انتهي استقبال الطلبات لهذه النسخة',r'اعتذر المنظمون عن اقامة البرنامج والغوه',
    r'تم الغاء البرنامج',r'الغيت الفعالية']


def normalize(text):
    clean=''.join(c for c in text if unicodedata.category(c)!='Mn')
    return clean.translate(str.maketrans('أإآٱى٠١٢٣٤٥٦٧٨٩','ااااي0123456789'))


def original_availability(source,evaluation_time):
    text=normalize(source['content'])
    violations=[]
    def add(rule,quote,value=None):
        violations.append({'source_id':source['source_id'],'rule':rule,'normalized_quote':quote,'value':value})
    for pattern in CLOSURES:
        for match in re.finditer(pattern,text):
            # A negated claim is not proof of closure.
            prefix=text[max(0,match.start()-20):match.start()].split('.')[-1]
            if re.search(r'(?<!\w)(?:ليس|لم|لا|لن)(?!\w)',prefix):continue
            add('explicitly_closed_or_cancelled',match[0])
    cutoff=datetime.fromisoformat(evaluation_time).date()-timedelta(days=1)
    patterns={'activity_ended':r'ينتهي(?: البرنامج)?(?: يوم)?\s+'+DATE,
        'one_day_activity_ended':r'هذا نشاط ليوم واحد بتاريخ\s+'+DATE,
        'application_deadline_passed':r'اخر يوم للتقديم\s+'+DATE}
    for rule,pattern in patterns.items():
        values=[]
        for match in re.finditer(pattern,text):
            try:values.append((date(int(match[3]),MONTHS[match[2]],int(match[1])),match[0]))
            except ValueError:continue
        # Contradicting dates in one latest announcement need manual review.
        if len({v for v,_ in values})==1 and values[0][0]<cutoff:
            add(rule,values[0][1],values[0][0].isoformat())
    return violations


def audit_response(case,response,package):
    sources={s['source_id']:s for s in package['sources']}
    violations=[]
    for rec in response.get('recommendations',[]):
        owned=[sources[s] for s in rec['source_ids'] if s in sources]
        if not owned:
            violations.append({'opportunity_id':rec['opportunity_id'],'rule':'missing_original_sources'})
            continue
        latest=max(owned,key=lambda s:(s.get('published_at') or '',s['source_id']))
        for finding in original_availability(latest,case['evaluation_time']):
            violations.append({'opportunity_id':rec['opportunity_id'],**finding})
    return {'metric':'source.availability','score':float(not violations),'violations':violations}
