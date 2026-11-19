"""Tenant, job and audit storage. Postgres in production (Supabase), SQLite for local tests."""
import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import (Column, DateTime, Integer, LargeBinary, MetaData, String, Table, Text,
                        create_engine, delete, insert, select, update)

from . import config

engine = create_engine(config.DATABASE_URL, pool_pre_ping=True, future=True)
md = MetaData()

installs = Table("installs", md,
    Column("location_id", String(64), primary_key=True),
    Column("company_id", String(64)),
    Column("access_token", Text), Column("refresh_token", Text),
    Column("expires_at", DateTime(timezone=True)),
    Column("installed_at", DateTime(timezone=True)), Column("status", String(16), default="active"))

settings = Table("settings", md,
    Column("location_id", String(64), primary_key=True),
    Column("practice_name", String(200)), Column("ncr_number", String(64)),
    Column("counsellor_name", String(200)), Column("logo_url", Text),
    Column("brand_colour", String(16)), Column("rubric_approved_by", String(200)),
    Column("send_channel", String(16), default="Email"),
    Column("booking_url", Text), Column("contact_phone", String(64)), Column("contact_email", String(200)))

NEW_SETTINGS_COLUMNS = {"booking_url": "TEXT", "contact_phone": "VARCHAR(64)", "contact_email": "VARCHAR(200)"}

jobs = Table("jobs", md,
    Column("id", String(36), primary_key=True),
    Column("location_id", String(64), index=True), Column("contact_id", String(64)),
    Column("contact_name", String(200)), Column("report_type", String(16)),
    Column("status", String(24)),   # queued, processing, review, approved, sent, rejected, failed
    Column("error", Text), Column("extracted", Text), Column("result", Text),
    Column("client_pdf", LargeBinary), Column("review_pdf", LargeBinary),
    Column("source_sha256", String(64)),
    Column("created_at", DateTime(timezone=True)), Column("updated_at", DateTime(timezone=True)),
    Column("approved_by", String(200)), Column("purge_after", DateTime(timezone=True)))

audit = Table("audit", md,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("location_id", String(64), index=True), Column("job_id", String(36)),
    Column("actor", String(200)), Column("action", String(64)), Column("detail", Text),
    Column("at", DateTime(timezone=True)))


def now():
    return datetime.now(timezone.utc)


def init():
    md.create_all(engine)
    # add settings columns introduced after the first deploy
    from sqlalchemy import inspect, text
    have = {c["name"] for c in inspect(engine).get_columns("settings", schema=settings.schema)}
    name = f"{settings.schema}.settings" if settings.schema else "settings"
    with engine.begin() as c:
        for col, typ in NEW_SETTINGS_COLUMNS.items():
            if col not in have:
                c.execute(text(f"ALTER TABLE {name} ADD COLUMN {col} {typ}"))


def log(location_id, job_id, actor, action, detail=""):
    with engine.begin() as c:
        c.execute(insert(audit).values(location_id=location_id, job_id=job_id, actor=actor,
                                       action=action, detail=detail, at=now()))


# ---- installs ----
def save_install(location_id, company_id, access_token, refresh_token, expires_in):
    row = dict(company_id=company_id, access_token=access_token, refresh_token=refresh_token,
               expires_at=now() + timedelta(seconds=int(expires_in) - 120), status="active")
    with engine.begin() as c:
        if c.execute(select(installs.c.location_id).where(installs.c.location_id == location_id)).first():
            c.execute(update(installs).where(installs.c.location_id == location_id).values(**row))
        else:
            c.execute(insert(installs).values(location_id=location_id, installed_at=now(), **row))
            c.execute(insert(settings).values(location_id=location_id, send_channel="Email"))


def get_install(location_id):
    with engine.begin() as c:
        r = c.execute(select(installs).where(installs.c.location_id == location_id)).mappings().first()
        return dict(r) if r else None


def uninstall(location_id):
    """App removed: delete tokens and all client data for this location."""
    with engine.begin() as c:
        c.execute(delete(jobs).where(jobs.c.location_id == location_id))
        c.execute(update(installs).where(installs.c.location_id == location_id)
                  .values(status="uninstalled", access_token=None, refresh_token=None))


# ---- settings ----
def get_settings(location_id):
    with engine.begin() as c:
        r = c.execute(select(settings).where(settings.c.location_id == location_id)).mappings().first()
        return dict(r) if r else {"location_id": location_id}


def save_settings(location_id, **vals):
    allowed = {k: v for k, v in vals.items() if k in settings.c and k != "location_id"}
    with engine.begin() as c:
        if c.execute(select(settings.c.location_id).where(settings.c.location_id == location_id)).first():
            c.execute(update(settings).where(settings.c.location_id == location_id).values(**allowed))
        else:
            c.execute(insert(settings).values(location_id=location_id, **allowed))


# ---- jobs ----
def new_job(location_id, contact_id):
    jid = str(uuid.uuid4())
    with engine.begin() as c:
        c.execute(insert(jobs).values(id=jid, location_id=location_id, contact_id=contact_id,
                                      status="queued", created_at=now(), updated_at=now()))
    return jid


def set_job(jid, **vals):
    vals["updated_at"] = now()
    for k in ("extracted", "result"):
        if k in vals and not isinstance(vals[k], (str, type(None))):
            vals[k] = json.dumps(vals[k], default=str)
    with engine.begin() as c:
        c.execute(update(jobs).where(jobs.c.id == jid).values(**vals))


def get_job(jid, location_id):
    """Always scoped to the caller's location: one practice can never read another's job."""
    with engine.begin() as c:
        r = c.execute(select(jobs).where(jobs.c.id == jid, jobs.c.location_id == location_id)).mappings().first()
        return dict(r) if r else None


def list_jobs(location_id, limit=100):
    cols = [jobs.c.id, jobs.c.contact_id, jobs.c.contact_name, jobs.c.report_type, jobs.c.status,
            jobs.c.error, jobs.c.created_at, jobs.c.updated_at, jobs.c.approved_by]
    with engine.begin() as c:
        rs = c.execute(select(*cols).where(jobs.c.location_id == location_id)
                       .order_by(jobs.c.created_at.desc()).limit(limit)).mappings().all()
        return [dict(r) for r in rs]


def purge_expired():
    with engine.begin() as c:
        n = c.execute(delete(jobs).where(jobs.c.purge_after != None, jobs.c.purge_after < now())).rowcount  # noqa: E711
    return n
