import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  ArrowDownToLine,
  CheckCircle2,
  Copy,
  Download,
  ExternalLink,
  FileText,
  FilterX,
  Link2,
  Pencil,
  Plus,
  QrCode,
  ReceiptText,
  Search,
  Trash2,
  XCircle,
} from 'lucide-react';
import { api, downloadFile } from '../api/client';
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
  money,
  statusTone,
  todayInput,
} from '../components/UI';
import type {
  Business,
  Customer,
  Invoice,
  InvoiceInput,
  InvoiceListItem,
  Paginated,
  Payment,
  PaymentInput,
  Product,
  QrResponse,
} from '../types';

const PAGE_SIZE = 15;

interface DraftItem {
  key: number;
  product_id: string;
  description: string;
  quantity: string;
  unit_price: string;
  discount_percent: string;
  gst_rate: string;
}

function emptyItem(key: number, defaultGst = 18): DraftItem {
  return {
    key,
    product_id: '',
    description: '',
    quantity: '1',
    unit_price: '0',
    discount_percent: '0',
    gst_rate: String(defaultGst),
  };
}

function computeTotals(
  items: DraftItem[],
  discountPercent: number,
): { subtotal: number; itemDiscount: number; taxable: number; tax: number; invoiceDiscount: number; total: number } {
  let subtotal = 0;
  let itemDiscount = 0;
  let taxable = 0;
  let tax = 0;
  items.forEach((item) => {
    const base = (Number(item.quantity) || 0) * (Number(item.unit_price) || 0);
    const disc = base * ((Number(item.discount_percent) || 0) / 100);
    const taxableAmount = base - disc;
    subtotal += base;
    itemDiscount += disc;
    taxable += taxableAmount;
    tax += taxableAmount * ((Number(item.gst_rate) || 0) / 100);
  });
  const afterTax = taxable + tax;
  const invoiceDiscount = afterTax * (discountPercent / 100);
  return {
    subtotal,
    itemDiscount,
    taxable,
    tax,
    invoiceDiscount,
    total: afterTax - invoiceDiscount,
  };
}

async function copyText(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    textarea.remove();
  }
}

/* ------------------------------------------------------------------ */
/* Invoice create / edit form                                           */
/* ------------------------------------------------------------------ */

function InvoiceForm({
  open,
  onClose,
  customers,
  products,
  initial,
  initialCustomerId = '',
  currency,
  business,
  onSaved,
}: {
  open: boolean;
  onClose: () => void;
  customers: Customer[];
  products: Product[];
  initial: Invoice | null;
  initialCustomerId?: string;
  currency: string;
  business: Business | null;
  onSaved: (invoice: Invoice, isEdit: boolean) => void;
}) {
  const [customerId, setCustomerId] = useState('');
  const [issueDate, setIssueDate] = useState(todayInput());
  const [dueDate, setDueDate] = useState('');
  const [items, setItems] = useState<DraftItem[]>([emptyItem(0)]);
  const [discountPercent, setDiscountPercent] = useState('0');
  const [notes, setNotes] = useState('');
  const [status, setStatus] = useState<'draft' | 'unpaid'>('unpaid');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const keyRef = useRef(1);

  useEffect(() => {
    if (!open) return;
    setError('');
    if (initial) {
      setCustomerId(initial.customer_id);
      setIssueDate(initial.issue_date);
      setDueDate(initial.due_date ?? '');
      setItems(
        initial.items.length
          ? initial.items.map((item, index) => ({
              key: index,
              product_id: item.product_id ?? '',
              description: item.description,
              quantity: String(item.quantity),
              unit_price: String(item.unit_price),
              discount_percent: String(item.discount_percent),
              gst_rate: String(item.gst_rate),
            }))
          : [emptyItem(0, business?.default_gst_rate ?? 18)],
      );
      setDiscountPercent(String(initial.discount_percent ?? 0));
      setNotes(initial.notes ?? '');
      setStatus(initial.status === 'draft' ? 'draft' : 'unpaid');
    } else {
      setCustomerId(initialCustomerId);
      setIssueDate(todayInput());
      setDueDate('');
      keyRef.current = 1;
      setItems([emptyItem(0, business?.default_gst_rate ?? 18)]);
      setDiscountPercent('0');
      setNotes('');
      setStatus('unpaid');
    }
  }, [open, initial, initialCustomerId, business]);

  const totals = computeTotals(items, Number(discountPercent) || 0);

  function updateItem(key: number, patch: Partial<DraftItem>) {
    setItems((prev) => prev.map((item) => (item.key === key ? { ...item, ...patch } : item)));
  }

  function onProductChange(key: number, productId: string) {
    const product = products.find((entry) => entry.id === productId);
    if (!product) {
      updateItem(key, { product_id: '', description: '', unit_price: '0' });
      return;
    }
    updateItem(key, {
      product_id: product.id,
      description: product.name,
      unit_price: String(product.price),
      gst_rate: String(product.gst_rate),
    });
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    setError('');
    if (!customerId) {
      setError('Please select a customer.');
      return;
    }
    const cleaned = items.filter((item) => item.description.trim() && Number(item.quantity) > 0);
    if (!cleaned.length) {
      setError('Add at least one item with a description and quantity.');
      return;
    }

    const payload: InvoiceInput = {
      customer_id: customerId,
      issue_date: issueDate,
      ...(dueDate ? { due_date: dueDate } : {}),
      items: cleaned.map((item) => ({
        ...(item.product_id ? { product_id: item.product_id } : {}),
        description: item.description.trim(),
        quantity: Number(item.quantity),
        unit_price: Number(item.unit_price) || 0,
        discount_percent: Number(item.discount_percent) || 0,
        gst_rate: Number(item.gst_rate) || 0,
      })),
      discount_percent: Number(discountPercent) || 0,
      notes: notes.trim() || undefined,
    };

    setSaving(true);
    try {
      const result = initial
        ? await api.patch<Invoice>(`/invoices/${initial.id}`, payload)
        : await api.post<Invoice>('/invoices', { ...payload, status });
      onSaved(result, Boolean(initial));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save the invoice.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={initial ? `Edit invoice ${initial.invoice_number}` : 'Create a new invoice'}
      subtitle="Add the customer and line items — totals update as you go."
      size="xl"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" form="invoice-form" loading={saving}>
            {initial ? 'Save changes' : 'Create invoice'}
          </Button>
        </>
      }
    >
      {error && <div className="alert alert--error">{error}</div>}
      <form id="invoice-form" onSubmit={save} className="invoice-form">
        <div className="form-grid form-grid--3">
          <Field label="Customer" required className="col-span-2">
            <Select value={customerId} onChange={(e) => setCustomerId(e.target.value)} required>
              <option value="">Select a customer…</option>
              {customers.map((customer) => (
                <option key={customer.id} value={customer.id}>
                  {customer.name}{customer.phone ? ` · ${customer.phone}` : ''}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Invoice status" required>
            <Select value={status} onChange={(e) => setStatus(e.target.value as 'draft' | 'unpaid')} disabled={Boolean(initial)}>
              <option value="unpaid">Unpaid (final)</option>
              <option value="draft">Draft</option>
            </Select>
          </Field>
          <Field label="Issue date" required>
            <Input type="date" value={issueDate} onChange={(e) => setIssueDate(e.target.value)} required />
          </Field>
          <Field label="Due date" hint="Defaults to 15 days after issue date">
            <Input type="date" value={dueDate} min={issueDate} onChange={(e) => setDueDate(e.target.value)} />
          </Field>
          <Field label="Discount on invoice (%)">
            <Input
              type="number"
              min="0"
              max="100"
              step="0.01"
              value={discountPercent}
              onChange={(e) => setDiscountPercent(e.target.value)}
            />
          </Field>
        </div>

        <div className="form-section">
          <div className="form-section__head">
            <h4>Line items</h4>
            <span className="muted">Pick a product to auto-fill price and GST</span>
          </div>
          <div className="table-scroll">
            <table className="data-table item-table">
              <thead>
                <tr>
                  <th className="col-product">Product / Service</th>
                  <th>Description</th>
                  <th className="col-small">Qty</th>
                  <th className="col-price">Rate</th>
                  <th className="col-small">Disc %</th>
                  <th className="col-small">GST %</th>
                  <th className="text-right col-total">Amount</th>
                  <th aria-label="Remove" />
                </tr>
              </thead>
              <tbody>
                {items.map((item) => {
                  const base = (Number(item.quantity) || 0) * (Number(item.unit_price) || 0);
                  const afterDisc = base - base * ((Number(item.discount_percent) || 0) / 100);
                  const lineTotal = afterDisc + afterDisc * ((Number(item.gst_rate) || 0) / 100);
                  return (
                    <tr key={item.key}>
                      <td>
                        <Select
                          value={item.product_id}
                          onChange={(e) => onProductChange(item.key, e.target.value)}
                        >
                          <option value="">Custom item</option>
                          {products.filter((p) => p.is_active).map((product) => (
                            <option key={product.id} value={product.id}>{product.name}</option>
                          ))}
                        </Select>
                      </td>
                      <td>
                        <Input
                          value={item.description}
                          placeholder="Item description"
                          onChange={(e) => updateItem(item.key, { description: e.target.value })}
                        />
                      </td>
                      <td>
                        <Input
                          type="number"
                          min="0.01"
                          step="0.01"
                          value={item.quantity}
                          onChange={(e) => updateItem(item.key, { quantity: e.target.value })}
                        />
                      </td>
                      <td>
                        <Input
                          type="number"
                          min="0"
                          step="0.01"
                          value={item.unit_price}
                          onChange={(e) => updateItem(item.key, { unit_price: e.target.value })}
                        />
                      </td>
                      <td>
                        <Input
                          type="number"
                          min="0"
                          max="100"
                          step="0.01"
                          value={item.discount_percent}
                          onChange={(e) => updateItem(item.key, { discount_percent: e.target.value })}
                        />
                      </td>
                      <td>
                        <Input
                          type="number"
                          min="0"
                          max="100"
                          step="0.01"
                          value={item.gst_rate}
                          onChange={(e) => updateItem(item.key, { gst_rate: e.target.value })}
                        />
                      </td>
                      <td className="text-right strong">{money(lineTotal, currency)}</td>
                      <td>
                        <button
                          type="button"
                          className="icon-btn icon-btn--danger"
                          onClick={() => setItems((prev) => prev.filter((entry) => entry.key !== item.key))}
                          disabled={items.length === 1}
                          aria-label="Remove item"
                        >
                          <Trash2 size={15} />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <Button
            variant="subtle"
            size="sm"
            icon={<Plus size={15} />}
            onClick={() => {
              setItems((prev) => [...prev, emptyItem(keyRef.current++, business?.default_gst_rate ?? 18)]);
            }}
          >
            Add another item
          </Button>
        </div>

        <div className="form-grid invoice-form__bottom">
          <Field label="Notes (optional)">
            <Textarea
              rows={3}
              value={notes}
              placeholder="Payment terms, thank-you note…"
              onChange={(e) => setNotes(e.target.value)}
            />
          </Field>
          <div className="totals-panel">
            <div className="totals-row"><span>Subtotal</span><strong>{money(totals.subtotal, currency)}</strong></div>
            <div className="totals-row"><span>Item discounts</span><strong>− {money(totals.itemDiscount, currency)}</strong></div>
            <div className="totals-row"><span>Taxable amount</span><strong>{money(totals.taxable, currency)}</strong></div>
            <div className="totals-row"><span>GST</span><strong>{money(totals.tax, currency)}</strong></div>
            {totals.invoiceDiscount > 0 && (
              <div className="totals-row"><span>Invoice discount</span><strong>− {money(totals.invoiceDiscount, currency)}</strong></div>
            )}
            <div className="totals-row totals-row--total"><span>Invoice total</span><strong>{money(totals.total, currency)}</strong></div>
          </div>
        </div>
      </form>
    </Modal>
  );
}

/* ------------------------------------------------------------------ */
/* Invoice detail drawer                                                */
/* ------------------------------------------------------------------ */

function InvoiceDetail({
  id,
  onClose,
  onEdit,
  onChanged,
  currency,
}: {
  id: string;
  onClose: () => void;
  onEdit: (invoice: Invoice) => void;
  onChanged: () => void;
  currency: string;
}) {
  const [invoice, setInvoice] = useState<Invoice | null>(null);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [qr, setQr] = useState<QrResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [qrLoading, setQrLoading] = useState(false);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [payOpen, setPayOpen] = useState(false);
  const [payForm, setPayForm] = useState({
    amount: '',
    method: 'upi',
    reference: '',
    payer_vpa: '',
    payment_date: todayInput(),
    notes: '',
    confirm: true,
  });
  const [paySaving, setPaySaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const inv = await api.get<Invoice>(`/invoices/${id}`);
      setInvoice(inv);
      const result = await api
        .get<Paginated<Payment>>('/payments', { query: inv.invoice_number, page_size: 200 })
        .catch(() => null);
      setPayments((result?.items ?? []).filter((payment) => payment.invoice_id === id));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  async function generateQr() {
    setQrLoading(true);
    try {
      setQr(await api.get<QrResponse>(`/invoices/${id}/qr`));
    } catch (err) {
      window.alert(err instanceof Error ? err.message : 'Could not generate QR code.');
    } finally {
      setQrLoading(false);
    }
  }

  async function setStatus(status: 'unpaid' | 'cancelled') {
    try {
      await api.patch<Invoice>(`/invoices/${id}/status`, { status });
      setConfirmCancel(false);
      await load();
      onChanged();
    } catch (err) {
      window.alert(err instanceof Error ? err.message : 'Could not update invoice status.');
    }
  }

  async function recordPayment(event: FormEvent) {
    event.preventDefault();
    if (!invoice) return;
    setPaySaving(true);
    try {
      const payload: PaymentInput = {
        invoice_id: invoice.id,
        amount: Number(payForm.amount),
        method: payForm.method,
        reference: payForm.reference.trim() || undefined,
        payer_vpa: payForm.payer_vpa.trim() || undefined,
        payment_date: payForm.payment_date || undefined,
        notes: payForm.notes.trim() || undefined,
        confirm: payForm.confirm,
      };
      await api.post<Payment>('/payments', payload);
      setPayOpen(false);
      setPayForm({ ...payForm, amount: '', reference: '', payer_vpa: '', notes: '' });
      await load();
      onChanged();
    } catch (err) {
      window.alert(err instanceof Error ? err.message : 'Could not record the payment.');
    } finally {
      setPaySaving(false);
    }
  }

  if (loading) return <Drawer open onClose={onClose} title="Invoice"><Loader label="Loading invoice…" full /></Drawer>;
  if (!invoice) return <Drawer open onClose={onClose} title="Invoice"><EmptyState title="Invoice not found" /></Drawer>;

  const shareUrl = `${window.location.origin}/pay/${invoice.public_token}`;
  const editable = invoice.status === 'draft' || invoice.status === 'unpaid';

  return (
    <>
      <Drawer
        open
        onClose={onClose}
        title={invoice.invoice_number}
        subtitle={`Issued ${formatDate(invoice.issue_date)} · ${invoice.customer_name ?? 'Customer'}`}
        width={620}
        footer={
          <div className="drawer-actions">
            <Button variant="secondary" size="sm" icon={<Download size={15} />}
              onClick={() => void downloadFile(`/invoices/${invoice.id}/pdf`, `${invoice.invoice_number}.pdf`)}>
              PDF
            </Button>
            <Button variant="secondary" size="sm" icon={<QrCode size={15} />} onClick={() => void generateQr()} loading={qrLoading}>
              QR code
            </Button>
            <Button variant="secondary" size="sm" icon={<Link2 size={15} />}
              onClick={() => void copyText(shareUrl).then(() => window.alert('Payment link copied to clipboard:\n' + shareUrl))}>
              Copy link
            </Button>
            <a href={shareUrl} target="_blank" rel="noreferrer" className="btn btn--secondary btn--sm">
              <ExternalLink size={15} /> Open link
            </a>
          </div>
        }
      >
        <div className="detail-head">
          <div>
            <div className="pricing-mode-badges">
              <StatusBadge status={invoice.status} />
              <Badge tone={invoice.pricing_mode === 'wholesale' ? 'info' : 'neutral'}>
                {invoice.pricing_mode === 'wholesale' ? 'Wholesale' : 'Retail'}
              </Badge>
            </div>
            {invoice.due_date && <p className="muted">Due {formatDate(invoice.due_date)}</p>}
          </div>
          <div className="detail-head__amount">
            <span className="muted">Total</span>
            <strong>{money(invoice.total_amount, currency)}</strong>
            <span className={invoice.balance_amount > 0 ? 'text-warning' : 'text-success'}>
              Balance {money(invoice.balance_amount, currency)}
            </span>
          </div>
        </div>

        {editable && (
          <div className="inline-actions">
            <Button size="sm" variant="secondary" icon={<Pencil size={14} />} onClick={() => onEdit(invoice)}>
              Edit invoice
            </Button>
            {invoice.status === 'draft' && (
              <Button size="sm" variant="secondary" icon={<CheckCircle2 size={14} />} onClick={() => void setStatus('unpaid')}>
                Finalize
              </Button>
            )}
            <Button size="sm" variant="ghost" icon={<XCircle size={14} />} onClick={() => setConfirmCancel(true)}>
              Cancel invoice
            </Button>
          </div>
        )}

        {qr && (
          <Card className="qr-card">
            <div className="qr-card__image"><img src={qr.qr_data_url} alt="UPI payment QR code" /></div>
            <div className="qr-card__info">
              <strong>{qr.payee_name}</strong>
              <p className="mono">{qr.upi_id}</p>
              <p className="strong">{money(qr.amount, currency)}</p>
              <a href={qr.upi_uri} className="text-link" target="_blank" rel="noreferrer">
                Open in UPI app <ExternalLink size={13} />
              </a>
            </div>
          </Card>
        )}

        <div className="detail-section">
          <h4>Billed to</h4>
          <p><strong>{invoice.customer_name ?? '—'}</strong></p>
          {invoice.customer_phone && <p className="muted">{invoice.customer_phone}</p>}
          {invoice.customer_email && <p className="muted">{invoice.customer_email}</p>}
        </div>

        <div className="detail-section">
          <h4>Items</h4>
          <div className="table-scroll">
            <table className="data-table data-table--compact">
              <thead>
                <tr>
                  <th>Description</th>
                  <th className="text-right">Qty</th>
                  <th className="text-right">Rate</th>
                  <th className="text-right">GST</th>
                  <th className="text-right">Amount</th>
                </tr>
              </thead>
              <tbody>
                {invoice.items.map((item) => (
                  <tr key={item.id}>
                    <td>{item.description}</td>
                    <td className="text-right">{item.quantity}</td>
                    <td className="text-right">{money(item.unit_price, currency)}</td>
                    <td className="text-right">{item.gst_rate}%</td>
                    <td className="text-right strong">{money(item.line_total, currency)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="totals-panel totals-panel--compact">
            <div className="totals-row"><span>Subtotal</span><strong>{money(invoice.subtotal, currency)}</strong></div>
            <div className="totals-row"><span>Discount</span><strong>− {money(invoice.discount_amount, currency)}</strong></div>
            <div className="totals-row"><span>GST</span><strong>{money(invoice.tax_amount, currency)}</strong></div>
            <div className="totals-row totals-row--total"><span>Total</span><strong>{money(invoice.total_amount, currency)}</strong></div>
            <div className="totals-row"><span>Paid</span><strong className="text-success">{money(invoice.paid_amount, currency)}</strong></div>
          </div>
          {invoice.notes && <p className="detail-notes">{invoice.notes}</p>}
        </div>

        <div className="detail-section">
          <div className="section-heading-row">
            <h4>Payments ({payments.length})</h4>
            {invoice.balance_amount > 0 && invoice.status !== 'cancelled' && (
              <Button size="sm" icon={<ArrowDownToLine size={14} />}
                onClick={() => {
                  setPayForm({ ...payForm, amount: String(invoice.balance_amount) });
                  setPayOpen(true);
                }}>
                Record payment
              </Button>
            )}
          </div>
          {payments.length ? (
            <div className="mini-list">
              {payments.map((payment) => (
                <div className="mini-list__item" key={payment.id}>
                  <div>
                    <strong>{money(payment.amount, currency)}</strong>
                    <span className="muted">{payment.method} · {formatDate(payment.payment_date ?? payment.created_at)}</span>
                  </div>
                  <StatusBadge status={payment.status} />
                </div>
              ))}
            </div>
          ) : (
            <p className="muted">No payments recorded for this invoice.</p>
          )}
        </div>
      </Drawer>

      <Modal
        open={payOpen}
        onClose={() => setPayOpen(false)}
        title="Record a payment"
        subtitle={`Invoice ${invoice.invoice_number} · balance ${money(invoice.balance_amount, currency)}`}
        size="sm"
        footer={
          <>
            <Button variant="secondary" onClick={() => setPayOpen(false)}>Cancel</Button>
            <Button type="submit" form="record-payment-form" loading={paySaving}>Record payment</Button>
          </>
        }
      >
        <form id="record-payment-form" onSubmit={recordPayment} className="form-stack">
          <Field label="Amount" required>
            <Input type="number" min="0.01" step="0.01" required
              value={payForm.amount} onChange={(e) => setPayForm({ ...payForm, amount: e.target.value })} />
          </Field>
          <div className="form-grid form-grid--2">
            <Field label="Method" required>
              <Select value={payForm.method} onChange={(e) => setPayForm({ ...payForm, method: e.target.value })}>
                <option value="upi">UPI</option>
                <option value="cash">Cash</option>
                <option value="card">Card</option>
                <option value="bank_transfer">Bank transfer</option>
                <option value="netbanking">Net banking</option>
                <option value="other">Other</option>
              </Select>
            </Field>
            <Field label="Payment date">
              <Input type="date" value={payForm.payment_date}
                onChange={(e) => setPayForm({ ...payForm, payment_date: e.target.value })} />
            </Field>
          </div>
          <Field label="Reference / UTR">
            <Input value={payForm.reference} placeholder="e.g. 423178659201"
              onChange={(e) => setPayForm({ ...payForm, reference: e.target.value })} />
          </Field>
          <Field label="Payer UPI ID">
            <Input value={payForm.payer_vpa} placeholder="payer@upi"
              onChange={(e) => setPayForm({ ...payForm, payer_vpa: e.target.value })} />
          </Field>
          <Field label="Notes">
            <Textarea rows={2} value={payForm.notes}
              onChange={(e) => setPayForm({ ...payForm, notes: e.target.value })} />
          </Field>
          <Checkbox checked={payForm.confirm}
            onChange={(checked) => setPayForm({ ...payForm, confirm: checked })}
            label="Confirm immediately" hint="Staff-recorded payments are confirmed right away." />
        </form>
      </Modal>

      <ConfirmDialog
        open={confirmCancel}
        onClose={() => setConfirmCancel(false)}
        onConfirm={() => void setStatus('cancelled')}
        title="Cancel this invoice?"
        description="This marks the invoice as cancelled. This action cannot be undone."
        confirmLabel="Cancel invoice"
        danger
      />
    </>
  );
}

/* ------------------------------------------------------------------ */
/* Billing page                                                         */
/* ------------------------------------------------------------------ */

export function Billing() {
  const { business } = useAuth();
  const currency = business?.currency ?? 'INR';
  const [searchParams] = useSearchParams();
  const initialQuery = searchParams.get('q') ?? '';
  const initialCustomer = searchParams.get('customer_id') ?? '';
  const [queryInput, setQueryInput] = useState(initialQuery);
  const [query, setQuery] = useState(initialQuery);
  const [status, setStatus] = useState('');
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [page, setPage] = useState(1);
  const [invoices, setInvoices] = useState<InvoiceListItem[]>([]);
  const [meta, setMeta] = useState({ total: 0, pages: 1, page_size: PAGE_SIZE });
  const [loading, setLoading] = useState(true);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Invoice | null>(null);
  const [detailId, setDetailId] = useState<string | null>(null);

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
      const result = await api.get<Paginated<InvoiceListItem>>('/invoices', {
        query: query || undefined,
        status: status || undefined,
        from_date: fromDate || undefined,
        to_date: toDate || undefined,
        page,
        page_size: PAGE_SIZE,
      });
      setInvoices(result.items);
      setMeta({ total: result.total, pages: result.pages, page_size: result.page_size });
    } finally {
      setLoading(false);
    }
  }, [query, status, fromDate, toDate, page]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    (async () => {
      try {
        const [customerResult, productResult] = await Promise.all([
          api.get<Paginated<Customer>>('/customers', { page_size: 200 }),
          api.get<Paginated<Product>>('/products', { page_size: 200 }),
        ]);
        setCustomers(customerResult.items);
        setProducts(productResult.items.filter((product) => product.is_active));
      } catch {
        // dropdowns will simply be empty
      }
    })();
  }, []);

  useEffect(() => {
    if (initialCustomer) {
      setFormOpen(true);
    }
  }, [initialCustomer]);

  function openCreate() {
    setEditing(null);
    setFormOpen(true);
  }

  function clearFilters() {
    setQueryInput('');
    setQuery('');
    setStatus('');
    setFromDate('');
    setToDate('');
    setPage(1);
  }

  const hasFilters = Boolean(query || status || fromDate || toDate);

  return (
    <>
      <PageHeader
        title="Invoices"
        subtitle="Create, track and manage every invoice in one place"
        actions={
          <Button icon={<Plus size={16} />} onClick={openCreate}>New invoice</Button>
        }
      />

      <Card className="filter-bar">
        <div className="filter-bar__search">
          <Search size={17} />
          <Input
            value={queryInput}
            onChange={(e) => setQueryInput(e.target.value)}
            placeholder="Search by invoice number or customer…"
            aria-label="Search invoices"
          />
        </div>
        <Select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} aria-label="Filter by status">
          <option value="">All statuses</option>
          <option value="draft">Draft</option>
          <option value="unpaid">Unpaid</option>
          <option value="partially_paid">Partially paid</option>
          <option value="paid">Paid</option>
          <option value="cancelled">Cancelled</option>
        </Select>
        <div className="date-range">
          <Input type="date" value={fromDate} max={toDate || undefined}
            onChange={(e) => { setFromDate(e.target.value); setPage(1); }} aria-label="From date" />
          <span>to</span>
          <Input type="date" value={toDate} min={fromDate || undefined}
            onChange={(e) => { setToDate(e.target.value); setPage(1); }} aria-label="To date" />
        </div>
        {hasFilters && (
          <Button variant="ghost" size="sm" icon={<FilterX size={15} />} onClick={clearFilters}>
            Clear
          </Button>
        )}
      </Card>

      <Card padded={false}>
        {loading ? (
          <Loader label="Loading invoices…" full />
        ) : invoices.length ? (
          <>
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Invoice #</th>
                    <th>Customer</th>
                    <th>Issue date</th>
                    <th>Due date</th>
                    <th className="text-right">Amount</th>
                    <th className="text-right">Balance</th>
                    <th>Status</th>
                    <th aria-label="Actions" />
                  </tr>
                </thead>
                <tbody>
                  {invoices.map((invoice) => (
                    <tr key={invoice.id} className="clickable-row" onClick={() => setDetailId(invoice.id)}>
                      <td>
                        <div className="cell-with-icon">
                          <span className="cell-icon"><FileText size={16} /></span>
                          <strong className="mono">{invoice.invoice_number}</strong>
                        </div>
                        <div className="invoice-mode">
                          <Badge tone={invoice.pricing_mode === 'wholesale' ? 'info' : 'neutral'}>
                            {invoice.pricing_mode === 'wholesale' ? 'Wholesale' : 'Retail'}
                          </Badge>
                        </div>
                      </td>
                      <td>{invoice.customer_name ?? '—'}</td>
                      <td>{formatDate(invoice.issue_date)}</td>
                      <td>{formatDate(invoice.due_date)}</td>
                      <td className="text-right strong">{money(invoice.total_amount, currency)}</td>
                      <td className={`text-right ${invoice.balance_amount > 0 ? 'text-warning' : 'text-success'}`}>
                        {money(invoice.balance_amount, currency)}
                      </td>
                      <td><StatusBadge status={invoice.status} /></td>
                      <td>
                        <button
                          type="button"
                          className="icon-btn"
                          aria-label="View invoice"
                          onClick={(event) => { event.stopPropagation(); setDetailId(invoice.id); }}
                        >
                          <ReceiptText size={16} />
                        </button>
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
            title={hasFilters ? 'No invoices match your filters' : 'No invoices yet'}
            description={hasFilters ? 'Try changing the search or filters.' : 'Create your first invoice to begin billing.'}
            icon={<ReceiptText size={24} />}
            action={hasFilters ? <Button variant="secondary" onClick={clearFilters}>Clear filters</Button>
              : <Button icon={<Plus size={15} />} onClick={openCreate}>New invoice</Button>}
          />
        )}
      </Card>

      <InvoiceForm
        open={formOpen}
        onClose={() => { setFormOpen(false); setEditing(null); }}
        customers={customers}
        products={products}
        initial={editing}
        initialCustomerId={initialCustomer}
        currency={currency}
        business={business}
        onSaved={() => {
          setFormOpen(false);
          setEditing(null);
          void load();
        }}
      />

      {detailId && (
        <InvoiceDetail
          id={detailId}
          onClose={() => setDetailId(null)}
          onEdit={(invoice) => {
            setDetailId(null);
            setEditing(invoice);
            setFormOpen(true);
          }}
          onChanged={() => void load()}
          currency={currency}
        />
      )}
    </>
  );
}
