# 🐳 Docker Installation & Setup Guide

Docker is a containerization software that wraps our database, scheduler, web server, and scraping worker into a single package. By using Docker, you do not need to install Python, PostgreSQL, or Redis manually on your machine.

Follow the instructions below for your specific operating system to install and start Docker.

---

## 🗔 1. Windows Setup (10 & 11)

### Step A: Download the Installer
1. Go to the official Docker website and download the installer for Windows:
   👉 **[Download Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/)**
2. Double-click the downloaded **`Docker Desktop Installer.exe`** to start the setup.

### Step B: Run the Installation Wizard
1. On the configuration page, make sure the option **"Use WSL 2 instead of Hyper-V"** is **checked** (this is highly recommended for speed and stability).
2. Click **Ok** and wait for the installer to unpack all files.
3. Once completed, click **Close and restart** your computer.

### Step C: Start Docker Desktop
1. After your computer restarts, open the **Docker Desktop** application from your Start Menu.
2. Accept the service agreement.
3. Keep the Docker Desktop window open. You should see a green indicator at the bottom left showing that the Docker engine is running.
4. You can now double-click **`setup.bat`** in your project folder to start the application!

---

## 🍎 2. macOS Setup (MacBook / iMac)

### Step A: Download the Installer
1. Go to the official Docker website:
   👉 **[Download Docker Desktop for Mac](https://www.docker.com/products/docker-desktop/)**
2. **Important:** Select the correct version for your Mac processor:
   * **Mac with Apple Chip:** Choose this if you have an M1, M2, or M3 Mac.
   * **Mac with Intel Chip:** Choose this if you have an older Intel Mac.

### Step B: Install the App
1. Double-click the downloaded `.dmg` file to open it.
2. Drag and drop the **Docker** icon into your **Applications** folder.

### Step C: Run Docker
1. Open your **Applications** folder and double-click **Docker.app**.
2. Approve any system access prompts and accept the terms of service.
3. Once the Docker icon in your menu bar stops animated and shows active, Docker is ready!
4. You can now run `./setup.sh` in your terminal inside the project directory.

---

## 🐧 3. Ubuntu & Linux Setup

Run the following commands in your terminal to download and install Docker:

### Step A: Install Docker and Docker Compose
```bash
# Update package list
sudo apt-get update

# Install Docker, the CLI, and the Compose plugin
sudo apt-get install -y docker.io docker-compose-v2
```

### Step B: Allow running Docker without sudo (Optional but Recommended)
By default, Docker commands require `sudo`. Run these commands so you don't have to prefix everything with sudo:
```bash
# Create the docker group (if it doesn't already exist)
sudo groupadd docker

# Add your user to the docker group
sudo usermod -aG docker $USER

# Apply the group changes (or log out and log back in)
newgrp docker
```

### Step C: Start the Docker Service
```bash
# Start Docker service
sudo systemctl start docker

# Enable Docker to start automatically on system boot
sudo systemctl enable docker
```

---

## 🩺 4. Verification Check

To confirm Docker is correctly installed and active on your system, open your terminal (or Command Prompt on Windows) and run:

```bash
docker --version
```
*Expected Output: `Docker version 24.x.x, build xxxxx`*

```bash
docker compose version
```
*Expected Output: `Docker Compose version v2.x.x`*
