import { useCallback, useEffect, useState } from 'react';
import {
  ArrowDownToLine,
  BarChart3,
  CalendarDays,
  Download,
  ReceiptText,
  ShoppingBag,
  TrendingUp,
  Users,
  Wallet,
} from 'lucide-react';
import { api, buildQuery, downloadFile } from '../api/client';
import { useAuth } from '../context/AuthContext';
import {
  PaymentMethodsChart,
  SalesBarChart,
  StatusBreakdownChart,
  TopProductsChart,
} from '../components/Charts';
import {
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  Field,
  Input,
  Loader,
  PageHeader,
  StatCard,
  formatDate,
  money,
  titleCase,
} from '../components/UI';
import type { AnalyticsResponse } from '../types';

export function Analytics() {
  const { business } = useAuth();
  const currency = business?.currency ?? 'INR';
  const [fromInput, setFromInput] = useState('');
  const [toInput, setToInput] = useState('');
  const [range, setRange] = useState({ from: '', to: '' });
  const [data, setData] = useState<AnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await api.get<AnalyticsResponse>('/analytics', {
        from_date: range.from || undefined,
        to_date: range.to || undefined,
      }));
    } finally {
      setLoading(false);
    }
  }, [range]);

  useEffect(() => {
    void load();
  }, [load]);

  async function downloadCsv() {
    setDownloading(true);
    try {
      const query = buildQuery({
        from_date: range.from || undefined,
        to_date: range.to || undefined,
      });
      await downloadFile(`/analytics/reports/sales.csv${query}`, 'billflow-sales-report.csv');
    } finally {
      setDownloading(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Analytics & Reports"
        subtitle="Dive into sales, collections and customer performance"
        actions={
          <Button variant="secondary" icon={<Download size={16} />} onClick={() => void downloadCsv()} loading={downloading}>
            Download CSV report
          </Button>
        }
      />

      <Card className="filter-bar">
        <div className="date-range date-range--labeled">
          <Field label="From date">
            <Input type="date" value={fromInput} max={toInput || undefined}
              onChange={(e) => setFromInput(e.target.value)} />
          </Field>
          <Field label="To date">
            <Input type="date" value={toInput} min={fromInput || undefined}
              onChange={(e) => setToInput(e.target.value)} />
          </Field>
        </div>
        <div className="filter-bar__buttons">
          <Button size="md" icon={<CalendarDays size={16} />}
            onClick={() => setRange({ from: fromInput, to: toInput })}>
            Apply range
          </Button>
          {(range.from || range.to || fromInput || toInput) && (
            <Button size="md" variant="ghost"
              onClick={() => {
                setFromInput('');
                setToInput('');
                setRange({ from: '', to: '' });
              }}>
              Clear
            </Button>
          )}
        </div>
        <div className="filter-bar__hint">
          {range.from || range.to ? (
            <Badge tone="info">
              {range.from ? formatDate(range.from) : 'Beginning'} → {range.to ? formatDate(range.to) : 'Today'}
            </Badge>
          ) : (
            <Badge tone="neutral">All time</Badge>
          )}
        </div>
      </Card>

      {loading ? (
        <Card><Loader label="Crunching your numbers…" full /></Card>
      ) : !data ? (
        <Card><EmptyState title="No analytics available" description="Try a different date range." /></Card>
      ) : (
        <>
          <div className="stat-grid stat-grid--4">
            <StatCard label="Total sales" value={money(data.summary.total_sales, currency)}
              icon={<TrendingUp size={19} />} tone="info"
              hint={`${data.summary.total_invoices} invoices`} />
            <StatCard label="Total collections" value={money(data.summary.total_collections, currency)}
              icon={<Wallet size={19} />} tone="success"
              hint={`${data.summary.total_transactions} transactions`} />
            <StatCard label="Average invoice" value={money(data.summary.average_invoice_value, currency)}
              icon={<ReceiptText size={19} />} tone="info"
              trend={data.summary.growth_percent} />
            <StatCard label="Outstanding" value={money(data.summary.outstanding, currency)}
              icon={<ArrowDownToLine size={19} />} tone="warning"
              hint={`${data.pending_invoices} unpaid invoices`} />
          </div>

          <div className="grid-12">
            <div className="col-8">
              <Card>
                <CardHeader title="Sales vs Collections" subtitle="Revenue billed against cash received" />
                <SalesBarChart data={data.sales_trend} currency={currency} />
              </Card>
            </div>
            <div className="col-4">
              <Card>
                <CardHeader title="Payment Methods" subtitle="How your customers pay" />
                <PaymentMethodsChart data={data.payment_methods} currency={currency} />
              </Card>
            </div>
          </div>

          <div className="grid-12">
            <div className="col-6">
              <Card>
                <CardHeader title="Top Products" subtitle="Highest revenue contributors" />
                <TopProductsChart data={data.top_products} currency={currency} />
              </Card>
            </div>
            <div className="col-6">
              <Card>
                <CardHeader title="Invoice Status" subtitle="Breakdown by value" />
                <StatusBreakdownChart data={data.status_breakdown} currency={currency} />
              </Card>
            </div>
          </div>

          <div className="grid-12">
            <div className="col-7">
              <Card padded={false}>
                <div className="card-padded">
                  <CardHeader title="Top Customers" subtitle="Your most valuable relationships" />
                </div>
                {data.top_customers.length ? (
                  <div className="table-scroll">
                    <table className="data-table data-table--compact">
                      <thead>
                        <tr>
                          <th>Customer</th>
                          <th className="text-right">Purchases</th>
                          <th className="text-right">Invoices</th>
                          <th className="text-right">Outstanding</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.top_customers.map((customer, index) => (
                          <tr key={customer.customer_id}>
                            <td>
                              <div className="cell-with-index">
                                <span className="rank-index">{index + 1}</span>
                                <strong>{customer.name}</strong>
                              </div>
                            </td>
                            <td className="text-right strong">{money(customer.total_purchases, currency)}</td>
                            <td className="text-right">{customer.invoice_count}</td>
                            <td className={`text-right ${customer.outstanding > 0 ? 'text-warning' : 'text-success'}`}>
                              {money(customer.outstanding, currency)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <EmptyState title="No customer data" description="Data appears here after your first sale." />
                )}
              </Card>
            </div>
            <div className="col-5">
              <Card>
                <CardHeader title="Business Snapshot" subtitle="Period highlights" />
                <div className="insight-list">
                  <div className="insight-list__item">
                    <span className="insight-list__icon"><Users size={17} /></span>
                    <div><strong>{data.total_customers}</strong><span>Total customers</span></div>
                  </div>
                  <div className="insight-list__item">
                    <span className="insight-list__icon"><BarChart3 size={17} /></span>
                    <div><strong>{data.active_customers}</strong><span>Active customers</span></div>
                  </div>
                  <div className="insight-list__item">
                    <span className="insight-list__icon"><ShoppingBag size={17} /></span>
                    <div><strong>{money(data.year_sales, currency)}</strong><span>Year-to-date sales</span></div>
                  </div>
                  <div className="insight-list__item">
                    <span className="insight-list__icon"><ReceiptText size={17} /></span>
                    <div><strong>{data.pending_invoices}</strong><span>Pending invoices</span></div>
                  </div>
                  <div className="insight-list__item">
                    <span className="insight-list__icon"><TrendingUp size={17} /></span>
                    <div>
                      <strong className={data.summary.growth_percent >= 0 ? 'text-success' : 'text-danger'}>
                        {data.summary.growth_percent >= 0 ? '+' : ''}{data.summary.growth_percent.toFixed(1)}%
                      </strong>
                      <span>Growth</span>
                    </div>
                  </div>
                </div>
                <p className="muted small insight-period">
                  {data.from_date && data.to_date
                    ? `${formatDate(data.from_date)} – ${formatDate(data.to_date)}`
                    : 'All available records'}
                </p>
                <div className="status-summary">
                  {data.status_breakdown.map((entry) => (
                    <span key={entry.status}><Badge tone="neutral">{titleCase(entry.status)}</Badge> {entry.count}</span>
                  ))}
                </div>
              </Card>
            </div>
          </div>
        </>
      )}
    </>
  );
}
