import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from netscan.api.auth import hash_key
from netscan.db import get_session
from netscan.models import ApiKey, IPAddress, IPHistory, IPStatus, ScanJob, Subnet, Webhook
from netscan.scanner.cidr import expand_cidr_hosts, get_subnet_metadata
from netscan.web.session import COOKIE_NAME, create_session_cookie, validate_session_cookie

templates_path = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_path))

web_router = APIRouter(include_in_schema=False)


def _get_current_user(request: Request, session: Session) -> ApiKey | None:
    """Extract and validate the session cookie, returning the ApiKey or None."""
    cookie_val = request.cookies.get(COOKIE_NAME)
    if not cookie_val:
        return None
    key_hash = validate_session_cookie(cookie_val)
    if not key_hash:
        return None
    return session.exec(select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active)).first()


def _require_dashboard_user(request: Request, session: Session) -> ApiKey:
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
    return templates.TemplateResponse(request=request, name="login.html", context={})


@web_router.post("/login")
async def login_submit(request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    api_key = form.get("api_key", "")

    if not api_key:
        return templates.TemplateResponse(request=request, name="login.html", context={"error": "API key is required."})

    key_hash = hash_key(api_key.strip())
    key_rec = session.exec(select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active)).first()
    if not key_rec:
        return templates.TemplateResponse(
            request=request, name="login.html", context={"error": "Invalid or revoked API key."}
        )

    cookie_value = create_session_cookie(api_key.strip())
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        COOKIE_NAME,
        cookie_value,
        max_age=86400 * 7,
        httponly=True,
        samesite="lax",
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
    count: int = 1,
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
