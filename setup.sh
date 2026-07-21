#!/bin/bash

# ============================================================================
#  Remote.io Job Scraper - Automated Setup Wizard
# ============================================================================

# Color palettes for terminal formatting
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color
BOLD='\033[1m'

echo -e "${BLUE}${BOLD}"
echo "================================================================="
echo "        REMOTE.IO JOB SCRAPER - AUTOMATED DEPLOYMENT WIZARD      "
echo "================================================================="
echo -e "${NC}"
echo "This installer will configure your environment, create configuration files,"
echo "and boot up the database, workers, and dashboard automatically."
echo "-----------------------------------------------------------------"

# Function to display error and exit
fail() {
    echo -e "\n${RED}❌ Error: $1${NC}"
    exit 1
}

# 1. Check if Docker is installed
echo -e "\n${BLUE}[1/5] Checking System Dependencies...${NC}"
if ! [ -x "$(command -v docker)" ]; then
    fail "Docker is not installed. Please install Docker first: https://docs.docker.com/get-docker/"
fi

if ! [ -x "$(command -v docker-compose)" ] && ! docker compose version &>/dev/null; then
    fail "Docker Compose is not installed. Please install docker-compose or update your Docker Desktop."
fi
echo -e "${GREEN}✓ Docker and Docker Compose detected.${NC}"

# 2. Setup Environment Configuration (.env)
echo -e "\n${BLUE}[2/5] Setting up environment configurations...${NC}"
ENV_FILE=".env"

if [ -f "$ENV_FILE" ]; then
    echo -e "${YELLOW}ℹ Existing .env configuration file detected.${NC}"
    read -p "Would you like to overwrite it and reconfigure your settings? (y/N): " OVERWRITE_ENV
    if [[ "$OVERWRITE_ENV" =~ ^[Yy]$ ]]; then
        rm "$ENV_FILE"
    fi
fi

if [ ! -f "$ENV_FILE" ]; then
    # Generate secure random API key as default
    DEFAULT_KEY=$(openssl rand -hex 16 2>/dev/null || echo "remoteio_sec_$(date +%s)")
    
    echo -e "Please configure the following settings. Press ${BOLD}[ENTER]${NC} to keep default values.\n"
    
    # Prompt for API Key
    read -p "🔑 Enter Security API Key [Default: $DEFAULT_KEY]: " USER_KEY
    API_KEY=${USER_KEY:-$DEFAULT_KEY}
    
    # Prompt for Proxy
    echo -e "\n${YELLOW}🛡️ Optional Proxy Config: Hides your scraper IP. Supports rotating residential proxies.${NC}"
    read -p "🌐 Enter Proxy URL (e.g., http://user:pass@host:port) [Default: None]: " USER_PROXY
    PROXY_URL=${USER_PROXY:-""}
    
    # Write .env file
    cat <<EOF > "$ENV_FILE"
# Remote.io Scraper Environment Settings
API_KEY=$API_KEY
PROXY_URL=$PROXY_URL
CORS_ORIGINS=http://localhost:8000,http://127.0.0.1:8000
POSTGRES_DB=remoteio_jobs
REDIS_URL=redis://redis:6379/0
EOF
    echo -e "\n${GREEN}✓ Configuration saved successfully to .env${NC}"
else
    echo -e "${GREEN}✓ Keeping existing configuration in .env${NC}"
    # Load existing API_KEY from .env to print it at the end
    API_KEY=$(grep -E "^API_KEY=" "$ENV_FILE" | cut -d'=' -f2- | tr -d '\r')
fi

# 3. Build and Start Docker Containers
echo -e "\n${BLUE}[3/5] Compiling and starting Docker containers...${NC}"
echo "This might take a few moments on the first run..."
docker compose up -d --build || fail "Failed to launch Docker containers."

# 4. Wait for Database to become healthy
echo -e "\n${BLUE}[4/5] Waiting for Database server to initialize...${NC}"
COUNTER=0
until docker compose exec -T postgres pg_isready -U postgres &>/dev/null; do
    sleep 2
    COUNTER=$((COUNTER + 1))
    if [ $COUNTER -gt 15 ]; then
        fail "Database container failed to initialize in time."
    fi
    echo -n "."
done
echo -e "\n${GREEN}✓ Database server is online and accepting connections.${NC}"

# 5. Verify API Server Health
echo -e "\n${BLUE}[5/5] Verifying API Server health...${NC}"
API_HEALTH=0
for i in {1..10}; do
    STATUS_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/docs || echo "000")
    if [ "$STATUS_CODE" == "200" ]; then
        API_HEALTH=1
        break
    fi
    sleep 2
done

if [ $API_HEALTH -eq 1 ]; then
    echo -e "${GREEN}✓ API Server is healthy and running.${NC}"
else
    echo -e "${YELLOW}⚠️ API Server is taking longer to respond. It may still be booting up.${NC}"
fi

# Summary
echo -e "\n${GREEN}${BOLD}=================================================================${NC}"
echo -e "${GREEN}${BOLD}🎉 SUCCESS! SETUP COMPLETE!${NC}"
echo -e "${GREEN}${BOLD}=================================================================${NC}"
echo -e "\nYour Remote.io Scraper Dashboard is now active and ready."
echo -e "\n👉 Access the Dashboard: ${BLUE}${BOLD}http://localhost:8000${NC}"
echo -e "🔑 Your Security API Key: ${YELLOW}${BOLD}$API_KEY${NC}"
echo -e "\nTo view logs from background scraper workers, run: ${BOLD}docker compose logs -f celery_worker${NC}"
echo -e "To stop the scraper services at any time, run: ${BOLD}docker compose down${NC}"
echo -e "-----------------------------------------------------------------\n"
