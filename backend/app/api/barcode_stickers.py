"""Owner-only Barcode Sticker Studio endpoints.

All validation lives in ``barcode_sticker_service`` so the preview and PDF
endpoints produce identical metadata and print jobs.
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_owner
from app.models.user import User
from app.services import barcode_sticker_service, product_service

router = APIRouter(prefix="/barcode-stickers", tags=["Barcode Sticker Studio"])


class EnsureRequest(BaseModel):
    product_ids: list[str]


class EnsureResponse(BaseModel):
    barcodes: dict[str, str]
    # Product ids whose barcode was newly generated (empty when all existed).
    generated: list[str]


class StickerItemRequest(BaseModel):
    product_id: str
    quantity: int = 1


class StickerJobRequest(BaseModel):
    items: list[StickerItemRequest]
    size: str = "small"
    width_mm: float | None = None
    height_mm: float | None = None
    layout: str = "sheet"


class StickerPreviewItem(BaseModel):
    product_id: str
    name: str
    barcode: str
    quantity: int


class StickerPreviewResponse(BaseModel):
    svg: str
    total_stickers: int
    pages: int
    width_mm: float
    height_mm: float
    layout: str
    items: list[StickerPreviewItem]


def _bad_request(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


def _not_found(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post("/ensure", response_model=EnsureResponse)
def ensure_sticker_barcodes(
    payload: EnsureRequest,
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    """Reuse existing barcodes; generate only the missing ones (idempotent)."""
    try:
        barcodes, generated = barcode_sticker_service.ensure_barcodes(
            db, user.business_id, payload.product_ids, user.id
        )
    except (barcode_sticker_service.ValidationError, product_service.ValidationError) as exc:
        raise _bad_request(exc)
    except (barcode_sticker_service.NotFoundError, product_service.NotFoundError) as exc:
        raise _not_found(exc)
    return EnsureResponse(barcodes=barcodes, generated=generated)


@router.post("/preview", response_model=StickerPreviewResponse)
def preview_sticker(
    payload: StickerJobRequest,
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    """SVG for one representative sticker plus the full job's pagination."""
    try:
        result = barcode_sticker_service.build_preview(
            db,
            user.business_id,
            [item.model_dump() for item in payload.items],
            size=payload.size,
            width_mm=payload.width_mm,
            height_mm=payload.height_mm,
            layout=payload.layout,
            user_id=user.id,
        )
    except (barcode_sticker_service.ValidationError, product_service.ValidationError) as exc:
        raise _bad_request(exc)
    except (barcode_sticker_service.NotFoundError, product_service.NotFoundError) as exc:
        raise _not_found(exc)
    return StickerPreviewResponse(**result)


@router.post("/pdf")
def sticker_pdf(
    payload: StickerJobRequest,
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    """Print-ready PDF: A4 sheets or one actual-size sticker per page."""
    try:
        content = barcode_sticker_service.build_pdf(
            db,
            user.business_id,
            [item.model_dump() for item in payload.items],
            size=payload.size,
            width_mm=payload.width_mm,
            height_mm=payload.height_mm,
            layout=payload.layout,
            user_id=user.id,
        )
    except (barcode_sticker_service.ValidationError, product_service.ValidationError) as exc:
        raise _bad_request(exc)
    except (barcode_sticker_service.NotFoundError, product_service.NotFoundError) as exc:
        raise _not_found(exc)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'inline; filename="billflow-barcode-stickers.pdf"'
        },
    )
