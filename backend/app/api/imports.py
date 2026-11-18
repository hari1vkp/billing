"""Owner-only product onboarding endpoints (template, parse, commit, OCR, AI prompt, labels)."""

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_owner
from app.models.business import Business
from app.models.product import Product
from app.models.user import User
from app.schemas.imports import (
    AICategoriesResponse,
    AIPromptRequest,
    AIPromptResponse,
    BarcodeLookupResponse,
    ImportCommitRequest,
    ImportCommitResponse,
    ImportParseResponse,
    OcrResponse,
)
from app.services import ai_catalogue_service, import_service

router = APIRouter(prefix="/products/import", tags=["Product Import"])
barcode_router = APIRouter(prefix="/products/barcode/lookup", tags=["Product Import"])
ai_router = APIRouter(prefix="/products/ai", tags=["AI Catalogue"])
labels_router = APIRouter(prefix="/products/barcodes", tags=["Product Import"])


def _business_gst_default(db: Session, user: User) -> float:
    business = db.get(Business, user.business_id)
    rate = getattr(business, "default_gst_rate", None) if business else None
    try:
        return float(rate) if rate is not None else 18.0
    except (TypeError, ValueError):
        return 18.0


# --- AI-assisted catalogue prompt (owner only) ------------------------------

@ai_router.get("/categories", response_model=AICategoriesResponse)
def ai_categories(user: User = Depends(require_owner)):
    return AICategoriesResponse(categories=ai_catalogue_service.CATEGORIES)


@ai_router.post("/prompt", response_model=AIPromptResponse)
def ai_prompt(payload: AIPromptRequest, user: User = Depends(require_owner)):
    return AIPromptResponse(
        prompt=ai_catalogue_service.generate_prompt(
            payload.category_id,
            business_name=payload.business_name,
            extra_notes=payload.extra_notes,
        )
    )


# --- Printable Code 128 labels (owner only) ---------------------------------

@labels_router.get("/labels")
def product_barcode_labels(
    ids: str = Query(..., description="Comma-separated product ids"),
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    requested = [part.strip() for part in ids.split(",") if part.strip()]
    products: list[Product] = []
    if requested:
        found = {
            product.id: product
            for product in db.execute(
                select(Product).where(
                    Product.business_id == user.business_id,
                    Product.id.in_(requested),
                )
            ).scalars().all()
        }
        # Keep the order the owner supplied in the query string.
        products = [found[pid] for pid in requested if pid in found]
    if not products:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No products found for the supplied ids",
        )
    return Response(
        content=import_service.barcode_labels_pdf(products),
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="billflow-barcode-labels.pdf"'
        },
    )


# --- Import template / parse / commit / OCR ---------------------------------

@router.get("/template")
def download_template(
    user: User = Depends(require_owner),
):
    return Response(
        content=import_service.template_csv(),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                'attachment; filename="billflow-product-catalogue-template.csv"'
            )
        },
    )


@router.post("/parse", response_model=ImportParseResponse)
async def parse_import(
    file: UploadFile = File(...),
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    content = await file.read()
    try:
        preview = import_service.parse_file(
            file.filename or "",
            content,
            default_gst_rate=_business_gst_default(db, user),
            db=db,
            business_id=user.business_id,
        )
    except import_service.ParseError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return ImportParseResponse(**preview)


@router.post("/ocr", response_model=OcrResponse)
async def ocr_import(
    file: UploadFile = File(...),
    user: User = Depends(require_owner),
):
    content = await file.read()
    try:
        result = import_service.ocr_extract(file.filename or "", content)
    except import_service.OcrUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        )
    except import_service.ParseError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return OcrResponse(**result)


@router.post("/commit", response_model=ImportCommitResponse)
def commit_import(
    payload: ImportCommitRequest,
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    default_gst = (
        payload.default_gst_rate
        if payload.default_gst_rate is not None
        else _business_gst_default(db, user)
    )
    result = import_service.commit_rows(
        db,
        user.business_id,
        user.id,
        payload.rows,
        overwrite_stock=payload.overwrite_stock,
        default_gst_rate=default_gst,
    )
    return ImportCommitResponse(**result)


@barcode_router.get("/{barcode}", response_model=BarcodeLookupResponse)
def lookup_product_barcode(
    barcode: str,
    user: User = Depends(require_owner),
):
    return BarcodeLookupResponse(**import_service.lookup_barcode(barcode))
