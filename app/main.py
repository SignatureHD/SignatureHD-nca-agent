"""Credit Report Agent: HighLevel Marketplace app backend."""
import hashlib
import hmac
import json
import logging
from datetime import timedelta
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from . import config, db, email_html, ghl, security
from .pipeline import render, validate
from .pipeline.run import analyse

log = logging.getLogger("nca-agent")
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(_app):
    db.init()
    db.purge_expired()
    yield

app = FastAPI(title="Credit Report Agent", docs_url=None, redoc_url=None, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=Path(__file__).resolve().parent / "static"), name="static")
APP_HTML = (Path(__file__).resolve().parent / "templates" / "app.html").read_text(encoding="utf-8")


@app.get("/health")
def health():
    return {"ok": True, "mock": config.MOCK}


# ---------------- install ----------------
@app.get("/oauth/callback", response_class=HTMLResponse)
def oauth_callback(code: str):
    t = ghl.exchange_code(code)
    loc = t.get("locationId")
    if loc:
        db.save_install(loc, t.get("companyId"), t["access_token"], t["refresh_token"], t.get("expires_in", 86399))
        db.log(loc, None, "system", "installed")
        return "<h3>Credit Report Agent is installed.</h3><p>Open it from the left menu of your sub-account to finish setup.</p>"
    company = t.get("companyId")
    if not company:
        raise HTTPException(400, "HighLevel did not return a sub-account or agency id")
    # Agency View install for one or more sub-accounts.
    ghl.save_company_token(t)
    done, failed = [], []
    for lid in ghl.installed_locations(company):
        try:
            done.append(ghl.install_location_from_company(company, lid))
        except Exception as e:  # noqa: BLE001
            log.warning("location token failed: %s", e)
            failed.append(lid)
    msg = f"<h3>Credit Report Agent is installed in {len(done)} sub-account(s).</h3>"
    if failed:
        msg += f"<p>{len(failed)} sub-account(s) could not be connected. Please reinstall from those sub-accounts.</p>"
    return msg + "<p>Open it from the left menu of each sub-account to finish setup.</p>"


@app.post("/ghl/webhook")
async def ghl_webhook(request: Request):
    """App lifecycle events. An UNINSTALL is only acted on once HighLevel confirms the token no longer works."""
    body = await request.json()
    if body.get("type") == "INSTALL" and body.get("locationId") and body.get("companyId"):
        loc = body["locationId"]
        inst = db.get_install(loc)
        if not inst or inst.get("status") != "active":
            try:
                ghl.install_location_from_company(body["companyId"], loc)
            except Exception as e:  # noqa: BLE001  (no agency token yet: the OAuth callback handles it)
                log.info("INSTALL webhook for %s not handled: %s", loc, e)
        return {"ok": True}
    if body.get("type") == "UNINSTALL" and body.get("locationId"):
        loc = body["locationId"]
        try:
            ghl.GHL(loc)._req("GET", f"/locations/{loc}")
            return {"ignored": "token still valid"}
        except Exception:
            db.uninstall(loc)
            db.log(loc, None, "system", "uninstalled", "tokens and client data deleted")
    return {"ok": True}


# ---------------- workflow action ----------------
def _check_action_key(x_action_key):
    if not config.ACTION_KEY or not hmac.compare_digest(x_action_key or "", config.ACTION_KEY):
        raise HTTPException(401, "Bad action key")


@app.post("/ghl/action/analyse")
async def action_analyse(request: Request, bg: BackgroundTasks, x_action_key: str = Header(None)):
    _check_action_key(x_action_key)
    body = await request.json()
    extras, data = body.get("extras") or {}, body.get("data") or {}
    loc = extras.get("locationId") or body.get("location_id") or body.get("locationId")
    contact = extras.get("contactId") or body.get("contact_id") or body.get("contactId")
    if not loc or not contact:
        raise HTTPException(400, "locationId and contactId are required")
    if not config.MOCK and not (db.get_install(loc) or {}).get("status") == "active":
        raise HTTPException(403, "App not installed for this sub-account")
    jid = db.new_job(loc, contact)
    db.log(loc, jid, "workflow", "queued", json.dumps({"workflowId": extras.get("workflowId")}))
    bg.add_task(process_job, jid, loc, contact, data.get("report_field_id"), data.get("fixture"))
    bg.add_task(db.purge_expired)
    return {"status": "queued", "job_id": jid}


def process_job(jid, loc, contact_id, field_id=None, fixture=None):
    db.set_job(jid, status="processing")
    try:
        g = ghl.client_for(loc)
        c = g.get_contact(contact_id)
        name = " ".join(x for x in (c.get("firstName"), c.get("lastName")) if x) or c.get("name") or contact_id
        urls = g.find_report_urls(c, field_id)
        if not urls:
            log.warning("no report URL; contact field shape: %s", json.dumps(ghl.GHL.describe_fields(c))[:2000])
            raise ValueError("No credit report PDF found on the contact. Upload it to the credit report file field.")
        pdf = g.download_first(urls)
        st = db.get_settings(loc)
        out = analyse(pdf, st, fixture=fixture)
        db.set_job(jid, status="review", contact_name=name, report_type=out["report_type"],
                   source_sha256=hashlib.sha256(pdf).hexdigest(), extracted=out["report"],
                   result={k: out[k] for k in ("rules", "draft", "warnings", "sources")},
                   client_pdf=out["client_pdf"], review_pdf=out["review_pdf"])
        g.add_note(contact_id, "Credit report analysed. A draft Findings and Action Plan is waiting for counsellor approval in Credit Report Agent.")
        g.add_task(contact_id, f"Review credit report findings: {name}", "Open Credit Report Agent from the left menu, check the review sheet and approve.")
        g.add_tag(contact_id, "credit-report-review")
        db.log(loc, jid, "system", "ready_for_review", f"{len(out['warnings'])} warnings")
    except Exception as ex:  # noqa: BLE001
        log.exception("job failed")
        db.set_job(jid, status="failed", error=str(ex)[:500])
        db.log(loc, jid, "system", "failed", str(ex)[:500])
        try:
            ghl.client_for(loc).add_note(contact_id, f"Credit Report Agent could not analyse the report: {str(ex)[:300]}")
        except Exception:  # noqa: BLE001
            pass


# ---------------- custom page ----------------
@app.get("/app", response_class=HTMLResponse)
def custom_page():
    return HTMLResponse(APP_HTML.replace("{{MOCK}}", "true" if config.MOCK else "false"),
                        headers={"Content-Security-Policy": "frame-ancestors *", "Cache-Control": "no-store"})


@app.post("/api/session")
async def session(request: Request):
    body = await request.json()
    if config.MOCK and body.get("mock_location"):
        loc, user = body["mock_location"], "Mock Counsellor"
    else:
        try:
            u = security.decrypt_user_context(body.get("encryptedData", ""))
        except Exception:
            raise HTTPException(401, "Could not verify HighLevel user")
        loc = u.get("activeLocation")
        user = u.get("userName") or u.get("email") or u.get("userId")
        if not loc:
            raise HTTPException(400, "Open this page from inside a sub-account")
        if (db.get_install(loc) or {}).get("status") != "active":
            raise HTTPException(403, "App not installed for this sub-account")
    return {"token": security.make_session(loc, user), "location_id": loc, "user": user}


def current(authorization: str = Header(None), t: str = None):
    tok = (authorization or "").removeprefix("Bearer ").strip() or t
    s = security.read_session(tok or "")
    if not s:
        raise HTTPException(401, "Session expired. Reload the page.")
    return s


@app.get("/api/jobs")
def jobs(s=Depends(current)):
    return db.list_jobs(s["loc"])


@app.get("/api/jobs/{jid}")
def job(jid: str, s=Depends(current)):
    j = db.get_job(jid, s["loc"])
    if not j:
        raise HTTPException(404)
    res = json.loads(j["result"] or "{}")
    review = None
    if res.get("rules") and j["extracted"]:
        report = json.loads(j["extracted"])
        review = {"meta": render.review_meta(report, res["rules"]),
                  "cards": render.review_cards(report, res["rules"], res.get("draft"))}
    return {"id": j["id"], "status": j["status"], "contact_name": j["contact_name"], "report_type": j["report_type"],
            "error": j["error"], "draft": res.get("draft"), "warnings": res.get("warnings"), "review": review,
            "rating": {k: res.get("rules", {}).get(k) for k in ("total", "band", "rubric_version")}}


@app.get("/api/jobs/{jid}/pdf/{kind}")
def job_pdf(jid: str, kind: str, s=Depends(current)):
    j = db.get_job(jid, s["loc"])
    if not j or kind not in ("client", "review") or not j[f"{kind}_pdf"]:
        raise HTTPException(404)
    db.log(s["loc"], jid, s["user"], f"viewed_{kind}_pdf")
    body = j[f"{kind}_pdf"]
    if kind == "review" and j["extracted"] and j["result"]:
        try:  # always show the review sheet in the current layout
            res = json.loads(j["result"])
            body = render.review_pdf(json.loads(j["extracted"]), res["rules"], res.get("draft") or {},
                                     res.get("warnings") or [], res.get("sources") or [], db.get_settings(s["loc"]))
        except Exception:  # noqa: BLE001
            log.exception("review re-render failed")
    return Response(body, media_type="application/pdf",
                    headers={"Content-Disposition": f"inline; filename={kind}.pdf", "Cache-Control": "no-store"})


@app.post("/api/jobs/{jid}/draft")
async def update_draft(jid: str, request: Request, s=Depends(current)):
    """Counsellor edits: re-validate and re-render both PDFs."""
    j = db.get_job(jid, s["loc"])
    if not j or j["status"] != "review":
        raise HTTPException(409, "Only drafts awaiting review can be edited")
    res = json.loads(j["result"])
    report = json.loads(j["extracted"])
    d, warnings = validate.validate((await request.json())["draft"], report, res["sources"])
    st = db.get_settings(s["loc"])
    res.update(draft=d, warnings=warnings)
    db.set_job(jid, result=res, client_pdf=render.client_pdf(report, res["rules"], d, st),
               review_pdf=render.review_pdf(report, res["rules"], d, warnings, res["sources"], st))
    db.log(s["loc"], jid, s["user"], "edited_draft")
    return {"ok": True, "warnings": warnings}


@app.post("/api/jobs/{jid}/approve")
async def approve(jid: str, s=Depends(current)):
    j = db.get_job(jid, s["loc"])
    if not j or j["status"] != "review":
        raise HTTPException(409, "Job is not awaiting review")
    st = db.get_settings(s["loc"])
    g = ghl.client_for(s["loc"])
    fname = f"Findings-and-Action-Plan-{(j['contact_name'] or 'client').replace(' ', '-')}.pdf"
    url = g.upload_media(fname, j["client_pdf"])
    first = (j["contact_name"] or "").split(" ")[0]
    g.send_email(j["contact_id"], "Your Findings and Action Plan is ready", email_html.plan_email(first, st), [url])
    g.add_note(j["contact_id"], f"Findings and Action Plan approved by {s['user']} and sent to the client.")
    g.add_tag(j["contact_id"], "credit-report-sent")
    db.set_job(jid, status="sent", approved_by=s["user"], purge_after=db.now() + timedelta(days=config.RETENTION_DAYS))
    db.log(s["loc"], jid, s["user"], "approved_and_sent")
    return {"ok": True}


@app.post("/api/jobs/{jid}/reject")
async def reject(jid: str, request: Request, s=Depends(current)):
    j = db.get_job(jid, s["loc"])
    if not j or j["status"] not in ("review", "failed"):
        raise HTTPException(409)
    reason = (await request.json()).get("reason", "")
    db.set_job(jid, status="rejected", purge_after=db.now() + timedelta(days=config.RETENTION_DAYS))
    db.log(s["loc"], jid, s["user"], "rejected", reason[:500])
    return {"ok": True}


@app.get("/api/settings")
def get_settings(s=Depends(current)):
    return db.get_settings(s["loc"])


@app.post("/api/settings")
async def save_settings(request: Request, s=Depends(current)):
    vals = await request.json()
    db.save_settings(s["loc"], **{k: (v or "").strip()[:300] for k, v in vals.items() if isinstance(v, str)})
    db.log(s["loc"], None, s["user"], "settings_saved", ", ".join(vals))
    return db.get_settings(s["loc"])
