"""HighLevel API client, one instance per sub-account (location). Refreshes tokens automatically."""
import re
from datetime import timedelta

import httpx

from . import config, db


class GHLError(Exception):
    pass


def exchange_code(code):
    r = httpx.post(f"{config.GHL_API_BASE}/oauth/token", data={
        "client_id": config.GHL_CLIENT_ID, "client_secret": config.GHL_CLIENT_SECRET,
        "grant_type": "authorization_code", "code": code, "user_type": "Location",
        "redirect_uri": config.GHL_REDIRECT_URI}, timeout=30)
    if r.status_code >= 400:
        raise GHLError(f"Token exchange failed: {r.status_code} {r.text[:300]}")
    return r.json()


# ---- agency (bulk) installs ----
# Installing from Agency View for several sub-accounts returns a Company token with no locationId.
# We keep that token under a "company:<id>" key and use it to mint a Location token per sub-account.
def _company_key(company_id):
    return f"company:{company_id}"


def _company_token(company_id):
    inst = db.get_install(_company_key(company_id))
    if not inst or inst.get("status") != "active":
        raise GHLError("No agency token stored for this company")
    exp = inst["expires_at"]
    if exp is not None and exp.tzinfo is None:
        exp = exp.replace(tzinfo=db.now().tzinfo)
    if exp is None or exp <= db.now():
        r = httpx.post(f"{config.GHL_API_BASE}/oauth/token", data={
            "client_id": config.GHL_CLIENT_ID, "client_secret": config.GHL_CLIENT_SECRET,
            "grant_type": "refresh_token", "refresh_token": inst["refresh_token"],
            "user_type": "Company"}, timeout=30)
        if r.status_code >= 400:
            raise GHLError(f"Agency token refresh failed: {r.status_code}")
        t = r.json()
        db.save_install(_company_key(company_id), company_id, t["access_token"], t["refresh_token"],
                        t.get("expires_in", 86399))
        return t["access_token"]
    return inst["access_token"]


def save_company_token(t):
    db.save_install(_company_key(t["companyId"]), t["companyId"], t["access_token"], t["refresh_token"],
                    t.get("expires_in", 86399))


def installed_locations(company_id):
    app_id = config.GHL_CLIENT_ID.split("-")[0]
    r = httpx.get(f"{config.GHL_API_BASE}/oauth/installedLocations",
                  params={"companyId": company_id, "appId": app_id, "isInstalled": "true", "limit": 500},
                  headers={"Authorization": f"Bearer {_company_token(company_id)}",
                           "Version": config.GHL_API_VERSION, "Accept": "application/json"}, timeout=30)
    if r.status_code >= 400:
        raise GHLError(f"installedLocations failed: {r.status_code} {r.text[:300]}")
    return [l.get("_id") or l.get("id") for l in r.json().get("locations", []) if l.get("_id") or l.get("id")]


def install_location_from_company(company_id, location_id):
    r = httpx.post(f"{config.GHL_API_BASE}/oauth/locationToken",
                   data={"companyId": company_id, "locationId": location_id},
                   headers={"Authorization": f"Bearer {_company_token(company_id)}",
                            "Version": config.GHL_API_VERSION, "Accept": "application/json"}, timeout=30)
    if r.status_code >= 400:
        raise GHLError(f"locationToken failed for {location_id}: {r.status_code} {r.text[:300]}")
    t = r.json()
    db.save_install(location_id, company_id, t["access_token"], t["refresh_token"], t.get("expires_in", 86399))
    db.log(location_id, None, "system", "installed", "via agency install")
    return location_id


class GHL:
    def __init__(self, location_id):
        self.location_id = location_id
        self.inst = db.get_install(location_id)
        if not self.inst or self.inst.get("status") != "active":
            raise GHLError("App is not installed for this sub-account")

    # ---- auth ----
    def _token(self):
        exp = self.inst["expires_at"]
        if exp is not None and exp.tzinfo is None:
            exp = exp.replace(tzinfo=db.now().tzinfo)
        if exp is None or exp <= db.now():
            r = httpx.post(f"{config.GHL_API_BASE}/oauth/token", data={
                "client_id": config.GHL_CLIENT_ID, "client_secret": config.GHL_CLIENT_SECRET,
                "grant_type": "refresh_token", "refresh_token": self.inst["refresh_token"],
                "user_type": "Location"}, timeout=30)
            if r.status_code >= 400:
                raise GHLError(f"Token refresh failed: {r.status_code}")
            t = r.json()
            db.save_install(self.location_id, self.inst.get("company_id"), t["access_token"],
                            t["refresh_token"], t.get("expires_in", 86399))
            self.inst = db.get_install(self.location_id)
        return self.inst["access_token"]

    def _h(self):
        return {"Authorization": f"Bearer {self._token()}", "Version": config.GHL_API_VERSION,
                "Accept": "application/json"}

    def _req(self, method, path, **kw):
        r = httpx.request(method, f"{config.GHL_API_BASE}{path}", headers=self._h(), timeout=60, **kw)
        if r.status_code >= 400:
            raise GHLError(f"{method} {path} -> {r.status_code} {r.text[:300]}")
        return r.json() if r.content else {}

    # ---- contacts ----
    def get_contact(self, contact_id):
        return self._req("GET", f"/contacts/{contact_id}").get("contact", {})

    def add_note(self, contact_id, body):
        return self._req("POST", f"/contacts/{contact_id}/notes", json={"body": body})

    def add_task(self, contact_id, title, body, due_days=1):
        due = (db.now() + timedelta(days=due_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        return self._req("POST", f"/contacts/{contact_id}/tasks",
                         json={"title": title, "body": body, "dueDate": due, "completed": False})

    def add_tag(self, contact_id, tag):
        return self._req("POST", f"/contacts/{contact_id}/tags", json={"tags": [tag]})

    # ---- files ----
    def find_report_urls(self, contact, field_id=None):
        """File-upload custom fields store URLs in nested objects (sometimes JSON-encoded strings).
        Returns every http(s) URL found, PDF-looking ones first; download() checks the bytes."""
        import json as _json
        pdfish, other = [], []

        def walk(v):
            if isinstance(v, str):
                t = v.strip()
                if t[:1] in "[{":
                    try:
                        return walk(_json.loads(t))
                    except ValueError:
                        pass
                if re.match(r"^https?://", t):
                    (pdfish if ".pdf" in t.lower() or "file" in t.lower() or "document" in t.lower() else other).append(t)
            elif isinstance(v, dict):
                for x in v.values(): walk(x)
            elif isinstance(v, list):
                for x in v: walk(x)
        for f in contact.get("customFields", []) or contact.get("customField", []) or []:
            if field_id and f.get("id") != field_id:
                continue
            walk(f.get("value", f.get("field_value")))
        return list(dict.fromkeys(pdfish + other))

    @staticmethod
    def describe_fields(contact):
        """Redacted shape of the contact's custom fields, for diagnosing file-field formats."""
        def shape(v, d=0):
            if d > 4: return "..."
            if isinstance(v, dict): return {k: shape(x, d + 1) for k, x in list(v.items())[:8]}
            if isinstance(v, list): return [shape(x, d + 1) for x in v[:3]]
            if isinstance(v, str): return ("url:" + v.split("?")[0][:60]) if v.startswith("http") else f"str({len(v)})"
            return type(v).__name__
        return [{"id": f.get("id"), "value": shape(f.get("value", f.get("field_value")))}
                for f in (contact.get("customFields") or contact.get("customField") or [])]

    def download_first(self, urls):
        last = None
        for u in urls[:10]:
            try:
                return self.download(u)
            except GHLError as e:
                last = e
        raise last or GHLError("Could not download the credit report PDF from the contact record")

    def download(self, url):
        for headers in ({"Authorization": f"Bearer {self._token()}"}, {}):
            r = httpx.get(url, headers=headers, timeout=60, follow_redirects=True)
            if r.status_code < 400 and r.content[:4] == b"%PDF":
                return r.content
        raise GHLError("Could not download the credit report PDF from the contact record")

    def upload_media(self, filename, content):
        r = httpx.post(f"{config.GHL_API_BASE}/medias/upload-file", headers=self._h(),
                       files={"file": (filename, content, "application/pdf")},
                       data={"hosted": "false", "name": filename}, timeout=120)
        if r.status_code >= 400:
            raise GHLError(f"Media upload failed: {r.status_code} {r.text[:200]}")
        j = r.json()
        return j.get("url") or j.get("fileUrl")

    # ---- messaging ----
    def send_email(self, contact_id, subject, html, attachment_urls):
        return self._req("POST", "/conversations/messages", json={
            "type": "Email", "contactId": contact_id, "subject": subject, "html": html,
            "attachments": attachment_urls})


class FakeGHL:
    """Stand-in used when MOCK=1, so the service runs without a HighLevel account."""
    sent = []

    def __init__(self, location_id):
        self.location_id = location_id

    def get_contact(self, contact_id):
        return {"id": contact_id, "firstName": "Test", "lastName": f"Client {contact_id[-4:]}",
                "customFields": [{"id": "cr_file", "value": {"f1": {"url": "https://example.test/files/report.pdf"}}}]}

    def find_report_urls(self, contact, field_id=None):
        return GHL.find_report_urls(self, contact, field_id)

    def download_first(self, urls):
        return self.download(urls[0])

    def download(self, url):
        return b"%PDF-1.4 mock"

    def add_note(self, contact_id, body):
        FakeGHL.sent.append(("note", contact_id, body))

    def add_task(self, contact_id, title, body, due_days=1):
        FakeGHL.sent.append(("task", contact_id, title))

    def add_tag(self, contact_id, tag):
        FakeGHL.sent.append(("tag", contact_id, tag))

    def upload_media(self, filename, content):
        return f"https://example.test/media/{filename}"

    def send_email(self, contact_id, subject, html, attachment_urls):
        FakeGHL.sent.append(("email", contact_id, subject, attachment_urls))
        return {"messageId": "mock"}


def client_for(location_id):
    return FakeGHL(location_id) if config.MOCK else GHL(location_id)
