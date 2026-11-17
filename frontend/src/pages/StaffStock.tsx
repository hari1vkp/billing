import { useCallback, useEffect, useState, type FormEvent } from 'react';
import {
  AlertTriangle,
  Boxes,
  Info,
  Package,
  Search,
  SlidersHorizontal,
  X,
} from 'lucide-react';
import { api } from '../api/client';
import {
  Badge,
  Button,
  Card,
  EmptyState,
  Field,
  Input,
  Loader,
  Modal,
  Select,
  Textarea,
  useToast,
} from '../components/UI';
import type { Paginated, Product, StockMovement } from '../types';

const STAFF_REASONS = [
  { value: 'found', label: 'Stock found' },
  { value: 'damaged', label: 'Damaged' },
  { value: 'return', label: 'Customer return' },
  { value: 'correction', label: 'Correction' },
];

interface AdjustTarget {
  product: Product;
}

export function StaffStock() {
  const toast = useToast();
  const [searchInput, setSearchInput] = useState('');
  const [query, setQuery] = useState('');
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [lowStockOnly, setLowStockOnly] = useState(false);
  const [target, setTarget] = useState<AdjustTarget | null>(null);
  const [quantityChange, setQuantityChange] = useState('');
  const [reason, setReason] = useState('found');
  const [notes, setNotes] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setQuery(searchInput.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api.get<Paginated<Product>>('/products', {
        query: query || undefined,
        page: 1,
        page_size: 100,
      });
      setProducts(
        result.items.filter((product) =>
          product.is_active !== false && (!lowStockOnly || product.is_low_stock),
        ),
      );
    } catch {
      setProducts([]);
    } finally {
      setLoading(false);
    }
  }, [query, lowStockOnly]);

  useEffect(() => {
    void load();
  }, [load]);

  function openAdjust(product: Product) {
    setTarget({ product });
    setQuantityChange('');
    setReason('found');
    setNotes('');
  }

  async function submitAdjust(event: FormEvent) {
    event.preventDefault();
    if (!target) return;
    const change = Number(quantityChange);
    if (!Number.isFinite(change) || change === 0) {
      toast.error('Enter a non-zero quantity change.');
      return;
    }
    if (Math.abs(change) > 20) {
      toast.error('Staff adjustments are limited to 20 units.');
      return;
    }
    setSaving(true);
    try {
      await api.post<StockMovement>('/inventory/adjust', {
        product_id: target.product.id,
        quantity_change: change,
        reason,
        ...(notes.trim() ? { notes: notes.trim() } : {}),
      });
      toast.success(`Stock updated for ${target.product.name}.`);
      setTarget(null);
      await load();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not adjust stock.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="pos-page staff-stock-page">
      <div className="stock-page-head">
        <div>
          <span className="pos-eyebrow">STOCK</span>
          <h1>Stock levels</h1>
          <p>Check availability and make small, reason-coded adjustments.</p>
        </div>
        <Badge tone="info" dot>Limited adjustments</Badge>
      </div>

      <Card className="stock-notice">
        <Info size={17} />
        <span>Adjustments are limited to 20 units and require a reason.</span>
      </Card>

      <Card className="filter-bar">
        <div className="filter-bar__search">
          <Search size={17} />
          <Input
            value={searchInput}
            onChange={(event) => setSearchInput(event.target.value)}
            placeholder="Search products by name, SKU or barcode…"
            aria-label="Search stock"
          />
          {searchInput && (
            <button type="button" className="icon-btn" aria-label="Clear search" onClick={() => setSearchInput('')}>
              <X size={15} />
            </button>
          )}
        </div>
        <button
          type="button"
          className={`toggle-chip ${lowStockOnly ? 'toggle-chip--active' : ''}`}
          onClick={() => setLowStockOnly((value) => !value)}
        >
          <AlertTriangle size={15} /> Low stock only
        </button>
        <span className="muted small">{products.length} item{products.length === 1 ? '' : 's'}</span>
      </Card>

      <Card padded={false}>
        {loading ? (
          <Loader label="Loading stock…" full />
        ) : products.length ? (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Product</th>
                  <th>Barcode / SKU</th>
                  <th className="text-right">Stock</th>
                  <th>Status</th>
                  <th className="text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {products.map((product) => {
                  const low = product.is_low_stock || product.stock <= (product.low_stock_threshold ?? 0);
                  return (
                    <tr key={product.id}>
                      <td>
                        <div className="cell-with-icon">
                          <span className="cell-icon"><Package size={16} /></span>
                          <div>
                            <strong>{product.name}</strong>
                            <small className="cell-sub">{product.is_service ? 'Service' : 'Physical product'}</small>
                          </div>
                        </div>
                      </td>
                      <td>
                        <strong className="small mono">{product.barcode || '—'}</strong>
                        <small className="cell-sub">SKU: {product.sku || '—'}</small>
                      </td>
                      <td className="text-right strong">{product.is_service ? '—' : product.stock}</td>
                      <td>
                        {product.is_service ? (
                          <Badge tone="neutral">N/A</Badge>
                        ) : low ? (
                          <Badge tone="warning" dot>Low stock</Badge>
                        ) : (
                          <Badge tone="success" dot>In stock</Badge>
                        )}
                      </td>
                      <td className="text-right">
                        <Button size="sm" variant="secondary" icon={<SlidersHorizontal size={14} />}
                          onClick={() => openAdjust(product)}>
                          Adjust
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            title="No products found"
            description="Try a different search term or low-stock filter."
            icon={<Boxes size={24} />}
          />
        )}
      </Card>

      <Modal
        open={Boolean(target)}
        onClose={() => setTarget(null)}
        title="Adjust stock"
        subtitle={target ? `${target.product.name} · current stock ${target.product.stock}` : ''}
        size="sm"
        footer={
          <>
            <Button variant="secondary" onClick={() => setTarget(null)}>Cancel</Button>
            <Button type="submit" form="staff-adjust-form" loading={saving}>Save adjustment</Button>
          </>
        }
      >
        <div className="alert alert--info">
          Adjustments are limited to 20 units and require a reason. Use a negative number to reduce stock.
        </div>
        <form id="staff-adjust-form" onSubmit={submitAdjust} className="form-stack">
          <Field label="Quantity change" required hint="Positive to add stock, negative to remove.">
            <Input
              type="number"
              min="-20"
              max="20"
              step="1"
              required
              autoFocus
              value={quantityChange}
              placeholder="e.g. 5 or -2"
              onChange={(event) => setQuantityChange(event.target.value)}
            />
          </Field>
          <Field label="Reason" required>
            <Select value={reason} onChange={(event) => setReason(event.target.value)}>
              {STAFF_REASONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </Select>
          </Field>
          <Field label="Notes (optional)">
            <Textarea rows={2} value={notes} placeholder="Where the stock came from or went…"
              onChange={(event) => setNotes(event.target.value)} />
          </Field>
        </form>
      </Modal>
    </div>
  );
}
