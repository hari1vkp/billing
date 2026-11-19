import { useEffect, useRef, useState, type FormEvent } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import {
  Activity,
  BarChart3,
  Building2,
  ChevronDown,
  CreditCard,
  LayoutDashboard,
  LogOut,
  Menu,
  Package,
  ReceiptText,
  ScanLine,
  Search,
  Settings,
  ShoppingCart,
  Truck,
  UserCog,
  Users,
  X,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { initials, titleCase } from './UI';

const NAV_ITEMS = [
  { to: '/admin', label: 'Overview', icon: LayoutDashboard, end: true },
  { to: '/admin/billing', label: 'Billing', icon: ReceiptText },
  { to: '/admin/inventory', label: 'Inventory', icon: Package },
  { to: '/admin/barcode-stickers', label: 'Barcode Studio', icon: ScanLine },
  { to: '/admin/customers', label: 'Customers', icon: Users },
  { to: '/admin/suppliers', label: 'Suppliers', icon: Truck },
  { to: '/admin/payments', label: 'Payments', icon: CreditCard },
  { to: '/admin/analytics', label: 'Analytics', icon: BarChart3 },
  { to: '/admin/staff', label: 'Staff', icon: UserCog },
  { to: '/admin/activity', label: 'Activity', icon: Activity },
  { to: '/admin/settings', label: 'Settings', icon: Settings },
];

const TITLES: Record<string, { title: string; subtitle: string }> = {
  '/admin': { title: 'Overview', subtitle: 'A snapshot of your business today' },
  '/admin/billing': { title: 'Billing & Invoices', subtitle: 'Create, manage and track every invoice' },
  '/admin/inventory': { title: 'Inventory', subtitle: 'Products, stock levels and movements' },
  '/admin/barcode-stickers': {
    title: 'Barcode Studio',
    subtitle: 'Generate and print barcode stickers for your products',
  },
  '/admin/customers': { title: 'Customers', subtitle: 'Your contacts, history and relationships' },
  '/admin/suppliers': { title: 'Suppliers', subtitle: 'Vendors, their products, reminders and visits' },
  '/admin/payments': { title: 'Payments', subtitle: 'Collections, confirmations and reconciliation' },
  '/admin/analytics': { title: 'Analytics', subtitle: 'Understand performance and spot trends' },
  '/admin/staff': { title: 'Staff', subtitle: 'Manage team access and roles' },
  '/admin/activity': { title: 'Activity log', subtitle: 'A record of everything that happened' },
  '/admin/settings': { title: 'Settings', subtitle: 'Business profile, UPI and team access' },
};

export function Layout() {
  const { user, business, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [search, setSearch] = useState('');
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMobileOpen(false);
    setMenuOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    function onDocClick(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, []);

  const meta = TITLES[location.pathname] ?? {
    title: 'BillFlow',
    subtitle: 'Billing management console',
  };

  function onSearch(event: FormEvent) {
    event.preventDefault();
    const query = search.trim();
    navigate(query ? `/admin/billing?q=${encodeURIComponent(query)}` : '/admin/billing');
  }

  return (
    <div className="app-shell">
      {mobileOpen && (
        <div className="sidebar-backdrop" onClick={() => setMobileOpen(false)} aria-hidden="true" />
      )}
      <aside className={`sidebar ${mobileOpen ? 'sidebar--open' : ''}`}>
        <div className="sidebar__brand">
          <div className="brand-mark">
            <ReceiptText size={20} strokeWidth={2.4} />
          </div>
          <div className="brand-text">
            <span className="brand-name">BillFlow</span>
            <span className="brand-tag">Billing made simple</span>
          </div>
          <button
            type="button"
            className="sidebar__close"
            onClick={() => setMobileOpen(false)}
            aria-label="Close navigation"
          >
            <X size={20} />
          </button>
        </div>

        <div className="sidebar__section-label">WORKSPACE</div>
        <nav className="sidebar__nav" aria-label="Main navigation">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) => `nav-item ${isActive ? 'nav-item--active' : ''}`}
              >
                <Icon size={18} strokeWidth={2} />
                <span>{item.label}</span>
              </NavLink>
            );
          })}
        </nav>

        <div className="sidebar__footer">
          <div className="sidebar-business">
            <span className="sidebar-business__icon">
              <Building2 size={18} />
            </span>
            <div className="sidebar-business__info">
              <strong>{business?.name ?? 'My Business'}</strong>
              <span>{business?.currency ?? 'INR'} · {titleCase(user?.role ?? 'owner')}</span>
            </div>
          </div>
          <div className="sidebar__version">BillFlow v1.0</div>
        </div>
      </aside>

      <div className="main-shell">
        <header className="topbar">
          <div className="topbar__left">
            <button
              type="button"
              className="icon-btn topbar__menu"
              onClick={() => setMobileOpen(true)}
              aria-label="Open navigation"
            >
              <Menu size={21} />
            </button>
            <div className="topbar__titles">
              <h1>{meta.title}</h1>
              <p>{meta.subtitle}</p>
            </div>
          </div>

          <div className="topbar__right">
            <NavLink to="/pos" className="btn btn--primary btn--md open-pos-btn">
              <ShoppingCart size={16} /> Open POS
            </NavLink>
            <form className="topbar-search" onSubmit={onSearch} role="search">
              <Search size={16} />
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search invoices…"
                aria-label="Search invoices"
              />
              <kbd>↵</kbd>
            </form>

            <div className="user-menu" ref={menuRef}>
              <button
                type="button"
                className="user-menu__trigger"
                onClick={() => setMenuOpen((open) => !open)}
                aria-expanded={menuOpen}
              >
                <span className="avatar avatar--sm">{initials(user?.full_name)}</span>
                <span className="user-menu__name">{user?.full_name?.split(' ')[0] ?? 'User'}</span>
                <ChevronDown size={15} className={menuOpen ? 'rotate' : ''} />
              </button>
              {menuOpen && (
                <div className="user-menu__dropdown">
                  <div className="user-menu__identity">
                    <span className="avatar">{initials(user?.full_name)}</span>
                    <div>
                      <strong>{user?.full_name ?? 'User'}</strong>
                      <span>{user?.email}</span>
                    </div>
                  </div>
                  <div className="user-menu__role">
                    <span className={`badge badge--${user?.role === 'owner' ? 'info' : 'neutral'}`}>
                      {titleCase(user?.role ?? 'staff')}
                    </span>
                    <span className="muted">{business?.name}</span>
                  </div>
                  <button type="button" className="user-menu__logout" onClick={() => void logout()}>
                    <LogOut size={16} /> Sign out
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>

        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

/** The admin shell; named alias for clarity in the route tree. */
export const AdminLayout = Layout;
