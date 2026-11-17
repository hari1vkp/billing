import { useEffect, useRef, useState } from 'react';
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import {
  ChevronDown,
  LayoutDashboard,
  LogOut,
  Package,
  Plus,
  ReceiptText,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { initials, titleCase } from './UI';

/**
 * The cashier shell — a single, focused top bar with no analytics, reports,
 * settings or management navigation. Managers get a single "Admin" shortcut.
 */
export function StaffLayout() {
  const { user, business, logout } = useAuth();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const isOwner = user?.role === 'owner';

  useEffect(() => {
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

  return (
    <div className="pos-shell">
      <header className="pos-topbar">
        <div className="pos-topbar__left">
          <Link to="/pos" className="pos-brand" aria-label="BillFlow POS home">
            <span className="brand-mark brand-mark--light">
              <ReceiptText size={19} strokeWidth={1.5} />
            </span>
            <span className="pos-brand__name">BillFlow</span>
          </Link>
          <span className="pos-topbar__divider" />
          <span className="pos-topbar__business">{business?.name ?? 'My Business'}</span>
          <span className="pos-topbar__badge">POS</span>
        </div>

        <nav className="pos-topbar__nav" aria-label="POS navigation">
          <Link
            to="/pos"
            className="btn btn--primary btn--md pos-new-bill"
            onClick={() => {
              // Reset an in-progress bill even when we are already on /pos.
              window.dispatchEvent(new Event('billflow:new-bill'));
            }}
          >
            <Plus size={17} /> New Bill
          </Link>
          <NavLink
            to="/pos/stock"
            className={({ isActive }) => `pos-nav-link ${isActive ? 'pos-nav-link--active' : ''}`}
          >
            <Package size={16} /> Stock
          </NavLink>
          {isOwner && (
            <Link to="/admin" className="pos-nav-link">
              <LayoutDashboard size={16} /> Admin
            </Link>
          )}
        </nav>

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
                <span className={`badge badge--${isOwner ? 'info' : 'neutral'}`}>
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
      </header>

      <main className="pos-main">
        <Outlet />
      </main>
    </div>
  );
}
