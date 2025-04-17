import asyncio
import logging
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union

# Import the registration decorator and utility functions/settings
from . import register_tool
from .tool_utils import ask_confirmation_async # Potentially needed if marked high-risk
from agent_system.config import settings

# WARNING: Database tools can be HIGH RISK. Executing arbitrary SQL can lead to data loss,
# corruption, or exposure of sensitive information. Ensure the database path is intended
# and the SQL query is safe before execution.

def _execute_sqlite_query_sync(db_path_str: str, query: str, parameters: Optional[Union[List, Tuple]] = None) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
    """
    Synchronous helper to connect to SQLite DB, execute query, and fetch results.
    Returns (results, error_message). results is None if error occurs. error_message is None on success.
    """
    results: Optional[List[Dict[str, Any]]] = None
    error_msg: Optional[str] = None
    conn = None
    try:
        db_path = Path(db_path_str).resolve()
        if not db_path.is_file():
            return None, f"Database file not found: {db_path}"

        logging.info(f"Connecting to SQLite DB: {db_path}")
        conn = sqlite3.connect(str(db_path), timeout=10) # Add timeout

        # Enable row factory for dictionary results
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        logging.info(f"Executing SQL (Parameters: {parameters}):\n---\n{query}\n---")
        params_tuple = tuple(parameters) if parameters is not None else ()
        cursor.execute(query, params_tuple)

        # Fetch results for SELECT queries, or get row count for others
        # Heuristic: check if query likely modifies data (crude check)
        is_select_query = query.strip().upper().startswith("SELECT") or \
                          query.strip().upper().startswith("PRAGMA")

        if is_select_query:
             rows = cursor.fetchall()
             results = [dict(row) for row in rows] # Convert rows to list of dicts
             logging.info(f"Query returned {len(results)} rows.")
        else:
             conn.commit() # Commit changes for INSERT, UPDATE, DELETE, etc.
             results = [{"rows_affected": cursor.rowcount}] # Provide affected row count
             logging.info(f"Query executed successfully. Rows affected: {cursor.rowcount}")

        cursor.close()

    except sqlite3.Error as e:
        logging.error(f"SQLite error executing query on '{db_path_str}': {e}")
        error_msg = f"SQLite Error: {e}"
        if conn:
             try: conn.rollback() # Rollback on error
             except Exception as rb_err: logging.error(f"Error during rollback: {rb_err}")
    except Exception as e:
        logging.exception(f"Unexpected error executing SQLite query on '{db_path_str}': {e}")
        error_msg = f"Unexpected Error: {e}"
    finally:
        if conn:
            try: conn.close()
            except Exception as close_err: logging.error(f"Error closing DB connection: {close_err}")

    return results, error_msg


@register_tool
async def execute_sqlite_query(db_path: str, query: str, parameters: Optional[List[Any]] = None) -> str:
    """
    Executes a given SQL query against a specified SQLite database file.
    Returns results for SELECT queries or row count for other statements.
    WARNING: Executes arbitrary SQL. HIGH RISK. Requires confirmation by default.

    Args:
        db_path: Path to the SQLite database file.
        query: The SQL query string to execute. Use placeholders (?) for parameters.
        parameters: Optional list of parameters to safely bind to placeholders in the query.

    Returns:
        A formatted string containing the query results (list of dictionaries)
        or an error message.
    """
    # Confirmation can be handled by the agent based on HIGH_RISK_TOOLS
    # Add 'execute_sqlite_query' to HIGH_RISK_TOOLS in .env/.env.example if desired.
    # if not await ask_confirmation_async("execute_sqlite_query", {"db_path": db_path, "query": query, "parameters": parameters}):
    #     return "Operation cancelled by user."

    if not isinstance(db_path, str) or not db_path:
        return "Error: db_path must be a non-empty string."
    if not isinstance(query, str) or not query:
        return "Error: query must be a non-empty string."
    if parameters and not isinstance(parameters, list):
        return "Error: parameters must be a list if provided."

    try:
        # Run the synchronous SQLite operations in a separate thread
        results, error_msg = await asyncio.to_thread(
            _execute_sqlite_query_sync, db_path, query, parameters
        )

        if error_msg:
            return f"Error executing SQLite query on '{db_path}': {error_msg}"
        elif results is not None:
            # Format results nicely (e.g., JSON)
            try:
                 results_json = json.dumps(results, indent=2, default=str) # Use default=str for non-serializable types
                 return f"SQLite query executed successfully on '{db_path}'. Results:\n```json\n{results_json}\n```"
            except Exception as json_e:
                 logging.error(f"Failed to serialize SQLite results to JSON: {json_e}")
                 return f"SQLite query executed successfully on '{db_path}'. Results (raw):\n```\n{results}\n```"
        else:
             # Should not happen if error_msg is None, but as fallback
             return f"SQLite query executed on '{db_path}', but no results or error were returned."

    except Exception as e:
        logging.exception(f"Unexpected error in execute_sqlite_query tool wrapper: {e}")
        return f"An unexpected wrapper error occurred: {e}"
