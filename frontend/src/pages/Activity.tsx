import { Fragment, useCallback, useEffect, useState } from 'react';
import {
  ChevronDown,
  ChevronRight,
  ScrollText,
  Search,
  X,
} from 'lucide-react';
import { api } from '../api/client';
import {
  Badge,
  Button,
  Card,
  EmptyState,
  Input,
  Loader,
  PageHeader,
  Pagination,
  formatDate,
  titleCase,
  useToast,
} from '../components/UI';
import type { ActivityLog, Paginated } from '../types';

const PAGE_SIZE = 20;

function formatDetails(details: unknown): string {
  if (details === null || details === undefined) return 'No additional details.';
  if (typeof details === 'string') return details;
  try {
    return JSON.stringify(details, null, 2);
  } catch {
    return String(details);
  }
}

export function Activity() {
  const toast = useToast();
  const [categoryInput, setCategoryInput] = useState('');
  const [actionInput, setActionInput] = useState('');
  const [queryInput, setQueryInput] = useState('');
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [filters, setFilters] = useState({
    category: '',
    action: '',
    query: '',
    from_date: '',
    to_date: '',
  });
  const [page, setPage] = useState(1);
  const [logs, setLogs] = useState<ActivityLog[]>([]);
  const [meta, setMeta] = useState({ total: 0, pages: 1, page_size: PAGE_SIZE });
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setFilters({
        category: categoryInput.trim(),
        action: actionInput.trim(),
        query: queryInput.trim(),
        from_date: fromDate,
        to_date: toDate,
      });
      setPage(1);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [categoryInput, actionInput, queryInput, fromDate, toDate]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await api.get<Paginated<ActivityLog>>('/activity', {
        category: filters.category || undefined,
        action: filters.action || undefined,
        query: filters.query || undefined,
        from_date: filters.from_date || undefined,
        to_date: filters.to_date || undefined,
        page,
        page_size: PAGE_SIZE,
      });
      setLogs(result.items);
      setMeta({ total: result.total, pages: result.pages, page_size: result.page_size });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not load the activity log.');
      setLogs([]);
    } finally {
      setLoading(false);
    }
  }, [filters, page, toast]);

  useEffect(() => {
    void load();
  }, [load]);

  const hasFilters = Boolean(
    filters.category || filters.action || filters.query || filters.from_date || filters.to_date,
  );

  function clearFilters() {
    setCategoryInput('');
    setActionInput('');
    setQueryInput('');
    setFromDate('');
    setToDate('');
  }

  return (
    <>
      <PageHeader
        title="Activity log"
        subtitle="A complete, owner-only record of actions across your workspace"
        actions={<Badge tone="info">{meta.total} event{meta.total === 1 ? '' : 's'}</Badge>}
      />

      <Card className="filter-bar">
        <div className="filter-bar__search">
          <Search size={17} />
          <Input value={queryInput} onChange={(event) => setQueryInput(event.target.value)}
            placeholder="Search actions, users or references…" aria-label="Search activity" />
        </div>
        <Input value={categoryInput} onChange={(event) => setCategoryInput(event.target.value)}
          placeholder="Category (e.g. invoice)" aria-label="Filter by category" />
        <Input value={actionInput} onChange={(event) => setActionInput(event.target.value)}
          placeholder="Action (e.g. created)" aria-label="Filter by action" />
        <div className="date-range">
          <Input type="date" value={fromDate} max={toDate || undefined} aria-label="From date"
            onChange={(event) => setFromDate(event.target.value)} />
          <span>to</span>
          <Input type="date" value={toDate} min={fromDate || undefined} aria-label="To date"
            onChange={(event) => setToDate(event.target.value)} />
        </div>
        {hasFilters && (
          <Button variant="ghost" size="sm" icon={<X size={15} />} onClick={clearFilters}>
            Clear
          </Button>
        )}
      </Card>

      <Card padded={false}>
        {loading ? (
          <Loader label="Loading activity…" full />
        ) : logs.length ? (
          <>
            <div className="table-scroll">
              <table className="data-table data-table--compact activity-table">
                <thead>
                  <tr>
                    <th>User</th>
                    <th>Action</th>
                    <th>Category</th>
                    <th>Reference</th>
                    <th>Details</th>
                    <th>Timestamp</th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map((log) => {
                    const isOpen = Boolean(expanded[log.id]);
                    return (
                      <Fragment key={log.id}>
                        <tr className="clickable-row"
                          onClick={() => setExpanded((prev) => ({ ...prev, [log.id]: !prev[log.id] }))}>
                          <td><strong>{log.user_name || 'System'}</strong></td>
                          <td><strong className="small">{titleCase(log.action)}</strong>
                            {log.entity_type && <small className="cell-sub">{log.entity_type}</small>}
                          </td>
                          <td><Badge tone="neutral">{titleCase(log.category)}</Badge></td>
                          <td className="small mono">{log.reference || '—'}</td>
                          <td>
                            <span className="text-link">
                              {isOpen ? 'Hide' : 'View'} {isOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                            </span>
                          </td>
                          <td>{formatDate(log.created_at, true)}</td>
                        </tr>
                        {isOpen && (
                          <tr className="activity-details-row">
                            <td colSpan={6}>
                              <pre>{formatDetails(log.details)}</pre>
                              {log.entity_id && <small className="muted">Entity ID: {log.entity_id}</small>}
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <Pagination page={page} pages={meta.pages} total={meta.total}
              pageSize={meta.page_size} onPage={setPage} />
          </>
        ) : (
          <EmptyState
            title="No activity found"
            description={hasFilters ? 'Try changing the filters.' : 'Actions will be logged here automatically.'}
            icon={<ScrollText size={24} />}
          />
        )}
      </Card>
    </>
  );
}
