import { useEffect, useState, type FormEvent } from 'react';
import {
  KeyRound,
  LockKeyhole,
  Save,
  ShieldCheck,
  Trash2,
  UserPlus,
  Users,
} from 'lucide-react';
import { api } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../components/UI';
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
  Select,
  Textarea,
  formatDate,
  initials,
  titleCase,
} from '../components/UI';
import type { AppUser, Business, BusinessUpdate, MessageResponse } from '../types';

export function Settings() {
  const { user, business, setBusiness } = useAuth();
  const toast = useToast();
  const isOwner = user?.role === 'owner';
  const [form, setForm] = useState<BusinessUpdate>({});
  const [saving, setSaving] = useState(false);
  const [users, setUsers] = useState<AppUser[]>([]);
  const [usersLoading, setUsersLoading] = useState(false);
  const [userModal, setUserModal] = useState(false);
  const [userForm, setUserForm] = useState({
    full_name: '', email: '', phone: '', password: '', role: 'staff',
  });
  const [savingUser, setSavingUser] = useState(false);
  const [removeTarget, setRemoveTarget] = useState<AppUser | null>(null);
  const [removing, setRemoving] = useState(false);
  const [passwordForm, setPasswordForm] = useState({ current: '', next: '', confirm: '' });
  const [changingPassword, setChangingPassword] = useState(false);

  useEffect(() => {
    if (business) {
      setForm({
        name: business.name ?? '',
        legal_name: business.legal_name ?? '',
        email: business.email ?? '',
        phone: business.phone ?? '',
        address: business.address ?? '',
        city: business.city ?? '',
        state: business.state ?? '',
        pincode: business.pincode ?? '',
        gstin: business.gstin ?? '',
        upi_id: business.upi_id ?? '',
        upi_name: business.upi_name ?? '',
        currency: business.currency ?? 'INR',
        invoice_prefix: business.invoice_prefix ?? '',
        invoice_footer: business.invoice_footer ?? '',
        default_gst_rate: business.default_gst_rate ?? 18,
        low_stock_threshold: business.low_stock_threshold ?? 10,
      });
    }
  }, [business]);

  const loadUsers = async () => {
    if (!isOwner) return;
    setUsersLoading(true);
    try {
      setUsers(await api.get<AppUser[]>('/business/users'));
    } catch {
      // Owner-only endpoint; ignore errors (shown as empty state).
    } finally {
      setUsersLoading(false);
    }
  };

  useEffect(() => {
    void loadUsers();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOwner]);

  function set(field: keyof BusinessUpdate, value: string | number) {
    setForm((prev) => ({ ...prev, [field]: value }));
  }

  async function saveBusiness(event: FormEvent) {
    event.preventDefault();
    if (!form.name?.trim()) {
      toast.error('Business name is required.');
      return;
    }
    setSaving(true);
    try {
      const updated = await api.patch<Business>('/business', {
        ...form,
        name: form.name.trim(),
        email: form.email?.trim() || undefined,
        gstin: form.gstin?.trim() || undefined,
        upi_id: form.upi_id?.trim() || undefined,
      });
      setBusiness(updated);
      toast.success('Business settings saved successfully.');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not save settings.');
    } finally {
      setSaving(false);
    }
  }

  async function createUser(event: FormEvent) {
    event.preventDefault();
    setSavingUser(true);
    try {
      const created = await api.post<AppUser>('/business/users', {
        ...userForm,
        full_name: userForm.full_name.trim(),
        email: userForm.email.trim(),
        phone: userForm.phone.trim() || undefined,
      });
      setUsers((prev) => [...prev, created]);
      setUserModal(false);
      setUserForm({ full_name: '', email: '', phone: '', password: '', role: 'staff' });
      toast.success('Team member added successfully.');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not add team member.');
    } finally {
      setSavingUser(false);
    }
  }

  async function removeUser() {
    if (!removeTarget) return;
    setRemoving(true);
    try {
      await api.delete<MessageResponse>(`/business/users/${removeTarget.id}`);
      setUsers((prev) => prev.map((entry) =>
        entry.id === removeTarget.id ? { ...entry, is_active: false } : entry));
      toast.success('Team member deactivated.');
      setRemoveTarget(null);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not deactivate team member.');
    } finally {
      setRemoving(false);
    }
  }

  async function changePassword(event: FormEvent) {
    event.preventDefault();
    if (passwordForm.next !== passwordForm.confirm) {
      toast.error('New passwords do not match.');
      return;
    }
    setChangingPassword(true);
    try {
      const result = await api.post<MessageResponse>('/auth/change-password', {
        current_password: passwordForm.current,
        new_password: passwordForm.next,
      });
      toast.success(result.message || 'Password changed successfully.');
      setPasswordForm({ current: '', next: '', confirm: '' });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not change password.');
    } finally {
      setChangingPassword(false);
    }
  }

  if (!business) {
    return (
      <>
        <PageHeader title="Settings" />
        <Card><Loader label="Loading settings…" full /></Card>
      </>
    );
  }

  return (
    <>
      <PageHeader title="Settings" subtitle="Manage your business profile, payments and team" />

      {!isOwner && (
        <div className="alert alert--info">
          Only the business owner can change settings and manage team members. You can still view the current configuration.
        </div>
      )}

      <form onSubmit={saveBusiness}>
        <div className="grid-12">
          <div className="col-7">
            <Card>
              <CardHeader title="Business profile" subtitle="Details printed on your invoices" />
              <div className="form-stack">
                <div className="form-grid form-grid--2">
                  <Field label="Business name" required>
                    <Input required disabled={!isOwner} value={form.name ?? ''}
                      onChange={(e) => set('name', e.target.value)} />
                  </Field>
                  <Field label="Legal name">
                    <Input disabled={!isOwner} value={form.legal_name ?? ''}
                      onChange={(e) => set('legal_name', e.target.value)} />
                  </Field>
                </div>
                <div className="form-grid form-grid--2">
                  <Field label="Email">
                    <Input type="email" disabled={!isOwner} value={form.email ?? ''}
                      onChange={(e) => set('email', e.target.value)} />
                  </Field>
                  <Field label="Phone">
                    <Input disabled={!isOwner} value={form.phone ?? ''}
                      onChange={(e) => set('phone', e.target.value)} />
                  </Field>
                </div>
                <Field label="Address">
                  <Textarea rows={2} disabled={!isOwner} value={form.address ?? ''}
                    onChange={(e) => set('address', e.target.value)} />
                </Field>
                <div className="form-grid form-grid--3">
                  <Field label="City">
                    <Input disabled={!isOwner} value={form.city ?? ''} onChange={(e) => set('city', e.target.value)} />
                  </Field>
                  <Field label="State">
                    <Input disabled={!isOwner} value={form.state ?? ''} onChange={(e) => set('state', e.target.value)} />
                  </Field>
                  <Field label="Pincode">
                    <Input disabled={!isOwner} value={form.pincode ?? ''} onChange={(e) => set('pincode', e.target.value)} />
                  </Field>
                </div>
                <Field label="GSTIN">
                  <Input disabled={!isOwner} value={form.gstin ?? ''} placeholder="27AAPFU0939F1ZV"
                    onChange={(e) => set('gstin', e.target.value)} />
                </Field>
              </div>
            </Card>
          </div>

          <div className="col-5">
            <Card>
              <CardHeader title="Invoice & UPI settings" subtitle="Configure payments and defaults" />
              <div className="form-stack">
                <div className="form-grid form-grid--2">
                  <Field label="Currency">
                    <Select disabled={!isOwner} value={form.currency ?? 'INR'}
                      onChange={(e) => set('currency', e.target.value)}>
                      <option value="INR">INR — ₹</option>
                      <option value="USD">USD — $</option>
                      <option value="AED">AED — د.إ</option>
                      <option value="GBP">GBP — £</option>
                    </Select>
                  </Field>
                  <Field label="Invoice prefix">
                    <Input disabled={!isOwner} value={form.invoice_prefix ?? ''}
                      onChange={(e) => set('invoice_prefix', e.target.value)} />
                  </Field>
                </div>
                <div className="form-grid form-grid--2">
                  <Field label="Default GST (%)">
                    <Input type="number" min="0" max="100" step="0.01" disabled={!isOwner}
                      value={form.default_gst_rate ?? 18}
                      onChange={(e) => set('default_gst_rate', Number(e.target.value))} />
                  </Field>
                  <Field label="Low stock threshold">
                    <Input type="number" min="0" step="1" disabled={!isOwner}
                      value={form.low_stock_threshold ?? 10}
                      onChange={(e) => set('low_stock_threshold', Number(e.target.value))} />
                  </Field>
                </div>
                <Field label="UPI ID / VPA" hint="Used to generate QR codes and payment links.">
                  <Input disabled={!isOwner} value={form.upi_id ?? ''} placeholder="business@upi"
                    onChange={(e) => set('upi_id', e.target.value)} />
                </Field>
                <Field label="UPI display name">
                  <Input disabled={!isOwner} value={form.upi_name ?? ''} placeholder="Your business name"
                    onChange={(e) => set('upi_name', e.target.value)} />
                </Field>
                <Field label="Invoice footer">
                  <Textarea rows={3} disabled={!isOwner} value={form.invoice_footer ?? ''}
                    placeholder="Thank you for your business…"
                    onChange={(e) => set('invoice_footer', e.target.value)} />
                </Field>
              </div>
            </Card>
          </div>
        </div>

        <div className="save-bar">
          <div className="save-bar__info">
            <ShieldCheck size={17} />
            <span>Settings apply to all new invoices on this workspace.</span>
          </div>
          {isOwner && (
            <Button type="submit" icon={<Save size={16} />} loading={saving}>Save changes</Button>
          )}
        </div>
      </form>

      <Card>
        <CardHeader
          title="Team members"
          subtitle="Manage who has access to this workspace"
          action={isOwner ? (
            <Button size="sm" icon={<UserPlus size={15} />} onClick={() => setUserModal(true)}>
              Add user
            </Button>
          ) : undefined}
        />
        {usersLoading ? (
          <Loader label="Loading team members…" />
        ) : users.length ? (
          <div className="table-scroll">
            <table className="data-table data-table--compact">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Joined</th>
                  <th aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {users.map((member) => (
                  <tr key={member.id}>
                    <td>
                      <div className="cell-with-icon">
                        <span className="avatar avatar--sm">{initials(member.full_name)}</span>
                        <strong>{member.full_name}</strong>
                      </div>
                    </td>
                    <td>{member.email}</td>
                    <td><Badge tone={member.role === 'owner' ? 'info' : 'neutral'}>{titleCase(member.role)}</Badge></td>
                    <td><Badge tone={member.is_active ? 'success' : 'neutral'} dot>{member.is_active ? 'Active' : 'Inactive'}</Badge></td>
                    <td>{formatDate(member.created_at)}</td>
                    <td>
                      {isOwner && member.id !== user?.id && member.is_active && (
                        <button type="button" className="icon-btn icon-btn--danger" title="Deactivate user"
                          onClick={() => setRemoveTarget(member)}>
                          <Trash2 size={15} />
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState title={isOwner ? 'No team members yet' : 'Team list unavailable'}
            description={isOwner ? 'Add a teammate to share the workload.' : 'Ask an owner for access.'}
            icon={<Users size={22} />} />
        )}
      </Card>

      <Card className="password-card">
        <CardHeader title="Change password" subtitle="Keep your account secure" />
        <form onSubmit={changePassword} className="form-stack form-stack--narrow">
          <Field label="Current password" required>
            <div className="input-with-icon">
              <LockKeyhole size={16} />
              <Input type="password" required value={passwordForm.current}
                onChange={(e) => setPasswordForm({ ...passwordForm, current: e.target.value })} />
            </div>
          </Field>
          <div className="form-grid form-grid--2">
            <Field label="New password" required hint="At least 8 characters">
              <Input type="password" required minLength={8} value={passwordForm.next}
                onChange={(e) => setPasswordForm({ ...passwordForm, next: e.target.value })} />
            </Field>
            <Field label="Confirm new password" required>
              <Input type="password" required minLength={8} value={passwordForm.confirm}
                onChange={(e) => setPasswordForm({ ...passwordForm, confirm: e.target.value })} />
            </Field>
          </div>
          <div>
            <Button type="submit" variant="secondary" icon={<KeyRound size={15} />}
              loading={changingPassword}>
              Update password
            </Button>
          </div>
        </form>
      </Card>

      <Modal
        open={userModal}
        onClose={() => setUserModal(false)}
        title="Add a team member"
        subtitle="They will receive access to this workspace."
        size="md"
        footer={
          <>
            <Button variant="secondary" onClick={() => setUserModal(false)}>Cancel</Button>
            <Button type="submit" form="add-user-form" loading={savingUser}>Add user</Button>
          </>
        }
      >
        <form id="add-user-form" onSubmit={createUser} className="form-stack">
          <div className="form-grid form-grid--2">
            <Field label="Full name" required>
              <Input required value={userForm.full_name}
                onChange={(e) => setUserForm({ ...userForm, full_name: e.target.value })} />
            </Field>
            <Field label="Email" required>
              <Input type="email" required value={userForm.email}
                onChange={(e) => setUserForm({ ...userForm, email: e.target.value })} />
            </Field>
          </div>
          <div className="form-grid form-grid--2">
            <Field label="Phone">
              <Input value={userForm.phone}
                onChange={(e) => setUserForm({ ...userForm, phone: e.target.value })} />
            </Field>
            <Field label="Role" required>
              <Select value={userForm.role} onChange={(e) => setUserForm({ ...userForm, role: e.target.value })}>
                <option value="staff">Staff</option>
                <option value="owner">Owner</option>
              </Select>
            </Field>
          </div>
          <Field label="Temporary password" required hint="At least 8 characters — share it with them securely.">
            <Input type="password" required minLength={8} value={userForm.password}
              onChange={(e) => setUserForm({ ...userForm, password: e.target.value })} />
          </Field>
        </form>
      </Modal>

      <ConfirmDialog
        open={Boolean(removeTarget)}
        onClose={() => setRemoveTarget(null)}
        onConfirm={() => void removeUser()}
        title="Deactivate this user?"
        description={`${removeTarget?.full_name ?? 'This user'} will lose access to the workspace. You can reactivate them later in the database.`}
        confirmLabel="Deactivate user"
        danger
        loading={removing}
      />
    </>
  );
}
