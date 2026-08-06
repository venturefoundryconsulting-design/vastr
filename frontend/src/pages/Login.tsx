import {
  AppstoreOutlined,
  BarChartOutlined,
  ContactsOutlined,
  CrownOutlined,
  ShopOutlined,
  ShoppingCartOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Button, Card, Col, Divider, Form, Input, Row, Typography, message } from "antd";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { getPublicBranding } from "../api/endpoints";
import { useAuth } from "../context/AuthContext";
import { BRAND, BRAND_DARK } from "../theme";

const DEMO_ACCOUNTS = {
  admin: { email: "admin@tanisi.demo.com", password: "admin123" },
  staff: { email: "staff@tanisi.demo.com", password: "staff123" },
};

const FEATURES = [
  { icon: <ShoppingCartOutlined />, label: "Fast, barcode-driven point of sale" },
  { icon: <AppstoreOutlined />, label: "Products, variants & multi-outlet inventory" },
  { icon: <ContactsOutlined />, label: "Customer loyalty, credit & WhatsApp marketing" },
  { icon: <BarChartOutlined />, label: "Live sales trends & business reports" },
];

function LogoMark({ size = 52, logoUrl }: { size?: number; logoUrl?: string | null }) {
  if (logoUrl) {
    return (
      <img
        src={logoUrl}
        alt="Logo"
        style={{
          width: size,
          height: size,
          minWidth: size,
          borderRadius: size * 0.27,
          objectFit: "contain",
          background: "#fff",
          boxShadow: "0 6px 18px rgba(157, 23, 77, 0.35)",
        }}
      />
    );
  }
  return (
    <div
      style={{
        width: size,
        height: size,
        minWidth: size,
        borderRadius: size * 0.27,
        background: `linear-gradient(135deg, ${BRAND}, #c2185b)`,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        boxShadow: "0 6px 18px rgba(157, 23, 77, 0.35)",
      }}
    >
      <ShopOutlined style={{ color: "#fff", fontSize: size * 0.5 }} />
    </div>
  );
}

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [quickRole, setQuickRole] = useState<"admin" | "staff" | null>(null);
  const { data: branding } = useQuery({
    queryKey: ["public-branding"],
    queryFn: () => getPublicBranding().then((r) => r.data),
  });
  const brandName = branding?.business_name || "Tanisi";

  const doLogin = async (email: string, password: string) => {
    setLoading(true);
    try {
      await login(email, password);
      navigate("/");
    } catch {
      message.error("Invalid email or password");
    } finally {
      setLoading(false);
      setQuickRole(null);
    }
  };

  const quickLogin = (role: "admin" | "staff") => {
    const creds = DEMO_ACCOUNTS[role];
    form.setFieldsValue(creds);
    setQuickRole(role);
    doLogin(creds.email, creds.password);
  };

  return (
    <Row style={{ minHeight: "100vh" }}>
      {/* Left: branding panel - hidden below the lg breakpoint, form takes full width there */}
      <Col
        xs={0}
        lg={13}
        style={{
          position: "relative",
          minHeight: "100vh",
          background: `linear-gradient(155deg, ${BRAND_DARK} 0%, ${BRAND} 65%, #c2185b 130%)`,
          overflow: "hidden",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          padding: "0 72px",
        }}
      >
        {/* Decorative blurred shapes - abstract, brand-colored, no external image dependency */}
        <div
          style={{
            position: "absolute",
            top: "-12%",
            right: "-8%",
            width: 420,
            height: 420,
            borderRadius: "50%",
            background: "rgba(255,255,255,0.08)",
            filter: "blur(10px)",
          }}
        />
        <div
          style={{
            position: "absolute",
            bottom: "-15%",
            left: "-10%",
            width: 480,
            height: 480,
            borderRadius: "50%",
            background: "rgba(0,0,0,0.12)",
            filter: "blur(20px)",
          }}
        />
        <div
          style={{
            position: "absolute",
            inset: 0,
            backgroundImage: "radial-gradient(rgba(255,255,255,0.14) 1.5px, transparent 1.5px)",
            backgroundSize: "28px 28px",
            opacity: 0.5,
          }}
        />

        <div style={{ position: "relative", zIndex: 1 }}>
          <div className="login-animate login-animate-1" style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 40 }}>
            <LogoMark logoUrl={branding?.logo_url} />
            <div>
              <div style={{ color: "#fff", fontWeight: 700, fontSize: 22, letterSpacing: 0.2 }}>{brandName}</div>
              <div style={{ color: "rgba(255,255,255,0.65)", fontSize: 12, letterSpacing: 1.6 }}>
                BOUTIQUE ERP
              </div>
            </div>
          </div>

          <Typography.Title
            level={1}
            className="login-animate login-animate-2"
            style={{ color: "#fff", fontSize: 40, lineHeight: 1.2, marginBottom: 16, maxWidth: 460 }}
          >
            Run your boutique like a flagship store.
          </Typography.Title>
          <Typography.Paragraph
            className="login-animate login-animate-2"
            style={{ color: "rgba(255,255,255,0.78)", fontSize: 16, maxWidth: 420, marginBottom: 40 }}
          >
            Inventory, sales, customers and marketing - in one calm, connected platform
            built for multi-outlet fashion retail.
          </Typography.Paragraph>

          <div className="login-animate login-animate-3" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {FEATURES.map((f) => (
              <div key={f.label} style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <div
                  style={{
                    width: 32,
                    height: 32,
                    minWidth: 32,
                    borderRadius: 9,
                    background: "rgba(255,255,255,0.14)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    color: "#fff",
                    fontSize: 15,
                  }}
                >
                  {f.icon}
                </div>
                <Typography.Text style={{ color: "rgba(255,255,255,0.88)", fontSize: 14.5 }}>
                  {f.label}
                </Typography.Text>
              </div>
            ))}
          </div>
        </div>
      </Col>

      {/* Right: login card */}
      <Col
        xs={24}
        lg={11}
        style={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: 24,
          background: "#f7f5f8",
        }}
      >
        <Card
          className="login-animate login-animate-card"
          style={{ width: 400, maxWidth: "100%", borderRadius: 20, border: "none" }}
          styles={{ body: { padding: "40px 36px" } }}
        >
          <div style={{ display: "flex", justifyContent: "center", marginBottom: 16 }}>
            <LogoMark size={56} logoUrl={branding?.logo_url} />
          </div>
          <Typography.Title level={3} style={{ textAlign: "center", marginBottom: 4 }}>
            Welcome back
          </Typography.Title>
          <Typography.Text type="secondary" style={{ display: "block", textAlign: "center", marginBottom: 28 }}>
            Sign in to continue to {brandName} ERP
          </Typography.Text>

          <div style={{ display: "flex", gap: 10, marginBottom: 20 }}>
            <Button
              block
              icon={<CrownOutlined />}
              loading={loading && quickRole === "admin"}
              disabled={loading && quickRole !== "admin"}
              onClick={() => quickLogin("admin")}
            >
              Super Admin
            </Button>
            <Button
              block
              icon={<UserOutlined />}
              loading={loading && quickRole === "staff"}
              disabled={loading && quickRole !== "staff"}
              onClick={() => quickLogin("staff")}
            >
              Staff
            </Button>
          </div>
          <Divider style={{ margin: "4px 0 24px", fontSize: 12, color: "#9a8b93" }}>or sign in manually</Divider>

          <Form form={form} layout="vertical" onFinish={(values) => doLogin(values.email, values.password)}>
            <Form.Item name="email" label="Email" rules={[{ required: true, type: "email" }]}>
              <Input placeholder="you@tanisi.demo.com" autoFocus />
            </Form.Item>
            <Form.Item name="password" label="Password" rules={[{ required: true }]}>
              <Input.Password placeholder="••••••••" />
            </Form.Item>
            <Form.Item style={{ marginBottom: 12 }}>
              <Button
                type="primary"
                htmlType="submit"
                block
                loading={loading && !quickRole}
                disabled={loading && !!quickRole}
                size="large"
              >
                Sign in
              </Button>
            </Form.Item>
          </Form>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Demo — Admin: admin@tanisi.demo.com / admin123 · Staff: staff@tanisi.demo.com / staff123
          </Typography.Text>
        </Card>
      </Col>
    </Row>
  );
}
