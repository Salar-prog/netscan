import asyncio
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlmodel import Session, select

from netscan.api.auth import hash_key
from netscan.config import settings
from netscan.db import get_session
from netscan.webhooks_check import is_url_blocked
from netscan.models import (
    ApiKey,
    EventType,
    IPAddress,
    IPHistory,
    IPStatus,
    Role,
    ScanJob,
    ScanStatus,
    Subnet,
    TriggerType,
    Webhook,
    utc_now,
)
from netscan.scanner.cidr import expand_cidr_hosts, get_subnet_metadata, validate_and_normalize_cidr
from netscan.services.scan_service import _scan_tasks, _track_scan_task, scan_service
from netscan.services.scheduler_service import scheduler
from netscan.web.session import COOKIE_NAME, create_session_cookie, validate_session_cookie

templates_path = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_path))

web_router = APIRouter(include_in_schema=False)


def _get_current_user(request: Request, session: Session) -> ApiKey | dict | None:
    """Extract and validate the session cookie, returning ApiKey, LDAP info dict, or None."""
    cookie_val = request.cookies.get(COOKIE_NAME)
    if not cookie_val:
        return None
    auth_info = validate_session_cookie(cookie_val)
    if not auth_info:
        return None
    if auth_info["type"] == "ldap":
        return {"type": "ldap", "username": auth_info["username"], "role": auth_info["role"]}
    key_rec = session.exec(select(ApiKey).where(ApiKey.key_hash == auth_info["key_hash"], ApiKey.is_active)).first()
    return key_rec


def _require_dashboard_user(request: Request, session: Session) -> ApiKey | dict:
    """Return the authenticated user or redirect to /login."""
    user = _get_current_user(request, session)
    if not user:
        if request.headers.get("hx-request"):
            raise HTTPException(
                status_code=401,
                headers={"HX-Redirect": "/login"},
            )
        raise HTTPException(status_code=307, headers={"Location": "/login"})
    return user


# ── Login / Logout ──────────────────────────────────────────────────────────


@web_router.get("/login", response_class=HTMLResponse)
def login_view(request: Request):
    return templates.TemplateResponse(
        request=request, name="login.html", context={"ldap_enabled": settings.LDAP_ENABLED}
    )


@web_router.post("/login")
async def login_submit(request: Request, session: Session = Depends(get_session)):
    form = await request.form()

    if settings.LDAP_ENABLED:
        return await _login_ldap(form, request)

    return await _login_api_key(form, request, session)


async def _login_ldap(form: dict, request: Request):
    from netscan.auth.ldap import ldap_authenticate, map_groups_to_role
    from netscan.web.session import create_ldap_session_cookie

    username = form.get("username", "").strip()
    password = form.get("password", "")

    if not username or not password:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"ldap_enabled": True, "error": "Username and password are required."},
        )

    result = await ldap_authenticate(username, password)
    if not result:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={"ldap_enabled": True, "error": "Invalid credentials or LDAP unavailable."},
        )

    role = map_groups_to_role(result["groups"])
    cookie_value = create_ldap_session_cookie(result["username"], role.value)
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        COOKIE_NAME, cookie_value, max_age=86400 * 7, httponly=True, samesite="lax", secure=not settings.DEBUG, path="/"
    )
    return response


async def _login_api_key(form: dict, request: Request, session: Session):
    api_key = form.get("api_key", "")

    if not api_key:
        return templates.TemplateResponse(
            request=request, name="login.html", context={"ldap_enabled": False, "error": "API key is required."}
        )

    key_hash = hash_key(api_key.strip())
    key_rec = session.exec(select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active)).first()
    if not key_rec:
        return templates.TemplateResponse(
            request=request, name="login.html", context={"ldap_enabled": False, "error": "Invalid or revoked API key."}
        )

    cookie_value = create_session_cookie(api_key.strip())
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        COOKIE_NAME,
        cookie_value,
        max_age=86400 * 7,
        httponly=True,
        samesite="lax",
        secure=not settings.DEBUG,
        path="/",
    )
    return response


@web_router.post("/logout")
def logout_view():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(COOKIE_NAME, path="/")
    return response


# ── Dashboard Routes (cookie-protected) ─────────────────────────────────────


@web_router.get("/", response_class=HTMLResponse)
def index_view(request: Request, session: Session = Depends(get_session)):
    _require_dashboard_user(request, session)

    subnets = session.exec(select(Subnet)).all()
    subnet_cards = []

    total_active = 0
    total_uncertain = 0
    total_available = 0

    for s in subnets:
        total_ips = len(expand_cidr_hosts(s.cidr))
        active_count = len(
            session.exec(
                select(IPAddress).where(IPAddress.subnet_id == s.id, IPAddress.status == IPStatus.ACTIVE_DETECTED)
            ).all()
        )
        uncertain_count = len(
            session.exec(
                select(IPAddress).where(IPAddress.subnet_id == s.id, IPAddress.status == IPStatus.UNCERTAIN_FIREWALLED)
            ).all()
        )
        reserved_count = len(
            session.exec(
                select(IPAddress).where(IPAddress.subnet_id == s.id, IPAddress.status == IPStatus.ASSIGNED_RESERVED)
            ).all()
        )
        available_count = max(0, total_ips - (active_count + uncertain_count + reserved_count))

        total_active += active_count
        total_uncertain += uncertain_count
        total_available += available_count

        meta = get_subnet_metadata(s.cidr)
        subnet_cards.append(
            {
                "id": s.id,
                "cidr": s.cidr,
                "name": s.name,
                "description": s.description,
                "scan_interval_minutes": s.scan_interval_minutes,
                "miss_threshold": s.miss_threshold,
                "quarantine_hours": s.quarantine_hours,
                "metadata": meta,
                "stats": {
                    "total": total_ips,
                    "active": active_count,
                    "uncertain": uncertain_count,
                    "reserved": reserved_count,
                    "available": available_count,
                },
            }
        )

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "active_page": "subnets",
            "subnets": subnet_cards,
            "total_subnets": len(subnets),
            "total_active_ips": total_active,
            "total_uncertain_ips": total_uncertain,
            "total_available_ips": total_available,
        },
    )


@web_router.get("/subnets/{subnet_id}/matrix", response_class=HTMLResponse)
def matrix_view(subnet_id: uuid.UUID, request: Request, session: Session = Depends(get_session)):
    _require_dashboard_user(request, session)

    subnet = session.get(Subnet, subnet_id)
    if not subnet:
        raise HTTPException(status_code=404, detail="Subnet not found")

    all_hosts = expand_cidr_hosts(subnet.cidr)
    existing_ips = session.exec(select(IPAddress).where(IPAddress.subnet_id == subnet.id)).all()
    ip_map = {ip_rec.ip: ip_rec for ip_rec in existing_ips}

    matrix = []
    for host_ip in all_hosts:
        rec = ip_map.get(host_ip)
        if rec:
            matrix.append(
                {
                    "ip": host_ip,
                    "status": rec.status.value,
                    "hostname": rec.hostname,
                }
            )
        else:
            matrix.append(
                {
                    "ip": host_ip,
                    "status": IPStatus.AVAILABLE_CANDIDATE.value,
                    "hostname": None,
                }
            )

    return templates.TemplateResponse(
        request=request,
        name="matrix.html",
        context={
            "active_page": "subnets",
            "subnet": subnet,
            "total_hosts": len(all_hosts),
            "matrix": matrix,
        },
    )


@web_router.get("/web/ips/{ip_address}/drawer", response_class=HTMLResponse)
def ip_drawer_partial(ip_address: str, request: Request, session: Session = Depends(get_session)):
    _require_dashboard_user(request, session)

    rec = session.exec(select(IPAddress).where(IPAddress.ip == ip_address.strip())).first()
    if not rec:
        raise HTTPException(status_code=404, detail=f"IP '{ip_address}' not tracked yet.")

    history = session.exec(
        select(IPHistory).where(IPHistory.ip_address_id == rec.id).order_by(IPHistory.timestamp.desc())
    ).all()

    return templates.TemplateResponse(
        request=request,
        name="drawer.html",
        context={
            "ip": rec,
            "history": history,
        },
    )


@web_router.get("/provision", response_class=HTMLResponse)
def provision_view(request: Request, session: Session = Depends(get_session)):
    _require_dashboard_user(request, session)

    subnets = session.exec(select(Subnet)).all()
    subnet_cards = []
    for s in subnets:
        total_ips = len(expand_cidr_hosts(s.cidr))
        unavailable = len(
            session.exec(
                select(IPAddress).where(
                    IPAddress.subnet_id == s.id,
                    IPAddress.status.in_(
                        [
                            IPStatus.ACTIVE_DETECTED,
                            IPStatus.ASSIGNED_RESERVED,
                            IPStatus.UNCERTAIN_FIREWALLED,
                        ]
                    ),
                )
            ).all()
        )
        subnet_cards.append(
            {
                "id": s.id,
                "cidr": s.cidr,
                "name": s.name,
                "stats": {"available": max(0, total_ips - unavailable)},
            }
        )

    return templates.TemplateResponse(
        request=request,
        name="provision.html",
        context={
            "active_page": "provision",
            "subnets": subnet_cards,
        },
    )


@web_router.get("/web/ips/available", response_class=JSONResponse)
def web_available_ips(
    subnet_id: str,
    count: int = Query(default=1, le=50),
    request: Request = None,
    session: Session = Depends(get_session),
):
    """Server-side available IPs endpoint for the provision page."""
    _require_dashboard_user(request, session)

    try:
        sid = uuid.UUID(subnet_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid subnet_id")
    subnet = session.get(Subnet, sid)
    if not subnet:
        raise HTTPException(status_code=404, detail="Subnet not found")

    all_hosts = expand_cidr_hosts(subnet.cidr)
    unavailable_query = select(IPAddress).where(
        IPAddress.subnet_id == subnet.id,
        IPAddress.status.in_([IPStatus.ACTIVE_DETECTED, IPStatus.ASSIGNED_RESERVED, IPStatus.UNCERTAIN_FIREWALLED]),
    )
    unavailable_ips = {rec.ip for rec in session.exec(unavailable_query).all()}

    available = [h for h in all_hosts if h not in unavailable_ips][:count]
    return {
        "subnet_id": str(subnet.id),
        "cidr": subnet.cidr,
        "requested_count": count,
        "available_ips": available,
        "count_returned": len(available),
    }


@web_router.get("/scans", response_class=HTMLResponse)
def scans_view(request: Request, session: Session = Depends(get_session)):
    _require_dashboard_user(request, session)

    scans = session.exec(select(ScanJob).order_by(ScanJob.created_at.desc()).limit(100)).all()
    return templates.TemplateResponse(
        request=request,
        name="scans.html",
        context={
            "active_page": "scans",
            "scans": scans,
            "str": str,
        },
    )


@web_router.get("/settings", response_class=HTMLResponse)
def settings_view(request: Request, session: Session = Depends(get_session)):
    _require_dashboard_user(request, session)

    keys = session.exec(select(ApiKey)).all()
    webhooks = session.exec(select(Webhook)).all()
    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={
            "active_page": "settings",
            "keys": keys,
            "webhooks": webhooks,
        },
    )


# ── Role helpers ─────────────────────────────────────────────────────────────


def _get_user_role(user: ApiKey | dict) -> Role:
    if isinstance(user, dict):
        return Role(user["role"])
    return user.role


def _require_role(user: ApiKey | dict, *allowed: Role):
    role = _get_user_role(user)
    if role not in allowed:
        raise HTTPException(status_code=403, detail=f"Requires role: {', '.join(r.value for r in allowed)}")


# ── Proxy Routes (cookie-protected, fix broken HTMX writes) ─────────────────


class SubnetCreate(BaseModel):
    cidr: str
    name: str


class WebhookCreate(BaseModel):
    name: str
    url: str
    events: list[str] = ["ip.state_changed", "scan.completed"]


class IPReservationUpdate(BaseModel):
    is_reserved: bool
    hostname: str | None = None


@web_router.post("/web/subnets")
def web_create_subnet(request: Request, payload: SubnetCreate, session: Session = Depends(get_session)):
    user = _require_dashboard_user(request, session)
    _require_role(user, Role.ADMIN, Role.OPERATOR)

    try:
        norm_cidr = validate_and_normalize_cidr(payload.cidr)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    existing = session.exec(select(Subnet).where(Subnet.cidr == norm_cidr)).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Subnet '{norm_cidr}' already exists.")

    subnet = Subnet(cidr=norm_cidr, name=payload.name)
    session.add(subnet)
    session.commit()
    session.refresh(subnet)
    scheduler.update_subnet_job(subnet)

    if request.headers.get("hx-request"):
        return RedirectResponse(url="/", status_code=303)
    return RedirectResponse(url="/", status_code=303)


@web_router.post("/web/subnets/{subnet_id}/scan")
def web_trigger_scan(subnet_id: uuid.UUID, request: Request, session: Session = Depends(get_session)):
    user = _require_dashboard_user(request, session)
    _require_role(user, Role.ADMIN, Role.OPERATOR)

    subnet = session.get(Subnet, subnet_id)
    if not subnet:
        raise HTTPException(status_code=404, detail="Subnet not found")

    active_job = session.exec(
        select(ScanJob).where(
            ScanJob.subnet_id == subnet.id,
            ScanJob.status.in_([ScanStatus.QUEUED, ScanStatus.RUNNING]),
        )
    ).first()
    if active_job:
        raise HTTPException(status_code=409, detail="Scan already in progress.")

    job = ScanJob(subnet_id=subnet.id, status=ScanStatus.QUEUED, triggered_by=TriggerType.MANUAL_API)
    session.add(job)
    session.commit()
    session.refresh(job)

    task = asyncio.create_task(scan_service.execute_scan(job.id))
    task.add_done_callback(_track_scan_task)
    _scan_tasks.add(task)

    if request.headers.get("hx-request"):
        return JSONResponse({"message": "Scan queued", "scan_job_id": str(job.id)})
    return RedirectResponse(url=f"/subnets/{subnet_id}/matrix", status_code=303)


@web_router.post("/web/auth/keys")
def web_create_key(request: Request, session: Session = Depends(get_session)):
    user = _require_dashboard_user(request, session)
    _require_role(user, Role.ADMIN)

    from netscan.api.auth import generate_api_key

    raw_key, key_hash, prefix = generate_api_key()
    api_key_rec = ApiKey(name="dashboard-key", key_hash=key_hash, prefix=prefix, role=Role.OPERATOR, is_active=True)
    session.add(api_key_rec)
    session.commit()
    session.refresh(api_key_rec)

    if request.headers.get("hx-request"):
        return JSONResponse({"raw_key": raw_key, "prefix": prefix, "message": "Key created. Store it — shown once."})
    return RedirectResponse(url="/settings", status_code=303)


@web_router.delete("/web/auth/keys/{key_id}")
def web_revoke_key(key_id: uuid.UUID, request: Request, session: Session = Depends(get_session)):
    user = _require_dashboard_user(request, session)
    _require_role(user, Role.ADMIN)

    rec = session.get(ApiKey, key_id)
    if not rec:
        raise HTTPException(status_code=404, detail="API Key not found")
    session.delete(rec)
    session.commit()

    if request.headers.get("hx-request"):
        return JSONResponse({"message": "Key revoked"})
    return RedirectResponse(url="/settings", status_code=303)


@web_router.post("/web/webhooks")
def web_create_webhook(request: Request, payload: WebhookCreate, session: Session = Depends(get_session)):
    user = _require_dashboard_user(request, session)
    _require_role(user, Role.ADMIN, Role.OPERATOR)

    if is_url_blocked(str(payload.url)):
        raise HTTPException(status_code=400, detail="Webhook URL targets a blocked private/metadata address")

    import secrets as _secrets

    raw_secret = _secrets.token_urlsafe(32)
    wh = Webhook(name=payload.name, url=payload.url, secret=raw_secret, events=payload.events, is_active=True)
    session.add(wh)
    session.commit()
    session.refresh(wh)

    if request.headers.get("hx-request"):
        return JSONResponse({"secret": raw_secret, "message": "Webhook created. Store the secret — shown once."})
    return RedirectResponse(url="/settings", status_code=303)


@web_router.delete("/web/webhooks/{webhook_id}")
def web_delete_webhook(webhook_id: uuid.UUID, request: Request, session: Session = Depends(get_session)):
    user = _require_dashboard_user(request, session)
    _require_role(user, Role.ADMIN, Role.OPERATOR)

    wh = session.get(Webhook, webhook_id)
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")
    session.delete(wh)
    session.commit()

    if request.headers.get("hx-request"):
        return JSONResponse({"message": "Webhook deleted"})
    return RedirectResponse(url="/settings", status_code=303)


@web_router.post("/web/webhooks/{webhook_id}/test")
async def web_test_webhook(webhook_id: uuid.UUID, request: Request, session: Session = Depends(get_session)):
    user = _require_dashboard_user(request, session)
    _require_role(user, Role.ADMIN, Role.OPERATOR)

    from netscan.services.webhook_service import WebhookDispatcher

    wh = session.get(Webhook, webhook_id)
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")

    test_data = {"test": True, "message": "NetScan test webhook delivery"}
    await WebhookDispatcher.dispatch_event_to("webhook.test", test_data, wh, session)

    if request.headers.get("hx-request"):
        return JSONResponse({"message": f"Test payload dispatched to {wh.url}"})
    return RedirectResponse(url="/settings", status_code=303)


@web_router.patch("/web/ips/{ip_address}")
def web_update_ip(
    ip_address: str, request: Request, payload: IPReservationUpdate, session: Session = Depends(get_session)
):
    user = _require_dashboard_user(request, session)
    _require_role(user, Role.ADMIN, Role.OPERATOR)

    rec = session.exec(select(IPAddress).where(IPAddress.ip == ip_address.strip())).first()
    if not rec:
        raise HTTPException(status_code=404, detail=f"IP '{ip_address}' not found.")

    old_status = rec.status
    now = utc_now()

    if payload.is_reserved:
        rec.status = IPStatus.ASSIGNED_RESERVED
    elif rec.status == IPStatus.ASSIGNED_RESERVED:
        rec.status = IPStatus.AVAILABLE_CANDIDATE

    if payload.hostname is not None:
        rec.hostname = payload.hostname

    rec.updated_at = now
    session.add(rec)

    if old_status != rec.status:
        history = IPHistory(
            ip_address_id=rec.id,
            event_type=EventType.RESERVED_TOGGLE,
            old_status=old_status.value,
            new_status=rec.status.value,
            probe_details={"updated_by": "dashboard_user"},
            timestamp=now,
        )
        session.add(history)

    session.commit()
    session.refresh(rec)

    if request.headers.get("hx-request"):
        return JSONResponse({"status": rec.status.value, "ip": rec.ip})
    return RedirectResponse(url="/", status_code=303)
