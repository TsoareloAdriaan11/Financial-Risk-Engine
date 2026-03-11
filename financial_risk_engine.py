from dotenv import load_dotenv
load_dotenv()
import smtplib
import os
from email.message import EmailMessage
from neo4j import GraphDatabase
from faker import Faker

fake = Faker()

class FinancialRiskEngine:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    # ... [Keep your clear_database, register_account, add_transfer, add_payment functions here] ...

    def run_anomaly_scans_and_alert(self, alert_email, email_password):
        print("\n🔍 Running Live Anomaly Detection Scans...")
        
        glitch_query = """
        MATCH (u:Account)-[t1:PAID]->(m:Merchant)
        MATCH (u)-[t2:PAID]->(m)
        WHERE t1.amount = t2.amount AND t1.tx_id <> t2.tx_id AND t1.card_type = "Virtual" AND abs(t1.timestamp - t2.timestamp) < 300000 
        RETURN u.first_name + ' ' + u.last_name AS Victim, m.name AS Merchant, t1.amount AS Amount
        """
        
        syndicate_query = """
        MATCH path = (a:Account)-[:TRANSFERRED_TO*3..10]->(a)
        RETURN [node in nodes(path) | node.first_name + " " + node.last_name] AS Ring
        """
        
        with self.driver.session() as session:
            glitches = session.run(glitch_query).data()
            syndicates = session.run(syndicate_query).data()

        # If it finds something, send the email!
        if glitches or syndicates:
            print("🚨 ANOMALIES DETECTED! Sending Alert...")
            self.send_email_alert(alert_email, email_password, glitches, syndicates)
        else:
            print("✅ Network is secure. No anomalies detected.")

    def send_email_alert(self, target_email, email_password, glitches, syndicates):
        msg = EmailMessage()
        msg['Subject'] = '🚨 CRITICAL: Financial Engine Anomaly Alert'
        msg['From'] = target_email
        msg['To'] = target_email

        body = "Automated Risk Engine Report:\n\n"
        
        if glitches:
            body += "⚠️ DUPLICATE PAYMENT GLITCH DETECTED:\n"
            for g in glitches:
                body += f"- {g['Victim']} charged twice at {g['Merchant']} for R{g['Amount']}\n"
                
        if syndicates:
            body += "\n⚠️ MONEY LAUNDERING SYNDICATE DETECTED:\n"
            for s in syndicates:
                body += f"- Closed-loop detected among: {', '.join(s['Ring'])}\n"

        msg.set_content(body)

        try:
            # 1. Force-clean the password of any hidden spaces or newlines
            clean_password = email_password.strip().replace(" ", "")
            
            # 2. Use Port 587 (TLS) - The modern standard for Gmail App Passwords
            with smtplib.SMTP('smtp.gmail.com', 587) as smtp:
                smtp.ehlo()
                smtp.starttls() # Upgrades the connection to a secure encrypted tunnel
                smtp.login(target_email, clean_password)
                smtp.send_message(msg)
            print("📧 Alert successfully sent to your phone/email!")
        except Exception as e:
            print(f"Failed to send email: {e}")

# --- RUNNING THE MASTER SIMULATION ---
if __name__ == "__main__":
    # We use os.getenv() to pull hidden variables
    URI = os.getenv("NEO4J_URI") 
    USER = "neo4j"
    DB_PASSWORD = os.getenv("NEO4J_PASSWORD") 
    
    # Your Email Alert Credentials
    ALERT_EMAIL = os.getenv("ALERT_EMAIL")
    EMAIL_APP_PASSWORD = os.getenv("EMAIL_PASSWORD")

    engine = FinancialRiskEngine(URI, USER, DB_PASSWORD)

    try:
        # 1. Inject the data (Simulating live network traffic)
        # engine.clear_database()
        # ... (Run your faker generation and injections here like before)
        
        # 2. Let the engine scan the database and alert you
        engine.run_anomaly_scans_and_alert(ALERT_EMAIL, EMAIL_APP_PASSWORD)

    finally:
        engine.close()