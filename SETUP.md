# 🛠️ Remote.io Scraper - Installation & Operations Guide

This guide provides step-by-step instructions on deploying, operating, and managing the Remote.io Job Scraper application stack.

---

## 📋 Prerequisites

Before running the scraper, verify that your machine has the following software installed:

1.  **Docker Desktop** (version 20.10 or newer)
    *   [Download for Windows/Mac/Linux](https://www.docker.com/products/docker-desktop/)
2.  **Internet Access**
    *   Required to download initial service images and connect to the Remote.io job API.

---

## ⚡ Quick Deployment Walkthrough

### 🍎 For macOS & 🐧 Linux (including Ubuntu)
1.  Open your terminal application.
2.  Navigate to the project folder:
    ```bash
    cd "/path/to/remoteio-job-scraper"
    ```
3.  Set execute permissions and run the setup wizard:
    ```bash
    chmod +x setup.sh
    ./setup.sh
    ```

---

### 🪟 For Windows (10/11)
1.  Open the project folder in File Explorer.
2.  Right-click **`setup.bat`** and click **Run as administrator** (or double-click to launch).
3.  The console window will open and walk you through generating your configuration.

---

## ⚙️ Environment Variables Config (`.env`)

During setup, a file named `.env` is created in your root directory. You can edit this file at any time with a standard text editor.

```ini
# Security key required by the dashboard to authorize manual scraper triggers.
API_KEY=your_secure_api_key_here

# Optional: List of custom proxy URLs, comma-separated (e.g. rotating residential proxies).
# Format: http://username:password@ip_address:port
PROXY_URL=http://user123:pass456@123.45.67.89:8080

# Permitted dashboard domain names
CORS_ORIGINS=http://localhost:8000,http://127.0.0.1:8000
```

> [!WARNING]
> If you make changes to the `.env` file while the containers are running, you must restart them to apply the new settings:
> ```bash
> docker compose restart
> ```

---

## 🌐 Configuring Scraper Proxies

To prevent Remote.io from rate limiting or blocking your IP addresses, you have two options for configuring proxies:

### Option A: Global Rotating Proxies (via `.env`)
You can add a list of proxy servers to `PROXY_URL` in your `.env` file:
```ini
PROXY_URL=http://p1.proxy.com:8080,http://p2.proxy.com:8080,http://p3.proxy.com:8080
```
If configured, the scraper will select a random proxy from this list for every page request, providing rotating security.

### Option B: Custom Scrape Override (via Dashboard UI)
If you have a specific proxy you want to use for an on-demand run:
1.  Open the dashboard browser window at [http://localhost:8000](http://localhost:8000).
2.  Locate the **Scraper Preferences** section.
3.  Enter your custom proxy URL in the **Proxy URL** text input.
4.  Click **Trigger Live Scrape**. This proxy will override any global proxy settings for the current scrape run.

---

## ⏰ Changing the Scrape Schedule (Cron)

By default, the worker is configured to run an automatic job scraping cycle **every hour**. To change this schedule:

1.  Open `docker-compose.yml` in a text editor.
2.  Look for the environment variables of the `celery_beat` and `celery_worker` services.
3.  Alternatively, the scheduler is configured in `app/scheduler/celery_tasks.py`. You can adjust the recurrence schedules in your Celery setup routines.

---

## 🩺 Diagnostic Operations

### 1. View Running Containers
Verify that all five application services are active and running:
```bash
docker compose ps
```
You should see:
*   `remoteio_api` (Up)
*   `remoteio_celery_worker` (Up)
*   `remoteio_celery_beat` (Up)
*   `remoteio_postgres` (Up)
*   `remoteio_redis` (Up)

### 2. Inspect Logging Output
To check logs for the scraper to ensure requests are passing successfully:
```bash
# Monitor scraping progress
docker compose logs -f celery_worker

# Monitor dashboard requests
docker compose logs -f api
```

### 3. Resolving Port Conflicts (Port 8000)
If the setup fails with `address already in use` for port `8000`:
1.  Open `docker-compose.yml` in a text editor.
2.  Locate the `api` service ports mapping:
    ```yaml
    ports:
      - "8000:8000"
    ```
3.  Change the host port (the first `8000`) to another free port, for example `8080`:
    ```yaml
    ports:
      - "8080:8000"
    ```
4.  Restart the containers: `docker compose up -d`. You will now access the dashboard at **`http://localhost:8080`**.

---

## 💻 Running Locally Without Docker (Advanced)

If you prefer to run the application directly on your local system without Docker, follow these steps.

### 1. Install External Dependencies
You must manually install and start these services on your system:
*   **Python 3.11**
*   **PostgreSQL** (Create a database named `remoteio_jobs`)
*   **Redis** (Used as the message broker for Celery)

### 2. Configure Local Environment Variables
Create a `.env` file in the root directory. Modify the database and Redis URLs to point to your local installations:
```ini
API_KEY=remoteio-secret-key
PROXY_URL=

# Local connection strings
DATABASE_URL=postgresql://postgres:password@localhost:5432/remoteio_jobs
REDIS_URL=redis://localhost:6379/0
```

### 3. Install Python Requirements
Create a virtual environment and install dependencies:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Run the services in 3 separate terminals

*   **Terminal 1: Start the Web Server (FastAPI)**
    ```bash
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
    ```
*   **Terminal 2: Start the background Worker (Celery)**
    ```bash
    celery -A app.scheduler.celery_tasks.celery_app worker --loglevel=info
    ```
*   **Terminal 3: Start the scheduler clock (Celery Beat)**
    ```bash
    celery -A app.scheduler.celery_tasks.celery_app beat --loglevel=info
    ```

