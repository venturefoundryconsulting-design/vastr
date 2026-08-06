import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import RequireAuth from "./components/RequireAuth";
import ScrollToTop from "./components/ScrollToTop";
import type { UserRole } from "./api/types";
import Alterations from "./pages/Alterations";
import Campaigns from "./pages/Campaigns";
import Customers from "./pages/Customers";
import Dashboard from "./pages/Dashboard";
import Discounts from "./pages/Discounts";
import HRM from "./pages/HRM";
import Inventory from "./pages/Inventory";
import Login from "./pages/Login";
import Outlets from "./pages/Outlets";
import Payroll from "./pages/Payroll";
import PurchaseOrderDetail from "./pages/PurchaseOrderDetail";
import PurchaseOrders from "./pages/PurchaseOrders";
import POS from "./pages/POS";
import Products from "./pages/Products";
import Reports from "./pages/Reports";
import Returns from "./pages/Returns";
import Sales from "./pages/Sales";
import Settings from "./pages/Settings";
import TransferDetail from "./pages/TransferDetail";
import Transfers from "./pages/Transfers";
import Users from "./pages/Users";
import Vendors from "./pages/Vendors";

function Protected({ children, minRole }: { children: React.ReactNode; minRole?: UserRole }) {
  return (
    <RequireAuth minRole={minRole}>
      <Layout>{children}</Layout>
    </RequireAuth>
  );
}

export default function App() {
  return (
    <>
      <ScrollToTop />
      <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/" element={<Protected><Dashboard /></Protected>} />
      <Route path="/pos" element={<Protected><POS /></Protected>} />
      <Route path="/sales" element={<Protected><Sales /></Protected>} />
      <Route path="/returns" element={<Protected><Returns /></Protected>} />
      <Route path="/alterations" element={<Protected><Alterations /></Protected>} />
      <Route path="/customers" element={<Protected><Customers /></Protected>} />
      <Route path="/campaigns" element={<Protected minRole="manager"><Campaigns /></Protected>} />
      <Route path="/products" element={<Protected><Products /></Protected>} />
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
