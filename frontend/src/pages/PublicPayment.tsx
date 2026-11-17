import { useEffect, useState, type FormEvent } from 'react';
import { useParams } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  CreditCard,
  ExternalLink,
  FileText,
  LockKeyhole,
  QrCode,
  ReceiptText,
  ShieldCheck,
} from 'lucide-react';
import { publicApi } from '../api/client';
import {
  Badge,
  Button,
  Card,
  EmptyState,
  Field,
  Input,
  Loader,
  Select,
  StatusBadge,
  Textarea,
  formatDate,
  money,
  titleCase,
} from '../components/UI';
import type {
  Payment,
  PublicInvoice,
  PublicPaymentInput,
  QrResponse,
} from '../types';

const VERIFICATION_NOTICE =
  'Your payment declaration has been submitted and will be verified by the business. Do not consider it paid until confirmed.';

export function PublicPayment() {
  const { token = '' } = useParams();
  const [invoice, setInvoice] = useState<PublicInvoice | null>(null);
  const [qr, setQr] = useState<QrResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [amount, setAmount] = useState('');
  const [method, setMethod] = useState('upi');
  const [reference, setReference] = useState('');
  const [payerVpa, setPayerVpa] = useState('');
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState<Payment | null>(null);

  useEffect(() => {
    let active = true;
    (async () => {
      setLoading(true);
      setError('');
      try {
        const [invoiceResult, qrResult] = await Promise.all([
          publicApi.get<PublicInvoice>(`/public/invoices/${token}`),
          publicApi.get<QrResponse>(`/public/invoices/${token}/qr`).catch(() => null),
        ]);
        if (!active) return;
        setInvoice(invoiceResult);
        setQr(qrResult);
        setAmount(String(invoiceResult.balance_amount || invoiceResult.total_amount));
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : 'This payment link is not available.');
        }
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [token]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError('');
    try {
      const payload: PublicPaymentInput = {
        amount: Number(amount),
        method,
        reference: reference.trim(),
        ...(payerVpa.trim() ? { payer_vpa: payerVpa.trim() } : {}),
        ...(notes.trim() ? { notes: notes.trim() } : {}),
      };
      const result = await publicApi.post<Payment>(`/public/invoices/${token}/payments`, payload);
      setSubmitted(result);
      setReference('');
      setPayerVpa('');
      setNotes('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not submit your declaration.');
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <div className="public-page">
        <Card className="public-card public-card--loading">
          <Loader label="Loading your invoice…" full />
        </Card>
      </div>
    );
  }

  if (error && !invoice) {
    return (
      <div className="public-page">
        <div className="public-header">
          <span className="brand-mark"><ReceiptText size={20} /></span>
          <span className="brand-name">BillFlow</span>
        </div>
        <Card className="public-card">
          <EmptyState
            title="Payment link unavailable"
            description={error || 'This invoice link is invalid or has expired.'}
            icon={<AlertTriangle size={24} />}
          />
        </Card>
      </div>
    );
  }

  if (!invoice) return null;
  const currency = invoice.currency || 'INR';

  return (
    <div className="public-page">
      <div className="public-header">
        <div className="public-header__brand">
          <span className="brand-mark"><ReceiptText size={20} /></span>
          <span className="brand-name">BillFlow</span>
        </div>
        <span className="public-header__secure"><LockKeyhole size={14} /> Secure payment page</span>
      </div>

      <div className="public-hero">
        <span className="public-hero__eyebrow">PAYMENT REQUEST</span>
        <h1>{invoice.business_name}</h1>
        <p>Invoice {invoice.invoice_number} · {formatDate(invoice.issue_date)}</p>
        <div className="public-hero__amount">
          <span>Amount due</span>
          <strong>{money(invoice.balance_amount || invoice.total_amount, currency)}</strong>
          <StatusBadge status={invoice.status} />
        </div>
      </div>

      <div className="public-grid">
        <Card className="public-card">
          <div className="public-card__head">
            <span className="public-card__icon"><FileText size={18} /></span>
            <div>
              <h2>Invoice details</h2>
              <p>{invoice.customer_name ? `Billed to ${invoice.customer_name}` : 'Invoice summary'}</p>
            </div>
          </div>
          <div className="public-meta-grid">
            <div><span>Invoice number</span><strong className="mono">{invoice.invoice_number}</strong></div>
            <div><span>Issue date</span><strong>{formatDate(invoice.issue_date)}</strong></div>
            <div><span>Due date</span><strong>{formatDate(invoice.due_date)}</strong></div>
            <div><span>Status</span><StatusBadge status={invoice.status} /></div>
          </div>
          <div className="table-scroll">
            <table className="data-table data-table--compact">
              <thead>
                <tr><th>Description</th><th className="text-right">Qty</th><th className="text-right">Rate</th><th className="text-right">Amount</th></tr>
              </thead>
              <tbody>
                {invoice.items.map((item, index) => (
                  <tr key={index}>
                    <td>{item.description}</td>
                    <td className="text-right">{item.quantity}</td>
                    <td className="text-right">{money(item.unit_price, currency)}</td>
                    <td className="text-right strong">{money(item.line_total, currency)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="totals-panel totals-panel--compact">
            <div className="totals-row"><span>Invoice total</span><strong>{money(invoice.total_amount, currency)}</strong></div>
            <div className="totals-row"><span>Already paid</span><strong className="text-success">{money(invoice.paid_amount, currency)}</strong></div>
            <div className="totals-row totals-row--total"><span>Balance due</span><strong>{money(invoice.balance_amount, currency)}</strong></div>
          </div>
        </Card>

        <div className="public-right">
          {qr ? (
            <Card className="public-card public-qr-card">
              <div className="public-card__head">
                <span className="public-card__icon public-card__icon--blue"><QrCode size={18} /></span>
                <div><h2>Pay with UPI</h2><p>Scan the code in any UPI app</p></div>
              </div>
              <div className="public-qr">
                <img src={qr.qr_data_url} alt="UPI payment QR code" />
              </div>
              <div className="public-upi-details">
                <div><span>Payee</span><strong>{qr.payee_name}</strong></div>
                <div><span>UPI ID</span><strong className="mono">{qr.upi_id}</strong></div>
                <div><span>Amount</span><strong>{money(qr.amount, qr.currency || currency)}</strong></div>
              </div>
              <a href={qr.upi_uri} className="btn btn--primary btn--lg btn--full" target="_blank" rel="noreferrer">
                <ArrowUpRight size={17} /> Open in UPI app
              </a>
              <p className="public-qr__hint"><ExternalLink size={12} /> Works with GPay, PhonePe, Paytm and more</p>
            </Card>
          ) : (
            <Card className="public-card">
              <EmptyState title="UPI not configured" description="Please contact the business for payment instructions." />
            </Card>
          )}

          <Card className="public-card">
            <div className="public-card__head">
              <span className="public-card__icon public-card__icon--amber"><CreditCard size={18} /></span>
              <div><h2>Declare a payment</h2><p>Already paid? Let the business know.</p></div>
            </div>

            {submitted ? (
              <div className="public-success">
                <CheckCircle2 size={32} />
                <h3>Declaration received</h3>
                <p>{VERIFICATION_NOTICE}</p>
                <div className="public-success__ref">
                  <span>Reference</span>
                  <strong className="mono">{submitted.reference || '—'}</strong>
                  <Badge tone="warning" dot>Submitted</Badge>
                </div>
                <Button variant="secondary" size="sm" onClick={() => setSubmitted(null)}>
                  Submit another declaration
                </Button>
              </div>
            ) : (
              <form onSubmit={submit} className="form-stack">
                {error && <div className="alert alert--error">{error}</div>}
                <div className="alert alert--warning public-warning">
                  <AlertTriangle size={17} />
                  <span>{VERIFICATION_NOTICE}</span>
                </div>
                <div className="form-grid form-grid--2">
                  <Field label="Amount paid" required>
                    <Input type="number" min="1" step="0.01" required value={amount}
                      onChange={(e) => setAmount(e.target.value)} />
                  </Field>
                  <Field label="Payment method" required>
                    <Select value={method} onChange={(e) => setMethod(e.target.value)}>
                      <option value="upi">UPI</option>
                      <option value="cash">Cash</option>
                      <option value="card">Card</option>
                      <option value="bank_transfer">Bank transfer</option>
                      <option value="netbanking">Net banking</option>
                      <option value="other">Other</option>
                    </Select>
                  </Field>
                </div>
                <Field label="UTR / Reference number" required hint="At least 4 characters — e.g. your UPI transaction ID.">
                  <Input required minLength={4} value={reference} placeholder="e.g. 423178659201"
                    onChange={(e) => setReference(e.target.value)} />
                </Field>
                <Field label="Your UPI ID (optional)">
                  <Input value={payerVpa} placeholder="you@upi"
                    onChange={(e) => setPayerVpa(e.target.value)} />
                </Field>
                <Field label="Notes (optional)">
                  <Textarea rows={2} value={notes} placeholder="Any additional details…"
                    onChange={(e) => setNotes(e.target.value)} />
                </Field>
                <Button type="submit" size="lg" full loading={submitting}>
                  Submit payment declaration
                </Button>
              </form>
            )}
          </Card>

          {invoice.payments.length > 0 && (
            <Card className="public-card">
              <div className="public-card__head">
                <span className="public-card__icon"><ShieldCheck size={18} /></span>
                <div><h2>Payment history</h2><p>Declarations and confirmations</p></div>
              </div>
              <div className="mini-list">
                {invoice.payments.map((payment) => (
                  <div className="mini-list__item" key={payment.id}>
                    <div>
                      <strong>{money(payment.amount, currency)}</strong>
                      <span className="muted">
                        {titleCase(payment.method)} · {payment.reference ? `Ref ${payment.reference}` : 'No reference'} ·{' '}
                        {formatDate(payment.created_at, true)}
                      </span>
                    </div>
                    <StatusBadge status={payment.status} />
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
      </div>

      <div className="public-footer">
        Powered by <strong>BillFlow</strong> · Payments are verified by {invoice.business_name}
      </div>
    </div>
  );
}
