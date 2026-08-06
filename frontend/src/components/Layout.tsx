import {
  AppstoreOutlined,
  ArrowDownOutlined,
  ArrowUpOutlined,
  BarChartOutlined,
  ContactsOutlined,
  DashboardOutlined,
  LogoutOutlined,
  MenuOutlined,
  PercentageOutlined,
  RollbackOutlined,
  ScissorOutlined,
  SendOutlined,
  SettingOutlined,
  ShopOutlined,
  ShoppingCartOutlined,
  ShoppingOutlined,
  SwapOutlined,
  TeamOutlined,
  TruckOutlined,
  WalletOutlined,
} from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Avatar, Button, Checkbox, Dropdown, Grid, Layout as AntLayout, List, Menu, Modal, Tag, theme } from "antd";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { getPublicBranding } from "../api/endpoints";
import { useAuth } from "../context/AuthContext";
import { BRAND } from "../theme";
import type { UserRole } from "../api/types";
import { hasMinRole } from "../utils/roles";

const { Header, Sider, Content } = AntLayout;
const { useBreakpoint } = Grid;
const NAV_ORDER_KEY = "tanisi_nav_order";

interface NavItem {
  key: string;
  icon: ReactNode;
  label: string;
  /** Lowest role allowed to see this item. Omit for all authenticated roles. */
  minRole?: UserRole;
}

const NAV_GROUPS: { group: string; items: NavItem[] }[] = [
  {
    group: "Overview",
    items: [{ key: "/dashboard", icon: <DashboardOutlined />, label: "Dashboard" }],
  },
  {
    group: "Sales",
    items: [
      { key: "/pos", icon: <ShoppingCartOutlined />, label: "Point of Sale" },
      { key: "/sales", icon: <ShoppingOutlined />, label: "Sales" },
      { key: "/returns", icon: <RollbackOutlined />, label: "Returns & Exchanges" },
      { key: "/alterations", icon: <ScissorOutlined />, label: "Tailor & Alterations" },
    ],
  },
  {
    group: "Catalog",
    items: [
      { key: "/products", icon: <AppstoreOutlined />, label: "Products" },
      { key: "/discounts", icon: <PercentageOutlined />, label: "Discounts & Coupons", minRole: "manager" },
      { key: "/inventory", icon: <AppstoreOutlined />, label: "Inventory" },
    ],
  },
  {
    group: "Customers",
    items: [
      { key: "/customers", icon: <ContactsOutlined />, label: "Customers" },
      { key: "/campaigns", icon: <SendOutlined />, label: "WhatsApp Marketing", minRole: "manager" },
    ],
  },
  {
    group: "Procurement",
    items: [
      { key: "/vendors", icon: <TeamOutlined />, label: "Vendors", minRole: "manager" },
      { key: "/purchase-orders", icon: <TruckOutlined />, label: "Purchase Orders", minRole: "manager" },
      { key: "/transfers", icon: <SwapOutlined />, label: "Stock Transfers", minRole: "manager" },
    ],
  },
  {
    group: "Insights",
    items: [{ key: "/reports", icon: <BarChartOutlined />, label: "Reports", minRole: "manager" }],
  },
  {
    group: "Workforce",
    items: [
      { key: "/hrm", icon: <TeamOutlined />, label: "HR Management" },
      { key: "/payroll", icon: <WalletOutlined />, label: "Payroll", minRole: "admin" },
    ],
  },
  {
    group: "Admin",
    items: [
      { key: "/outlets", icon: <ShopOutlined />, label: "Outlets", minRole: "admin" },
      { key: "/users", icon: <TeamOutlined />, label: "Users", minRole: "admin" },
      { key: "/settings", icon: <SettingOutlined />, label: "Settings", minRole: "admin" },
    ],
  },
];

const ALL_NAV_ITEMS: NavItem[] = NAV_GROUPS.flatMap((g) => g.items);
const DEFAULT_ORDER = ALL_NAV_ITEMS.map((i) => ({ key: i.key, visible: true }));

function loadNavOrder(): { key: string; visible: boolean }[] | null {
  try {
    const raw = localStorage.getItem(NAV_ORDER_KEY);
    if (!raw) return null;
    const saved: { key: string; visible: boolean }[] = JSON.parse(raw);
    const knownKeys = new Set(ALL_NAV_ITEMS.map((i) => i.key));
    const cleaned = saved.filter((s) => knownKeys.has(s.key));
    for (const item of ALL_NAV_ITEMS) {
      if (!cleaned.some((s) => s.key === item.key)) cleaned.push({ key: item.key, visible: true });
    }
    return cleaned;
  } catch {
    return null;
  }
}

function CustomizeMenuModal({
  order,
  onChange,
  onClose,
}: {
  order: { key: string; visible: boolean }[];
  onChange: (o: { key: string; visible: boolean }[] | null) => void;
  onClose: () => void;
}) {
  const labelFor = (key: string) => ALL_NAV_ITEMS.find((i) => i.key === key)?.label ?? key;
  const move = (index: number, dir: -1 | 1) => {
    const next = [...order];
    const target = index + dir;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    onChange(next);
  };

  return (
    <Modal title="Customize menu" open onCancel={onClose} footer={null} width={440}>
      <List
        dataSource={order}
        renderItem={(item, index) => (
          <List.Item
            actions={[
              <Button key="up" size="small" icon={<ArrowUpOutlined />} disabled={index === 0} onClick={() => move(index, -1)} />,
              <Button
                key="down"
                size="small"
                icon={<ArrowDownOutlined />}
                disabled={index === order.length - 1}
                onClick={() => move(index, 1)}
              />,
            ]}
          >
            <Checkbox
              checked={item.visible}
              onChange={(e) => onChange(order.map((o) => (o.key === item.key ? { ...o, visible: e.target.checked } : o)))}
            >
              {labelFor(item.key)}
            </Checkbox>
          </List.Item>
        )}
      />
      <Button style={{ marginTop: 12 }} onClick={() => onChange(null)}>
        Reset to default grouping
      </Button>
    </Modal>
  );
}

export default function Layout({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const screens = useBreakpoint();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [customizeOpen, setCustomizeOpen] = useState(false);
  const [navOrder, setNavOrder] = useState<{ key: string; visible: boolean }[] | null>(loadNavOrder);
  const {
    token: { colorBgContainer },
  } = theme.useToken();
  const { data: branding } = useQuery({
    queryKey: ["public-branding"],
    queryFn: () => getPublicBranding().then((r) => r.data),
  });
  const brandName = branding?.business_name || "Tanisi";

  useEffect(() => {
    if (navOrder) localStorage.setItem(NAV_ORDER_KEY, JSON.stringify(navOrder));
    else localStorage.removeItem(NAV_ORDER_KEY);
  }, [navOrder]);

  const isMobile = !screens.lg;
  const collapsed = isMobile ? !mobileOpen : false;

  const isAllowed = (item: NavItem) => hasMinRole(user?.role, item.minRole);

  const menuItems = navOrder
    ? navOrder
        .filter((o) => o.visible)
        .map((o) => ALL_NAV_ITEMS.find((i) => i.key === o.key))
        .filter((i): i is NavItem => !!i && isAllowed(i))
        .map((i) => ({ key: i.key, icon: i.icon, label: i.label }))
    : NAV_GROUPS.map((g) => ({
        key: g.group,
        type: "group" as const,
        label: g.group,
        children: g.items.filter(isAllowed).map((i) => ({ key: i.key, icon: i.icon, label: i.label })),
      })).filter((g) => g.children.length > 0);

  const currentLabel = ALL_NAV_ITEMS.find((item) => item.key === location.pathname)?.label ?? "";

  return (
    <AntLayout style={{ minHeight: "100vh" }}>
      {isMobile && mobileOpen && (
        <div
          onClick={() => setMobileOpen(false)}
          style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 99 }}
        />
      )}
      <Sider
        collapsedWidth={0}
        collapsed={collapsed}
        trigger={null}
        width={232}
        style={
          isMobile
            ? { background: "#221019", position: "fixed", height: "100vh", insetInlineStart: 0, top: 0, zIndex: 100, display: "flex", flexDirection: "column" }
            : { background: "#221019", display: "flex", flexDirection: "column" }
        }
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            padding: collapsed ? "20px 0" : "20px 20px",
            justifyContent: collapsed ? "center" : "flex-start",
          }}
        >
          {branding?.logo_url ? (
            <img
              src={branding.logo_url}
              alt="Logo"
              style={{ width: 34, height: 34, minWidth: 34, borderRadius: 10, objectFit: "contain", background: "#fff" }}
            />
          ) : (
            <div
              style={{
                width: 34,
                height: 34,
                minWidth: 34,
                borderRadius: 10,
                background: `linear-gradient(135deg, ${BRAND}, #c2185b)`,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                boxShadow: "0 2px 8px rgba(157, 23, 77, 0.45)",
              }}
            >
              <ShopOutlined style={{ color: "#fff", fontSize: 17 }} />
            </div>
          )}
          {!collapsed && (
            <div style={{ lineHeight: 1.1, overflow: "hidden" }}>
              <div style={{ color: "#fff", fontWeight: 700, fontSize: 16, letterSpacing: 0.2 }}>{brandName}</div>
              <div style={{ color: "rgba(255,255,255,0.5)", fontSize: 11, letterSpacing: 1.2 }}>BOUTIQUE ERP</div>
            </div>
          )}
        </div>
        <div style={{ flex: 1, overflowY: "auto" }}>
          <Menu
            theme="dark"
            mode="inline"
            selectedKeys={[location.pathname]}
            items={menuItems}
            onClick={(e) => {
              navigate(e.key);
              if (isMobile) setMobileOpen(false);
            }}
            style={{ background: "transparent", borderInlineEnd: "none" }}
          />
        </div>
        {!collapsed && (
          <div style={{ padding: 12, borderTop: "1px solid rgba(255,255,255,0.08)" }}>
            <Button
              type="text"
              icon={<SettingOutlined />}
              onClick={() => setCustomizeOpen(true)}
              style={{ color: "rgba(255,255,255,0.6)", width: "100%", textAlign: "left" }}
            >
              Customize menu
            </Button>
          </div>
        )}
      </Sider>
      <AntLayout>
        <Header
          style={{
            background: colorBgContainer,
            padding: "0 20px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 12,
            borderBottom: "1px solid #eee3ea",
            position: "sticky",
            top: 0,
            zIndex: 10,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            {isMobile && (
              <MenuOutlined
                style={{ fontSize: 18, cursor: "pointer" }}
                onClick={() => setMobileOpen((o) => !o)}
              />
            )}
            <span style={{ fontWeight: 600, fontSize: 15, color: "#221019" }}>{currentLabel}</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <Tag color="magenta" style={{ borderRadius: 6 }}>
              {user?.role?.replace("_", " ").toUpperCase()}
            </Tag>
            <Dropdown
              menu={{
                items: [{ key: "logout", icon: <LogoutOutlined />, label: "Logout", onClick: logout }],
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
                <Avatar style={{ background: BRAND }}>{user?.name?.[0]?.toUpperCase()}</Avatar>
                {!isMobile && <span>{user?.name}</span>}
              </div>
            </Dropdown>
          </div>
        </Header>
        <Content style={{ margin: isMobile ? 12 : 20 }}>{children}</Content>
      </AntLayout>

      {customizeOpen && (
        <CustomizeMenuModal
          order={navOrder ?? DEFAULT_ORDER}
          onChange={setNavOrder}
          onClose={() => setCustomizeOpen(false)}
        />
      )}
    </AntLayout>
  );
}
