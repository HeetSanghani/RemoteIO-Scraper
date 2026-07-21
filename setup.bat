@echo off
rem ============================================================================
rem  Remote.io Job Scraper - Automated Windows Setup Script
rem ============================================================================

cls
echo =================================================================
echo        REMOTE.IO JOB SCRAPER - AUTOMATED WINDOWS DEPLOYMENT
echo =================================================================
echo This helper wizard will verify your software dependencies, write the
echo necessary security credentials, and spin up the complete application.
echo -----------------------------------------------------------------

rem Step 1: Dependency Check
echo.
echo [Step 1: Checking System Requirements...]
echo Checking if Docker is installed...
where docker >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Docker is missing. Please download and install Docker Desktop first: https://www.docker.com/products/docker-desktop/
    pause
    exit /b 1
)

echo Checking if Docker Desktop is running...
docker info >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Docker is installed but the Docker service is not running. 
    echo Please make sure Docker Desktop is started and try again.
    pause
    exit /b 1
)
echo All system requirements met successfully.

rem Step 2: Environment Configuration
echo.
echo [Step 2: Configuring Secrets ^& Environment Variables...]
set ENV_FILE=.env

if exist %ENV_FILE% (
    echo [INFO] Found an existing settings file (.env).
    set /p OVERWRITE="Would you like to overwrite it and reconfigure? [y/N]: "
)

if "%OVERWRITE%"=="y" (
    del %ENV_FILE%
)
if "%OVERWRITE%"=="Y" (
    del %ENV_FILE%
)

if not exist %ENV_FILE% (
    set DEFAULT_KEY=remoteio_sec_%RANDOM%%RANDOM%
    echo Please fill out the setup options. Press [ENTER] to select default values.
    echo.
    
    set /p USER_KEY="Choose Security API Key [Default: %DEFAULT_KEY%]: "
    if "%USER_KEY%"=="" (
        set API_KEY=%DEFAULT_KEY%
    ) else (
        set API_KEY=%USER_KEY%
    )
    
    echo.
    echo Optional Proxy: Used to mask scraping requests to avoid rate limits.
    set /p USER_PROXY="Enter Proxy URL (e.g. http://username:password@ip:port) [Default: None]: "
    if "%USER_PROXY%"=="" (
        set PROXY_URL=
    ) else (
        set PROXY_URL=%USER_PROXY%
    )
    
    rem Write settings file
    echo API_KEY=%API_KEY% > .env
    echo PROXY_URL=%PROXY_URL% >> .env
    echo CORS_ORIGINS=http://localhost:8000,http://127.0.0.1:8000 >> .env
    echo POSTGRES_DB=remoteio_jobs >> .env
    echo REDIS_URL=redis://redis:6379/0 >> .env
    
    echo.
    echo [SUCCESS] Environment configuration generated and saved to .env
) else (
    echo [INFO] Using existing environment configurations from .env
    for /f "tokens=2 delims==" %%i in ('findstr "API_KEY" .env') do set API_KEY=%%i
)

rem Step 3: Compiling and starting services
echo.
echo [Step 3: Spinning up application services via Docker...]
echo Starting the download and compilation of these services:
echo   - remoteio_postgres (Job listing database)
echo   - remoteio_redis (Message broker ^& caching)
echo   - remoteio_api (Web dashboard server)
echo   - remoteio_celery_worker (Web scraper core engine)
echo   - remoteio_celery_beat (Hourly automation scheduler)
echo.
echo Running docker compose build ^& launch...
docker compose up -d --build
if %errorlevel% neq 0 (
    echo [ERROR] Docker Compose build failed.
    pause
    exit /b 1
)
echo.
echo Containers launched successfully in background.

rem Step 4: Verification
echo.
echo [Step 4: Waiting for database tables to initialize...]
echo.
:wait_loop
docker compose exec -T postgres pg_isready -U postgres >nul 2>nul
if %errorlevel% neq 0 (
    timeout /t 2 >nul
    echo | set /p ="."
    goto wait_loop
)
echo.
echo Database server is online and ready.

echo.
echo =================================================================
echo 🎉 SUCCESS! INSTALLATION COMPLETED SUCCESSFULLY!
echo =================================================================
echo Your Remote.io Scraper Application is now fully deployed and running.
echo.
echo 👉 Dashboard URL: http://localhost:8000
echo.
echo Useful Commands:
echo   * Check active containers:     docker compose ps
echo   * Monitor live scraper logs:   docker compose logs -f celery_worker
echo   * View API web server logs:    docker compose logs -f api
echo   * Stop/Turn off application:   docker compose down
echo =================================================================
pause
