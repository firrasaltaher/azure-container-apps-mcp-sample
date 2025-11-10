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
from datetime import datetime, date
import decimal

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Custom JSON encoder to handle datetime and decimal objects
class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        elif isinstance(obj, decimal.Decimal):
            return float(obj)
        elif hasattr(obj, '__dict__'):
            return obj.__dict__
        return super().default(obj)

def safe_json_dumps(obj, **kwargs):
    """Safely serialize objects to JSON with custom encoder"""
    return json.dumps(obj, cls=CustomJSONEncoder, **kwargs)

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
@app.get("/mcp", tags=["HTTP MCP"])
async def mcp_handler(request: Request):
    """Main MCP endpoint handler"""
    try:
        if request.method == "GET":
            # Handle GET requests (like for tools/list)
            return JSONResponse({
                "jsonrpc": "2.0", 
                "id": 1,
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
        else:
            # Handle POST requests
            body = await request.json()
            logger.info(f"Received request body: {safe_json_dumps(body, indent=2)}")
            
            method = body.get("method")
            request_id = body.get("id", 1)
            
            if method == "initialize":
                response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
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
                }
                logger.info(f"Returning initialize response: {safe_json_dumps(response, indent=2)}")
                return JSONResponse(response)
                
            elif method == "tools/list":
                return await mcp_list_tools_handler(body)
                
            elif method == "tools/call":
                return await mcp_call_tool_handler(body)
                
            else:
                error_response = {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}"
                    }
                }
                logger.error(f"Unknown method '{method}', returning error: {safe_json_dumps(error_response, indent=2)}")
                return JSONResponse(error_response)
                
    except Exception as e:
        logger.error(f"MCP handler error: {str(e)}")
        error_response = {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {
                "code": -32603,
                "message": str(e)
            }
        }
        return JSONResponse(error_response, status_code=500)

async def mcp_list_tools_handler(body: dict):
    """Handle tools/list requests"""
    request_id = body.get("id", 1)
    
    tools_list = [
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
    
    response = {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "tools": tools_list
        }
    }
    
    logger.info(f"Returning tools list response: {safe_json_dumps(response, indent=2)}")
    return JSONResponse(response)

async def mcp_call_tool_handler(body: dict):
    """Handle tools/call requests"""
    try:
        params = body.get("params", {})
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        request_id = body.get("id", 1)
        
        logger.info(f"Calling tool: {tool_name} with arguments: {arguments}")
        
        if tool_name == "get_tables":
            from sql_server_tools import get_tables
            result = get_tables()
            
        elif tool_name == "run_query":
            query = arguments.get("query")
            if not query:
                return JSONResponse({
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32602,
                        "message": "Query parameter is required"
                    }
                })
            
            from sql_server_tools import run_query
            result = run_query(query=query)
            
        else:
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32601,
                    "message": f"Unknown tool: {tool_name}"
                }
            })
        
        # Use safe JSON serialization for the result
        try:
            result_text = safe_json_dumps(result, indent=2) if isinstance(result, (dict, list)) else str(result)
        except Exception as json_error:
            logger.error(f"JSON serialization error: {str(json_error)}")
            result_text = str(result)  # Fallback to string representation
        
        response = {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": result_text
                    }
                ]
            }
        }
        
        logger.info(f"Tool call successful, returning result")
        return JSONResponse(response)
        
    except Exception as e:
        logger.error(f"Tool execution error: {str(e)}")
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": body.get("id", 1),
            "error": {
                "code": -32603,
                "message": str(e)
            }
        }, status_code=500)

@app.post("/mcp/initialize", tags=["HTTP MCP"])
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
@app.get("/mcp/tools/list", tags=["HTTP MCP"])
async def mcp_list_tools(request: Request = None):
    """List available MCP tools"""
    # Handle both POST and GET requests
    request_body = {}
    if request and request.method == "POST":
        try:
            request_body = await request.json()
        except:
            request_body = {}
    
    tools_list = [
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
    
    response = {
        "jsonrpc": "2.0",
        "id": request_body.get("id", 1),
        "result": {
            "tools": tools_list
        }
    }
    
    logger.info(f"Returning tools list response: {json.dumps(response, indent=2)}")
    return JSONResponse(response)

@app.post("/mcp/tools/call", tags=["HTTP MCP"])
async def mcp_call_tool(request: Request):
    """Call an MCP tool"""
    try:
        body = await request.json()
        tool_name = body.get("params", {}).get("name") or body.get("name")
        arguments = body.get("params", {}).get("arguments") or body.get("arguments", {})
        request_id = body.get("id", 1)
        
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
            "id": request_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result, indent=2) if isinstance(result, (dict, list)) else str(result)
                    }
                ]
            }
        })
        
    except Exception as e:
        logger.error(f"Tool execution error: {str(e)}")
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": body.get("id", 1) if 'body' in locals() else 1,
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

@app.post("/mcp/debug", tags=["HTTP MCP"])
async def mcp_debug(request: Request):
    """Debug endpoint to see exactly what the MCP Inspector is sending"""
    try:
        body = await request.json()
        logger.info(f"DEBUG: Received request: {safe_json_dumps(body, indent=2)}")
        
        # Return the exact same thing but with debugging info
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": body.get("id", 1),
            "result": {
                "debug": "Request received successfully",
                "received_body": body,
                "method_found": body.get("method", "NO_METHOD"),
                "params_found": body.get("params", "NO_PARAMS")
            }
        })
    except Exception as e:
        logger.error(f"Debug endpoint error: {str(e)}")
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": 1,
            "error": {
                "code": -32603,
                "message": str(e)
            }
        }, status_code=500)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)