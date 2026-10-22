"""Extend the supplied notebook helpers into an evidence-linked local catalog."""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import date
import hashlib
import re

from .details import canonical
from .request_plan import DIGITS
from .request_requirements import normalized

MONTHS = {'يناير': 1, 'فبراير': 2, 'مارس': 3, 'ابريل': 4, 'مايو': 5, 'يونيو': 6,
          'يوليو': 7, 'اغسطس': 8, 'سبتمبر': 9, 'اكتوبر': 10, 'نوفمبر': 11, 'ديسمبر': 12}
DATE = r'(\d{1,2})\s+(' + '|'.join(MONTHS) + r')\s+(\d{4})'
UNKNOWN_FIELDS = ('title', 'organizer', 'opportunity_type', 'description', 'cost_sar',
    'delivery_mode', 'location', 'physical_attendance_required', 'remote_participation_allowed',
    'deadline', 'start_date', 'end_date', 'registration_opens_on', 'duration_days',
    'mandatory_requirements', 'preferred_requirements', 'required_skills', 'application_url',
    'application_status_reported')


def activity_titles(helper, publisher):
    # Some templates quote both the publisher and the activity. The supplied
    # helper keeps both; a publisher name is not a second activity title.
    return list(dict.fromkeys(t for t in helper.get('title_candidates') or [] if t != publisher))


def matches(content, pattern):
    text, offsets = normalized(content)
    text = text.translate(DIGITS)
    for match in re.finditer(pattern, text):
        start, end = offsets[match.start()], offsets[match.end()-1] + 1
        yield match, content[start:end]


def date_value(match, offset=0):
    return date(int(match[3+offset]), MONTHS[match[2+offset]], int(match[1+offset])).isoformat()


def _observations(row, helper):
    text = row['content']
    values = []
    explicit = set()

    def add(field, value, quote, *, update=False):
        item = (field, value, quote)
        if item not in values:
            values.append(item)
        if update:
            explicit.add((field, canonical(value), quote))

    titles = activity_titles(helper, row['source_name'])
    if len(titles) == 1:
        add('title', titles[0], '«' + titles[0] + '»')
    if row['source_name'] in text:
        add('organizer', row['source_name'], row['source_name'])
    fee = helper.get('fee_evidence')
    amount = helper.get('cost_sar')
    if fee and amount is not None and fee in text:
        add('cost_sar', float(amount), fee)
    for match, quote in matches(text, r'المشاركه مجانيه|المشاركة مجانية|رسوم المشاركه (\d+(?:\.\d+)?)|رسوم المشاركة (\d+(?:\.\d+)?)'):
        number = next((v for v in match.groups() if v), None)
        add('cost_sar', float(number) if number else 0, quote)
    type_patterns = {
        'workshop': r'ورشه تطبيقيه|ورشة تطبيقية|ورشه عمل|ورشة عمل|جلسه تدريبيه عمليه|جلسة تدريبية عملية',
        'course': r'برنامج تعليمي متسلسل|دوره تدريبيه|دورة تدريبية|دوره قصيره|دورة قصيرة|دورة من عدة لقاءات',
        'event': r'فعاليه حواريه|فعالية حوارية|لقاء تعريفي|لقاء مفتوح|امسية معرفية',
        'competition': r'منافسه لتطوير فكره|منافسة لتطوير فكرة|مسابقه|مسابقة',
        'volunteering': r'فريق تطوعي|فرصه تطوعيه|فرصة تطوعية|نشاط تطوعي|فرصة للتطوع|مهمة تطوعية مجتمعية',
        'internship': r'تدريب عملي|تدريب ميداني|تدريب مهني داخل المؤسسة'}
    for kind, pattern in type_patterns.items():
        for _, quote in matches(text, pattern):
            add('opportunity_type', kind, quote)
    activity_pattern = (r'(?:سيتناول المشاركون|تدور الانشطه حول|تدور الأنشطة حول|تتنافس الفرق|'
        r'يعمل المشاركون|يستعرض المنظمون|في الجزء الاول|في الجزء الأول|'
        r'سيتعاون المشاركون|سيتعاون المتطوعون|يتعاون المشاركون|يمكن للحضور|'
        r'يتعلم المشاركون|يتدرب المشاركون|يتعرف المشاركون|يتدرب المتطوعون|'
        r'يساعد المتطوعون|يركز المحتوي علي|يعمل المتدرب)[^.\n]+')
    activity = [quote for _, quote in matches(text, activity_pattern)]
    if not activity:
        # An actual source excerpt is a safe search fallback; retain a review flag.
        activity = [text.strip()[:350]]
    add('description', activity[0], activity[0])
    hybrid = list(matches(text, r'البدايه حضوريه في[^.\n]+|البداية حضورية في[^.\n]+'))
    if hybrid and any('عن بعد' in q for _, q in hybrid):
        quote = hybrid[0][1]
        add('delivery_mode', 'hybrid', quote)
        if 'يتطلب' in normalized(quote)[0] and 'حضور' in quote:
            add('physical_attendance_required', True, quote)
            add('remote_participation_allowed', False, quote)
    else:
        for _, quote in matches(text, r'المشاركه عن بعد بالكامل[^.\n]*|المشاركة عن بعد بالكامل[^.\n]*'):
            add('delivery_mode', 'online', quote)
            add('physical_attendance_required', False, quote)
            add('remote_participation_allowed', True, quote)
        for _, quote in matches(text, r'الحضور في[^.\n]+داخل مقر[^.\n]*'):
            add('delivery_mode', 'in_person', quote)
        for _, quote in matches(text, r'العمل حضوري داخل مقر[^.\n]*'):
            add('delivery_mode', 'in_person', quote)
    for match, quote in matches(text, r'(?:الحضور في|البدايه حضوريه في|البداية حضورية في)\s+(.+?)\s+(?:داخل|ثم)'):
        add('location', match[1].strip(), quote)
    for match, quote in matches(text, r'العمل حضوري داخل مقر[^.\n]+ في ([^.\n]+)'):
        add('location', match[1].strip(), quote)
    for field, pattern in {
        'start_date': r'يبدا البرنامج (?:يوم )?' + DATE,
        'end_date': r'ينتهي (?:البرنامج )?(?:يوم )?' + DATE,
        'registration_opens_on': r'(?:يفتح التسجيل|يفتح باب التقديم) (?:يوم )?' + DATE,
        'deadline': r'اخر يوم للتقديم ' + DATE}.items():
        for match, quote in matches(text, pattern):
            try:
                value = date_value(match)
            except ValueError:
                continue
            add(field, {'date': value, 'precision': 'date', 'time': None, 'timezone': None}
                if field == 'deadline' else value, quote)
    for match, quote in matches(text, r'هذا نشاط ليوم واحد بتاريخ ' + DATE):
        value = date_value(match)
        add('start_date', value, quote)
        add('end_date', value, quote)
        add('duration_days', 1, quote)
    for match, quote in matches(text, r'مده (?:البرنامج|النشاط) (\d+) (?:ايام|يوم)|مدة (?:البرنامج|النشاط) (\d+) (?:ايام|يوم)'):
        add('duration_days', int(next(v for v in match.groups() if v)), quote)
    updates = {
        'start_date': r'تغير الموعد من ' + DATE + r' الي ' + DATE,
        'deadline': r'مدد اخر يوم للتقديم من ' + DATE + r' الي ' + DATE}
    for field, pattern in updates.items():
        for match, quote in matches(text, pattern):
            new_date = date_value(match, 3)
            value = {'date': new_date, 'precision': 'date', 'time': None, 'timezone': None} if field == 'deadline' else new_date
            add(field, value, quote, update=True)
    for status, pattern in {
        'closed': r'باب التقديم مغلق حاليا|التسجيل مغلق حاليا|انتهي استقبال الطلبات لهذه النسخة',
        'cancelled': r'الغي البرنامج|الغيت الفعاليه|الغيت الفعالية|تم الغاء|اعتذر المنظمون عن اقامة البرنامج والغوه',
        'open': r'تستقبل الطلبات الان|التسجيل متاح حاليا|باب التقديم مفتوح|التسجيل مفتوح حاليا|باب المشاركة مفتوح وقت نشر الاعلان'}.items():
        for _, quote in matches(text, pattern):
            add('application_status_reported', status, quote)
    for field, pattern in {'mandatory_requirements': r'يشترط[^.\n]+',
                            'preferred_requirements': r'يفضل[^.\n]+'}.items():
        clauses = [quote for _, quote in matches(text, pattern)]
        if clauses:
            # An English or unsupported clause is retained, never partly confirmed.
            add(field, clauses, ' '.join(clauses)) if ' '.join(clauses) in text else None
    return values, explicit, activity, titles


def prepare_catalog(raw_rows, helper_records, *, extras=None):
    helpers = {r['source_id']: r for r in helper_records}
    if len(helpers) != len(raw_rows) or set(helpers) != {r['source_id'] for r in raw_rows}:
        raise ValueError('Helper output must preserve every source exactly once')
    groups = defaultdict(list)
    source_lookup = {}
    for row in raw_rows:
        helper = helpers[row['source_id']]
        if helper['content'] != row['content']:
            raise ValueError('Raw source content changed during preparation')
        titles = activity_titles(helper, row['source_name'])
        url = helper.get('activity_url')
        key = (row['source_name'], titles[0], url) if len(titles) == 1 and url else ('unmerged', row['source_id'])
        groups[key].append(row)
        source_lookup[row['source_id']] = {**row, 'cleaned_content': helper['cleaned_content'],
            'dataset_origin': 'provided_csv', 'content_sha256': hashlib.sha256(row['content'].encode()).hexdigest()}
    package = {'schema_version': 'real-catalog-v1', 'reviewed_by': 'supplied preparation helpers plus evidence-preserving mappings v1',
        'scope_version': 'production-v1-scope-2026-10-22', 'sources': list(source_lookup.values()),
        'opportunities': [], 'evidence': []}
    explicit_resolutions = 0
    for key, rows in groups.items():
        identifier = 'OPP-CSV-' + hashlib.sha256(canonical(key).encode()).hexdigest()[:20]
        rows = sorted(rows, key=lambda r: (r['published_at'], r['source_id']))
        owned_evidence, facts = {}, {f: {'status': 'unknown', 'value': None, 'evidence_ids': []} for f in UNKNOWN_FIELDS}
        by_field, updates, activity_parts = defaultdict(list), defaultdict(list), []
        title_candidates = []
        for row in rows:
            values, explicit, activities, titles = _observations(row, helpers[row['source_id']])
            title_candidates.extend(titles)
            for field, value, quote in values:
                proof_id = 'EV-CSV-' + hashlib.sha256(canonical([row['source_id'], field, value, quote]).encode()).hexdigest()[:24]
                proof = {'evidence_id': proof_id, 'opportunity_id': identifier, 'field': field,
                    'source_id': row['source_id'], 'asserted_value': value, 'quote': quote}
                owned_evidence[proof_id] = proof
                by_field[field].append(proof_id)
                if (field, canonical(value), quote) in explicit:
                    updates[field].append((row['published_at'], proof_id))
            for quote in activities:
                if quote not in [p['text'] for p in activity_parts]:
                    activity_parts.append({'role': 'activity', 'source_id': row['source_id'], 'text': quote[:350]})
        for field, refs in by_field.items():
            refs = list(dict.fromkeys(refs))
            distinct = {canonical(owned_evidence[e]['asserted_value']) for e in refs}
            fact = {'status': 'known' if len(distinct) == 1 else 'conflicted',
                    'value': owned_evidence[refs[0]]['asserted_value'] if len(distinct) == 1 else None,
                    'evidence_ids': refs}
            if len(distinct) > 1 and updates.get(field):
                _, chosen = max(updates[field])
                value = owned_evidence[chosen]['asserted_value']
                previous = [e for e in refs if canonical(owned_evidence[e]['asserted_value']) != canonical(value)]
                fact.update(status='known', value=value, resolution={'kind': 'explicit_update',
                    'update_evidence_ids': [chosen], 'superseded_evidence_ids': previous})
                explicit_resolutions += 1
            facts[field] = fact
        if facts['title']['status'] != 'known':
            title = rows[0]['content'].strip()[:80]
            proof_id = identifier + '-source-label'
            owned_evidence[proof_id] = {'evidence_id': proof_id, 'opportunity_id': identifier,
                'field': 'title', 'source_id': rows[0]['source_id'], 'asserted_value': title, 'quote': title}
            facts['title'] = {'status': 'known', 'value': title, 'evidence_ids': [proof_id]}
        title_ref = owned_evidence[facts['title']['evidence_ids'][0]]
        if not activity_parts:
            activity_parts = [{'role': 'activity', 'source_id': rows[0]['source_id'], 'text': rows[0]['content'][:300]}]
        # Avoid claiming a new end date from an old schedule when only start changed.
        if updates.get('start_date'):
            update_source = owned_evidence[max(updates['start_date'])[1]]['source_id']
            if not any(owned_evidence[e]['source_id'] == update_source for e in by_field.get('end_date', [])):
                facts['end_date'] = {'status': 'unknown', 'value': None, 'evidence_ids': by_field.get('end_date', [])}
        urls = [helpers[r['source_id']].get('activity_url') for r in rows]
        url = next((u for u in urls if u), None)
        opportunity = {'opportunity_id': identifier, 'source_ids': [r['source_id'] for r in rows],
            'canonical_url': url or 'urn:fursah:source:' + rows[0]['source_id'],
            'information_url': url, 'publication_state': 'active' if len(set(title_candidates)) == 1 else 'withdrawn',
            'grouping_reason': 'Exact publisher, quoted title and URL; otherwise retain separate source record',
            'dataset_origin': 'provided_csv', 'last_verified_at': None, 'facts': facts,
            'data_notes': [], 'search_parts': [{'role': 'title', 'source_id': title_ref['source_id'],
                'text': facts['title']['value'] if facts['title']['value'] in source_lookup[title_ref['source_id']]['content'] else title_ref['quote']},
                *activity_parts[:2]]}
        package['opportunities'].append(opportunity)
        package['evidence'].extend(owned_evidence.values())
    if extras:
        package['sources'].extend(deepcopy(extras['sources']))
        package['opportunities'].extend(deepcopy(extras['opportunities']))
        package['evidence'].extend(deepcopy(extras['evidence']))
    return package, {'input_announcements': len(raw_rows), 'prepared_source_observations': len(helper_records),
        'grouped_csv_opportunities': len(groups), 'extra_opportunities': len(extras['opportunities']) if extras else 0,
        'explicit_update_resolutions': explicit_resolutions,
        'quarantined_ambiguous_titles': sum(o['publication_state'] != 'active' for o in package['opportunities']),
        'total_opportunities': len(package['opportunities']), 'total_sources': len(package['sources'])}
