import uuid
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select
from netscan.api.auth import generate_api_key, get_current_api_key, require_role
from netscan.db import get_session
from netscan.models import ApiKey, Role

router = APIRouter(prefix="/auth/keys", tags=["API Keys"])


class ApiKeyCreate(BaseModel):
    name: str
    role: Role = Role.OPERATOR


class ApiKeyResponse(BaseModel):
    id: uuid.UUID
    name: str
    prefix: str
    role: Role
    is_active: bool
    last_used_at: Optional[datetime]
    created_at: datetime


@router.get("", response_model=List[ApiKeyResponse])
def list_keys(
    session: Session = Depends(get_session),
    current_user=Depends(get_current_api_key),
):
    return session.exec(select(ApiKey)).all()


@router.post("", status_code=status.HTTP_201_CREATED)
def create_api_key(
    payload: ApiKeyCreate,
    session: Session = Depends(get_session),
    current_user=Depends(require_role(Role.ADMIN)),
):
    raw_key, key_hash, prefix = generate_api_key()
    api_key_rec = ApiKey(
        name=payload.name,
        key_hash=key_hash,
        prefix=prefix,
        role=payload.role,
        is_active=True,
    )
    session.add(api_key_rec)
    session.commit()
    session.refresh(api_key_rec)

    return {
        "id": api_key_rec.id,
        "name": api_key_rec.name,
        "prefix": api_key_rec.prefix,
        "role": api_key_rec.role,
        "raw_key": raw_key,  # Returned only once upon creation
        "message": "Store this key safely! It will never be shown again.",
    }


@router.post("/bootstrap", status_code=status.HTTP_201_CREATED)
def bootstrap_first_key(
    payload: ApiKeyCreate,
    session: Session = Depends(get_session),
):
    """Create the first API key when no keys exist. Disabled once any key exists."""
    existing = session.exec(select(ApiKey)).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bootstrap disabled: API keys already exist. Use POST /api/v1/auth/keys with a valid key.",
        )
    raw_key, key_hash, prefix = generate_api_key()
    api_key_rec = ApiKey(
        name=payload.name,
        key_hash=key_hash,
        prefix=prefix,
        role=Role.ADMIN,
        is_active=True,
    )
    session.add(api_key_rec)
    session.commit()
    session.refresh(api_key_rec)
    return {
        "id": api_key_rec.id,
        "name": api_key_rec.name,
        "prefix": api_key_rec.prefix,
        "role": api_key_rec.role,
        "raw_key": raw_key,
        "message": "Store this key safely! It will never be shown again. This is the bootstrap key (role: admin).",
    }


@router.delete("/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_key(
    key_id: uuid.UUID,
    session: Session = Depends(get_session),
    current_user=Depends(require_role(Role.ADMIN)),
):
    rec = session.get(ApiKey, key_id)
    if not rec:
        raise HTTPException(status_code=404, detail="API Key not found")
    session.delete(rec)
    session.commit()
    return None
