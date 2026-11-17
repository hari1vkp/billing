import { useEffect, useState, type FormEvent } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import {
  ArrowRight,
  BarChart3,
  CheckCircle2,
  Eye,
  EyeOff,
  LockKeyhole,
  Mail,
  ReceiptText,
  ShieldCheck,
  Sparkles,
  Wallet,
} from 'lucide-react';
import { homeForRole, useAuth } from '../context/AuthContext';
import { ApiError } from '../api/client';
import { Button, Field, Input } from '../components/UI';
import type { RegisterPayload } from '../types';

export function Login() {
  const { login, register, user, loading: authLoading } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [form, setForm] = useState<RegisterPayload>({
    business_name: '',
    owner_name: '',
    email: '',
    password: '',
    phone: '',
    upi_id: '',
    gstin: '',
  });
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!authLoading && user) navigate(homeForRole(user.role), { replace: true });
  }, [authLoading, user, navigate]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      if (mode === 'login') {
        await login(email.trim(), password);
      } else {
        await register({
          ...form,
          business_name: form.business_name.trim(),
          owner_name: form.owner_name.trim(),
          email: form.email.trim(),
          ...(form.phone?.trim() ? { phone: form.phone.trim() } : {}),
          ...(form.upi_id?.trim() ? { upi_id: form.upi_id.trim() } : {}),
          ...(form.gstin?.trim() ? { gstin: form.gstin.trim() } : {}),
        });
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to sign in. Please try again.');
    } finally {
      setSubmitting(false);
    }
  }

  function fillDemo() {
    setMode('login');
    setEmail('demo@billingapp.com');
    setPassword('Demo@1234');
    setError('');
  }

  if (!authLoading && user) return <Navigate to={homeForRole(user.role)} replace />;

  return (
    <div className="auth-page">
      <section className="auth-brand">
        <div className="auth-brand__glow" aria-hidden="true" />
        <div className="auth-brand__content">
          <div className="auth-logo">
            <span className="brand-mark brand-mark--light">
              <ReceiptText size={22} strokeWidth={1.5} />
            </span>
            <span className="brand-name brand-name--light">BillFlow</span>
          </div>

          <div className="auth-brand__copy">
            <span className="auth-eyebrow">
              <Sparkles size={14} /> All-in-one business billing
            </span>
            <h1>
              Invoice smarter.
              <br />
              Get paid faster.
            </h1>
            <p>
              Billing, customer relationships and real-time analytics — thoughtfully brought
              together in one clean workspace.
            </p>
          </div>

          <div className="auth-features">
            <div className="auth-feature">
              <span className="auth-feature__icon"><ReceiptText size={18} /></span>
              <div>
                <strong>GST-ready invoicing</strong>
                <span>Create professional invoices with tax and UPI QR in seconds.</span>
              </div>
            </div>
            <div className="auth-feature">
              <span className="auth-feature__icon"><Wallet size={18} /></span>
              <div>
                <strong>Payments without the chase</strong>
                <span>Share payment links, collect declarations and reconcile instantly.</span>
              </div>
            </div>
            <div className="auth-feature">
              <span className="auth-feature__icon"><BarChart3 size={18} /></span>
              <div>
                <strong>Clarity at a glance</strong>
                <span>Track sales, collections and outstanding balances as they happen.</span>
              </div>
            </div>
          </div>

          <div className="demo-card">
            <div className="demo-card__head">
              <ShieldCheck size={18} />
              <strong>Explore with the demo account</strong>
            </div>
            <div className="demo-card__body">
              <code>demo@billingapp.com</code>
              <span className="demo-card__dot">·</span>
              <code>Demo@1234</code>
            </div>
            <button type="button" onClick={fillDemo} className="demo-card__button">
              Use demo credentials <ArrowRight size={14} />
            </button>
          </div>
        </div>
        <div className="auth-brand__footer">
          © {new Date().getFullYear()} BillFlow. Built for growing businesses.
        </div>
      </section>

      <section className="auth-form-side">
        <div className="auth-form-wrap">
          <div className="auth-mobile-logo">
            <span className="brand-mark"><ReceiptText size={20} /></span>
            <span className="brand-name">BillFlow</span>
          </div>

          <div className="auth-form-header">
            <h2>{mode === 'login' ? 'Welcome back' : 'Create your workspace'}</h2>
            <p>
              {mode === 'login'
                ? 'Sign in to continue to your dashboard.'
                : 'Start managing billing and payments in minutes.'}
            </p>
          </div>

          <div className="auth-tabs" role="tablist" aria-label="Authentication mode">
            <button
              type="button"
              role="tab"
              aria-selected={mode === 'login'}
              className={mode === 'login' ? 'is-active' : ''}
              onClick={() => {
                setMode('login');
                setError('');
              }}
            >
              Sign in
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === 'register'}
              className={mode === 'register' ? 'is-active' : ''}
              onClick={() => {
                setMode('register');
                setError('');
              }}
            >
              Register
            </button>
          </div>

          {error && (
            <div className="alert alert--error" role="alert">
              <span>{error}</span>
            </div>
          )}

          <form className="auth-form" onSubmit={onSubmit}>
            {mode === 'register' && (
              <>
                <div className="form-grid form-grid--2">
                  <Field label="Business name" required>
                    <Input
                      required
                      value={form.business_name}
                      onChange={(e) => setForm({ ...form, business_name: e.target.value })}
                      placeholder="Acme Traders"
                    />
                  </Field>
                  <Field label="Owner name" required>
                    <Input
                      required
                      value={form.owner_name}
                      onChange={(e) => setForm({ ...form, owner_name: e.target.value })}
                      placeholder="Jane Doe"
                    />
                  </Field>
                </div>
              </>
            )}

            <Field label="Email address" required>
              <div className="input-with-icon">
                <Mail size={16} />
                <Input
                  type="email"
                  required
                  autoComplete="email"
                  value={mode === 'login' ? email : form.email}
                  onChange={(e) =>
                    mode === 'login'
                      ? setEmail(e.target.value)
                      : setForm({ ...form, email: e.target.value })
                  }
                  placeholder="you@company.com"
                />
              </div>
            </Field>

            <Field label="Password" required hint={mode === 'register' ? 'At least 8 characters' : undefined}>
              <div className="input-with-icon input-with-icon--password">
                <LockKeyhole size={16} />
                <Input
                  type={showPassword ? 'text' : 'password'}
                  required
                  minLength={mode === 'register' ? 8 : 1}
                  autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                  value={mode === 'login' ? password : form.password}
                  onChange={(e) =>
                    mode === 'login'
                      ? setPassword(e.target.value)
                      : setForm({ ...form, password: e.target.value })
                  }
                  placeholder="••••••••"
                />
                <button
                  type="button"
                  className="input-toggle"
                  onClick={() => setShowPassword((visible) => !visible)}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                  aria-pressed={showPassword}
                  title={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
                </button>
              </div>
            </Field>

            {mode === 'register' && (
              <div className="form-grid form-grid--2">
                <Field label="Phone">
                  <Input
                    value={form.phone ?? ''}
                    onChange={(e) => setForm({ ...form, phone: e.target.value })}
                    placeholder="+91 98765 43210"
                  />
                </Field>
                <Field label="UPI ID (optional)">
                  <Input
                    value={form.upi_id ?? ''}
                    onChange={(e) => setForm({ ...form, upi_id: e.target.value })}
                    placeholder="business@upi"
                  />
                </Field>
              </div>
            )}

            {mode === 'register' && (
              <Field label="GSTIN (optional)">
                <Input
                  value={form.gstin ?? ''}
                  onChange={(e) => setForm({ ...form, gstin: e.target.value })}
                  placeholder="27AAPFU0939F1ZV"
                />
              </Field>
            )}

            <Button type="submit" size="lg" full loading={submitting} icon={<ArrowRight size={17} />}>
              {mode === 'login' ? 'Sign in to BillFlow' : 'Create account'}
            </Button>
          </form>

          <div className="auth-footnote">
            <CheckCircle2 size={15} /> Secure, private and built for Indian businesses.
          </div>
        </div>
      </section>
    </div>
  );
}
