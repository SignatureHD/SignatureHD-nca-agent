# Credit Report Agent: setup guide

This guide gets the app live on Railway and installed only in the debt counselling practices you choose.

## How it works

1. A counsellor uploads a client's bureau PDF to the contact, using the intake form's file field.
2. A workflow runs the **Analyse credit report** action.
3. The app reads the PDF with Claude, runs the legal checks, and drafts the client PDF and the internal review sheet. It then adds a note, a task and the tag `credit-report-review` to the contact.
4. The counsellor opens **Credit Report Agent** in the left menu, reads the warnings and review sheet, edits the wording if needed, and clicks **Approve and send**.
5. The client receives the PDF by email from the practice's own HighLevel account. Every step is logged in the audit table.

Nothing reaches a client without a counsellor's approval.

---

## Step 1: Deploy the engine (about 20 minutes)

1. Push this folder to a **private** GitHub repo.
2. **Supabase:** create a project in the EU (Frankfurt) region. Copy the connection string from Project Settings > Database > Connection string > URI, using the pooler on port 6543. Change the start to `postgresql+psycopg://`.
3. **Railway:** New Project > Deploy from GitHub repo > pick the repo. Railway builds from the `Dockerfile`.
4. In Railway > Variables, add everything from `.env.example`.
   - For `ACTION_KEY` and `SESSION_SECRET`, use two different long random strings (`openssl rand -hex 32`).
   - Leave the three `GHL_` values blank for now.
5. Railway > Settings > Networking > Generate Domain. Open `https://YOUR-DOMAIN/health` and check that it returns `{"ok":true,"mock":false}`. The tables are created on first start.

## Step 2: Create the Private Marketplace app

1. Go to marketplace.gohighlevel.com > sign in with your developer account > **My Apps** > **Create App**.
2. Enter these settings:
   - **App type: Private.** It isn't listed in the Marketplace, and only people with your install link can add it.
   - **Target user:** Sub-account
   - **Who can install:** Both Agency & Sub-account
   - **Listing type:** White-label, so your name shows, not HighLevel's
3. **Advanced Settings > Auth**:
   - **Redirect URL:** `https://YOUR-DOMAIN/oauth/callback`
   - **Scopes** (the minimum this app needs): `contacts.readonly`, `contacts.write`, `conversations.readonly`, `conversations.write`, `conversations/message.write`, `medias.readonly`, `medias.write`, `locations.readonly`
   - **Client keys:** generate them, then copy the Client ID and Client Secret into Railway as `GHL_CLIENT_ID` and `GHL_CLIENT_SECRET`
   - **Shared Secret:** click Generate and copy it into Railway as `GHL_SHARED_SECRET`
   - Set `GHL_REDIRECT_URI` in Railway to the same Redirect URL. Redeploy.
4. **Webhooks:** set the default webhook URL to `https://YOUR-DOMAIN/ghl/webhook` and subscribe to **UninstallApp**. When a practice removes the app, its tokens and client data are deleted. The app double-checks with HighLevel first, so a fake uninstall call can't wipe anyone's data.
5. **Custom Page** (Modules > Custom Pages):
   - **URL:** `https://YOUR-DOMAIN/app`
   - **Placement:** left navigation
   - **Name:** Credit Report Agent

   The page identifies the user through HighLevel's signed user context, not the URL, so one practice can't open another's reports.
6. **Workflow Action** (Modules > Workflow Actions > Create):
   - **Name:** Analyse credit report. **Key:** `analyse_credit_report`
   - **Execution:** API, POST `https://YOUR-DOMAIN/ghl/action/analyse`
   - **Header:** `X-Action-Key` = the same value as `ACTION_KEY` in Railway
   - **Field (optional):** Text, Reference `report_field_id`, label "Credit report field ID". Leave it blank and the app uses the latest PDF on the contact.

## Step 3: Install it only for chosen practices

Use the **install link** from your app in My Apps. Send it only to the practices you've signed up. Because the app is Private, nobody else can find it.

Know the limit:
- A Private app can be installed in **up to 5 agencies**. At 6 or more, new installs are blocked unless the app passes HighLevel's Security Review.
- After passing the review, the app stays Private and the cap is lifted.
- The cap counts **agencies**, not sub-accounts. A practice set up as a sub-account under your own SignatureHD agency doesn't use up the cap.

The route that scales: put each practice on a sub-account in your agency and install there. Only practices with their own HighLevel agency count towards the 5. Once you near 5 of those, request the Security Review.

## Step 4: The intake setup (build once, save as a snapshot)

In one sub-account, build:
1. **Custom field:** "Credit report (PDF)", type File Upload.
2. **Form "Credit report check"** with:
   - name, email and mobile
   - the file field
   - a required consent checkbox: "I consent to [Practice] obtaining and processing my credit report to assess my credit position, under the POPIA and section 70 of the National Credit Act."
3. **Workflow:**
   - **Trigger:** Form Submitted (Credit report check)
   - **Action:** Analyse credit report
4. **Pipeline stage** "Report in review" (optional). Move contacts there with a second workflow triggered by the tag `credit-report-review`.

Save it as a **snapshot**. For each new practice: load the snapshot, install the app, open Credit Report Agent > Settings, and fill in the practice name, NCR number, approving counsellor, logo URL and brand colour.

## Step 5: Before the first real client

1. **Rubric sign-off.** A senior debt counsellor reviews the readiness checklists (`app/pipeline/rules_*.py`) and their name goes into Settings > "Rubric signed off by". Until then, every review sheet carries a warning.
2. **Live test on your own sub-account.** Use the fictitious TransUnion reports and confirm these four points, which HighLevel's documentation doesn't fully specify:
   - The action request arrives with `extras.locationId` and `extras.contactId`. Check the Railway logs.
   - The PDF downloads from the file-upload field.
   - The client PDF uploads to Media and arrives as an email attachment.
   - The custom page shows "Signed in as [your name]".
3. **POPIA.**
   - Sign an operator agreement with each practice. The app processes credit reports on their behalf.
   - The source PDF is never stored. Only its fingerprint is kept.
   - Extracted data and PDFs are deleted `RETENTION_DAYS` after approval or rejection (default 30).

## Running the tests

```
pip install -r requirements.txt
MOCK=1 ACTION_KEY=test-key DATABASE_URL=sqlite:///./test.db python -m pytest -q tests
```

Mock mode needs no HighLevel account or Claude key. To see the page locally, run:

```
MOCK=1 ACTION_KEY=k uvicorn app.main:app
```

Then open `http://localhost:8000/app?mock_location=demo`.
