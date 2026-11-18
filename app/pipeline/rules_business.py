"""Business (company) report checks and Finance Readiness rating (fixed rubric v1, needs sign-off)."""
from datetime import date

RUBRIC_VERSION = "business-v1-draft"
BAND_PTS = {"C1": 20, "C2": 18, "C3": 15, "C4": 10, "C5": 8, "C6": 0, "C7": 0}
PRINCIPAL_PTS = {"C1": 15, "C2": 13, "C3": 10, "C4": 7, "C5": 3, "C6": 0}


def d(s):
    return date.fromisoformat(str(s)[:10])


def months(a, b):
    return (b.year - a.year) * 12 + (b.month - a.month) - (1 if b.day < a.day else 0)


def run(r):
    asof = d(r["date_requested"])
    flags = []
    old = [e for e in r.get("enquiries", []) if months(d(e["date"]), asof) >= 12]
    if old:
        flags.append({"id": "old_enquiries", "items": old,
                      "detail": "Enquiries older than 12 months still showing. Only disputable if the NCA applied: "
                                "turnover and assets below R1 million and principal debt below R250 000 when applying",
                      "sources": ["NCA-s4", "REG2015-r17", "NCRG-005-2025-A1.3", "NCA-s72"]})
    for p in r.get("principals", []):
        if p.get("status") == "Active" and not p.get("contribution_pct"):
            flags.append({"id": "zero_contribution", "detail": f"{p['name']} recorded with 0% contribution",
                          "sources": ["NCA-s72", "NCRG-005-2025-A3.6"]})
    for e in r.get("enquiries", []):
        if e.get("own_account") or "counsellor" in str(e.get("note", "")).lower():
            flags.append({"id": "own_enquiry_name", "internal": True, "detail": f"Own enquiry listed under {e.get('subscriber')}",
                          "sources": []})
    flags.append({"id": "business_client", "internal": True,
                  "detail": "Company report. Check the director's personal position and the basis of the service",
                  "sources": ["NCA-s4", "NCA-s86"]})

    s = r.get("scores", {})
    adv = sum((r.get("adverse") or {}).values())
    ext_12m = [e for e in r.get("enquiries", []) if months(d(e["date"]), asof) < 12
               and not e.get("own_account") and "note" not in e]
    age = months(d(r["business"]["registration_date"]), asof) / 12
    changes = [a for a in r.get("principal_archive", []) if a.get("date_resigned") and months(d(a["date_resigned"]), asof) < 36]
    rubric = [
        ("Clean record (no judgments, defaults or notices)", 30 if adv == 0 else max(0, 30 - 10 * adv), 30),
        ("Business credit score band", BAND_PTS.get((s.get("commercial_lending") or {}).get("band"), 0), 20),
        ("Director's personal risk score", PRINCIPAL_PTS.get((s.get("sme_principal") or {}).get("band"), 0), 15),
        ("Recent credit applications", 10 if not ext_12m else 8 if len(ext_12m) == 1 else 5 if len(ext_12m) <= 3 else 2, 10),
        ("Age of business", 10 if age >= 10 else 7 if age >= 5 else 4 if age >= 2 else 1, 10),
        ("Track record lenders can see (trade payments, property)",
         (5 if r.get("trade_payment_records") else 0) + (5 if r.get("deeds") else 0), 10),
        ("Stable leadership (no director changes in 3 years)", 5 if not changes else 2, 5),
    ]
    total = sum(x[1] for x in rubric)
    band = "Ready" if total >= 80 else "Nearly ready" if total >= 65 else "Building" if total >= 50 else "Not ready"
    return {"flags": flags, "rubric": rubric, "total": total, "band": band, "rubric_version": RUBRIC_VERSION,
            "metrics": {"business_age_years": round(age, 1), "external_enquiries_12m": len(ext_12m)}}
