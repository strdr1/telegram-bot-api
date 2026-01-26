# PowerShell Deployment Script for Telegram Bot
# Server: a950841.fvds.ru (155.212.164.61)
# Password: Mashkov.Rest

param(
    [switch]$Force
)

# Server Configuration
$ServerIP = "155.212.164.61"
$ServerUser = "root"
$ServerPassword = "Mashkov.Rest"
$ServerDomain = "a950841.fvds.ru"

# Output Functions
function Write-Success { 
    param($Message) 
    Write-Host "[SUCCESS] $Message" -ForegroundColor Green 
}

function Write-Info { 
    param($Message) 
    Write-Host "[INFO] $Message" -ForegroundColor Blue 
}

function Write-Warning { 
    param($Message) 
    Write-Host "[WARNING] $Message" -ForegroundColor Yellow 
}

function Write-Error { 
    param($Message) 
    Write-Host "[ERROR] $Message" -ForegroundColor Red 
}

function Write-Header { 
    param($Message) 
    Write-Host "`n==================================" -ForegroundColor Blue
    Write-Host $Message -ForegroundColor Blue
    Write-Host "==================================" -ForegroundColor Blue
}

# Check for PuTTY
function Test-PuTTY {
    if (-not (Get-Command plink -ErrorAction SilentlyContinue)) {
        Write-Warning "PuTTY not found. Downloading..."
        
        $puttyUrl = "https://the.earth.li/~sgtatham/putty/latest/w64/putty.zip"
        $puttyZip = Join-Path $env:TEMP "putty.zip"
        $puttyDir = Join-Path $env:TEMP "putty"
        
        try {
            Invoke-WebRequest -Uri $puttyUrl -OutFile $puttyZip
            Expand-Archive -Path $puttyZip -DestinationPath $puttyDir -Force
            $env:PATH += ";$puttyDir"
            Write-Success "PuTTY downloaded and configured"
        }
        catch {
            Write-Error "Failed to download PuTTY: $_"
            Write-Info "Please download PuTTY manually from https://putty.org/"
            exit 1
        }
    }
}

# Execute remote command
function Invoke-RemoteCommand {
    param($Command)
    Write-Info "Executing: $Command"
    
    $result = & plink -ssh -batch -pw $ServerPassword "$ServerUser@$ServerIP" $Command 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Command finished with code $LASTEXITCODE"
    }
    return $result
}

# Copy file to server
function Copy-ToServer {
    param($LocalFile, $RemotePath)
    Write-Info "Copying $LocalFile -> $RemotePath"
    & pscp -batch -pw $ServerPassword $LocalFile "$ServerUser@$ServerIP`:$RemotePath"
}

# Main deployment function
function Start-Deployment {
    Write-Header "[DEPLOYMENT] TELEGRAM BOT AUTO DEPLOYMENT"
    
    Write-Info "Server: $ServerDomain ($ServerIP)"
    Write-Info "User: $ServerUser"
    Write-Info "Starting deployment..."
    
    # Check PuTTY
    Test-PuTTY
    
    # Test connection
    Write-Info "Testing server connection..."
    try {
        $testResult = Invoke-RemoteCommand "echo 'Connection successful'"
        if ($testResult -match "Connection successful") {
            Write-Success "Server connection established"
        } else {
            throw "Unexpected server response"
        }
    }
    catch {
        Write-Error "Failed to connect to server!"
        Write-Error "Check IP address, password and server availability"
        exit 1
    }
    
    # Step 1: Update system
    Write-Header "[STEP 1] INSTALLING SYSTEM PACKAGES"
    Invoke-RemoteCommand "apt update"
    Invoke-RemoteCommand "apt upgrade -y"
    Invoke-RemoteCommand "apt install -y python3 python3-pip python3-venv git nginx supervisor sqlite3 curl wget certbot python3-certbot-nginx"
    Write-Success "System packages installed"
    
    # Step 2: Create user
    Write-Header "[STEP 2] CREATING USER"
    Invoke-RemoteCommand "if ! id 'botuser' &>/dev/null; then useradd -m -s /bin/bash botuser; usermod -aG www-data botuser; fi"
    Write-Success "User botuser created"
    
    # Step 3: Create directories
    Write-Header "[STEP 3] CREATING DIRECTORIES"
    Invoke-RemoteCommand "mkdir -p /opt/telegram-bot /var/log/telegram-bot /var/run/telegram-bot"
    Invoke-RemoteCommand "chown -R botuser:botuser /opt/telegram-bot /var/log/telegram-bot /var/run/telegram-bot"
    Write-Success "Directories created"
    
    # Step 4: Clone repository
    Write-Header "[STEP 4] CLONING REPOSITORY"
    
    # Backup database if exists
    Write-Info "Backing up database..."
    Invoke-RemoteCommand "if [ -f /opt/telegram-bot/restaurant.db ]; then cp /opt/telegram-bot/restaurant.db /tmp/restaurant.db.bak; fi"
    
    Invoke-RemoteCommand "cd /opt"
    Invoke-RemoteCommand "if [ -d 'telegram-bot' ]; then rm -rf telegram-bot; fi"
    Invoke-RemoteCommand "git clone https://github.com/strdr1/telegram-bot-api.git telegram-bot"
    
    # Restore database if backup exists
    Write-Info "Restoring database..."
    Invoke-RemoteCommand "if [ -f /tmp/restaurant.db.bak ]; then cp /tmp/restaurant.db.bak /opt/telegram-bot/restaurant.db; rm /tmp/restaurant.db.bak; fi"
    
    Invoke-RemoteCommand "chown -R botuser:botuser /opt/telegram-bot"
    Write-Success "Repository cloned and database restored"
    
    # Step 5: Python dependencies
    Write-Header "[STEP 5] INSTALLING PYTHON DEPENDENCIES"
    Invoke-RemoteCommand "cd /opt/telegram-bot && sudo -u botuser python3 -m venv venv"
    Invoke-RemoteCommand "cd /opt/telegram-bot && sudo -u botuser bash -c 'source venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt'"
    Write-Success "Python dependencies installed"
    
    # Step 6: Create .env file
    Write-Header "[STEP 6] CREATING CONFIGURATION"
    
    if (Test-Path ".env") {
        Write-Info "Reading local .env file..."
        
        $envContent = Get-Content ".env"
        $botToken = ($envContent | Where-Object { $_ -match "BOT_TOKEN=" }) -replace "BOT_TOKEN=", ""
        $adminPassword = ($envContent | Where-Object { $_ -match "ADMIN_PASSWORD=" }) -replace "ADMIN_PASSWORD=", ""
        $prestoConnectionId = ($envContent | Where-Object { $_ -match "PRESTO_CONNECTION_ID=" }) -replace "PRESTO_CONNECTION_ID=", ""
        $prestoAppSecret = ($envContent | Where-Object { $_ -match "PRESTO_APP_SECRET=" }) -replace "PRESTO_APP_SECRET=", ""
        $prestoSecretKey = ($envContent | Where-Object { $_ -match "PRESTO_SECRET_KEY=" }) -replace "PRESTO_SECRET_KEY=", ""
        $prestoAccessToken = ($envContent | Where-Object { $_ -match "PRESTO_ACCESS_TOKEN=" }) -replace "PRESTO_ACCESS_TOKEN=", ""
        $googleApiKey = ($envContent | Where-Object { $_ -match "GOOGLE_API_KEY=" }) -replace "GOOGLE_API_KEY=", ""
        $googleSearchEngineId = ($envContent | Where-Object { $_ -match "GOOGLE_SEARCH_ENGINE_ID=" }) -replace "GOOGLE_SEARCH_ENGINE_ID=", ""
        
        # Create server .env file
        $serverEnv = @"
# Telegram Bot Configuration
BOT_TOKEN=$botToken
ADMIN_USER_ID=515216260
ADMIN_PASSWORD=$adminPassword

# Database
DATABASE_URL=sqlite:///restaurant.db

# Presto API Keys
PRESTO_CONNECTION_ID=$prestoConnectionId
PRESTO_APP_SECRET=$prestoAppSecret
PRESTO_SECRET_KEY=$prestoSecretKey
PRESTO_ACCESS_TOKEN=$prestoAccessToken

# Google API Keys
GOOGLE_API_KEY=$googleApiKey
GOOGLE_SEARCH_ENGINE_ID=$googleSearchEngineId

# AI API
POLZA_AI_TOKEN=ak_MUlqpkRNU2jE5Xo3tf2yOfZImxVP90gcvvcN2Neif2g

# Restaurant Settings
RESTAURANT_NAME=Mashkov
RESTAURANT_PHONE=+7 (495) 123-45-67
RESTAURANT_ADDRESS=Moscow, Example St, 1
RESTAURANT_HOURS=Daily 10:00-23:00

# Server Settings
HOST=0.0.0.0
PORT=8000
WEBHOOK_MODE=true
WEBHOOK_URL=https://$ServerDomain/webhook
WEBHOOK_PATH=/webhook
WEBHOOK_PORT=8000

# Miniapp Settings
MINIAPP_URL=https://$ServerDomain/miniapp/

# GitHub Auto-update
GITHUB_REPO=strdr1/telegram-bot-api
GITHUB_BRANCH=master

# Logging
LOG_LEVEL=INFO
LOG_FILE=/var/log/telegram-bot/bot.log
"@
        
        # Save to temp file and copy to server
        $tempEnvFile = Join-Path $env:TEMP "server.env"
        $serverEnv | Out-File -FilePath $tempEnvFile -Encoding UTF8
        Copy-ToServer $tempEnvFile "/opt/telegram-bot/.env"
        Invoke-RemoteCommand "chown botuser:botuser /opt/telegram-bot/.env"
        Remove-Item $tempEnvFile
        
        Write-Success "Configuration created"
    } else {
        Write-Error "Local .env file not found!"
        exit 1
    }
    
    # Step 7: SSL certificate
    Write-Header "[STEP 7] CONFIGURING SSL CERTIFICATE"
    Invoke-RemoteCommand "certbot certonly --nginx -d $ServerDomain --email admin@$ServerDomain --agree-tos --non-interactive --quiet || echo 'SSL already configured or error'"
    Write-Success "SSL certificate configured"
    
    # Step 8: Nginx
    Write-Header "[STEP 8] CONFIGURING NGINX"
    Invoke-RemoteCommand "cp /opt/telegram-bot/nginx.conf /etc/nginx/sites-available/telegram-bot"
    Invoke-RemoteCommand "ln -sf /etc/nginx/sites-available/telegram-bot /etc/nginx/sites-enabled/"
    Invoke-RemoteCommand "rm -f /etc/nginx/sites-enabled/default"
    Invoke-RemoteCommand "nginx -t"
    Invoke-RemoteCommand "systemctl restart nginx"
    Write-Success "Nginx configured"
    
    # Step 9: Supervisor
    Write-Header "[STEP 9] CONFIGURING SUPERVISOR"
    Invoke-RemoteCommand "cp /opt/telegram-bot/supervisor.conf /etc/supervisor/conf.d/telegram-bot.conf"
    Invoke-RemoteCommand "supervisorctl reread"
    Invoke-RemoteCommand "supervisorctl update"
    Write-Success "Supervisor configured"
    
    # Step 10: Start services
    Write-Header "[STEP 10] STARTING SERVICES"
    Invoke-RemoteCommand "supervisorctl start telegram-bot-group"
    Start-Sleep -Seconds 5
    Write-Success "Services started"
    
    # Step 11: Check status
    Write-Header "[STEP 11] CHECKING STATUS"
    Invoke-RemoteCommand "supervisorctl status"
    
    # Check webhook
    Write-Info "Checking webhook..."
    try {
        $webhookTest = Invoke-WebRequest -Uri "https://$ServerDomain/health" -UseBasicParsing
        if ($webhookTest.Content -match "ok") {
            Write-Success "Webhook is working!"
        } else {
            Write-Warning "Webhook may not be ready yet, check in a minute"
        }
    }
    catch {
        Write-Warning "Webhook may not be ready yet, check in a minute"
    }
    
    # Final information
    Write-Header "[COMPLETED] DEPLOYMENT FINISHED!"
    
    Write-Host "`n[SUCCESS] Bot successfully deployed to server!" -ForegroundColor Green
    Write-Host "`n[LINKS] Links:" -ForegroundColor Yellow
    Write-Host "   • Webhook: https://$ServerDomain/webhook"
    Write-Host "   • Health check: https://$ServerDomain/health"
    Write-Host "   • Miniapp: https://$ServerDomain/miniapp/"
    Write-Host "`n[NEXT STEPS] What to do next:" -ForegroundColor Yellow
    Write-Host "   1. Configure miniapp in @BotFather:"
    Write-Host "      URL: https://$ServerDomain/miniapp/"
    Write-Host "   2. Test the bot in Telegram"
    Write-Host "`n[MANAGEMENT] Management:" -ForegroundColor Yellow
    Write-Host "   • Status: plink -ssh -batch -pw $ServerPassword $ServerUser@$ServerIP '/opt/telegram-bot/monitor.sh status'"
    Write-Host "   • Logs: plink -ssh -batch -pw $ServerPassword $ServerUser@$ServerIP '/opt/telegram-bot/monitor.sh logs bot'"
    Write-Host "   • Restart: plink -ssh -batch -pw $ServerPassword $ServerUser@$ServerIP '/opt/telegram-bot/monitor.sh restart'"
}

# Start deployment
Start-Deployment