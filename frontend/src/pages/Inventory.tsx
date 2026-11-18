import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { AlertTriangle, Boxes, Package, SlidersHorizontal, Upload, X } from 'lucide-react';
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
  PageHeader,
  Pagination,
  Select,
  Textarea,
  formatDate,
  useToast,
} from '../components/UI';
import { Products } from './Products';
import { ImportProducts } from './ImportProducts';
import type { Paginated, Product, StockMovement } from '../types';

const PAGE_SIZE = 15;

const OWNER_REASONS = [
  { value: 'found', label: 'Stock found' },
  { value: 'damaged', label: 'Damaged' },
  { value: 'return', label: 'Customer return' },
  { value: 'correction', label: 'Correction' },
  { value: 'purchase', label: 'Purchase / restock' },
  { value: 'sale', label: 'Sale' },
  { value: 'opening', label: 'Opening stock' },
  { value: 'audit', label: 'Audit' },
  { value: 'other', label: 'Other' },
];

export function Inventory() {
  const toast = useToast();
  const [tab, setTab] = useState<'products' | 'movements'>('products');
  const [products, setProducts] = useState<Product[]>([]);
  const [movements, setMovements] = useState<StockMovement[]>([]);
  const [productId, setProductId] = useState('');
  const [reason, setReason] = useState('');
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [page, setPage] = useState(1);
  const [meta, setMeta] = useState({ total: 0, pages: 1, page_size: PAGE_SIZE });
  const [loading, setLoading] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [adjustOpen, setAdjustOpen] = useState(false);
  const [adjustForm, setAdjustForm] = useState({
    product_id: '',
    quantity_change: '',
    reason: 'correction',
    reference: '',
    notes: '',
  });
  const [saving, setSaving] = useState(false);

  const loadProducts = useCallback(async () => {
    try {
      const result = await api.get<Paginated<Product>>('/products', { page_size: 200 });
      setProducts(result.items);
    } catch {
      // Adjustment picker will stay empty if products cannot be loaded.
    }
  }, []);

  useEffect(() => {
    void loadProducts();
  }, [loadProducts]);

  const loadMovements = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api.get<Paginated<StockMovement>>('/inventory/movements', {
        product_id: productId || undefined,
        reason: reason || undefined,
        from_date: fromDate || undefined,
        to_date: toDate || undefined,
        page,
        page_size: PAGE_SIZE,
      });
      setMovements(result.items);
      setMeta({ total: result.total, pages: result.pages, page_size: result.page_size });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not load stock movements.');
      setMovements([]);
    } finally {
      setLoading(false);
    }
  }, [productId, reason, fromDate, toDate, page, toast]);

  useEffect(() => {
    if (tab === 'movements') void loadMovements();
  }, [tab, loadMovements]);

  function openAdjust() {
    setAdjustForm({
      product_id: products[0]?.id ?? '',
      quantity_change: '',
      reason: 'correction',
      reference: '',
      notes: '',
    });
    setAdjustOpen(true);
  }

  async function submitAdjust(event: FormEvent) {
    event.preventDefault();
    const change = Number(adjustForm.quantity_change);
    if (!adjustForm.product_id) {
      toast.error('Select a product.');
      return;
    }
    if (!Number.isFinite(change) || change === 0) {
      toast.error('Enter a non-zero quantity change.');
      return;
    }
    setSaving(true);
    try {
      await api.post<StockMovement>('/inventory/adjust', {
        product_id: adjustForm.product_id,
        quantity_change: change,
        reason: adjustForm.reason,
        ...(adjustForm.reference.trim() ? { reference: adjustForm.reference.trim() } : {}),
        ...(adjustForm.notes.trim() ? { notes: adjustForm.notes.trim() } : {}),
      });
      toast.success('Stock adjustment recorded.');
      setAdjustOpen(false);
      if (tab === 'movements') await loadMovements();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not record the adjustment.');
    } finally {
      setSaving(false);
    }
  }

  const hasFilters = Boolean(productId || reason || fromDate || toDate);

  return (
    <>
      <PageHeader
        title="Inventory"
        subtitle="Products, stock levels and every adjustment in one place"
        actions={
          <>
            <Button variant="secondary" icon={<Upload size={16} />} onClick={() => setImportOpen(true)}>
              Import Products
            </Button>
            <Button icon={<SlidersHorizontal size={16} />} onClick={openAdjust}>
              Adjust stock
            </Button>
          </>
        }
      />

      <div className="admin-tabs" role="tablist" aria-label="Inventory sections">
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'products'}
          className={tab === 'products' ? 'admin-tab admin-tab--active' : 'admin-tab'}
          onClick={() => setTab('products')}
        >
          <Package size={16} /> Products
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'movements'}
          className={tab === 'movements' ? 'admin-tab admin-tab--active' : 'admin-tab'}
          onClick={() => setTab('movements')}
        >
          <Boxes size={16} /> Stock movements
        </button>
      </div>

      {tab === 'products' ? (
        <Products embedded />
      ) : (
        <>
          <Card className="filter-bar">
            <Select value={productId} aria-label="Filter by product"
              onChange={(event) => { setProductId(event.target.value); setPage(1); }}>
              <option value="">All products</option>
              {products.map((product) => (
                <option key={product.id} value={product.id}>{product.name}</option>
              ))}
            </Select>
            <Select value={reason} aria-label="Filter by reason"
              onChange={(event) => { setReason(event.target.value); setPage(1); }}>
              <option value="">All reasons</option>
              {OWNER_REASONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </Select>
            <div className="date-range">
              <Input type="date" value={fromDate} max={toDate || undefined} aria-label="From date"
                onChange={(event) => { setFromDate(event.target.value); setPage(1); }} />
              <span>to</span>
              <Input type="date" value={toDate} min={fromDate || undefined} aria-label="To date"
                onChange={(event) => { setToDate(event.target.value); setPage(1); }} />
            </div>
            {hasFilters && (
              <Button variant="ghost" size="sm" icon={<X size={15} />}
                onClick={() => {
                  setProductId('');
                  setReason('');
                  setFromDate('');
                  setToDate('');
                  setPage(1);
                }}>
                Clear
              </Button>
            )}
            <span className="muted small">{meta.total} movement{meta.total === 1 ? '' : 's'}</span>
          </Card>

          <Card padded={false}>
            {loading ? (
              <Loader label="Loading stock movements…" full />
            ) : movements.length ? (
              <>
                <div className="table-scroll">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Product</th>
                        <th className="text-right">Change</th>
                        <th className="text-right">Before</th>
                        <th className="text-right">After</th>
                        <th>Reason</th>
                        <th>Reference</th>
                        <th>Performed by</th>
                        <th>Date</th>
                      </tr>
                    </thead>
                    <tbody>
                      {movements.map((movement) => (
                        <tr key={movement.id}>
                          <td>
                            <div className="cell-with-icon">
                              <span className="cell-icon"><Package size={16} /></span>
                              <div>
                                <strong>{movement.product_name}</strong>
                                <small className="cell-sub">
                                  {movement.barcode || movement.sku || '—'}
                                </small>
                              </div>
                            </div>
                            {movement.notes && <small className="cell-sub">{movement.notes}</small>}
                          </td>
                          <td className={`text-right strong ${movement.quantity_change > 0 ? 'text-success' : 'text-danger'}`}>
                            {movement.quantity_change > 0 ? '+' : ''}{movement.quantity_change}
                          </td>
                          <td className="text-right">{movement.quantity_before}</td>
                          <td className="text-right strong">{movement.quantity_after}</td>
                          <td><Badge tone={movement.quantity_change > 0 ? 'success' : 'warning'}>{movement.reason}</Badge></td>
                          <td className="small mono">{movement.reference || '—'}</td>
                          <td>{movement.performed_by_name || '—'}</td>
                          <td>{formatDate(movement.created_at, true)}</td>
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
                title="No stock movements found"
                description={hasFilters ? 'Try changing the filters.' : 'Adjustments will appear here.'}
                icon={<AlertTriangle size={24} />}
              />
            )}
          </Card>
        </>
      )}

      <Modal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        title="Import products"
        subtitle="Add products from a file, barcode, photo or by hand."
        size="xl"
      >
        <ImportProducts
          onClose={() => setImportOpen(false)}
          onImported={() => { void loadProducts(); }}
        />
      </Modal>

      <Modal
        open={adjustOpen}
        onClose={() => setAdjustOpen(false)}
        title="Adjust stock"
        subtitle="Record a stock correction with a full audit trail."
        size="md"
        footer={
          <>
            <Button variant="secondary" onClick={() => setAdjustOpen(false)}>Cancel</Button>
            <Button type="submit" form="owner-adjust-form" loading={saving}>Record adjustment</Button>
          </>
        }
      >
        <form id="owner-adjust-form" onSubmit={submitAdjust} className="form-stack">
          <Field label="Product" required>
            <Select value={adjustForm.product_id} required
              onChange={(event) => setAdjustForm({ ...adjustForm, product_id: event.target.value })}>
              <option value="">Select a product…</option>
              {products.map((product) => (
                <option key={product.id} value={product.id}>{product.name}</option>
              ))}
            </Select>
          </Field>
          <div className="form-grid form-grid--2">
            <Field label="Quantity change" required hint="Negative values reduce stock.">
              <Input type="number" step="1" required value={adjustForm.quantity_change}
                placeholder="e.g. 10 or -3"
                onChange={(event) => setAdjustForm({ ...adjustForm, quantity_change: event.target.value })} />
            </Field>
            <Field label="Reason" required>
              <Select value={adjustForm.reason}
                onChange={(event) => setAdjustForm({ ...adjustForm, reason: event.target.value })}>
                {OWNER_REASONS.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </Select>
            </Field>
          </div>
          <Field label="Reference (optional)">
            <Input value={adjustForm.reference} placeholder="PO number, invoice, etc."
              onChange={(event) => setAdjustForm({ ...adjustForm, reference: event.target.value })} />
          </Field>
          <Field label="Notes (optional)">
            <Textarea rows={2} value={adjustForm.notes}
              onChange={(event) => setAdjustForm({ ...adjustForm, notes: event.target.value })} />
          </Field>
        </form>
      </Modal>
    </>
  );
}
