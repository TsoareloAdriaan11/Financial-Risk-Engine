"""
glitch_detector.py
Payment Gateway Glitch Detection Engine.

Simulates and detects the FNB virtual card processing error that resulted
in duplicate consumer charges on Takealot.

Detection logic:
  → Same Account → Same Merchant
  → Same Amount (within R0.01 tolerance)
  → Second charge within 60-second window of the first
  → Account type is 'virtual' (FNB virtual card gateway)
"""

import logging
from db_connection import Neo4jConnection

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Cypher: Duplicate virtual card charge detection
# ─────────────────────────────────────────────────────────────────────────────

DUPLICATE_CHARGE_QUERY = """
MATCH (a:Account {account_type: 'virtual'})-[:SENT]->(t1:Transaction)-[:TO]->(m:Merchant),
      (a)-[:SENT]->(t2:Transaction)-[:TO]->(m)
WHERE t1.txn_id < t2.txn_id
  AND abs(t1.amount - t2.amount) < 0.01
  AND abs(t1.timestamp - t2.timestamp) <= $window_seconds
  AND t1.channel = 'virtual_card'
  AND t2.channel = 'virtual_card'
MATCH (a)<-[:OWNS]-(c:Customer)
RETURN
    c.customer_id          AS customer_id,
    c.full_name            AS customer_name,
    c.email                AS customer_email,
    a.account_id           AS account_id,
    a.bank                 AS bank,
    m.merchant_id          AS merchant_id,
    m.name                 AS merchant_name,
    t1.txn_id              AS original_txn_id,
    t1.timestamp           AS original_timestamp,
    t2.txn_id              AS duplicate_txn_id,
    t2.timestamp           AS duplicate_timestamp,
    t1.amount              AS charged_amount,
    (t1.amount + t2.amount) AS total_debited,
    abs(t1.timestamp - t2.timestamp) AS seconds_between_charges
ORDER BY total_debited DESC
"""

# ─────────────────────────────────────────────────────────────────────────────
# Cypher: Aggregate glitch impact summary
# ─────────────────────────────────────────────────────────────────────────────

GLITCH_SUMMARY_QUERY = """
MATCH (a:Account {account_type: 'virtual'})-[:SENT]->(t1:Transaction)-[:TO]->(m:Merchant),
      (a)-[:SENT]->(t2:Transaction)-[:TO]->(m)
WHERE t1.txn_id < t2.txn_id
  AND abs(t1.amount - t2.amount) < 0.01
  AND abs(t1.timestamp - t2.timestamp) <= $window_seconds
  AND t1.channel = 'virtual_card'
  AND t2.channel = 'virtual_card'
RETURN
    m.name                          AS merchant_name,
    count(*)                        AS duplicate_count,
    sum(t1.amount)                  AS total_overcharged_zar,
    min(t1.amount)                  AS min_charge,
    max(t1.amount)                  AS max_charge,
    avg(t1.amount)                  AS avg_charge
ORDER BY total_overcharged_zar DESC
"""


# ─────────────────────────────────────────────────────────────────────────────
# Detector class
# ─────────────────────────────────────────────────────────────────────────────

class GlitchDetector:

    # Default detection window: 60 seconds (matches FNB gateway retry timeout)
    DETECTION_WINDOW_SECONDS = 60

    def __init__(self, conn: Neo4jConnection,
                 window_seconds: int = DETECTION_WINDOW_SECONDS):
        self.conn           = conn
        self.window_seconds = window_seconds

    def detect_duplicate_charges(self) -> list[dict]:
        """
        Identify customers who were charged twice for the same transaction
        via the virtual card gateway within the detection window.
        """
        logger.info(
            "🔍 Scanning for duplicate virtual card charges (window: %ds)...",
            self.window_seconds,
        )
        results = self.conn.query(
            DUPLICATE_CHARGE_QUERY,
            {"window_seconds": self.window_seconds},
        )

        if not results:
            logger.info("✅ No duplicate charges detected.")
            return []

        findings = []
        for row in results:
            finding = {
                "type":                   "PAYMENT_GATEWAY_GLITCH",
                "severity":               _classify_severity(row.get("total_debited", 0)),
                "customer_id":            row["customer_id"],
                "customer_name":          row["customer_name"],
                "customer_email":         row.get("customer_email", ""),
                "account_id":             row["account_id"],
                "bank":                   row.get("bank", "Unknown"),
                "merchant_name":          row["merchant_name"],
                "original_txn_id":        row["original_txn_id"],
                "duplicate_txn_id":       row["duplicate_txn_id"],
                "charged_amount_zar":     round(row["charged_amount"], 2),
                "total_debited_zar":      round(row["total_debited"], 2),
                "overcharged_zar":        round(row["charged_amount"], 2),   # Duplicate portion
                "seconds_between_charges": row["seconds_between_charges"],
                "description": (
                    f"Duplicate virtual card charge detected. "
                    f"Customer {row['customer_name']} (Acc: {row['account_id']}) was charged "
                    f"R{round(row['charged_amount'], 2):,.2f} twice at {row['merchant_name']} "
                    f"within {row['seconds_between_charges']}s. "
                    f"Total debited: R{round(row['total_debited'], 2):,.2f}. "
                    f"Refund required: R{round(row['charged_amount'], 2):,.2f}."
                ),
            }
            findings.append(finding)
            logger.warning(
                "🚨 Duplicate Charge | %s | %s | R%.2f x2 | %ds gap",
                row["customer_id"], row["merchant_name"],
                row["charged_amount"], row["seconds_between_charges"],
            )

        logger.info("🏁 Glitch scan complete. %d duplicate(s) found.", len(findings))
        return findings

    def get_impact_summary(self) -> dict:
        """
        Returns aggregated financial impact of the glitch per merchant.
        """
        logger.info("📊 Generating glitch impact summary...")
        results = self.conn.query(
            GLITCH_SUMMARY_QUERY,
            {"window_seconds": self.window_seconds},
        )
        if not results:
            return {}

        summary = {}
        for row in results:
            summary[row["merchant_name"]] = {
                "duplicate_events":       row["duplicate_count"],
                "total_overcharged_zar":  round(row["total_overcharged_zar"], 2),
                "min_charge_zar":         round(row["min_charge"], 2),
                "max_charge_zar":         round(row["max_charge"], 2),
                "avg_charge_zar":         round(row["avg_charge"], 2),
            }
            logger.info(
                "  📌 %s → %d duplicates | R%.2f overcharged",
                row["merchant_name"], row["duplicate_count"],
                row["total_overcharged_zar"],
            )
        return summary

    def run_all(self) -> list[dict]:
        return self.detect_duplicate_charges()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _classify_severity(total_debited: float) -> str:
    """Severity based on total amount erroneously debited."""
    if total_debited >= 5_000:
        return "CRITICAL"
    if total_debited >= 1_000:
        return "HIGH"
    if total_debited >= 200:
        return "MEDIUM"
    return "LOW"
