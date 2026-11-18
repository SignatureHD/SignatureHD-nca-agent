"""Checks every draft before a counsellor sees it. Problems become warnings on the review sheet."""
import json
import re

from . import corpus

AMOUNT = re.compile(r"R\s?(\d{1,3}(?:[ ,]\d{3})+|\d{3,})")
SA_ID = re.compile(r"\b\d{13}\b")


def _amounts_in(obj):
    s = json.dumps(obj, default=str)
    return {int(x) for x in re.findall(r"\d{3,}", s)}


def _fix_text(t, warnings, where):
    if not isinstance(t, str):
        return t
    t2 = re.sub(r"\s*—\s*", ", ", t).replace("–", "-")
    if SA_ID.search(t2):
        t2 = SA_ID.sub("[ID removed]", t2)
        warnings.append(f"{where}: a 13-digit number (possible ID) was removed")
    return t2


def validate(draft, report, sources):
    warnings = []
    allowed = set(sources)
    known = _amounts_in(report)

    def check_cites(cites, where):
        good = []
        for c in cites or []:
            if c in allowed and corpus.citable(c):
                good.append(c)
            else:
                r = corpus.records().get(c)
                why = "not in force" if r and r["status"] == "not_in_force" else "not citable or not supplied"
                warnings.append(f"{where}: removed citation {c} ({why})")
        return good

    def check_amounts(text, where):
        for m in AMOUNT.finditer(text or ""):
            v = int(re.sub(r"[ ,]", "", m.group(1)))
            if v not in known and v not in (250000, 1000000):   # statutory thresholds are allowed
                warnings.append(f"{where}: amount R{v:,} is not in the report data. Check it".replace(",", " "))

    d = draft
    d["summary"] = _fix_text(d.get("summary", ""), warnings, "Summary")
    check_amounts(d["summary"], "Summary")
    for sec in ("why", "fixes", "counsellor_notes"):
        for i, it in enumerate(d.get(sec, [])):
            where = f"{sec} {i + 1}"
            it["title"] = _fix_text(it.get("title", ""), warnings, where)
            it["body"] = _fix_text(it.get("body", ""), warnings, where)
            check_amounts(it["title"] + " " + it["body"], where)
            it["cites"] = check_cites(it.get("cites"), where)
    for i, it in enumerate(d.get("disputes", [])):
        where = f"dispute {i + 1}"
        it["item"] = _fix_text(it.get("item", ""), warnings, where)
        it["why"] = _fix_text(it.get("why", ""), warnings, where)
        it["steps"] = [_fix_text(s, warnings, where) for s in it.get("steps", [])]
        check_amounts(" ".join([it["item"], it["why"]] + it["steps"]), where)
        it["cites"] = check_cites(it.get("cites"), where)
    for k in ("d30", "d60", "d90"):
        d["plan"][k] = [_fix_text(s, warnings, "plan") for s in d.get("plan", {}).get(k, [])]
    d["rating_comment"] = _fix_text(d.get("rating_comment", ""), warnings, "rating")
    for doubt in report.get("extraction_doubts", []) or []:
        warnings.append(f"Extraction doubt: {doubt}")
    return d, warnings
