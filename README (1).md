# 🏦 Financial Risk Engine

### Autonomous Graph-Based Fraud Detection | Neo4j AuraDB · GitHub Actions · Python 3.11 · HTML
### University of the Witwatersrand · Data Science Project · South Africa

---

## 📋 Table of Contents

1. [Project Overview](#project-overview)
2. [Why This Was Built](#why-this-was-built)
3. [Why a Graph Database?](#why-a-graph-database)
4. [System Architecture](#system-architecture)
5. [Detection Capabilities](#detection-capabilities)
6. [Graph Visualizations](#graph-visualizations)
7. [Source Files — What Each Does](#source-files--what-each-does)
8. [Live Report Evidence](#live-report-evidence)
9. [Email Alert System](#email-alert-system)
10. [Technical Challenges & Solutions](#technical-challenges--solutions)
11. [Benefits & Commercial Relevance](#benefits--commercial-relevance)
12. [Setup & Deployment](#setup--deployment)
13. [Stack](#stack)

---

## Project Overview

The Financial Risk Engine is a **fully autonomous, cloud-hosted financial crime detection system** that runs continuously on GitHub Actions infrastructure without any human intervention. It streams synthetic South African payment transactions into a Neo4j graph database, applies two independent fraud detection algorithms in real time, generates detailed HTML investigation reports, and dispatches structured email alerts to analysts the moment anomalies are found.

In a single live scan, the engine has detected:

| Metric | Value |
|--------|-------|
| Total findings in one run | **898** |
| AML smurfing rings detected | **389** |
| Transaction structuring patterns | **50** |
| Duplicate payment charges detected | **459** |
| Total AML financial exposure | **R20,629,304** |
| Total refunds owed to customers | **R865,092** |

This is not a static analysis tool — it operates in real time, 24 hours a day, 7 days a week, with each scan taking under 2 minutes.

---

## Why This Was Built

### Academic Motivation
This project was built as a data science capstone to demonstrate that **graph databases offer a qualitatively different capability** for fraud detection compared to traditional relational databases. The central argument is that financial crime is fundamentally a *relationship problem* — it exists in the connections between entities, not in the entities themselves. A SQL table can tell you who sent money. A graph database tells you *who sent money to whom, via whom, in what pattern, and whether that pattern forms a closed loop*.

### Commercial Motivation
The project directly replicates two real-world South African financial risk scenarios:

**1. FICA Structuring** — South Africa's Financial Intelligence Centre Act (FICA) requires banks to report transactions above R5,000 to the Financial Intelligence Centre. Criminals deliberately break large transfers into many sub-R5,000 payments to avoid this threshold. This engine detects exactly that pattern.

**2. The FNB/Takealot Virtual Card Glitch** — A documented South African FinTech incident where FNB's virtual card payment gateway triggered duplicate charges on Takealot. Customers were billed twice for the same purchase within seconds. This engine detects every such pair and calculates the exact refund owed to each affected customer.

Building a detection engine around real incidents demonstrates practical commercial awareness of the South African financial risk landscape — FICA compliance, FSCA incident response frameworks, and the operational realities of payment gateway failure modes.

---

## Why a Graph Database?

Traditional SQL cannot efficiently answer the question *"does this account eventually send money back to itself through a network of other accounts?"* — because that requires a recursive self-join across an unknown number of hops. In SQL, this becomes an exponentially expensive query. In Neo4j, it is a single Cypher traversal.

| Capability | SQL | Neo4j (this engine) |
|------------|-----|---------------------|
| Detect A → B → C → A ring | ❌ Requires recursive CTE, extremely slow | ✅ Single Cypher path query |
| Multi-hop fraud traversal | ❌ Performance degrades with each hop | ✅ Constant time regardless of hops |
| Relationship-first data model | ❌ Relationships are secondary (foreign keys) | ✅ Relationships are first-class citizens |
| Visual graph exploration | ❌ Not native | ✅ Built-in Neo4j Browser |
| Live streaming inserts | ✅ Adequate | ✅ Excellent with constraint indexes |

The graph model used by this engine:

```
(Customer)-[:OWNS]→(Account)-[:SENT]→(Transaction)-[:TO]→(Account)
                                                           ↘
                                                       (Merchant)
```

Every node and relationship has properties. A `Transaction` node carries its `amount`, `timestamp`, `aml_ring` tag, `glitch_flag`, and `channel`. This means fraud detection queries can filter, traverse, and aggregate across the entire graph in a single Cypher statement.

---

## System Architecture

The engine runs as two independent GitHub Actions workflows that chain together automatically:

```
┌─────────────────────────────────────────────────────────────────┐
│  WORKFLOW 1 — transaction_stream.yml                            │
│  Runs every 6 hours (or manually with custom runtime)           │
│                                                                 │
│  transaction_stream.py                                          │
│  ├── Startup: deduplicates Takealot nodes                       │
│  ├── Seeds 5 guaranteed glitch bursts + 3 AML rings             │
│  ├── Every 15s → writes 2 normal ZA payment transactions        │
│  ├── 15% probability → injects AML smurfing ring burst          │
│  └── 15% probability → injects FNB/Takealot glitch duplicate    │
│                              │                                  │
│                    Neo4j AuraDB (live graph)                    │
│                              │                                  │
│  On completion → triggers Workflow 2 automatically              │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  WORKFLOW 2 — risk_engine.yml                                   │
│  Fires automatically when Workflow 1 completes                  │
│  Also available as manual trigger                               │
│                                                                 │
│  main.py (orchestrator)                                         │
│  ├── Step 1 → aml_detector.py (smurfing rings + structuring)    │
│  ├── Step 2 → glitch_detector.py (duplicate charges)            │
│  ├── Step 3 → report_generator.py (full HTML report)            │
│  └── Step 4 → alert_engine.py (email dispatch)                  │
│                                                                 │
│  Outputs:                                                       │
│  ├── HTML report uploaded as GitHub Actions artifact (90 days)  │
│  └── Email: summary + full report attached                      │
└─────────────────────────────────────────────────────────────────┘
```

**Key design decisions:**
- Workflow 2 is triggered by Workflow 1 completing (`workflow_run: completed`), never on an independent schedule — this prevents stale re-scans when no new data has been written
- The stream seeds guaranteed anomalies at startup so even a 120-second test run produces detectable findings
- The stream cleans up duplicate Takealot merchant nodes on startup to ensure glitch detection joins work correctly
- `db_connection.py` implements automatic retry with reconnection on `ServiceUnavailable` — AuraDB free tier drops idle connections after ~5 minutes, and the retry logic handles this transparently

---

## Detection Capabilities

### 1. AML — Smurfing Rings

A smurfing ring is a closed-loop money laundering pattern where a group of accounts repeatedly transfer funds between each other, with each individual transfer kept below R5,000 to avoid FICA reporting obligations.

**Pattern:**
```
Account A → Account B → Account C → Account D → Account A
   R4,200      R3,800      R4,750      R4,100
```

**How it works in this engine:**
- The stream injects rings of 3–5 participants with 2–4 hops, tagging each transaction with a unique `aml_ring` ID
- `aml_detector.py` scans for all transactions with a non-null `aml_ring` tag, groups them by ring ID, sums the total laundered amount, and identifies the participating accounts
- Each ring gets a severity rating: **CRITICAL** if total laundered > R50,000, **HIGH** otherwise
- The detector is hardened against false positives — rings with 0 detected accounts are skipped with a warning

**Sample findings from a live scan:**
- Ring `LIVE-RING-A3F2B1` | 5 accounts | **R70,904.72** | CRITICAL
- Ring `LIVE-RING-D8E4C7` | 5 accounts | **R69,504.78** | CRITICAL
- Ring `LIVE-RING-F1A9D3` | 4 accounts | **R66,933.89** | CRITICAL

---

### 2. AML — Transaction Structuring

Structuring is when a single account deliberately breaks one large transaction into many smaller ones, all kept below R5,000, to avoid triggering FICA reporting thresholds. Unlike smurfing rings, structuring involves only one account acting alone.

**How it works:**
- `aml_detector.py` scans for accounts with more than 5 transactions in the R1,000–R4,999 range within a rolling 24-hour window, excluding transactions already tagged as AML ring transfers
- Results are ordered by total structured amount descending, capped at the top 50 findings
- Severity: **MEDIUM** (structuring is serious but less acute than active ring laundering)

---

### 3. Payment Glitch — Duplicate Virtual Card Charges

This detection module mathematically replicates the FNB/Takealot virtual card incident. FNB's payment gateway had a retry mechanism that fired the same transaction twice when the initial request timed out before a confirmation was received.

**Pattern:**
```
Account (virtual) → R3,488.84 → Takealot  [timestamp: T+0s]
Account (virtual) → R3,488.84 → Takealot  [timestamp: T+32s]
                                  ↑ duplicate — customer charged twice
```

**How it works:**
- `glitch_detector.py` scans for pairs of virtual card transactions from the same account to the same merchant, with amounts differing by less than R0.01, within a 6-hour detection window
- The query uses `t1.timestamp < t2.timestamp` for ordering (not txn_id string ordering, which caused a silent detection failure due to `TXN-DUP` sorting alphabetically before `TXN-ORIG`)
- Merchants are matched by name (`m1.name = m2.name`) rather than node identity, which prevents missed detections when multiple Takealot nodes exist from old data
- Each finding includes: customer name, account ID, original transaction ID, duplicate transaction ID, refund amount, and time gap between charges

---

## Graph Visualizations

Each finding in the HTML report includes a **"View in Neo4j"** button that opens Neo4j Browser pre-loaded with the exact Cypher query for that specific finding. The visualizations below are live screenshots from Neo4j Browser using queries generated by this engine.

### Smurfing Ring — 5 Participants

The ring visualization shows only **Customer name nodes** connected by `TRANSFERRED_TO` relationships. Clicking any customer node reveals their account ID, bank, balance, and transaction history as properties in the side panel. The closed pentagon shape is the visual signature of a smurfing ring — money circulating through 5 people and returning to the origin.

> *Live visualization: 5-person ring — Kelly Robinson → Ricky Walker → Erin Clay → Keith Barnes → Robert Massey → Kelly Robinson*

---

### Transaction Structuring — Single Account, Many Transfers

The structuring visualization shows a single **Customer node** radiating outward to dozens of individual transaction amounts via their Account node. The star pattern — one source, many small outbound amounts — is the visual signature of structuring behaviour. The amounts shown (R337, R664, R696, R803 etc.) are all deliberately below the R5,000 FICA threshold.

> *Live visualization: Account ACC-1C14221E — 50+ sub-R5,000 transactions fanning outward*

---

### Payment Glitch — Duplicate Charge

The glitch visualization shows the exact path of a duplicate charge: **Customer → Account → two identical Transaction nodes → Takealot**. Both transaction nodes carry the same amount (R3,488.84) pointing to the same merchant, confirming the duplicate. The customer name node is the primary visual anchor — clicking it reveals the account number as an attribute.

> *Live visualization: Lisa Jones → ACC-9FF37799 → R3,488.84 (×2) → Takealot*

---

## Source Files — What Each Does

### `transaction_stream.py`
The live data generator. Runs continuously for up to 5 hours 50 minutes per GitHub Actions job, then exits cleanly — the next cron trigger picks up immediately. On every startup it deduplicates Takealot merchant nodes and seeds guaranteed anomalies. The main loop fires every 15 seconds:
- `emit_normal_transactions()` — creates 2 normal ZA payment transactions, reusing existing accounts 80% of the time to simulate a realistic payment network rather than an ever-growing pool of one-time customers
- `emit_aml_burst()` — creates a new ring of 3–5 customers with dedicated accounts, injects 2–4 hops of transactions all tagged with a unique `ring_id`
- `emit_glitch_burst()` — creates a new virtual card customer, looks up or creates the single canonical Takealot node, and writes both the original and duplicate transactions with timestamps 5–45 seconds apart

### `main.py`
The detection orchestrator. Runs in under 2 minutes, calls each detector in sequence, generates the report, and dispatches the email. Handles the slicing logic that ensures both smurfing rings and structuring patterns always appear in the email summary regardless of how many of each there are.

### `aml_detector.py`
Contains two Cypher queries:
- `RING_DETECTION_QUERY` — a two-step query that first aggregates all transactions by `aml_ring` tag, then separately identifies which accounts sent those transactions. This two-step approach was developed after the single-step query produced incorrect account counts due to Cypher's aggregation scope
- `STRUCTURING_QUERY` — filters accounts with >5 sub-threshold transactions in 24 hours, excluding ring-tagged transactions to prevent double-counting

### `glitch_detector.py`
Contains `DUPLICATE_CHARGE_QUERY` — matches pairs of virtual card transactions from the same account to merchants with the same name, where amounts differ by less than R0.01 and timestamps differ by less than 6 hours. The query uses `t1.timestamp < t2.timestamp` for deduplication (preventing the same pair from appearing as both (A,B) and (B,A)), with merchants matched by name rather than node identity.

### `report_generator.py`
Generates a complete self-contained HTML file with three separate sections: Smurfing Rings, Transaction Structuring, and Payment Glitch Findings. Each row has a **"View in Neo4j"** button that encodes the Cypher query into a Neo4j Browser deep link URL. The report includes stat cards, a Glitch Impact Summary table by merchant, and a Save as PDF button. Reports are retained for 90 days as GitHub Actions artifacts.

### `alert_engine.py`
Sends a single summary email per scan with the full HTML report attached. The summary shows top 25 smurfing rings and top 25 structuring patterns in separate tables, plus top 50 glitch findings. All stat card figures (AML exposure, glitch refunds) are calculated from the full findings list in `main.py` and passed in explicitly — this ensures the email totals match the HTML report exactly.

### `data_generator.py`
Faker-based synthetic data factory for South African customers, accounts, and merchants. Key design: named merchants like Takealot use `MERGE (m:Merchant {name: $name})` so they always resolve to a single node regardless of how many times the function is called — critical for glitch detection accuracy.

### `db_connection.py`
Neo4j AuraDB connection handler with automatic retry logic. On `ServiceUnavailable`, it closes the stale driver, reconnects, and retries the query up to 3 times with a 5-second pause. This handles AuraDB free tier's idle connection drop behaviour which occurs after ~5 minutes of inactivity.

---

## Live Report Evidence

The engine produces a full HTML anomaly report on every scan. A sample from a live run on **2026-04-18 at 12:48 SAST** (Run ID: 24605014443):

```
Total findings:      898
AML findings:        439  (389 smurfing rings + 50 structuring)
Glitch duplicates:   459
AML exposure:        R20,629,304
Refunds due:         R865,092
```

Each finding in the report includes:
- Customer full name
- Ring ID or account ID
- Ring size (number of participating accounts) or transaction count
- Total amount laundered or overcharged
- Severity badge (CRITICAL / HIGH / MEDIUM)
- Transaction IDs involved
- A direct "View in Neo4j" link that opens the graph for that specific finding

The report is uploaded as a GitHub Actions artifact with 90-day retention and is also attached directly to the summary email, so analysts can investigate without logging into GitHub.

---

## Email Alert System

After every scan, a single HTML email is dispatched containing:

- **Stat cards** — AML Rings count, Glitch Duplicates count, total AML Exposure (R), total Refunds Due (R)
- **Smurfing Rings table** — top 25 rings with customer name, ring size, amount, severity
- **Structuring Patterns table** — top 25 structuring findings with customer name, transaction count, amount
- **Payment Glitch table** — top 50 duplicate charges with customer name, merchant, refund amount
- **Download button** — links directly to the GitHub Actions artifact for the full report
- **Attached HTML file** — the complete report is attached so it opens with one double-click

The email subject line format is:
```
[RISK ENGINE] Scan Complete — 898 Finding(s) | 2026-04-18 12:48:00 SAST
```

---

## Technical Challenges & Solutions

### Challenge 1: Glitch detection silently returning zero findings
**Problem:** The duplicate charge detector used `t1.txn_id < t2.txn_id` for deduplication. Transaction IDs are named `TXN-ORIG-...` and `TXN-DUP-...`. Alphabetically, `D < O`, so the query always assigned `t1 = DUP` (the later transaction) and `t2 = ORIG` (the earlier one). The condition `t2.timestamp >= t1.timestamp` then read as `original_time >= duplicate_time` — always false. Every single glitch pair was silently rejected on every scan for the entire early development period.

**Solution:** Replaced `t1.txn_id < t2.txn_id` with `t1.timestamp < t2.timestamp` — ordering by actual time rather than string label, ensuring `t1` is always the chronologically first transaction.

---

### Challenge 2: Multiple Takealot merchant nodes
**Problem:** `_create_merchant()` originally generated a new random `merchant_id` on every call and used `MERGE (m:Merchant {merchant_id: $merchant_id})`. This created hundreds of separate Takealot nodes, each with a different ID. A glitch pair written to two different Takealot nodes could never be matched by a query joining on the same merchant node.

**Solution:** Named merchants now use `MERGE (m:Merchant {name: $name})` — a single node per merchant name, regardless of how many times the function is called. Additionally, a startup deduplication step re-points all orphan transactions to the canonical node.

---

### Challenge 3: AML rings reporting 0 accounts
**Problem:** The ring detection Cypher grouped by `ring_id` and collected `DISTINCT a.account_id` in a single aggregation pass. When the same account appeared in multiple rings (possible after many hours of streaming), Cypher's aggregation scope produced incorrect `size(accounts)` values of 0 for some rings.

**Solution:** Rewrote as a two-step query — first aggregate transactions by ring_id to get totals, then in a separate `MATCH` clause collect the accounts. Added a Python-side guard to skip any ring that returns 0 accounts.

---

### Challenge 4: AuraDB idle connection drops
**Problem:** AuraDB free tier silently drops connections after ~5 minutes of no activity. Mid-stream queries fail with `ServiceUnavailable: Unable to retrieve routing information`.

**Solution:** Added retry logic in `db_connection.py` — on `ServiceUnavailable`, close the stale driver, reconnect, and retry up to 3 times with a 5-second pause. Also added `max_connection_lifetime=3600` and `keep_alive=True` to the driver configuration.

---

### Challenge 5: Structuring findings buried in email
**Problem:** `run_all()` returns `rings + structs` in that order. With 700+ rings, `aml_findings[:50]` cut the list before a single structuring finding appeared. The email never showed structuring.

**Solution:** `main.py` now separates findings by type before slicing: `rings[:25] + structuring[:25]`, guaranteeing both types always appear in the email regardless of the rings count.

---

### Challenge 6: Email totals not matching report totals
**Problem:** The email stat cards summed amounts from the sliced lists (50 findings) while the report summed all findings. The AML Exposure and Glitch Refunds figures differed between email and report.

**Solution:** `main.py` computes full totals from the complete findings lists and passes them explicitly to `alert_engine.py`. The email builder uses these passed-in totals for stat cards rather than recalculating from the truncated lists.

---

## Benefits & Commercial Relevance

### For Financial Institutions
- Detects FICA-evasion structuring patterns that are invisible to per-transaction rules
- Catches payment gateway duplicate charge incidents within the same detection window as they occur, enabling same-day customer remediation
- Produces investigation-ready reports with direct graph visualization links — an analyst can go from email to investigating the live graph in two clicks

### For Data Science
- Demonstrates that graph traversal algorithms solve a class of fraud detection problems that SQL cannot approach efficiently
- Shows a complete end-to-end ML/analytics pipeline: data generation → storage → detection → reporting → alerting, all automated
- The graph model exposes relationship patterns that flat-table feature engineering cannot capture

### For South African FinTech Context
- Directly references FICA (Financial Intelligence Centre Act) threshold mechanics
- Replicates a documented FNB/Takealot incident with mathematically correct detection logic
- Demonstrates awareness of FSCA (Financial Sector Conduct Authority) incident response expectations

### Operational Benefits
- Zero manual intervention — the system runs, detects, reports, and alerts autonomously
- 90-day artifact retention means historical scan reports are always accessible
- Graph visualizations in Neo4j Browser make findings explainable to non-technical stakeholders
- Email attachment means the full report is accessible without GitHub credentials

---

## Setup & Deployment

### Prerequisites
- GitHub repository
- Neo4j AuraDB free account ([console.neo4j.io](https://console.neo4j.io))
- Gmail account with App Password enabled

### Required GitHub Actions Secrets (6)

| Secret | Description |
|--------|-------------|
| `NEO4J_URI` | AuraDB connection URI (`neo4j+s://xxxx.databases.neo4j.io`) |
| `NEO4J_USERNAME` | AuraDB username |
| `NEO4J_PASSWORD` | AuraDB password |
| `ALERT_EMAIL_SENDER` | Gmail address to send from |
| `ALERT_EMAIL_PASSWORD` | Gmail App Password (16-character) |
| `ALERT_EMAIL_RECIPIENT` | Analyst email to receive alerts |

### Running a Quick Test
1. Go to **Actions** → **Live Transaction Stream** → **Run workflow**
2. Set `test_runtime` to `120` (seconds)
3. The stream runs for 2 minutes, seeds guaranteed anomalies, then exits
4. **Financial Risk Engine** fires automatically when the stream completes
5. Check your email — the summary with attached report should arrive within 3 minutes

### Production Operation
Enable both workflows. The stream cron (`0 */6 * * *`) keeps the database populated continuously. The risk engine fires automatically after each stream run. The AuraDB instance stays active as long as workflows are enabled — disabling workflows for more than 72 hours will cause the free tier instance to pause and require manual resumption at [console.neo4j.io](https://console.neo4j.io).

---

## Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Graph Database | Neo4j AuraDB Free | Stores and traverses the transaction graph |
| Query Language | Cypher | Ring detection, structuring detection, duplicate matching |
| Data Generation | Python Faker (`en_ZA`) | Synthetic South African KYC profiles and transactions |
| Alerting | Python smtplib + Gmail SMTP | HTML email dispatch with file attachment |
| CI/CD | GitHub Actions | Workflow orchestration, scheduling, artifact storage |
| Language | Python 3.11 | All detection, generation, and reporting logic |
| Report Format | Self-contained HTML | Portable, no dependencies, opens in any browser |

---

## Repository Structure

```
src/
├── transaction_stream.py   # Live data generator — runs 24/7
├── main.py                 # Detection orchestrator
├── aml_detector.py         # Smurfing ring + structuring detection
├── glitch_detector.py      # Duplicate charge detection
├── report_generator.py     # HTML report builder
├── alert_engine.py         # Email dispatch
├── data_generator.py       # Synthetic data factory (customers, accounts, merchants)
└── db_connection.py        # Neo4j connection with auto-retry

.github/workflows/
├── transaction_stream.yml  # Workflow 1 — data streaming (6h cron)
└── risk_engine.yml         # Workflow 2 — detection scan (triggered by Workflow 1)
```

---

*University of the Witwatersrand · Data Science · 2026*

*This project demonstrates that graph database technology provides a qualitatively superior capability for financial fraud detection compared to relational databases — not incrementally better, but categorically different in the class of problems it can solve.*
