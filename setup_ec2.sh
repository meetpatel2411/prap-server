#!/usr/bin/env bash
# ==============================================================================
# setup_ec2.sh - Automated EC2 Ubuntu Deployment Script for PRAP
# Sets up Python 3 venv, SQLite, Gunicorn systemd service, and Nginx reverse proxy.
# ==============================================================================

set -e

echo "=== [1/6] Updating Ubuntu Packages & Installing Prerequisites ==="
sudo apt update -y
sudo apt install -y python3-pip python3-venv nginx sqlite3 unzip git curl

# Ensure Nginx (www-data) can read static files in /home/ubuntu
sudo chmod 755 /home/ubuntu

APP_DIR="/home/ubuntu/prap"
if [ ! -d "$APP_DIR" ]; then
    echo "Creating application directory: $APP_DIR"
    mkdir -p "$APP_DIR"
fi

cd "$APP_DIR"

echo "=== [2/6] Preparing Upload Temp Directory ==="
sudo mkdir -p /tmp/prap_uploads
sudo chown -R ubuntu:www-data /tmp/prap_uploads
sudo chmod -R 775 /tmp/prap_uploads

echo "=== [3/6] Setting Up Python Virtual Environment ==="
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "=== [4/6] Configuring Gunicorn Systemd Service ==="
sudo cp prap.service /etc/systemd/system/prap.service
sudo systemctl daemon-reload
sudo systemctl start prap
sudo systemctl enable prap

echo "=== [5/6] Configuring Nginx Reverse Proxy ==="
sudo cp prap_nginx.conf /etc/nginx/sites-available/prap
sudo rm -f /etc/nginx/sites-enabled/default
sudo ln -sf /etc/nginx/sites-available/prap /etc/nginx/sites-enabled/prap

sudo nginx -t
sudo systemctl restart nginx

echo "=== [6/6] Verifying Deployment Status ==="
sudo systemctl status prap --no-pager --lines=5

PUBLIC_IP=$(curl -s http://checkip.amazonaws.com || curl -s ifconfig.me || echo "your-ec2-public-ip")

echo "=================================================================="
echo "🎉 PRAP Successfully Deployed on AWS EC2!"
echo "Access the Platform Web UI at: http://${PUBLIC_IP}"
echo "API Health Check:              http://${PUBLIC_IP}/api/health"
echo "Assessment Endpoint:          POST http://${PUBLIC_IP}/api/assessments"
echo "=================================================================="
