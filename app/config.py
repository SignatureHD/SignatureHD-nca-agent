import os


def env(name, default=None, required=False):
    v = os.environ.get(name, default)
    if required and not v:
        raise RuntimeError(f"Missing environment variable {name}")
    return v


# HighLevel Marketplace app credentials (My Apps > your app > Advanced Settings > Auth)
GHL_CLIENT_ID = env("GHL_CLIENT_ID", "")
GHL_CLIENT_SECRET = env("GHL_CLIENT_SECRET", "")
GHL_SHARED_SECRET = env("GHL_SHARED_SECRET", "")          # for signed user context on the custom page
GHL_REDIRECT_URI = env("GHL_REDIRECT_URI", "")             # https://<your-domain>/oauth/callback
GHL_API_BASE = env("GHL_API_BASE", "https://services.leadconnectorhq.com")
GHL_API_VERSION = env("GHL_API_VERSION", "2021-07-28")

# Header value HighLevel sends with the workflow action (set in the action's Headers)
ACTION_KEY = env("ACTION_KEY", "")
# Signs the session cookie for the custom page
SESSION_SECRET = env("SESSION_SECRET", "dev-only-change-me")

DATABASE_URL = env("DATABASE_URL", "sqlite:///./nca_agent.db")
# Railway and Supabase give postgres:// or postgresql:// URLs; SQLAlchemy needs the psycopg driver named
for _p in ("postgres://", "postgresql://"):
    if DATABASE_URL.startswith(_p):
        DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len(_p):]
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = env("CLAUDE_MODEL", "claude-sonnet-5-5")

# MOCK=1 runs without Claude or HighLevel: uses fixture extractions and a fake GHL client
MOCK = env("MOCK", "0") == "1"
# Days to keep generated PDFs and extracted data after a job is closed (POPIA minimisation)
RETENTION_DAYS = int(env("RETENTION_DAYS", "30"))
PUBLIC_BASE_URL = env("PUBLIC_BASE_URL", "http://localhost:8000")
