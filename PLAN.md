# NetScan: Production-Grade IP Discovery & Availability System
## Architecture & Technical Specification (Refined)

A robust, API-first IP availability tracking and network discovery platform built with **FastAPI**, **SQLModel (SQLite/PostgreSQL)**, **Nmap multi-stage probe engine**, and a **lightweight HTMX/Tailwind web dashboard**.

---

## 1. System Overview & Architecture

`mermaid
flowchart TD
    subgraph Clients & Integrations
        API_Client[External App / CI/CD Automation]
        UI[FastAPI + Jinja2 + HTMX Dashboard]
    end

    subgraph NetScan Control Plane (FastAPI Process)
        Auth[API Key / Bearer Authentication]
        APIRouter[OpenAPI REST Endpoints]
        UIRouter[HTMX Web UI Routes]
        Scheduler[In-Process APScheduler]
        TaskQueue[AsyncIO Background Job Queue]
        WebhookService[Webhook Dispatcher with Payload Snapshots]
    end

    subgraph Storage Layer
        DB[(SQLModel: SQLite / PostgreSQL)]
    end

    subgraph Discovery Engine
        ProbePipeline[Multi-Stage Probe Pipeline]
        NmapRunner[Nmap Runner: Auto-Detect Capabilities]
        HeuristicClassifier[State & Quarantine Classifier]
    end

    API_Client -->|HTTPS + Token| Auth
    UI -->|Session / API| UIRouter
    Auth --> APIRouter
    APIRouter & UIRouter --> DB
    Scheduler -->|Cron Trigger| TaskQueue
    APIRouter & UIRouter -->|Manual Trigger| TaskQueue
    TaskQueue --> ProbePipeline
    ProbePipeline --> NmapRunner
    NmapRunner --> HeuristicClassifier
    HeuristicClassifier -->|State Updates & Audit Trails| DB
    HeuristicClassifier -->|Emit Event + Full Snapshot| WebhookService
    WebhookService -->|HTTP POST| ExternalEndpoints[External Webhooks]
`

---

## 2. Agreed Architectural Decisions

1. **Scanner Privileges & Fallback**:
   * Auto-detects capabilities at runtime.
   * If running with CAP_NET_RAW / root: executes fast L2 ARP sweeps and L4 TCP SYN stealth probes (-sS).
   * If unprivileged: gracefully falls back to unprivileged TCP Connect sweeps (-sT) and ICMP sockets.
2. **Safe Availability & Quarantine Policy**:
   * An unresponsive host enters UNCERTAIN_FIREWALLED.
   * An IP only transitions from UNCERTAIN to AVAILABLE_CANDIDATE after meeting **both** criteria:
     - **Miss Count Threshold**: $ consecutive missed scans (configurable, default: 3).
     - **Quarantine Window**: Elapsed time $\ge T$ hours (configurable, default: 48h) with zero positive probes.
3. **Task Orchestration**:
   * In-process **AsyncIO Task Queue** + **APScheduler** (no Redis or Celery broker required; low memory footprint, single-container deployment).
4. **Database Strategy**:
   * Configurable via DATABASE_URL (SQLite by default for instant local setup/testing, PostgreSQL for production).
5. **Outbound Webhooks**:
   * Delivers HTTP POST events (ip.discovered, ip.state_changed, scan.completed) containing **full IP object snapshots** and signature headers.
6. **Web Dashboard**:
   * Built with **FastAPI + Jinja2 + HTMX + Tailwind CSS** (zero Node.js build step, live polling, interactive CIDR IP matrix grid, and detail drawers).
7. **Needle SLM Integration**:
   * Reserved as an optional Phase 2 plugin for natural language queries and offline banner extraction.

---

## 3. Data Model Schema (SQLModel)

### Subnet (CIDR Pool)
* id: UUID (PK)
* cidr: String (e.g., 192.168.1.0/24, indexed)
* 
ame: String
* description: String
* scan_interval_minutes: Integer (default 60, 0 = manual only)
* miss_threshold: Integer (default 3)
* quarantine_hours: Integer (default 48)
* is_active: Boolean (default True)
* created_at, updated_at: DateTime

### IPAddress
* id: UUID (PK)
* subnet_id: UUID (FK to Subnet)
* ip: String (indexed)
* status: Enum (ACTIVE_DETECTED, AVAILABLE_CANDIDATE, ASSIGNED_RESERVED, UNCERTAIN_FIREWALLED)
* hostname: String (rDNS / NetBIOS)
* mac_address: String (if L2 discovered)
* mac_vendor: String (OUI resolved)
* open_ports: JSON List (e.g., [{port: 80, service: http, state: open}])
* discovery_method: Enum (ARP, ICMP, TCP_SYN, TCP_CONNECT, MANUAL)
* consecutive_misses: Integer (default 0)
* irst_seen_at: DateTime
* last_seen_at: DateTime
* last_scanned_at: DateTime
* custom_metadata: JSON

### ScanJob
* id: UUID (PK)
* subnet_id: UUID (FK)
* status: Enum (QUEUED, RUNNING, COMPLETED, FAILED)
* started_at, completed_at: DateTime
* 	otal_ips: Integer
* ctive_ips: Integer
* uncertain_ips: Integer
* vailable_ips: Integer
* error_message: String
* 	riggered_by: String (SCHEDULE, MANUAL_API, MANUAL_UI)

### IPHistory / AuditLog
* id: UUID (PK)
* ip_address_id: UUID (FK)
* event_type: Enum (DISCOVERED, STATE_CHANGE, PORT_CHANGE, RESERVED_TOGGLE)
* old_status: String
* 
ew_status: String
* probe_details: JSON
* 	imestamp: DateTime

### Webhook
* id: UUID (PK)
* url: String
* secret: String
* events: JSON List
* is_active: Boolean
* created_at: DateTime

### ApiKey
* id: UUID (PK)
* 
ame: String
* key_hash: String (indexed)
* prefix: String
* ole: Enum (dmin, operator, ead_only)
* last_used_at, created_at: DateTime

---

## 4. API Endpoints Specification

### Authentication & Keys
* POST /api/v1/auth/keys: Generate new API key
* GET /api/v1/auth/keys: List active keys
* DELETE /api/v1/auth/keys/{id}: Revoke key

### Subnets & Pools
* GET /api/v1/subnets: List all tracked subnets with summary stats
* POST /api/v1/subnets: Add new subnet CIDR
* GET /api/v1/subnets/{id}: Get subnet details
* GET /api/v1/subnets/{id}/matrix: Get visual tile grid of all IPs
* POST /api/v1/subnets/{id}/scan: Trigger immediate scan job

### IP Availability & Inspection
* GET /api/v1/ips: Search/filter IPs (by subnet, status, hostname, ports)
* GET /api/v1/ips/available: Retrieve next $ available IPs for provisioning
* GET /api/v1/ips/{ip}: Inspect single IP details
* PATCH /api/v1/ips/{ip}: Mark reserved / assign metadata
* GET /api/v1/ips/{ip}/history: Audit timeline of status & probe changes

### Scans & Webhooks
* GET /api/v1/scans: List scan jobs
* GET /api/v1/scans/{id}: Inspect scan job progress / results
* GET /api/v1/webhooks: List webhooks
* POST /api/v1/webhooks: Register webhook
* POST /api/v1/webhooks/{id}/test: Dispatch test payload

---

## 5. Phased Implementation Steps

* **Phase 1: Foundation & Discovery Engine**
  * Project structure, settings (pydantic-settings), SQLModel schemas, and DB session manager.
  * Async Nmap execution wrapper with capability detection and L2/L3/L4 multi-probe parsing.
  * Safe Heuristic Classifier implementing miss counts & quarantine duration rules.
* **Phase 2: API, Scheduler & Webhooks**
  * API Key authentication middleware and OpenAPI endpoints.
  * In-process background scan job runner and APScheduler integration.
  * Outbound webhook dispatcher with snapshot payloads.
* **Phase 3: HTMX/Tailwind Dashboard**
  * Jinja2 templates with HTMX for live scan progress polling, CIDR visual grid, and IP inspector drawer.
  * CSV/JSON export functionality.
