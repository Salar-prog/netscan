# Production-Grade IP Discovery & Availability System (NetScan)

A robust, API-first IP availability tracking and network discovery platform built with **FastAPI**, **PostgreSQL/SQLModel**, **Nmap multi-stage probe engine**, and a **modern web dashboard**.

---

## 1. System Overview & Architecture

The system reconciles real-time active network observation with managed IP pool state, categorizing addresses into explicit, safe states without making dangerous assumptions.

`mermaid
flowchart TD
    subgraph Client & Integration
        API_Client[External App / CI/CD / Automation]
        UI[Web Dashboard SPA]
    end

    subgraph Core Control Plane (FastAPI)
        Auth[API Key / Bearer Auth]
        Router[REST API & OpenAPI Layer]
        Scheduler[Scan Scheduler / Background Worker]
        WebhookService[Webhook Dispatcher]
    end

    subgraph Storage Layer
        DB[(PostgreSQL / SQLite)]
    end

    subgraph Discovery Engine
        ProbePipeline[Multi-Stage Probe Pipeline]
        NmapRunner[Nmap & ARP/ICMP/TCP Runner]
        HeuristicClassifier[State & Confidence Classifier]
    end

    API_Client & UI -->|HTTPS + Token| Auth
    Auth --> Router
    Router --> DB
    Scheduler -->|Trigger Run| ProbePipeline
    Router -->|Manual Trigger| ProbePipeline
    ProbePipeline --> NmapRunner
    NmapRunner --> HeuristicClassifier
    HeuristicClassifier -->|State Updates & Audit Trails| DB
    HeuristicClassifier -->|Emit Events| WebhookService
    WebhookService -->|POST Payload| ExternalWebhooks[External Systems]
`

---

## 2. Multi-Stage Discovery & Safe State Classification

Standard ping tools fail because firewalls drop ICMP, causing systems to falsely label active servers as free/available. NetScan avoids this via a multi-probe confidence pipeline:

### Probe Pipeline
1. **L2 Probing (Local Subnets)**: ARP request / neighbor cache inspection (yields 100% confidence + MAC address & vendor).
2. **L3 Probing (ICMP Sweeps)**: ICMP Echo (-PE) + Timestamp (-PP).
3. **L4 Probing (Targeted TCP Syn Sweeps)**: Sweeps top standard ports (80, 443, 22, 445, 3389, 8080, 8443, 53).
4. **Resolution**: Reverse DNS (PTR query) and hostname extraction.

### State Machine Heuristics
* ACTIVE_DETECTED: Responded to ARP, ICMP, or any TCP SYN probe.
* ASSIGNED_RESERVED: Manually designated as reserved or assigned in IPAM, regardless of whether it responds.
* UNCERTAIN_FIREWALLED: Closed/filtered TCP behavior or historically detected recently, but currently unresponsive to ping. **Never marked as free**.
* AVAILABLE_CANDIDATE: Zero responses across all probes for **$ consecutive scan runs** (configurable, default 3) over a defined quarantine retention window.

---

## 3. Database Schema (SQLModel / SQLAlchemy)

### Key Entities
* **Subnet / IPPool**:
  * id, cidr (e.g., 192.168.1.0/24), 
ame, description, scan_interval_minutes, is_active, created_at, updated_at.
* **IPAddress**:
  * id, subnet_id, ip (indexed), status (ACTIVE_DETECTED, AVAILABLE_CANDIDATE, ASSIGNED_RESERVED, UNCERTAIN_FIREWALLED).
  * hostname, mac_address, mac_vendor, open_ports (JSON), discovery_method (ARP, ICMP, TCP_SYN, MANUAL).
  * irst_seen_at, last_seen_at, last_scanned_at, consecutive_misses, custom_metadata (JSON).
* **ScanJob**:
  * id, subnet_id, status (QUEUED, RUNNING, COMPLETED, FAILED), started_at, completed_at, 	otal_ips, detected_ips, error_message, 	riggered_by.
* **AuditLog / IPHistory**:
  * id, ip_address_id, event_type (STATE_CHANGE, PROBE_DETECTED, PORT_CHANGE), old_state, 
ew_state, aw_probe_data (JSON), 	imestamp.
* **Webhook**:
  * id, url, secret, events (e.g., [ip.state_changed, scan.completed]), is_active, created_at.
* **ApiKey**:
  * id, 
ame, key_hash, prefix, ole (dmin, ead_write, ead_only), last_used_at, created_at.

---

## 4. API-First Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| POST | /api/v1/auth/tokens | Manage API tokens |
| GET/POST | /api/v1/subnets | List, create, and configure CIDR subnets |
| GET | /api/v1/subnets/{id}/matrix | Get visual matrix of all IPs in a subnet with statuses |
| POST | /api/v1/subnets/{id}/scan | Trigger immediate scan on a subnet |
| GET | /api/v1/ips | Query IPs with filters (status, subnet, hostname, min_last_seen) |
| GET | /api/v1/ips/available | Get next available IP(s) in a pool for automated provisioning |
| GET/PATCH| /api/v1/ips/{ip} | Inspect single IP details, update reserved status or custom metadata |
| GET | /api/v1/ips/{ip}/history | Historical timeline and audit events for an address |
| GET/POST | /api/v1/webhooks | Register and manage outbound webhook endpoints |
| GET | /api/v1/scans | List historical and active scan jobs |

---

## 5. Web Dashboard (Integrated UI)

A modern, responsive dashboard sharing the exact same REST API:
1. **Subnet IP Matrix Grid**: Interactive tile grid representing CIDR blocks with live color coding (Active = Green, Reserved = Blue, Uncertain = Amber, Available = Slate).
2. **IP Inspector Drawer**: Detailed view showing MAC address, vendor, open ports, reverse DNS, and chronological audit history.
3. **Quick Provision / Available Finder**: Find next available IP widget with copy-to-clipboard and reservation toggle.
4. **Scan Job Monitor**: Real-time progress bar for active scans and past run logs.
5. **Webhook & API Key Manager**: UI to generate scoped tokens and test webhook payloads.

---

## 6. Implementation Roadmap

### Phase 1: Core Foundation & Multi-Probe Discovery
* Scaffolding, dependency configuration (astapi, sqlmodel, uvicorn, pydantic, pscheduler, httpx).
* Nmap multi-probe async wrapper (L2 ARP, L3 ICMP, L4 TCP SYN probes).
* Heuristic classifier evaluating confidence levels and state transitions.

### Phase 2: Central API, Workers & Webhooks
* Token authentication & RBAC.
* Full REST API for Subnets, IP allocation, scanning triggers, and audit logs.
* Background scan job runner and webhook event dispatcher.

### Phase 3: Web Dashboard & Integration Polish
* Modern Single Page Application (SPA) dashboard.
* JSON/CSV export, interactive OpenAPI docs, and end-to-end testing.
