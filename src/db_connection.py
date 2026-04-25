"""
db_connection.py
Neo4j AuraDB connection handler for the Financial Risk Engine.

Handles two failure modes:
  1. Mid-stream idle drop — AuraDB free tier drops connections after ~5min inactivity
  2. Instance paused — AuraDB free tier pauses after 72h of no workflow activity

Both are handled by connect_with_retry() which attempts up to 5 connections
with 15-second pauses, giving a resuming instance time to become reachable.
"""

import os
import time
import logging
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

CONNECT_RETRIES   = 5    # attempts on initial connect / reconnect
CONNECT_DELAY_S   = 15   # seconds between connect attempts
QUERY_RETRIES     = 3    # attempts on a mid-session query failure
QUERY_DELAY_S     = 5    # seconds between query retry attempts


class Neo4jConnection:
    """
    Manages a persistent connection to Neo4j AuraDB with full retry logic.

    connect_with_retry() is used for both the initial connection and any
    reconnection attempt — it retries multiple times with a delay so that
    a recently-resumed AuraDB instance has time to become fully reachable.
    """

    def __init__(self):
        self.uri      = os.environ["NEO4J_URI"]
        self.username = os.environ["NEO4J_USERNAME"]
        self.password = os.environ["NEO4J_PASSWORD"]
        self._driver  = None

    def _try_connect_once(self):
        """Create driver and verify connectivity. Raises on failure."""
        if self._driver:
            try:
                self._driver.close()
            except Exception:
                pass
            self._driver = None

        self._driver = GraphDatabase.driver(
            self.uri,
            auth=(self.username, self.password),
            max_connection_lifetime=3600,
            keep_alive=True,
        )
        self._driver.verify_connectivity()

    def connect_with_retry(self):
        """
        Connect to Neo4j, retrying up to CONNECT_RETRIES times.
        This handles both fresh connections and reconnections after a drop.
        AuraDB takes ~60-90s to resume from paused state, so we wait patiently.
        """
        for attempt in range(1, CONNECT_RETRIES + 1):
            try:
                self._try_connect_once()
                logger.info("✅ Connected to Neo4j AuraDB (attempt %d)", attempt)
                return
            except AuthError:
                logger.error("❌ Authentication failed — check NEO4J_USERNAME / NEO4J_PASSWORD secrets.")
                raise  # Auth errors are never transient — fail immediately
            except ServiceUnavailable as e:
                if attempt < CONNECT_RETRIES:
                    logger.warning(
                        "⚠️  AuraDB not reachable (attempt %d/%d): %s — retrying in %ds...",
                        attempt, CONNECT_RETRIES, e, CONNECT_DELAY_S
                    )
                    time.sleep(CONNECT_DELAY_S)
                else:
                    logger.error(
                        "❌ AuraDB unreachable after %d attempts. "
                        "If this is a fresh run, go to console.neo4j.io and check your instance is Running.",
                        CONNECT_RETRIES
                    )
                    raise

    def connect(self):
        """Public connect entry point — delegates to connect_with_retry."""
        self.connect_with_retry()

    def close(self):
        if self._driver:
            self._driver.close()
            logger.info("🔌 Neo4j connection closed.")

    def query(self, cypher: str, parameters: dict = None):
        """
        Execute a Cypher query and return all records.
        Retries on ServiceUnavailable (mid-session idle drop) by reconnecting.
        """
        if not self._driver:
            raise RuntimeError("Driver not initialised. Call connect() first.")

        for attempt in range(1, QUERY_RETRIES + 1):
            try:
                with self._driver.session() as session:
                    result = session.run(cypher, parameters or {})
                    return [record.data() for record in result]
            except ServiceUnavailable as e:
                logger.warning(
                    "⚠️  Query lost connection (attempt %d/%d): %s",
                    attempt, QUERY_RETRIES, e
                )
                if attempt < QUERY_RETRIES:
                    time.sleep(QUERY_DELAY_S)
                    logger.info("🔄 Reconnecting...")
                    self.connect_with_retry()
                else:
                    logger.error("❌ Query failed after %d reconnect attempts.", QUERY_RETRIES)
                    raise

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
