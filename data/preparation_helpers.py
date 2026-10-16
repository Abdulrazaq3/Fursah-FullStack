"""Supplied teaching helpers / أدوات مساعدة مقدمة للتدريب.

Use the notebook to understand and inspect each operation. These rules cover a
few observed corpus formats; they are not a complete opportunity extractor.
They preserve source rows and never merge announcements or confirm eligibility.
"""
from pathlib import Path

import pandas as pd

_TITLE = r"«([^»]+)»"
_FEE = r"(المشاركة مجانية|رسوم المشاركة [0-9]+(?:\.[0-9]+)?)"
_AMOUNT = r"([0-9]+(?:\.[0-9]+)?)"
_LINK = r"(https://fursah-[0-9]+\.example/info)"
_DEADLINE = r"آخر يوم للتقديم ([0-9]{1,2})\s+([^.\n]+)\s+([0-9]{4})"
_MONTHS = {
    "يناير": 1, "فبراير": 2, "مارس": 3, "أبريل": 4,
    "مايو": 5, "يونيو": 6, "يوليو": 7, "أغسطس": 8,
    "سبتمبر": 9, "أكتوبر": 10, "نوفمبر": 11, "ديسمبر": 12,
}


def extract_facts(frame: pd.DataFrame) -> pd.DataFrame:
    """Copy cleaned sources; add title suggestions, fee evidence/cost and links.

    نسخ المصادر المنظفة وإضافة اقتراح العنوان ودليل الرسوم والرابط.
    Expects source columns plus cleaned_content. Unknown costs stay missing.
    Multiple quoted phrases are retained rather than guessing a title. Fee
    patterns are limited to observed wording: inspect source text for negation,
    multiple claims, updates and unsupported formats before relying on a value.
    """
    result = frame.copy()
    text = result["cleaned_content"]
    result["title_candidates"] = text.str.findall(_TITLE)
    count = result["title_candidates"].str.len()
    result["title_suggestion"] = result["title_candidates"].str[0].where(count == 1)
    result["title_needs_review"] = count != 1
    result["activity_url"] = text.str.extract(_LINK, expand=False)
    result["fee_evidence"] = text.str.extract(_FEE, expand=False)
    amount = result["fee_evidence"].str.extract(_AMOUNT, expand=False)
    result["cost_sar"] = pd.to_numeric(amount, errors="coerce")
    is_free = result["fee_evidence"].eq("المشاركة مجانية").fillna(False)
    result.loc[is_free, "cost_sar"] = 0
    return result


def related_sources(frame: pd.DataFrame) -> pd.DataFrame:
    """Return rows sharing a nonmissing activity URL; do not merge or delete.

    عرض المصادر ذات رابط نشاط مشترك للمراجعة دون دمج أو حذف.
    A shared URL suggests a review pair, not confirmed identity or agreement.
    Missing URLs are excluded from this view, not from the source dataset.
    """
    shared = frame["activity_url"].notna() & frame["activity_url"].duplicated(keep=False)
    return frame.loc[shared].copy()


def review_deadlines(frame: pd.DataFrame, evaluation_time) -> pd.DataFrame:
    """Add date-only deadline review states at an explicit timezone-aware time.

    إضافة حالة مراجعة الموعد مع وقت تقييم محدد يتضمن المنطقة الزمنية.
    Recognizes 'آخر يوم للتقديم DAY MONTH YEAR'. It does not read published_at
    as a deadline or resolve updates/conflicts. A one-day review buffer around
    the Riyadh evaluation date avoids assigning an invented cutoff timezone:
    dates before yesterday are passed, after tomorrow not_passed, otherwise
    uncertain. This intentionally retains extra cases; it is not an exact-cutoff
    parser. States describe each source claim, not confirmed availability.
    """
    now = pd.Timestamp(evaluation_time)
    if pd.isna(now) or now.tzinfo is None:
        raise ValueError("evaluation_time must include a timezone / حدد المنطقة الزمنية")
    now = now.tz_convert("Asia/Riyadh")
    result = frame.copy()
    parts = result["cleaned_content"].str.extract(_DEADLINE)
    parts.columns = ["day", "month", "year"]
    parts["month"] = parts["month"].str.strip().map(_MONTHS)
    parts = parts.apply(pd.to_numeric, errors="coerce").astype(float)
    result["deadline_date"] = pd.to_datetime(parts, errors="coerce")
    day = pd.Timestamp(now.date())
    buffer = pd.Timedelta(days=1)
    result["deadline_state"] = "uncertain"
    result.loc[result["deadline_date"] < day - buffer, "deadline_state"] = "passed"
    result.loc[result["deadline_date"] > day + buffer, "deadline_state"] = "not_passed"
    result["deadline_evaluated_at"] = now.isoformat()
    return result


def prepare_announcements(frame: pd.DataFrame, evaluation_time) -> pd.DataFrame:
    """Reuse the notebook's cleaning, extraction and deadline steps on any batch.

    إعادة استخدام خطوات الدرس على عينة أو البيانات كاملة، مع حفظ كل مصدر.
    Returns one row per input source with its original columns/text unchanged.
    This is a source-level teaching table, not the application's API schema.
    """
    cleaned = frame.copy()
    cleaned["cleaned_content"] = cleaned["content"].str.strip()
    facts = extract_facts(cleaned)
    return review_deadlines(facts, evaluation_time)


def save_prepared_data(frame: pd.DataFrame, output_path) -> Path:
    """Save teaching records as UTF-8 JSON; return the destination path.

    حفظ جدول التدريب بصيغة JSON مع إبقاء العربية مقروءة والقيم المفقودة null.
    Re-running replaces this chosen JSON file. Date-only serialization is not
    evidence of a midnight cutoff. Use the notebook's separate teaching path.
    """
    path = Path(output_path)
    if path.suffix.lower() != ".json":
        raise ValueError("Choose a .json output file / اختر ملف JSON للمخرجات")
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_json(path, orient="records", force_ascii=False, date_format="iso", indent=2)
    return path
