"""Consumer report checks and Finance Readiness rating (fixed rubric v1, needs senior counsellor sign-off)."""
from datetime import date

RUBRIC_VERSION = "consumer-v1-draft"


def d(s):
    s = str(s)
    return date.fromisoformat(s if len(s) == 10 else s[:7] + "-01")


def months(a, b):
    return (b.year - a.year) * 12 + (b.month - a.month) - (1 if b.day < a.day else 0)


def run(r):
    asof = d(r["date_requested"])
    accts = r.get("accounts", [])
    flags = []

    def hist(a):
        return a.get("history") or {}

    serious_recent = [a for a in accts if any(v in ("90", "120", "150+") and months(d(m), asof) < 6 for m, v in hist(a).items())]
    for a in accts:
        if a.get("overdue") and a.get("opening_balance") and (a.get("current_balance") or 0) > 1.5 * a["opening_balance"]:
            flags.append({"id": "in_duplum", "acct": a["supplier"],
                          "detail": f"Balance R{a['current_balance']:,} against opening balance R{a['opening_balance']:,}",
                          "sources": ["NCA-s103", "NCA-s101"]})
    for a in accts:
        unpaid = a.get("overdue") or a.get("industry") == "Debt recovery"
        lp = a.get("last_payment")
        if lp and unpaid:
            gap = months(d(lp), asof)
            if gap >= 36:
                detail = (f"Last payment {lp}, {gap // 12} years {gap % 12} months before the report: likely prescribed "
                          "unless the debt was acknowledged in writing or a summons was served")
            else:
                detail = f"Last payment {lp}, under 3 years before the report: not prescribed yet"
        elif a.get("opened") and months(d(a["opened"]), asof) > 36 and unpaid:
            detail = "Account older than 3 years with arrears or in debt recovery, and no last payment date on the report"
        else:
            continue
        flags.append({"id": "prescription_check", "acct": a["supplier"], "detail": detail,
                      "sources": ["NCA-s126B", "REG2015-r19", "NCRG-005-2025-A6.1"]})
    for a in accts:
        if str(a.get("latest_status", "")).startswith("B") and "150+" in hist(a).values():
            flags.append({"id": "closed_after_adverse", "acct": a["supplier"],
                          "detail": "Closed, but worst status still shows serious arrears",
                          "sources": ["NCA-s71A", "REG2015-r17", "NCRG-005-2025-A1.1"]})
    nu = [a for a in accts if str(a.get("latest_status")) == "NU" and a.get("overdue")]
    for a in nu:
        flags.append({"id": "not_updated", "acct": a["supplier"], "detail": "Account in arrears but not updated",
                      "sources": ["NCRG-005-2025-A3.7"]})
    arrears_months = [d(m) for a in accts for m, v in hist(a).items() if v in ("90", "120", "150+")]
    first_arrears = min(arrears_months) if arrears_months else None
    for a in accts:
        amt = a.get("opening_balance") or a.get("limit")
        if first_arrears and a.get("opened") and d(a["opened"]) > first_arrears and amt:
            flags.append({"id": "possible_reckless", "acct": a["supplier"], "opened": a["opened"], "amount": amt,
                          "detail": "Credit granted after serious arrears were already on record",
                          "sources": ["NCA-s80", "NCA-s81", "NCA-s83", "REG2015-r23A"], "internal": True})
    enq = " ".join(e.get("subscriber", "").lower() for e in r.get("enquiries", []))
    for a in accts:
        if a.get("opened") and months(d(a["opened"]), asof) < 12 and a["supplier"].split()[0].lower() not in enq:
            flags.append({"id": "no_enquiry_for_new_account", "acct": a["supplier"], "opened": a["opened"], "internal": True,
                          "detail": "New account with no matching enquiry on this bureau", "sources": []})
    for n in (r.get("consumer") or {}).get("aka_names", []):
        flags.append({"id": "check_aka", "detail": f"Other name on record: {n.get('name')}",
                      "sources": ["NCA-s72", "NCRG-005-2025-A3.6"]})

    total_bal = (r.get("totals") or {}).get("current_balance") or sum(a.get("current_balance") or 0 for a in accts)
    overdue = sum(a.get("overdue") or 0 for a in accts)
    share = overdue / total_bal if total_bal else 0
    new_6m = [a for a in accts if a.get("opened") and months(d(a["opened"]), asof) < 6]
    enq_6m = [e for e in r.get("enquiries", []) if months(d(e["date"]), asof) < 6 and not e.get("own_account")]
    rev = [a for a in accts if a.get("revolving") and a.get("limit")]
    util = sum(a.get("current_balance") or 0 for a in rev) / sum(a["limit"] for a in rev) if rev else 0
    in_arrears = [a for a in accts if a.get("overdue")]
    others_clean = all(str(a.get("latest_status")) in ("0", "NU") for a in accts
                       if a not in in_arrears and not a.get("industry"))
    adverse = sum((r.get("adverse") or {}).values())

    def step(v, cuts):
        for lim, pts in cuts:
            if v <= lim:
                return pts
        return 0

    rubric = [
        ("No serious arrears (90+ days) in the last 6 months", 0 if serious_recent else 30, 30),
        ("No judgments, defaults or court notices", 15 if adverse == 0 else 0, 15),
        ("Overdue amount as a share of total debt", step(share, [(0, 20), (0.10, 12), (0.25, 6)]), 20),
        ("New accounts opened in the last 6 months", step(len(new_6m), [(0, 10), (1, 6), (2, 3)]), 10),
        ("Credit applications in the last 6 months", step(len(enq_6m), [(0, 10), (2, 6), (4, 3)]), 10),
        ("Credit card and facility use against limits", step(util, [(0.30, 10), (0.50, 7), (0.75, 4), (0.999, 2)]), 10),
        ("Other accounts paid up to date", 5 if others_clean else 0, 5),
    ]
    total = sum(x[1] for x in rubric)
    band = "Ready" if total >= 80 else "Nearly ready" if total >= 65 else "Building" if total >= 50 else "Not ready"
    return {"flags": flags, "rubric": rubric, "total": total, "band": band, "rubric_version": RUBRIC_VERSION,
            "metrics": {"overdue": overdue, "total_balance": total_bal, "overdue_share": round(share, 3),
                        "revolving_utilisation": round(util, 3), "new_accounts_6m": [a["supplier"] for a in new_6m],
                        "enquiries_6m": len(enq_6m)}}
