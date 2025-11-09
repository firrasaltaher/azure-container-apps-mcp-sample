import pyodbc
import os
import logging
from typing import Any
from mcp.server.fastmcp import FastMCP

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastMCP server for SQL Server tools
mcp = FastMCP("sql_server")

# SQL Server connection string
SQL_SERVER_CONNECTION_STRING = os.environ.get("SQL_SERVER_CONNECTION_STRING", "")

# Validate connection string on startup
if not SQL_SERVER_CONNECTION_STRING:
    logger.warning("SQL_SERVER_CONNECTION_STRING environment variable is not set")
else:
    logger.info("SQL Server connection string configured")

@mcp.tool()
def get_tables() -> list[str]:
    """Retrieve a list of tables from the SQL Server database."""
    if not SQL_SERVER_CONNECTION_STRING:
        return ["Error: SQL_SERVER_CONNECTION_STRING not configured"]
    
    try:
        with pyodbc.connect(SQL_SERVER_CONNECTION_STRING) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE'")
            tables = [row[0] for row in cursor.fetchall()]
        logger.info(f"Retrieved {len(tables)} tables from database")
        return tables
    except Exception as e:
        logger.error(f"Error retrieving tables: {str(e)}")
        return [f"Error: {str(e)}"]

@mcp.tool()
def run_query(query: str) -> list[dict[str, Any]]:
    """Execute a SQL query and return the results.

    Args:
        query: The SQL query to execute.
    """
    if not SQL_SERVER_CONNECTION_STRING:
        return [{"error": "SQL_SERVER_CONNECTION_STRING not configured"}]
    
    try:
        with pyodbc.connect(SQL_SERVER_CONNECTION_STRING) as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            columns = [column[0] for column in cursor.description]
            results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        logger.info(f"Query executed successfully, returned {len(results)} rows")
        return results
    except Exception as e:
        logger.error(f"Error executing query: {str(e)}")
        return [{"error": str(e)}]

if __name__ == "__main__":
    # Initialize and run the server
    mcp.run(transport='stdio')