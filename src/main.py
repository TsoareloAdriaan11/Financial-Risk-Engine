"""
main.py
Financial Risk Engine — Detection & Alert Orchestrator
"""
from dotenv import load_dotenv
load_dotenv()
import os
import sys
import logging

from db_connection    import Neo4jConnection
from aml_detector     import AMLDetector
from glitch_detector  import GlitchDetector
from alert_engine     import AlertEngine
from report_generator import generate_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("risk_engine.main")


def main():
    logger.info("=" * 70)
    logger.info("FINANCIAL RISK ENGINE — Detection Scan Starting")
    logger.info("   (Live transaction stream is running separately)")
    logger.info("=" * 70)

    alert  = AlertEngine()
    run_id = os.environ.get("GITHUB_RUN_ID", "local")

    with Neo4jConnection() as conn:

        # ── 1. AML Detection ───────────────────────────────────────────────
        logger.info("\nStep 1/4: Running AML detection algorithms...")
        aml_detector = AMLDetector(conn)
        aml_findings = aml_detector.run_all()

        # ── 2. Glitch Detection ────────────────────────────────────────────
        logger.info("\nStep 2/4: Running payment glitch detection...")
        glitch_detector = GlitchDetector(conn, window_seconds=21600)
        glitch_findings = glitch_detector.run_all()
        impact_summary  = glitch_detector.get_impact_summary()

        # ── 3. Generate HTML Report ────────────────────────────────────────
        logger.info("\nStep 3/4: Generating full anomaly report...")
        report_path = ""
        total_findings = len(aml_findings) + len(glitch_findings)
        if total_findings > 0:
            report_result = generate_report(aml_findings, glitch_findings, impact_summary, run_id)
            
            # Extracts the file path whether the generator returns a tuple or a string
            report_path = report_result[0] if isinstance(report_result, tuple) else report_result
            
            logger.info("Report saved: %s", report_path)

        # ── 4. Alerting ────────────────────────────────────────────────────
        logger.info("\nStep 4/4: Dispatching alerts...")

        if total_findings == 0:
            logger.info("✅ No anomalies detected — sending clean-run notification.")
            alert.send_clean_run()
        else:
            logger.info("📦 Packaging findings into master digest report...")

            # Split AML findings into rings and structuring separately
            # so both types always appear in the email summary regardless
            # of how many rings there are
            rings      = [f for f in aml_findings if f.get("type") == "AML_SMURFING_RING"]
            structuring = [f for f in aml_findings if f.get("type") == "AML_STRUCTURING"]

            # Take top 25 of each type, then recombine for the email
            aml_for_email = rings[:25] + structuring[:25]

            # Compute full totals so email stat cards match the HTML report exactly
            total_rings_count   = sum(1 for f in aml_findings if f.get("type") == "AML_SMURFING_RING")
            total_structs_count = sum(1 for f in aml_findings if f.get("type") == "AML_STRUCTURING")
            full_glitch_refunds = sum(f.get("overcharged_zar", 0) for f in glitch_findings)
            full_aml_exposure   = sum(f.get("total_laundered_zar", f.get("total_structured_amount", 0)) for f in aml_findings)

            alert.send_run_summary(
                aml_for_email,
                glitch_findings[:50],
                impact_summary,
                total_aml=len(aml_findings),
                total_glitch=len(glitch_findings),
                run_id=run_id,
                report_path=report_path,
                total_rings=total_rings_count,
                total_structs=total_structs_count,
                total_glitch_refunds=full_glitch_refunds,
                total_aml_exposure=full_aml_exposure,
            )

        # ── Summary log ────────────────────────────────────────────────────
        logger.info("\n" + "=" * 70)
        logger.info("SCAN COMPLETE")
        logger.info("   AML findings       : %d", len(aml_findings))
        logger.info("   Glitch findings    : %d", len(glitch_findings))
        logger.info(
            "   Total AML exposure : R%.2f",
            sum(f.get("total_laundered_zar", f.get("total_structured_amount", 0)) for f in aml_findings),
        )
        logger.info(
            "   Total refunds due  : R%.2f",
            sum(f.get("overcharged_zar", 0) for f in glitch_findings),
        )
        if report_path:
            logger.info("   Report file        : %s", report_path)
        logger.info("=" * 70)

if __name__ == "__main__":
    main()
