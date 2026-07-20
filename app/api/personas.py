"""Persona controller — HTTP routes for /personas.

Thin layer: parse request, call service, return response.
No FK validation, no DB calls — all of that lives in
app/services/persona_service.py.

Endpoints:
  POST   /personas          — create
  GET    /personas          — list
  GET    /personas/{id}     — get one (404 if not yours)
  PUT    /personas/{id}     — partial update
  DELETE /personas/{id}     — remove (204 on success, 404 on repeat)
"""

import fitz
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.logging import get_logger
from app.db.models import User
from app.repositories import persona_repo
from app.schemas.persona import PersonaCreate, PersonaResponse, PersonaUpdate
from app.services import persona_service

log = get_logger("api.personas")

router = APIRouter(prefix="/personas", tags=["personas"])


@router.post(
    "",
    response_model=PersonaResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_persona(
    data: PersonaCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a persona. model_override (if provided) must be your own provider."""
    from fastapi import HTTPException
    try:
        row = await persona_service.create(db, user, data)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return persona_service.to_response(row)


@router.get("", response_model=list[PersonaResponse])
async def list_personas(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all personas owned by the current user, newest first."""
    rows = await persona_service.list_for_user(db, user)
    return [persona_service.to_response(r) for r in rows]


@router.get("/{persona_id}", response_model=PersonaResponse)
async def get_persona(
    persona_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get one persona. 404 if not found OR not yours (don't leak existence)."""
    from fastapi import HTTPException
    row = await persona_service.get_or_404(db, user, persona_id)
    if row is None:
        raise HTTPException(status_code=404, detail="persona not found")
    return persona_service.to_response(row)


@router.put("/{persona_id}", response_model=PersonaResponse)
async def update_persona(
    persona_id: str,
    data: PersonaUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Partial update. Only fields you send are changed."""
    from fastapi import HTTPException
    row = await persona_service.update(db, user, persona_id, data)
    if row is None:
        raise HTTPException(status_code=404, detail="persona not found")
    return persona_service.to_response(row)


@router.post("/knowledge/extract")
async def extract_knowledge(
    file: UploadFile = File(...),
):
    """Extract text from a PDF and return it. Does not save — caller fills the form."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="only PDF files are accepted")

    try:
        contents = await file.read()
        doc = fitz.open(stream=contents, filetype="pdf")
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
    except Exception as exc:
        log.error("pdf_extract_failed", error=str(exc))
        raise HTTPException(status_code=422, detail="failed to extract text from PDF")

    text = text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="PDF appears to contain no extractable text")

    log.info("pdf_extracted", filename=file.filename, chars=len(text))
    return {"text": text}


@router.post("/{persona_id}/knowledge/upload", response_model=PersonaResponse)
async def upload_knowledge(
    persona_id: str,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a PDF to extract text and store directly as the persona's knowledge base."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="only PDF files are accepted")

    row = await persona_service.get_or_404(db, user, persona_id)
    if row is None:
        raise HTTPException(status_code=404, detail="persona not found")

    try:
        contents = await file.read()
        doc = fitz.open(stream=contents, filetype="pdf")
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
    except Exception as exc:
        log.error("pdf_extract_failed", persona_id=persona_id, error=str(exc))
        raise HTTPException(status_code=422, detail="failed to extract text from PDF")

    text = text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="PDF appears to contain no extractable text")

    updated = await persona_repo.update_persona(db, persona_id, {"knowledge_base": text})
    log.info("knowledge_uploaded", persona_id=persona_id, chars=len(text))
    return persona_service.to_response(updated)


@router.delete("/{persona_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_persona(
    persona_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove the persona. Idempotent: 404 if not found / not yours."""
    from fastapi import HTTPException
    ok = await persona_service.delete(db, user, persona_id)
    if not ok:
        raise HTTPException(status_code=404, detail="persona not found")
    return None