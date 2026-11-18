import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from 'react';
import {
  AlertCircle,
  Camera,
  CheckCircle2,
  Download,
  FileSpreadsheet,
  FileText,
  Keyboard,
  Package,
  RotateCcw,
  ScanLine,
  Trash2,
  Upload,
} from 'lucide-react';
import {
  ApiError,
  api,
  downloadFile,
  getRefreshToken,
  getToken,
  setTokenResponse,
} from '../api/client';
import { getBackendUrl, isTauri } from '../tauri';
import { useAuth } from '../context/AuthContext';
import { Badge, Button, Checkbox, Field, Input, Loader, Select, useToast } from '../components/UI';
import type {
  BarcodeLookupResponse,
  Product,
  ProductImportCommitResponse,
  ProductImportCommitRow,
  ProductImportParseResponse,
  ProductInput,
  ProductOcrResponse,
} from '../types';

/* ------------------------------------------------------------------ */
/* Multipart helper — same auth/base rules as the shared api client.   */
/* ------------------------------------------------------------------ */

const DEFAULT_TAURI_BASE = 'http://127.0.0.1:8000/api/v1';
let apiBasePromise: Promise<string> | null = null;

function apiBase(): Promise<string> {
  if (!isTauri()) return Promise.resolve('/api/v1');
  if (apiBasePromise === null) {
    apiBasePromise = getBackendUrl().catch(() => DEFAULT_TAURI_BASE);
  }
  return apiBasePromise;
}

async function multipartPost<T>(path: string, file: File): Promise<T> {
  const base = await apiBase();
  const form = new FormData();
  form.append('file', file);

  const send = () => {
    const token = getToken();
    return fetch(`${base}${path}`, {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: form,
    });
  };

  let response = await send();
  if (response.status === 401) {
    const refreshToken = getRefreshToken();
    if (refreshToken) {
      try {
        const refresh = await fetch(`${base}/auth/refresh`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
        if (refresh.ok) {
          setTokenResponse(await refresh.json());
          response = await send();
        }
      } catch {
        // Keep the original 401 response below.
      }
    }
  }

  if (!response.ok) {
    let message = `Something went wrong (${response.status})`;
    try {
      const data = (await response.json()) as { detail?: unknown };
      if (typeof data.detail === 'string') message = data.detail;
    } catch {
      // Keep the generic message.
    }
    throw new ApiError(message, response.status);
  }

  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

function errorText(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

/* ------------------------------------------------------------------ */
/* Shared product draft used by the Barcode and Manual tabs.           */
/* ------------------------------------------------------------------ */

interface ProductDraft {
  name: string;
  barcode: string;
  sellingPrice: string;
  costPrice: string;
  openingStock: string;
  category: string;
}

function emptyDraft(): ProductDraft {
  return {
    name: '',
    barcode: '',
    sellingPrice: '',
    costPrice: '',
    openingStock: '0',
    category: '',
  };
}

function buildProductPayload(draft: ProductDraft, defaultGst: number, forcedBarcode?: string) {
  const barcode = (forcedBarcode ?? draft.barcode).trim();
  const cost = draft.costPrice.trim();
  const payload: ProductInput & { cost_price?: number } = {
    name: draft.name.trim(),
    barcode: barcode || undefined,
    sku: barcode || undefined,
    description: draft.category.trim() || undefined,
    price: Number(draft.sellingPrice),
    stock: Number(draft.openingStock),
    gst_rate: defaultGst,
    track_inventory: true,
    is_service: false,
    ...(cost !== '' ? { cost_price: Number(cost) } : {}),
  };
  return payload;
}

function productFormFields(
  draft: ProductDraft,
  set: (field: keyof ProductDraft, value: string) => void,
  options: { lockBarcode?: boolean; stockRequired?: boolean } = {},
) {
  const stockRequired = options.stockRequired ?? true;
  return (
    <>
      <Field label="Product name" required>
        <Input required value={draft.name} placeholder="e.g. Cotton T-Shirt"
          onChange={(event) => set('name', event.target.value)} />
      </Field>
      <Field label="Barcode" hint="From the package or your own label.">
        <Input value={draft.barcode} placeholder="8901234567890" readOnly={options.lockBarcode}
          onChange={(event) => set('barcode', event.target.value)} />
      </Field>
      <div className="form-grid form-grid--2">
        <Field label="Selling price" required hint="We never fill this in for you.">
          <Input type="number" min="0" step="0.01" required value={draft.sellingPrice}
            placeholder="0.00" onChange={(event) => set('sellingPrice', event.target.value)} />
        </Field>
        <Field label="Cost price (optional)">
          <Input type="number" min="0" step="0.01" value={draft.costPrice}
            placeholder="0.00" onChange={(event) => set('costPrice', event.target.value)} />
        </Field>
      </div>
      <div className="form-grid form-grid--2">
        <Field label="Opening stock" required={stockRequired} hint="How many you have right now.">
          <Input type="number" min="0" step="1" required={stockRequired} value={draft.openingStock}
            placeholder="0" onChange={(event) => set('openingStock', event.target.value)} />
        </Field>
        <Field label="Category (optional)">
          <Input value={draft.category} placeholder="e.g. Clothing"
            onChange={(event) => set('category', event.target.value)} />
        </Field>
      </div>
    </>
  );
}

/* ------------------------------------------------------------------ */
/* Bulk file tab                                                       */
/* ------------------------------------------------------------------ */

interface EditableRow {
  row_number: number;
  name: string;
  brand: string;
  category: string;
  subcategory: string;
  variant: string;
  size_pack: string;
  barcode: string;
  barcode_type: string;
  sku: string;
  cost_price: string;
  selling_price: string;
  discount_type: string;
  discount_value: string;
  quantity: string;
  gst_rate: number;
  errors: string[];
  warnings: string[];
  valid: boolean;
}

type EditableTextField = Exclude<
  keyof EditableRow,
  'row_number' | 'gst_rate' | 'errors' | 'warnings' | 'valid'
>;

const DISCOUNT_TYPES = ['none', 'percent', 'flat'];

function toEditable(row: ProductImportParseResponse['rows'][number]): EditableRow {
  return {
    row_number: row.row_number,
    name: row.name ?? '',
    brand: row.brand ?? '',
    category: row.category ?? '',
    subcategory: row.subcategory ?? '',
    variant: row.variant ?? '',
    size_pack: row.size_pack ?? '',
    barcode: row.barcode ?? '',
    barcode_type: row.barcode_type ?? '',
    sku: row.sku ?? '',
    cost_price: row.cost_price === null || row.cost_price === undefined ? '' : String(row.cost_price),
    selling_price: row.selling_price === null || row.selling_price === undefined ? '' : String(row.selling_price),
    discount_type: row.discount_type ?? 'none',
    discount_value: row.discount_value === null || row.discount_value === undefined ? '' : String(row.discount_value),
    quantity: row.quantity === null || row.quantity === undefined ? '' : String(row.quantity),
    gst_rate: row.gst_rate,
    errors: row.errors ?? [],
    warnings: row.warnings ?? [],
    valid: row.valid,
  };
}

/** Re-check the few rules a person can fix by editing a cell. */
function revalidate(row: EditableRow): EditableRow {
  const errors: string[] = [];
  if (!row.name.trim()) errors.push('Name is required.');
  if (row.selling_price.trim() === '' || Number(row.selling_price) < 0) {
    errors.push('Selling price is required and cannot be negative.');
  }
  if (row.quantity.trim() !== '' && Number(row.quantity) < 0) {
    errors.push('Quantity cannot be negative.');
  }
  const discount = row.discount_value.trim();
  if (discount !== '') {
    const value = Number(discount);
    if (!Number.isFinite(value) || value < 0) {
      errors.push('Discount value cannot be negative.');
    } else if (row.discount_type === 'percent' && value > 100) {
      errors.push('A percentage discount cannot be more than 100.');
    }
  }
  return { ...row, errors, valid: errors.length === 0 };
}

function BulkImport({ onImported }: { onImported: () => void }) {
  const toast = useToast();
  const [fileKey, setFileKey] = useState(0);
  const [rows, setRows] = useState<EditableRow[]>([]);
  const [fileName, setFileName] = useState('');
  const [overwrite, setOverwrite] = useState(false);
  const [parsing, setParsing] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [summary, setSummary] = useState<ProductImportCommitResponse | null>(null);
  const [error, setError] = useState('');

  async function pickFile(file: File | undefined) {
    if (!file) return;
    setError('');
    setSummary(null);
    setRows([]);
    setFileName(file.name);
    setParsing(true);
    try {
      const result = await multipartPost<ProductImportParseResponse>('/products/import/parse', file);
      setRows(result.rows.map(toEditable));
      if (!result.rows.length) setError('We could not find any products in that file.');
    } catch (err) {
      setRows([]);
      setError(errorText(err, 'We could not read that file. Please try the template.'));
    } finally {
      setParsing(false);
    }
  }

  function reset() {
    setRows([]);
    setFileName('');
    setSummary(null);
    setError('');
    setOverwrite(false);
    setFileKey((value) => value + 1);
  }

  function updateRow(index: number, field: keyof EditableRow, value: string) {
    setRows((current) => current.map((row, i) => (
      i === index ? revalidate({ ...row, [field]: value }) : row
    )));
  }

  function removeRow(index: number) {
    setRows((current) => current.filter((_, i) => i !== index));
  }

  async function commit() {
    const validRows = rows.filter((row) => row.valid);
    if (!validRows.length) return;
    setCommitting(true);
    setError('');
    setSummary(null);
    const commitRows: ProductImportCommitRow[] = validRows.map((row) => ({
      name: row.name.trim(),
      brand: row.brand.trim() || undefined,
      category: row.category.trim() || undefined,
      subcategory: row.subcategory.trim() || undefined,
      variant: row.variant.trim() || undefined,
      size_pack: row.size_pack.trim() || undefined,
      barcode: row.barcode.trim() || undefined,
      barcode_type: row.barcode_type.trim() || undefined,
      sku: row.sku.trim() || undefined,
      cost_price: row.cost_price.trim() !== '' ? Number(row.cost_price) : undefined,
      selling_price: Number(row.selling_price),
      discount_type: row.discount_type || 'none',
      discount_value: row.discount_value.trim() !== '' ? Number(row.discount_value) : undefined,
      quantity: row.quantity.trim() !== '' ? Number(row.quantity) : 0,
      gst_rate: row.gst_rate,
    }));
    try {
      const result = await api.post<ProductImportCommitResponse>('/products/import/commit', {
        rows: commitRows,
        overwrite_stock: overwrite,
      });
      setSummary(result);
      toast.success(`Imported ${result.created} new product${result.created === 1 ? '' : 's'}.`);
      onImported();
    } catch (err) {
      setError(errorText(err, 'The import could not be finished. Please try again.'));
    } finally {
      setCommitting(false);
    }
  }

  function cell(
    index: number,
    row: EditableRow,
    field: EditableTextField,
    label: string,
    options: { className?: string; type?: 'text' | 'number'; min?: string; step?: string } = {},
  ) {
    return (
      <td>
        <Input
          className={`import-cell-input ${options.className ?? ''}`}
          type={options.type ?? 'text'}
          min={options.min}
          step={options.step}
          value={row[field]}
          aria-label={`${label} for row ${row.row_number}`}
          onChange={(event) => updateRow(index, field, event.target.value)}
        />
      </td>
    );
  }

  const validCount = rows.filter((row) => row.valid).length;

  return (
    <div className="form-stack">
      <p className="import-intro">
        Add many products at once from a CSV file or spreadsheet. Not sure what to put in the file?
        Download the template and fill in the columns.
      </p>

      <div className="import-toolbar">
        <Button variant="secondary" size="sm" icon={<Download size={15} />}
          onClick={() => {
            void downloadFile('/products/import/template', 'billflow-product-import-template.csv')
              .catch((err) => setError(errorText(err, 'The template could not be downloaded.')));
          }}>
          Download template
        </Button>
        <div className="import-file-picker">
          <Input key={fileKey} className="import-file-input" type="file"
            accept=".csv,.xlsx,.xls" aria-label="Choose a product file"
            onChange={(event) => void pickFile(event.target.files?.[0])} />
          {fileName && <span className="import-file-name">{fileName}</span>}
        </div>
      </div>

      {parsing && <Loader label="Reading your file…" />}
      {error && <div className="alert alert--error"><AlertCircle size={16} /> {error}</div>}

      {rows.length > 0 && !parsing && (
        <>
          <div className="import-preview">
            <div className="table-scroll">
              <table className="data-table data-table--compact">
                <thead>
                  <tr>
                    <th>Row</th>
                    <th>Name</th>
                    <th>Brand</th>
                    <th>Category</th>
                    <th>Subcategory</th>
                    <th>Variant</th>
                    <th>Size / Pack</th>
                    <th>Barcode</th>
                    <th>Barcode type</th>
                    <th>SKU</th>
                    <th>Cost</th>
                    <th>Selling price</th>
                    <th>Discount type</th>
                    <th>Discount value</th>
                    <th>Qty</th>
                    <th>Status</th>
                    <th aria-label="Remove" />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, index) => (
                    <tr key={`${row.row_number}-${index}`}
                      className={row.valid ? '' : 'import-row--invalid'}>
                      <td className="mono small">{row.row_number}</td>
                      {cell(index, row, 'name', 'Name', { className: 'import-cell-input--name' })}
                      {cell(index, row, 'brand', 'Brand')}
                      {cell(index, row, 'category', 'Category')}
                      {cell(index, row, 'subcategory', 'Subcategory')}
                      {cell(index, row, 'variant', 'Variant')}
                      {cell(index, row, 'size_pack', 'Size / Pack')}
                      {cell(index, row, 'barcode', 'Barcode')}
                      {cell(index, row, 'barcode_type', 'Barcode type')}
                      {cell(index, row, 'sku', 'SKU')}
                      {cell(index, row, 'cost_price', 'Cost', { type: 'number', min: '0', step: '0.01' })}
                      {cell(index, row, 'selling_price', 'Selling price', { type: 'number', min: '0', step: '0.01' })}
                      <td>
                        <Select className="import-cell-input import-cell-select" value={row.discount_type}
                          aria-label={`Discount type for row ${row.row_number}`}
                          onChange={(event) => updateRow(index, 'discount_type', event.target.value)}>
                          {!DISCOUNT_TYPES.includes(row.discount_type) && (
                            <option value={row.discount_type}>{row.discount_type}</option>
                          )}
                          <option value="none">None</option>
                          <option value="percent">Percent</option>
                          <option value="flat">Flat</option>
                        </Select>
                      </td>
                      {cell(index, row, 'discount_value', 'Discount value', { type: 'number', min: '0', step: '0.01' })}
                      {cell(index, row, 'quantity', 'Quantity', { type: 'number', min: '0', step: '1', className: 'import-cell-input--qty' })}
                      <td>
                        <Badge tone={row.valid ? 'success' : 'danger'} dot>
                          {row.valid ? 'Ready' : 'Needs fixing'}
                        </Badge>
                        {row.errors.map((message, i) => (
                          <div key={`e-${i}`} className="import-errors">{message}</div>
                        ))}
                        {row.warnings.map((message, i) => (
                          <div key={`w-${i}`} className="import-warnings">{message}</div>
                        ))}
                      </td>
                      <td>
                        <button type="button" className="icon-btn icon-btn--danger"
                          aria-label={`Remove row ${row.row_number}`}
                          onClick={() => removeRow(index)}>
                          <Trash2 size={15} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <Checkbox checked={overwrite} onChange={setOverwrite}
            label="Overwrite existing stock for matching products"
            hint="Usually off. If a barcode already exists, we keep its current price and stock. Turn this on only when this file should replace the stock count of products you already have." />

          <div className="import-actions">
            <Button variant="secondary" size="sm" icon={<RotateCcw size={15} />} onClick={reset}>
              Choose another file
            </Button>
            <Button size="sm" icon={<Upload size={15} />} loading={committing}
              disabled={validCount === 0} onClick={() => void commit()}>
              {committing ? 'Importing…' : `Import ${validCount} valid product${validCount === 1 ? '' : 's'}`}
            </Button>
          </div>
        </>
      )}

      {summary && (
        <div className="import-summary">
          <div className="import-summary__title">
            <CheckCircle2 size={17} /> Import finished
          </div>
          <div className="import-summary__stats">
            <span><strong>{summary.created}</strong> created</span>
            <span><strong>{summary.updated}</strong> updated</span>
            <span><strong>{summary.skipped}</strong> skipped</span>
          </div>
          {summary.errors.length > 0 && (
            <div className="import-summary__errors">
              {summary.errors.map((entry, i) => (
                <div key={i}>Row {entry.row}: {entry.message}</div>
              ))}
            </div>
          )}
          <p className="import-note">Your product list has been refreshed.</p>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Barcode tab                                                         */
/* ------------------------------------------------------------------ */

interface DetectedCode {
  rawValue: string;
}
interface BarcodeDetectorLike {
  detect(source: HTMLVideoElement): Promise<DetectedCode[]>;
}
type BarcodeDetectorCtor = new (options?: { formats?: string[] }) => BarcodeDetectorLike;

function BarcodeImport({ onImported }: { onImported: () => void }) {
  const toast = useToast();
  const { business } = useAuth();
  const [code, setCode] = useState('');
  const [draft, setDraft] = useState<ProductDraft>(emptyDraft);
  const [state, setState] = useState<'idle' | 'looking' | 'ready'>('idle');
  const [source, setSource] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [cameraOn, setCameraOn] = useState(false);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const rafRef = useRef<number | null>(null);

  const DetectorCtor = (window as unknown as { BarcodeDetector?: BarcodeDetectorCtor }).BarcodeDetector;
  const canScanCamera = Boolean(DetectorCtor && navigator.mediaDevices?.getUserMedia);

  function stopCamera() {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setCameraOn(false);
  }

  useEffect(() => () => {
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    streamRef.current?.getTracks().forEach((track) => track.stop());
  }, []);

  useEffect(() => {
    if (!cameraOn || !DetectorCtor) return;
    const video = videoRef.current;
    const stream = streamRef.current;
    if (!video || !stream) return;
    video.srcObject = stream;
    void video.play().catch(() => undefined);
    const detector = new DetectorCtor({
      formats: ['ean_13', 'ean_8', 'upc_a', 'upc_e', 'code_128', 'code_39', 'qr_code'],
    });
    let cancelled = false;
    const tick = async () => {
      if (cancelled) return;
      try {
        const found = await detector.detect(video);
        if (found.length > 0) {
          const value = found[0].rawValue;
          stopCamera();
          setCode(value);
          void lookup(value);
          return;
        }
      } catch {
        // Keep trying until the camera is stopped.
      }
      if (!cancelled) rafRef.current = requestAnimationFrame(() => void tick());
    };
    void tick();
    return () => {
      cancelled = true;
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
    // `lookup` is intentionally read from the current render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cameraOn]);

  function prefill(name: string, barcode: string, category: string, from: string) {
    // Prices and stock are never invented — the person enters them.
    setDraft({
      ...emptyDraft(),
      name,
      barcode,
      category,
      openingStock: '',
      sellingPrice: '',
      costPrice: '',
    });
    setSource(from);
    setState('ready');
  }

  async function lookup(value: string) {
    const scanned = value.trim();
    if (!scanned) return;
    setError('');
    setState('looking');
    setSource('');
    try {
      const product = await api.get<Product>(`/products/barcode/${encodeURIComponent(scanned)}`);
      prefill(product.name, product.barcode ?? scanned, product.description ?? '', 'Found in your products');
      return;
    } catch (err) {
      if (!(err instanceof ApiError) || err.status !== 404) {
        setError(errorText(err, 'We could not check that barcode. Please try again.'));
        setState('idle');
        return;
      }
    }
    try {
      const result = await api.get<BarcodeLookupResponse>(
        `/products/barcode/lookup/${encodeURIComponent(scanned)}`,
      );
      if (result.found) {
        const category = [result.brand, result.category].filter(Boolean).join(' · ');
        prefill(result.name ?? '', result.barcode || scanned, category, result.source || 'Product catalogue');
        return;
      }
      setDraft({ ...emptyDraft(), barcode: scanned });
      setSource(result.message || 'Not found in any catalogue.');
      setState('ready');
    } catch (err) {
      setDraft({ ...emptyDraft(), barcode: scanned });
      setSource('Not found in any catalogue.');
      setState('ready');
      setError(errorText(err, 'Catalogue lookup was unavailable. You can still add the product yourself.'));
    }
  }

  async function startCamera() {
    if (!canScanCamera) {
      setError('Camera scanning is not available here. A USB scanner or typing works too.');
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' } });
      streamRef.current = stream;
      setError('');
      setCameraOn(true);
    } catch {
      setError('We could not open the camera. You can still type or scan the barcode.');
    }
  }

  function reset() {
    stopCamera();
    setCode('');
    setDraft(emptyDraft());
    setSource('');
    setState('idle');
    setError('');
  }

  function set(field: keyof ProductDraft, value: string) {
    setDraft((current) => ({ ...current, [field]: value }));
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!draft.name.trim()) {
      setError('Please enter a product name.');
      return;
    }
    if (draft.sellingPrice.trim() === '' || Number(draft.sellingPrice) < 0) {
      setError('Please enter a selling price.');
      return;
    }
    if (draft.openingStock.trim() === '' || Number(draft.openingStock) < 0) {
      setError('Please enter the opening stock (0 is fine).');
      return;
    }
    setSaving(true);
    setError('');
    try {
      await api.post<Product>('/products', buildProductPayload(draft, business?.default_gst_rate ?? 18));
      toast.success(`${draft.name.trim()} was added.`);
      onImported();
      reset();
    } catch (err) {
      setError(errorText(err, 'The product could not be saved.'));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="form-stack">
      <p className="import-intro">
        Scan a barcode with a USB scanner (it types and presses Enter for you), or type the number
        and press Enter. We will check your products first, then a public catalogue.
      </p>

      <form className="import-scanner" onSubmit={(event) => {
        event.preventDefault();
        void lookup(code);
      }}>
        <Field label="Barcode" hint="Press Enter after scanning.">
          <div className="import-scanner-row">
            <Input className="import-scanner-input" autoFocus inputMode="numeric" value={code}
              placeholder="Scan or type a barcode…" aria-label="Barcode"
              onChange={(event) => setCode(event.target.value)} />
            <Button type="submit" size="sm" icon={<ScanLine size={15} />} disabled={!code.trim() || state === 'looking'}>
              Look up
            </Button>
          </div>
        </Field>
      </form>

      {state === 'looking' && <Loader label="Looking up this barcode…" />}
      {error && <div className="alert alert--error"><AlertCircle size={16} /> {error}</div>}

      {canScanCamera ? (
        <>
          {cameraOn && <video ref={videoRef} className="import-camera" playsInline muted />}
          <div className="import-actions">
            <Button variant="secondary" size="sm" icon={<Camera size={15} />}
              onClick={() => (cameraOn ? stopCamera() : void startCamera())}>
              {cameraOn ? 'Stop camera' : 'Scan with camera'}
            </Button>
          </div>
        </>
      ) : (
        <p className="import-note">
          <Keyboard size={14} /> Camera scanning is not available in this browser. Use a USB scanner
          or type the barcode instead.
        </p>
      )}

      {source && state !== 'looking' && (
        <div className="import-source"><Package size={14} /> {source}</div>
      )}

      {state === 'ready' && (
        <form onSubmit={(event) => void save(event)} className="form-stack">
          <div className="import-section-title">Add this product</div>
          <p className="import-note">Check the details below. Prices are always up to you.</p>
          {productFormFields(draft, set, { lockBarcode: false })}
          <div className="import-actions">
            <Button variant="secondary" size="sm" icon={<RotateCcw size={15} />} onClick={reset}>
              Scan another
            </Button>
            <Button type="submit" size="sm" icon={<CheckCircle2 size={15} />} loading={saving}>
              Save product
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Photo / PDF tab                                                     */
/* ------------------------------------------------------------------ */

interface OcrEditableRow {
  row_number: number;
  name: string;
  quantity: string;
  confidence: number;
  uncertain_fields: string[];
  raw_line: string;
}

function OcrImport({ onImported }: { onImported: () => void }) {
  const toast = useToast();
  const [fileKey, setFileKey] = useState(0);
  const [rows, setRows] = useState<OcrEditableRow[]>([]);
  const [fileName, setFileName] = useState('');
  const [source, setSource] = useState('');
  const [reading, setReading] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [summary, setSummary] = useState<ProductImportCommitResponse | null>(null);
  const [error, setError] = useState('');

  async function readFile(file: File | undefined) {
    if (!file) return;
    setError('');
    setSummary(null);
    setRows([]);
    setSource('');
    setFileName(file.name);
    setReading(true);
    try {
      const result = await multipartPost<ProductOcrResponse>('/products/import/ocr', file);
      setSource(result.source);
      setRows(result.rows.map((row, index) => ({
        row_number: index + 1,
        name: row.name ?? '',
        quantity: row.quantity === null || row.quantity === undefined ? '' : String(row.quantity),
        confidence: row.confidence,
        uncertain_fields: row.uncertain_fields ?? [],
        raw_line: row.raw_line ?? '',
      })));
      if (!result.rows.length) setError('We could not read any product names from that file.');
    } catch (err) {
      setRows([]);
      if (err instanceof ApiError && err.status === 503) {
        setError('OCR is not available on this server. Please use CSV import or manual entry instead.');
      } else {
        setError(errorText(err, 'We could not read that file. Please try a clear photo or PDF.'));
      }
    } finally {
      setReading(false);
    }
  }

  function reset() {
    setRows([]);
    setFileName('');
    setSource('');
    setSummary(null);
    setError('');
    setFileKey((value) => value + 1);
  }

  function updateRow(index: number, field: 'name' | 'quantity', value: string) {
    setRows((current) => current.map((row, i) => (
      i === index ? { ...row, [field]: value } : row
    )));
  }

  function removeRow(index: number) {
    setRows((current) => current.filter((_, i) => i !== index));
  }

  async function commit() {
    const ready = rows.filter((row) => row.name.trim());
    if (!ready.length) return;
    setCommitting(true);
    setError('');
    setSummary(null);
    const commitRows: ProductImportCommitRow[] = ready.map((row) => ({
      name: row.name.trim(),
      quantity: row.quantity.trim() !== '' ? Number(row.quantity) : 0,
      selling_price: 0,
    }));
    try {
      const result = await api.post<ProductImportCommitResponse>('/products/import/commit', {
        rows: commitRows,
        overwrite_stock: false,
      });
      setSummary(result);
      toast.success(`Added ${result.created} product${result.created === 1 ? '' : 's'} from your file.`);
      onImported();
    } catch (err) {
      setError(errorText(err, 'The import could not be finished. Please try again.'));
    } finally {
      setCommitting(false);
    }
  }

  const readyCount = rows.filter((row) => row.name.trim()).length;

  return (
    <div className="form-stack">
      <p className="import-intro">
        Take a clear photo of your product list, or upload a PDF. We will read what we can and show it
        below for you to check before anything is added.
      </p>

      <div className="import-file-picker">
        <Input key={fileKey} className="import-file-input" type="file"
          accept="image/png,image/jpeg,image/webp,application/pdf" aria-label="Choose a photo or PDF"
          onChange={(event) => void readFile(event.target.files?.[0])} />
        {fileName && <span className="import-file-name">{fileName}</span>}
      </div>

      {reading && <Loader label="Reading your file…" />}
      {error && <div className="alert alert--error"><AlertCircle size={16} /> {error}</div>}
      {source && !reading && <p className="import-note">Read with {source}.</p>}

      {rows.length > 0 && !reading && (
        <>
          <div className="import-preview">
            <div className="table-scroll">
              <table className="data-table data-table--compact">
                <thead>
                  <tr>
                    <th>Row</th>
                    <th>Name</th>
                    <th>Qty</th>
                    <th>Check</th>
                    <th aria-label="Remove" />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, index) => (
                    <tr key={row.row_number}>
                      <td className="mono small">{row.row_number}</td>
                      <td>
                        <Input className="import-cell-input import-cell-input--name" value={row.name}
                          aria-label={`Name for row ${row.row_number}`}
                          onChange={(event) => updateRow(index, 'name', event.target.value)} />
                        {row.raw_line && <small className="cell-sub">“{row.raw_line}”</small>}
                      </td>
                      <td>
                        <Input className="import-cell-input import-cell-input--qty" type="number" min="0" step="1"
                          value={row.quantity} aria-label={`Quantity for row ${row.row_number}`}
                          onChange={(event) => updateRow(index, 'quantity', event.target.value)} />
                      </td>
                      <td>
                        {row.uncertain_fields.length > 0 && (
                          <span className="import-uncertain">
                            Uncertain: {row.uncertain_fields.join(', ')}
                          </span>
                        )}
                        <Badge tone={row.confidence >= 0.8 ? 'success' : 'warning'}>
                          {Math.round(row.confidence * 100)}% sure
                        </Badge>
                      </td>
                      <td>
                        <button type="button" className="icon-btn icon-btn--danger"
                          aria-label={`Remove row ${row.row_number}`}
                          onClick={() => removeRow(index)}>
                          <Trash2 size={15} />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <p className="import-note">
            Please check every row. These products are added with a selling price of 0 — add real
            prices in your catalogue later. We never guess prices.
          </p>

          <div className="import-actions">
            <Button variant="secondary" size="sm" icon={<RotateCcw size={15} />} onClick={reset}>
              Choose another file
            </Button>
            <Button size="sm" icon={<FileText size={15} />} loading={committing}
              disabled={readyCount === 0} onClick={() => void commit()}>
              {committing ? 'Importing…' : `Confirm and import ${readyCount} product${readyCount === 1 ? '' : 's'}`}
            </Button>
          </div>
        </>
      )}

      {summary && (
        <div className="import-summary">
          <div className="import-summary__title">
            <CheckCircle2 size={17} /> Import finished
          </div>
          <div className="import-summary__stats">
            <span><strong>{summary.created}</strong> created</span>
            <span><strong>{summary.updated}</strong> updated</span>
            <span><strong>{summary.skipped}</strong> skipped</span>
          </div>
          {summary.errors.length > 0 && (
            <div className="import-summary__errors">
              {summary.errors.map((entry, i) => (
                <div key={i}>Row {entry.row}: {entry.message}</div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Manual tab                                                          */
/* ------------------------------------------------------------------ */

function ManualImport({ onImported }: { onImported: () => void }) {
  const toast = useToast();
  const { business } = useAuth();
  const [draft, setDraft] = useState<ProductDraft>(emptyDraft);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  function set(field: keyof ProductDraft, value: string) {
    setDraft((current) => ({ ...current, [field]: value }));
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!draft.name.trim()) {
      setError('Please enter a product name.');
      return;
    }
    if (draft.sellingPrice.trim() === '' || Number(draft.sellingPrice) < 0) {
      setError('Please enter a selling price.');
      return;
    }
    if (draft.openingStock.trim() === '' || Number(draft.openingStock) < 0) {
      setError('Please enter the opening stock (0 is fine).');
      return;
    }
    setSaving(true);
    setError('');
    try {
      await api.post<Product>('/products', buildProductPayload(draft, business?.default_gst_rate ?? 18));
      toast.success(`${draft.name.trim()} was added.`);
      setDraft(emptyDraft());
      onImported();
    } catch (err) {
      setError(errorText(err, 'The product could not be saved.'));
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={(event) => void save(event)} className="form-stack">
      <p className="import-intro">Add one product by hand. Start with the name, price and stock.</p>
      {error && <div className="alert alert--error"><AlertCircle size={16} /> {error}</div>}
      {productFormFields(draft, set)}
      <div className="import-actions">
        <Button type="submit" icon={<CheckCircle2 size={15} />} loading={saving}>
          Add product
        </Button>
      </div>
    </form>
  );
}

/* ------------------------------------------------------------------ */
/* Root                                                                */
/* ------------------------------------------------------------------ */

type ImportTab = 'bulk' | 'barcode' | 'photo' | 'manual';

const TABS: Array<{ id: ImportTab; label: string; icon: typeof Upload }> = [
  { id: 'bulk', label: 'Bulk file', icon: FileSpreadsheet },
  { id: 'barcode', label: 'Barcode', icon: ScanLine },
  { id: 'photo', label: 'Photo / PDF', icon: FileText },
  { id: 'manual', label: 'Manual', icon: Package },
];

export function ImportProducts({ onClose, onImported }: {
  onClose: () => void;
  onImported: () => void;
}) {
  const [tab, setTab] = useState<ImportTab>('bulk');

  return (
    <div className="import-root">
      <div className="import-tabs" role="tablist" aria-label="How would you like to add products?">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button key={id} type="button" role="tab" aria-selected={tab === id}
            className={tab === id ? 'import-tab import-tab--active' : 'import-tab'}
            onClick={() => setTab(id)}>
            <Icon size={15} /> {label}
          </button>
        ))}
      </div>

      <div className="import-panel" role="tabpanel">
        {tab === 'bulk' && <BulkImport onImported={onImported} />}
        {tab === 'barcode' && <BarcodeImport onImported={onImported} />}
        {tab === 'photo' && <OcrImport onImported={onImported} />}
        {tab === 'manual' && <ManualImport onImported={onImported} />}
      </div>

      <div className="import-footer">
        <Button variant="secondary" size="sm" onClick={onClose}>Close</Button>
      </div>
    </div>
  );
}
