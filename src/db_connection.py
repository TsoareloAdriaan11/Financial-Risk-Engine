"""
db_connection.py
Neo4j AuraDB connection handler for the Financial Risk Engine.
Credentials are injected via GitHub Actions Secrets as environment variables.
 
Includes automatic retry logic — AuraDB free tier drops idle connections
after ~5 minutes. The query() method transparently reconnects on failure.
"""
 
import os
import time
import logging
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError
 
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
 
MAX_RETRIES    = 3
RETRY_DELAY_S  = 5   # seconds between retries
 
 
class Neo4jConnection:
    """Manages a persistent connection to Neo4j AuraDB with auto-reconnect."""
 
    def __init__(self):
        self.uri      = os.environ["NEO4J_URI"]
        self.username = os.environ["NEO4J_USERNAME"]
        self.password = os.environ["NEO4J_PASSWORD"]
        self._driver  = None
 
    def connect(self):
        try:
            self._driver = GraphDatabase.driver(
                self.uri,
                auth=(self.username, self.password),
                max_connection_lifetime=3600,   # recycle connections after 1h
                keep_alive=True,
            )
            self._driver.verify_connectivity()
            logger.info("✅ Connected to Neo4j AuraDB at %s", self.uri)
        except AuthError:
            logger.error("❌ Neo4j authentication failed. Check NEO4J_USERNAME / NEO4J_PASSWORD secrets.")
            raise
        except ServiceUnavailable:
            logger.error("❌ Neo4j AuraDB is unreachable. Check NEO4J_URI secret.")
            raise
 
    def _reconnect(self):
        """Close the stale driver and open a fresh one."""
        logger.warning("🔄 Reconnecting to Neo4j AuraDB...")
        try:
            if self._driver:
                self._driver.close()
        except Exception:
            pass
        self._driver = None
        self.connect()
 
    def close(self):
        if self._driver:
            self._driver.close()
            logger.info("🔌 Neo4j connection closed.")
 
    def query(self, cypher: str, parameters: dict = None):
        """
        Execute a read/write Cypher query and return all records.
        Automatically retries on ServiceUnavailable (dropped idle connection).
        """
        if not self._driver:
            raise RuntimeError("Driver not initialised. Call connect() first.")
 
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                with self._driver.session() as session:
                    result = session.run(cypher, parameters or {})
                    return [record.data() for record in result]
            except ServiceUnavailable as e:
                logger.warning(
                    "⚠️  Neo4j connection lost (attempt %d/%d): %s",
                    attempt, MAX_RETRIES, e
                )
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY_S)
                    self._reconnect()
                else:
                    logger.error("❌ All %d reconnect attempts failed.", MAX_RETRIES)
                    raise
 
    def __enter__(self):
        self.connect()
        return self
 
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
