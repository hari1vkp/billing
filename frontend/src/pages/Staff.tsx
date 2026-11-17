import { useCallback, useEffect, useState, type FormEvent } from 'react';
import {
  RotateCcw,
  Search,
  ShieldCheck,
  Trash2,
  UserPlus,
  Users,
} from 'lucide-react';
import { api } from '../api/client';
import { useAuth } from '../context/AuthContext';
import {
  Badge,
  Button,
  Card,
  ConfirmDialog,
  EmptyState,
  Field,
  Input,
  Loader,
  Modal,
  PageHeader,
  Select,
  formatDate,
  initials,
  useToast,
} from '../components/UI';
import type { AppUser } from '../types';

export function Staff() {
  const { user } = useAuth();
  const toast = useToast();
  const [members, setMembers] = useState<AppUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [queryInput, setQueryInput] = useState('');
  const [query, setQuery] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [toggleTarget, setToggleTarget] = useState<AppUser | null>(null);
  const [form, setForm] = useState({
    full_name: '',
    email: '',
    phone: '',
    password: '',
    role: 'staff',
  });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setMembers(await api.get<AppUser[]>('/business/users'));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not load staff members.');
    } finally {
      setLoading(false);
    }
  }, [toast]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const timer = window.setTimeout(() => setQuery(queryInput.trim().toLowerCase()), 250);
    return () => window.clearTimeout(timer);
  }, [queryInput]);

  const visible = query
    ? members.filter((member) =>
        [member.full_name, member.email, member.phone]
          .some((value) => (value ?? '').toLowerCase().includes(query)),
      )
    : members;

  async function createMember(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    try {
      const created = await api.post<AppUser>('/business/users', {
        full_name: form.full_name.trim(),
        email: form.email.trim(),
        ...(form.phone.trim() ? { phone: form.phone.trim() } : {}),
        password: form.password,
        role: form.role,
      });
      setMembers((previous) => [...previous, created]);
      setModalOpen(false);
      setForm({ full_name: '', email: '', phone: '', password: '', role: 'staff' });
      toast.success('Team member added successfully.');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not add the team member.');
    } finally {
      setSaving(false);
    }
  }

  async function toggleActive() {
    if (!toggleTarget) return;
    setSaving(true);
    try {
      const updated = await api.patch<AppUser>(`/business/users/${toggleTarget.id}`, {
        is_active: !toggleTarget.is_active,
      });
      setMembers((previous) =>
        previous.map((member) => (member.id === updated.id ? { ...member, ...updated } : member)),
      );
      toast.success(updated.is_active ? 'Team member activated.' : 'Team member deactivated.');
      setToggleTarget(null);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not update the team member.');
    } finally {
      setSaving(false);
    }
  }

  async function changeRole(member: AppUser, role: string) {
    if (member.role === role) return;
    try {
      const updated = await api.patch<AppUser>(`/business/users/${member.id}`, { role });
      setMembers((previous) =>
        previous.map((entry) => (entry.id === member.id ? { ...entry, ...updated } : entry)),
      );
      toast.success(`${member.full_name} is now a ${role}.`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not change the role.');
      await load();
    }
  }

  return (
    <>
      <PageHeader
        title="Staff"
        subtitle="Manage who can use the POS and what they can access"
        actions={
          <Button icon={<UserPlus size={16} />} onClick={() => setModalOpen(true)}>
            Add staff
          </Button>
        }
      />

      <Card className="filter-bar">
        <div className="filter-bar__search">
          <Search size={17} />
          <Input
            value={queryInput}
            onChange={(event) => setQueryInput(event.target.value)}
            placeholder="Search by name, email or phone…"
            aria-label="Search staff"
          />
        </div>
        <span className="muted small">{members.length} team member{members.length === 1 ? '' : 's'}</span>
      </Card>

      <Card padded={false}>
        {loading ? (
          <Loader label="Loading staff…" full />
        ) : visible.length ? (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Contact</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Joined</th>
                  <th className="text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((member) => (
                  <tr key={member.id}>
                    <td>
                      <div className="cell-with-icon">
                        <span className="avatar avatar--sm">{initials(member.full_name)}</span>
                        <strong>{member.full_name}</strong>
                      </div>
                    </td>
                    <td>
                      <strong className="small">{member.email}</strong>
                      <small className="cell-sub">{member.phone || '—'}</small>
                    </td>
                    <td>
                      <Select
                        value={member.role === 'owner' ? 'owner' : 'staff'}
                        aria-label={`Role for ${member.full_name}`}
                        onChange={(event) => void changeRole(member, event.target.value)}
                      >
                        <option value="staff">Staff</option>
                        <option value="owner">Owner</option>
                      </Select>
                    </td>
                    <td>
                      <Badge tone={member.is_active ? 'success' : 'neutral'} dot>
                        {member.is_active ? 'Active' : 'Inactive'}
                      </Badge>
                    </td>
                    <td>{formatDate(member.created_at)}</td>
                    <td>
                      <div className="row-actions row-actions--end">
                        {member.id !== user?.id && (
                          <button
                            type="button"
                            className={`icon-btn ${member.is_active ? 'icon-btn--danger' : 'icon-btn--success'}`}
                            title={member.is_active ? 'Deactivate' : 'Activate'}
                            onClick={() => setToggleTarget(member)}
                          >
                            {member.is_active ? <Trash2 size={15} /> : <RotateCcw size={15} />}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState
            title="No staff members found"
            description={query ? 'Try a different search.' : 'Add a team member to help with billing.'}
            icon={<Users size={24} />}
          />
        )}
      </Card>

      <Card className="staff-info-card">
        <ShieldCheck size={18} />
        <div>
          <strong>Staff accounts are POS-only</strong>
          <p>Staff can bill, collect payments and make limited stock adjustments. Only owners can see analytics, reports and settings.</p>
        </div>
      </Card>

      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title="Add a staff member"
        subtitle="They will be able to sign in to the POS immediately."
        size="md"
        footer={
          <>
            <Button variant="secondary" onClick={() => setModalOpen(false)}>Cancel</Button>
            <Button type="submit" form="staff-create-form" loading={saving}>Add staff</Button>
          </>
        }
      >
        <form id="staff-create-form" onSubmit={createMember} className="form-stack">
          <div className="form-grid form-grid--2">
            <Field label="Full name" required>
              <Input required value={form.full_name}
                onChange={(event) => setForm({ ...form, full_name: event.target.value })} />
            </Field>
            <Field label="Email" required>
              <Input type="email" required value={form.email}
                onChange={(event) => setForm({ ...form, email: event.target.value })} />
            </Field>
          </div>
          <div className="form-grid form-grid--2">
            <Field label="Phone">
              <Input value={form.phone}
                onChange={(event) => setForm({ ...form, phone: event.target.value })} />
            </Field>
            <Field label="Role" required>
              <Select value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value })}>
                <option value="staff">Staff — POS only</option>
                <option value="owner">Owner — full access</option>
              </Select>
            </Field>
          </div>
          <Field label="Temporary password" required hint="At least 8 characters — share it with them securely.">
            <Input type="password" required minLength={8} value={form.password}
              onChange={(event) => setForm({ ...form, password: event.target.value })} />
          </Field>
        </form>
      </Modal>

      <ConfirmDialog
        open={Boolean(toggleTarget)}
        onClose={() => setToggleTarget(null)}
        onConfirm={() => void toggleActive()}
        title={toggleTarget?.is_active ? 'Deactivate this member?' : 'Activate this member?'}
        description={
          toggleTarget?.is_active
            ? `${toggleTarget.full_name} will no longer be able to sign in. You can reactivate them at any time.`
            : `${toggleTarget?.full_name ?? 'This member'} will regain POS access.`
        }
        confirmLabel={toggleTarget?.is_active ? 'Deactivate' : 'Activate'}
        danger={Boolean(toggleTarget?.is_active)}
        loading={saving}
      />
    </>
  );
}
