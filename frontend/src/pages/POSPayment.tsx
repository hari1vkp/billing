import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  ArrowUpRight,
  Banknote,
  CheckCircle2,
  Copy,
  CreditCard,
  Download,
  ExternalLink,
  Link2,
  QrCode,
  ShieldAlert,
  Smartphone,
} from 'lucide-react';
import { api, downloadFile, publicApi } from '../api/client';
import { useAuth } from '../context/AuthContext';
import {
  Badge,
  Button,
  Card,
  EmptyState,
  Field,
  Input,
  Loader,
  Select,
  money,
  titleCase,
  useToast,
} from '../components/UI';
import type { Invoice, Paginated, Payment, QrResponse } from '../types';

const PAYMENT_NOTICE =
  'Scanning the QR does not confirm payment. Payment is confirmed only after verification or staff confirmation.';

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

function normalizePayments(value: Payment[] | Paginated<Payment> | null): Payment[] {
  if (!value) return [];
  return Array.isArray(value) ? value : value.items;
}

interface SuccessInfo {
  amount: number;
  method: string;
  reference?: string | null;
}

export function POSPayment() {
  const { invoiceId = '' } = useParams();
  const { business } = useAuth();
  const currency = business?.currency ?? 'INR';
  const toast = useToast();

  const [invoice, setInvoice] = useState<Invoice | null>(null);
  const [qr, setQr] = useState<QrResponse | null>(null);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<'upi' | 'other'>('upi');
  const [amount, setAmount] = useState('');
  const [method, setMethod] = useState('cash');
  const [reference, setReference] = useState('');
  const [payerVpa, setPayerVpa] = useState('');
  const [declared, setDeclared] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState<SuccessInfo | null>(null);

  const loadPayments = useCallback(async (): Promise<Payment[]> => {
    const result = await api.get<Payment[] | Paginated<Payment>>(
      `/invoices/${invoiceId}/payments`,
    );
    const list = normalizePayments(result);
    setPayments(list);
    return list;
  }, [invoiceId]);

  useEffect(() => {
    let active = true;
    (async () => {
      setLoading(true);
      try {
        const [invoiceResult, qrResult, paymentList] = await Promise.all([
          api.get<Invoice>(`/invoices/${invoiceId}`),
          api.get<QrResponse>(`/invoices/${invoiceId}/qr`).catch(() => null),
          loadPayments().catch(() => [] as Payment[]),
        ]);
        if (!active) return;
        setInvoice(invoiceResult);
        setQr(qrResult);
        setAmount(String(invoiceResult.balance_amount || invoiceResult.total_amount));
        if (paymentList.some((payment) => payment.status === 'confirmed') && invoiceResult.status === 'paid') {
          const confirmed = [...paymentList].reverse().find((p) => p.status === 'confirmed');
          if (confirmed) {
            setSuccess({
              amount: confirmed.amount,
              method: confirmed.method,
              reference: confirmed.reference,
            });
          }
        }
      } catch (error) {
        if (active) toast.error(error instanceof Error ? error.message : 'Could not load the invoice.');
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [invoiceId, loadPayments]);

  // After a customer declaration, poll until a staff member confirms the payment.
  useEffect(() => {
    if (!declared || success) return;
    const timer = window.setInterval(async () => {
      try {
        const list = await loadPayments();
        const confirmed = list.find((payment) => payment.status === 'confirmed');
        if (confirmed) {
          setSuccess({
            amount: confirmed.amount,
            method: confirmed.method,
            reference: confirmed.reference,
          });
        }
      } catch {
        // Keep polling — transient failures are not fatal.
      }
    }, 4000);
    return () => window.clearInterval(timer);
  }, [declared, success, loadPayments]);

  async function submitDeclaration(event: FormEvent) {
    event.preventDefault();
    if (!invoice) return;
    setSubmitting(true);
    try {
      await publicApi.post<Payment>(`/public/invoices/${invoice.public_token}/payments`, {
        amount: Number(amount),
        method: 'upi',
        reference: reference.trim(),
        ...(payerVpa.trim() ? { payer_vpa: payerVpa.trim() } : {}),
      });
      setDeclared(true);
      toast.success('Payment declaration submitted — awaiting verification');
      setReference('');
      setPayerVpa('');
      await loadPayments();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not submit the declaration.');
    } finally {
      setSubmitting(false);
    }
  }

  async function verifyDeclaration(event: FormEvent) {
    event.preventDefault();
    const ref = reference.trim();
    if (!ref) {
      toast.error('Enter the UTR / reference to verify.');
      return;
    }
    const match = [...payments]
      .reverse()
      .find(
        (payment) =>
          (payment.reference ?? '').trim().toLowerCase() === ref.toLowerCase() &&
          payment.status !== 'confirmed',
      );
    if (!match) {
      toast.error('No payment declaration found with that reference.');
      return;
    }
    setSubmitting(true);
    try {
      const confirmed = await api.post<Payment>(`/payments/${match.id}/confirm`, {
        reference: ref,
      });
      setSuccess({
        amount: confirmed.amount,
        method: confirmed.method,
        reference: confirmed.reference,
      });
      toast.success('Payment confirmed successfully.');
      await loadPayments();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not confirm the payment.');
    } finally {
      setSubmitting(false);
    }
  }

  async function recordOtherPayment(event: FormEvent) {
    event.preventDefault();
    if (!invoice) return;
    setSubmitting(true);
    try {
      const result = await api.post<Payment>('/payments', {
        invoice_id: invoice.id,
        amount: Number(amount),
        method,
        ...(reference.trim() ? { reference: reference.trim() } : {}),
        payment_date: new Date().toISOString().slice(0, 10),
        confirm: true,
      });
      setSuccess({
        amount: result.amount,
        method: result.method,
        reference: result.reference,
      });
      toast.success('Payment recorded and confirmed.');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not record the payment.');
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <div className="pos-page">
        <Card><Loader label="Loading payment details…" full /></Card>
      </div>
    );
  }

  if (!invoice) {
    return (
      <div className="pos-page">
        <Card><EmptyState title="Invoice not found" description="Return to the POS and create a new bill." /></Card>
      </div>
    );
  }

  const shareUrl = `${window.location.origin}/pay/${invoice.public_token}`;
  const transactionRef = invoice.transaction_ref ?? qr?.transaction_ref ?? '—';
  const balance = invoice.balance_amount ?? invoice.total_amount;

  if (success) {
    return (
      <div className="pos-page pos-payment-page">
        <Card className="success-card">
          <div className="success-card__icon"><CheckCircle2 size={56} strokeWidth={1.8} /></div>
          <h1>Payment received</h1>
          <p>Invoice {invoice.invoice_number} has been marked as paid.</p>
          <div className="success-card__amount">{money(success.amount, currency)}</div>
          <div className="success-card__meta">
            <span><Badge tone="success" dot>Confirmed</Badge></span>
            <span>{titleCase(success.method)}</span>
            {success.reference && <span className="mono">Ref: {success.reference}</span>}
          </div>
          <div className="success-card__actions">
            <Button
              variant="secondary"
              icon={<Download size={16} />}
              onClick={() =>
                void downloadFile(`/invoices/${invoice.id}/pdf`, `${invoice.invoice_number}.pdf`)
              }
            >
              Download PDF
            </Button>
            <Button icon={<Link2 size={15} />} onClick={() => void copyText(shareUrl)}>
              Copy payment link
            </Button>
            <Link to="/pos" className="btn btn--primary btn--lg">
              <CheckCircle2 size={17} /> New bill
            </Link>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="pos-page pos-payment-page">
      <div className="payment-hero">
        <div className="payment-hero__info">
          <span className="payment-hero__eyebrow">COLLECT PAYMENT</span>
          <h1>Invoice {invoice.invoice_number}</h1>
          <p>
            {invoice.customer_name ?? 'Walk-in Customer'} · Transaction ref{' '}
            <strong className="mono">{transactionRef}</strong>
          </p>
        </div>
        <div className="payment-hero__amounts">
          <div><span>Total payable</span><strong>{money(invoice.total_amount, currency)}</strong></div>
          <div className="payment-hero__balance">
            <span>Balance due</span><strong>{money(balance, currency)}</strong>
          </div>
        </div>
      </div>

      <div className="payment-grid">
        <Card className="payment-method-card" padded={false}>
          <div className="payment-tabs" role="tablist" aria-label="Payment method">
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'upi'}
              className={tab === 'upi' ? 'payment-tab payment-tab--active' : 'payment-tab'}
              onClick={() => setTab('upi')}
            >
              <QrCode size={17} /> UPI / QR
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'other'}
              className={tab === 'other' ? 'payment-tab payment-tab--active' : 'payment-tab'}
              onClick={() => setTab('other')}
            >
              <Banknote size={17} /> Cash / Card / Other
            </button>
          </div>

          {tab === 'upi' ? (
            <div className="payment-tab-body">
              <div className="payment-notice">
                <ShieldAlert size={18} />
                <span>{PAYMENT_NOTICE}</span>
              </div>

              <div className="qr-card payment-qr-card">
                {qr ? (
                  <>
                    <div className="qr-card__image"><img src={qr.qr_data_url} alt="UPI payment QR code" /></div>
                    <div className="qr-card__info">
                      <span className="muted small">Payee</span>
                      <strong>{qr.payee_name}</strong>
                      <span className="mono">{qr.upi_id}</span>
                      <strong className="qr-card__amount">{money(qr.amount, currency)}</strong>
                      <div className="qr-card__links">
                        <a href={qr.upi_uri} target="_blank" rel="noreferrer" className="text-link">
                          Open in UPI app <ExternalLink size={13} />
                        </a>
                        <button type="button" className="text-link" onClick={() => void copyText(qr.upi_id)}>
                          <Copy size={13} /> Copy UPI ID
                        </button>
                        <button type="button" className="text-link" onClick={() => void copyText(shareUrl)}>
                          <Copy size={13} /> Copy link
                        </button>
                      </div>
                    </div>
                  </>
                ) : (
                  <EmptyState title="UPI is not configured" description="Use another payment method below." />
                )}
              </div>

              <div className="payment-forms">
                <form onSubmit={submitDeclaration} className="payment-form">
                  <h3><Smartphone size={16} /> Customer paid — submit UTR</h3>
                  {declared ? (
                    <div className="declaration-pending">
                      <CheckCircle2 size={22} />
                      <div>
                        <strong>Payment declaration submitted — awaiting verification</strong>
                        <p>The bill will update automatically once a staff member confirms the payment.</p>
                      </div>
                    </div>
                  ) : (
                    <>
                      <div className="form-grid form-grid--2">
                        <Field label="Amount" required>
                          <Input
                            type="number"
                            min="1"
                            step="0.01"
                            required
                            value={amount}
                            onChange={(event) => setAmount(event.target.value)}
                          />
                        </Field>
                        <Field label="Payer UPI ID (optional)">
                          <Input
                            value={payerVpa}
                            placeholder="payer@upi"
                            onChange={(event) => setPayerVpa(event.target.value)}
                          />
                        </Field>
                      </div>
                      <Field label="UTR / Reference" required>
                        <Input
                          required
                          value={reference}
                          placeholder="Enter the UPI transaction reference"
                          onChange={(event) => setReference(event.target.value)}
                        />
                      </Field>
                      <Button type="submit" full loading={submitting} variant="secondary">
                        Submit payment declaration
                      </Button>
                    </>
                  )}
                </form>

                <form onSubmit={verifyDeclaration} className="payment-form payment-form--verify">
                  <h3><CheckCircle2 size={16} /> Staff verification</h3>
                  <p className="muted small">
                    Confirm a customer-submitted declaration after checking the UTR against your account.
                  </p>
                  <Field label="UTR / Reference" required>
                    <Input
                      required
                      value={reference}
                      placeholder="Reference entered by the customer"
                      onChange={(event) => setReference(event.target.value)}
                    />
                  </Field>
                  <Button type="submit" full loading={submitting} icon={<CheckCircle2 size={16} />}>
                    Verify & confirm payment
                  </Button>
                  {payments.length > 0 && (
                    <div className="payment-mini-list">
                      <span className="muted small">Declarations for this bill</span>
                      {payments.slice(-4).reverse().map((payment) => (
                        <div key={payment.id}>
                          <span className="mono">{payment.reference || 'No reference'}</span>
                          <span>{money(payment.amount, currency)}</span>
                          <Badge tone={payment.status === 'confirmed' ? 'success' : 'warning'}>
                            {titleCase(payment.status)}
                          </Badge>
                        </div>
                      ))}
                    </div>
                  )}
                </form>
              </div>
            </div>
          ) : (
            <form onSubmit={recordOtherPayment} className="payment-tab-body payment-other-form">
              <div className="payment-notice payment-notice--info">
                <CreditCard size={18} />
                <span>Staff-recorded payments are confirmed immediately. Verify cash in hand or the card terminal before continuing.</span>
              </div>
              <Field label="Amount" required>
                <Input
                  type="number"
                  min="1"
                  step="0.01"
                  required
                  value={amount}
                  onChange={(event) => setAmount(event.target.value)}
                />
              </Field>
              <Field label="Payment method" required>
                <Select value={method} onChange={(event) => setMethod(event.target.value)}>
                  <option value="cash">Cash</option>
                  <option value="card">Card</option>
                  <option value="bank_transfer">Bank transfer</option>
                  <option value="netbanking">Net banking</option>
                  <option value="other">Other</option>
                </Select>
              </Field>
              <Field label="Reference (optional)">
                <Input
                  value={reference}
                  placeholder="Terminal / transaction reference"
                  onChange={(event) => setReference(event.target.value)}
                />
              </Field>
              <Button type="submit" size="lg" full loading={submitting} icon={<CheckCircle2 size={17} />}>
                Confirm payment · {money(Number(amount) || 0, currency)}
              </Button>
            </form>
          )}
        </Card>

        <aside className="payment-side">
          <Card>
            <h3>Bill summary</h3>
            <div className="payment-summary">
              <div><span>Invoice</span><strong className="mono">{invoice.invoice_number}</strong></div>
              <div><span>Transaction ref</span><strong className="mono">{transactionRef}</strong></div>
              <div><span>Customer</span><strong>{invoice.customer_name ?? 'Walk-in Customer'}</strong></div>
              <div><span>Total</span><strong>{money(invoice.total_amount, currency)}</strong></div>
              <div><span>Balance</span><strong className="text-warning">{money(balance, currency)}</strong></div>
            </div>
            <Button
              variant="secondary"
              full
              icon={<Download size={15} />}
              onClick={() => void downloadFile(`/invoices/${invoice.id}/pdf`, `${invoice.invoice_number}.pdf`)}
            >
              Download PDF
            </Button>
          </Card>
          <Card>
            <h3>Share payment link</h3>
            <p className="muted small">Let the customer open the invoice and declare their payment.</p>
            <a href={shareUrl} target="_blank" rel="noreferrer" className="text-link">
              <ArrowUpRight size={14} /> Open payment link
            </a>
            <Button variant="ghost" size="sm" icon={<Copy size={14} />}
              onClick={() => void copyText(shareUrl)}>
              Copy link
            </Button>
          </Card>
          <Link to="/pos" className="btn btn--ghost btn--full">
            ← Back to POS
          </Link>
        </aside>
      </div>
    </div>
  );
}
