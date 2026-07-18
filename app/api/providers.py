"""Provider controller — HTTP routes for /providers.

Thin layer: parse request, call service, return response.
No encryption, no masking, no DB calls — all of that lives in
app/services/provider_service.py.

Endpoints:
  POST   /providers                 — create
  GET    /providers                 — list
  GET    /providers/{id}            — get one (404 if not yours)
  PUT    /providers/{id}            — partial update
  DELETE /providers/{id}            — remove
  POST   /providers/{id}/validate   — confirm key works against real API
  POST   /providers/{id}/default    — promote to default
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.db.models import User
from app.schemas.provider import (
    ProviderCreate,
    ProviderCreateResponse,
    ProviderResponse,
    ProviderUpdate,
)
from app.services import provider_service

router = APIRouter(prefix="/providers", tags=["providers"])


@router.post(
    "",
    response_model=ProviderCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_provider(
    data: ProviderCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a provider. Response includes the plaintext api_key exactly once."""
    row, plain = await provider_service.create(db, user, data)
    return provider_service.to_response(row, plaintext=plain)


@router.get("", response_model=list[ProviderResponse])
async def list_providers(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all providers owned by the current user."""
    rows = await provider_service.list_for_user(db, user)
    return [provider_service.to_response(r) for r in rows]


@router.get("/{provider_id}", response_model=ProviderResponse)
async def get_provider(
    provider_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get one provider. 404 if not found OR not yours (don't leak existence)."""
    row = await provider_service.get_or_404(db, user, provider_id)
    if row is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="provider not found")
    return provider_service.to_response(row)


@router.put("/{provider_id}", response_model=ProviderResponse)
async def update_provider(
    provider_id: str,
    data: ProviderUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Partial update. Only fields you send are changed."""
    from fastapi import HTTPException
    row = await provider_service.update(db, user, provider_id, data)
    if row is None:
        raise HTTPException(status_code=404, detail="provider not found")
    return provider_service.to_response(row)


@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(
    provider_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove the provider. Idempotent: 404 if not found / not yours."""
    from fastapi import HTTPException
    ok = await provider_service.delete(db, user, provider_id)
    if not ok:
        raise HTTPException(status_code=404, detail="provider not found")
    return None


@router.post("/{provider_id}/validate")
async def validate_provider(
    provider_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Hit the real provider API to confirm the saved key works."""
    from fastapi import HTTPException
    ok = await provider_service.validate_provider(db, user, provider_id)
    if ok is None:
        raise HTTPException(status_code=404, detail="provider not found")
    return {"valid": ok}


@router.post(
    "/{provider_id}/default",
    response_model=ProviderResponse,
)
async def set_default_provider(
    provider_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Promote this provider to default. Clears any prior default."""
    from fastapi import HTTPException
    row = await provider_service.set_default(db, user, provider_id)
    if row is None:
        raise HTTPException(status_code=404, detail="provider not found")
    return provider_service.to_response(row)