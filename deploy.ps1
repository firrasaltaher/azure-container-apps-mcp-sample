# PowerShell deployment script for MCP SDK Server

# Function to check if a resource exists
function Test-AzureResource {
    param(
        [string]$Command,
        [string]$ResourceName,
        [string]$ResourceType
    )
    
    try {
        $result = Invoke-Expression $Command 2>$null
        if ($LASTEXITCODE -eq 0 -and $result) {
            Write-Host "✅ $ResourceType '$ResourceName' already exists" -ForegroundColor Green
            return $true
        }
    }
    catch {
        # Resource doesn't exist
    }
    
    Write-Host "❌ $ResourceType '$ResourceName' does not exist" -ForegroundColor Yellow
    return $false
}

# Load environment variables from .env file
Get-Content .env | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]*?)\s*=\s*(.*?)\s*$') {
        $name = $matches[1]
        $value = $matches[2]
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

# Get environment variables
$RESOURCE_GROUP_NAME = $env:RESOURCE_GROUP_NAME
$CONTAINER_APP_NAME = $env:CONTAINER_APP_NAME
$CONTAINER_APP_ENV = $env:CONTAINER_APP_ENV
$LOCATION = $env:LOCATION
$API_KEYS = $env:API_KEYS
$SQL_SERVER_CONNECTION_STRING = $env:SQL_SERVER_CONNECTION_STRING
$REGISTRY_NAME = $env:REGISTRY_NAME

# Validate required variables
if (-not $RESOURCE_GROUP_NAME) { Write-Host "❌ RESOURCE_GROUP_NAME is not set" -ForegroundColor Red; exit 1 }
if (-not $CONTAINER_APP_NAME) { Write-Host "❌ CONTAINER_APP_NAME is not set" -ForegroundColor Red; exit 1 }
if (-not $CONTAINER_APP_ENV) { Write-Host "❌ CONTAINER_APP_ENV is not set" -ForegroundColor Red; exit 1 }
if (-not $LOCATION) { Write-Host "❌ LOCATION is not set" -ForegroundColor Red; exit 1 }
if (-not $REGISTRY_NAME) { Write-Host "❌ REGISTRY_NAME is not set" -ForegroundColor Red; exit 1 }

# Check if Dockerfile exists
if (-not (Test-Path "Dockerfile")) {
    Write-Host "❌ Dockerfile not found in current directory" -ForegroundColor Red
    exit 1
}

Write-Host "🚀 Deploying MCP SDK Server to Azure Container Apps" -ForegroundColor Green
Write-Host "Resource Group: $RESOURCE_GROUP_NAME" -ForegroundColor Cyan
Write-Host "Container App: $CONTAINER_APP_NAME" -ForegroundColor Cyan
Write-Host "Environment: $CONTAINER_APP_ENV" -ForegroundColor Cyan
Write-Host "Location: $LOCATION" -ForegroundColor Cyan
Write-Host "Registry: $REGISTRY_NAME" -ForegroundColor Cyan

# Check if resource group exists
Write-Host "📦 Checking resource group..." -ForegroundColor Yellow
$rgExists = Test-AzureResource -Command "az group show --name '$RESOURCE_GROUP_NAME' --query 'name' -o tsv" -ResourceName $RESOURCE_GROUP_NAME -ResourceType "Resource Group"

if (-not $rgExists) {
    Write-Host "📦 Creating resource group..." -ForegroundColor Yellow
    az group create --name $RESOURCE_GROUP_NAME --location $LOCATION
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Failed to create resource group" -ForegroundColor Red
        exit 1
    }
    Write-Host "✅ Resource group created successfully" -ForegroundColor Green
}

# Check if container app environment exists
Write-Host "🌐 Checking Container App Environment..." -ForegroundColor Yellow
$envExists = Test-AzureResource -Command "az containerapp env show --name '$CONTAINER_APP_ENV' --resource-group '$RESOURCE_GROUP_NAME' --query 'name' -o tsv" -ResourceName $CONTAINER_APP_ENV -ResourceType "Container App Environment"

if (-not $envExists) {
    Write-Host "🌐 Creating Container App Environment..." -ForegroundColor Yellow
    az containerapp env create --name $CONTAINER_APP_ENV --resource-group $RESOURCE_GROUP_NAME --location $LOCATION
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Failed to create container app environment" -ForegroundColor Red
        exit 1
    }
    Write-Host "✅ Container App Environment created successfully" -ForegroundColor Green
}

# Check if container app exists
Write-Host "📱 Checking Container App..." -ForegroundColor Yellow
$appExists = Test-AzureResource -Command "az containerapp show --name '$CONTAINER_APP_NAME' --resource-group '$RESOURCE_GROUP_NAME' --query 'name' -o tsv" -ResourceName $CONTAINER_APP_NAME -ResourceType "Container App"

if ($appExists) {
    Write-Host "🔄 Container App exists, updating..." -ForegroundColor Yellow
    $deployAction = "update"
} else {
    Write-Host "🚢 Container App does not exist, creating..." -ForegroundColor Yellow
    $deployAction = "create"
}

# Check if Azure Container Registry exists
Write-Host "📦 Checking Azure Container Registry..." -ForegroundColor Yellow
$acrExists = Test-AzureResource -Command "az acr show --name '$REGISTRY_NAME' --resource-group '$RESOURCE_GROUP_NAME' --query 'name' -o tsv" -ResourceName $REGISTRY_NAME -ResourceType "Azure Container Registry"

if (-not $acrExists) {
    Write-Host "📦 Creating Azure Container Registry..." -ForegroundColor Yellow
    az acr create --name $REGISTRY_NAME --resource-group $RESOURCE_GROUP_NAME --location $LOCATION --sku Basic
    if ($LASTEXITCODE -ne 0) {
        Write-Host "❌ Failed to create Azure Container Registry" -ForegroundColor Red
        exit 1
    }
    Write-Host "✅ Azure Container Registry created successfully" -ForegroundColor Green
}

# Retrieve ACR login server
Write-Host "🔍 Retrieving ACR login server..." -ForegroundColor Yellow
$acrLoginServer = az acr show --name $REGISTRY_NAME --resource-group $RESOURCE_GROUP_NAME --query 'loginServer' -o tsv
if (-not $acrLoginServer) {
    Write-Host "❌ Failed to retrieve ACR login server" -ForegroundColor Red
    exit 1
}
Write-Host "✅ ACR login server: $acrLoginServer" -ForegroundColor Green

# Enable admin user for ACR to ensure authentication works
Write-Host "🔐 Enabling ACR admin user..." -ForegroundColor Yellow
az acr update --name $REGISTRY_NAME --admin-enabled true --only-show-errors
if ($LASTEXITCODE -ne 0) {
    Write-Host "⚠️  Warning: Failed to enable ACR admin user" -ForegroundColor Yellow
}

# Alternative 1: Try ACR Build (cloud-based, no local Docker needed)
Write-Host "🔨 Building and pushing Docker image to ACR (cloud build)..." -ForegroundColor Yellow
$acrImageName = "$CONTAINER_APP_NAME:latest"
Write-Host "Image name: $acrImageName" -ForegroundColor Gray
Write-Host "Registry: $REGISTRY_NAME" -ForegroundColor Gray
Write-Host "Build context: $(Get-Location)" -ForegroundColor Gray

# Create a simple ACR task for one-time build
$buildSuccess = $false
try {
    az acr build --image "$acrImageName" --registry $REGISTRY_NAME --file Dockerfile . --no-logs
    if ($LASTEXITCODE -eq 0) {
        $buildSuccess = $true
        Write-Host "✅ Docker image built and pushed successfully via ACR Build: $acrImageName" -ForegroundColor Green
    }
}
catch {
    Write-Host "⚠️ ACR Build failed, trying alternative method..." -ForegroundColor Yellow
}

# Alternative 2: Use containerapp up with source (builds in cloud)
if (-not $buildSuccess) {
    Write-Host "🔄 Using containerapp up with source build..." -ForegroundColor Yellow
    Write-Host "✅ Will build image during container app deployment" -ForegroundColor Green
    $useSourceBuild = $true
} else {
    $useSourceBuild = $false
}

# Deploy the container app using the appropriate method
Write-Host "🚢 Deploying Container App ($deployAction)..." -ForegroundColor Yellow

if ($useSourceBuild) {
    # Use source build (builds image in cloud during deployment)
    az containerapp up `
        --name $CONTAINER_APP_NAME `
        --resource-group $RESOURCE_GROUP_NAME `
        --environment $CONTAINER_APP_ENV `
        --location $LOCATION `
        --registry-server $acrLoginServer `
        --source . `
        --env-vars "API_KEYS=$API_KEYS" "SQL_SERVER_CONNECTION_STRING=$SQL_SERVER_CONNECTION_STRING" `
        --ingress external `
        --target-port 8000
} else {
    # Use pre-built image from ACR
    az containerapp up `
        --name $CONTAINER_APP_NAME `
        --resource-group $RESOURCE_GROUP_NAME `
        --environment $CONTAINER_APP_ENV `
        --location $LOCATION `
        --registry-server $acrLoginServer `
        --image "$acrLoginServer/$acrImageName" `
        --env-vars "API_KEYS=$API_KEYS" "SQL_SERVER_CONNECTION_STRING=$SQL_SERVER_CONNECTION_STRING" `
        --ingress external `
        --target-port 8000
}

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Failed to deploy container app" -ForegroundColor Red
    exit 1
}

Write-Host "✅ MCP SDK Server deployment completed!" -ForegroundColor Green
Write-Host ""

# Get the FQDN
Write-Host "🔍 Retrieving deployment information..." -ForegroundColor Yellow
$fqdn = az containerapp show --name $CONTAINER_APP_NAME --resource-group $RESOURCE_GROUP_NAME --query 'properties.configuration.ingress.fqdn' -o tsv

if ($fqdn) {
    Write-Host "📋 Deployment Summary:" -ForegroundColor Green
    Write-Host "  🔗 URL: https://$fqdn" -ForegroundColor White
    Write-Host "  🔑 API Key: $API_KEYS" -ForegroundColor White
    Write-Host "  📊 Health Check: https://$fqdn/health" -ForegroundColor White
    Write-Host "  🛠️  Tools List: https://$fqdn/mcp/tools/list" -ForegroundColor White
    Write-Host ""
    Write-Host "🧪 Testing endpoints..." -ForegroundColor Yellow
    
    # Test health endpoint
    try {
        $healthResponse = Invoke-RestMethod -Uri "https://$fqdn/health" -Headers @{ "x-api-key" = $API_KEYS } -Method Get -TimeoutSec 30
        Write-Host "✅ Health check: PASSED" -ForegroundColor Green
    }
    catch {
        Write-Host "⚠️  Health check: FAILED (may take a few minutes to be ready)" -ForegroundColor Yellow
    }

    # Use healthResponse to log the health check result
    if ($healthResponse) {
        Write-Host "Health check response: $($healthResponse | ConvertTo-Json -Depth 2)" -ForegroundColor Gray
    }
} else {
    Write-Host "⚠️  Could not retrieve FQDN. Check deployment status manually." -ForegroundColor Yellow
}
Write-Host ""
Write-Host "💡 To view logs: az containerapp logs show --name $CONTAINER_APP_NAME --resource-group $RESOURCE_GROUP_NAME" -ForegroundColor Yellow