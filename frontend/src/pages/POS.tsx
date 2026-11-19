import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ComponentProps,
  type ComponentType,
  type KeyboardEvent as ReactKeyboardEvent,
} from 'react';
import {
  Barcode,
  CheckCircle2,
  Minus,
  Package,
  Plus,
  ScanBarcode,
  Search,
  ShoppingBasket,
  Trash2,
  UserRound,
  X,
} from 'lucide-react';
import { api, ApiError } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { CheckoutModal } from '../components/CheckoutModal';
import {
  Badge,
  Button,
  Card,
  EmptyState,
  Input,
  Loader,
  money,
  useToast,
} from '../components/UI';
import type {
  Customer,
  Paginated,
  PosCheckoutResponse,
  PricingMode,
  Product,
} from '../types';

interface CartLine {
  product: Product;
  quantity: number;
  discount_percent: number;
}

const round2 = (value: number): number => Math.round(value * 100) / 100;

/** Display-only helper: the backend re-derives the charged price at checkout. */
export function effectiveUnitPrice(product: Product, mode: PricingMode): number {
  if (mode === 'wholesale') {
    const discount = product.wholesale_discount_percent || 0;
    return round2(product.price * (1 - discount / 100));
  }
  return product.price;
}

const pricingModeLabel = (mode: PricingMode): string =>
  mode === 'wholesale' ? 'Wholesale' : 'Retail';

/*
 * CheckoutModal builds the /pos/qr and /pos/checkout request bodies itself.
 * Inject the active pricing mode into just those two calls so the backend can
 * apply its authoritative, mode-derived unit prices — no second pricing engine
 * and no changes to the shared checkout component.
 */
type ApiPost = typeof api.post;
const originalPost = api.post.bind(api) as ApiPost;
let activePricingMode: PricingMode = 'retail';
(api as { post: ApiPost }).post = (async (path: string, body?: unknown) => {
  if (
    (path === '/pos/qr' || path === '/pos/checkout') &&
    body !== null &&
    typeof body === 'object'
  ) {
    return originalPost(path, {
      ...(body as Record<string, unknown>),
      pricing_mode: activePricingMode,
    });
  }
  return originalPost(path, body);
}) as ApiPost;

// Forward-compatible with a CheckoutModal that accepts the mode as a prop.
const CheckoutModalWithMode = CheckoutModal as ComponentType<
  ComponentProps<typeof CheckoutModal> & { pricingMode?: PricingMode }
>;

export function POS() {
  const { business } = useAuth();
  const currency = business?.currency ?? 'INR';
  const toast = useToast();

  const [cart, setCart] = useState<CartLine[]>([]);
  const [pricingMode, setPricingMode] = useState<PricingMode>('retail');
  const [barcodeValue, setBarcodeValue] = useState('');
  const [scanning, setScanning] = useState(false);
  const [searchInput, setSearchInput] = useState('');
  const [query, setQuery] = useState('');
  const [products, setProducts] = useState<Product[]>([]);
  const [productsLoading, setProductsLoading] = useState(false);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [customerQuery, setCustomerQuery] = useState('');
  const [customerOpen, setCustomerOpen] = useState(false);
  const [customerId, setCustomerId] = useState<string | null>(null);
  const [customerName, setCustomerName] = useState('Walk-in Customer');
  const [invoiceDiscount, setInvoiceDiscount] = useState('0');
  const [checkoutOpen, setCheckoutOpen] = useState(false);

  const barcodeRef = useRef<HTMLInputElement>(null);
  const customerRef = useRef<HTMLDivElement>(null);

  /* ---------------------------- focus behaviour --------------------------- */

  useEffect(() => {
    barcodeRef.current?.focus();
  }, []);

  // Keep the value injected into POS checkout requests in sync with the UI.
  useEffect(() => {
    activePricingMode = pricingMode;
  }, [pricingMode]);

  // The "New Bill" button in the staff top bar resets an in-progress bill.
  useEffect(() => {
    const resetBill = () => {
      setCart([]);
      setPricingMode('retail');
      setInvoiceDiscount('0');
      setCustomerId(null);
      setCustomerName('Walk-in Customer');
      setCustomerQuery('');
      setBarcodeValue('');
      barcodeRef.current?.focus();
    };
    window.addEventListener('billflow:new-bill', resetBill);
    return () => window.removeEventListener('billflow:new-bill', resetBill);
  }, []);

  useEffect(() => {
    function onGlobalKey(event: KeyboardEvent) {
      if (event.key === 'F2') {
        event.preventDefault();
        barcodeRef.current?.focus();
        return;
      }
      const target = event.target as HTMLElement | null;
      const tag = target?.tagName;
      const editable =
        tag === 'INPUT' ||
        tag === 'TEXTAREA' ||
        tag === 'SELECT' ||
        Boolean(target?.isContentEditable);
      // Keyboard-wedge scanners type into whatever has focus; make sure that is us.
      if (
        !editable &&
        event.key.length === 1 &&
        !event.ctrlKey &&
        !event.metaKey &&
        !event.altKey
      ) {
        barcodeRef.current?.focus();
      }
    }
    window.addEventListener('keydown', onGlobalKey);
    return () => window.removeEventListener('keydown', onGlobalKey);
  }, []);

  useEffect(() => {
    function onDocClick(event: MouseEvent) {
      if (customerRef.current && !customerRef.current.contains(event.target as Node)) {
        setCustomerOpen(false);
      }
    }
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, []);

  /* ------------------------------- loading -------------------------------- */

  useEffect(() => {
    const timer = window.setTimeout(() => setQuery(searchInput.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  useEffect(() => {
    let active = true;
    setProductsLoading(true);
    (async () => {
      try {
        const result = await api.get<Paginated<Product>>('/products', {
          query: query || undefined,
          page: 1,
          page_size: query ? 40 : 20,
        });
        if (active) setProducts(result.items.filter((product) => product.is_active !== false));
      } catch {
        if (active) setProducts([]);
      } finally {
        if (active) setProductsLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [query]);

  useEffect(() => {
    (async () => {
      try {
        const result = await api.get<Paginated<Customer>>('/customers', { page_size: 200 });
        setCustomers(result.items.filter((customer) => customer.is_active !== false));
      } catch {
        // Customer picker simply stays empty; walk-in billing still works.
      }
    })();
  }, []);

  /* --------------------------------- cart --------------------------------- */

  const addToCart = useCallback((product: Product) => {
    setCart((previous) => {
      const existing = previous.find((line) => line.product.id === product.id);
      if (existing) {
        return previous.map((line) =>
          line.product.id === product.id ? { ...line, quantity: line.quantity + 1 } : line,
        );
      }
      return [...previous, { product, quantity: 1, discount_percent: 0 }];
    });
  }, []);

  async function onBarcodeKeyDown(event: ReactKeyboardEvent<HTMLInputElement>) {
    if (event.key !== 'Enter') return;
    event.preventDefault();
    const code = barcodeValue.trim();
    if (!code || scanning) return;
    setScanning(true);
    try {
      const product = await api.get<Product>(
        `/products/barcode/${encodeURIComponent(code)}`,
      );
      addToCart(product);
      setBarcodeValue('');
      toast.success(`${product.name} added to bill`);
      barcodeRef.current?.focus();
    } catch (error) {
      const notFound = error instanceof ApiError && error.status === 404;
      toast.error(
        notFound
          ? `No product found for barcode “${code}”`
          : error instanceof Error
            ? error.message
            : 'Barcode lookup failed',
      );
      // Keep the scanned value selected so a cashier can retry or correct it.
      window.requestAnimationFrame(() => barcodeRef.current?.select());
    } finally {
      setScanning(false);
    }
  }

  function changeQuantity(productId: string, next: number) {
    setCart((previous) =>
      previous
        .map((line) =>
          line.product.id === productId
            ? { ...line, quantity: Math.max(0, Math.floor(next) || 0) }
            : line,
        )
        .filter((line) => line.quantity > 0),
    );
  }

  function changeDiscount(productId: string, percent: number) {
    setCart((previous) =>
      previous.map((line) =>
        line.product.id === productId
          ? {
              ...line,
              discount_percent: Math.min(100, Math.max(0, percent || 0)),
            }
          : line,
      ),
    );
  }

  function selectCustomer(customer: Customer | null) {
    setCustomerId(customer?.id ?? null);
    setCustomerName(customer?.name ?? 'Walk-in Customer');
    setCustomerQuery(customer?.name ?? '');
    setCustomerOpen(false);
  }

  const filteredCustomers = useMemo(() => {
    const term = customerQuery.trim().toLowerCase();
    if (!term) return customers.slice(0, 30);
    return customers
      .filter((customer) =>
        [customer.name, customer.phone, customer.email]
          .some((value) => (value ?? '').toLowerCase().includes(term)),
      )
      .slice(0, 30);
  }, [customers, customerQuery]);

  const totals = useMemo(() => {
    let subtotal = 0;
    let itemDiscount = 0;
    let tax = 0;
    cart.forEach((line) => {
      const base = effectiveUnitPrice(line.product, pricingMode) * line.quantity;
      const discount = base * (line.discount_percent / 100);
      const taxable = base - discount;
      subtotal += base;
      itemDiscount += discount;
      tax += taxable * ((line.product.gst_rate || 0) / 100);
    });
    const afterTax = subtotal - itemDiscount + tax;
    const discount = afterTax * (Math.min(100, Math.max(0, Number(invoiceDiscount) || 0)) / 100);
    return {
      subtotal,
      itemDiscount,
      tax,
      invoiceDiscount: discount,
      total: afterTax - discount,
      units: cart.reduce((sum, line) => sum + line.quantity, 0),
    };
  }, [cart, invoiceDiscount, pricingMode]);

  // Opening checkout does not touch the database. The invoice, payment and
  // stock movements are created only when the cashier presses Complete Sale.
  function openCheckout() {
    if (!cart.length) return;
    setCheckoutOpen(true);
  }

  function onSaleComplete(_result: PosCheckoutResponse) {
    setCart([]);
    // A completed sale starts the next bill back in retail mode.
    setPricingMode('retail');
    setInvoiceDiscount('0');
    setCustomerId(null);
    setCustomerName('Walk-in Customer');
    setCustomerQuery('');
    setBarcodeValue('');
    toast.success('Sale completed');
    window.setTimeout(() => barcodeRef.current?.focus(), 0);
  }

  /* --------------------------------- render -------------------------------- */

  return (
    <div className="pos-page">
      <div className="pos-grid">
        <section className="pos-left" aria-label="Product selection">
          <Card className="barcode-card" padded={false}>
            <div className="barcode-box">
              <div className="barcode-box__icon">
                <ScanBarcode size={26} strokeWidth={2} />
              </div>
              <div className="barcode-box__main">
                <label className="barcode-box__label" htmlFor="pos-barcode">
                  Scan barcode or type and press Enter
                </label>
                <div className="barcode-input-wrap">
                  <Barcode size={19} />
                  <input
                    id="pos-barcode"
                    ref={barcodeRef}
                    className="barcode-input"
                    value={barcodeValue}
                    onChange={(event) => setBarcodeValue(event.target.value)}
                    onKeyDown={onBarcodeKeyDown}
                    placeholder="Scan or enter product barcode…"
                    autoComplete="off"
                    autoCorrect="off"
                    spellCheck={false}
                    aria-label="Product barcode"
                  />
                  {scanning && <Loader label="" />}
                  {barcodeValue && !scanning && (
                    <button
                      type="button"
                      className="icon-btn"
                      aria-label="Clear barcode"
                      onClick={() => {
                        setBarcodeValue('');
                        barcodeRef.current?.focus();
                      }}
                    >
                      <X size={16} />
                    </button>
                  )}
                  <kbd>F2</kbd>
                </div>
              </div>
            </div>
          </Card>

          <Card className="pos-catalog" padded={false}>
            <div className="pos-catalog__head">
              <div>
                <h2>{query ? `Results for “${query}”` : 'Popular products'}</h2>
                <p>Click a product to add it to the current bill</p>
              </div>
              <div className="pos-search">
                <Search size={17} />
                <Input
                  value={searchInput}
                  onChange={(event) => setSearchInput(event.target.value)}
                  placeholder="Search products or barcode…"
                  aria-label="Search products"
                />
                {searchInput && (
                  <button
                    type="button"
                    className="icon-btn"
                    aria-label="Clear search"
                    onClick={() => setSearchInput('')}
                  >
                    <X size={15} />
                  </button>
                )}
              </div>
            </div>

            <div className="pos-catalog__body">
              {productsLoading && products.length === 0 ? (
                <Loader label="Loading products…" full />
              ) : products.length ? (
                <div className="product-grid">
                  {products.map((product) => {
                    const low = product.is_low_stock || product.stock <= (product.low_stock_threshold ?? 0);
                    return (
                      <button
                        type="button"
                        key={product.id}
                        className="product-tile"
                        onClick={() => {
                          addToCart(product);
                          toast.success(`${product.name} added to bill`);
                          barcodeRef.current?.focus();
                        }}
                      >
                        <span className="product-tile__icon"><Package size={19} /></span>
                        <span className="product-tile__name">{product.name}</span>
                        <span className="product-tile__meta">
                          {product.barcode || product.sku || 'No SKU'}
                        </span>
                        <span className="product-tile__bottom">
                          <strong>{money(effectiveUnitPrice(product, pricingMode), currency)}</strong>
                          <small>{product.gst_rate}% GST</small>
                        </span>
                        {pricingMode === 'wholesale' && (
                          <span className="wholesale-price">
                            Wholesale · {product.wholesale_discount_percent || 0}% off
                            <s>{money(product.price, currency)}</s>
                          </span>
                        )}
                        <span className="product-tile__stock">
                          {product.is_service ? 'Service' : `Stock: ${product.stock}`}
                          {low && !product.is_service && <Badge tone="warning" dot>Low</Badge>}
                        </span>
                      </button>
                    );
                  })}
                </div>
              ) : (
                <EmptyState
                  title={query ? 'No products found' : 'No products yet'}
                  description={
                    query
                      ? 'Try a different name or barcode.'
                      : 'Add products from the admin inventory to start billing.'
                  }
                  icon={<Package size={24} />}
                />
              )}
            </div>
          </Card>
        </section>

        <aside className="pos-cart" aria-label="Current bill">
          <div className="pos-cart__head">
            <div>
              <h2>Current bill</h2>
              <p>{totals.units} item{totals.units === 1 ? '' : 's'} in cart</p>
            </div>
            {cart.length > 0 && (
              <Button
                variant="ghost"
                size="sm"
                icon={<Trash2 size={14} />}
                onClick={() => setCart([])}
              >
                Clear
              </Button>
            )}
          </div>

          <div className="pricing-mode-row">
            <span className="pricing-mode-row__label">Pricing mode</span>
            <div className="pricing-mode-switch" role="tablist" aria-label="Pricing mode">
              <button
                type="button"
                role="tab"
                aria-selected={pricingMode === 'retail'}
                className={`pricing-mode-switch__btn ${pricingMode === 'retail' ? 'is-active' : ''}`}
                onClick={() => setPricingMode('retail')}
              >
                Retail
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={pricingMode === 'wholesale'}
                className={`pricing-mode-switch__btn ${pricingMode === 'wholesale' ? 'is-active' : ''}`}
                onClick={() => setPricingMode('wholesale')}
              >
                Wholesale
              </button>
            </div>
          </div>

          <div className="pos-customer" ref={customerRef}>
            <span className="pos-customer__label"><UserRound size={15} /> Customer</span>
            <div className="pos-customer__control">
              <Input
                value={customerQuery}
                placeholder="Search customer…"
                aria-label="Search customer"
                onFocus={() => setCustomerOpen(true)}
                onChange={(event) => {
                  setCustomerQuery(event.target.value);
                  setCustomerOpen(true);
                }}
              />
              <span className="pos-customer__selected">{customerName}</span>
            </div>
            {customerOpen && (
              <div className="pos-customer__menu" role="listbox">
                <button type="button" role="option" aria-selected={!customerId}
                  onClick={() => selectCustomer(null)}>
                  <UserRound size={15} /> Walk-in Customer
                  {!customerId && <CheckCircle2 size={15} className="pos-customer__check" />}
                </button>
                {filteredCustomers.map((customer) => (
                  <button
                    type="button"
                    role="option"
                    aria-selected={customerId === customer.id}
                    key={customer.id}
                    onClick={() => selectCustomer(customer)}
                  >
                    <span className="avatar avatar--sm">
                      {(customer.name || '?').charAt(0).toUpperCase()}
                    </span>
                    <span className="pos-customer__option">
                      <strong>{customer.name}</strong>
                      <small>{customer.phone || 'No phone'}</small>
                    </span>
                    {customerId === customer.id && (
                      <CheckCircle2 size={15} className="pos-customer__check" />
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="pos-cart__lines">
            {cart.length === 0 ? (
              <EmptyState
                title="Your cart is empty"
                description="Scan a barcode or tap a product to begin."
                icon={<ShoppingBasket size={30} />}
              />
            ) : (
              cart.map((line) => {
                const unitPrice = effectiveUnitPrice(line.product, pricingMode);
                const base = unitPrice * line.quantity;
                const discount = base * (line.discount_percent / 100);
                const lineTotal = base - discount + (base - discount) * ((line.product.gst_rate || 0) / 100);
                return (
                  <div className="cart-row" key={line.product.id}>
                    <div className="cart-row__top">
                      <div className="cart-row__name">
                        <strong>{line.product.name}</strong>
                        <small>
                          {money(unitPrice, currency)} · {line.product.gst_rate}% GST
                        </small>
                        {pricingMode === 'wholesale' && (
                          <small className="wholesale-price">
                            Wholesale price · {line.product.wholesale_discount_percent || 0}% off
                            <s>{money(line.product.price, currency)}</s>
                          </small>
                        )}
                      </div>
                      <button
                        type="button"
                        className="icon-btn icon-btn--danger"
                        aria-label={`Remove ${line.product.name}`}
                        onClick={() =>
                          setCart((previous) =>
                            previous.filter((entry) => entry.product.id !== line.product.id),
                          )
                        }
                      >
                        <Trash2 size={15} />
                      </button>
                    </div>
                    <div className="cart-row__controls">
                      <div className="qty-stepper">
                        <button
                          type="button"
                          aria-label="Decrease quantity"
                          onClick={() => changeQuantity(line.product.id, line.quantity - 1)}
                        >
                          <Minus size={14} />
                        </button>
                        <input
                          type="number"
                          min="1"
                          value={line.quantity}
                          aria-label="Quantity"
                          onChange={(event) =>
                            changeQuantity(line.product.id, Number(event.target.value))
                          }
                        />
                        <button
                          type="button"
                          aria-label="Increase quantity"
                          onClick={() => changeQuantity(line.product.id, line.quantity + 1)}
                        >
                          <Plus size={14} />
                        </button>
                      </div>
                      <label className="cart-row__discount">
                        Disc %
                        <input
                          type="number"
                          min="0"
                          max="100"
                          value={line.discount_percent}
                          aria-label="Discount percent"
                          onChange={(event) =>
                            changeDiscount(line.product.id, Number(event.target.value))
                          }
                        />
                      </label>
                      <strong className="cart-row__total">{money(lineTotal, currency)}</strong>
                    </div>
                  </div>
                );
              })
            )}
          </div>

          <div className="pos-totals">
            <div className="pos-totals__row"><span>Subtotal</span><strong>{money(totals.subtotal, currency)}</strong></div>
            <div className="pos-totals__row"><span>Item discounts</span><strong>− {money(totals.itemDiscount, currency)}</strong></div>
            <div className="pos-totals__row"><span>GST</span><strong>{money(totals.tax, currency)}</strong></div>
            <div className="pos-totals__row pos-totals__row--input">
              <label htmlFor="pos-invoice-discount">Invoice discount (%)</label>
              <input
                id="pos-invoice-discount"
                type="number"
                min="0"
                max="100"
                step="0.01"
                value={invoiceDiscount}
                onChange={(event) => setInvoiceDiscount(event.target.value)}
              />
              <strong>− {money(totals.invoiceDiscount, currency)}</strong>
            </div>
            <div className="pos-totals__row pos-totals__row--grand">
              <span>Grand total</span>
              <strong>{money(totals.total, currency)}</strong>
            </div>
            <div className="pos-totals__row pricing-mode-note">
              <span>Checkout pricing mode</span>
              <strong>{pricingModeLabel(pricingMode)}</strong>
            </div>
          </div>

          <div className="pos-cart__footer">
            <Button
              full
              size="lg"
              icon={<CheckCircle2 size={19} />}
              disabled={cart.length === 0}
              onClick={openCheckout}
            >
              Proceed to Payment · {money(totals.total, currency)}
            </Button>
            <p className="pos-cart__hint">
              {pricingModeLabel(pricingMode)} pricing ·{' '}
              {cart.length === 0
                ? 'Add at least one item to continue to payment.'
                : 'UPI QR or cash — one step to complete the sale.'}
            </p>
          </div>
        </aside>
      </div>

      <CheckoutModalWithMode
        open={checkoutOpen}
        cart={cart}
        customerId={customerId}
        discountPercent={Number(invoiceDiscount) || 0}
        pricingMode={pricingMode}
        businessName={business?.name ?? 'BillFlow'}
        currency={currency}
        onCancel={() => setCheckoutOpen(false)}
        onSaleComplete={onSaleComplete}
      />
    </div>
  );
}
