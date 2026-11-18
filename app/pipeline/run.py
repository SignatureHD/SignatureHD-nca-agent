"""The full pipeline for one report: extract, check, rate, draft, validate, render."""
from . import draft as drafting
from . import extract, render, rules_business, rules_consumer, validate


def analyse(pdf_bytes, settings, fixture=None):
    report = extract.extract(pdf_bytes, fixture=fixture)
    rtype = report.get("report_type", "consumer")
    rules = (rules_business if rtype == "business" else rules_consumer).run(report)
    d, sources = drafting.draft(report, rules)
    d, warnings = validate.validate(d, report, sources)
    if not settings.get("rubric_approved_by"):
        warnings.insert(0, "The readiness rubric has not been signed off by a senior debt counsellor for this practice.")
    return {
        "report": report, "rules": rules, "draft": d, "warnings": warnings, "sources": sources, "report_type": rtype,
        "client_pdf": render.client_pdf(report, rules, d, settings),
        "review_pdf": render.review_pdf(report, rules, d, warnings, sources, settings),
    }
