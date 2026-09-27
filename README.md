# Production Readiness Assessment Platform (PRAP)

[![PRAP Test Suite](https://img.shields.io/badge/pytest-passing-success.svg)](file:///d:/whiteandbox/project/PRAP/tests/test_prap.py)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Deployment](https://img.shields.io/badge/AWS-EC2%20%2B%20Ubuntu-orange.svg)](setup_ec2.sh)
[![WSGI](https://img.shields.io/badge/server-Gunicorn%20%2B%20Nginx-blueviolet.svg)](prap.service)

The **Production Readiness Assessment Platform (PRAP)** is an automated software audit and governance platform designed to evaluate cloud applications and microservices against **26 standardized production-readiness rules** before live deployment.

PRAP combines rapid static codebase analysis, weighted readiness scoring (0–100), automated discrepancy detection, and a formal **Risk Exceptions workflow**, all served through a modern dark-mode DevOps observability dashboard.

---

## 🏛️ System Architecture

```text
       [ Developer / CI/CD ]
                 │ (Upload .zip or JSON path)
                 ▼
       [ AWS EC2 - Ubuntu 24.04 ]
                 │ (Port 80 / 443)
                 ▼
        [ Nginx Reverse Proxy ]
                 │ (Unix Socket: prap.sock)
                 ▼
   [ Gunicorn WSGI Application Server ]
                 │
   [ Flask PRAP Core Application Engine ]
    ├── Temporary Ingestion Pipeline (/tmp/prap_uploads/ UUID)
    ├── 26 Rules Engine (Security, Reliability, Observability, etc.)
    ├── Score & Status Evaluator (Ready / Needs Attention / High Risk)
    ├── Ephemeral Directory Immediate Purge (Prevents EBS Exhaustion)
    └── SQLite3 Relational Database Layer (database.db)
```

---

## 📋 The 26 Production Readiness Rules

PRAP evaluates target repositories against 26 comprehensive rules spanning 6 core operational pillars:

| Pillar | Rules Count | Key Verification Checks |
| :--- | :---: | :--- |
| **1. Security (SEC)** | 5 | No hardcoded secrets/API keys (`SEC-001`), Protected `.gitignore` (`SEC-002`), HTTPS/SSL cookies (`SEC-003`), Production debug mode disabled (`SEC-004`), Pinned dependency constraints (`SEC-005`). |
| **2. Reliability (REL)** | 5 | `/health` endpoint (`REL-001`), Global error handlers (`REL-002`), Database retry/timeout resilience (`REL-003`), Graceful shutdown hooks (`REL-004`), Network call timeouts (`REL-005`). |
| **3. Observability (OBS)** | 4 | Standard logging framework (`OBS-001`), Elimination of naked `print()` statements (`OBS-002`), Request telemetry/timing (`OBS-003`), Structured log formatters (`OBS-004`). |
| **4. Performance (PERF)** | 4 | Production WSGI/Gunicorn configured (`PERF-001`), Payload buffer limits bounded (`PERF-002`), Database primary keys/indexes (`PERF-003`), Caching/compression enabled (`PERF-004`). |
| **5. Operations (OPS)** | 5 | Environment variable configuration (`OPS-001`), Systemd service or Dockerfile provided (`OPS-002`), Nginx reverse proxy configured (`OPS-003`), Database initialization/migrations (`OPS-004`), CI/CD pipeline defined (`OPS-005`). |
| **6. Documentation (DOC)** | 3 | Comprehensive `README.md` (`DOC-001`), Automated test suite with pytest (`DOC-002`), API route documentation (`DOC-003`). |

---

## 🚀 Phase 1: Local Development & Setup

### Prerequisites
- Python 3.10+
- SQLite3

### 1. Clone & Set Up Virtual Environment
```bash
git clone <your-repo-url> prap
cd prap
python3 -m venv venv

# Linux/macOS
source venv/bin/activate
# Windows PowerShell
.\venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

### 2. Run the Application Locally
```bash
python app.py
```
Open **[http://localhost:5000](http://localhost:5000)** in your browser.

---

## ⚡ Phase 2: Ingestion & Ephemeral Processing Pipeline

When hosted in the cloud, PRAP processes uploaded `.zip` archives through an ephemeral pipeline:
1. **Upload**: Receives `.zip` file via `POST /api/assessments` (supports files up to 50MB).
2. **Safe Extraction**: Extracts contents into `/tmp/prap_uploads/extract_<UUID>` using path sanitization to guard against Zip Slip directory traversal vulnerabilities.
3. **Execution**: Evaluates all 26 rules, identifies findings with line numbers and snippets, and saves the result to SQLite.
4. **Immediate Purge**: The temporary directory is completely deleted inside a `finally:` block, preventing EBS volume exhaustion.

---

## ☁️ Phase 3: Fast AWS Deployment (EC2 + Nginx + Gunicorn)

### 1. Provision EC2 Instance
- Launch an **Ubuntu 24.04 LTS** instance (`t3.micro` or `t3.small`).
- Security Group Inbound Rules:
  - **Port 80 (HTTP)** from `0.0.0.0/0`
  - **Port 443 (HTTPS)** from `0.0.0.0/0`
  - **Port 22 (SSH)** from your IP

### 2. Automated One-Click Deployment
SSH into your instance and run:
```bash
git clone <your-repo-url> /home/ubuntu/prap
cd /home/ubuntu/prap
chmod +x setup_ec2.sh
./setup_ec2.sh
```

### 3. Manual Step-by-Step Configuration (If Preferred)

#### Prepare Server
```bash
sudo apt update && sudo apt install python3-pip python3-venv nginx sqlite3 unzip git -y
cd /home/ubuntu/prap
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### Configure Systemd Service
Create `/etc/systemd/system/prap.service`:
```ini
[Unit]
Description=Gunicorn instance to serve PRAP
After=network.target

[Service]
User=ubuntu
Group=www-data
WorkingDirectory=/home/ubuntu/prap
Environment="PATH=/home/ubuntu/prap/venv/bin"
Environment="PRAP_DB_PATH=/home/ubuntu/prap/database.db"
ExecStart=/home/ubuntu/prap/venv/bin/gunicorn --workers 3 --bind 127.0.0.1:5000 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl start prap
sudo systemctl enable prap
```

#### Configure Nginx Reverse Proxy
Create `/etc/nginx/sites-available/prap`:
```nginx
server {
    listen 80;
    server_name _;

    client_max_body_size 50M;

    location /static/ {
        alias /home/ubuntu/prap/static/;
        expires 30d;
    }

    location / {
        include proxy_params;
        proxy_pass http://127.0.0.1:5000;
    }
}
```

Enable site and restart Nginx:
```bash
sudo ln -sf /etc/nginx/sites-available/prap /etc/nginx/sites-enabled/prap
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
```

---

## 🤖 Phase 4: Automation (GitHub Actions CI/CD)

The repository includes a ready-to-use GitHub Actions workflow in [`.github/workflows/deploy.yml`](file:///d:/whiteandbox/project/PRAP/.github/workflows/deploy.yml).

### Setup GitHub Secrets:
In your GitHub Repository Settings (`Settings` -> `Secrets and variables` -> `Actions`):
- `EC2_HOST`: Public IP or DNS of your EC2 instance.
- `EC2_USERNAME`: `ubuntu`
- `EC2_SSH_KEY`: Private SSH Key (`.pem` format) used to access the instance.

On every push to `main`, the workflow automatically:
1. Runs the `pytest` test suite across all 26 rules and endpoints.
2. Connects to EC2 via SSH.
3. Pulls latest changes, installs dependencies, and gracefully restarts `prap.service`.

---

## 📡 REST API Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/assessments` | Trigger assessment. Accepts `.zip` upload (`file` key) or JSON `{"project_path": "..."}`. |
| `GET` | `/api/assessments/<id>` | Fetch assessment details, score, rules, and findings. |
| `GET` | `/api/assessments` | List all historical assessments. |
| `DELETE` | `/api/assessments/<id>` | Delete assessment and cascaded findings. |
| `GET` | `/api/findings` | Query findings with optional filters (`status`, `severity`, `category`). |
| `PATCH` | `/api/findings/<id>/status` | Update finding status (`Open`, `In Review`, `Resolved`, `Exception Granted`). |
| `POST` | `/api/exceptions` | Register a Risk Exception (`finding_id`, `owner`, `requested_by`, `reason`, `expiry_date`). |
| `GET` | `/api/exceptions` | List all documented risk exceptions. |
| `GET` | `/api/rules` | Return the catalog of 26 rules. |
| `GET` | `/api/dashboard/stats` | Return aggregated dashboard KPIs and trends. |
| `GET` | `/api/health` | Health probe & SQLite connection test. |

---

## 🛡️ Risk Exception Governance Model

When a finding cannot be resolved prior to a release deadline, PRAP provides a documented governance workflow:
1. Identify the failed rule in the Assessment Report.
2. Click **"Request Risk Exception"**.
3. Specify the **Designated Owner**, **Requested By**, **Business Justification**, and **Expiry Date**.
4. The system updates the finding status to **Exception Granted**, records the expiration timeline, and catalogs it under the Risk Exceptions portal for recurring architectural audits.

---

## 🧪 Running Automated Tests

Run the complete test suite locally:
```bash
pytest -v tests/
```

Test coverage includes:
- Rule YAML schema integrity & 26 rules presence
- Database initialization and cascading CRUD
- In-memory Zip upload pipeline with automatic cleanup
- Risk exception workflow and finding status transitions
- Dashboard analytics aggregation
- All Web UI route templates
