# /app/services/database.py
import time
import psycopg2
from psycopg2.pool import SimpleConnectionPool
from typing import List, Tuple, Any
from app.core.config import settings

# A custom exception to make error handling in the API layer more specific.
class DatabaseConnectionError(Exception):
    """Custom exception for when the database is unavailable after all retries."""
    pass

class DatabaseHandler:
    """
    Handles all database interactions.
    - Per Phase 3 guide, implements a connection pool for efficiency.
    - Implements retry logic with exponential backoff for resilience.
    """
    def __init__(self, connection_string: str):
        try:
            # Initialize a thread-safe connection pool
            self.pool = SimpleConnectionPool(minconn=1, maxconn=10, dsn=connection_string)
        except psycopg2.OperationalError as e:
            print(f"CRITICAL: Failed to connect to PostgreSQL: {e}")
            raise

    def execute_query_with_retry(self, query: str, params: tuple = None, max_retries: int = 3) -> List[Tuple[Any, ...]]:
        """
        Executes a query with automatic retry on transient connection failures.
        Implements exponential backoff as required by the Phase 3 guide.
        """
        attempt = 0
        wait_time = 1  # Start with a 1-second wait
        while attempt < max_retries:
            try:
                conn = self.pool.getconn()
                with conn.cursor() as cur:
                    print(f"--- EXECUTING DB QUERY ---")
                    cur.execute(query, params)
                    # Use fetchall() to get all results from the SELECT query
                    results = cur.fetchall()
                self.pool.putconn(conn)
                return results
            except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
                print(f"WARNING: Database connection error: {e}. Retrying in {wait_time}s... (Attempt {attempt + 1}/{max_retries})")
                attempt += 1
                if attempt >= max_retries:
                    # After all retries fail, raise our custom exception
                    # Per Phase 3 guide, this allows the API to return a 503 status
                    raise DatabaseConnectionError("Database is unavailable after multiple retries.") from e

                time.sleep(wait_time)
                wait_time *= 2  # Exponential backoff
            except Exception as e:
                 # For non-connection errors (e.g., SQL syntax), fail immediately
                print(f"ERROR: An unexpected database error occurred: {e}")
                # Ensure the connection is returned to the pool on unexpected errors
                if 'conn' in locals() and conn:
                    self.pool.putconn(conn)
                raise # Re-raise the original exception
        return [] # Should not be reached, but satisfies linters