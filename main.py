from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from mcp.server.sse import SseServerTransport
from starlette.routing import Mount
from sql_server_tools import mcp as fastmcp_server
from api_key_auth import ensure_valid_api_key
import uvicorn
import logging
import os
import json
from typing import Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Log startup information
logger.info("Starting MCP SQL Server application")
logger.info(f"API_KEYS configured: {'Yes' if os.environ.get('API_KEYS') else 'No'}")
logger.info(f"SQL_SERVER_CONNECTION_STRING configured: {'Yes' if os.environ.get('SQL_SERVER_CONNECTION_STRING') else 'No'}")

app = FastAPI(docs_url=None, redoc_url=None, dependencies=[Depends(ensure_valid_api_key)])

# FastMCP SSE transport (original implementation)
fastmcp_sse = SseServerTransport("/messages/")
app.router.routes.append(Mount("/messages", app=fastmcp_sse.handle_post_message))

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "api_keys_configured": bool(os.environ.get("API_KEYS")),
        "sql_connection_configured": bool(os.environ.get("SQL_SERVER_CONNECTION_STRING")),
        "implementations": {
            "fastmcp_sse": "/sse",
            "http_mcp": "/mcp"
        }
    }

@app.get("/sse", tags=["FastMCP"])
async def handle_fastmcp_sse(request: Request):
    """FastMCP SSE endpoint for simple SQL operations"""
    async with fastmcp_sse.connect_sse(request.scope, request.receive, request._send) as (
        read_stream,
        write_stream,
    ):
        init_options = fastmcp_server._mcp_server.create_initialization_options()

        await fastmcp_server._mcp_server.run(
            read_stream,
            write_stream,
            init_options,
        )

# HTTP MCP endpoints for APIM integration
@app.post("/mcp", tags=["HTTP MCP"])
async def mcp_initialize(request: Request):
    """MCP initialization endpoint for APIM"""
    body = await request.json()
    
    return JSONResponse({
        "jsonrpc": "2.0",
        "id": body.get("id"),
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {}
            },
            "serverInfo": {
                "name": "sql-mcp-server",
                "version": "1.0.0"
            }
        }
    })

@app.post("/mcp/tools/list", tags=["HTTP MCP"])
async def mcp_list_tools():
    """List available MCP tools"""
    return JSONResponse({
        "jsonrpc": "2.0",
        "result": {
            "tools": [
                {
                    "name": "get_tables",
                    "description": "Get all database tables",
                    "inputSchema": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                },
                {
                    "name": "run_query",
                    "description": "Execute a SQL query",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "SQL query to execute"
                            }
                        },
                        "required": ["query"]
                    }
                }
            ]
        }
    })

@app.post("/mcp/tools/call", tags=["HTTP MCP"])
async def mcp_call_tool(request: Request):
    """Call an MCP tool"""
    try:
        body = await request.json()
        tool_name = body.get("name")
        arguments = body.get("arguments", {})
        
        if tool_name == "get_tables":
            from sql_server_tools import get_tables
            result = get_tables()  # Remove await - this is a sync function
            
        elif tool_name == "run_query":
            query = arguments.get("query")
            if not query:
                raise HTTPException(status_code=400, detail="Query parameter is required")
            
            from sql_server_tools import run_query
            result = run_query(query=query)  # Remove await - this is a sync function
            
        else:
            raise HTTPException(status_code=400, detail=f"Unknown tool: {tool_name}")
        
        return JSONResponse({
            "jsonrpc": "2.0",
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result, indent=2)
                    }
                ]
            }
        })
        
    except Exception as e:
        logger.error(f"Tool execution error: {str(e)}")
        return JSONResponse({
            "jsonrpc": "2.0",
            "error": {
                "code": -1,
                "message": str(e)
            }
        }, status_code=500)

@app.get("/mcp/resources", tags=["HTTP MCP"])
async def mcp_list_resources():
    """List available MCP resources"""
    return JSONResponse({
        "jsonrpc": "2.0",
        "result": {
            "resources": []
        }
    })


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)