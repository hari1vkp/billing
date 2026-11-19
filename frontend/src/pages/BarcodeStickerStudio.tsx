import { useEffect, useMemo, useState } from 'react';
import { Eye, Info, Printer, Search, Trash2 } from 'lucide-react';
import { api, getToken } from '../api/client';
import {
  Button,
  Card,
  CardHeader,
  EmptyState,
  Input,
  Loader,
  PageHeader,
  Pagination,
  useToast,
} from '../components/UI';
import { getBackendUrl, isTauri, printFile, saveExportBytes } from '../tauri';
import type {
  BarcodeStickerPayload,
  BarcodeStickerPreviewResponse,
  Paginated,
  Product,
  StickerLayout,
  StickerSize,
} from '../types';

const PAGE_SIZE = 20;

const SIZE_OPTIONS: Array<{ value: StickerSize; label: string; dims: string }> = [
  { value: 'small', label: 'Small', dims: '40 × 25 mm' },
  { value: 'medium', label: 'Medium', dims: '50 × 30 mm' },
  { value: 'large', label: 'Large', dims: '60 × 40 mm' },
  { value: 'xl', label: 'Extra Large', dims: '100 × 50 mm' },
  { value: 'custom', label: 'Custom', dims: 'Set your own' },
];

/** Dimensions come from the contract; the backend is the source of truth. */
const PRESET_DIMENSIONS: Record<Exclude<StickerSize, 'custom'>, { width: number; height: number }> = {
  small: { width: 40, height: 25 },
  medium: { width: 50, height: 30 },
  large: { width: 60, height: 40 },
  xl: { width: 100, height: 50 },
};

const DEFAULT_PDF_BASE = 'http://127.0.0.1:8000/api/v1';

function clampQuantity(raw: string | number | undefined | null): number {
  const value = Math.floor(Number(raw));
  return Number.isFinite(value) && value > 0 ? value : 1;
}

function clampDimension(raw: string, fallback: number): number {
  if (raw.trim() === '') return fallback;
  const value = Math.floor(Number(raw));
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

function layoutLabel(layout: StickerLayout): string {
  return layout === 'sheet' ? 'A4 sheet' : 'Individual';
}

export function BarcodeStickerStudio({ embedded = false }: { embedded?: boolean } = {}) {
  const toast = useToast();

  /* Product browser */
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [products, setProducts] = useState<Product[]>([]);
  const [total, setTotal] = useState(0);
  const [pages, setPages] = useState(1);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);

  /* Selection is independent of quantity so a deselected product keeps its
     quantity if it is selected again. */
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set<string>());
  const [quantities, setQuantities] = useState<Record<string, string>>({});
  const [selectingAll, setSelectingAll] = useState(false);

  /* Sticker setup */
  const [size, setSize] = useState<StickerSize>('small');
  const [customWidth, setCustomWidth] = useState('50');
  const [customHeight, setCustomHeight] = useState('30');
  const [layout, setLayout] = useState<StickerLayout>('sheet');

  /* Output */
  const [preview, setPreview] = useState<BarcodeStickerPreviewResponse | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [printing, setPrinting] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setLoadError(false);
    const timer = window.setTimeout(() => {
      api
        .get<Paginated<Product>>('/products', {
          q: search.trim() || undefined,
          page,
          page_size: PAGE_SIZE,
        })
        .then((response) => {
          if (!active) return;
          setProducts(response.items);
          setTotal(response.total);
          setPages(response.pages || 1);
        })
        .catch(() => {
          if (!active) return;
          setProducts([]);
          setTotal(0);
          setPages(1);
          setLoadError(true);
        })
        .finally(() => {
          if (active) setLoading(false);
        });
    }, 220);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [search, page]);

  const selectedList = useMemo(() => Array.from(selectedIds), [selectedIds]);

  const totalStickers = useMemo(
    () => selectedList.reduce((sum, id) => sum + clampQuantity(quantities[id] ?? '1'), 0),
    [selectedList, quantities],
  );

  const dimensions = useMemo(() => {
    if (size === 'custom') {
      return {
        width: clampDimension(customWidth, 50),
        height: clampDimension(customHeight, 30),
      };
    }
    return PRESET_DIMENSIONS[size];
  }, [size, customWidth, customHeight]);

  function toggleProduct(id: string) {
    setSelectedIds((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function selectPage() {
    if (!products.length) return;
    setSelectedIds((previous) => {
      const next = new Set(previous);
      products.forEach((product) => next.add(product.id));
      return next;
    });
  }

  async function selectAllMatching() {
    const query = search.trim() || undefined;
    setSelectingAll(true);
    try {
      const first = await api.get<Paginated<Product>>('/products', {
        q: query,
        page: 1,
        page_size: PAGE_SIZE,
      });
      const ids: string[] = first.items.map((product) => product.id);
      const lastPage = Number.isFinite(first.pages) ? first.pages : 1;
      for (let nextPage = 2; nextPage <= lastPage; nextPage += 1) {
        const response = await api.get<Paginated<Product>>('/products', {
          q: query,
          page: nextPage,
          page_size: PAGE_SIZE,
        });
        response.items.forEach((product) => ids.push(product.id));
      }
      setSelectedIds((previous) => {
        const next = new Set(previous);
        ids.forEach((id) => next.add(id));
        return next;
      });
      toast.success(`Selected ${ids.length} matching product${ids.length === 1 ? '' : 's'}.`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not select all products.');
    } finally {
      setSelectingAll(false);
    }
  }

  function clearSelection() {
    setSelectedIds(new Set<string>());
    setQuantities({});
    setPreview(null);
  }

  function updateQuantity(id: string, raw: string) {
    if (raw === '') {
      setQuantities((previous) => ({ ...previous, [id]: '' }));
      return;
    }
    const value = Number(raw);
    const normalized = Number.isFinite(value) && value > 0 ? String(Math.floor(value)) : '1';
    setQuantities((previous) => ({ ...previous, [id]: normalized }));
  }

  function normalizeQuantity(id: string) {
    setQuantities((previous) => ({
      ...previous,
      [id]: String(clampQuantity(previous[id] ?? '1')),
    }));
  }

  function buildPayload(): BarcodeStickerPayload {
    return {
      items: selectedList.map((id) => ({
        product_id: id,
        quantity: clampQuantity(quantities[id] ?? '1'),
      })),
      size,
      width_mm: dimensions.width,
      height_mm: dimensions.height,
      layout,
    };
  }

  async function generatePreview() {
    if (!selectedList.length) {
      toast.error('Select at least one product first.');
      return;
    }
    setPreviewing(true);
    try {
      const response = await api.post<BarcodeStickerPreviewResponse>(
        '/barcode-stickers/preview',
        buildPayload(),
      );
      setPreview(response);
    } catch (error) {
      setPreview(null);
      toast.error(error instanceof Error ? error.message : 'Could not generate the preview.');
    } finally {
      setPreviewing(false);
    }
  }

  async function printStickers() {
    if (!selectedList.length) {
      toast.error('Select at least one product first.');
      return;
    }
    setPrinting(true);
    try {
      // The generic API client parses JSON, so PDF bytes need an authenticated fetch.
      const base = isTauri()
        ? await getBackendUrl().catch(() => DEFAULT_PDF_BASE)
        : '/api/v1';
      const token = getToken();
      const response = await fetch(`${base}/barcode-stickers/pdf`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(buildPayload()),
      });
      if (!response.ok) {
        let message = `Could not build the sticker PDF (${response.status}).`;
        try {
          const data = (await response.json()) as { detail?: unknown };
          if (typeof data.detail === 'string') message = data.detail;
        } catch {
          // Keep the generic message when the error body is not JSON.
        }
        throw new Error(message);
      }
      const blob = await response.blob();

      if (isTauri()) {
        const bytes = Array.from(new Uint8Array(await blob.arrayBuffer()));
        const path = await saveExportBytes('billflow-barcode-stickers.pdf', bytes);
        await printFile(path);
        toast.success('Stickers sent to the printer.');
      } else {
        const url = URL.createObjectURL(blob);
        const printWindow = window.open(url, '_blank');
        if (printWindow) {
          const triggerPrint = () => {
            try {
              printWindow.focus();
              printWindow.print();
            } catch {
              // Some browsers block scripting a PDF viewer window.
            }
          };
          printWindow.addEventListener('load', triggerPrint, { once: true });
          window.setTimeout(triggerPrint, 1200);
        } else {
          const anchor = document.createElement('a');
          anchor.href = url;
          anchor.target = '_blank';
          anchor.rel = 'noopener';
          document.body.appendChild(anchor);
          anchor.click();
          anchor.remove();
          toast.info('PDF opened in a new tab — use your browser’s print dialog.');
        }
        window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not print the stickers.');
    } finally {
      setPrinting(false);
    }
  }

  return (
    <div className="sticker-page">
      {embedded ? (
        <div className="sticker-embedded-bar">
          <span className="muted small">Select products, choose a sticker size and print scannable barcodes</span>
          <span className="sticker-total">
            <strong>{totalStickers}</strong> sticker{totalStickers === 1 ? '' : 's'} ·{' '}
            <strong>{selectedList.length}</strong> selected
          </span>
          <Button
            variant="secondary"
            icon={<Trash2 size={15} />}
            onClick={clearSelection}
            disabled={!selectedList.length}
          >
            Clear Selection
          </Button>
        </div>
      ) : (
        <PageHeader
          title="Barcode Studio"
          subtitle="Select products, choose a sticker size and print scannable barcodes"
          actions={
            <>
              <span className="sticker-total">
                <strong>{totalStickers}</strong> sticker{totalStickers === 1 ? '' : 's'} ·{' '}
                <strong>{selectedList.length}</strong> selected
              </span>
              <Button
                variant="secondary"
                icon={<Trash2 size={15} />}
                onClick={clearSelection}
                disabled={!selectedList.length}
              >
                Clear Selection
              </Button>
            </>
          }
        />
      )}

      <Card>
        <CardHeader
          title="Select products"
          subtitle="Search by name, SKU or barcode. Each product has its own sticker quantity."
          action={<span className="muted small">{total} product{total === 1 ? '' : 's'}</span>}
        />

        <div className="sticker-toolbar">
          <div className="sticker-toolbar__search">
            <Search size={16} />
            <Input
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setPage(1);
              }}
              placeholder="Search products by name, SKU or barcode…"
              aria-label="Search products"
            />
          </div>
          <div className="sticker-toolbar__actions">
            <Button size="sm" variant="secondary" onClick={selectPage} disabled={!products.length}>
              Select page
            </Button>
            <Button
              size="sm"
              variant="secondary"
              loading={selectingAll}
              onClick={() => void selectAllMatching()}
              disabled={!total}
            >
              Select all matching
            </Button>
          </div>
        </div>

        {loading ? (
          <Loader label="Loading products…" />
        ) : loadError ? (
          <EmptyState
            title="Could not load products"
            description="Try again in a moment."
            icon={<Info size={22} />}
          />
        ) : products.length ? (
          <>
            <div className="sticker-product-grid">
              {products.map((product) => {
                const isSelected = selectedIds.has(product.id);
                const quantity = quantities[product.id] ?? '1';
                return (
                  <div
                    key={product.id}
                    role="button"
                    tabIndex={0}
                    aria-pressed={isSelected}
                    className={
                      isSelected
                        ? 'sticker-product-card sticker-product-card--selected'
                        : 'sticker-product-card'
                    }
                    onClick={() => toggleProduct(product.id)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        toggleProduct(product.id);
                      }
                    }}
                  >
                    <label
                      className="sticker-product-check"
                      onClick={(event) => event.stopPropagation()}
                    >
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={() => toggleProduct(product.id)}
                        aria-label={`Select ${product.name}`}
                      />
                    </label>
                    <div className="sticker-product-main">
                      <strong className="sticker-product-name">{product.name}</strong>
                      <span className="sticker-product-meta">
                        {product.sku ? `SKU ${product.sku}` : 'No SKU'}
                      </span>
                    </div>
                    <div className="sticker-product-barcode">
                      {product.barcode ? (
                        <span className="mono">{product.barcode}</span>
                      ) : (
                        <span className="sticker-product-nobarcode">
                          No barcode — will be generated
                        </span>
                      )}
                    </div>
                    <label
                      className="sticker-qty"
                      onClick={(event) => event.stopPropagation()}
                    >
                      <span className="sticker-qty__label">Qty</span>
                      <Input
                        className="sticker-qty__input"
                        type="number"
                        min={1}
                        step={1}
                        value={quantity}
                        aria-label={`Sticker quantity for ${product.name}`}
                        onChange={(event) => updateQuantity(product.id, event.target.value)}
                        onBlur={() => normalizeQuantity(product.id)}
                      />
                    </label>
                  </div>
                );
              })}
            </div>
            {total > PAGE_SIZE && (
              <Pagination
                page={page}
                pages={pages}
                total={total}
                pageSize={PAGE_SIZE}
                onPage={setPage}
              />
            )}
          </>
        ) : (
          <EmptyState
            title="No products found"
            description={search.trim() ? 'Try a different search.' : 'Add products in Inventory first.'}
            icon={<Search size={22} />}
          />
        )}
      </Card>

      <div className="sticker-grid">
        <Card>
          <CardHeader title="Sticker setup" subtitle="Applied to every selected product." />

          <div className="sticker-field-label">Sticker size</div>
          <div className="sticker-options" role="group" aria-label="Sticker size">
            {SIZE_OPTIONS.map((option) => (
              <button
                key={option.value}
                type="button"
                aria-pressed={size === option.value}
                className={
                  size === option.value
                    ? 'sticker-option sticker-option--active'
                    : 'sticker-option'
                }
                onClick={() => setSize(option.value)}
              >
                <span className="sticker-option__label">{option.label}</span>
                <span className="sticker-option__dim">{option.dims}</span>
              </button>
            ))}
          </div>

          {size === 'custom' && (
            <div className="sticker-custom-dims">
              <label className="sticker-custom-dim">
                <span>Width (mm)</span>
                <Input
                  type="number"
                  min={1}
                  step={1}
                  value={customWidth}
                  onChange={(event) => setCustomWidth(event.target.value)}
                  onBlur={() => setCustomWidth(String(clampDimension(customWidth, 50)))}
                />
              </label>
              <label className="sticker-custom-dim">
                <span>Height (mm)</span>
                <Input
                  type="number"
                  min={1}
                  step={1}
                  value={customHeight}
                  onChange={(event) => setCustomHeight(event.target.value)}
                  onBlur={() => setCustomHeight(String(clampDimension(customHeight, 30)))}
                />
              </label>
            </div>
          )}

          <div className="sticker-field-label">Print layout</div>
          <div className="sticker-options" role="group" aria-label="Print layout">
            <button
              type="button"
              aria-pressed={layout === 'sheet'}
              className={
                layout === 'sheet' ? 'sticker-option sticker-option--active' : 'sticker-option'
              }
              onClick={() => setLayout('sheet')}
            >
              <span className="sticker-option__label">A4 sheet</span>
              <span className="sticker-option__dim">Multiple stickers per page</span>
            </button>
            <button
              type="button"
              aria-pressed={layout === 'individual'}
              className={
                layout === 'individual'
                  ? 'sticker-option sticker-option--active'
                  : 'sticker-option'
              }
              onClick={() => setLayout('individual')}
            >
              <span className="sticker-option__label">Individual</span>
              <span className="sticker-option__dim">One sticker per page</span>
            </button>
          </div>

          <div className="sticker-note">
            <Info size={15} />
            <span>
              Missing barcodes are generated automatically and saved to the product. Stock,
              price and SKU are never changed.
            </span>
          </div>

          <div className="sticker-actions">
            <Button
              icon={<Eye size={16} />}
              loading={previewing}
              disabled={!selectedList.length}
              onClick={() => void generatePreview()}
            >
              Generate Preview
            </Button>
            <Button
              variant="secondary"
              icon={<Printer size={16} />}
              loading={printing}
              disabled={!selectedList.length}
              onClick={() => void printStickers()}
            >
              Print Stickers
            </Button>
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Preview & print summary"
            subtitle="One real sticker is shown; the PDF uses the exact dimensions."
          />
          <div className="sticker-preview-frame">
            {preview ? (
              <div
                className="sticker-preview-svg"
                dangerouslySetInnerHTML={{ __html: preview.svg }}
              />
            ) : (
              <div className="sticker-preview-placeholder">
                Generate a preview to see the sticker and print summary.
              </div>
            )}
          </div>

          {preview && (
            <div className="sticker-summary">
              <div className="sticker-summary__grid">
                <div className="sticker-summary__stat">
                  <span className="sticker-summary__stat-label">Stickers</span>
                  <span className="sticker-summary__stat-value">{preview.total_stickers}</span>
                </div>
                <div className="sticker-summary__stat">
                  <span className="sticker-summary__stat-label">Dimensions</span>
                  <span className="sticker-summary__stat-value">
                    {preview.width_mm} × {preview.height_mm} mm
                  </span>
                </div>
                <div className="sticker-summary__stat">
                  <span className="sticker-summary__stat-label">Layout</span>
                  <span className="sticker-summary__stat-value">{layoutLabel(preview.layout)}</span>
                </div>
                <div className="sticker-summary__stat">
                  <span className="sticker-summary__stat-label">Est. pages</span>
                  <span className="sticker-summary__stat-value">{preview.pages}</span>
                </div>
              </div>
              <div className="sticker-summary__items">
                {preview.items.map((item) => (
                  <div key={item.product_id} className="sticker-summary-item">
                    <div className="sticker-summary-item__info">
                      <span className="sticker-summary-item__name">{item.name}</span>
                      {item.barcode && (
                        <span className="sticker-summary-item__barcode mono">{item.barcode}</span>
                      )}
                    </div>
                    <span className="sticker-summary-item__qty">× {item.quantity}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
