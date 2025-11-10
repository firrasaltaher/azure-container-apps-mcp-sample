# Azure Container Apps remote MCP server example

This MCP server uses SSE transport and is authenticated with an API key.

## Running locally

Prerequisites:
* Python 3.11 or later
* [uv](https://docs.astral.sh/uv/getting-started/installation/)
* [Microsoft ODBC Driver 18 for SQL Server](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server)

Run the server locally:

```bash
uv venv
uv sync

# linux/macOS
export API_KEYS=<AN_API_KEY>
# windows
set API_KEYS=<AN_API_KEY>

# or load the vars from the .env file
# First load the .env file
Get-Content .env | ForEach-Object {
    if ($_ -match '^(?<key>[^#=]+)=(?<value>.+)$') {
        [System.Environment]::SetEnvironmentVariable($matches['key'], $matches['value'])
    }
}

uv run fastapi dev main.py

```

VS Code MCP configuration (mcp.json):

```json
{
    "inputs": [
        {
            "type": "promptString",
            "id": "api-key",
            "description": "SQL Server MCP API Key",
            "password": true
        }
    ],
    "servers": {
        "sql-server-mcp-sse": {
            "type": "sse",
            "url": "http://localhost:8000/sse",
            "headers": {
                "x-api-key": "${input:api-key}"
            }
        }
    }
}
```

## Deploy to Azure Container Apps

```bash
.\deploy.ps1
```

Alternatively, you can deploy using the Azure CLI directly:

```bash
az containerapp up -g ${{RESOURCE_GROUP_NAME}} -n weather-mcp --environment mcp -l westus --env-vars-file .env --source .
```

```bash
# First load the .env file
Get-Content .env | ForEach-Object {
    if ($_ -match '^(?<key>[^#=]+)=(?<value>.+)$') {
        [System.Environment]::SetEnvironmentVariable($matches['key'], $matches['value'])
    }
}

# Then run with individual env vars
az containerapp up -g $env:RESOURCE_GROUP_NAME -n "sql-mcp" --environment $env:CONTAINER_APP_ENV -l $env:LOCATION --env-vars "API_KEYS=$env:API_KEYS" "SQL_SERVER_CONNECTION_STRING=$env:SQL_SERVER_CONNECTION_STRING" --source .
```

If the deployment is successful, the Azure CLI returns the URL of the app. You can use this URL to connect to the server from Visual Studio Code.

If the deployment fails, try again after updating the CLI and the Azure Container Apps extension:

```bash
az upgrade
az extension add -n containerapp --upgrade
```

## APIM Configuration

API Management instance of Basic V2 will need to be created/deployed either in the portal, terraform,bicep, or ARM.  PS/az cli is not available yet.

Once APIM Basic V2 (or any V2 tier that has MCP Server functionality), is available:

* Navigate to the "MCP Servers (preview)" section under APIs
* Click on "Create MCP server" and then choose "Expose an existing MCP server":
  * MCP server base url: Enter the container app endpoint, followed by /mcp
  * Display name: Functionality of the mcp server (sql mcp server)
  * Base path: This will be added as a suffix to the APIM url

* Once created, you should now see an MCP Server with a server url of https://{apim_fqdn}/{base_path}/mcp
