import {
  BarChartOutlined,
  ContactsOutlined,
  CrownOutlined,
  RocketOutlined,
  SafetyOutlined,
  ShopOutlined,
  ShoppingCartOutlined,
  TeamOutlined,
} from "@ant-design/icons";
import { Button, Card, Col, Row, Typography } from "antd";
import { useNavigate } from "react-router-dom";
import { BRAND, BRAND_DARK } from "../theme";

const FEATURES = [
  {
    icon: <ShoppingCartOutlined />,
    title: "Point of sale",
    body: "Fast, barcode-driven checkout built for busy counters and multi-outlet stores.",
  },
  {
    icon: <ShopOutlined />,
    title: "Inventory & products",
    body: "Variants, stock transfers, purchase orders and reorder alerts, all in one place.",
  },
  {
    icon: <ContactsOutlined />,
    title: "Customers & loyalty",
    body: "Credit, loyalty points, and WhatsApp marketing campaigns that bring people back.",
  },
  {
    icon: <BarChartOutlined />,
    title: "Reports that matter",
    body: "Live sales trends, stock aging, and dead-stock insight without spreadsheets.",
  },
  {
    icon: <TeamOutlined />,
    title: "HR & payroll",
    body: "Attendance, leave, salaries and payslips for every outlet's staff.",
  },
  {
    icon: <SafetyOutlined />,
    title: "Built for multi-tenant",
    body: "Every business gets its own isolated workspace, users, and data - by design.",
  },
];

function LogoMark({ size = 44 }: { size?: number }) {
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
      <CrownOutlined style={{ color: "#fff", fontSize: size * 0.48 }} />
    </div>
  );
}

export default function Landing() {
  const navigate = useNavigate();

  return (
    <div style={{ background: "#fff" }}>
      {/* Hero */}
      <div
        style={{
          position: "relative",
          overflow: "hidden",
          background: `linear-gradient(155deg, ${BRAND_DARK} 0%, ${BRAND} 65%, #c2185b 130%)`,
          padding: "0 24px",
        }}
      >
        <div
          style={{
            position: "absolute",
            top: "-15%",
            right: "-10%",
            width: 480,
            height: 480,
            borderRadius: "50%",
            background: "rgba(255,255,255,0.08)",
            filter: "blur(10px)",
          }}
        />
        <div
          style={{
            position: "absolute",
            inset: 0,
            backgroundImage: "radial-gradient(rgba(255,255,255,0.12) 1.5px, transparent 1.5px)",
            backgroundSize: "28px 28px",
            opacity: 0.5,
          }}
        />

        <div style={{ position: "relative", maxWidth: 1120, margin: "0 auto", padding: "28px 0 96px" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 96 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <LogoMark />
              <span style={{ color: "#fff", fontWeight: 700, fontSize: 22, letterSpacing: 0.3 }}>Velora</span>
            </div>
            <Button ghost size="large" onClick={() => navigate("/login")}>
              Sign in
            </Button>
          </div>

          <Row align="middle" gutter={48}>
            <Col xs={24} lg={14}>
              <Typography.Title level={1} style={{ color: "#fff", fontSize: 48, lineHeight: 1.15, marginBottom: 20 }}>
                Fashion retail, reimagined.
              </Typography.Title>
              <Typography.Paragraph style={{ color: "rgba(255,255,255,0.82)", fontSize: 17, maxWidth: 520, marginBottom: 32 }}>
                Velora is the all-in-one platform for boutique and multi-outlet fashion
                retailers - point of sale, inventory, customers, marketing, and reports,
                built as a calm, connected workspace for your whole team.
              </Typography.Paragraph>
              <div style={{ display: "flex", gap: 12 }}>
                <Button
                  type="primary"
                  size="large"
                  icon={<RocketOutlined />}
                  style={{ background: "#fff", color: BRAND, borderColor: "#fff", fontWeight: 700 }}
                  onClick={() => navigate("/login")}
                >
                  Sign in to your workspace
                </Button>
              </div>
            </Col>
            <Col xs={0} lg={10} />
          </Row>
        </div>
      </div>

      {/* Features */}
      <div style={{ maxWidth: 1120, margin: "0 auto", padding: "72px 24px" }}>
        <Typography.Title level={2} style={{ textAlign: "center", marginBottom: 8 }}>
          Everything your boutique needs
        </Typography.Title>
        <Typography.Paragraph
          type="secondary"
          style={{ textAlign: "center", fontSize: 16, maxWidth: 560, margin: "0 auto 48px" }}
        >
          One platform, one login, every outlet - no more juggling spreadsheets and
          disconnected tools.
        </Typography.Paragraph>
        <Row gutter={[24, 24]}>
          {FEATURES.map((f) => (
            <Col xs={24} sm={12} lg={8} key={f.title}>
              <Card style={{ height: "100%", borderRadius: 16 }} styles={{ body: { padding: 28 } }}>
                <div
                  style={{
                    width: 44,
                    height: 44,
                    borderRadius: 12,
                    background: "#fdf0f5",
                    color: BRAND,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 20,
                    marginBottom: 16,
                  }}
                >
                  {f.icon}
                </div>
                <Typography.Title level={5} style={{ marginBottom: 8 }}>
                  {f.title}
                </Typography.Title>
                <Typography.Text type="secondary">{f.body}</Typography.Text>
              </Card>
            </Col>
          ))}
        </Row>
      </div>

      {/* Footer */}
      <div style={{ borderTop: "1px solid #eee3ea", padding: "28px 24px", textAlign: "center" }}>
        <Typography.Text type="secondary" style={{ fontSize: 13 }}>
          © {new Date().getFullYear()} Velora. Fashion retail, reimagined.
        </Typography.Text>
      </div>
    </div>
  );
}
