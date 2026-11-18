"""Pydantic models for the beginner-friendly product onboarding API.

These mirror the shapes documented in AI_CATALOGUE_CONTRACT.md. They are
deliberately lenient about optional values: the parser/commit service performs
the actual validation so that individual bad rows can be reported instead of
rejecting a whole upload.
"""

from pydantic import BaseModel, Field


class ImportRowInput(BaseModel):
    """A single row sent by the client to the commit endpoint."""

    name: str
    brand: str | None = None
    category: str | None = None
    subcategory: str | None = None
    variant: str | None = None
    size_pack: str | None = None
    barcode: str | None = None
    barcode_type: str | None = None
    sku: str | None = None
    cost_price: float | None = None
    selling_price: float
    discount_type: str | None = None
    discount_value: float | None = None
    quantity: float = 0
    gst_rate: float | None = None


class ImportPreviewRow(BaseModel):
    """One parsed row shown in the editable preview table."""

    row_number: int
    name: str
    brand: str | None = None
    category: str | None = None
    subcategory: str | None = None
    variant: str | None = None
    size_pack: str | None = None
    barcode: str | None = None
    barcode_type: str | None = None
    sku: str | None = None
    cost_price: float | None = None
    selling_price: float | None = None
    discount_type: str = "none"
    discount_value: float = 0
    quantity: float = 0
    gst_rate: float
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    valid: bool = True


class ImportParseResponse(BaseModel):
    recognized_columns: dict[str, str | None] = Field(default_factory=dict)
    unsupported_columns: list[str] = Field(default_factory=list)
    total_rows: int = 0
    error_count: int = 0
    rows: list[ImportPreviewRow] = Field(default_factory=list)


class CommitRowError(BaseModel):
    row: int
    message: str


class ImportCommitRequest(BaseModel):
    rows: list[ImportRowInput] = Field(default_factory=list)
    overwrite_stock: bool = False
    default_gst_rate: float | None = None


class ImportCommitResponse(BaseModel):
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[CommitRowError] = Field(default_factory=list)
    stock_movements: int = 0
    activity_entries: int = 0


class OcrRow(BaseModel):
    name: str
    quantity: float | None = None
    confidence: float
    uncertain_fields: list[str] = Field(default_factory=list)
    raw_line: str


class OcrResponse(BaseModel):
    rows: list[OcrRow] = Field(default_factory=list)
    source: str
    warnings: list[str] = Field(default_factory=list)


class BarcodeLookupResponse(BaseModel):
    found: bool
    source: str
    barcode: str
    name: str | None = None
    brand: str | None = None
    category: str | None = None
    image_url: str | None = None
    # The catalogue has no reliable pricing data; this is always null.
    price: None = None
    message: str


# --- AI-assisted catalogue onboarding -------------------------------------


class AICategory(BaseModel):
    id: str
    label: str
    description: str


class AICategoriesResponse(BaseModel):
    categories: list[AICategory]


class AIPromptRequest(BaseModel):
    category_id: str
    business_name: str | None = None
    extra_notes: str | None = None


class AIPromptResponse(BaseModel):
    prompt: str
