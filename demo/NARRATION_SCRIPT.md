# AP Autopilot · demo narration script

Video: `demo/ap-autopilot-demo.mp4` · **4:50** · 1600×900 · silent (add your voice).

Read each line when the video reaches its timestamp. The lines are timed for a relaxed pace (~150 words/min), so you'll have a breath of slack in most scenes. Replace **[your name]** in the first line.

| Time | On screen | Say | Words · fits in |
|---|---|---|---|
| **0:01–0:15** | ‘How it works’ page: the 8-step pipeline | Hi, I'm [your name]. This is AP Autopilot, my solution to problem statement one: invoice processing, from PDF to decision. Every invoice goes through eight stages, from intake to a final decision. | 32 · 13s of 14s |
| **0:15–0:25** | Approve / Review / Reject cards, then the four edge-case cards | Gemini reads the document; fixed rules decide: approve, review, or reject. I designed four edge cases, and I'll run each one live. | 22 · 9s of 10s |
| **0:25–0:35** | Upload page and scenario library | Drop in any PDF, digital or scanned, or pick a prepared scenario: two happy paths, four edge cases, six exceptions. | 20 · 8s of 10s |
| **0:35–0:49** | Clean Apex invoice runs; pipeline fills in live | Let's start with a clean invoice from Apex Office Supplies. Watch the pipeline on the left: it checks the file, reads the text layer, and extracts every field. | 28 · 11s of 15s |
| **0:49–1:04** | Green ‘Approve’ banner, 29/29 checks, Data tab | Approved: all twenty-nine checks passed, and the next step is routed to the AP supervisor, with payment scheduled on Net 30. Every field shows a confidence score and the text it came from. | 33 · 13s of 15s |
| **1:04–1:17** | PO match tab: line matching | In the PO match tab, every invoice line maps to the purchase order. Quantity, price and tax are all within tolerance: a clean two-way match. | 25 · 10s of 12s |
| **1:17–1:29** | Northwind ‘invoice 2 of 3’ runs | Second happy path: Northwind bills one PO in three monthly instalments. The PO number is written oddly and the dates are day-first, but it still resolves. | 26 · 10s of 12s |
| **1:29–1:41** | PO consumption bar and prior invoice | It matches against what's left on the PO, not the full value. This is invoice two of three, so it's approved, and the PO is now sixty-seven percent used. | 29 · 12s of 12s |
| **1:41–2:04** | Edge case 1: scanned Cobalt invoice runs, then amber ‘Manual review’ | Edge case one: a scanned invoice with no PO number at all. There's no text layer, so it runs OCR, at ninety-three percent confidence, and then it has to work out which purchase order this belongs to. It goes to manual review. | 42 · 17s of 23s |
| **2:04–2:12** | Document tab: scan next to OCR text | Here's the original scan beside the text the system read. | 10 · 4s of 8s |
| **2:12–2:23** | PO candidates table | It scored Cobalt's open POs: a hundred percent match versus sixteen. Strong, but an inferred PO still needs the buyer's confirmation. | 21 · 8s of 11s |
| **2:23–2:46** | Edge case 2: Apex ‘payment reminder’ copy, red ‘Reject’ | Edge case two is about duplicates. Apex re-sent an invoice we already paid, as a payment reminder, with a new date and the number re-formatted with a leading zero. Normalised, it's the same invoice, so it's rejected before it can be paid twice. | 43 · 17s of 23s |
| **2:46–3:12** | Summit monthly invoice approved; Duplicates tab | But the opposite mistake is just as costly. Summit bills the same four thousand five hundred dollars every month, so a naive check would block it. The system sees a different service period, recognises recurring billing, and approves it. | 39 · 16s of 26s |
| **3:12–3:46** | Edge case 3: Northwind final instalment; PO match bar | Edge case three: Northwind's final instalment. The agreed rate is sixteen thousand a month, but this invoice says nineteen and a half thousand, with a surcharge bundled in. The bar shows earlier invoices in grey, this one in amber, and the overrun in red. That's a twenty-one point nine percent price variance, so it goes to the buyer, by name, for a PO amendment or a corrected invoice. | 68 · 27s of 33s |
| **3:46–4:15** | Edge case 4: impersonation; issues expand; vendor fields | Edge case four is the expensive one: vendor impersonation. The PO and the amounts are perfect. But it says Limited instead of Inc, the tax ID digits are swapped, the email domain is a look-alike, and it asks us to pay a new bank account. Two or more identity mismatches mean a fraud hold: don't pay, and call the vendor on the number we already have on file. | 68 · 27s of 29s |
| **4:15–4:33** | Review queue; note typed; Approve | Back to the scanned invoice in the review queue. The buyer has confirmed the PO, so I add a note and approve. My name, the decision and the reason all go into the audit trail. | 35 · 14s of 18s |
| **4:33–4:50** | Dashboard: KPIs, donut, ‘Rejected’ filter | Finally, the dashboard: every invoice, its decision and why, with the value cleared and the value blocked. Gemini reads, rules decide, and every outcome can be explained. Thanks for watching. | 30 · 12s of 18s |

## Plain script (for reading aloud)

**[0:01]** Hi, I'm [your name]. This is AP Autopilot, my solution to problem statement one: invoice processing, from PDF to decision. Every invoice goes through eight stages, from intake to a final decision.  

**[0:15]** Gemini reads the document; fixed rules decide: approve, review, or reject. I designed four edge cases, and I'll run each one live.  

**[0:25]** Drop in any PDF, digital or scanned, or pick a prepared scenario: two happy paths, four edge cases, six exceptions.  

**[0:35]** Let's start with a clean invoice from Apex Office Supplies. Watch the pipeline on the left: it checks the file, reads the text layer, and extracts every field.  

**[0:49]** Approved: all twenty-nine checks passed, and the next step is routed to the AP supervisor, with payment scheduled on Net 30. Every field shows a confidence score and the text it came from.  

**[1:04]** In the PO match tab, every invoice line maps to the purchase order. Quantity, price and tax are all within tolerance: a clean two-way match.  

**[1:17]** Second happy path: Northwind bills one PO in three monthly instalments. The PO number is written oddly and the dates are day-first, but it still resolves.  

**[1:29]** It matches against what's left on the PO, not the full value. This is invoice two of three, so it's approved, and the PO is now sixty-seven percent used.  

**[1:41]** Edge case one: a scanned invoice with no PO number at all. There's no text layer, so it runs OCR, at ninety-three percent confidence, and then it has to work out which purchase order this belongs to. It goes to manual review.  

**[2:04]** Here's the original scan beside the text the system read.  

**[2:12]** It scored Cobalt's open POs: a hundred percent match versus sixteen. Strong, but an inferred PO still needs the buyer's confirmation.  

**[2:23]** Edge case two is about duplicates. Apex re-sent an invoice we already paid, as a payment reminder, with a new date and the number re-formatted with a leading zero. Normalised, it's the same invoice, so it's rejected before it can be paid twice.  

**[2:46]** But the opposite mistake is just as costly. Summit bills the same four thousand five hundred dollars every month, so a naive check would block it. The system sees a different service period, recognises recurring billing, and approves it.  

**[3:12]** Edge case three: Northwind's final instalment. The agreed rate is sixteen thousand a month, but this invoice says nineteen and a half thousand, with a surcharge bundled in. The bar shows earlier invoices in grey, this one in amber, and the overrun in red. That's a twenty-one point nine percent price variance, so it goes to the buyer, by name, for a PO amendment or a corrected invoice.  

**[3:46]** Edge case four is the expensive one: vendor impersonation. The PO and the amounts are perfect. But it says Limited instead of Inc, the tax ID digits are swapped, the email domain is a look-alike, and it asks us to pay a new bank account. Two or more identity mismatches mean a fraud hold: don't pay, and call the vendor on the number we already have on file.  

**[4:15]** Back to the scanned invoice in the review queue. The buyer has confirmed the PO, so I add a note and approve. My name, the decision and the reason all go into the audit trail.  

**[4:33]** Finally, the dashboard: every invoice, its decision and why, with the value cleared and the value blocked. Gemini reads, rules decide, and every outcome can be explained. Thanks for watching.  
