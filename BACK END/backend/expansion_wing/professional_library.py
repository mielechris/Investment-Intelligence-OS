from __future__ import annotations

from dataclasses import asdict, dataclass

from .investor_intelligence import ProfessionalProfile


@dataclass(frozen=True)
class AcquisitionPlan:
    professional_id: str
    specialties: tuple[str, ...]
    source_priority: tuple[str, ...]
    hypothesis_status: str = "SOURCE_REVIEW_REQUIRED"
    acquisition_status: str = "NOT_ACTIVATED"
    external_requests_allowed: bool = False


_LIBRARY = (
    ("warren_buffett", "Warren Buffett", ("VALUE_QUALITY", "CAPITAL_ALLOCATION"), ("EQUITY",), ("SHAREHOLDER_LETTER", "SEC_FILING", "PUBLIC_INTERVIEW")),
    ("charlie_munger", "Charlie Munger", ("VALUE_QUALITY", "MENTAL_MODELS"), ("EQUITY",), ("SHAREHOLDER_LETTER", "PUBLIC_INTERVIEW", "UNIVERSITY_LECTURE")),
    ("peter_lynch", "Peter Lynch", ("GROWTH_AT_REASONABLE_PRICE",), ("EQUITY",), ("PUBLIC_INTERVIEW", "UNIVERSITY_LECTURE", "BOOK_NOTE")),
    ("howard_marks", "Howard Marks", ("CYCLE_CREDIT", "DISTRESSED"), ("FIXED_INCOME", "DISTRESSED"), ("SHAREHOLDER_LETTER", "PUBLIC_INTERVIEW")),
    ("stanley_druckenmiller", "Stanley Druckenmiller", ("MACRO", "LIQUIDITY"), ("MACRO", "EQUITY", "FUTURES"), ("PUBLIC_INTERVIEW", "CONFERENCE")),
    ("george_soros", "George Soros", ("REFLEXIVITY", "MACRO"), ("MACRO", "FX"), ("UNIVERSITY_LECTURE", "PUBLIC_INTERVIEW", "BOOK_NOTE")),
    ("paul_tudor_jones", "Paul Tudor Jones", ("MACRO", "RISK_CONTROL"), ("FUTURES", "COMMODITY"), ("PUBLIC_INTERVIEW", "CONFERENCE")),
    ("joel_greenblatt", "Joel Greenblatt", ("SYSTEMATIC_VALUE_QUALITY",), ("EQUITY", "QUANT_FACTOR"), ("UNIVERSITY_LECTURE", "ACADEMIC_RESEARCH", "BOOK_NOTE")),
    ("bill_gross", "Bill Gross", ("DURATION_CREDIT",), ("FIXED_INCOME", "TREASURY"), ("SHAREHOLDER_LETTER", "PUBLIC_INTERVIEW")),
    ("ed_seykota", "Ed Seykota", ("SYSTEMATIC_TREND",), ("FUTURES", "TREND_FOLLOWING"), ("PUBLIC_INTERVIEW", "ARTICLE")),
    ("cliff_asness", "Cliff Asness", ("ACADEMIC_FACTORS",), ("QUANT_FACTOR",), ("ACADEMIC_RESEARCH", "ARTICLE")),
    ("jim_rogers", "Jim Rogers", ("COMMODITY_CYCLES",), ("COMMODITY", "FUTURES"), ("PUBLIC_INTERVIEW", "ARTICLE")),
    ("jay_ritter", "Jay Ritter", ("IPO_EMPIRICS",), ("IPO",), ("ACADEMIC_RESEARCH", "UNIVERSITY_LECTURE")),
    ("john_t_barone", "John T. Barone", ("PHYSICAL_COMMODITY_DOMAIN_RESEARCH",),
        ("COMMODITY", "FUTURES", "AGRICULTURE", "ENERGY"),
        ("PAID_SUBSCRIPTION_COMMODITY_RESEARCH",)),
)


def initial_library() -> tuple[dict, ...]:
    result = []
    for identifier, name, hypotheses, specialties, source_priority in _LIBRARY:
        profile = ProfessionalProfile(identifier, name, "INVESTOR_OR_SPECIALIST", hypotheses)
        profile.validate()
        plan = AcquisitionPlan(identifier, specialties, source_priority)
        result.append({"profile": asdict(profile), "plan": asdict(plan), "opinions_are_hypotheses": True})
    return tuple(result)
