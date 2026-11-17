import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowUpRight,
  Building2,
  Mail,
  MessageSquarePlus,
  Pencil,
  Phone,
  Plus,
  ReceiptText,
  Search,
  Trash2,
  UserRound,
  Users,
} from 'lucide-react';
import { api } from '../api/client';
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
  Textarea,
  formatDate,
  initials,
  money,
} from '../components/UI';
import type {
  Customer,
  CustomerDetail,
  CustomerInput,
  CustomerStats,
  Interaction,
  MessageResponse,
  Paginated,
} from '../types';

const PAGE_SIZE = 12;
const EMPTY_STATS: CustomerStats = {
  total_purchases: 0,
  invoice_count: 0,
  outstanding_balance: 0,
  total_paid: 0,
  last_transaction_date: null,
  last_invoice_date: null,
};

function daysSince(value?: string | null): number | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return Math.floor((Date.now() - date.getTime()) / 86400000);
}

function customerLabel(stats: CustomerStats): { label: string; tone: 'success' | 'neutral' | 'warning' } {
  const days = daysSince(stats.last_invoice_date);
  if (stats.invoice_count >= 3) return { label: 'Frequent', tone: 'success' };
  if (days === null || days > 90) return { label: 'Inactive', tone: 'neutral' };
  return { label: 'Regular', tone: 'warning' };
}

/* ------------------------------------------------------------------ */
/* Customer create / edit form                                          */
/* ------------------------------------------------------------------ */

function CustomerForm({
  open,
  onClose,
  initial,
  onSaved,
}: {
  open: boolean;
  onClose: () => void;
  initial: Customer | null;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<CustomerInput>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open) return;
    setError('');
    setForm(
      initial
        ? {
            name: initial.name,
            phone: initial.phone ?? '',
            email: initial.email ?? '',
            address: initial.address ?? '',
            city: initial.city ?? '',
            state: initial.state ?? '',
            pincode: initial.pincode ?? '',
            gstin: initial.gstin ?? '',
            notes: initial.notes ?? '',
            is_active: initial.is_active,
          }
        : {
            name: '', phone: '', email: '', address: '', city: '',
            state: '', pincode: '', gstin: '', notes: '', is_active: true,
          },
    );
  }, [open, initial]);

  function set(field: keyof CustomerInput, value: string | boolean) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    setError('');
    if (!form.name?.trim()) {
      setError('Customer name is required.');
      return;
    }
    const payload: CustomerInput = {
      ...form,
      name: form.name.trim(),
      email: form.email?.trim() || undefined,
      phone: form.phone?.trim() || undefined,
      gstin: form.gstin?.trim() || undefined,
    };
    setSaving(true);
    try {
      if (initial) {
        await api.patch<Customer>(`/customers/${initial.id}`, payload);
      } else {
        await api.post<Customer>('/customers', payload);
      }
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save the customer.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={initial ? 'Edit customer' : 'Add a customer'}
      subtitle="Keep your customer records accurate and up to date."
      size="lg"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" form="customer-form" loading={saving}>
            {initial ? 'Save changes' : 'Add customer'}
          </Button>
        </>
      }
    >
      {error && <div className="alert alert--error">{error}</div>}
      <form id="customer-form" onSubmit={save} className="form-stack">
        <div className="form-grid form-grid--2">
          <Field label="Full name" required>
            <Input required value={form.name ?? ''} placeholder="Rohan Sharma"
              onChange={(e) => set('name', e.target.value)} />
          </Field>
          <Field label="Phone">
            <Input value={form.phone ?? ''} placeholder="+91 98765 43210"
              onChange={(e) => set('phone', e.target.value)} />
          </Field>
        </div>
        <div className="form-grid form-grid--2">
          <Field label="Email">
            <Input type="email" value={form.email ?? ''} placeholder="name@example.com"
              onChange={(e) => set('email', e.target.value)} />
          </Field>
          <Field label="GSTIN">
            <Input value={form.gstin ?? ''} placeholder="27AAPFU0939F1ZV"
              onChange={(e) => set('gstin', e.target.value)} />
          </Field>
        </div>
        <Field label="Address">
          <Textarea rows={2} value={form.address ?? ''} placeholder="Street, area, landmark…"
            onChange={(e) => set('address', e.target.value)} />
        </Field>
        <div className="form-grid form-grid--3">
          <Field label="City"><Input value={form.city ?? ''} onChange={(e) => set('city', e.target.value)} /></Field>
          <Field label="State"><Input value={form.state ?? ''} onChange={(e) => set('state', e.target.value)} /></Field>
          <Field label="Pincode"><Input value={form.pincode ?? ''} onChange={(e) => set('pincode', e.target.value)} /></Field>
        </div>
        <Field label="Notes">
          <Textarea rows={2} value={form.notes ?? ''} placeholder="Internal notes about this customer…"
            onChange={(e) => set('notes', e.target.value)} />
        </Field>
        {initial && (
          <Checkbox checked={Boolean(form.is_active)} onChange={(checked) => set('is_active', checked)}
            label="Active customer" hint="Inactive customers are hidden from new invoice pickers." />
        )}
      </form>
    </Modal>
  );
}

/* ------------------------------------------------------------------ */
/* Customer detail drawer                                               */
/* ------------------------------------------------------------------ */

function CustomerDetailDrawer({
  id,
  onClose,
  onEdit,
  onChanged,
  currency,
}: {
  id: string;
  onClose: () => void;
  onEdit: (customer: Customer) => void;
  onChanged: () => void;
  currency: string;
}) {
  const navigate = useNavigate();
  const [detail, setDetail] = useState<CustomerDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [interactionType, setInteractionType] = useState('note');
  const [content, setContent] = useState('');
  const [saving, setSaving] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);

  const load = useCallback(async () => {
    try {
      setDetail(await api.get<CustomerDetail>(`/customers/${id}`));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  async function addInteraction(event: FormEvent) {
    event.preventDefault();
    if (!content.trim()) return;
    setSaving(true);
    try {
      await api.post<Interaction>(`/customers/${id}/interactions`, {
        type: interactionType,
        content: content.trim(),
      });
      setContent('');
      await load();
      onChanged();
    } finally {
      setSaving(false);
    }
  }

  async function removeCustomer() {
    try {
      await api.delete<MessageResponse>(`/customers/${id}`);
      setDeleteOpen(false);
      onClose();
      onChanged();
    } finally {
      setDeleteOpen(false);
    }
  }

  if (loading) return <Drawer open onClose={onClose} title="Customer"><Loader label="Loading customer…" full /></Drawer>;
  if (!detail) return <Drawer open onClose={onClose} title="Customer"><EmptyState title="Customer not found" /></Drawer>;

  const stats = detail.stats;
  const label = customerLabel(stats);

  return (
    <>
      <Drawer
        open
        onClose={onClose}
        title={detail.name}
        subtitle={detail.phone ?? detail.email ?? 'Customer profile'}
        width={580}
        footer={
          <div className="drawer-actions">
            <Button size="sm" onClick={() => { onClose(); navigate(`/admin/billing?customer_id=${detail.id}`); }}
              icon={<ReceiptText size={15} />}>
              New invoice
            </Button>
            <Button size="sm" variant="secondary" icon={<Pencil size={14} />}
              onClick={() => onEdit(detail)}>
              Edit profile
            </Button>
            <Button size="sm" variant="ghost" icon={<Trash2 size={14} />}
              onClick={() => setDeleteOpen(true)}>
              Delete
            </Button>
          </div>
        }
      >
        <div className="customer-profile-head">
          <span className="avatar avatar--lg">{initials(detail.name)}</span>
          <div>
            <div className="customer-profile-head__badges">
              <Badge tone={detail.is_active ? 'success' : 'neutral'} dot>
                {detail.is_active ? 'Active' : 'Inactive'}
              </Badge>
              <Badge tone={label.tone}>{label.label}</Badge>
            </div>
            <p className="muted">{detail.email || 'No email on file'}</p>
          </div>
        </div>

        <div className="detail-stat-grid">
          <div className="detail-stat"><span>Total purchases</span><strong>{money(stats.total_purchases, currency)}</strong></div>
          <div className="detail-stat"><span>Outstanding</span><strong className="text-warning">{money(stats.outstanding_balance, currency)}</strong></div>
          <div className="detail-stat"><span>Invoices</span><strong>{stats.invoice_count}</strong></div>
          <div className="detail-stat"><span>Total paid</span><strong className="text-success">{money(stats.total_paid, currency)}</strong></div>
        </div>

        <div className="detail-section">
          <h4>Contact & address</h4>
          <div className="contact-grid">
            <span><Phone size={15} /> {detail.phone || '—'}</span>
            <span><Mail size={15} /> {detail.email || '—'}</span>
            <span><Building2 size={15} /> {[detail.address, detail.city, detail.state, detail.pincode].filter(Boolean).join(', ') || '—'}</span>
            <span><UserRound size={15} /> GSTIN: {detail.gstin || '—'}</span>
          </div>
          {detail.notes && <p className="detail-notes">{detail.notes}</p>}
          <p className="muted small">
            Last invoice: {formatDate(stats.last_invoice_date)} · Last payment: {formatDate(stats.last_transaction_date)}
          </p>
        </div>

        <div className="detail-section">
          <h4>Interactions ({detail.interactions.length})</h4>
          <form className="interaction-form" onSubmit={addInteraction}>
            <Select value={interactionType} onChange={(e) => setInteractionType(e.target.value)}>
              <option value="note">Note</option>
              <option value="call">Call</option>
              <option value="email">Email</option>
              <option value="meeting">Meeting</option>
              <option value="other">Other</option>
            </Select>
            <Input value={content} placeholder="What happened?" onChange={(e) => setContent(e.target.value)} required />
            <Button type="submit" size="sm" icon={<MessageSquarePlus size={14} />} loading={saving}>Add</Button>
          </form>
          {detail.interactions.length ? (
            <div className="timeline">
              {detail.interactions.map((interaction) => (
                <div className="timeline__item" key={interaction.id}>
                  <span className="timeline__dot" />
                  <div>
                    <div className="timeline__meta">
                      <Badge tone="info">{interaction.type}</Badge>
                      <span className="muted">{formatDate(interaction.created_at, true)}</span>
                    </div>
                    <p>{interaction.content}</p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted">No interactions logged yet.</p>
          )}
        </div>
      </Drawer>

      <ConfirmDialog
        open={deleteOpen}
        onClose={() => setDeleteOpen(false)}
        onConfirm={() => void removeCustomer()}
        title="Delete this customer?"
        description="This will remove the customer record. Existing invoices remain intact."
        confirmLabel="Delete customer"
        danger
      />
    </>
  );
}

/* ------------------------------------------------------------------ */
/* Customers page                                                       */
/* ------------------------------------------------------------------ */

export function Customers() {
  const { business } = useAuth();
  const currency = business?.currency ?? 'INR';
  const [queryInput, setQueryInput] = useState('');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1);
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [statsMap, setStatsMap] = useState<Record<string, CustomerStats>>({});
  const [meta, setMeta] = useState({ total: 0, pages: 1, page_size: PAGE_SIZE });
  const [loading, setLoading] = useState(true);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Customer | null>(null);
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
      const result = await api.get<Paginated<Customer>>('/customers', {
        query: query || undefined,
        page,
        page_size: PAGE_SIZE,
      });
      setCustomers(result.items);
      setMeta({ total: result.total, pages: result.pages, page_size: result.page_size });

      const details = await Promise.allSettled(
        result.items.map((customer) => api.get<CustomerDetail>(`/customers/${customer.id}`)),
      );
      const next: Record<string, CustomerStats> = {};
      details.forEach((entry, index) => {
        if (entry.status === 'fulfilled') {
          next[result.items[index].id] = entry.value.stats;
        }
      });
      setStatsMap(next);
    } finally {
      setLoading(false);
    }
  }, [query, page]);

  useEffect(() => {
    void load();
  }, [load]);

  const frequentCount = Object.values(statsMap).filter((s) => s.invoice_count >= 3).length;
  const outstandingTotal = Object.values(statsMap).reduce((sum, s) => sum + s.outstanding_balance, 0);

  return (
    <>
      <PageHeader
        title="Customers"
        subtitle="Manage relationships and keep track of every interaction"
        actions={<Button icon={<Plus size={16} />} onClick={() => { setEditing(null); setFormOpen(true); }}>
          Add customer
        </Button>}
      />

      <div className="stat-grid stat-grid--3">
        <Card className="stat-card stat-card--info">
          <span className="stat-card__icon"><Users size={19} /></span>
          <div className="stat-card__value">{meta.total}</div>
          <div className="stat-card__label">Total customers</div>
        </Card>
        <Card className="stat-card stat-card--success">
          <span className="stat-card__icon"><ArrowUpRight size={19} /></span>
          <div className="stat-card__value">{frequentCount}</div>
          <div className="stat-card__label">Frequent buyers (3+ invoices)</div>
        </Card>
        <Card className="stat-card stat-card--warning">
          <span className="stat-card__icon"><ReceiptText size={19} /></span>
          <div className="stat-card__value">{money(outstandingTotal, currency)}</div>
          <div className="stat-card__label">Outstanding on this page</div>
        </Card>
      </div>

      <Card className="filter-bar">
        <div className="filter-bar__search">
          <Search size={17} />
          <Input value={queryInput} onChange={(e) => setQueryInput(e.target.value)}
            placeholder="Search by name, phone, email or GSTIN…" aria-label="Search customers" />
        </div>
        <span className="muted small">{meta.total} customer{meta.total === 1 ? '' : 's'}</span>
      </Card>

      <Card padded={false}>
        {loading ? (
          <Loader label="Loading customers…" full />
        ) : customers.length ? (
          <>
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Customer</th>
                    <th>Contact</th>
                    <th className="text-right">Purchases</th>
                    <th className="text-right">Outstanding</th>
                    <th className="text-right">Invoices</th>
                    <th>Last transaction</th>
                    <th>Segment</th>
                    <th aria-label="Actions" />
                  </tr>
                </thead>
                <tbody>
                  {customers.map((customer) => {
                    const stats = statsMap[customer.id] ?? EMPTY_STATS;
                    const segment = customerLabel(stats);
                    return (
                      <tr key={customer.id} className="clickable-row" onClick={() => setDetailId(customer.id)}>
                        <td>
                          <div className="cell-with-icon">
                            <span className="avatar avatar--sm">{initials(customer.name)}</span>
                            <div>
                              <strong>{customer.name}</strong>
                              <small className="cell-sub">{customer.city || '—'}</small>
                            </div>
                          </div>
                        </td>
                        <td>
                          <strong className="small">{customer.phone || '—'}</strong>
                          <small className="cell-sub">{customer.email || '—'}</small>
                        </td>
                        <td className="text-right strong">{money(stats.total_purchases, currency)}</td>
                        <td className={`text-right ${stats.outstanding_balance > 0 ? 'text-warning' : 'text-success'}`}>
                          {money(stats.outstanding_balance, currency)}
                        </td>
                        <td className="text-right">{stats.invoice_count}</td>
                        <td>{formatDate(stats.last_transaction_date)}</td>
                        <td><Badge tone={segment.tone}>{segment.label}</Badge></td>
                        <td>
                          <button type="button" className="icon-btn" aria-label="View customer"
                            onClick={(event) => { event.stopPropagation(); setDetailId(customer.id); }}>
                            <ArrowUpRight size={16} />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <Pagination page={page} pages={meta.pages} total={meta.total}
              pageSize={meta.page_size} onPage={setPage} />
          </>
        ) : (
          <EmptyState title="No customers found" description="Try a different search or add a new customer."
            icon={<Users size={24} />}
            action={<Button icon={<Plus size={15} />} onClick={() => { setEditing(null); setFormOpen(true); }}>Add customer</Button>} />
        )}
      </Card>

      <CustomerForm open={formOpen} onClose={() => { setFormOpen(false); setEditing(null); }}
        initial={editing} onSaved={() => { setFormOpen(false); setEditing(null); void load(); }} />

      {detailId && (
        <CustomerDetailDrawer id={detailId} onClose={() => setDetailId(null)}
          onEdit={(customer) => { setDetailId(null); setEditing(customer); setFormOpen(true); }}
          onChanged={() => void load()} currency={currency} />
      )}
    </>
  );
}
