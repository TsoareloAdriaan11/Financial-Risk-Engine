# 🏦 Financial Risk Engine
### Autonomous Graph-Based AML & Payment Glitch Detection
### Neo4j AuraDB · GitHub Actions · Python · South Africa

---

## What This Is

A fully autonomous cloud microservice that:
- **Streams** synthetic South African payment transactions into a graph database 24/7
- **Detects** two types of financial crime using Cypher graph traversal algorithms
- **Alerts** risk analysts via real-time HTML email the moment an anomaly is found

Traditional SQL databases cannot efficiently detect multi-hop fraud patterns.
This engine uses Neo4j's graph model to traverse complex relationship networks
in milliseconds — exposing patterns invisible to flat table queries.

---

## Two Risk Cases

### 1. AML — Smurfing Rings
Detects closed-loop circular transfers between accounts:
- 3 to 5 participants transferring money in a ring: A → B → C → A
- All transactions kept below R5,000 (under FICA reporting threshold)
- 2 to 5 hop traversal using Cypher path matching
- Severity classified by total laundered amount

### 2. FNB/Takealot Glitch — Duplicate Virtual Card Charges
Replicates a real South African FinTech incident:
- FNB virtual card gateway fired duplicate charges on Takealot
- Same account, same merchant, same amount within seconds
- Engine detects pairs within a 6-hour detection window
- Calculates exact refund amount per affected customer

---

## Architecture

Two independent GitHub Actions workflows run in parallel:

```
WORKFLOW 1: transaction_stream.yml (restarts every 6h)
  transaction_stream.py
  ├── Every 15s → writes 2 normal ZA payment transactions
  ├── 15% chance → injects AML smurfing ring burst
  └── 15% chance → injects FNB/Takealot glitch duplicate
                        ↓
                  Neo4j AuraDB (live graph, growing 24/7)
                        ↓
WORKFLOW 2: risk_engine.yml (scans every 6h)
  main.py
  ├── aml_detector.py    → Cypher ring traversal (2–5 hops)
  ├── glitch_detector.py → Duplicate charge detection
  └── alert_engine.py   → HTML email alerts → analyst inbox
```

---

## Graph Model

```
(Customer)-[:OWNS]→(Account)-[:SENT]→(Transaction)-[:TO]→(Account)
                                                           ↘
                                                       (Merchant)
```

| Node | Key Properties |
|------|---------------|
| Customer | customer_id, full_name, email, kyc_verified, risk_score |
| Account | account_id, account_type (cheque/savings/virtual), bank |
| Transaction | txn_id, amount, timestamp, txn_type, aml_ring, glitch_flag |
| Merchant | merchant_id, name, category (Takealot, Checkers, Engen...) |

---

## Stack

| Component | Technology |
|-----------|-----------|
| Graph Database | Neo4j AuraDB Free |
| Data Generation | Python Faker (en_ZA locale) |
| Detection | Cypher query language |
| Alerting | Python smtplib + Gmail SMTP |
| CI/CD | GitHub Actions (2 workflows) |
| Language | Python 3.11 |

---

## Commercial Context

The glitch detection module mathematically replicates a documented FNB/Takealot
incident where virtual card payments were duplicated due to a gateway retry error.
This demonstrates practical commercial awareness of real South African FinTech
risk events and the detection infrastructure needed to respond to them in real time.

---

## Setup

Requires 6 GitHub Actions Secrets:
- `NEO4J_URI` — AuraDB connection URI
- `NEO4J_USERNAME` — AuraDB username
- `NEO4J_PASSWORD` — AuraDB password
- `ALERT_EMAIL_SENDER` — Gmail sender address
- `ALERT_EMAIL_PASSWORD` — Gmail App Password
- `ALERT_EMAIL_RECIPIENT` — Analyst email

See the full setup guide for step-by-step instructions.

---

*University of the Witwatersrand · Data Science · Graph Database Project*

*Built for demonstrating commercial awareness of South African FinTech risk scenarios — FICA compliance, FSCA incident response, and real-time graph-based anomaly detection.*
