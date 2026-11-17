import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowRight,
  Banknote,
  CreditCard,
  Package,
  ReceiptText,
  ShoppingCart,
  TrendingUp,
  Users,
} from 'lucide-react';
import { api } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { PaymentMethodsChart, SalesTrendChart } from '../components/Charts';
import {
  Button,
  Card,
  CardHeader,
  EmptyState,
  Loader,
  PageHeader,
  StatCard,
  StatusBadge,
  formatDate,
  money,
  titleCase,
} from '../components/UI';
import type { AnalyticsResponse } from '../types';

export function Dashboard() {
  const { business } = useAuth();
  const currency = business?.currency ?? 'INR';
  const [data, setData] = useState<AnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const result = await api.get<AnalyticsResponse>('/analytics/dashboard');
        if (active) setData(result);
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : 'Failed to load dashboard');
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  if (loading) {
    return (
      <>
        <PageHeader title="Overview" subtitle="A snapshot of your business today" />
        <Card><Loader label="Loading your dashboard…" full /></Card>
      </>
    );
  }

  if (error || !data) {
    return (
      <>
        <PageHeader title="Overview" />
        <Card>
          <EmptyState
            title="Couldn't load your dashboard"
            description={error || 'Please try again in a moment.'}
            action={<Button onClick={() => window.location.reload()}>Retry</Button>}
          />
        </Card>
      </>
    );
  }

  const { summary } = data;

  return (
    <>
      <PageHeader
        title="Dashboard overview"
        subtitle="Here's what's happening across your business today"
        actions={
          <div className="header-actions">
            <span className="period-chip">
              <TrendingUp size={15} />
              {summary.growth_percent >= 0 ? '+' : ''}
              {summary.growth_percent.toFixed(1)}% growth
            </span>
            <Link to="/admin/billing">
              <Button icon={<ReceiptText size={16} />}>New invoice</Button>
            </Link>
          </div>
        }
      />

      <div className="stat-grid stat-grid--6">
        <StatCard
          label="Today's Sales"
          value={money(data.today_sales, currency)}
          icon={<ShoppingCart size={19} />}
          tone="info"
          hint={`${data.today_transactions} transactions today`}
        />
        <StatCard
          label="Today's Collections"
          value={money(data.today_collections, currency)}
          icon={<Banknote size={19} />}
          tone="success"
          hint="Cash received today"
        />
        <StatCard
          label="This Month's Sales"
          value={money(data.month_sales, currency)}
          icon={<TrendingUp size={19} />}
          tone="info"
          hint={money(data.year_sales, currency) + ' this year'}
          trend={summary.growth_percent}
        />
        <StatCard
          label="Outstanding"
          value={money(data.pending_amount, currency)}
          icon={<CreditCard size={19} />}
          tone="warning"
          hint={`${data.pending_invoices} invoices pending`}
        />
        <StatCard
          label="Low Stock"
          value={data.low_stock_products}
          icon={<AlertTriangle size={19} />}
          tone="danger"
          hint={data.low_stock_products ? 'Items need restocking' : 'All stock levels healthy'}
        />
        <StatCard
          label="Customers"
          value={data.total_customers}
          icon={<Users size={19} />}
          tone="info"
          hint={`${data.active_customers} active customers`}
        />
      </div>

      <div className="grid-12">
        <div className="col-8">
          <Card>
            <CardHeader
              title="Sales & Collections"
              subtitle="How revenue is tracking over time"
              action={
                <Link to="/admin/analytics" className="text-link">
                  View report <ArrowRight size={14} />
                </Link>
              }
            />
            <SalesTrendChart data={data.sales_trend} currency={currency} />
          </Card>
        </div>
        <div className="col-4">
          <Card>
            <CardHeader title="Payment Methods" subtitle="Share of collections" />
            <PaymentMethodsChart data={data.payment_methods} currency={currency} />
          </Card>
        </div>
      </div>

      <div className="grid-12">
        <div className="col-6">
          <Card padded={false}>
            <div className="card-padded">
              <CardHeader
                title="Top Products"
                subtitle="Best sellers by revenue"
                action={<Link to="/admin/inventory" className="text-link">All products</Link>}
              />
            </div>
            {data.top_products.length ? (
              <div className="table-scroll">
                <table className="data-table data-table--compact">
                  <thead>
                    <tr>
                      <th>Product</th>
                      <th className="text-right">Qty</th>
                      <th className="text-right">Revenue</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.top_products.slice(0, 5).map((product, index) => (
                      <tr key={`${product.product_id ?? 'product'}-${index}`}>
                        <td>
                          <div className="cell-with-index">
                            <span className="rank-index">{index + 1}</span>
                            <strong>{product.name}</strong>
                          </div>
                        </td>
                        <td className="text-right">{product.quantity_sold}</td>
                        <td className="text-right strong">{money(product.revenue, currency)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState title="No product sales yet" description="Sales will appear here once you create invoices." />
            )}
          </Card>
        </div>

        <div className="col-6">
          <Card padded={false}>
            <div className="card-padded">
              <CardHeader
                title="Recent Invoices"
                subtitle="Latest billing activity"
                action={<Link to="/admin/billing" className="text-link">All invoices</Link>}
              />
            </div>
            {data.recent_invoices.length ? (
              <div className="table-scroll">
                <table className="data-table data-table--compact">
                  <thead>
                    <tr>
                      <th>Invoice</th>
                      <th>Customer</th>
                      <th className="text-right">Amount</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.recent_invoices.slice(0, 5).map((invoice) => (
                      <tr key={invoice.id}>
                        <td>
                          <strong className="mono">{invoice.invoice_number}</strong>
                          <small className="cell-sub">{formatDate(invoice.issue_date)}</small>
                        </td>
                        <td>{invoice.customer_name ?? '—'}</td>
                        <td className="text-right strong">{money(invoice.total_amount, currency)}</td>
                        <td><StatusBadge status={invoice.status} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState title="No invoices yet" description="Create your first invoice to get started." />
            )}
          </Card>
        </div>
      </div>

      <Card>
        <CardHeader
          title="Recent Payments"
          subtitle="The latest collections recorded"
          action={<Link to="/admin/payments" className="text-link">All payments <ArrowRight size={14} /></Link>}
        />
        {data.recent_payments.length ? (
          <div className="activity-list">
            {data.recent_payments.slice(0, 6).map((payment) => (
              <div className="activity-item" key={payment.id}>
                <span className="activity-item__icon">
                  <CreditCard size={17} />
                </span>
                <div className="activity-item__main">
                  <strong>{payment.customer_name ?? payment.invoice_number ?? 'Payment'}</strong>
                  <span>
                    {payment.invoice_number ? `${payment.invoice_number} · ` : ''}
                    {titleCase(payment.method)} · {formatDate(payment.created_at, true)}
                  </span>
                </div>
                <span className="activity-item__amount">+{money(payment.amount, currency)}</span>
                <StatusBadge status={payment.status} />
              </div>
            ))}
          </div>
        ) : (
          <EmptyState title="No payments yet" description="Recorded payments will show up here." />
        )}
      </Card>
    </>
  );
}
