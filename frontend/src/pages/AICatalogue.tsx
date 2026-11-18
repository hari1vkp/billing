import { useEffect, useState } from 'react';
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Clipboard,
  Download,
  ExternalLink,
  FileSpreadsheet,
  Info,
  RotateCcw,
  Sparkles,
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
import {
  Badge,
  Button,
  Checkbox,
  Field,
  Input,
  Loader,
  Modal,
  Select,
  Textarea,
  useToast,
} from '../components/UI';
import type {
  AICategoriesResponse,
  AICategory,
  AIPromptResponse,
  ProductImportCommitResponse,
  ProductImportCommitRow,
  ProductImportParseResponse,
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

/** A service that is not configured yet gets a calm, plain-language message. */
function describeError(error: unknown, fallback: string, unavailable: string): string {
  if (error instanceof ApiError && error.status === 503) return unavailable;
  return errorText(error, fallback);
}

/* ------------------------------------------------------------------ */
/* Editable preview row (all 14 official template columns).            */
/* ------------------------------------------------------------------ */

interface AIEditableRow {
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
  gst_rate?: number;
  errors: string[];
  warnings: string[];
  valid: boolean;
}

type EditableTextField =
  | 'name'
  | 'brand'
  | 'category'
  | 'subcategory'
  | 'variant'
  | 'size_pack'
  | 'barcode'
  | 'barcode_type'
  | 'sku'
  | 'cost_price'
  | 'selling_price'
  | 'discount_type'
  | 'discount_value'
  | 'quantity';

function toEditableRow(row: ProductImportParseResponse['rows'][number]): AIEditableRow {
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

/** Re-check only the rules a person can fix by editing a cell. */
function revalidate(row: AIEditableRow): AIEditableRow {
  const errors: string[] = [];
  if (!row.name.trim()) errors.push('A product name is needed.');
  const selling = row.selling_price.trim();
  if (selling === '' || !Number.isFinite(Number(selling)) || Number(selling) < 0) {
    errors.push('Add a selling price (0 is fine). We never guess prices.');
  }
  const quantity = row.quantity.trim();
  if (quantity !== '' && (!Number.isFinite(Number(quantity)) || Number(quantity) < 0)) {
    errors.push('Opening stock cannot be negative.');
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

const STEPS = [
  { number: 1, label: 'Business type' },
  { number: 2, label: 'Generate prompt' },
  { number: 3, label: 'Your prompt' },
  { number: 4, label: 'Copy & open' },
  { number: 5, label: 'How it works' },
  { number: 6, label: 'Upload file' },
  { number: 7, label: 'Review & import' },
];

const DISCOUNT_TYPES = ['none', 'percent', 'flat'];

export function AICatalogue({ open, onClose, onImported }: {
  open: boolean;
  onClose: () => void;
  onImported?: () => void;
}) {
  const toast = useToast();
  const { business } = useAuth();

  const [step, setStep] = useState(1);
  const [categories, setCategories] = useState<AICategory[]>([]);
  const [categoriesLoaded, setCategoriesLoaded] = useState(false);
  const [categoriesLoading, setCategoriesLoading] = useState(false);
  const [categoriesError, setCategoriesError] = useState('');
  const [categoryId, setCategoryId] = useState('');
  const [businessName, setBusinessName] = useState('');
  const [extraNotes, setExtraNotes] = useState('');
  const [prompt, setPrompt] = useState('');
  const [generating, setGenerating] = useState(false);
  const [promptError, setPromptError] = useState('');
  const [fileKey, setFileKey] = useState(0);
  const [fileName, setFileName] = useState('');
  const [parsing, setParsing] = useState(false);
  const [parseError, setParseError] = useState('');
  const [rows, setRows] = useState<AIEditableRow[]>([]);
  const [overwrite, setOverwrite] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [commitError, setCommitError] = useState('');
  const [summary, setSummary] = useState<ProductImportCommitResponse | null>(null);

  /* A fresh wizard each time it is opened. `business` is read at open time. */
  useEffect(() => {
    if (!open) return;
    setStep(1);
    setCategoryId('');
    setBusinessName(business?.name ?? '');
    setExtraNotes('');
    setPrompt('');
    setGenerating(false);
    setPromptError('');
    setFileKey((value) => value + 1);
    setFileName('');
    setParsing(false);
    setParseError('');
    setRows([]);
    setOverwrite(false);
    setCommitting(false);
    setCommitError('');
    setSummary(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    if (!open || categoriesLoaded) return;
    let active = true;
    setCategoriesError('');
    setCategoriesLoading(true);
    api.get<AICategoriesResponse>('/products/ai/categories')
      .then((result) => {
        if (active) setCategories(result.categories ?? []);
      })
      .catch((error) => {
        if (active) setCategoriesError(errorText(error, 'We could not load the business types.'));
      })
      .finally(() => {
        if (active) {
          setCategoriesLoading(false);
          setCategoriesLoaded(true);
        }
      });
    return () => {
      active = false;
    };
  }, [open, categoriesLoaded]);

  const selectedCategory = categories.find((category) => category.id === categoryId);
  const validCount = rows.filter((row) => row.valid).length;
  const canAdvance = step === 1
    ? Boolean(categoryId)
    : step === 2
      ? Boolean(prompt)
      : step === 6
        ? rows.length > 0
        : step === 7
          ? false
          : true;

  function goBack() {
    setStep((current) => Math.max(1, current - 1));
  }

  function goNext() {
    setStep((current) => Math.min(7, current + 1));
  }

  async function generatePrompt() {
    if (!categoryId) {
      setPromptError('Choose a business type first.');
      return;
    }
    setGenerating(true);
    setPromptError('');
    try {
      const result = await api.post<AIPromptResponse>('/products/ai/prompt', {
        category_id: categoryId,
        ...(businessName.trim() ? { business_name: businessName.trim() } : {}),
        ...(extraNotes.trim() ? { extra_notes: extraNotes.trim() } : {}),
      });
      setPrompt(result.prompt ?? '');
      setStep(3);
    } catch (error) {
      setPromptError(describeError(
        error,
        'We could not create your prompt. Please try again.',
        'Prompt creation is not available on this server right now. Please try again shortly.',
      ));
    } finally {
      setGenerating(false);
    }
  }

  async function copyPrompt() {
    try {
      if (!navigator.clipboard?.writeText) {
        throw new Error('Clipboard access is not available here. Select the text and copy it yourself.');
      }
      await navigator.clipboard.writeText(prompt);
      toast.success('Prompt copied. Paste it into your AI assistant.');
    } catch (error) {
      toast.error(errorText(error, 'We could not copy the prompt. Select the text and copy it yourself.'));
    }
  }

  async function downloadTemplate() {
    try {
      await downloadFile('/products/import/template', 'billflow-product-catalogue-template.csv');
      toast.success('Product catalogue template downloaded.');
    } catch (error) {
      toast.error(errorText(error, 'We could not download the template. Please try again.'));
    }
  }

  async function pickFile(file: File | undefined) {
    if (!file) return;
    setParseError('');
    setSummary(null);
    setRows([]);
    setFileName(file.name);
    setParsing(true);
    try {
      const result = await multipartPost<ProductImportParseResponse>('/products/import/parse', file);
      setRows(result.rows.map(toEditableRow));
      if (!result.rows.length) {
        setParseError('We could not find any products in that file. Check it against the template and try again.');
      } else {
        setStep(7);
      }
    } catch (error) {
      setRows([]);
      setParseError(describeError(
        error,
        'We could not read that file. Please check it and try again.',
        'File reading is not available on this server right now. Please try again shortly.',
      ));
    } finally {
      setParsing(false);
    }
  }

  function resetFile() {
    setRows([]);
    setFileName('');
    setParseError('');
    setSummary(null);
    setOverwrite(false);
    setFileKey((value) => value + 1);
    setStep(6);
  }

  function updateRow(index: number, field: EditableTextField, value: string) {
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
    setCommitError('');
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
      ...(row.gst_rate !== undefined ? { gst_rate: row.gst_rate } : {}),
    }));
    try {
      const result = await api.post<ProductImportCommitResponse>('/products/import/commit', {
        rows: commitRows,
        overwrite_stock: overwrite,
      });
      setSummary(result);
      toast.success(`Imported ${result.created} new product${result.created === 1 ? '' : 's'}.`);
      onImported?.();
    } catch (error) {
      setCommitError(describeError(
        error,
        'The import could not be finished. Please try again.',
        'Importing is not available on this server right now. Please try again shortly.',
      ));
    } finally {
      setCommitting(false);
    }
  }

  function editableCell(
    index: number,
    row: AIEditableRow,
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

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Create products with AI"
      subtitle="A guided setup: BillFlow writes the prompt, you use your own AI assistant."
      size="xl"
    >
      <div className="ai-wizard">
        <div className="ai-steps" aria-label="Setup progress">
          {STEPS.map(({ number, label }) => {
            const state = number === step ? 'active' : number < step ? 'done' : 'todo';
            return (
              <button
                key={number}
                type="button"
                className={`ai-step ai-step--${state}`}
                disabled={number > step}
                aria-current={number === step ? 'step' : undefined}
                onClick={() => setStep(number)}
              >
                <span className="ai-step__num">{number < step ? '✓' : number}</span>
                <span className="ai-step__label">{label}</span>
              </button>
            );
          })}
        </div>

        <div className="ai-content">
          {step === 1 && (
            <div className="ai-step-pane">
              <h3 className="ai-heading">1. What kind of business do you run?</h3>
              <p className="ai-lead">Pick the closest match — the prompt will be written for that kind of shop.</p>
              <Field label="Business type" required
                hint="This only shapes the prompt. No products are generated inside BillFlow.">
                <Select value={categoryId} disabled={categoriesLoading || Boolean(categoriesError)}
                  onChange={(event) => setCategoryId(event.target.value)}>
                  <option value="">Choose a business type…</option>
                  {categories.map((category) => (
                    <option key={category.id} value={category.id}>{category.label}</option>
                  ))}
                </Select>
              </Field>
              {categoriesLoading && <Loader label="Loading business types…" />}
              {categoriesError && (
                <div className="alert alert--error">
                  <AlertCircle size={16} />
                  <span>{categoriesError}</span>
                  <Button size="sm" variant="secondary" onClick={() => setCategoriesLoaded(false)}>
                    Try again
                  </Button>
                </div>
              )}
              {selectedCategory?.description && (
                <div className="ai-note"><Info size={15} /><span>{selectedCategory.description}</span></div>
              )}
            </div>
          )}

          {step === 2 && (
            <div className="ai-step-pane">
              <h3 className="ai-heading">2. Create your prompt</h3>
              <p className="ai-lead">We'll write a ready-to-copy prompt you can paste into any AI assistant.</p>
              <Field label="Business name (optional)">
                <Input value={businessName} placeholder="e.g. Sharma General Store"
                  onChange={(event) => setBusinessName(event.target.value)} />
              </Field>
              <Field label="Anything else to include? (optional)"
                hint="For example: brands you stock, your city, or the sizes you sell.">
                <Textarea rows={3} value={extraNotes} placeholder="Add any extra instructions here…"
                  onChange={(event) => setExtraNotes(event.target.value)} />
              </Field>
              {promptError && (
                <div className="alert alert--error"><AlertCircle size={16} /> {promptError}</div>
              )}
              <div className="ai-actions">
                <Button icon={<Sparkles size={15} />} loading={generating} disabled={!categoryId}
                  onClick={() => void generatePrompt()}>
                  {generating ? 'Creating prompt…' : 'Generate prompt'}
                </Button>
                {prompt && (
                  <Button variant="secondary" icon={<CheckCircle2 size={15} />} onClick={goNext}>
                    Prompt ready — continue
                  </Button>
                )}
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="ai-step-pane">
              <h3 className="ai-heading">3. Your ready-to-copy prompt</h3>
              <p className="ai-lead">This prompt tells an AI assistant exactly which product list to create for you.</p>
              <Textarea className="ai-prompt" readOnly rows={14} value={prompt}
                aria-label="Generated product catalogue prompt" />
              <div className="ai-note">
                <Info size={15} />
                <span>It's just text. In the next step you can copy it and open an official AI website.</span>
              </div>
            </div>
          )}

          {step === 4 && (
            <div className="ai-step-pane">
              <h3 className="ai-heading">4. Copy the prompt and open an AI assistant</h3>
              <p className="ai-lead">Use any assistant you like. We only open their websites — nothing runs inside BillFlow.</p>
              <div className="ai-actions">
                <Button variant="secondary" icon={<Clipboard size={15} />}
                  onClick={() => void copyPrompt()}>Copy prompt</Button>
                <a className="btn btn--secondary btn--md ai-action-link"
                  href="https://chatgpt.com/" target="_blank" rel="noopener noreferrer">
                  <ExternalLink size={15} /> Open ChatGPT
                </a>
                <a className="btn btn--secondary btn--md ai-action-link"
                  href="https://gemini.google.com/" target="_blank" rel="noopener noreferrer">
                  <ExternalLink size={15} /> Open Gemini
                </a>
              </div>
              <div className="ai-actions">
                <Button variant="secondary" icon={<Download size={15} />}
                  onClick={() => void downloadTemplate()}>
                  Download BillFlow Excel Template
                </Button>
              </div>
              <div className="ai-note">
                <Info size={15} />
                <span>
                  No AI account is connected to BillFlow. These buttons only open the official websites in a
                  new tab — you do the copying and pasting yourself.
                </span>
              </div>
            </div>
          )}

          {step === 5 && (
            <div className="ai-step-pane">
              <h3 className="ai-heading">5. What you do next</h3>
              <p className="ai-lead ai-instructions">
                Copy the prompt, paste it into your preferred AI assistant, ask it to generate the product
                catalogue, download the Excel/CSV file, and upload it here.
              </p>
              <div className="ai-note">
                <Info size={15} />
                <span>
                  The assistant will give you a file with the BillFlow columns. Leave any price you don't
                  know blank — we will never invent one for you.
                </span>
              </div>
            </div>
          )}

          {step === 6 && (
            <div className="ai-step-pane">
              <h3 className="ai-heading">6. Upload the file you downloaded</h3>
              <p className="ai-lead">Choose the .csv, .xlsx or .xls file. We'll read it and show every row for you to check.</p>
              <div className="ai-upload">
                <FileSpreadsheet size={22} />
                <Input key={fileKey} className="import-file-input" type="file"
                  accept=".csv,.xlsx,.xls" aria-label="Choose your product catalogue file"
                  onChange={(event) => void pickFile(event.target.files?.[0])} />
                {fileName && <span className="import-file-name">{fileName}</span>}
              </div>
              {parsing && <Loader label={`Reading ${fileName || 'your file'}…`} />}
              {parseError && (
                <div className="alert alert--error"><AlertCircle size={16} /> {parseError}</div>
              )}
              {rows.length > 0 && !parsing && (
                <div className="ai-note">
                  <CheckCircle2 size={15} />
                  <span>Found {rows.length} product{rows.length === 1 ? '' : 's'}. Review them in the next step.</span>
                </div>
              )}
              {fileName && !parsing && (
                <Button variant="ghost" size="sm" icon={<RotateCcw size={15} />} onClick={resetFile}>
                  Choose another file
                </Button>
              )}
            </div>
          )}

          {step === 7 && (
            <div className="ai-step-pane">
              <h3 className="ai-heading">7. Check everything, then import</h3>
              <p className="ai-lead">
                Edit any cell, remove rows you don't want, then import the ready ones. Blank prices stay blank.
              </p>
              {commitError && (
                <div className="alert alert--error"><AlertCircle size={16} /> {commitError}</div>
              )}
              {rows.length === 0 ? (
                <div className="alert alert--info">
                  <Info size={16} /> No rows to review yet. Go back to step 6 and upload your file.
                </div>
              ) : (
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
                              {editableCell(index, row, 'name', 'Name', { className: 'import-cell-input--name' })}
                              {editableCell(index, row, 'brand', 'Brand')}
                              {editableCell(index, row, 'category', 'Category')}
                              {editableCell(index, row, 'subcategory', 'Subcategory')}
                              {editableCell(index, row, 'variant', 'Variant')}
                              {editableCell(index, row, 'size_pack', 'Size / Pack')}
                              {editableCell(index, row, 'barcode', 'Barcode')}
                              {editableCell(index, row, 'barcode_type', 'Barcode type')}
                              {editableCell(index, row, 'sku', 'SKU')}
                              {editableCell(index, row, 'cost_price', 'Cost', { type: 'number', min: '0', step: '0.01' })}
                              {editableCell(index, row, 'selling_price', 'Selling price', { type: 'number', min: '0', step: '0.01' })}
                              <td>
                                <Select className="import-cell-input ai-cell-select" value={row.discount_type}
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
                              {editableCell(index, row, 'discount_value', 'Discount value', { type: 'number', min: '0', step: '0.01' })}
                              {editableCell(index, row, 'quantity', 'Opening stock', { type: 'number', min: '0', step: '1', className: 'import-cell-input--qty' })}
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
                    hint="Usually off. If a barcode already exists, we keep its price and stock. Turn this on only when this file should replace stock counts you already have." />

                  <div className="ai-nav">
                    <Button variant="secondary" size="sm" icon={<RotateCcw size={15} />} onClick={resetFile}>
                      Choose another file
                    </Button>
                    <Button size="sm" icon={<Upload size={15} />} loading={committing}
                      disabled={validCount === 0 || Boolean(summary)} onClick={() => void commit()}>
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
                  <div className="ai-nav ai-nav--end">
                    <Button size="sm" onClick={onClose}>Done</Button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {step !== 7 && (
          <div className="ai-nav">
            <Button variant="ghost" size="sm" icon={<ArrowLeft size={15} />}
              disabled={step === 1} onClick={goBack}>Back</Button>
            <Button size="sm" icon={<ArrowRight size={15} />}
              disabled={!canAdvance} onClick={goNext}>Continue</Button>
          </div>
        )}
      </div>
    </Modal>
  );
}
