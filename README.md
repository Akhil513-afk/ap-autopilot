# AP Autopilot: Invoice PDF → Decision

Zamp AI Solutions Analyst case study, **PS-1 (Finance / Accounts Payable)**.

**Live app:** https://ap-autopilot-6lpu.onrender.com. It's on Render's free plan, so the first visit after a quiet spell can take up to a minute to wake.

You give it a vendor invoice PDF. It reads the invoice (digital or scanned), extracts the data, validates it, checks the vendor against the vendor master, finds and matches the purchase order, checks for duplicates, and returns **Approve / Manual review / Reject**. Every decision comes with the reasons, the checks that passed and failed, and the next action, each assigned to a named owner. You can watch every stage run live, and every run is kept with a full audit trail.

---

## Run it

Requires Python 3.11+ and Tesseract (`brew install tesseract`).

```bash
./run.sh            # creates .venv, installs requirements, starts http://localhost:8000
```

Optional: turn on Gemini for document understanding. A free key from Google AI Studio (aistudio.google.com/apikey) works, and the system also runs without one.

Paste the key into the `.env` file in the project folder (copy `.env.example` if `.env` doesn't exist), then restart the app:

```
GEMINI_API_KEY=your-key-here
```

`.env` is ignored by git and Docker, so the key is never committed or baked into an image. An exported environment variable takes priority over `.env`. On a hosting platform, set `GEMINI_API_KEY` in the host's environment-variable settings instead.

| Env var | Default | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | unset | Turns on Gemini extraction (free tier works). Without it, or if the free quota runs out, the deterministic parser runs alone. `GOOGLE_API_KEY` is also accepted. |
| `GEMINI_MODEL` | `gemini-3.1-flash-lite` | Primary Gemini model. |
| `GEMINI_FALLBACK_MODELS` | `gemini-3.5-flash-lite,gemini-3.5-flash,gemini-3.8-flash` | Tried in order when the primary is overloaded (503), rate-limited (429) or retired (404). This is common on the free tier. |
| `GEMINI_TIMEOUT_S` / `GEMINI_TOTAL_BUDGET_S` | `15` / `30` | Per-model timeout and total time across the chain, after which the rule-based parser takes over. |
| `USE_LLM` | `1` | Set `0` to force the parser even when a key is set. |
| `STAGE_PACING` | `0.6` | Seconds to pause between stages so the live view is easy to follow. Set `0` for full speed. |
| `AS_OF_DATE` | today | Business date used for invoice-age checks. Pin it (e.g. `2026-11-18`) for a reproducible demo. |
| `WORKERS` | `3` | Invoices processed in parallel; the rest wait in a queue (shown as "Queued" in the UI). |
| `MAX_UPLOAD_MB` | `20` | Upload size limit, enforced while streaming the upload. |
| `ALLOW_RESET` | `1` | Set `0` in any shared environment to disable the demo reset endpoint and button. |
| `STORAGE_DIR` | `./storage` | Where the SQLite database and uploaded PDFs live. Mount a volume here in production. |
| `LOG_LEVEL` | `INFO` | Server log level. |

**Demo reset:** **Reset demo** in the sidebar footer (or `POST /api/reset`) deletes all runs and puts the invoice ledger back to its seeded ERP history. It asks for confirmation first.

### Deploy to Render (free)

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/Akhil513-afk/ap-autopilot)

`render.yaml` defines a free Docker web service. Render asks for `GEMINI_API_KEY` during setup; leave it blank to run on the rule-based engine.

On the free plan:
- The service sleeps after about 15 minutes idle, so the first visit takes 30–60 s.
- Runs are kept on temporary storage and reset whenever the service restarts. The sample scenarios and **Reset demo** make that harmless.

### Deploy (Docker)

```bash
docker build -t ap-autopilot .
docker run -p 8000:8000 -v ap-data:/data -e GEMINI_API_KEY=... -e ALLOW_RESET=1 ap-autopilot
```

The image includes Tesseract, runs as a non-root user, keeps data on the `/data` volume, and has a health check on `/api/health`. It works on any container host (Render, Railway, Fly.io, Cloud Run). Run a **single instance**: the job queue and the live stream are in-process, backed by SQLite.

### Tests

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

The suite runs all 12 scenario invoices through the real API and asserts each decision and the check that drove it. It also covers re-submission of the same file, review rules (a note is required, and an invoice can only be reviewed once), upload validation, security headers and path traversal.

### Production hardening in this version
- **Processing:** a bounded worker pool with a queue; runs interrupted by a restart are marked as errors on startup instead of hanging; SQLite in WAL mode.
- **API:** upload size enforced while streaming; strict run-ID and file-name sanitising; reviews validated (approve/reject need a note; an invoice can only be reviewed once); JSON export per run; OpenAPI docs at `/api/docs`.
- **Security headers:** Content-Security-Policy (no inline scripts), `X-Frame-Options`, `nosniff`, Referrer-Policy and Permissions-Policy, plus gzip.
- **UI:**
  - Accessible: keyboard tabs and rows, focus rings, ARIA live regions, a skip link, reduced-motion support.
  - Feedback: loading skeletons, empty and error states with retry, toasts, confirmation dialogs for destructive actions.
  - Uploads: several files at once with per-file progress and client-side checks.
  - Dashboard: sorting, filtering, pagination and CSV export.
  - Layout: print styles, and a responsive layout down to phone width with an icon sidebar.

---

## What's in the box

```
app/
  main.py                 FastAPI: upload, SSE live stream, history, review actions, reference data
  db.py                   SQLite: runs, per-run event log (audit trail), invoice ledger
  pipeline/
    reader.py             A. Intake (file validity) + reading (text layer or OCR)
    extract_rules.py      B. Deterministic, layout-agnostic parser (labels + qty×price=amount rows)
    extract_llm.py        B. Gemini reads the PDF → JSON schema with confidence + evidence
    extract.py            B. Orchestrates both engines and cross-checks them
    validate.py           C. Completeness, arithmetic, dates, tax-rate consistency
    vendor.py             D. Vendor identification + identity verification + impersonation rule
    po_match.py           E. PO lookup / inference, split-PO balance, line & bundle matching, tolerances
    duplicates.py         F. File hash → normalised invoice # → fuzzy same-amount-same-content
    decision.py           G. Outcome, reasons, owner-assigned next actions, approval routing
    runner.py             Runs the stages and writes every step to the event log
data/                     vendors.json, purchase_orders.json, policy.json, seed_ledger.json
samples/                  12 test invoices (scripts/generate_samples.py regenerates them)
static/                   UI (vanilla JS, no build step)
```

---

## Design choices

**1. Gemini reads the invoice; rules decide.** Reading messy documents is where a language model is strong: layouts vary, labels differ ("Bill Number", "Your Order Ref"), and references can be implied. The approve/reject decision moves money, so it has to be deterministic, repeatable and auditable. Gemini therefore only fills a strict JSON schema. Every business rule and the final decision live in plain Python, and anyone can trace them.

**2. Two independent extraction engines.** When Gemini is on, the rule-based parser re-reads the key fields (invoice #, date, PO, subtotal, tax, total, tax ID, bank account). If both engines agree, the field is marked *confirmed* (≥97% confidence). If they disagree, confidence drops below the review threshold and the reviewer sees both values. Without an API key, or when the free-tier quota is exhausted, the parser runs alone, so the demo can never fail because of the network or a rate limit.

*Data note:* Google may use content sent on the free tier to improve its products. That's fine for these fictional invoices; a production deployment would use a paid tier, which doesn't do this.

**3. The decision is a pure function of the checks.** Each check has a status (pass / warn / fail / info) and, if it fails, a severity:
- any **reject**-severity failure → **REJECT** (duplicate, fraud pattern, unknown or suspended vendor, not an invoice, unreadable)
- else any **review**-severity failure → **MANUAL REVIEW** (variances, missing fields, inferred PO, tax mismatch, …)
- else → **APPROVE**, routed to an approver by amount (≤ $10k AP Supervisor, ≤ $50k Finance Manager, above that Controller)

Warnings ("notes") never block an invoice. They are kept for the record, e.g. a $35 freight charge accepted within the allowance. Each failed check maps to a **next action** and an **owner** (Vendor, Buyer by name, Treasury, Tax team, Security, Procurement), so a review item tells the person exactly what to do.

**4. Split POs are matched against what is left on them.** The ledger of approved and paid invoices is the source of truth for how much of each PO has been consumed. An invoice is compared with the PO's *remaining* balance and remaining quantity, not its original value. That is how a legitimate "invoice 2 of 3" gets approved while an over-billing third instalment gets caught.

**5. Duplicate detection avoids false positives.** Recurring invoices (rent, retainers, monthly services) have the same amount every month by design. A near-duplicate (same vendor, same amount, same content) is only flagged when the service periods do *not* differ.

**6. Human in the loop, with accountability.** Reviewers can approve, reject or request info, and a written justification is required. Manual approvals post to the ledger and update PO balances, just like automatic ones. The system's original decision and the human's action are both kept on the run.

---

## Pipeline and checks

| Stage | Checks (ID) |
|---|---|
| A. Intake & read | `A-INTAKE` PDF signature, opens, not encrypted, page count · `A-READ` text layer or OCR (median denoise, binarise, Tesseract, confidence) · `A-DOCTYPE` invoice vs statement / credit note / quote / PO |
| B. Extract | vendor name, address, email, tax ID, bank account and bank, change-of-bank notice · invoice #, date, due date, PO ref, service period · currency, subtotal, tax, rate, total, tax-inclusive · line items with qty, price, amount and ancillary flag · per-field confidence + evidence text |
| C. Validate | `V-REQ` critical fields · `V-CONF` low-confidence fields · `V-DATE` future / stale · `V-DATEFMT` ambiguous DD/MM vs MM/DD · `V-LINEMATH` qty×price · `V-SUM` Σlines = subtotal (or total if tax-inclusive) · `V-TOTAL` subtotal+tax = total · `V-TAXRATE` stated rate vs amount |
| D. Vendor | `D-FOUND` in master (by tax ID, name/aliases, domain, bank) · `D-STATUS` approved · `D-NAME` legal entity · `D-TAXID` · `D-DOMAIN` · `D-BANK` · `D-BANKNOTICE` · `D-FRAUD` ≥2 hard identity mismatches = impersonation · `D-CUR` |
| E. PO match | `E-FIND`/`E-REF` exact → normalised ("PO 2026/0398") → partial ("Purchase Order 0431") → **inferred** from open POs (line similarity × amount fit) · `E-VENDOR` · `E-STATUS` · `E-CUR` · `E-LINES` incl. **bundled lines** = sum of several PO lines · `E-PRICE` ±2% · `E-QTY` ≤ remaining qty · `E-AMOUNT` ≤ remaining balance + min(2%, $100) · `E-ANC` freight/surcharges ≤ $100 · `E-TAX` rate vs PO · `E-SPLIT` cumulative billing |
| F. Duplicates | `F-FILE` SHA-256 · `F-INV` same vendor + normalised number (case, separators, leading zeros, "-R"/"COPY") · `F-FUZZY` same amount + ≥85% same content + within 60 days, excluding different service periods |
| G. Decide | outcome, headline, reasons, notes, next actions with owners, queue, priority, approver |

All thresholds are in `data/policy.json`.

---

## Scenario library (in the app under *Process invoice*)

| File | Expected | What it shows |
|---|---|---|
| `01_happy_apex_office_supplies` | ✅ Approve | Clean PDF, itemised, explicit PO, exact 2-way match |
| `02_happy_northwind_split_po_2of3` | ✅ Approve | Legitimate 2nd invoice on a 3-month PO; odd PO format "PO 2026/0398"; DD/MM dates |
| **Edge 1** `03_edge_scanned_no_po_cobalt` | ⚠️ Review | Scanned image (OCR); **no PO reference** → PO inferred from vendor's open POs (100% vs 16%); $35 freight accepted within allowance; buyer must confirm the inferred PO |
| **Edge 2a** `04_edge_disguised_duplicate_apex` | ⛔ Reject | Already-paid invoice re-sent as "PAYMENT REMINDER" with number `AOS-047950` vs ledger `AOS-47950` |
| **Edge 2b** `05_edge_recurring_not_duplicate_summit` | ✅ Approve | Same vendor, same $4,500 as last month: **not** a duplicate, because the service period differs |
| **Edge 3** `06_edge_split_po_overbilling_northwind` | ⚠️ Review | Final instalment billed at $19,500 vs $16,000/month agreed: +21.9% unit-price variance and over the remaining PO balance |
| **Edge 4** `07_edge_vendor_impersonation_bank_change` | ⛔ Reject | "Apex Office Supplies **Ltd.**", transposed tax ID, look-alike domain `.co`, new bank, "our banking details have changed" → fraud hold |
| `08_extra_bundled_no_invoice_number_brightpath` | ⚠️ Review | Bundled line = 2 PO lines (recognised); no invoice number; tax 9% vs PO 8.25% |
| `09_extra_suspended_vendor_vertex` | ⛔ Reject | Vendor on compliance hold |
| `10_extra_unknown_vendor_greenleaf` | ⛔ Reject | Vendor not onboarded; route to Procurement |
| `11_extra_not_an_invoice_statement` | ⛔ Reject | Statement of account, classified as not an invoice |
| `12_extra_corrupted_file` | ⛔ Reject | Truncated PDF, stopped at intake |

Running `01` a second time is rejected as an exact file duplicate.

### Why these four edge cases
1. **Scanned + no PO.** The common real-world case where "extract and compare" breaks: there is nothing to compare *to* until the system works out which PO the invoice belongs to. It also shows restraint: the inferred match is strong, but policy still requires a human to confirm it.
2. **Duplicate vs recurring (a pair).** Duplicate payments are the classic AP loss. Naive exact-number matching misses re-formatted resends, and naive amount matching blocks every monthly invoice. The pair proves the logic handles both.
3. **Split-PO over-billing.** Multiple invoices against one PO are legitimate. Detecting overruns requires tracking state across invoices, not just comparing one invoice with one PO.
4. **Vendor impersonation (BEC).** The most expensive AP failure. Amounts and PO match perfectly; only the identity attributes give it away. The system reasons over the *combination* of mismatches and says not to reply to the sender.

---

## Assumptions (made explicit, per the brief)
- The buyer is "Meridian Home Goods Inc."; all data in `data/` is fictional.
- 2-way match (invoice ↔ PO). Goods-receipt (3-way) data is not in scope; the remaining-quantity check stands in for it.
- Tolerance policy: PO amount within min(2%, $100); unit price within 2%; non-PO ancillary charges up to $100.
- An inferred PO (no reference on the invoice) always needs the buyer to confirm it, however strong the match ("no PO, no pay").
- Ambiguous numeric dates default to the vendor's convention (US vendors → MM/DD), and a note is raised.
- Only approved or paid invoices consume PO balance. Invoices still in review are checked for duplicates but don't reserve balance.

## What I'd build next
- Email intake (IMAP/Gmail webhook) and ERP posting (NetSuite/SAP connector) in place of the upload button and SQLite ledger.
- 3-way match with goods receipts; multi-currency with FX tolerance.
- Vendor master change-control workflow (bank changes verified by call-back before the master is updated).
- An evaluation set of real invoices to measure field-level extraction accuracy per engine, plus a feedback loop from reviewer corrections.
