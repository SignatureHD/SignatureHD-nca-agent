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


def _decode(v):
    """Models sometimes return nested values as JSON strings; decode them."""
    if isinstance(v, str) and v.strip()[:1] in "[{":
        try:
            return _decode(json.loads(v))
        except ValueError:
            return v
    if isinstance(v, list):
        return [_decode(x) for x in v]
    if isinstance(v, dict):
        return {k: _decode(x) for k, x in v.items()}
    return v


def _as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def normalise(d):
    """Coerce the draft into the shape the renderer expects, whatever small deviations the model made."""
    d = _decode(d) if isinstance(d, dict) else {}
    for sec in ("why", "fixes", "counsellor_notes"):
        items = []
        for it in _as_list(d.get(sec)):
            if isinstance(it, str):
                title, _, body = it.partition(": ")
                it = {"title": title if body else "", "body": body or it}
            if isinstance(it, dict):
                items.append({"title": str(it.get("title") or ""), "body": str(it.get("body") or ""),
                              "cites": [str(c) for c in _as_list(it.get("cites"))]})
        d[sec] = items
    disputes = []
    for it in _as_list(d.get("disputes")):
        if isinstance(it, str):
            it = {"item": it, "why": "", "steps": []}
        if isinstance(it, dict):
            disputes.append({"item": str(it.get("item") or ""), "why": str(it.get("why") or ""),
                             "steps": [str(x) for x in _as_list(it.get("steps"))],
                             "cites": [str(c) for c in _as_list(it.get("cites"))]})
    d["disputes"] = disputes
    plan = d.get("plan") if isinstance(d.get("plan"), dict) else {}
    d["plan"] = {k: [str(x) for x in _as_list(plan.get(k))] for k in ("d30", "d60", "d90")}
    for k in ("summary", "rating_comment"):
        d[k] = d.get(k) if isinstance(d.get(k), str) else ("" if d.get(k) is None else str(d.get(k)))
    return d


def validate(draft, report, sources):
    draft = normalise(draft)
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
