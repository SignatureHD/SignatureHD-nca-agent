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
    """
    return CSS.replace("{{FOOTER}}", footer.replace('"', "'")) + extra


def subject_name(report):
    return (report.get("consumer") or {}).get("name") or (report.get("business") or {}).get("name") or "Client"


def client_pdf(report, rules, d, st):
    brand = st.get("brand_colour") or "#1f3a5f"
    name = subject_name(report)
    practice = st.get("practice_name") or report.get("requested_by") or "Your debt counsellor"
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
    plan = "".join(f"<div class='col'><h4>{t}</h4><ul>{''.join(f'<li>{e(s)}</li>' for s in d['plan'][k])}</ul></div>"
                   for t, k in (("Days 1 to 30", "d30"), ("Days 31 to 60", "d60"), ("Days 61 to 90", "d90")))
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
    <h4 style="margin:14px 0 8px">Your 30, 60 and 90 day plan</h4><div class="cols">{plan}</div>
    <div class="note">This report explains your credit information and suggests next steps. It is not legal advice and not a guarantee that any lender will approve credit. Prepared by {e(practice)} and approved by your debt counsellor.</div>
    </body></html>"""
    return HTML(string=html).write_pdf()


def review_pdf(report, rules, d, warnings, sources, st):
    brand = st.get("brand_colour") or "#1f3a5f"
    name = subject_name(report)
    footer = f"INTERNAL review sheet. {report.get('bureau', '')} report {report.get('ticket_number', '')}."
    warn = ("<div class='warn'><b>Validator warnings</b><ul>" + "".join(f"<li>{e(w)}</li>" for w in warnings) + "</ul></div>") if warnings else \
        "<div class='summary'><p>No validator warnings.</p></div>"
    notes = "".join(f"<div class='card'><h4>{e(x['title'])}</h4><p>{e(x['body'])}</p>{_basis(x['cites'])}</div>" for x in d["counsellor_notes"])
    flags = "".join(f"<li><b>{e(f['id'])}</b>: {e(f.get('detail'))}{' (internal)' if f.get('internal') else ''}</li>" for f in rules["flags"])
    srcs = "".join(f"<li>{e(s)}: {e(corpus.label(s))}, {e(corpus.records()[s]['heading'])}</li>" for s in sources)
    approved = st.get("rubric_approved_by") or "NOT YET APPROVED"
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>{_css(footer, brand)}
    ul.small li {{ font-size: 8.8pt; }}</style></head><body>
    <div class="draft">INTERNAL. Counsellor review sheet. Not for the client.</div>
    <div class="hero"><div class="kicker">Counsellor review notes</div><h1>{e(name)}</h1>
    <div class="meta">{e(report.get('bureau'))} ticket {e(report.get('ticket_number'))} · Readiness {rules['total']}/100 ({rules['band']}) · Rubric {e(rules['rubric_version'])}, approved by: {e(approved)}</div></div>
    {warn}{notes}
    <h4 style="margin-top:12px">Automatic flags</h4><ul class="small">{flags}</ul>
    <h4 style="margin-top:12px">Sources given to the drafting step</h4><ul class="small">{srcs}</ul>
    </body></html>"""
    return HTML(string=html).write_pdf()
