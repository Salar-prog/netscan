# NetScan Manual QA Test Guide

Step-by-step testing guide for QA on a fresh Debian/Ubuntu system.

---

## Prerequisites

### Fresh Debian/Ubuntu Setup

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
sudo apt install -y docker.io docker-compose-v2
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
# Log out and back in for docker group to take effect

# Install curl and jq (for API testing)
sudo apt install -y curl jq

# Install nmap (required by NetScan at runtime)
sudo apt install -y nmap
```

### Verify Prerequisites

```bash
docker --version    # Docker version 24+
curl --version      # curl 7+
jq --version        # jq 1+
nmap --version      # Nmap 7+
```

---

## Step 1: Start the App

### Option A: Docker (Recommended for QA)

```bash
# Pull or build the image
docker build -t netscan:test /home/a/pnpjt/prod/netscan

# Run the container
docker run -d \
  --name netscan \
  -p 8000:8000 \
  -e SECRET_KEY=qa-test-secret-key \
  netscan:test

# Verify it's running
docker ps
curl http://localhost:8000/health
```

Expected:
```json
{
  "status": "healthy",
  "service": "NetScan",
  "version": "0.1.0",
  "checks": {
    "database": "ok",
    "nmap": "ok"
  }
}
```

### Option B: Local Install

```bash
# Install Python 3.10+
sudo apt install -y python3 python3-pip python3-venv

# Clone and install
git clone https://github.com/Salar-prog/netscan.git
cd netscan
pip install -e ".[test]"

# Run
netscan serve --host 0.0.0.0 --port 8000
```

---

## Step 2: Bootstrap API Key

Every API call requires an `X-API-Key` header. Create your first (admin) key:

```bash
curl -X POST http://localhost:8000/api/v1/auth/keys/bootstrap \
  -H "Content-Type: application/json" \
  -d '{"name": "qa-admin-key"}' | jq
```

Expected:
```json
{
  "id": "...",
  "name": "qa-admin-key",
  "prefix": "nsc_...",
  "role": "admin",
  "raw_key": "nsc_...",
  "is_active": true,
  "created_at": "..."
}
```

**Save the `raw_key` value.** It is never shown again.

```bash
# Set it as an env var for convenience
export NSCAN_KEY="nsc_YOUR_KEY_HERE"
```

---

## Step 3: Dashboard Browser Testing

Open http://localhost:8000/ in your browser.

| # | Check | Expected | Pass |
|---|-------|----------|------|
| 3.1 | Page loads | Dark theme, no errors in console | [ ] |
| 3.2 | Header text | "Network Subnets & IP Pools" | [ ] |
| 3.3 | Summary cards | 4 cards: Tracked Subnets, Active IPs, Uncertain, Available | [ ] |
| 3.4 | "Add Subnet CIDR" button | Opens a modal form | [ ] |
| 3.5 | Empty state | No subnets listed yet, clean empty state | [ ] |
| 3.6 | Navigation | Links to Settings, Scans pages work | [ ] |

---

## Step 4: Subnet CRUD

### 4.1 Create a Subnet

```bash
curl -X POST http://localhost:8000/api/v1/subnets \
  -H "X-API-Key: $NSCAN_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "cidr": "192.168.1.0/30",
    "name": "QA Test Subnet",
    "description": "Created during QA testing",
    "scan_interval_minutes": 60,
    "miss_threshold": 3,
    "quarantine_hours": 48
  }' | jq
```

Expected: 201 Created with subnet object including `id` field.

**Save the subnet ID:**
```bash
export SUBNET_ID=$(curl -s http://localhost:8000/api/v1/subnets \
  -H "X-API-Key: $NSCAN_KEY" | jq -r '.[0].id')
```

| # | Check | Expected | Pass |
|---|-------|----------|------|
| 4.1 | Create subnet | 201, returns subnet with ID | [ ] |
| 4.2 | Invalid CIDR | `{"cidr": "999.999.0.0/24"}` returns 400 | [ ] |
| 4.3 | Duplicate CIDR | Same CIDR twice returns 409 | [ ] |

### 4.2 List Subnets

```bash
curl -s http://localhost:8000/api/v1/subnets \
  -H "X-API-Key: $NSCAN_KEY" | jq
```

| # | Check | Expected | Pass |
|---|-------|----------|------|
| 4.4 | List returns array | Array with at least 1 subnet | [ ] |
| 4.5 | Subnet has stats | `stats` object with total/active/uncertain/reserved/available | [ ] |

### 4.3 Get Subnet Details

```bash
curl -s http://localhost:8000/api/v1/subnets/$SUBNET_ID \
  -H "X-API-Key: $NSCAN_KEY" | jq
```

| # | Check | Expected | Pass |
|---|-------|----------|------|
| 4.6 | Returns subnet | Full subnet object with all fields | [ ] |
| 4.7 | Unknown ID | Non-existent UUID returns 404 | [ ] |

### 4.4 Get CIDR Matrix

```bash
curl -s http://localhost:8000/api/v1/subnets/$SUBNET_ID/matrix \
  -H "X-API-Key: $NSCAN_KEY" | jq
```

| # | Check | Expected | Pass |
|---|-------|----------|------|
| 4.8 | Returns IP list | Array of IPs in the subnet (4 IPs for /30) | [ ] |
| 4.9 | IP has status | Each IP has `status` field (AVAILABLE_CANDIDATE, etc.) | [ ] |

### 4.5 Delete Subnet

```bash
curl -X DELETE http://localhost:8000/api/v1/subnets/$SUBNET_ID \
  -H "X-API-Key: $NSCAN_KEY"
```

| # | Check | Expected | Pass |
|---|-------|----------|------|
| 4.10 | Delete returns 200 | Subnet removed | [ ] |
| 4.11 | Get after delete | 404 Not Found | [ ] |

---

## Step 5: IP Operations

Re-create a subnet for IP testing:

```bash
curl -X POST http://localhost:8000/api/v1/subnets \
  -H "X-API-Key: $NSCAN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"cidr": "10.0.0.0/30", "name": "IP Test Subnet"}'

export SUBNET_ID=$(curl -s http://localhost:8000/api/v1/subnets \
  -H "X-API-Key: $NSCAN_KEY" | jq -r '.[0].id')
```

### 5.1 List IPs

```bash
curl -s http://localhost:8000/api/v1/ips \
  -H "X-API-Key: $NSCAN_KEY" | jq
```

| # | Check | Expected | Pass |
|---|-------|----------|------|
| 5.1 | Returns array | Array of IP objects | [ ] |

### 5.2 Filter IPs by Subnet

```bash
curl -s "http://localhost:8000/api/v1/ips?subnet_id=$SUBNET_ID" \
  -H "X-API-Key: $NSCAN_KEY" | jq
```

| # | Check | Expected | Pass |
|---|-------|----------|------|
| 5.2 | Filtered results | Only IPs from the specified subnet | [ ] |

### 5.3 Get Next Available IPs

```bash
curl -s "http://localhost:8000/api/v1/ips/available?subnet_id=$SUBNET_ID&count=2" \
  -H "X-API-Key: $NSCAN_KEY" | jq
```

| # | Check | Expected | Pass |
|---|-------|----------|------|
| 5.3 | Returns 2 IPs | Array with 2 available IPs | [ ] |
| 5.4 | IPs are available | Status is AVAILABLE_CANDIDATE | [ ] |

### 5.4 Reserve an IP

```bash
curl -X PATCH http://localhost:8000/api/v1/ips/10.0.0.1 \
  -H "X-API-Key: $NSCAN_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "is_reserved": true,
    "hostname": "printer.corp",
    "custom_metadata": {"owner": "infra-team", "location": "building-A"}
  }' | jq
```

| # | Check | Expected | Pass |
|---|-------|----------|------|
| 5.5 | Reserve returns 200 | IP status changes to ASSIGNED_RESERVED | [ ] |
| 5.6 | Metadata saved | `custom_metadata` contains the provided data | [ ] |
| 5.7 | Hostname saved | `hostname` is "printer.corp" | [ ] |

### 5.5 Unreserve an IP

```bash
curl -X PATCH http://localhost:8000/api/v1/ips/10.0.0.1 \
  -H "X-API-Key: $NSCAN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"is_reserved": false}' | jq
```

| # | Check | Expected | Pass |
|---|-------|----------|------|
| 5.8 | Unreserve returns 200 | IP status changes back to AVAILABLE_CANDIDATE | [ ] |

### 5.6 Get IP History

```bash
curl -s http://localhost:8000/api/v1/ips/10.0.0.1/history \
  -H "X-API-Key: $NSCAN_KEY" | jq
```

| # | Check | Expected | Pass |
|---|-------|----------|------|
| 5.9 | Returns history | Array with at least 1 event (RESERVED_TOGGLE) | [ ] |
| 5.10 | Event has details | Each event has `event_type`, `old_status`, `new_status` | [ ] |

### 5.7 Unknown IP

```bash
curl -s http://localhost:8000/api/v1/ips/10.99.99.99 \
  -H "X-API-Key: $NSCAN_KEY"
```

| # | Check | Expected | Pass |
|---|-------|----------|------|
| 5.11 | Unknown IP | 404 Not Found | [ ] |

---

## Step 6: Scanning

**Note:** Scanning requires `nmap` installed on the host. In Docker it's pre-installed.

### 6.1 Trigger a Scan

```bash
curl -X POST http://localhost:8000/api/v1/subnets/$SUBNET_ID/scan \
  -H "X-API-Key: $NSCAN_KEY" | jq
```

| # | Check | Expected | Pass |
|---|-------|----------|------|
| 6.1 | Scan triggered | 202 Accepted with scan job ID | [ ] |

### 6.2 Check Scan Jobs

```bash
curl -s http://localhost:8000/api/v1/scans \
  -H "X-API-Key: $NSCAN_KEY" | jq
```

| # | Check | Expected | Pass |
|---|-------|----------|------|
| 6.2 | Returns jobs | Array with at least 1 scan job | [ ] |
| 6.3 | Job has status | Status is QUEUED, RUNNING, COMPLETED, or FAILED | [ ] |

### 6.3 Wait and Re-check

```bash
# Wait 10 seconds for scan to complete
sleep 10

curl -s http://localhost:8000/api/v1/scans \
  -H "X-API-Key: $NSCAN_KEY" | jq '.[0]'
```

| # | Check | Expected | Pass |
|---|-------|----------|------|
| 6.4 | Scan completed | Status is COMPLETED (or FAILED if nmap can't scan the subnet) | [ ] |
| 6.5 | Stats populated | `total_ips`, `active_ips` fields are set | [ ] |

---

## Step 7: Webhooks

### 7.1 Create a Webhook

```bash
curl -X POST http://localhost:8000/api/v1/webhooks \
  -H "X-API-Key: $NSCAN_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "QA Test Webhook",
    "url": "https://httpbin.org/post",
    "events": ["ip.state_changed", "scan.completed"]
  }' | jq
```

| # | Check | Expected | Pass |
|---|-------|----------|------|
| 7.1 | Create webhook | 201 Created with webhook ID | [ ] |
| 7.2 | Secret returned | Response includes `secret` field (shown only once) | [ ] |
| 7.3 | Invalid URL | `{"url": "not-a-url"}` returns 400 | [ ] |

**Save the webhook ID:**
```bash
export WEBHOOK_ID=$(curl -s http://localhost:8000/api/v1/webhooks \
  -H "X-API-Key: $NSCAN_KEY" | jq -r '.[0].id')
```

### 7.2 List Webhooks

```bash
curl -s http://localhost:8000/api/v1/webhooks \
  -H "X-API-Key: $NSCAN_KEY" | jq
```

| # | Check | Expected | Pass |
|---|-------|----------|------|
| 7.4 | Returns webhooks | Array with at least 1 webhook | [ ] |
| 7.5 | Secret hidden | Response does NOT contain `secret` field | [ ] |

### 7.3 Test Webhook

```bash
curl -X POST http://localhost:8000/api/v1/webhooks/$WEBHOOK_ID/test \
  -H "X-API-Key: $NSCAN_KEY" | jq
```

| # | Check | Expected | Pass |
|---|-------|----------|------|
| 7.6 | Test dispatched | 200 OK, test payload sent to URL | [ ] |

### 7.4 Delete Webhook

```bash
curl -X DELETE http://localhost:8000/api/v1/webhooks/$WEBHOOK_ID \
  -H "X-API-Key: $NSCAN_KEY"
```

| # | Check | Expected | Pass |
|---|-------|----------|------|
| 7.7 | Delete returns 200 | Webhook removed | [ ] |

---

## Step 8: Authentication & Roles

### 8.1 Create Read-Only Key

```bash
curl -X POST http://localhost:8000/api/v1/auth/keys \
  -H "X-API-Key: $NSCAN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "readonly-key", "role": "read_only"}' | jq
```

**Save the key:**
```bash
export RO_KEY="nsc_YOUR_READONLY_KEY"
```

### 8.2 Test Read-Only Access

```bash
# Should WORK (read operation)
curl -s http://localhost:8000/api/v1/subnets \
  -H "X-API-Key: $RO_KEY" | jq

# Should FAIL (write operation)
curl -s -X POST http://localhost:8000/api/v1/subnets \
  -H "X-API-Key: $RO_KEY" \
  -H "Content-Type: application/json" \
  -d '{"cidr": "10.99.0.0/24", "name": "Should Fail"}'
```

| # | Check | Expected | Pass |
|---|-------|----------|------|
| 8.1 | Read-only can read | 200 OK | [ ] |
| 8.2 | Read-only can't write | 403 Forbidden | [ ] |

### 8.3 Create Operator Key

```bash
curl -X POST http://localhost:8000/api/v1/auth/keys \
  -H "X-API-Key: $NSCAN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "operator-key", "role": "operator"}' | jq
```

**Save the key:**
```bash
export OP_KEY="nsc_YOUR_OPERATOR_KEY"
```

### 8.4 Test Operator Access

```bash
# Should WORK (write subnets)
curl -s -X POST http://localhost:8000/api/v1/subnets \
  -H "X-API-Key: $OP_KEY" \
  -H "Content-Type: application/json" \
  -d '{"cidr": "10.88.0.0/30", "name": "Operator Subnet"}' | jq

# Should FAIL (manage keys - admin only)
curl -s -X POST http://localhost:8000/api/v1/auth/keys \
  -H "X-API-Key: $OP_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "should-fail", "role": "read_only"}'
```

| # | Check | Expected | Pass |
|---|-------|----------|------|
| 8.3 | Operator can write subnets | 201 Created | [ ] |
| 8.4 | Operator can't manage keys | 403 Forbidden | [ ] |

### 8.5 Bootstrap Only Works Once

```bash
curl -X POST http://localhost:8000/api/v1/auth/keys/bootstrap \
  -H "Content-Type: application/json" \
  -d '{"name": "second-bootstrap"}'
```

| # | Check | Expected | Pass |
|---|-------|----------|------|
| 8.5 | Second bootstrap | 403 "Bootstrap disabled" | [ ] |

### 8.6 Invalid API Key

```bash
curl -s http://localhost:8000/api/v1/subnets \
  -H "X-API-Key: fake-key-12345"
```

| # | Check | Expected | Pass |
|---|-------|----------|------|
| 8.6 | Invalid key | 403 "Invalid or revoked API Key" | [ ] |

### 8.7 Missing API Key

```bash
curl -s http://localhost:8000/api/v1/subnets
```

| # | Check | Expected | Pass |
|---|-------|----------|------|
| 8.7 | No key header | 403 "Not authenticated" | [ ] |

---

## Step 9: Error Cases

| # | Test | Command | Expected | Pass |
|---|------|---------|----------|------|
| 9.1 | Invalid CIDR | `POST /subnets` with `{"cidr": "invalid"}` | 400 | [ ] |
| 9.2 | Missing required field | `POST /subnets` with `{}` | 400 | [ ] |
| 9.3 | Unknown subnet | `GET /subnets/00000000-0000-0000-0000-000000000000` | 404 | [ ] |
| 9.4 | Unknown IP | `GET /ips/999.999.999.999` | 404 | [ ] |
| 9.5 | Rate limiting | Hit any endpoint 120+ times in a minute | 429 | [ ] |
| 9.6 | Method not allowed | `DELETE /health` | 405 | [ ] |

---

## Step 10: Health & System

### 10.1 Health Check

```bash
curl -s http://localhost:8000/health | jq
```

| # | Check | Expected | Pass |
|---|-------|----------|------|
| 10.1 | Health returns OK | `"status": "healthy"` | [ ] |
| 10.2 | Database check | `"database": "ok"` | [ ] |
| 10.3 | Nmap check | `"nmap": "ok"` | [ ] |

### 10.2 Swagger Docs

Open http://localhost:8000/docs in your browser.

| # | Check | Expected | Pass |
|---|-------|----------|------|
| 10.4 | Swagger loads | Interactive API documentation | [ ] |
| 10.5 | Try it out | Can execute API calls from the UI | [ ] |

### 10.3 ReDoc

Open http://localhost:8000/redoc in your browser.

| # | Check | Expected | Pass |
|---|-------|----------|------|
| 10.6 | ReDoc loads | Clean API reference documentation | [ ] |

---

## Step 11: Dashboard UI (Browser)

After creating subnets and IPs via API, check the dashboard:

| # | Check | Expected | Pass |
|---|-------|----------|------|
| 11.1 | Subnets appear | Created subnets listed on dashboard | [ ] |
| 11.2 | Stats updated | Summary cards show correct counts | [ ] |
| 11.3 | Click subnet | Opens CIDR matrix view | [ ] |
| 11.4 | IP grid | Matrix shows IPs with color-coded statuses | [ ] |
| 11.5 | Click IP | Opens IP detail drawer | [ ] |
| 11.6 | Reserve from UI | Toggle reservation in drawer | [ ] |
| 11.7 | Settings page | Webhook management works | [ ] |
| 11.8 | Scans page | Shows scan job history | [ ] |

---

## Quick Smoke Test (Copy-Paste All)

Run this single block to verify core functionality:

```bash
export KEY=$(curl -s -X POST http://localhost:8000/api/v1/auth/keys/bootstrap \
  -H "Content-Type: application/json" \
  -d '{"name": "smoke-test"}' | jq -r '.raw_key')

# Create subnet
SUBNET=$(curl -s -X POST http://localhost:8000/api/v1/subnets \
  -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"cidr": "10.0.0.0/30", "name": "Smoke Test"}' | jq -r '.id')

echo "Subnet ID: $SUBNET"

# List subnets
curl -s -H "X-API-Key: $KEY" http://localhost:8000/api/v1/subnets | jq length

# Get available IPs
curl -s -H "X-API-Key: $KEY" "http://localhost:8000/api/v1/ips/available?subnet_id=$SUBNET&count=2" | jq length

# Reserve an IP
curl -s -X PATCH -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  http://localhost:8000/api/v1/ips/10.0.0.1 \
  -d '{"is_reserved": true, "hostname": "smoke-test"}' | jq .status

# Trigger scan
curl -s -X POST -H "X-API-Key: $KEY" http://localhost:8000/api/v1/subnets/$SUBNET/scan | jq .status

# Create webhook
curl -s -X POST -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  http://localhost:8000/api/v1/webhooks \
  -d '{"name": "smoke", "url": "https://httpbin.org/post"}' | jq .name

# Health
curl -s http://localhost:8000/health | jq .status

echo "=== SMOKE TEST COMPLETE ==="
```

Expected: All commands return valid JSON, no errors.

---

## Cleanup

After testing, remove the container:

```bash
docker stop netscan && docker rm netscan
```

---

## Test Results Summary

| Section | Total | Passed | Failed |
|---------|-------|--------|--------|
| 3. Dashboard Browser | 6 | | |
| 4. Subnet CRUD | 11 | | |
| 5. IP Operations | 11 | | |
| 6. Scanning | 5 | | |
| 7. Webhooks | 7 | | |
| 8. Auth & Roles | 7 | | |
| 9. Error Cases | 6 | | |
| 10. Health & System | 6 | | |
| 11. Dashboard UI | 8 | | |
| **Total** | **67** | | |

**QA Tester:** _________________ **Date:** _________________
