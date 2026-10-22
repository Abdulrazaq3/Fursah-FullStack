"""Bounded, inspectable tool/activity checks; never a general language planner.

Rules only veto unsupported semantic matches. They do not promote a low model
score or confirm eligibility. Original quotations survive normalization.
"""
from dataclasses import dataclass
import re
import unicodedata

from .topic_verifier import TopicCandidate, verify_topics

RULE_VERSION = 'explicit-requirements-v1.3'
TOOLS = {
    'excel': ('Excel', 'Microsoft Excel', 'إكسل', 'إكسيل'),
    'sql': ('SQL', 'إس كيو إل', 'سيكويل'),
    'python': ('Python', 'بايثون', 'بيثون'),
    'power_bi': ('Power BI', 'PowerBI', 'باور بي آي'),
    'tableau': ('Tableau', 'تابلو'),
    'java': ('Java', 'جافا'),
    'javascript': ('JavaScript', 'جافاسكريبت'),
    'flutter': ('Flutter', 'فلاتر'),
    'rust': ('Rust', 'رست'),
    'sqlite': ('SQLite',),
}


def normalized(text):
    chars, offsets = [], []
    replacements = str.maketrans('أإآٱى', 'ااااي')
    for index, char in enumerate(text):
        for item in unicodedata.normalize('NFKC', char).casefold().translate(replacements):
            if item == 'ـ' or unicodedata.category(item) == 'Mn':
                continue
            chars.append(item)
            offsets.append(index)
    return ''.join(chars), offsets


def _pattern(aliases):
    terms = sorted({normalized(alias)[0] for alias in aliases}, key=len, reverse=True)
    # Arabic prepositions/conjunctions may attach to a tool name: بإكسل, وPython.
    return re.compile(r'(?<!\w)(?:(?:وال|بال|لل|ال|وب|و|ب|ل))?(?:'
                      + '|'.join(re.escape(term).replace(r'\ ', r'\s+') for term in terms) + r')(?!\w)')


TOOL_PATTERNS = {name: _pattern(aliases) for name, aliases in TOOLS.items()}
DIRECT_NEGATION = re.compile(r'(?<!\w)(?:بدون|باستثناء|عدا|مو|غير|without|not|exclude|'
    r'لا(?:\s+(?:اريد|ابي|ابغي|ابغى|يشمل|تشمل|يتضمن|تتضمن|استخدم|نستخدم))?|ما\s+(?:ابي|ابغى))\s*$')
REVIEW_CONTEXT = re.compile(r'\b(?:خبرتي|خبرة|سابقا|اشتغلت|اعرف|بدل|بديل|اكره|افضل|مثلا)\b')
NEGATION = re.compile(r'(?<!\w)(?:لا|ليس|ليست|مو|بدون|not|without)(?!\w)')


def tool_mentions(text):
    value, offsets = normalized(text)
    found = []
    for canonical, pattern in TOOL_PATTERNS.items():
        for match in pattern.finditer(value):
            start, end = offsets[match.start()], offsets[match.end()-1]+1
            prefix = re.split(r'[,،;؛.!؟\n]|\b(?:بل|لكن)\b', value[:match.start()])[-1]
            found.append({'tool': canonical, 'quote': text[start:end], 'start': start, 'end': end,
                          'polarity': 'excluded' if DIRECT_NEGATION.search(prefix[-70:]) else 'required'})
    return sorted(found, key=lambda item: (item['start'], -(item['end']-item['start'])))


def activity_mentions(text):
    """Small activity vocabulary for the current verification slice, not all topics."""
    value, offsets = normalized(text)
    rules = {
        'translation': [r'ترجم\w*|مترجم\w*|translation'],
        'database_querying': [r'استعلام\w*|طرح\s+الاسئلة\s+علي\s+الجداول|اسئلة\s+للجداول'],
        'database_administration': [r'سيرفر|خادم|خوادم|صلاحيات|server', r'sql|قواعد\s+البيانات|database'],
        'data_analysis': [r'تحليل\s+(?:ال)?بيانات|مؤشرات|شيتات|تنظيم\s+(?:ال)?جداول|ترتيب\s+(?:ال)?جداول'],
        'public_presentation': [r'(?:ا|ن|ت|ي)?عرض\w*|تقديم', r'افكار\w*|فكر\w*|الجمهور|جمهور|الحضور|الحاضرين'],
        'newsletter_editing': [r'نشر[ةه]|اختيار\s+الاخبار|مراجعة\s+العناوين'],
        'customer_service': [r'عميل|عملاء|زبون|زبائن', r'خدم\w*|متجر|متاجر|محل|ردود|ردي|الرد|اجاب\w*'],
        'correspondence_writing': [r'رسالة|رسائل|مراسلات|خطاب|خطابات', r'كتاب\w*|تحرير|صياغ\w*|تعديل|واضح\w*|وضوح|مفهوم\w*|مختصر\w*'],
        'audio_story': [r'قص[ةه]|حكاي\w*|نص|سرد', r'صوت\w*|تسجيل\w*|اسجل\w*|مسجل\w*|مسموع\w*'],
        'programming': [r'برمج\w*|تعليمات|اوامر|كود|code|programming'],
        'poetry': [r'شعر|قصائد|قافية|العروض'],
        'video_editing': [r'مونتاج|فيديو|مؤثرات\s+بصرية'],
    }
    matches = []
    for activity, groups in rules.items():
        anchors = [re.search(r'(?<!\w)(?:(?:وال|بال|لل|ال|وب|و|ب|ل))?(?:'+pattern+r')(?!\w)', value)
                   for pattern in groups]
        if all(anchors):
            quotes = []
            for match in anchors:
                start, end = offsets[match.start()], offsets[match.end()-1]+1
                quotes.append({'quote': text[start:end], 'start': start, 'end': end})
            matches.append({'activity': activity, 'anchors': quotes})
    # A specific customer-service task is not a second request to write general letters.
    if any(item['activity']=='customer_service' for item in matches):
        matches = [item for item in matches if item['activity']!='correspondence_writing']
    return matches


@dataclass(frozen=True)
class RequestRequirements:
    tools: tuple[dict, ...]
    activities: tuple[dict, ...]
    tool_mode: str
    review_reasons: tuple[str, ...]


def extract_requirements(query: str) -> RequestRequirements:
    if not isinstance(query, str) or not query.strip() or len(query)>2000:
        raise ValueError('Invalid query')
    value, _ = normalized(query)
    tools, activities = tool_mentions(query), activity_mentions(query)
    reasons = []
    if tools and REVIEW_CONTEXT.search(value):
        reasons.append('tool_mention_may_be_history_preference_or_example')
    required = {m['tool'] for m in tools if m['polarity']=='required'}
    excluded = {m['tool'] for m in tools if m['polarity']=='excluded'}
    if required & excluded:
        reasons.append('conflicting_tool_requirements')
    if len(activities)>1:
        reasons.append('multiple_activities_need_interpretation')
    has_or = bool(re.search(r'(?<!\w)(?:او|or)(?!\w)', value))
    mode = 'any' if has_or and len(required)>1 else 'all'
    if has_or and (len(required)<2 or len(activities)>1):
        reasons.append('alternative_scope_needs_interpretation')
    if has_or and len(required)>2:
        reasons.append('mixed_tool_expression_needs_interpretation')
    if NEGATION.search(value) and not excluded:
        reasons.append('negation_scope_needs_interpretation')
    return RequestRequirements(tuple(tools), tuple(activities), mode, tuple(dict.fromkeys(reasons)))


def check_requirements(requirements: RequestRequirements, candidate: TopicCandidate):
    checks = []
    if requirements.review_reasons:
        return {'status':'needs_review','reason_codes':list(requirements.review_reasons),'checks':checks}
    support, negative, activity_support = {}, {}, {}
    for role, source_id, quote in candidate.excerpts:
        for mention in tool_mentions(quote):
            entry={'source_id':source_id,'role':role,'quote':quote,'matched_quote':mention['quote']}
            target=negative if mention['polarity']=='excluded' else support
            target.setdefault(mention['tool'],[]).append(entry)
        for mention in activity_mentions(quote):
            activity_support.setdefault(mention['activity'],[]).append({'source_id':source_id,'role':role,'quote':quote,
                                                                        'anchors':mention['anchors']})
    requested={m['tool'] for m in requirements.tools if m['polarity']=='required'}
    excluded={m['tool'] for m in requirements.tools if m['polarity']=='excluded'}
    if requested:
        matched={t for t in requested if t in support and t not in negative}
        passed=bool(matched) if requirements.tool_mode=='any' else matched==requested
        conflict=bool(requested & set(support) & set(negative))
        checks.append({'kind':'required_tools','mode':requirements.tool_mode,'requested':sorted(requested),
            'status':'supported' if passed and not conflict else 'unknown',
            'reason_code':'requested_tool_in_source' if passed and not conflict else 'required_tool_not_established',
            'evidence':[e for t in requested for e in support.get(t,[])+negative.get(t,[])]})
    for tool in sorted(excluded):
        state='unknown' if tool in support and tool in negative else 'mismatch' if tool in support else 'supported' if tool in negative else 'unknown'
        checks.append({'kind':'excluded_tool','requested':tool,'status':state,
            'reason_code':'source_uses_excluded_tool' if state=='mismatch' else 'negative_tool_evidence_checked',
            'evidence':support.get(tool,[])+negative.get(tool,[])})
    for activity in requirements.activities:
        refs=activity_support.get(activity['activity'],[])
        checks.append({'kind':'activity','requested':activity['activity'],
            'status':'supported' if refs else 'unknown',
            'reason_code':'activity_supported' if refs else 'requested_activity_not_established','evidence':refs})
    status = ('mismatch' if any(c['status']=='mismatch' for c in checks) else
              'unknown' if any(c['status']=='unknown' for c in checks) else 'supported' if checks else 'not_checked')
    return {'status':status,'reason_codes':[c['reason_code'] for c in checks if c['status']!='supported'],'checks':checks}


def verify_with_requirements(query, candidates, expected_versions, policy, score_pairs):
    """Apply bounded constraints without creating new positive semantic matches."""
    requirements=extract_requirements(query)
    baseline=verify_topics(query,candidates,expected_versions,policy,score_pairs)
    results=[]
    for item,result in zip(candidates,baseline,strict=True):
        guard=check_requirements(requirements,item)
        decision,reason=result['decision'],result['reason_code']
        if guard['status']=='mismatch':
            decision,reason='unrelated','explicit_requirement_mismatch'
        elif guard['status'] in {'unknown','needs_review'} and decision=='related':
            decision,reason='insufficient_evidence','explicit_requirement_not_established'
        results.append({**result,'semantic_decision':result['decision'],'decision':decision,'reason_code':reason,
                        'requirements_check':guard,'requirements_rule_version':RULE_VERSION})
    return requirements,results
