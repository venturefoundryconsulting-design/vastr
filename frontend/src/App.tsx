import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import RequireAuth from "./components/RequireAuth";
import ScrollToTop from "./components/ScrollToTop";
import type { UserRole } from "./api/types";
import { useAuth } from "./context/AuthContext";
import Alterations from "./pages/Alterations";
import Campaigns from "./pages/Campaigns";
import Customers from "./pages/Customers";
import Dashboard from "./pages/Dashboard";
import Discounts from "./pages/Discounts";
import HRM from "./pages/HRM";
import Inventory from "./pages/Inventory";
import Landing from "./saas/Landing";
import LegalPage from "./saas/LegalPage";
import Signup from "./saas/Signup";
import VerifyEmail from "./saas/VerifyEmail";
import Login from "./pages/Login";
import Outlets from "./pages/Outlets";
import Payroll from "./pages/Payroll";
import PurchaseOrderDetail from "./pages/PurchaseOrderDetail";
import PurchaseOrders from "./pages/PurchaseOrders";
import POS from "./pages/POS";
import BomBuilder from "./pages/BomBuilder";
import Boms from "./pages/Boms";
import ProductionOrderDetail from "./pages/ProductionOrderDetail";
import ProductionOrders from "./pages/ProductionOrders";
import Tailors from "./pages/Tailors";
import WorkOrders from "./pages/WorkOrders";
import MyWork from "./pages/MyWork";
import CustomerOrders from "./pages/CustomerOrders";
import CustomerOrderDetail from "./pages/CustomerOrderDetail";
import GoodsReceipts from "./pages/GoodsReceipts";
import Mrp from "./pages/Mrp";
import AiImport from "./pages/AiImport";
import Items from "./pages/Items";
import Units from "./pages/Units";
import Products from "./pages/Products";
import Reports from "./pages/Reports";
import Returns from "./pages/Returns";
import Sales from "./pages/Sales";
import Settings from "./pages/Settings";
import TransferDetail from "./pages/TransferDetail";
import Transfers from "./pages/Transfers";
import Users from "./pages/Users";
import Vendors from "./pages/Vendors";
import RequireSuperAdmin from "./admin/RequireSuperAdmin";
import SuperAdminLayout from "./admin/SuperAdminLayout";
import Activity from "./admin/Activity";
import GlobalSettings from "./admin/GlobalSettings";
import LandingPageSettings from "./admin/LandingPageSettings";
import Overview from "./admin/Overview";
import SubdomainSettings from "./admin/SubdomainSettings";
import Subscriptions from "./admin/Subscriptions";
import TenantDetail from "./admin/TenantDetail";
import TenantsList from "./admin/TenantsList";

function Protected({ children, minRole }: { children: React.ReactNode; minRole?: UserRole }) {
  return (
    <RequireAuth minRole={minRole}>
      <Layout>{children}</Layout>
    </RequireAuth>
  );
}

function PlatformAdmin({ children }: { children: React.ReactNode }) {
  return (
    <RequireSuperAdmin>
      <SuperAdminLayout>{children}</SuperAdminLayout>
    </RequireSuperAdmin>
  );
}

/** Public landing page for guests; already-authenticated visitors skip
 * straight to their dashboard rather than seeing marketing copy again. */
function Root() {
  const { user, loading } = useAuth();
  if (loading) return null;
  return user ? <Navigate to="/dashboard" replace /> : <Landing />;
}

export default function App() {
  return (
    <>
      <ScrollToTop />
      <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route path="/verify-email" element={<VerifyEmail />} />
      <Route path="/terms" element={<LegalPage slug="terms" fallbackTitle="Terms of Service" />} />
      <Route path="/privacy" element={<LegalPage slug="privacy" fallbackTitle="Privacy Policy" />} />
      <Route path="/" element={<Root />} />
      <Route path="/dashboard" element={<Protected><Dashboard /></Protected>} />
      <Route
        path="/platform-admin/overview"
        element={<PlatformAdmin><Overview /></PlatformAdmin>}
      />
      <Route
        path="/platform-admin/tenants"
        element={<PlatformAdmin><TenantsList /></PlatformAdmin>}
      />
      <Route
        path="/platform-admin/tenants/:id"
        element={<PlatformAdmin><TenantDetail /></PlatformAdmin>}
      />
      <Route
        path="/platform-admin/activity"
        element={<PlatformAdmin><Activity /></PlatformAdmin>}
      />
      <Route
        path="/platform-admin/subscriptions"
        element={<PlatformAdmin><Subscriptions /></PlatformAdmin>}
      />
      <Route
        path="/platform-admin/domain"
        element={<PlatformAdmin><SubdomainSettings /></PlatformAdmin>}
      />
      <Route
        path="/platform-admin/landing"
        element={<PlatformAdmin><LandingPageSettings /></PlatformAdmin>}
      />
      <Route
        path="/platform-admin/settings"
        element={<PlatformAdmin><GlobalSettings /></PlatformAdmin>}
      />
      <Route path="/pos" element={<Protected><POS /></Protected>} />
      <Route path="/sales" element={<Protected><Sales /></Protected>} />
      <Route path="/returns" element={<Protected><Returns /></Protected>} />
      <Route path="/alterations" element={<Protected><Alterations /></Protected>} />
      <Route path="/customers" element={<Protected><Customers /></Protected>} />
      <Route path="/campaigns" element={<Protected minRole="manager"><Campaigns /></Protected>} />
      <Route path="/products" element={<Protected><Products /></Protected>} />
      <Route path="/items" element={<Protected><Items /></Protected>} />
      <Route path="/boms" element={<Protected><Boms /></Protected>} />
      <Route path="/boms/:id" element={<Protected><BomBuilder /></Protected>} />
      <Route path="/production" element={<Protected minRole="manager"><ProductionOrders /></Protected>} />
      <Route path="/production/:id" element={<Protected minRole="manager"><ProductionOrderDetail /></Protected>} />
      <Route path="/tailors" element={<Protected minRole="manager"><Tailors /></Protected>} />
      <Route path="/work-orders" element={<Protected minRole="manager"><WorkOrders /></Protected>} />
      <Route path="/my-work" element={<Protected><MyWork /></Protected>} />
      <Route path="/customer-orders" element={<Protected><CustomerOrders /></Protected>} />
      <Route path="/customer-orders/:id" element={<Protected><CustomerOrderDetail /></Protected>} />
      <Route path="/goods-receipts" element={<Protected minRole="manager"><GoodsReceipts /></Protected>} />
      <Route path="/mrp" element={<Protected minRole="manager"><Mrp /></Protected>} />
      <Route path="/ai-import" element={<Protected minRole="manager"><AiImport /></Protected>} />
      <Route path="/units" element={<Protected minRole="manager"><Units /></Protected>} />
      <Route path="/discounts" element={<Protected minRole="manager"><Discounts /></Protected>} />
      <Route path="/inventory" element={<Protected><Inventory /></Protected>} />
      <Route path="/reports" element={<Protected minRole="manager"><Reports /></Protected>} />
      <Route path="/vendors" element={<Protected minRole="manager"><Vendors /></Protected>} />
      <Route
        path="/purchase-orders"
        element={<Protected minRole="manager"><PurchaseOrders /></Protected>}
      />
      <Route
        path="/purchase-orders/:id"
        element={<Protected minRole="manager"><PurchaseOrderDetail /></Protected>}
      />
      <Route path="/transfers" element={<Protected minRole="manager"><Transfers /></Protected>} />
      <Route path="/transfers/:id" element={<Protected minRole="manager"><TransferDetail /></Protected>} />
      <Route path="/hrm" element={<Protected><HRM /></Protected>} />
      <Route path="/payroll" element={<Protected minRole="admin"><Payroll /></Protected>} />
      <Route path="/outlets" element={<Protected minRole="admin"><Outlets /></Protected>} />
      <Route path="/users" element={<Protected minRole="admin"><Users /></Protected>} />
      <Route path="/settings" element={<Protected minRole="admin"><Settings /></Protected>} />
      </Routes>
    </>
  );
}
