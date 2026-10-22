"""Map stored, source-supported facts to the existing public details contract."""
from __future__ import annotations

from datetime import date
import hashlib
import json
import math
from typing import Any

from pydantic import ValidationError

from .infrastructure.errors import DataAccessError
from .schemas import OpportunityDetailsResponse


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def map_details(opportunity: dict, sources: dict, evidence: dict) -> OpportunityDetailsResponse:
    """Reject broken provenance; leave absent, unknown and conflicting facts unset."""
    try:
        if not all(isinstance(item, dict) for item in (opportunity, sources, evidence)):
            raise ValueError("Invalid stored record shape")
        identifier = opportunity["opportunity_id"]
        source_ids = opportunity["source_ids"]
        if not source_ids or len(source_ids) != len(set(source_ids)) or set(source_ids) != set(sources):
            raise ValueError("Source links do not match the opportunity")
        for source_id, source in sources.items():
            if source["source_id"] != source_id or not isinstance(source["content"], str):
                raise ValueError("Source identity mismatch")
        for evidence_id, item in evidence.items():
            source = sources.get(item["source_id"])
            if (item["evidence_id"] != evidence_id or item["opportunity_id"] != identifier
                    or source is None or not isinstance(item["quote"], str)
                    or not item["quote"].strip() or item["quote"] not in source["content"]):
                raise ValueError("Evidence ownership or quotation mismatch")

        facts = opportunity["facts"]
        if not isinstance(facts, dict):
            raise ValueError("Invalid facts shape")
        for name, fact in facts.items():
            if fact["status"] not in {"known", "unknown", "conflicted"}:
                raise ValueError("Unsupported fact status")
            refs = [evidence[key] for key in fact["evidence_ids"]]
            if any(item["field"] != name for item in refs):
                raise ValueError("Evidence belongs to a different field")
            if fact["status"] == "known":
                if fact["value"] is None or not any(canonical(item["asserted_value"]) == canonical(fact["value"]) for item in refs):
                    raise ValueError("Known fact lacks matching evidence")
            elif fact["value"] is not None:
                raise ValueError("Unknown or conflicting fact has a selected value")
            resolution = fact.get("resolution")
            if fact["status"] == "known" and len({canonical(item["asserted_value"]) for item in refs}) > 1 and not resolution:
                raise ValueError("Conflicting evidence requires an explicit resolution")
            if resolution:
                updates = [evidence[key] for key in resolution["update_evidence_ids"]]
                previous = [evidence[key] for key in resolution["superseded_evidence_ids"]]
                if (resolution["kind"] != "explicit_update" or not updates or not previous
                        or not set(resolution["update_evidence_ids"]).issubset(fact["evidence_ids"])
                        or set(resolution["update_evidence_ids"]) & set(resolution["superseded_evidence_ids"])
                        or any(item["field"] != name for item in updates + previous)
                        or any(canonical(item["asserted_value"]) != canonical(fact["value"]) for item in updates)):
                    raise ValueError("Invalid explicit update")

        def known(name: str):
            fact = facts.get(name)
            return fact["value"] if fact and fact["status"] == "known" else None

        warnings = ["الحقول غير المذكورة لا تعني عدم وجود شروط أو متطلبات."]
        labels = {
            "cost_sar": "رسوم المشاركة", "deadline": "آخر موعد للتقديم",
            "application_status_reported": "حالة التسجيل", "registration_opens_on": "موعد فتح التسجيل",
            "mandatory_requirements": "شروط الأهلية", "required_skills": "المهارات المطلوبة",
            "location": "الموقع", "duration_days": "المدة بالأيام", "application_url": "رابط التقديم",
        }
        for name, fact in facts.items():
            if fact["status"] == "conflicted":
                warnings.append(f"يوجد تعارض غير محسوم في {labels.get(name, 'إحدى معلومات الفرصة')}.")
            elif fact["status"] == "unknown" and name in labels:
                warnings.append(f"{labels[name]} غير محدد في البيانات المجهزة.")

        deadline = known("deadline")
        if deadline is not None:
            if not isinstance(deadline, dict) or deadline.get("precision") != "date" or deadline.get("time") is not None or deadline.get("timezone") is not None:
                raise ValueError("Unsupported deadline precision")
            deadline = date.fromisoformat(deadline["date"]).isoformat()
            warnings.append("موعد التقديم مذكور كتاريخ فقط؛ ساعة الإغلاق والمنطقة الزمنية غير محددتين.")
        for name in ["start_date", "end_date"]:
            if known(name) is not None:
                date.fromisoformat(known(name))
        cost = known("cost_sar")
        if cost is not None and (isinstance(cost, bool) or not isinstance(cost, (int, float)) or not math.isfinite(cost) or cost < 0):
            raise ValueError("Invalid cost")
        if known("application_status_reported") is not None:
            warnings.append("حالة التسجيل الواردة في الإعلان تخص وقت النشر، وليست تحققًا من حالته الآن.")
        if opportunity.get("last_verified_at") is None:
            warnings.append("لم يُسجل وقت تحقق حديث من معلومات الفرصة.")

        version = "sha256:" + hashlib.sha256(canonical({
            "opportunity": opportunity,
            "sources": [sources[key] for key in sorted(source_ids)],
            "evidence": [evidence[key] for key in sorted(evidence)],
        }).encode("utf-8")).hexdigest()
        return OpportunityDetailsResponse(
            opportunity_id=identifier, title=known("title"), source_ids=source_ids,
            evidence_version=version, opportunity_type=known("opportunity_type"),
            description=known("description"), location=known("location"), delivery_mode=known("delivery_mode"),
            start_date=known("start_date"), end_date=known("end_date"), deadline=deadline,
            remote_participation_allowed=known("remote_participation_allowed"),
            physical_attendance_required=known("physical_attendance_required"),
            duration=known("duration_days"), cost=cost, application_url=known("application_url"),
            required_skills=known("required_skills"),
            eligibility_requirements={"mandatory": known("mandatory_requirements"), "preferred": known("preferred_requirements")},
            application_status="requires_verification", last_verified_at=opportunity.get("last_verified_at"),
            data_warnings=warnings,
        )
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        raise DataAccessError() from exc
