import { useEffect, useState } from 'react';
import { Banknote, Check, QrCode } from 'lucide-react';
import { ApiError, api } from '../api/client';
import type {
  PosCheckoutResponse,
  PosQRResponse,
  Product,
} from '../types';
import { Button, Loader, money } from './UI';
import { Modal } from './UI';

interface CartLine {
  product: Product;
  quantity: number;
  discount_percent: number;
}

interface Props {
  open: boolean;
  cart: CartLine[];
  customerId: string | null;
  discountPercent: number;
  businessName: string;
  currency: string;
  onCancel: () => void;
  onSaleComplete: (result: PosCheckoutResponse) => void;
}

type Method = 'upi' | 'cash';

export function CheckoutModal({
  open,
  cart,
  customerId,
  discountPercent,
  businessName,
  currency,
  onCancel,
  onSaleComplete,
}: Props) {
  const [method, setMethod] = useState<Method>('upi');
  const [invoiceNumber, setInvoiceNumber] = useState('');
  const [qr, setQr] = useState<PosQRResponse | null>(null);
  const [qrError, setQrError] = useState('');
  const [loading, setLoading] = useState(false);
  const [completing, setCompleting] = useState(false);
  const [result, setResult] = useState<PosCheckoutResponse | null>(null);

  const quote = {
    customer_id: customerId,
    items: cart.map((line) => ({
      product_id: line.product.id,
      quantity: line.quantity,
      discount_percent: line.discount_percent,
    })),
    discount_percent: discountPercent,
    transaction_ref: invoiceNumber,
  };

  // Everything is prepared when the modal opens. No invoice, payment or stock
  // record exists yet — pressing Cancel leaves the database untouched.
  useEffect(() => {
    if (!open) return;
    let active = true;
    setResult(null);
    setMethod('upi');
    setQr(null);
    setQrError('');
    setLoading(true);

    (async () => {
      try {
        const preview = await api.get<{ invoice_number: string }>('/pos/next-number');
        if (!active) return;
        setInvoiceNumber(preview.invoice_number);
        const response = await api.post<PosQRResponse>('/pos/qr', {
          ...quote,
          transaction_ref: preview.invoice_number,
        });
        if (!active) return;
        setQr(response);
      } catch (error) {
        if (active) {
          setQrError(
            error instanceof ApiError
              ? error.message
              : 'Could not prepare the UPI QR. Cash payments are still available.',
          );
        }
      } finally {
        if (active) setLoading(false);
      }
    })();

    return () => {
      active = false;
    };
    // The cart is frozen while the modal is open.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  async function completeSale() {
    if (completing || !invoiceNumber) return;
    setCompleting(true);
    try {
      const response = await api.post<PosCheckoutResponse>('/pos/checkout', {
        ...quote,
        method,
      });
      onSaleComplete(response);
      setResult(response);
    } catch (error) {
      window.alert(
        error instanceof Error ? error.message : 'Could not complete the sale.',
      );
    } finally {
      setCompleting(false);
    }
  }

  const amount = qr?.amount ?? 0;

  return (
    <Modal
      open={open}
      onClose={completing ? () => undefined : onCancel}
      title={result ? 'Sale completed' : 'Checkout'}
      subtitle={result ? undefined : businessName}
    >
      {result ? (
        <div className="checkout-receipt">
          <div className="checkout-receipt__icon"><Check size={30} strokeWidth={2} /></div>
          <p className="checkout-receipt__label">Amount received</p>
          <p className="checkout-receipt__amount">
            {money(result.receipt.amount, currency)}
          </p>
          <div className="checkout-receipt__meta">
            <div><span>Invoice</span><strong>{result.receipt.invoice_number}</strong></div>
            <div><span>Method</span><strong>{result.receipt.method === 'upi' ? 'UPI QR' : 'Cash'}</strong></div>
            <div><span>Status</span><strong>Paid</strong></div>
          </div>
          <p className="checkout-receipt__note">{result.receipt.note}</p>
          <Button full onClick={onCancel}>New Sale</Button>
        </div>
      ) : (
        <div className="checkout">
          <div className="checkout__headline">
            <div>
              <span className="checkout__label">Invoice</span>
              <strong className="checkout__invoice">{invoiceNumber || '—'}</strong>
            </div>
            <div className="checkout__total">
              <span className="checkout__label">Total payable</span>
              <strong>{money(amount, currency)}</strong>
            </div>
          </div>

          <div className="checkout-tabs" role="tablist" aria-label="Payment method">
            <button
              type="button"
              role="tab"
              aria-selected={method === 'upi'}
              className={`checkout-tab ${method === 'upi' ? 'is-active' : ''}`}
              onClick={() => setMethod('upi')}
            >
              <QrCode size={16} /> UPI QR
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={method === 'cash'}
              className={`checkout-tab ${method === 'cash' ? 'is-active' : ''}`}
              onClick={() => setMethod('cash')}
            >
              <Banknote size={16} /> Cash
            </button>
          </div>

          {loading ? (
            <div className="checkout__loading"><Loader label="Preparing checkout…" /></div>
          ) : method === 'upi' ? (
            <div className="checkout-upi">
              {qr && !qrError ? (
                <>
                  <img className="checkout-upi__qr" src={qr.qr_data_url} alt="UPI payment QR code" />
                  <p className="checkout-upi__vpa">{qr.upi_id}</p>
                  <p className="checkout-upi__hint">
                    Customer scans with any UPI app and pays {money(amount, currency)}.
                  </p>
                </>
              ) : (
                <p className="checkout-upi__hint">
                  {qrError || 'UPI QR is unavailable for this business.'}
                </p>
              )}
            </div>
          ) : (
            <div className="checkout-cash">
              <span className="checkout__label">Collect exactly</span>
              <strong className="checkout-cash__amount">{money(amount, currency)}</strong>
              <p className="checkout-upi__hint">Confirm the cash in hand, then complete the sale.</p>
            </div>
          )}

          <div className="checkout__actions">
            <Button variant="secondary" onClick={onCancel} disabled={completing}>
              Cancel
            </Button>
            <Button onClick={() => void completeSale()} loading={completing} disabled={loading || !invoiceNumber}>
              Complete Sale
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
}
