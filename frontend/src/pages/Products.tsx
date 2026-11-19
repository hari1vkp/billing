import { useCallback, useEffect, useState, type FormEvent } from 'react';
import {
  AlertTriangle,
  Archive,
  Boxes,
  Package,
  Pencil,
  Plus,
  RotateCcw,
  Search,
  Wrench,
} from 'lucide-react';
import { api } from '../api/client';
import { useAuth } from '../context/AuthContext';
import {
  Badge,
  Button,
  Card,
  Checkbox,
  ConfirmDialog,
  EmptyState,
  Field,
  Input,
  Loader,
  Modal,
  PageHeader,
  Pagination,
  StatCard,
  Textarea,
  formatDate,
  money,
} from '../components/UI';
import type { Paginated, Product, ProductInput } from '../types';

const PAGE_SIZE = 15;

const round2 = (value: number): number => Math.round(value * 100) / 100;

/** Read-only preview of the wholesale price derived from retail + discount. */
function wholesalePrice(retail: number, discountPercent: number): number {
  return round2(retail * (1 - Math.min(100, Math.max(0, discountPercent)) / 100));
}

function ProductForm({
  open,
  onClose,
  initial,
  defaultGst,
  currency,
  onSaved,
}: {
  open: boolean;
  onClose: () => void;
  initial: Product | null;
  defaultGst: number;
  currency: string;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<ProductInput>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open) return;
    setError('');
    setForm(initial
      ? {
          name: initial.name,
          sku: initial.sku ?? '',
          barcode: initial.barcode ?? '',
          description: initial.description ?? '',
          hsn_code: initial.hsn_code ?? '',
          price: initial.price,
          wholesale_discount_percent: initial.wholesale_discount_percent ?? 0,
          gst_rate: initial.gst_rate,
          stock: initial.stock,
          track_inventory: initial.track_inventory,
          is_service: initial.is_service,
          low_stock_threshold: initial.low_stock_threshold,
        }
      : {
          name: '', sku: '', barcode: '', description: '', hsn_code: '', price: 0,
          wholesale_discount_percent: 0,
          gst_rate: defaultGst, stock: 0, track_inventory: true,
          is_service: false, low_stock_threshold: 10,
        });
  }, [open, initial, defaultGst]);

  function set(field: keyof ProductInput, value: string | number | boolean) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  const retailPrice = Number(form.price) || 0;
  const discountPercent = Math.min(100, Math.max(0, Number(form.wholesale_discount_percent) || 0));
  const wholesalePreview = wholesalePrice(retailPrice, discountPercent);

  async function save(event: FormEvent) {
    event.preventDefault();
    setError('');
    if (!form.name?.trim()) {
      setError('Product name is required.');
      return;
    }
    const payload: ProductInput = {
      ...form,
      name: form.name.trim(),
      sku: form.sku?.trim() || undefined,
      barcode: form.barcode?.trim() || undefined,
      hsn_code: form.hsn_code?.trim() || undefined,
      price: Number(form.price) || 0,
      wholesale_discount_percent: Math.min(
        100,
        Math.max(0, Number(form.wholesale_discount_percent) || 0),
      ),
      gst_rate: Number(form.gst_rate) || 0,
      stock: form.is_service ? 0 : Number(form.stock) || 0,
      track_inventory: form.is_service ? false : Boolean(form.track_inventory),
      low_stock_threshold: Number(form.low_stock_threshold) || 0,
    };
    setSaving(true);
    try {
      if (initial) {
        await api.patch<Product>(`/products/${initial.id}`, payload);
      } else {
        await api.post<Product>('/products', payload);
      }
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save the product.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={initial ? 'Edit product' : 'Add a product'}
      subtitle="Set pricing, GST and inventory preferences."
      size="lg"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" form="product-form" loading={saving}>
            {initial ? 'Save changes' : 'Add product'}
          </Button>
        </>
      }
    >
      {error && <div className="alert alert--error">{error}</div>}
      <form id="product-form" onSubmit={save} className="form-stack">
        <div className="form-grid form-grid--2">
          <Field label="Product / service name" required>
            <Input required value={form.name ?? ''} placeholder="e.g. Cotton T-Shirt"
              onChange={(e) => set('name', e.target.value)} />
          </Field>
          <Field label="SKU">
            <Input value={form.sku ?? ''} placeholder="TSH-001"
              onChange={(e) => set('sku', e.target.value)} />
          </Field>
        </div>
        <Field label="Barcode" hint="Used by the POS scanner and barcode lookup.">
          <Input value={form.barcode ?? ''} placeholder="8901234567890"
            onChange={(e) => set('barcode', e.target.value)} />
        </Field>
        <Field label="Description">
          <Textarea rows={2} value={form.description ?? ''} placeholder="Short description…"
            onChange={(e) => set('description', e.target.value)} />
        </Field>
        <div className="form-grid form-grid--3">
          <Field label="Price" required>
            <Input type="number" min="0" step="0.01" required value={form.price ?? 0}
              onChange={(e) => set('price', e.target.value)} />
          </Field>
          <Field label="GST rate (%)">
            <Input type="number" min="0" max="100" step="0.01" value={form.gst_rate ?? 0}
              onChange={(e) => set('gst_rate', e.target.value)} />
          </Field>
          <Field label="HSN code">
            <Input value={form.hsn_code ?? ''} placeholder="6109"
              onChange={(e) => set('hsn_code', e.target.value)} />
          </Field>
        </div>
        <div className="form-grid form-grid--2">
          <Field label="Wholesale Discount (%)" hint="Applied to the retail price for wholesale bills (0–100).">
            <Input
              type="number"
              min="0"
              max="100"
              step="0.01"
              value={form.wholesale_discount_percent ?? 0}
              onChange={(e) => set('wholesale_discount_percent', e.target.value)}
            />
          </Field>
          <Field label="Wholesale price" hint="Calculated from retail price and discount; read-only.">
            <div className="wholesale-preview" aria-live="polite">
              <strong>{money(wholesalePreview, currency)}</strong>
              <span className="muted small">
                {discountPercent}% off {money(retailPrice, currency)}
              </span>
            </div>
          </Field>
        </div>
        <div className="form-grid form-grid--2">
          <Field label="Opening stock">
            <Input type="number" min="0" step="0.01" disabled={Boolean(form.is_service)}
              value={form.stock ?? 0} onChange={(e) => set('stock', e.target.value)} />
          </Field>
          <Field label="Low stock threshold">
            <Input type="number" min="0" step="1" disabled={Boolean(form.is_service)}
              value={form.low_stock_threshold ?? 10}
              onChange={(e) => set('low_stock_threshold', e.target.value)} />
          </Field>
        </div>
        <div className="checkbox-grid">
          <Checkbox checked={Boolean(form.track_inventory)}
            onChange={(checked) => set('track_inventory', checked)}
            label="Track inventory" hint="Show stock levels and low-stock alerts."
            />
          <Checkbox checked={Boolean(form.is_service)}
            onChange={(checked) => set('is_service', checked)}
            label="This is a service" hint="Services have no inventory to track." />
        </div>
      </form>
    </Modal>
  );
}

export function Products({ embedded = false }: { embedded?: boolean }) {
  const { business } = useAuth();
  const currency = business?.currency ?? 'INR';
  const [queryInput, setQueryInput] = useState('');
  const [query, setQuery] = useState('');
  const [lowStockOnly, setLowStockOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [products, setProducts] = useState<Product[]>([]);
  const [meta, setMeta] = useState({ total: 0, pages: 1, page_size: PAGE_SIZE });
  const [loading, setLoading] = useState(true);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Product | null>(null);
  const [archiveTarget, setArchiveTarget] = useState<Product | null>(null);
  const [archiving, setArchiving] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setQuery(queryInput);
      setPage(1);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [queryInput]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api.get<Paginated<Product>>('/products', {
        query: query || undefined,
        low_stock_only: lowStockOnly || undefined,
        page,
        page_size: PAGE_SIZE,
      });
      setProducts(result.items);
      setMeta({ total: result.total, pages: result.pages, page_size: result.page_size });
    } finally {
      setLoading(false);
    }
  }, [query, lowStockOnly, page]);

  useEffect(() => {
    void load();
  }, [load]);

  async function toggleArchive() {
    if (!archiveTarget) return;
    setArchiving(true);
    try {
      await api.patch<Product>(`/products/${archiveTarget.id}`, { is_active: !archiveTarget.is_active });
      setArchiveTarget(null);
      void load();
    } finally {
      setArchiving(false);
    }
  }

  const lowStockCount = products.filter((product) => product.is_low_stock && product.is_active).length;
  const serviceCount = products.filter((product) => product.is_service && product.is_active).length;
  const stockValue = products.reduce(
    (sum, product) => sum + (product.track_inventory ? product.price * product.stock : 0),
    0,
  );

  return (
    <>
      {!embedded && (
        <PageHeader
          title="Products & Services"
          subtitle="Your catalogue, pricing and stock at a glance"
          actions={<Button icon={<Plus size={16} />} onClick={() => { setEditing(null); setFormOpen(true); }}>
            Add product
          </Button>}
        />
      )}

      <div className="stat-grid stat-grid--4">
        <StatCard label="Items on this page" value={products.length} icon={<Package size={19} />} tone="info" />
        <StatCard label="Low stock" value={lowStockCount} icon={<AlertTriangle size={19} />} tone="danger"
          hint="Needs your attention" />
        <StatCard label="Services" value={serviceCount} icon={<Wrench size={19} />} tone="success" />
        <StatCard label="Stock value (page)" value={money(stockValue, currency)} icon={<Boxes size={19} />} tone="info" />
      </div>

      <Card className="filter-bar">
        <div className="filter-bar__search">
          <Search size={17} />
          <Input value={queryInput} onChange={(e) => setQueryInput(e.target.value)}
            placeholder="Search by name, SKU, barcode or HSN…" aria-label="Search products" />
        </div>
        <button
          type="button"
          className={`toggle-chip ${lowStockOnly ? 'toggle-chip--active' : ''}`}
          onClick={() => { setLowStockOnly((value) => !value); setPage(1); }}
        >
          <AlertTriangle size={15} /> Low stock only
        </button>
        <span className="muted small">{meta.total} item{meta.total === 1 ? '' : 's'}</span>
      </Card>

      <Card padded={false}>
        {loading ? (
          <Loader label="Loading products…" full />
        ) : products.length ? (
          <>
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Product</th>
                    <th>SKU / Barcode / HSN</th>
                    <th className="text-right">Price</th>
                    <th className="text-right">GST</th>
                    <th>Stock</th>
                    <th>Type</th>
                    <th>Status</th>
                    <th className="text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {products.map((product) => (
                    <tr key={product.id}>
                      <td>
                        <div className="cell-with-icon">
                          <span className={`cell-icon ${product.is_service ? 'cell-icon--service' : ''}`}>
                            {product.is_service ? <Wrench size={16} /> : <Package size={16} />}
                          </span>
                          <div>
                            <strong>{product.name}</strong>
                            <small className="cell-sub">{product.description || `Added ${formatDate(product.created_at)}`}</small>
                          </div>
                        </div>
                      </td>
                      <td>
                        <strong className="small mono">{product.sku || '—'}</strong>
                        <small className="cell-sub">Barcode: {product.barcode || '—'}</small>
                        <small className="cell-sub">HSN: {product.hsn_code || '—'}</small>
                      </td>
                      <td className="text-right strong">
                        {money(product.price, currency)}
                        <small className="wholesale-price">
                          Wholesale {money(
                            product.wholesale_price ?? wholesalePrice(
                              product.price,
                              product.wholesale_discount_percent ?? 0,
                            ),
                            currency,
                          )}
                        </small>
                      </td>
                      <td className="text-right">{product.gst_rate}%</td>
                      <td>
                        {product.is_service ? (
                          <span className="muted">Not tracked</span>
                        ) : product.track_inventory ? (
                          <div className="stock-cell">
                            <strong>{product.stock}</strong>
                            {product.is_low_stock && <Badge tone="warning" dot>Low</Badge>}
                          </div>
                        ) : (
                          <span className="muted">Untracked</span>
                        )}
                      </td>
                      <td><Badge tone={product.is_service ? 'info' : 'neutral'}>{product.is_service ? 'Service' : 'Product'}</Badge></td>
                      <td><Badge tone={product.is_active ? 'success' : 'neutral'} dot>{product.is_active ? 'Active' : 'Archived'}</Badge></td>
                      <td>
                        <div className="row-actions">
                          <button type="button" className="icon-btn" aria-label="Edit product"
                            onClick={() => { setEditing(product); setFormOpen(true); }}>
                            <Pencil size={15} />
                          </button>
                          <button type="button" className="icon-btn" aria-label={product.is_active ? 'Archive product' : 'Restore product'}
                            onClick={() => setArchiveTarget(product)}>
                            {product.is_active ? <Archive size={15} /> : <RotateCcw size={15} />}
                          </button>
                        </div>
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
          <EmptyState title="No products found" description="Try a different search or add a new product."
            icon={<Package size={24} />}
            action={<Button icon={<Plus size={15} />} onClick={() => { setEditing(null); setFormOpen(true); }}>Add product</Button>} />
        )}
      </Card>

      <ProductForm open={formOpen} onClose={() => { setFormOpen(false); setEditing(null); }}
        initial={editing} defaultGst={business?.default_gst_rate ?? 18} currency={currency}
        onSaved={() => { setFormOpen(false); setEditing(null); void load(); }} />

      <ConfirmDialog
        open={Boolean(archiveTarget)}
        onClose={() => setArchiveTarget(null)}
        onConfirm={() => void toggleArchive()}
        title={archiveTarget?.is_active ? 'Archive this product?' : 'Restore this product?'}
        description={archiveTarget?.is_active
          ? 'Archived products remain on existing invoices but disappear from the invoice picker.'
          : 'This product will become available again on new invoices.'}
        confirmLabel={archiveTarget?.is_active ? 'Archive' : 'Restore'}
        loading={archiving}
      />
    </>
  );
}
