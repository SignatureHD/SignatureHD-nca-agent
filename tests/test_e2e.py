"""End-to-end test in mock mode: no HighLevel account or Claude key needed.
Run: MOCK=1 ACTION_KEY=test-key DATABASE_URL=sqlite:///./test.db python -m pytest -q tests
"""
import os

os.environ.setdefault("MOCK", "1")
os.environ.setdefault("ACTION_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")

from fastapi.testclient import TestClient  # noqa: E402

from app import db, ghl, security  # noqa: E402
from app.main import app  # noqa: E402

LOC_A, LOC_B = "locA_practice", "locB_other"


def session(c, loc):
    r = c.post("/api/session", json={"mock_location": loc})
    assert r.status_code == 200
    return {"Authorization": "Bearer " + r.json()["token"]}


def test_full_flow():
    with TestClient(app) as c:
        assert c.post("/ghl/action/analyse", json={}).status_code == 401
        payload = {"data": {"fixture": "consumer_tu"}, "extras": {"locationId": LOC_A, "contactId": "c_0001", "workflowId": "wf1"},
                   "meta": {"key": "analyse_credit_report", "version": "1.0"}}
        r = c.post("/ghl/action/analyse", json=payload, headers={"X-Action-Key": "test-key"})
        assert r.status_code == 200, r.text
        jid = r.json()["job_id"]

        ha = session(c, LOC_A)
        c.post("/api/settings", json={"practice_name": "Test Practice", "ncr_number": "NCRDC0001"}, headers=ha)
        jobs = c.get("/api/jobs", headers=ha).json()
        assert jobs[0]["id"] == jid and jobs[0]["status"] == "review", jobs
        j = c.get(f"/api/jobs/{jid}", headers=ha).json()
        assert j["rating"]["total"] == 23 and j["rating"]["band"] == "Not ready"
        assert any("not in force" in w for w in j["warnings"])

        pdf = c.get(f"/api/jobs/{jid}/pdf/client", headers=ha)
        assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"

        # another practice can never see this job
        hb = session(c, LOC_B)
        assert c.get(f"/api/jobs/{jid}", headers=hb).status_code == 404
        assert c.get(f"/api/jobs/{jid}/pdf/review", headers=hb).status_code == 404
        assert c.get("/api/jobs", headers=hb).json() == []

        # counsellor edits wording, PDFs rebuild, em dash is cleaned
        d = j["draft"]
        d["summary"] = "Edited — by the counsellor."
        r = c.post(f"/api/jobs/{jid}/draft", json={"draft": d}, headers=ha)
        assert r.status_code == 200
        assert c.get(f"/api/jobs/{jid}", headers=ha).json()["draft"]["summary"] == "Edited, by the counsellor."

        r = c.post(f"/api/jobs/{jid}/approve", headers=ha)
        assert r.status_code == 200
        assert any(x[0] == "email" and x[1] == "c_0001" for x in ghl.FakeGHL.sent)
        assert c.get(f"/api/jobs/{jid}", headers=ha).json()["status"] == "sent"
        assert c.post(f"/api/jobs/{jid}/approve", headers=ha).status_code == 409   # no double send

        # business report path
        payload["data"]["fixture"] = "business_tu"
        jid2 = c.post("/ghl/action/analyse", json=payload, headers={"X-Action-Key": "test-key"}).json()["job_id"]
        j2 = c.get(f"/api/jobs/{jid2}", headers=ha).json()
        assert j2["report_type"] == "business" and j2["rating"]["total"] == 74


def test_user_context_roundtrip():
    ctx = {"userId": "u1", "companyId": "co1", "activeLocation": LOC_A, "userName": "Jane Counsellor"}
    enc = security.encrypt_user_context(ctx, "shh-secret")
    assert security.decrypt_user_context(enc, "shh-secret")["activeLocation"] == LOC_A
    try:
        security.decrypt_user_context(enc, "wrong-secret")
        assert False, "should fail with the wrong secret"
    except Exception:
        pass


def test_sessions_cannot_be_forged():
    tok = security.make_session(LOC_A, "x")
    body, sig = tok.rsplit(".", 1)
    assert security.read_session(tok)["loc"] == LOC_A
    assert security.read_session(body + "." + "0" * len(sig)) is None
