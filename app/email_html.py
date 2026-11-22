"""Branded HTML email that carries the approved Findings and Action Plan to the client."""
from html import escape as e


def plan_email(first_name, st):
    brand = st.get("brand_colour") or "#1f3a5f"
    practice = st.get("practice_name") or "your debt counsellor"
    logo = (f'<img src="{e(st["logo_url"])}" alt="{e(practice)}" height="32" '
            f'style="display:block;height:32px;width:auto;border:0;">') if st.get("logo_url") else \
        f'<div style="font-size:20px;font-weight:800;color:{e(brand)};">{e(practice)}</div>'
    url = st.get("booking_url") or ""
    contact = " &middot; ".join(e(x) for x in (st.get("contact_phone"), st.get("contact_email")) if x)
    if url:
        action = (f'<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>'
                  f'<td style="background:{e(brand)};border-radius:999px;"><a href="{e(url)}" '
                  f'style="display:inline-block;padding:16px 30px;font-size:16px;font-weight:700;color:#FFFFFF;'
                  f'text-decoration:none;border-radius:999px;">Book my free review</a></td></tr></table>')
    else:
        action = ('<p style="margin:0;"><strong>Reply to this email</strong> with two or three times that suit you, '
                  'and we will confirm your free review.</p>')
    hi = f"Hi {e(first_name)}," if first_name else "Hi,"
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#F7F5F0;">
<div style="display:none;max-height:0;overflow:hidden;">Your Findings and Action Plan is attached, with your next step.</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#F7F5F0;"><tr><td align="center" style="padding:28px 12px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:600px;background:#FFFFFF;border-radius:24px;overflow:hidden;font-family:Inter,Arial,Helvetica,sans-serif;">
<tr><td height="6" style="background:{e(brand)};font-size:0;line-height:0;">&nbsp;</td></tr>
<tr><td style="padding:30px 40px 0;">{logo}</td></tr>
<tr><td style="padding:28px 40px 0;"><h1 style="margin:0;font-size:28px;line-height:1.2;font-weight:800;color:#12263A;">Your plan is ready</h1></td></tr>
<tr><td style="padding:16px 40px 0;font-size:16px;line-height:1.6;color:#4A5B6B;">
<p style="margin:0 0 14px;">{hi}</p>
<p style="margin:0 0 14px;">Your Findings and Action Plan is attached. It explains what is on your credit report, what you can dispute for free, and the steps to take over the next 90 days.</p>
<p style="margin:0 0 14px;">Start with the steps for days 1 to 30. Please don't pay or sign anything about the accounts we have flagged until we have spoken.</p></td></tr>
<tr><td style="padding:8px 40px 0;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#F4FAF8;border:2px dashed #9FCFC4;border-radius:16px;"><tr><td style="padding:18px 20px;font-size:15px;line-height:1.55;color:#12263A;">
<p style="margin:0 0 6px;font-size:13px;font-weight:700;letter-spacing:.06em;text-transform:uppercase;color:{e(brand)};">Your next step</p>
<p style="margin:0 0 14px;">Book your free review. We go through your findings with you, check your budget and agree the next steps.</p>
{action}</td></tr></table></td></tr>
<tr><td style="padding:26px 40px 34px;font-size:16px;line-height:1.6;color:#4A5B6B;"><p style="margin:0;">Kind regards,<br>{e(practice)}</p>
{f'<p style="margin:8px 0 0;font-size:14px;color:#8A97A3;">{contact}</p>' if contact else ""}</td></tr>
</table>
<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:600px;"><tr><td align="center" style="padding:20px 24px 8px;font-family:Inter,Arial,sans-serif;font-size:13px;line-height:1.6;color:#8A97A3;">
This plan explains your credit information and suggests next steps. It is not legal advice and not a guarantee of credit.</td></tr></table>
</td></tr></table></body></html>"""
