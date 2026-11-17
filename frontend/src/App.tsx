import type { ReactNode } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { AdminLayout } from './components/Layout';
import { StaffLayout } from './components/StaffLayout';
import { Loader } from './components/UI';
import { homeForRole, useAuth } from './context/AuthContext';
import { Login } from './pages/Login';
import { PublicPayment } from './pages/PublicPayment';
import { Dashboard } from './pages/Dashboard';
import { Billing } from './pages/Billing';
import { Inventory } from './pages/Inventory';
import { Customers } from './pages/Customers';
import { Payments } from './pages/Payments';
import { Analytics } from './pages/Analytics';
import { Staff } from './pages/Staff';
import { Activity } from './pages/Activity';
import { Settings } from './pages/Settings';
import { POS } from './pages/POS';
import { StaffStock } from './pages/StaffStock';

function FullPageLoader() {
  return (
    <div className="app-loading">
      <Loader label="Loading BillFlow…" full />
    </div>
  );
}

function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <FullPageLoader />;
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function OwnerRoute({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  if (user?.role !== 'owner') return <Navigate to="/pos" replace />;
  return <>{children}</>;
}

function RoleRedirect() {
  const { user, loading } = useAuth();
  if (loading) return <FullPageLoader />;
  if (!user) return <Navigate to="/login" replace />;
  return <Navigate to={homeForRole(user.role)} replace />;
}

export default function App() {
  return (
    <Routes>
      {/* Public */}
      <Route path="/login" element={<Login />} />
      <Route path="/pay/:token" element={<PublicPayment />} />
      <Route path="/" element={<RoleRedirect />} />

      {/* Cashier experience */}
      <Route
        element={
          <ProtectedRoute>
            <StaffLayout />
          </ProtectedRoute>
        }
      >
        <Route path="/pos" element={<POS />} />
        <Route path="/pos/stock" element={<StaffStock />} />
      </Route>

      {/* Owner management experience */}
      <Route
        element={
          <ProtectedRoute>
            <OwnerRoute>
              <AdminLayout />
            </OwnerRoute>
          </ProtectedRoute>
        }
      >
        <Route path="/admin" element={<Dashboard />} />
        <Route path="/admin/billing" element={<Billing />} />
        <Route path="/admin/inventory" element={<Inventory />} />
        <Route path="/admin/customers" element={<Customers />} />
        <Route path="/admin/payments" element={<Payments />} />
        <Route path="/admin/analytics" element={<Analytics />} />
        <Route path="/admin/staff" element={<Staff />} />
        <Route path="/admin/activity" element={<Activity />} />
        <Route path="/admin/settings" element={<Settings />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
