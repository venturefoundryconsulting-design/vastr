import {
  CreditCardOutlined,
  CrownOutlined,
  DashboardOutlined,
  FileTextOutlined,
  GlobalOutlined,
  HistoryOutlined,
  LogoutOutlined,
  SettingOutlined,
  ShopOutlined,
} from "@ant-design/icons";
import { Avatar, Dropdown, Layout as AntLayout, Menu } from "antd";
import type { ReactNode } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

const { Header, Sider, Content } = AntLayout;

// Deliberately a different accent (deep indigo) from the tenant app's magenta
// brand (see ../theme.ts) - a visual cue that this is the Vastr platform
// shell, not a tenant's own branded workspace, since a Super Admin operator
// could plausibly have both open in different tabs.
const PLATFORM_INK = "#1e1b3a";
const PLATFORM_ACCENT = "#4c1d95";

const NAV_ITEMS = [
  { key: "/platform-admin/overview", icon: <DashboardOutlined />, label: "Overview" },
  { key: "/platform-admin/tenants", icon: <ShopOutlined />, label: "Fashion Brands" },
  { key: "/platform-admin/subscriptions", icon: <CreditCardOutlined />, label: "Subscriptions" },
  { key: "/platform-admin/domain", icon: <GlobalOutlined />, label: "Sub-domain Config" },
  { key: "/platform-admin/landing", icon: <FileTextOutlined />, label: "Landing Page" },
  { key: "/platform-admin/activity", icon: <HistoryOutlined />, label: "Activity" },
  { key: "/platform-admin/settings", icon: <SettingOutlined />, label: "Global Settings" },
];

export default function SuperAdminLayout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const selectedKey =
    NAV_ITEMS.find((item) => location.pathname.startsWith(item.key))?.key ?? location.pathname;

  return (
    <AntLayout style={{ minHeight: "100vh" }}>
      <Sider width={232} style={{ background: PLATFORM_INK, display: "flex", flexDirection: "column" }}>
        <div
          style={{ display: "flex", alignItems: "center", gap: 10, padding: "20px 20px", cursor: "pointer" }}
          onClick={() => navigate("/platform-admin/overview")}
        >
          <div
            style={{
              width: 34,
              height: 34,
              minWidth: 34,
              borderRadius: 10,
              background: `linear-gradient(135deg, ${PLATFORM_ACCENT}, #7c3aed)`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: "0 2px 8px rgba(76, 29, 149, 0.45)",
            }}
          >
            <CrownOutlined style={{ color: "#fff", fontSize: 17 }} />
          </div>
          <div style={{ lineHeight: 1.1 }}>
            <div style={{ color: "#fff", fontWeight: 700, fontSize: 16, letterSpacing: 0.2 }}>Vastr</div>
            <div style={{ color: "rgba(255,255,255,0.5)", fontSize: 11, letterSpacing: 1.2 }}>PLATFORM ADMIN</div>
          </div>
        </div>
        <div style={{ flex: 1 }}>
          <Menu
            theme="dark"
            mode="inline"
            selectedKeys={[selectedKey]}
            items={NAV_ITEMS}
            onClick={(e) => navigate(e.key)}
            style={{ background: "transparent", borderInlineEnd: "none" }}
          />
        </div>
      </Sider>
      <AntLayout>
        <Header
          style={{
            background: "#fff",
            padding: "0 20px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            borderBottom: "1px solid #e5e3ee",
            position: "sticky",
            top: 0,
            zIndex: 10,
          }}
        >
          <span style={{ fontWeight: 600, fontSize: 15, color: PLATFORM_INK }}>Super Admin</span>
          <Dropdown
            menu={{ items: [{ key: "logout", icon: <LogoutOutlined />, label: "Logout", onClick: logout }] }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
              <Avatar style={{ background: PLATFORM_ACCENT }}>{user?.name?.[0]?.toUpperCase()}</Avatar>
              <span>{user?.name}</span>
            </div>
          </Dropdown>
        </Header>
        <Content style={{ margin: 20 }}>{children}</Content>
      </AntLayout>
    </AntLayout>
  );
}
