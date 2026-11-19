import { useCallback, useEffect, useMemo, useState, type FormEvent } from 'react';
import {
  ArrowUpRight,
  CalendarDays,
  Check,
  CheckCircle2,
  ClipboardList,
  Info,
  Mail,
  MessageCircle,
  Package,
  Pencil,
  Phone,
  Plus,
  PowerOff,
  Search,
  Trash2,
  Truck,
} from 'lucide-react';
import { api, ApiError } from '../api/client';
import { useAuth } from '../context/AuthContext';
import {
  Badge,
  Button,
  Card,
  Checkbox,
  ConfirmDialog,
  Drawer,
  EmptyState,
  Field,
  Input,
  Loader,
  Modal,
  PageHeader,
  Pagination,
  Select,
  StatusBadge,
  Textarea,
  formatDate,
  initials,
  money,
  todayInput,
  useToast,
} from '../components/UI';
import type {
  MessageResponse,
  Paginated,
  Product,
  QuickReminderPayload,
  SupplierPurchaseConversion,
  PurchaseReminderItem,
  PurchaseReminderItemInput,
  PurchaseReminderList,
  Supplier,
  SupplierCategorySuggestions,
  SupplierDetail,
  SupplierInput,
  SupplierProduct,
  SupplierProductInput,
  SupplierVisit,
  SupplierVisitInput,
} from '../types';

const PAGE_SIZE = 10;

/** Clearly labelled examples — never used as hard-coded taxonomy values. */
const EXAMPLE_INDUSTRIES =
  'Examples only — grocery, clothing, electronics, hardware, pharmacy, furniture.';

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

/**
 * Item-level supplier routes can be shaped either as
 * `/suppliers/{resource}/{id}` or `/suppliers/{id}/{resource}/{id}`. Try both
 * so the UI keeps working while the API rollout settles.
 */
async function patchOrDelete<T>(
  paths: string[],
  method: 'patch' | 'delete',
  body?: unknown,
): Promise<T> {
  let lastError: unknown;
  for (const path of paths) {
    try {
      return method === 'patch'
        ? await api.patch<T>(path, body)
        : await api.delete<T>(path);
    } catch (error) {
      lastError = error;
      const status = error instanceof ApiError ? error.status : 0;
      if (status !== 404 && status !== 405) break;
    }
  }
  throw lastError;
}

function normalizeSuggestions(
  response: SupplierCategorySuggestions | string[] | null | undefined,
): SupplierCategorySuggestions {
  if (Array.isArray(response)) return { categories: response, brands: [], product_types: [] };
  if (!response) return {};
  return response.data ?? response;
}

function SuggestionsDatalist({ id, values }: { id: string; values?: string[] }) {
  return (
    <datalist id={id}>
      {(values ?? []).map((value) => (
        <option key={value} value={value} />
      ))}
    </datalist>
  );
}

/* ------------------------------------------------------------------ */
/* Existing-product picker (never creates inventory products)           */
/* ------------------------------------------------------------------ */

function ProductSourceFields({
  products,
  productId,
  customName,
  onProductId,
  onCustomName,
}: {
  products: Product[];
  productId: string;
  customName: string;
  onProductId: (value: string) => void;
  onCustomName: (value: string) => void;
}) {
  return (
    <div className="supplier-source">
      <Select
        value={productId}
        onChange={(event) => onProductId(event.target.value)}
        aria-label="Choose an existing product or a custom item"
      >
        <option value="">Custom item — type a name</option>
        {products.map((product) => (
          <option key={product.id} value={product.id}>
            {product.name}
            {product.sku ? ` · ${product.sku}` : ''}
          </option>
        ))}
      </Select>
      {!productId && (
        <Input
          value={customName}
          onChange={(event) => onCustomName(event.target.value)}
          placeholder="Custom item name (not added to inventory)"
          aria-label="Custom item name"
        />
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Supplier create / edit form                                          */
/* ------------------------------------------------------------------ */

function SupplierForm({
  open,
  onClose,
  initial,
  suggestions,
  idPrefix,
  onSaved,
}: {
  open: boolean;
  onClose: () => void;
  initial: Supplier | null;
  suggestions: SupplierCategorySuggestions;
  idPrefix: string;
  onSaved: () => void;
}) {
  const toast = useToast();
  const [form, setForm] = useState<SupplierInput>({});
  const [saving, setSaving] = useState(false);
  const [catalog, setCatalog] = useState<Product[]>([]);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [productSearch, setProductSearch] = useState('');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [existingLinks, setExistingLinks] = useState<SupplierProduct[]>([]);

  useEffect(() => {
    if (!open) return;
    let active = true;
    setProductSearch('');
    setSelectedIds([]);
    setExistingLinks([]);
    setCatalogLoading(true);
    api.get<Paginated<Product>>('/products', { page_size: 200 })
      .then((response) => { if (active) setCatalog(response.items); })
      .catch(() => { /* catalogue remains empty; supplier details still editable */ })
      .finally(() => { if (active) setCatalogLoading(false); });
    if (initial?.id) {
      api.get<SupplierProduct[] | { items: SupplierProduct[] }>(`/suppliers/${initial.id}/products`)
        .then((response) => {
          if (!active) return;
          const links = Array.isArray(response) ? response : (response.items ?? []);
          setExistingLinks(links);
          setSelectedIds(
            links.map((link) => link.product_id).filter((id): id is string => Boolean(id)),
          );
        })
        .catch(() => { /* keep associations unchanged if they cannot be loaded */ });
    }
    return () => { active = false; };
  }, [open, initial?.id]);

  useEffect(() => {
    if (!open) return;
    setForm(
      initial
        ? {
            name: initial.name,
            contact_person: initial.contact_person ?? '',
            phone: initial.phone ?? '',
            whatsapp: initial.whatsapp ?? '',
            email: initial.email ?? '',
            address: initial.address ?? '',
            category: initial.category ?? '',
            brands: initial.brands ?? '',
            notes: initial.notes ?? '',
            is_active: initial.is_active,
          }
        : {
            name: '',
            contact_person: '',
            phone: '',
            whatsapp: '',
            email: '',
            address: '',
            category: '',
            brands: '',
            notes: '',
            is_active: true,
          },
    );
  }, [open, initial]);

  function set(field: keyof SupplierInput, value: string | boolean) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  const filteredCatalog = useMemo(() => {
    const term = productSearch.trim().toLowerCase();
    if (!term) return catalog;
    return catalog.filter((product) =>
      [product.name, product.sku, product.barcode].some((value) =>
        (value ?? '').toLowerCase().includes(term),
      ),
    );
  }, [catalog, productSearch]);

  function toggleProduct(productId: string) {
    setSelectedIds((previous) =>
      previous.includes(productId)
        ? previous.filter((id) => id !== productId)
        : [...previous, productId],
    );
  }

  // Associations only — never create or modify inventory products here.
  async function syncProducts(supplierId: string) {
    const previousIds = existingLinks
      .map((link) => link.product_id)
      .filter((id): id is string => Boolean(id));
    for (const link of existingLinks) {
      if (link.product_id && !selectedIds.includes(link.product_id)) {
        await patchOrDelete<void>(
          [`/suppliers/products/${link.id}`, `/suppliers/${supplierId}/products/${link.id}`],
          'delete',
        );
      }
    }
    for (const productId of selectedIds) {
      if (!previousIds.includes(productId)) {
        await api.post(`/suppliers/${supplierId}/products`, { product_id: productId });
      }
    }
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!form.name?.trim()) {
      toast.error('Supplier / company name is required.');
      return;
    }
    const payload: SupplierInput = {
      ...form,
      name: form.name.trim(),
      contact_person: form.contact_person?.trim() || undefined,
      phone: form.phone?.trim() || undefined,
      whatsapp: form.whatsapp?.trim() || undefined,
      email: form.email?.trim() || undefined,
      address: form.address?.trim() || undefined,
      category: form.category?.trim() || undefined,
      brands: form.brands?.trim() || undefined,
      notes: form.notes?.trim() || undefined,
    };
    setSaving(true);
    try {
      const saved = initial
        ? await api.patch<Supplier>(`/suppliers/${initial.id}`, payload)
        : await api.post<Supplier>('/suppliers', payload);
      await syncProducts(saved.id);
      toast.success(initial ? 'Supplier updated.' : 'Supplier added.');
      onSaved();
    } catch (error) {
      toast.error(errorMessage(error, 'Could not save the supplier.'));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={initial ? 'Edit supplier' : 'Add a supplier'}
      subtitle="Only the supplier / company name is required. Everything else is optional."
      size="lg"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" form="supplier-form" loading={saving}>
            {initial ? 'Save changes' : 'Add supplier'}
          </Button>
        </>
      }
    >
      <form id="supplier-form" onSubmit={save} className="form-stack">
        <Field label="Supplier / company name" required>
          <Input required value={form.name ?? ''} placeholder="e.g. your supplier or company name"
            onChange={(event) => set('name', event.target.value)} />
        </Field>

        <div className="form-grid form-grid--2">
          <Field label="Contact person">
            <Input value={form.contact_person ?? ''} placeholder="Who do you usually talk to?"
              onChange={(event) => set('contact_person', event.target.value)} />
          </Field>
          <Field label="Email">
            <Input type="email" value={form.email ?? ''} placeholder="name@example.com"
              onChange={(event) => set('email', event.target.value)} />
          </Field>
        </div>

        <div className="form-grid form-grid--2">
          <Field label="Phone">
            <Input type="tel" value={form.phone ?? ''} placeholder="+91 98765 43210"
              onChange={(event) => set('phone', event.target.value)} />
          </Field>
          <Field label="WhatsApp">
            <Input type="tel" value={form.whatsapp ?? ''} placeholder="Optional WhatsApp number"
              onChange={(event) => set('whatsapp', event.target.value)} />
          </Field>
        </div>

        <Field label="Address">
          <Textarea rows={2} value={form.address ?? ''} placeholder="Street, area, city…"
            onChange={(event) => set('address', event.target.value)} />
        </Field>

        <div className="form-grid form-grid--2">
          <Field label="Category" hint={`${EXAMPLE_INDUSTRIES} Type your own.`}>
            <Input list={`${idPrefix}-category-options`} value={form.category ?? ''}
              placeholder="Type a category…"
              onChange={(event) => set('category', event.target.value)} />
          </Field>
          <Field label="Brands" hint={`${EXAMPLE_INDUSTRIES} Separate several brands with commas.`}>
            <Input list={`${idPrefix}-brand-options`} value={form.brands ?? ''}
              placeholder="Type brand names…"
              onChange={(event) => set('brands', event.target.value)} />
          </Field>
        </div>
        <SuggestionsDatalist id={`${idPrefix}-category-options`} values={suggestions.categories} />
        <SuggestionsDatalist id={`${idPrefix}-brand-options`} values={suggestions.brands} />

        <div className="supplier-products-section">
          <div className="supplier-section-head">
            <h4>Products Supplied</h4>
            <span className="muted small">
              {selectedIds.length} selected · only these appear in this supplier's purchase reminders
            </span>
          </div>
          <Input
            value={productSearch}
            onChange={(event) => setProductSearch(event.target.value)}
            placeholder="Search your store products by name, SKU or barcode…"
            aria-label="Search store products"
          />
          {catalogLoading ? (
            <Loader label="Loading products…" />
          ) : filteredCatalog.length ? (
            <div className="supplier-catalog-scroll">
              <div className="supplier-card-grid supplier-card-grid--compact">
                {filteredCatalog.map((product) => {
                  const isSelected = selectedIds.includes(product.id);
                  return (
                    <button
                      type="button"
                      key={product.id}
                      aria-pressed={isSelected}
                      className={
                        isSelected
                          ? 'supplier-product-card supplier-product-card--selected'
                          : 'supplier-product-card'
                      }
                      onClick={() => toggleProduct(product.id)}
                    >
                      <span className="supplier-card__name">{product.name}</span>
                      {product.sku && <span className="supplier-card__meta">{product.sku}</span>}
                      <span className="supplier-card__footer">
                        <span className="supplier-card__unit">{product.unit ?? 'pcs'}</span>
                        {isSelected && (
                          <span className="supplier-card__selected">
                            <Check size={12} /> Selected
                          </span>
                        )}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          ) : (
            <p className="muted small">No store products found. Add products in Inventory first.</p>
          )}
          <p className="supplier-help">
            Choose products this supplier provides. Tap a selected card again to remove it.
            No new product records are created here.
          </p>
        </div>

        <Field label="Notes (optional)">
          <Textarea rows={2} value={form.notes ?? ''} placeholder="Payment terms, delivery details…"
            onChange={(event) => set('notes', event.target.value)} />
        </Field>

        <Checkbox
          checked={Boolean(form.is_active)}
          onChange={(checked) => set('is_active', checked)}
          label="Active supplier"
          hint="Turn this off to deactivate without deleting the record or its history."
        />
      </form>
    </Modal>
  );
}

/* ------------------------------------------------------------------ */
/* Products tab                                                         */
/* ------------------------------------------------------------------ */

function ProductsTab({
  supplierId,
  links,
  catalog,
  currency,
  reload,
}: {
  supplierId: string;
  links: SupplierProduct[];
  catalog: Product[];
  currency: string;
  reload: () => Promise<void>;
}) {
  const toast = useToast();
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<SupplierProduct | null>(null);
  const [form, setForm] = useState<SupplierProductInput>({});
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState<SupplierProduct | null>(null);

  useEffect(() => {
    if (!formOpen) return;
    setForm(
      editing
        ? {
            product_id: editing.product_id ?? '',
            custom_name: editing.custom_name ?? '',
            supplier_sku: editing.supplier_sku ?? '',
            supplier_price: editing.supplier_price ?? null,
            notes: editing.notes ?? '',
          }
        : {
            product_id: '',
            custom_name: '',
            supplier_sku: '',
            supplier_price: null,
            notes: '',
          },
    );
  }, [formOpen, editing]);

  async function save(event: FormEvent) {
    event.preventDefault();
    const productId = form.product_id || null;
    const customName = productId ? null : (form.custom_name ?? '').trim();
    if (!productId && !customName) {
      toast.error('Choose an existing product or enter a custom name.');
      return;
    }
    const price = form.supplier_price;
    const payload: SupplierProductInput = {
      product_id: productId,
      custom_name: customName,
      supplier_sku: (form.supplier_sku ?? '').trim() || undefined,
      supplier_price:
        price === null || price === undefined || Number.isNaN(Number(price))
          ? undefined
          : Number(price),
      notes: (form.notes ?? '').trim() || undefined,
    };
    setSaving(true);
    try {
      if (editing) {
        await patchOrDelete<void>(
          [`/suppliers/products/${editing.id}`, `/suppliers/${supplierId}/products/${editing.id}`],
          'patch',
          payload,
        );
        toast.success('Supplier product updated.');
      } else {
        await api.post(`/suppliers/${supplierId}/products`, payload);
        toast.success('Product linked to this supplier.');
      }
      setFormOpen(false);
      await reload();
    } catch (error) {
      toast.error(errorMessage(error, 'Could not save the supplier product.'));
    } finally {
      setSaving(false);
    }
  }

  async function remove() {
    if (!deleting) return;
    setSaving(true);
    try {
      await patchOrDelete<void>(
        [`/suppliers/products/${deleting.id}`, `/suppliers/${supplierId}/products/${deleting.id}`],
        'delete',
      );
      toast.success('Product link removed.');
      setDeleting(null);
      await reload();
    } catch (error) {
      toast.error(errorMessage(error, 'Could not remove the product link.'));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="supplier-panel">
      <div className="section-heading-row">
        <h4>Linked products ({links.length})</h4>
        <Button size="sm" icon={<Plus size={14} />}
          onClick={() => { setEditing(null); setFormOpen(true); }}>
          Link a product
        </Button>
      </div>
      <p className="supplier-help">
        Link products this supplier offers. Choose an existing BillFlow product or type a custom
        name — this never creates a new inventory product.
      </p>

      {links.length ? (
        <div className="table-scroll">
          <table className="data-table data-table--compact supplier-table">
            <thead>
              <tr>
                <th>Item</th>
                <th>Supplier SKU</th>
                <th className="text-right">Supplier price</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {links.map((link) => (
                <tr key={link.id}>
                  <td data-label="Item">
                    <strong>{link.product_name || link.custom_name || '—'}</strong>
                    <small className="cell-sub">
                      {link.product_id
                        ? 'Existing BillFlow product'
                        : 'Custom name — not in inventory'}
                    </small>
                    {link.notes && <small className="cell-sub">{link.notes}</small>}
                  </td>
                  <td data-label="Supplier SKU" className="mono">{link.supplier_sku || '—'}</td>
                  <td data-label="Supplier price" className="text-right">
                    {link.supplier_price != null ? money(link.supplier_price, currency) : '—'}
                  </td>
                  <td data-label="Actions" className="supplier-row-actions">
                    <button type="button" className="icon-btn" aria-label="Edit product link"
                      onClick={() => { setEditing(link); setFormOpen(true); }}>
                      <Pencil size={14} />
                    </button>
                    <button type="button" className="icon-btn" aria-label="Remove product link"
                      onClick={() => setDeleting(link)}>
                      <Trash2 size={14} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState
          title="No products linked yet"
          description="Add the items this supplier can provide, with their SKU and price."
          icon={<Package size={22} />}
          action={<Button size="sm" icon={<Plus size={14} />}
            onClick={() => { setEditing(null); setFormOpen(true); }}>Link a product</Button>}
        />
      )}

      <Modal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        title={editing ? 'Edit supplier product' : 'Link a product'}
        subtitle="Existing product or custom name — no inventory product is created here."
        size="md"
        footer={
          <>
            <Button variant="secondary" onClick={() => setFormOpen(false)}>Cancel</Button>
            <Button type="submit" form="supplier-product-form" loading={saving}>
              {editing ? 'Save changes' : 'Link product'}
            </Button>
          </>
        }
      >
        <form id="supplier-product-form" onSubmit={save} className="form-stack">
          <Field label="Item" required hint="Pick an existing product, or choose custom and type a name.">
            <ProductSourceFields
              products={catalog}
              productId={form.product_id ?? ''}
              customName={form.custom_name ?? ''}
              onProductId={(value) => setForm((prev) => ({ ...prev, product_id: value }))}
              onCustomName={(value) => setForm((prev) => ({ ...prev, custom_name: value }))}
            />
          </Field>
          <div className="form-grid form-grid--2">
            <Field label="Supplier SKU (optional)">
              <Input value={form.supplier_sku ?? ''} placeholder="Their item code"
                onChange={(event) => setForm((prev) => ({ ...prev, supplier_sku: event.target.value }))} />
            </Field>
            <Field label="Supplier price (optional)">
              <Input type="number" min="0" step="0.01" value={form.supplier_price ?? ''}
                placeholder="0.00"
                onChange={(event) => setForm((prev) => ({
                  ...prev,
                  supplier_price: event.target.value === '' ? null : Number(event.target.value),
                }))} />
            </Field>
          </div>
          <Field label="Notes (optional)">
            <Textarea rows={2} value={form.notes ?? ''} placeholder="Pack size, lead time…"
              onChange={(event) => setForm((prev) => ({ ...prev, notes: event.target.value }))} />
          </Field>
        </form>
      </Modal>

      <ConfirmDialog
        open={Boolean(deleting)}
        onClose={() => setDeleting(null)}
        onConfirm={() => void remove()}
        title="Remove this product link?"
        description="Only the link to this supplier is removed. The BillFlow product and its stock stay untouched."
        confirmLabel="Remove link"
        danger
        loading={saving}
      />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Purchase reminder helpers & building blocks                          */
/* ------------------------------------------------------------------ */

/** Accept the response shapes the supplier-products endpoint may use. */
function toArray<T>(response: unknown): T[] {
  if (Array.isArray(response)) return response as T[];
  if (response && typeof response === 'object') {
    const record = response as Record<string, unknown>;
    for (const key of ['items', 'data', 'products']) {
      if (Array.isArray(record[key])) return record[key] as T[];
    }
  }
  return [];
}

function cardName(card: SupplierProduct): string {
  return card.product_name || card.custom_name || card.product_sku || 'Untitled product';
}

/** Stable identity for selection/deduplication: the product, not the link row. */
function cardKey(card: SupplierProduct): string {
  return card.product_id || card.id;
}

/** Effective unit for a supplier card: supplier override first, product unit next. */
function cardUnit(card: SupplierProduct): string {
  return (card.unit || card.product_unit || 'pcs').trim() || 'pcs';
}

type SelectedProduct = {
  card: SupplierProduct;
  quantity: string;
  unit: string;
  expectedPrice: string;
  notes: string;
};

/** Compact, clickable card for a product linked to the current supplier. */
function SupplierProductCardGrid({
  products,
  selectedIds,
  onToggle,
}: {
  products: SupplierProduct[];
  selectedIds: string[];
  onToggle: (card: SupplierProduct) => void;
}) {
  return (
    <div className="supplier-card-grid">
      {products.map((card) => {
        const isSelected = selectedIds.includes(cardKey(card));
        const brandCategory = [card.product_brand, card.product_category].filter(Boolean).join(' · ');
        const variantSize = [card.product_variant, card.product_size_pack].filter(Boolean).join(' · ');
        return (
          <button
            type="button"
            key={card.id}
            aria-pressed={isSelected}
            className={
              isSelected ? 'supplier-product-card supplier-product-card--selected' : 'supplier-product-card'
            }
            onClick={() => onToggle(card)}
          >
            <span className="supplier-card__name">{cardName(card)}</span>
            {brandCategory && <span className="supplier-card__meta">{brandCategory}</span>}
            {variantSize && <span className="supplier-card__variant">{variantSize}</span>}
            <span className="supplier-card__footer">
              <span className="supplier-card__unit">{cardUnit(card)}</span>
              {isSelected && (
                <span className="supplier-card__selected">
                  <Check size={12} /> Selected
                </span>
              )}
            </span>
          </button>
        );
      })}
    </div>
  );
}

/** One product in the new-reminder panel, with all fields editable inline. */
function SelectedProductRow({
  selected,
  currency,
  onChange,
  onRemove,
}: {
  selected: SelectedProduct;
  currency: string;
  onChange: (id: string, field: keyof SelectedProduct, value: string) => void;
  onRemove: (id: string) => void;
}) {
  const id = cardKey(selected.card);
  return (
    <div className="supplier-selected-row">
      <div className="supplier-selected-row__head">
        <strong className="supplier-selected-row__name">{cardName(selected.card)}</strong>
        <button type="button" className="icon-btn" aria-label={`Remove ${cardName(selected.card)}`}
          onClick={() => onRemove(id)}>
          <Trash2 size={14} />
        </button>
      </div>
      <div className="reminder-fields">
        <label className="reminder-field">
          <span>Qty</span>
          <Input type="number" min="0.001" step="0.001" value={selected.quantity}
            onChange={(event) => onChange(id, 'quantity', event.target.value)} />
        </label>
        <label className="reminder-field">
          <span>Unit</span>
          <Input value={selected.unit} placeholder="pcs, boxes, kg…"
            onChange={(event) => onChange(id, 'unit', event.target.value)} />
        </label>
        <label className="reminder-field">
          <span>Expected price ({currency})</span>
          <Input type="number" min="0" step="0.01" value={selected.expectedPrice} placeholder="optional"
            onChange={(event) => onChange(id, 'expectedPrice', event.target.value)} />
        </label>
        <label className="reminder-field reminder-field--notes">
          <span>Notes</span>
          <Input value={selected.notes} placeholder="optional"
            onChange={(event) => onChange(id, 'notes', event.target.value)} />
        </label>
      </div>
    </div>
  );
}

/** One item of a saved list. Every field saves in place through the item PATCH. */
function ReminderItemRow({
  item,
  currency,
  onPatch,
  onTogglePurchased,
  onRemove,
}: {
  item: PurchaseReminderItem;
  currency: string;
  onPatch: (item: PurchaseReminderItem, patch: PurchaseReminderItemInput) => Promise<boolean>;
  onTogglePurchased: (item: PurchaseReminderItem) => void;
  onRemove: (item: PurchaseReminderItem) => void;
}) {
  const toast = useToast();
  const [quantity, setQuantity] = useState(String(item.quantity));
  const [unit, setUnit] = useState(item.unit ?? '');
  const [expectedPrice, setExpectedPrice] = useState(
    item.expected_price != null ? String(item.expected_price) : '',
  );
  const [notes, setNotes] = useState(item.notes ?? '');

  useEffect(() => {
    setQuantity(String(item.quantity));
    setUnit(item.unit ?? '');
    setExpectedPrice(item.expected_price != null ? String(item.expected_price) : '');
    setNotes(item.notes ?? '');
  }, [item]);

  async function commit(patch: PurchaseReminderItemInput, reset: () => void) {
    const ok = await onPatch(item, patch);
    if (!ok) reset();
  }

  return (
    <div className={item.is_purchased ? 'reminder-item-row reminder-item-row--done' : 'reminder-item-row'}>
      <div className="reminder-item-row__head">
        <div className="reminder-item-row__title">
          <strong>{item.product_name || item.name}</strong>
          {item.product_id && <small className="cell-sub">Existing BillFlow product</small>}
          {!item.product_id && <small className="cell-sub">Custom name — not in inventory</small>}
        </div>
        <div className="reminder-item-row__tools">
          <label className="reminder-check">
            <input type="checkbox" checked={item.is_purchased}
              onChange={() => onTogglePurchased(item)} />
            {item.is_purchased ? 'Purchased' : 'Pending'}
          </label>
          <button type="button" className="icon-btn" aria-label="Remove item"
            onClick={() => onRemove(item)}>
            <Trash2 size={14} />
          </button>
        </div>
      </div>
      <div className="reminder-fields">
        <label className="reminder-field">
          <span>Qty</span>
          <Input type="number" min="0.001" step="0.001" value={quantity}
            onChange={(event) => setQuantity(event.target.value)}
            onBlur={() => {
              const value = Number(quantity);
              if (!(value > 0)) {
                setQuantity(String(item.quantity));
                toast.error('Quantity must be greater than 0.');
                return;
              }
              if (value === Number(item.quantity)) return;
              void commit({ quantity: value }, () => setQuantity(String(item.quantity)));
            }} />
        </label>
        <label className="reminder-field">
          <span>Unit</span>
          <Input value={unit} placeholder="pcs, boxes, kg…"
            onChange={(event) => setUnit(event.target.value)}
            onBlur={() => {
              const value = unit.trim() || null;
              if (value === (item.unit || null)) return;
              void commit({ unit: value }, () => setUnit(item.unit ?? ''));
            }} />
        </label>
        <label className="reminder-field">
          <span>Expected price ({currency})</span>
          <Input type="number" min="0" step="0.01" value={expectedPrice} placeholder="optional"
            onChange={(event) => setExpectedPrice(event.target.value)}
            onBlur={() => {
              const raw = expectedPrice.trim();
              if (raw === '' || Number.isNaN(Number(raw))) {
                if ((item.expected_price ?? null) === null) return;
                void commit({ expected_price: null }, () =>
                  setExpectedPrice(item.expected_price != null ? String(item.expected_price) : ''));
                return;
              }
              const value = Number(raw);
              if (value === item.expected_price) return;
              void commit({ expected_price: value }, () =>
                setExpectedPrice(item.expected_price != null ? String(item.expected_price) : ''));
            }} />
        </label>
        <label className="reminder-field reminder-field--notes">
          <span>Notes</span>
          <Input value={notes} placeholder="optional"
            onChange={(event) => setNotes(event.target.value)}
            onBlur={() => {
              const value = notes.trim() || null;
              if (value === (item.notes || null)) return;
              void commit({ notes: value }, () => setNotes(item.notes ?? ''));
            }} />
        </label>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Purchase reminders tab                                              */
/* ------------------------------------------------------------------ */

function RemindersTab({
  supplierId,
  supplierName,
  lists,
  currency,
  reload,
  onChanged,
  onGoToProducts,
}: {
  supplierId: string;
  supplierName: string;
  lists: PurchaseReminderList[];
  currency: string;
  reload: () => Promise<void>;
  onChanged: () => void;
  onGoToProducts: () => void;
}) {
  const toast = useToast();

  const [cards, setCards] = useState<SupplierProduct[]>([]);
  const [cardsLoading, setCardsLoading] = useState(true);
  const [newTitle, setNewTitle] = useState('');
  const [newNotes, setNewNotes] = useState('');
  const [selected, setSelected] = useState<SelectedProduct[]>([]);
  const [saving, setSaving] = useState(false);

  const [selectedId, setSelectedId] = useState<string | null>(lists[0]?.id ?? null);
  const [itemsByList, setItemsByList] = useState<Record<string, PurchaseReminderItem[]>>({});
  const [addOpen, setAddOpen] = useState(false);
  const [addSelectedIds, setAddSelectedIds] = useState<string[]>([]);
  const [adding, setAdding] = useState(false);
  const [carryingId, setCarryingId] = useState<string | null>(null);
  const [deletingList, setDeletingList] = useState<PurchaseReminderList | null>(null);
  const [deletingItem, setDeletingItem] = useState<PurchaseReminderItem | null>(null);
  const [itemSaving, setItemSaving] = useState(false);

  const [convertList, setConvertList] = useState<PurchaseReminderList | null>(null);
  const [convertForm, setConvertForm] = useState({
    purchase_date: todayInput(),
    notes: '',
    only_purchased: true,
  });
  const [converting, setConverting] = useState(false);
  const [result, setResult] = useState<SupplierPurchaseConversion | null>(null);

  // Load ONLY this supplier's linked products. Changing supplier clears every
  // selection so a product from another supplier can never leak into a reminder.
  useEffect(() => {
    let active = true;
    setCardsLoading(true);
    setCards([]);
    setSelected([]);
    setAddOpen(false);
    setAddSelectedIds([]);
    void api
      .get<unknown>(`/suppliers/${supplierId}/products`)
      .then((response) => { if (active) setCards(toArray<SupplierProduct>(response)); })
      .catch(() => { if (active) toast.error('Could not load the supplier products.'); })
      .finally(() => { if (active) setCardsLoading(false); });
    return () => { active = false; };
  }, [supplierId, toast]);

  // Only real product links can be saved by quick-save (it requires a product_id).
  const linkedProducts = useMemo(
    () => cards.filter((card) => Boolean(card.product_id)),
    [cards],
  );
  const selectedIds = useMemo(() => selected.map((entry) => cardKey(entry.card)), [selected]);

  useEffect(() => {
    if (!selectedId && lists.length) setSelectedId(lists[0].id);
    if (selectedId && !lists.some((list) => list.id === selectedId)) {
      setSelectedId(lists[0]?.id ?? null);
    }
  }, [lists, selectedId]);

  // Prefer items embedded in the detail payload; otherwise fetch per list.
  useEffect(() => {
    const embedded: Record<string, PurchaseReminderItem[]> = {};
    const missing: PurchaseReminderList[] = [];
    lists.forEach((list) => {
      if (list.items) embedded[list.id] = list.items;
      else missing.push(list);
    });
    if (Object.keys(embedded).length) {
      setItemsByList((prev) => ({ ...prev, ...embedded }));
    }
    if (!missing.length) return;
    let active = true;
    void Promise.all(
      missing.map(async (list) => {
        try {
          const response = await api.get<unknown>(`/suppliers/reminders/${list.id}/items`);
          return [list.id, toArray<PurchaseReminderItem>(response)] as const;
        } catch {
          return [list.id, [] as PurchaseReminderItem[]] as const;
        }
      }),
    ).then((entries) => {
      if (active) setItemsByList((prev) => ({ ...prev, ...Object.fromEntries(entries) }));
    });
    return () => { active = false; };
  }, [lists]);

  const selectedList = lists.find((list) => list.id === selectedId) ?? null;
  const items = selectedList ? (itemsByList[selectedList.id] ?? selectedList.items ?? []) : [];
  const pendingCount = items.filter((item) => !item.is_purchased).length;

  function togglePick(card: SupplierProduct) {
    setSelected((prev) => {
      const exists = prev.some((entry) => cardKey(entry.card) === cardKey(card));
      if (exists) return prev.filter((entry) => cardKey(entry.card) !== cardKey(card));
      return [...prev, {
        card,
        quantity: '1',
        unit: cardUnit(card),
        expectedPrice: '',
        notes: '',
      }];
    });
  }

  function updateSelected(id: string, field: keyof SelectedProduct, value: string) {
    setSelected((prev) => prev.map((entry) =>
      cardKey(entry.card) === id ? { ...entry, [field]: value } : entry,
    ));
  }

  async function saveQuickReminder(event: FormEvent) {
    event.preventDefault();
    const title = newTitle.trim();
    if (!title) {
      toast.error('Give the reminder a title.');
      return;
    }
    if (!selected.length) {
      toast.error('Select at least one product first.');
      return;
    }

    // Local relationship check: every selected id must still belong to this supplier.
    const validIds = new Set(linkedProducts.map((card) => card.product_id as string));
    const invalid = selected.find((entry) =>
      !entry.card.product_id || !validIds.has(entry.card.product_id));
    if (invalid) {
      toast.error('A selected product is no longer linked to this supplier. Review your selection.');
      setSelected([]);
      return;
    }
    const badQuantity = selected.find((entry) => !(Number(entry.quantity) > 0));
    if (badQuantity) {
      toast.error('Enter a quantity greater than 0 for every product.');
      return;
    }

    const payload: QuickReminderPayload = {
      title,
      notes: newNotes.trim() || undefined,
      items: selected.map((entry) => {
        const price = Number(entry.expectedPrice);
        return {
          product_id: entry.card.product_id as string,
          quantity: Number(entry.quantity),
          unit: entry.unit.trim() || cardUnit(entry.card),
          expected_price:
            entry.expectedPrice.trim() !== '' && Number.isFinite(price) ? price : undefined,
          notes: entry.notes.trim() || undefined,
        };
      }),
    };

    setSaving(true);
    try {
      const created = await api.post<PurchaseReminderList>(
        `/suppliers/${supplierId}/reminders/quick-save`,
        payload,
      );
      toast.success('Reminder saved.');
      setNewTitle('');
      setNewNotes('');
      setSelected([]);
      if (created?.id) setSelectedId(created.id);
      await reload();
    } catch (error) {
      toast.error(errorMessage(error, 'Could not save the reminder.'));
    } finally {
      setSaving(false);
    }
  }

  async function patchItem(
    item: PurchaseReminderItem,
    patch: PurchaseReminderItemInput,
  ): Promise<boolean> {
    try {
      await patchOrDelete<void>(
        [
          `/suppliers/reminders/items/${item.id}`,
          `/suppliers/reminders/${item.list_id}/items/${item.id}`,
        ],
        'patch',
        patch,
      );
      await reload();
      return true;
    } catch (error) {
      toast.error(errorMessage(error, 'Could not update the item.'));
      return false;
    }
  }

  const existingProductIds = useMemo(
    () => new Set(items.map((item) => item.product_id).filter(Boolean) as string[]),
    [items],
  );
  const addableProducts = useMemo(
    () => linkedProducts.filter((card) => !existingProductIds.has(card.product_id as string)),
    [linkedProducts, existingProductIds],
  );

  function toggleAddPick(card: SupplierProduct) {
    const key = cardKey(card);
    setAddSelectedIds((prev) =>
      prev.includes(key) ? prev.filter((id) => id !== key) : [...prev, key],
    );
  }

  async function addPickedProducts() {
    if (!selectedList || !addSelectedIds.length) return;
    const picks = addableProducts.filter((card) => addSelectedIds.includes(cardKey(card)));
    if (!picks.length) return;
    setAdding(true);
    try {
      await Promise.all(
        picks.map((card) =>
          api.post(`/suppliers/reminders/${selectedList.id}/items`, {
            product_id: card.product_id,
            name: cardName(card),
            quantity: 1,
            unit: cardUnit(card),
          }),
        ),
      );
      toast.success(
        picks.length === 1
          ? 'Product added to the reminder.'
          : `${picks.length} products added to the reminder.`,
      );
      setAddSelectedIds([]);
      setAddOpen(false);
      await reload();
    } catch (error) {
      toast.error(errorMessage(error, 'Could not add the products.'));
    } finally {
      setAdding(false);
    }
  }

  async function removeItem() {
    if (!deletingItem) return;
    setItemSaving(true);
    try {
      await patchOrDelete<void>(
        [
          `/suppliers/reminders/items/${deletingItem.id}`,
          `/suppliers/reminders/${deletingItem.list_id}/items/${deletingItem.id}`,
        ],
        'delete',
      );
      toast.success('Reminder item removed.');
      setDeletingItem(null);
      await reload();
    } catch (error) {
      toast.error(errorMessage(error, 'Could not remove the item.'));
    } finally {
      setItemSaving(false);
    }
  }

  async function carryForward(list: PurchaseReminderList) {
    setCarryingId(list.id);
    try {
      await api.post(`/suppliers/reminders/${list.id}/carry-forward`);
      toast.success('Unfinished items carried forward to a new list.');
      await reload();
    } catch (error) {
      toast.error(errorMessage(error, 'Could not carry the items forward.'));
    } finally {
      setCarryingId(null);
    }
  }

  async function deleteList() {
    if (!deletingList) return;
    const deletedId = deletingList.id;
    setItemSaving(true);
    try {
      await api.delete(`/suppliers/reminders/${deletedId}`);
      toast.success('Reminder list deleted.');
      setDeletingList(null);
      if (selectedId === deletedId) setSelectedId(null);
      await reload();
    } catch (error) {
      toast.error(errorMessage(error, 'Could not delete the reminder list.'));
    } finally {
      setItemSaving(false);
    }
  }

  async function convert() {
    if (!convertList) return;
    setConverting(true);
    try {
      const response = await api.post<SupplierPurchaseConversion>(
        `/suppliers/reminders/${convertList.id}/convert-to-purchase`,
        {
          purchase_date: convertForm.purchase_date || undefined,
          notes: convertForm.notes.trim() || undefined,
          only_purchased: convertForm.only_purchased,
        },
      );
      setResult(response ?? {});
      setConvertList(null);
      toast.success('Reminder list converted to a purchase.');
      await reload();
      onChanged();
    } catch (error) {
      toast.error(errorMessage(error, 'Could not convert the reminder list.'));
    } finally {
      setConverting(false);
    }
  }

  return (
    <div className="supplier-panel">
      <div className="reminder-supplier-head">
        <h4>Purchase reminders for {supplierName}</h4>
        <span className="supplier-help">
          Build a reminder from this supplier’s linked products, then save it for your next visit.
        </span>
      </div>

      <div className="supplier-note">
        <Info size={15} />
        <span>
          Saving or ticking a reminder <strong>does not change stock</strong>. Goods are only
          received into inventory when you use <strong>Convert to purchase</strong>, which follows
          the normal purchase workflow. Unticked items stay pending and can be carried forward.
        </span>
      </div>

      <div className="reminder-compose">
        <div className="section-heading-row">
          <h4>New reminder</h4>
          <span className="supplier-help">Only products linked to {supplierName} can be selected.</span>
        </div>
        <div className="reminder-compose__titles">
          <Input value={newTitle} onChange={(event) => setNewTitle(event.target.value)}
            placeholder="Reminder title (e.g. weekly restock)" aria-label="Reminder title" />
          <Input value={newNotes} onChange={(event) => setNewNotes(event.target.value)}
            placeholder="Notes (optional)" aria-label="Reminder notes" />
        </div>

        {cardsLoading ? (
          <Loader label="Loading supplier products…" />
        ) : linkedProducts.length === 0 ? (
          <div className="reminder-empty">
            <p>No products linked to this supplier yet.</p>
            <Button size="sm" icon={<Package size={14} />} onClick={onGoToProducts}>
              Go to Products
            </Button>
          </div>
        ) : (
          <div className="reminder-compose__columns">
            <div className="reminder-picker">
              <div className="section-heading-row">
                <h4>Available products ({linkedProducts.length})</h4>
              </div>
              <p className="supplier-help">Click a card to select it. Click again to remove it.</p>
              <SupplierProductCardGrid
                products={linkedProducts}
                selectedIds={selectedIds}
                onToggle={togglePick}
              />
            </div>

            <form className="supplier-selected-panel" onSubmit={saveQuickReminder}>
              <div className="section-heading-row">
                <h4>Selected products ({selected.length})</h4>
              </div>
              {selected.length === 0 ? (
                <p className="supplier-help">
                  Pick a product on the left, then set its quantity and unit here before saving.
                </p>
              ) : (
                <div className="supplier-selected-list">
                  {selected.map((entry) => (
                    <SelectedProductRow
                      key={cardKey(entry.card)}
                      selected={entry}
                      currency={currency}
                      onChange={updateSelected}
                      onRemove={(id) =>
                        setSelected((prev) => prev.filter((item) => cardKey(item.card) !== id))
                      }
                    />
                  ))}
                </div>
              )}
              <Button type="submit" icon={<ClipboardList size={15} />} loading={saving} full>
                Save Reminder
              </Button>
            </form>
          </div>
        )}
      </div>

      <div className="reminder-saved">
        <div className="section-heading-row">
          <h4>Saved reminders ({lists.length})</h4>
        </div>
        {lists.length ? (
          <>
            <div className="supplier-list-tabs" role="tablist" aria-label="Reminder lists">
              {lists.map((list) => (
                <button key={list.id} type="button" role="tab"
                  aria-selected={list.id === selectedId}
                  className={list.id === selectedId ? 'supplier-list-tab supplier-list-tab--active' : 'supplier-list-tab'}
                  onClick={() => {
                    setSelectedId(list.id);
                    setAddOpen(false);
                    setAddSelectedIds([]);
                  }}>
                  {list.title}
                  <Badge tone={list.status === 'converted' ? 'success' : 'warning'} dot>
                    {list.status === 'converted' ? 'Converted' : 'Pending'}
                  </Badge>
                </button>
              ))}
            </div>

            {selectedList && (
              <div className="supplier-list-body">
                <div className="section-heading-row">
                  <h4>{selectedList.title}</h4>
                  <div className="supplier-inline-actions">
                    <Button size="sm" variant="secondary" icon={<Plus size={14} />}
                      onClick={() => {
                        setAddSelectedIds([]);
                        setAddOpen((open) => !open);
                      }}>
                      {addOpen ? 'Close picker' : 'Add products'}
                    </Button>
                    <Button size="sm" variant="secondary" icon={<ArrowUpRight size={14} />}
                      loading={carryingId === selectedList.id}
                      disabled={selectedList.status === 'converted' || pendingCount === 0}
                      onClick={() => void carryForward(selectedList)}>
                      Carry forward
                    </Button>
                    <Button size="sm" variant="ghost" icon={<Trash2 size={14} />}
                      onClick={() => setDeletingList(selectedList)}>
                      Delete list
                    </Button>
                    <Button size="sm" icon={<CheckCircle2 size={14} />}
                      disabled={selectedList.status === 'converted'}
                      onClick={() => {
                        setConvertForm({ purchase_date: todayInput(), notes: '', only_purchased: true });
                        setConvertList(selectedList);
                      }}>
                      Convert to purchase
                    </Button>
                  </div>
                </div>
                {selectedList.notes && <p className="supplier-help">{selectedList.notes}</p>}
                <p className="supplier-help">
                  {pendingCount} pending · {items.length} item{items.length === 1 ? '' : 's'} on this
                  list. Quantities and units can be edited in place.
                </p>

                {addOpen && (
                  <div className="reminder-add-panel">
                    {addableProducts.length ? (
                      <>
                        <p className="supplier-help">
                          Choose products linked to {supplierName} to add to this list.
                        </p>
                        <SupplierProductCardGrid
                          products={addableProducts}
                          selectedIds={addSelectedIds}
                          onToggle={toggleAddPick}
                        />
                        <Button size="sm" icon={<Plus size={14} />} loading={adding}
                          disabled={!addSelectedIds.length}
                          onClick={() => void addPickedProducts()}>
                          Add selected ({addSelectedIds.length})
                        </Button>
                      </>
                    ) : (
                      <p className="supplier-help">
                        All of this supplier’s linked products are already on this list.
                      </p>
                    )}
                  </div>
                )}

                {items.length ? (
                  <div className="reminder-item-list">
                    {items.map((item) => (
                      <ReminderItemRow
                        key={item.id}
                        item={item}
                        currency={currency}
                        onPatch={patchItem}
                        onTogglePurchased={(target) =>
                          void patchItem(target, { is_purchased: !target.is_purchased })
                        }
                        onRemove={(target) => setDeletingItem(target)}
                      />
                    ))}
                  </div>
                ) : (
                  <EmptyState title="No items yet"
                    description="Add products from this supplier to the reminder."
                    icon={<ClipboardList size={22} />}
                    action={<Button size="sm" icon={<Plus size={14} />}
                      onClick={() => setAddOpen(true)}>Add products</Button>} />
                )}
              </div>
            )}
          </>
        ) : (
          <EmptyState title="No reminder lists yet"
            description="Use Save Reminder above to create your first list from this supplier’s products."
            icon={<ClipboardList size={22} />} />
        )}
      </div>

      <ConfirmDialog
        open={Boolean(deletingItem)}
        onClose={() => setDeletingItem(null)}
        onConfirm={() => void removeItem()}
        title="Remove this item?"
        description="The item will be removed from this reminder list. No stock is changed."
        confirmLabel="Remove item"
        danger
        loading={itemSaving}
      />

      <ConfirmDialog
        open={Boolean(deletingList)}
        onClose={() => setDeletingList(null)}
        onConfirm={() => void deleteList()}
        title="Delete this reminder list?"
        description="The list and all of its items will be removed. No stock is changed."
        confirmLabel="Delete list"
        danger
        loading={itemSaving}
      />

      <Modal
        open={Boolean(convertList)}
        onClose={() => setConvertList(null)}
        title="Convert to purchase"
        subtitle={convertList ? `Create a real purchase from “${convertList.title}”.` : undefined}
        size="md"
        footer={
          <>
            <Button variant="secondary" onClick={() => setConvertList(null)}>Cancel</Button>
            <Button type="submit" form="supplier-convert-form" loading={converting}>
              Convert to purchase
            </Button>
          </>
        }
      >
        <form id="supplier-convert-form" onSubmit={(event) => { event.preventDefault(); void convert(); }}
          className="form-stack">
          <div className="supplier-note">
            <Info size={15} />
            <span>
              Linked BillFlow products are received into stock. Custom-name items cannot be stocked,
              so they are carried into the purchase notes instead. This marks the list converted.
            </span>
          </div>
          <div className="form-grid form-grid--2">
            <Field label="Purchase date">
              <Input type="date" value={convertForm.purchase_date}
                onChange={(event) => setConvertForm((prev) => ({
                  ...prev,
                  purchase_date: event.target.value,
                }))} />
            </Field>
            <Field label="Notes (optional)">
              <Input value={convertForm.notes} placeholder="Purchase reference or remarks"
                onChange={(event) => setConvertForm((prev) => ({
                  ...prev,
                  notes: event.target.value,
                }))} />
            </Field>
          </div>
          <Checkbox checked={convertForm.only_purchased}
            onChange={(checked) => setConvertForm((prev) => ({ ...prev, only_purchased: checked }))}
            label="Only include items marked purchased"
            hint="Turn off to receive every item on this list into stock."
          />
        </form>
      </Modal>

      <Modal
        open={Boolean(result)}
        onClose={() => setResult(null)}
        title="Purchase created"
        subtitle="The reminder list was converted successfully."
        size="md"
        footer={<Button onClick={() => setResult(null)}>Done</Button>}
      >
        <div className="supplier-convert-summary">
          <p>
            A purchase was created from the reminder list. Items linked to BillFlow products were
            received into stock; custom-name items were recorded in the purchase notes only. Simply
            ticking an item as purchased never changes stock.
          </p>
          <div className="detail-stat-grid">
            <div className="detail-stat">
              <span>Purchase number</span>
              <strong>{result?.purchase_number ?? result?.purchase?.purchase_number ?? '—'}</strong>
            </div>
            {result?.purchase_date || result?.purchase?.purchase_date ? (
              <div className="detail-stat">
                <span>Purchase date</span>
                <strong>{formatDate(result.purchase_date ?? result.purchase?.purchase_date)}</strong>
              </div>
            ) : null}
            {result?.items_created !== undefined && (
              <div className="detail-stat"><span>Items received</span><strong>{result.items_created}</strong></div>
            )}
            {(result?.stock_movements ?? result?.movements_created) !== undefined && (
              <div className="detail-stat">
                <span>Stock movements</span>
                <strong>{result?.stock_movements ?? result?.movements_created}</strong>
              </div>
            )}
            {(result?.custom_items_skipped ?? result?.skipped_custom_items) !== undefined && (
              <div className="detail-stat">
                <span>Custom items in notes</span><strong>{result?.custom_items_skipped ?? result?.skipped_custom_items}</strong>
              </div>
            )}
            {result?.total_amount !== undefined && (
              <div className="detail-stat">
                <span>Total amount</span><strong>{money(result.total_amount, currency)}</strong>
              </div>
            )}
          </div>
          {result?.message && <p className="supplier-help">{result.message}</p>}
        </div>
      </Modal>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Visits tab                                                           */
/* ------------------------------------------------------------------ */

function VisitsTab({
  supplierId,
  visits,
  reload,
}: {
  supplierId: string;
  visits: SupplierVisit[];
  reload: () => Promise<void>;
}) {
  const toast = useToast();
  const [form, setForm] = useState<SupplierVisitInput>({ visit_date: todayInput() });
  const [saving, setSaving] = useState(false);

  function set(field: keyof SupplierVisitInput, value: string) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!form.visit_date) {
      toast.error('Choose the visit date.');
      return;
    }
    const payload: SupplierVisitInput = {
      visit_date: form.visit_date,
      discussion_notes: form.discussion_notes?.trim() || undefined,
      items_discussed: form.items_discussed?.trim() || undefined,
      items_requested: form.items_requested?.trim() || undefined,
      follow_up: form.follow_up?.trim() || undefined,
      next_visit_date: form.next_visit_date || undefined,
      notes: form.notes?.trim() || undefined,
    };
    setSaving(true);
    try {
      await api.post(`/suppliers/${supplierId}/visits`, payload);
      setForm({ visit_date: todayInput() });
      toast.success('Visit recorded.');
      await reload();
    } catch (error) {
      toast.error(errorMessage(error, 'Could not record the visit.'));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="supplier-panel">
      <form className="supplier-visit-form" onSubmit={save}>
        <div className="section-heading-row">
          <h4>Record a visit</h4>
          <Button type="submit" size="sm" icon={<Plus size={14} />} loading={saving}>
            Save visit
          </Button>
        </div>
        <div className="form-grid form-grid--2">
          <Field label="Visit date" required>
            <Input type="date" value={form.visit_date ?? ''}
              onChange={(event) => set('visit_date', event.target.value)} />
          </Field>
          <Field label="Next visit date (optional)">
            <Input type="date" value={form.next_visit_date ?? ''}
              onChange={(event) => set('next_visit_date', event.target.value)} />
          </Field>
        </div>
        <Field label="Discussion notes">
          <Textarea rows={2} value={form.discussion_notes ?? ''} placeholder="What did you discuss?"
            onChange={(event) => set('discussion_notes', event.target.value)} />
        </Field>
        <div className="form-grid form-grid--2">
          <Field label="Items discussed">
            <Textarea rows={2} value={form.items_discussed ?? ''} placeholder="Items talked about…"
              onChange={(event) => set('items_discussed', event.target.value)} />
          </Field>
          <Field label="Items requested">
            <Textarea rows={2} value={form.items_requested ?? ''} placeholder="Items you asked for…"
              onChange={(event) => set('items_requested', event.target.value)} />
          </Field>
        </div>
        <Field label="Follow-up">
          <Textarea rows={2} value={form.follow_up ?? ''} placeholder="What needs to happen next?"
            onChange={(event) => set('follow_up', event.target.value)} />
        </Field>
        <Field label="Notes (optional)">
          <Textarea rows={2} value={form.notes ?? ''} placeholder="Anything else to remember…"
            onChange={(event) => set('notes', event.target.value)} />
        </Field>
      </form>

      <div className="detail-section">
        <h4>Visit history ({visits.length})</h4>
        {visits.length ? (
          <div className="timeline">
            {visits.map((visit) => (
              <div className="timeline__item" key={visit.id}>
                <span className="timeline__dot" />
                <div className="supplier-visit">
                  <div className="timeline__meta">
                    <Badge tone="info">{formatDate(visit.visit_date)}</Badge>
                    {visit.next_visit_date && (
                      <span className="muted">Next visit: {formatDate(visit.next_visit_date)}</span>
                    )}
                  </div>
                  {visit.discussion_notes && <p>{visit.discussion_notes}</p>}
                  {visit.items_discussed && (
                    <p className="supplier-visit__line"><strong>Discussed:</strong> {visit.items_discussed}</p>
                  )}
                  {visit.items_requested && (
                    <p className="supplier-visit__line"><strong>Requested:</strong> {visit.items_requested}</p>
                  )}
                  {visit.follow_up && (
                    <p className="supplier-visit__line"><strong>Follow-up:</strong> {visit.follow_up}</p>
                  )}
                  {visit.notes && <p className="supplier-visit__line"><strong>Notes:</strong> {visit.notes}</p>}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState title="No visits recorded yet"
            description="Log a visit above to keep a history of discussions and follow-ups."
            icon={<CalendarDays size={22} />} />
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Supplier profile drawer                                              */
/* ------------------------------------------------------------------ */

function SupplierProfileDrawer({
  id,
  onClose,
  onChanged,
  currency,
  suggestions,
}: {
  id: string;
  onClose: () => void;
  onChanged: () => void;
  currency: string;
  suggestions: SupplierCategorySuggestions;
}) {
  const toast = useToast();
  const [detail, setDetail] = useState<SupplierDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<'products' | 'reminders' | 'visits'>('products');
  const [catalog, setCatalog] = useState<Product[]>([]);
  const [editOpen, setEditOpen] = useState(false);
  const [deactivateOpen, setDeactivateOpen] = useState(false);
  const [deactivating, setDeactivating] = useState(false);

  const reload = useCallback(async () => {
    try {
      setDetail(await api.get<SupplierDetail>(`/suppliers/${id}`));
    } catch (error) {
      toast.error(errorMessage(error, 'Could not load the supplier.'));
    } finally {
      setLoading(false);
    }
  }, [id, toast]);

  useEffect(() => { void reload(); }, [reload]);

  useEffect(() => {
    let active = true;
    api.get<Paginated<Product>>('/products', { page_size: 200 })
      .then((response) => { if (active) setCatalog(response.items); })
      .catch(() => { /* picker will show only custom entry */ });
    return () => { active = false; };
  }, []);

  const links = useMemo(
    () => detail?.products ?? detail?.supplier_products ?? [],
    [detail],
  );
  const lists = useMemo(
    () => detail?.reminder_lists ?? detail?.reminders ?? [],
    [detail],
  );
  const visits = useMemo(() => detail?.visits ?? [], [detail]);

  async function deactivate() {
    if (!detail) return;
    setDeactivating(true);
    try {
      await api.delete<MessageResponse>(`/suppliers/${detail.id}`);
      toast.success(`${detail.name} was deactivated.`);
      setDeactivateOpen(false);
      onClose();
      onChanged();
    } catch (error) {
      toast.error(errorMessage(error, 'Could not deactivate the supplier.'));
    } finally {
      setDeactivating(false);
    }
  }

  if (loading) {
    return (
      <Drawer open onClose={onClose} title="Supplier">
        <Loader label="Loading supplier…" full />
      </Drawer>
    );
  }
  if (!detail) {
    return (
      <Drawer open onClose={onClose} title="Supplier">
        <EmptyState title="Supplier not found" />
      </Drawer>
    );
  }

  return (
    <>
      <Drawer
        open
        onClose={onClose}
        title={detail.name}
        subtitle={detail.category || 'Supplier profile'}
        width={620}
        footer={
          <div className="drawer-actions">
            <Button size="sm" variant="secondary" icon={<Pencil size={14} />}
              onClick={() => setEditOpen(true)}>
              Edit profile
            </Button>
            {detail.is_active && (
              <Button size="sm" variant="ghost" icon={<PowerOff size={14} />}
                onClick={() => setDeactivateOpen(true)}>
                Deactivate
              </Button>
            )}
          </div>
        }
      >
        <div className="supplier-profile-head">
          <span className="avatar avatar--lg">{initials(detail.name)}</span>
          <div>
            <div className="supplier-profile-head__badges">
              <StatusBadge status={detail.is_active ? 'active' : 'inactive'} />
              {detail.category && <Badge tone="neutral">{detail.category}</Badge>}
              {detail.brands && <Badge tone="info">{detail.brands}</Badge>}
            </div>
            {detail.contact_person && <p className="muted small">Contact: {detail.contact_person}</p>}
          </div>
        </div>

        <div className="supplier-contact-grid">
          {detail.phone ? (
            <a href={`tel:${detail.phone.replace(/\s/g, '')}`}>
              <Phone size={15} /> {detail.phone}
            </a>
          ) : <span className="muted"><Phone size={15} /> No phone on file</span>}
          {detail.whatsapp ? (
            <a href={`https://wa.me/${detail.whatsapp.replace(/[^\d]/g, '')}`}
              target="_blank" rel="noreferrer">
              <MessageCircle size={15} /> {detail.whatsapp}
            </a>
          ) : <span className="muted"><MessageCircle size={15} /> No WhatsApp on file</span>}
          {detail.email ? (
            <a href={`mailto:${detail.email}`}>
              <Mail size={15} /> {detail.email}
            </a>
          ) : <span className="muted"><Mail size={15} /> No email on file</span>}
          {detail.address && (
            <span><Truck size={15} /> {detail.address}</span>
          )}
        </div>
        {detail.notes && <div className="detail-notes">{detail.notes}</div>}

        <div className="admin-tabs supplier-tabs" role="tablist" aria-label="Supplier sections">
          <button type="button" role="tab" aria-selected={tab === 'products'}
            className={tab === 'products' ? 'admin-tab admin-tab--active' : 'admin-tab'}
            onClick={() => setTab('products')}>
            <Package size={15} /> Products
          </button>
          <button type="button" role="tab" aria-selected={tab === 'reminders'}
            className={tab === 'reminders' ? 'admin-tab admin-tab--active' : 'admin-tab'}
            onClick={() => setTab('reminders')}>
            <ClipboardList size={15} /> Purchase reminders
          </button>
          <button type="button" role="tab" aria-selected={tab === 'visits'}
            className={tab === 'visits' ? 'admin-tab admin-tab--active' : 'admin-tab'}
            onClick={() => setTab('visits')}>
            <CalendarDays size={15} /> Visits
          </button>
        </div>

        {tab === 'products' && (
          <ProductsTab supplierId={detail.id} links={links} catalog={catalog}
            currency={currency} reload={reload} />
        )}
        {tab === 'reminders' && (
          <RemindersTab key={detail.id} supplierId={detail.id} supplierName={detail.name}
            lists={lists} currency={currency} reload={reload} onChanged={onChanged}
            onGoToProducts={() => setTab('products')} />
        )}
        {tab === 'visits' && (
          <VisitsTab supplierId={detail.id} visits={visits} reload={reload} />
        )}
      </Drawer>

      <SupplierForm open={editOpen} onClose={() => setEditOpen(false)} initial={detail}
        suggestions={suggestions} idPrefix="supplier-drawer"
        onSaved={() => { setEditOpen(false); void reload(); onChanged(); }} />

      <ConfirmDialog
        open={deactivateOpen}
        onClose={() => setDeactivateOpen(false)}
        onConfirm={() => void deactivate()}
        title="Deactivate this supplier?"
        description="The supplier will be hidden from active lists. Products, reminders and visit history stay intact."
        confirmLabel="Deactivate"
        danger
        loading={deactivating}
      />
    </>
  );
}

/* ------------------------------------------------------------------ */
/* Suppliers dashboard                                                  */
/* ------------------------------------------------------------------ */

export function Suppliers() {
  const toast = useToast();
  const { business } = useAuth();
  const currency = business?.currency ?? 'INR';

  const [queryInput, setQueryInput] = useState('');
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('');
  const [productType, setProductType] = useState('');
  const [sort, setSort] = useState('created-desc');
  const [page, setPage] = useState(1);
  const [rows, setRows] = useState<Supplier[]>([]);
  const [meta, setMeta] = useState({ total: 0, pages: 1, page_size: PAGE_SIZE });
  const [loading, setLoading] = useState(true);
  const [suggestions, setSuggestions] = useState<SupplierCategorySuggestions>({});
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Supplier | null>(null);
  const [profileId, setProfileId] = useState<string | null>(null);
  const [deactivating, setDeactivating] = useState<Supplier | null>(null);

  const loadSuggestions = useCallback(async () => {
    try {
      const response = await api.get<SupplierCategorySuggestions | string[]>('/suppliers/categories');
      setSuggestions(normalizeSuggestions(response));
    } catch {
      // Suggestions are optional; free-text entry still works.
    }
  }, []);

  useEffect(() => { void loadSuggestions(); }, [loadSuggestions]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setQuery(queryInput);
      setPage(1);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [queryInput]);

  const load = useCallback(async () => {
    setLoading(true);
    const field = sort === 'name-asc' || sort === 'name-desc' ? 'name' : 'created_at';
    const order = sort.endsWith('-desc') ? 'desc' : 'asc';
    try {
      const result = await api.get<Paginated<Supplier>>('/suppliers', {
        q: query || undefined,
        category: category || undefined,
        product_type: productType || undefined,
        sort: field,
        order,
        page,
        page_size: PAGE_SIZE,
      });
      setRows(result.items);
      setMeta({ total: result.total, pages: result.pages, page_size: result.page_size });
    } catch (error) {
      toast.error(errorMessage(error, 'Could not load suppliers.'));
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [query, category, productType, sort, page, toast]);

  useEffect(() => { void load(); }, [load]);

  async function deactivate() {
    if (!deactivating) return;
    try {
      await api.delete<MessageResponse>(`/suppliers/${deactivating.id}`);
      toast.success(`${deactivating.name} was deactivated.`);
      setDeactivating(null);
      await load();
      await loadSuggestions();
    } catch (error) {
      toast.error(errorMessage(error, 'Could not deactivate the supplier.'));
    }
  }

  function clearFilters() {
    setQueryInput('');
    setQuery('');
    setCategory('');
    setProductType('');
    setSort('created-desc');
    setPage(1);
  }

  const hasFilters = Boolean(queryInput || category || productType || sort !== 'created-desc');

  return (
    <>
      <PageHeader
        title="Suppliers"
        subtitle="Vendors, their products, purchase reminders and visits in one place"
        actions={
          <Button icon={<Plus size={16} />}
            onClick={() => { setEditing(null); setFormOpen(true); }}>
            Add supplier
          </Button>
        }
      />

      <Card className="filter-bar supplier-filter">
        <div className="filter-bar__search">
          <Search size={17} />
          <Input value={queryInput} onChange={(event) => setQueryInput(event.target.value)}
            placeholder="Search name, company, brand or product…" aria-label="Search suppliers" />
        </div>
        <div className="supplier-filter__field">
          <Input list="supplier-filter-categories" value={category}
            onChange={(event) => { setCategory(event.target.value); setPage(1); }}
            placeholder="Category" aria-label="Filter by category" />
        </div>
        <div className="supplier-filter__field">
          <Input list="supplier-filter-types" value={productType}
            onChange={(event) => { setProductType(event.target.value); setPage(1); }}
            placeholder="Product type" aria-label="Filter by product type" />
        </div>
        <Select value={sort} aria-label="Sort suppliers"
          onChange={(event) => { setSort(event.target.value); setPage(1); }}>
          <option value="created-desc">Newest first</option>
          <option value="created-asc">Oldest first</option>
          <option value="name-asc">Name (A–Z)</option>
          <option value="name-desc">Name (Z–A)</option>
        </Select>
        {hasFilters && (
          <Button variant="ghost" size="sm" icon={<Trash2 size={14} />} onClick={clearFilters}>
            Clear
          </Button>
        )}
        <span className="muted small">{meta.total} supplier{meta.total === 1 ? '' : 's'}</span>
      </Card>
      <SuggestionsDatalist id="supplier-filter-categories" values={suggestions.categories} />
      <SuggestionsDatalist id="supplier-filter-types" values={suggestions.product_types} />

      <Card padded={false}>
        {loading ? (
          <Loader label="Loading suppliers…" full />
        ) : rows.length ? (
          <>
            <div className="table-scroll">
              <table className="data-table supplier-table">
                <thead>
                  <tr>
                    <th>Supplier</th>
                    <th>Contact person</th>
                    <th>Phone / WhatsApp</th>
                    <th>Category</th>
                    <th>Brands</th>
                    <th className="text-right">Products</th>
                    <th>Status</th>
                    <th aria-label="Actions" />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.id} className="clickable-row" onClick={() => setProfileId(row.id)}>
                      <td data-label="Supplier">
                        <div className="cell-with-icon">
                          <span className="avatar avatar--sm">{initials(row.name)}</span>
                          <div>
                            <strong>{row.name}</strong>
                            <small className="cell-sub">{row.email || '—'}</small>
                          </div>
                        </div>
                      </td>
                      <td data-label="Contact person">{row.contact_person || '—'}</td>
                      <td data-label="Phone / WhatsApp">
                        <div className="supplier-contact-cell">
                          {row.phone ? (
                            <a href={`tel:${row.phone.replace(/\s/g, '')}`}
                              onClick={(event) => event.stopPropagation()}>
                              <Phone size={13} /> {row.phone}
                            </a>
                          ) : <span className="muted">—</span>}
                          {row.whatsapp && (
                            <a href={`https://wa.me/${row.whatsapp.replace(/[^\d]/g, '')}`}
                              target="_blank" rel="noreferrer"
                              onClick={(event) => event.stopPropagation()}>
                              <MessageCircle size={13} /> WhatsApp
                            </a>
                          )}
                        </div>
                      </td>
                      <td data-label="Category">
                        {row.category ? <Badge tone="neutral">{row.category}</Badge> : '—'}
                      </td>
                      <td data-label="Brands">
                        <span className="supplier-brands">{row.brands || '—'}</span>
                      </td>
                      <td data-label="Products" className="text-right">
                        <Badge tone="info">{row.product_count ?? 0}</Badge>
                      </td>
                      <td data-label="Status">
                        <StatusBadge status={row.is_active ? 'active' : 'inactive'} />
                      </td>
                      <td data-label="Actions" className="supplier-row-actions">
                        <button type="button" className="icon-btn" aria-label="View supplier"
                          onClick={(event) => { event.stopPropagation(); setProfileId(row.id); }}>
                          <ArrowUpRight size={16} />
                        </button>
                        <button type="button" className="icon-btn" aria-label="Edit supplier"
                          onClick={(event) => { event.stopPropagation(); setEditing(row); setFormOpen(true); }}>
                          <Pencil size={15} />
                        </button>
                        {row.is_active && (
                          <button type="button" className="icon-btn" aria-label="Deactivate supplier"
                            onClick={(event) => { event.stopPropagation(); setDeactivating(row); }}>
                            <PowerOff size={15} />
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination page={page} pages={meta.pages} total={meta.total}
              pageSize={meta.page_size} onPage={setPage} />
          </>
        ) : (
          <EmptyState
            title="No suppliers found"
            description="Try different filters, or add your first supplier."
            icon={<Truck size={24} />}
            action={<Button icon={<Plus size={15} />}
              onClick={() => { setEditing(null); setFormOpen(true); }}>
              Add supplier
            </Button>}
          />
        )}
      </Card>

      <SupplierForm open={formOpen} onClose={() => { setFormOpen(false); setEditing(null); }}
        initial={editing} suggestions={suggestions} idPrefix="supplier-main"
        onSaved={() => { setFormOpen(false); setEditing(null); void load(); void loadSuggestions(); }} />

      {profileId && (
        <SupplierProfileDrawer id={profileId} onClose={() => setProfileId(null)}
          onChanged={() => { void load(); void loadSuggestions(); }}
          currency={currency} suggestions={suggestions} />
      )}

      <ConfirmDialog
        open={Boolean(deactivating)}
        onClose={() => setDeactivating(null)}
        onConfirm={() => void deactivate()}
        title="Deactivate this supplier?"
        description="The supplier will be hidden from active lists. Products, reminders and visit history stay intact."
        confirmLabel="Deactivate"
        danger
      />
    </>
  );
}
