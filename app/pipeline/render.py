"""Branded client PDF and internal counsellor review sheet."""
from html import escape
from pathlib import Path

from weasyprint import HTML

from . import corpus

CSS = (Path(__file__).resolve().parent.parent / "templates" / "style.css").read_text(encoding="utf-8")
BANDS = [("Not ready", 0, 49), ("Building", 50, 64), ("Nearly ready", 65, 79), ("Ready", 80, 100)]
BAND_COLOUR = {"Not ready": "#b3412e", "Building": "#b7791f", "Nearly ready": "#1d6b3a", "Ready": "#1d6b3a"}


def e(t):
    return escape(str(t or ""))


def _basis(cites):
    if not cites:
        return ""
    return "<p class='basis'>Legal basis: " + "; ".join(e(corpus.label(c)) for c in cites) + "</p>"


def _css(footer, brand):
    extra = f"""
    .basis {{ font-size: 8pt; color: #7a8494; margin: 2px 0 0; }}
    .brandbar {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; }}
    .brandbar img {{ max-height: 34px; }}
    h1, h2, .kicker, .col h4 {{ color: {brand}; }} h2 .sn {{ background: {brand}; }}
    .warn {{ background:#fdf0ee; border:1px solid #f2c4bb; border-radius:6px; padding:8px 12px; margin-bottom:10px; font-size:9pt; }}
    .warn li {{ margin-bottom:2px; }}
    .col .who {{ font-size:8pt; color:#64748b; margin:0 0 4px; text-transform:uppercase; letter-spacing:.04em; }}
    ol.steps {{ margin:0; padding-left:16px; }} ol.steps li {{ margin-bottom:4px; }}
    .cta {{ margin-top:16px; border:2px solid {brand}; border-radius:10px; padding:14px 16px; page-break-inside:avoid; }}
    .cta .k {{ font-size:8pt; font-weight:700; letter-spacing:.08em; text-transform:uppercase; color:{brand}; }}
    .cta h3 {{ margin:2px 0 6px; font-size:14pt; color:{brand}; }}
    .cta .btn {{ display:inline-block; background:{brand}; color:#fff; text-decoration:none; font-weight:700; padding:8px 14px; border-radius:6px; margin:6px 0; }}
    .cta ul {{ margin:4px 0 0; padding-left:16px; }} .cta .contact {{ margin-top:6px; }}
    """
    return CSS.replace("{{FOOTER}}", footer.replace('"', "'")) + extra


def next_step_html(st):
    """The single call to action that closes the client PDF."""
    who = st.get("counsellor_name") or st.get("practice_name") or "your debt counsellor"
    url = st.get("booking_url") or ""
    contact = " · ".join(x for x in (st.get("contact_phone"), st.get("contact_email")) if x)
    action = (f"<a class='btn' href='{e(url)}'>Book your review</a><br><span class='muted'>{e(url)}</span>" if url
              else "<p><b>Reply to the email this plan came with, or call us, to book your review.</b></p>")
    return f"""<div class="cta"><div class="k">Your next step</div>
    <h3>Book your free review with {e(who)}</h3>
    <p>In this session we go through your findings, check your budget and agree the steps for days 31 to 90.</p>
    {action}
    <p class="label" style="margin-top:8px">Please bring</p><ul><li>Your latest 3 payslips</li><li>3 months' bank statements</li>
    <li>A list of your monthly expenses</li><li>The reference numbers of any disputes you have lodged</li></ul>
    {f"<p class='contact'>{e(contact)}</p>" if contact else ""}</div>"""


def subject_name(report):
    return (report.get("consumer") or {}).get("name") or (report.get("business") or {}).get("name") or "Client"


def client_pdf(report, rules, d, st):
    brand = st.get("brand_colour") or "#1f3a5f"
    name = subject_name(report)
    practice = st.get("practice_name") or "your debt counsellor"
    ncr = f" · NCR {e(st['ncr_number'])}" if st.get("ncr_number") else ""
    footer = f"Based on {report.get('bureau', '')} report {report.get('ticket_number', '')}, dated {report.get('date_requested', '')}. Not a guarantee of credit."
    pct, band = rules["total"], rules["band"]
    logo = f"<img src='{e(st['logo_url'])}'>" if st.get("logo_url") else ""
    ident = (report.get("consumer") or {}).get("id_masked") or (report.get("business") or {}).get("registration_no") or ""
    why = "".join(f"<div class='point'><div class='n'>{i}</div><div><h4>{e(x['title'])}</h4><p>{e(x['body'])}</p>{_basis(x['cites'])}</div></div>"
                  for i, x in enumerate(d["why"], 1))
    disputes = "".join(
        f"<div class='card'><h4>{e(x['item'])}</h4><p>{e(x['why'])}</p><p class='label'>Free dispute steps</p>"
        f"<ol>{''.join(f'<li>{e(s)}</li>' for s in x['steps'])}</ol>{_basis(x['cites'])}</div>" for x in d["disputes"]) \
        or "<p>Nothing on this report gives grounds for a dispute at this stage.</p>"
    fixes = "".join(f"<div class='point'><div class='tick'>✓</div><div><h4>{e(x['title'])}</h4><p>{e(x['body'])}</p>{_basis(x['cites'])}</div></div>"
                    for x in d["fixes"])
    rubric = "".join(f"<tr><td>{e(n)}</td><td class='num'>{g}</td><td class='num muted'>/ {m}</td></tr>" for n, g, m in rules["rubric"])
    bands = "".join(f"<div class='band {'on' if lo <= pct <= hi else ''}'><b>{n}</b><span>{lo} to {hi}</span></div>" for n, lo, hi in BANDS)
    plan = "".join(f"<div class='col'><h4>{t}</h4><p class='who'>{w}</p><ol class='steps'>{''.join(f'<li>{e(s)}</li>' for s in d['plan'][k])}</ol></div>"
                   for t, k, w in (("Days 1 to 30", "d30", "What you can do now"),
                                   ("Days 31 to 60", "d60", "With your counsellor"),
                                   ("Days 61 to 90", "d90", "With your counsellor")))
    cta = next_step_html(st)
    col = BAND_COLOUR[band]
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{_css(footer, brand)}
    .band.on {{ background:{col}; }} .bandname {{ color:{col}; }}</style></head><body>
    <div class="brandbar"><div class="kicker">{e(practice)}{ncr}</div>{logo}</div>
    <div class="hero"><div class="kicker">Findings and action plan</div><h1>{e(name)}</h1>
    <div class="meta">{e(ident)} · Credit report: {e(report.get('bureau'))}, {e(report.get('date_requested'))}</div></div>
    <div class="summary"><p><b>The short version:</b> {e(d['summary'])}</p></div>
    <h2><span class="sn">1</span> Why you were likely declined</h2>
    <p class="intro">Based on what this report shows. Lenders also look at income and bank statements, which your counsellor will go through with you.</p>{why}
    <h2><span class="sn">2</span> What can be disputed</h2>
    <p class="intro">You have the right to challenge information on your credit report that you believe is wrong. Disputes with the credit bureau are free.</p>{disputes}
    <h2><span class="sn">3</span> What's correct but can be fixed</h2><p class="intro">These items are accurate, but you can improve them.</p>{fixes}
    <h2><span class="sn">4</span> Finance readiness rating and plan</h2>
    <div class="rating"><div class="big">{pct}<small> / 100</small></div><div><div class="bandname">{band}</div><div>{e(d['rating_comment'])}</div></div></div>
    <div class="bands">{bands}</div><table>{rubric}</table>
    <h4 style="margin:14px 0 4px">Your 30, 60 and 90 day action plan</h4>
    <p class="intro">Start with the first column this week. Your counsellor will take you through the rest.</p><div class="cols">{plan}</div>
    {cta}
    <div class="note">This report explains your credit information and suggests next steps. It is not legal advice and not a guarantee that any lender will approve credit. Prepared by {e(practice)} and approved by your debt counsellor.</div>
    </body></html>"""
    return HTML(string=html).write_pdf()


FLAG_TITLES = {
    "prescription_check": "Possible prescription",
    "not_updated": "Accounts not updated",
    "no_enquiry_for_new_account": "No matching enquiry for a new account",
    "check_aka": "Name variations on the report",
}


def split_warnings(warnings):
    """Validator checks the counsellor must act on, versus notes on how the PDF was read."""
    checks = [w for w in warnings if not w.startswith("Extraction doubt:")]
    doubts = [w.replace("Extraction doubt:", "").strip() for w in warnings if w.startswith("Extraction doubt:")]
    return checks, doubts


def _flag_cards(flags):
    """Fallback when the draft has no counsellor notes: one card per flag type, accounts listed."""
    groups = {}
    for f in flags:
        groups.setdefault(f["id"], []).append(f)
    out = []
    for fid, fs in groups.items():
        title = FLAG_TITLES.get(fid, fid.replace("_", " ").capitalize())
        details = list(dict.fromkeys(x.get("detail", "") for x in fs))
        accts = [x.get("acct") for x in fs if x.get("acct")]
        body = " ".join(details) + (f" Accounts: {', '.join(dict.fromkeys(accts))}." if accts else "")
        cites = list(dict.fromkeys(c for x in fs for c in x.get("sources", [])))[:3]
        out.append({"title": title, "body": body, "cites": cites})
    return out


DATA_HANDLING = {"title": "Data handling", "cites": [], "body":
    "ID and account numbers are masked in the client PDF. Keep this report under the client's POPIA consent, "
    "and delete the working copies once the file is closed."}


def review_cards(report, rules, d):
    """The judgement cards shown on the review sheet and on screen."""
    notes = (d or {}).get("counsellor_notes") or _flag_cards(rules.get("flags", []))
    merged = {}
    for x in notes:  # one card per title: repeated issues are listed together
        key = (x.get("title") or "").strip().lower()
        if key in merged:
            m = merged[key]
            if x.get("body") and x["body"] not in m["body"]:
                m["body"] = (m["body"] + " " + x["body"]).strip()
            m["cites"] = list(dict.fromkeys((m.get("cites") or []) + (x.get("cites") or [])))
        else:
            merged[key] = {"title": x.get("title") or "", "body": x.get("body") or "", "cites": list(x.get("cites") or [])}
    notes = list(merged.values())
    return [{**x, "basis": "; ".join(corpus.label(c) for c in (x.get("cites") or []))} for x in notes] + [{**DATA_HANDLING, "basis": ""}]


def review_meta(report, rules):
    score_txt = ""
    for k, v in (report.get("scores") or {}).items():
        if isinstance(v, dict) and v.get("score"):
            score_txt = f"{k.replace('_', ' ').upper()} score {v['score']}"
            break
    parts = [f"{report.get('bureau') or ''} ticket {report.get('ticket_number') or ''}".strip(), score_txt,
             f"Readiness {rules['total']}/100 ({rules['band']})"]
    return " · ".join(p for p in parts if p)


def review_pdf(report, rules, d, warnings, sources, st):
    brand = st.get("brand_colour") or "#1f3a5f"
    name = subject_name(report)
    footer = f"INTERNAL review sheet. Based on {report.get('bureau', '')} report {report.get('ticket_number', '')}, dated {report.get('date_requested', '')}."
    checks, doubts = split_warnings(warnings)
    cards = "".join(f"<div class='card'><h4>{e(x['title'])}</h4><p>{e(x['body'])}</p>{_basis(x.get('cites'))}</div>"
                    for x in review_cards(report, rules, d))
    check_html = ("<div class='warn'><b>Check before approving</b><ul>" + "".join(f"<li>{e(w)}</li>" for w in checks) + "</ul></div>") if checks else ""
    doubt_html = ("<h4 style='margin-top:14px'>How the report was read</h4><p class='intro'>Points the reader was unsure about. "
                  "Check them against the original report if they affect your advice.</p><ul class='small'>"
                  + "".join(f"<li>{e(w[:400])}</li>" for w in doubts[:8]) + "</ul>") if doubts else ""
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{_css(footer, brand)}
    ul.small li {{ font-size: 8.6pt; margin-bottom: 3px; }}</style></head><body>
    <div class="draft">INTERNAL. Counsellor review sheet. Not for the client.</div>
    <div class="hero"><div class="kicker">Counsellor review notes</div><h1>{e(name)}</h1>
    <div class="meta">{e(review_meta(report, rules))}</div></div>
    <p class="intro">These items were raised by the automatic checks and need a counsellor's judgement before the client PDF is approved.</p>
    {cards}{check_html}{doubt_html}
    </body></html>"""
    return HTML(string=html).write_pdf()
