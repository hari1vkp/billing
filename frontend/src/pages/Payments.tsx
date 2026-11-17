import { useCallback, useEffect, useState, type FormEvent } from 'react';
import {
  AlertCircle,
  BadgeCheck,
  Banknote,
  CheckCircle2,
  Clock3,
  CreditCard,
  FilterX,
  RotateCcw,
  Search,
  XCircle,
} from 'lucide-react';
import { api } from '../api/client';
import { useAuth } from '../context/AuthContext';
import {
  Badge,
  Button,
  Card,
  CardHeader,
  ConfirmDialog,
  EmptyState,
  Field,
  Input,
  Loader,
  Modal,
  PageHeader,
  Pagination,
  Select,
  StatCard,
  StatusBadge,
  formatDate,
  money,
  titleCase,
} from '../components/UI';
import type { AnalyticsResponse, MessageResponse, Paginated, Payment } from '../types';

const PAGE_SIZE = 15;

export function Payments() {
  const { business } = useAuth();
  const currency = business?.currency ?? 'INR';
  const [queryInput, setQueryInput] = useState('');
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('');
  const [method, setMethod] = useState('');
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [page, setPage] = useState(1);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [pending, setPending] = useState<Payment[]>([]);
  const [analytics, setAnalytics] = useState<AnalyticsResponse | null>(null);
  const [meta, setMeta] = useState({ total: 0, pages: 1, page_size: PAGE_SIZE });
  const [loading, setLoading] = useState(true);

  const [confirmTarget, setConfirmTarget] = useState<Payment | null>(null);
  const [confirmRef, setConfirmRef] = useState('');
  const [confirmNotes, setConfirmNotes] = useState('');
  const [confirming, setConfirming] = useState(false);
  const [actionTarget, setActionTarget] = useState<{ payment: Payment; action: 'fail' | 'refund' } | null>(null);
  const [acting, setActing] = useState(false);

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
      const [result, pendingResult, analyticsResult] = await Promise.all([
        api.get<Paginated<Payment>>('/payments', {
          query: query || undefined,
          status: status || undefined,
          method: method || undefined,
          from_date: fromDate || undefined,
          to_date: toDate || undefined,
          page,
          page_size: PAGE_SIZE,
        }),
        api.get<Paginated<Payment>>('/payments', {
          status: 'submitted', page_size: 100,
        }).catch(() => null),
        api.get<AnalyticsResponse>('/analytics/dashboard').catch(() => null),
      ]);
      setPayments(result.items);
      setMeta({ total: result.total, pages: result.pages, page_size: result.page_size });
      setPending(pendingResult?.items ?? []);
      setAnalytics(analyticsResult);
    } finally {
      setLoading(false);
    }
  }, [query, status, method, fromDate, toDate, page]);

  useEffect(() => {
    void load();
  }, [load]);

  async function confirmPayment(event: FormEvent) {
    event.preventDefault();
    if (!confirmTarget || !confirmRef.trim()) return;
    setConfirming(true);
    try {
      await api.post<Payment>(`/payments/${confirmTarget.id}/confirm`, {
        reference: confirmRef.trim(),
        notes: confirmNotes.trim() || undefined,
      });
      setConfirmTarget(null);
      setConfirmRef('');
      setConfirmNotes('');
      void load();
    } finally {
      setConfirming(false);
    }
  }

  async function runAction() {
    if (!actionTarget) return;
    setActing(true);
    try {
      await api.post<Payment | MessageResponse>(`/payments/${actionTarget.payment.id}/${actionTarget.action}`);
      setActionTarget(null);
      void load();
    } finally {
      setActing(false);
    }
  }

  function clearFilters() {
    setQueryInput('');
    setQuery('');
    setStatus('');
    setMethod('');
    setFromDate('');
    setToDate('');
    setPage(1);
  }

  const hasFilters = Boolean(query || status || method || fromDate || toDate);
  const pendingAmount = pending.reduce((sum, payment) => sum + payment.amount, 0);

  return (
    <>
      <PageHeader title="Payments" subtitle="Track collections and verify customer declarations"
        actions={<span className="period-chip"><Clock3 size={15} /> {pending.length} awaiting confirmation</span>} />

      <div className="stat-grid stat-grid--4">
        <StatCard label="Confirmed today" value={money(analytics?.today_collections ?? 0, currency)}
          icon={<Banknote size={19} />} tone="success"
          hint={`${analytics?.today_transactions ?? 0} transactions today`} />
        <StatCard label="Awaiting confirmation" value={pending.length}
          icon={<Clock3 size={19} />} tone="warning" hint={money(pendingAmount, currency)} />
        <StatCard label="Total collected" value={money(analytics?.summary.total_collections ?? 0, currency)}
          icon={<CheckCircle2 size={19} />} tone="info"
          hint={`${analytics?.summary.total_transactions ?? 0} confirmed transactions`} />
        <StatCard label="Outstanding" value={money(analytics?.pending_amount ?? 0, currency)}
          icon={<CreditCard size={19} />} tone="danger"
          hint={`${analytics?.pending_invoices ?? 0} invoices unpaid`} />
      </div>

      {pending.length > 0 && (
        <Card className="attention-card">
          <CardHeader
            title={<span className="attention-card__title"><AlertCircle size={18} /> Needs your attention</span>}
            subtitle="Customers have declared these payments — verify the UTR before confirming."
            action={<Badge tone="warning">{pending.length} pending</Badge>}
          />
          <div className="attention-list">
            {pending.slice(0, 5).map((payment) => (
              <div className="attention-item" key={payment.id}>
                <span className="avatar avatar--sm"><CreditCard size={15} /></span>
                <div className="attention-item__main">
                  <strong>{payment.customer_name ?? 'Customer'}</strong>
                  <span>
                    {payment.invoice_number ?? 'Invoice'} · {titleCase(payment.method)} ·{' '}
                    {payment.reference ? `Ref ${payment.reference}` : 'No reference'} ·{' '}
                    {formatDate(payment.created_at, true)}
                  </span>
                </div>
                <strong className="attention-item__amount">{money(payment.amount, currency)}</strong>
                <Button size="sm" icon={<BadgeCheck size={15} />}
                  onClick={() => {
                    setConfirmTarget(payment);
                    setConfirmRef(payment.reference ?? '');
                    setConfirmNotes('');
                  }}>
                  Confirm
                </Button>
              </div>
            ))}
          </div>
          {pending.length > 5 && <p className="muted small">+ {pending.length - 5} more pending payments below.</p>}
        </Card>
      )}

      <Card className="filter-bar">
        <div className="filter-bar__search">
          <Search size={17} />
          <Input value={queryInput} onChange={(e) => setQueryInput(e.target.value)}
            placeholder="Search by invoice, customer or reference…" aria-label="Search payments" />
        </div>
        <Select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} aria-label="Filter by status">
          <option value="">All statuses</option>
          <option value="submitted">Submitted</option>
          <option value="pending">Pending</option>
          <option value="confirmed">Confirmed</option>
          <option value="failed">Failed</option>
          <option value="refunded">Refunded</option>
        </Select>
        <Select value={method} onChange={(e) => { setMethod(e.target.value); setPage(1); }} aria-label="Filter by method">
          <option value="">All methods</option>
          <option value="upi">UPI</option>
          <option value="cash">Cash</option>
          <option value="card">Card</option>
          <option value="bank_transfer">Bank transfer</option>
          <option value="netbanking">Net banking</option>
          <option value="other">Other</option>
        </Select>
        <div className="date-range">
          <Input type="date" value={fromDate} max={toDate || undefined}
            onChange={(e) => { setFromDate(e.target.value); setPage(1); }} aria-label="From date" />
          <span>to</span>
          <Input type="date" value={toDate} min={fromDate || undefined}
            onChange={(e) => { setToDate(e.target.value); setPage(1); }} aria-label="To date" />
        </div>
        {hasFilters && <Button variant="ghost" size="sm" icon={<FilterX size={15} />} onClick={clearFilters}>Clear</Button>}
      </Card>

      <Card padded={false}>
        {loading ? (
          <Loader label="Loading payments…" full />
        ) : payments.length ? (
          <>
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Invoice</th>
                    <th>Customer</th>
                    <th className="text-right">Amount</th>
                    <th>Method</th>
                    <th>Reference</th>
                    <th>Date</th>
                    <th>Status</th>
                    <th className="text-right">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {payments.map((payment) => (
                    <tr key={payment.id}>
                      <td><strong className="mono">{payment.invoice_number ?? '—'}</strong></td>
                      <td>{payment.customer_name ?? '—'}</td>
                      <td className="text-right strong">{money(payment.amount, currency)}</td>
                      <td><Badge tone="info">{titleCase(payment.method)}</Badge></td>
                      <td className="small mono">{payment.reference || '—'}</td>
                      <td>{formatDate(payment.payment_date ?? payment.created_at)}</td>
                      <td><StatusBadge status={payment.status} /></td>
                      <td>
                        <div className="row-actions row-actions--end">
                          {(payment.status === 'submitted' || payment.status === 'pending') && (
                            <>
                              <button type="button" className="icon-btn icon-btn--success" title="Confirm payment"
                                onClick={() => {
                                  setConfirmTarget(payment);
                                  setConfirmRef(payment.reference ?? '');
                                  setConfirmNotes('');
                                }}>
                                <CheckCircle2 size={16} />
                              </button>
                              <button type="button" className="icon-btn icon-btn--danger" title="Mark as failed"
                                onClick={() => setActionTarget({ payment, action: 'fail' })}>
                                <XCircle size={16} />
                              </button>
                            </>
                          )}
                          {payment.status === 'confirmed' && (
                            <button type="button" className="icon-btn icon-btn--warning" title="Refund payment"
                              onClick={() => setActionTarget({ payment, action: 'refund' })}>
                              <RotateCcw size={16} />
                            </button>
                          )}
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
          <EmptyState title="No payments found" description="Try changing your filters, or record a payment from an invoice."
            icon={<CreditCard size={24} />}
            action={hasFilters ? <Button variant="secondary" onClick={clearFilters}>Clear filters</Button> : undefined} />
        )}
      </Card>

      <Modal
        open={Boolean(confirmTarget)}
        onClose={() => setConfirmTarget(null)}
        title="Confirm payment"
        subtitle={confirmTarget
          ? `${money(confirmTarget.amount, currency)} · ${confirmTarget.invoice_number ?? 'Invoice'} · ${titleCase(confirmTarget.method)}`
          : ''}
        size="sm"
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirmTarget(null)}>Cancel</Button>
            <Button type="submit" form="confirm-payment-form" loading={confirming}>Confirm payment</Button>
          </>
        }
      >
        <form id="confirm-payment-form" onSubmit={confirmPayment} className="form-stack">
          <div className="alert alert--info">
            Verify the UTR / reference against your bank statement before confirming this payment.
          </div>
          <Field label="UTR / Reference" required hint="The transaction reference number for this payment.">
            <Input required value={confirmRef} onChange={(e) => setConfirmRef(e.target.value)}
              placeholder="e.g. 423178659201" />
          </Field>
          <Field label="Notes (optional)">
            <Input value={confirmNotes} onChange={(e) => setConfirmNotes(e.target.value)}
              placeholder="Verification notes" />
          </Field>
        </form>
      </Modal>

      <ConfirmDialog
        open={Boolean(actionTarget)}
        onClose={() => setActionTarget(null)}
        onConfirm={() => void runAction()}
        title={actionTarget?.action === 'refund' ? 'Refund this payment?' : 'Mark this payment as failed?'}
        description={actionTarget?.action === 'refund'
          ? 'This records the payment as refunded. The invoice balance will be recalculated.'
          : 'This marks the declaration as failed. The customer can submit a new declaration.'}
        confirmLabel={actionTarget?.action === 'refund' ? 'Refund payment' : 'Mark failed'}
        danger={actionTarget?.action === 'fail'}
        loading={acting}
      />
    </>
  );
}
