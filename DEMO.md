# Demo script (5 minutes)

**Before:** run `./run.sh` and open http://localhost:8000. Click **Reset demo** (sidebar footer) and confirm. Keep `STAGE_PACING=0.6` so stages are easy to follow.

| Time | Do | Say |
|---|---|---|
| 0:00 | Open **How it works** | "Gemini reads the document; deterministic rules decide. Eight stages. Every check has a severity, and the decision is a pure function of the checks." |
| 0:30 | **Process invoice** → run `01_happy_apex` | Narrate the timeline as it fills: text layer → fields with confidence and evidence → vendor verified on tax ID, domain and bank → PO-2026-0412 matched line by line → no duplicate → **Approve**, routed to AP Supervisor with a payment date. |
| 1:15 | Run `02_happy_northwind` | "Same vendor billing one PO in three instalments. It's matched against what's *left* on the PO: invoice 2 of 3, 67% consumed after this one. Also note the PO was written 'PO 2026/0398' and still resolved." |
| 1:45 | **Edge 1** `03_edge_scanned` | "No text layer, so OCR at 93%. No PO number at all. It scored Cobalt's two open POs, 100% vs 16%, and found the match. It accepted $35 freight within the allowance. Policy still says an inferred PO needs the buyer to confirm it." Approve it with a note → show the reviewer audit entry. |
| 2:45 | **Edge 2a** `04_edge_disguised_duplicate` then **2b** `05_recurring` | "Resent as a 'payment reminder' with AOS-047950 instead of AOS-47950: normalised, it's the same, so rejected. Now Summit: same $4,500 as last month, but a different service period, so it's recognised as recurring and approved, not falsely blocked." |
| 3:30 | **Edge 3** `06_edge_split_po_overbilling` | Open the **PO match** tab: consumption bar, +21.9% unit price, over the remaining balance. Next action goes to buyer R. Alvarez for a PO amendment. |
| 4:00 | **Edge 4** `07_edge_vendor_impersonation` | "Amounts and PO are perfect. But: Ltd. vs Inc., transposed tax ID, `.co` domain, a new bank account, and a 'banking details have changed' notice. Two or more hard mismatches means impersonation: fraud hold, don't reply, call the number on file." |
| 4:40 | **Dashboard** | KPIs (touchless rate, value cleared vs blocked), filters, every run clickable with its full audit log. |

**Backup questions to be ready for:** why not let the LLM decide (auditability, determinism, money movement) · how tolerances work (`data/policy.json`) · what happens if Gemini is down or the free quota runs out (falls back to the parser, shown in the engine badge) · how to scale (email intake, ERP connector, reviewer corrections as eval data).
