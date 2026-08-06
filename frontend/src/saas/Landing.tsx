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
import { Button, Typography } from "antd";
import { Link, useNavigate } from "react-router-dom";
import { BRAND, BRAND_DARK } from "../theme";
import PricingCards from "./Pricing";

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
    title: "Fully isolated workspace",
    body: "Every store gets its own subdomain, users, and data — completely private by design.",
  },
];

function LogoMark({ size = 44 }: { size?: number }) {
  return (
    <div
      style={{
        width: size, height: size, borderRadius: size * 0.27,
        background: `linear-gradient(135deg, ${BRAND}, #c2185b)`,
        display: "flex", alignItems: "center", justifyContent: "center",
        boxShadow: "0 4px 14px rgba(157, 23, 77, 0.3)",
      }}
    >
      <ShopOutlined style={{ color: "#fff", fontSize: size * 0.48 }} />
    </div>
  );
}

const NAV_H = 64;

export default function Landing() {
  const navigate = useNavigate();

  return (
    <div style={{ fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif", background: "#fff" }}>
      {/* Nav */}
      <nav
        style={{
          position: "sticky", top: 0, zIndex: 100,
          height: NAV_H, display: "flex", alignItems: "center",
          padding: "0 48px", background: "rgba(255,255,255,0.92)",
          backdropFilter: "blur(12px)", borderBottom: "1px solid rgba(0,0,0,0.06)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10, flex: 1 }}>
          <LogoMark size={34} />
          <span style={{ fontWeight: 800, fontSize: 18, color: "#221019", letterSpacing: -0.3 }}>Velora</span>
        </div>
        <div style={{ display: "flex", gap: 12 }}>
          <Button onClick={() => document.getElementById("pricing")?.scrollIntoView({ behavior: "smooth" })}>
            Pricing
          </Button>
          <Link to="/login"><Button>Sign in</Button></Link>
          <Button type="primary" icon={<RocketOutlined />} onClick={() => navigate("/signup")} style={{ borderRadius: 20 }}>
            Start free trial
          </Button>
        </div>
      </nav>

      {/* Hero */}
      <section
        style={{
          minHeight: "calc(92vh - 64px)",
          background: `linear-gradient(160deg, #fff9fb 0%, #fff 55%, #f0f9f4 100%)`,
          display: "flex", flexDirection: "column",
          alignItems: "center", justifyContent: "center",
          textAlign: "center", padding: "80px 24px 60px",
        }}
      >
        <div
          style={{
            display: "inline-flex", alignItems: "center", gap: 8,
            background: "#fce7f3", borderRadius: 20, padding: "5px 16px",
            marginBottom: 24,
          }}
        >
          <RocketOutlined style={{ color: BRAND, fontSize: 13 }} />
          <Typography.Text style={{ color: BRAND, fontSize: 12.5, fontWeight: 600 }}>
            Fashion retail, reimagined as SaaS
          </Typography.Text>
        </div>

        <Typography.Title
          style={{
            fontSize: "clamp(36px, 5vw, 64px)", lineHeight: 1.1, fontWeight: 900,
            color: "#221019", margin: 0, maxWidth: 720,
          }}
        >
          Run your boutique
          <span style={{ color: BRAND }}> like a flagship.</span>
        </Typography.Title>
        <Typography.Paragraph
          style={{ fontSize: 18, color: "#6b5a62", maxWidth: 560, margin: "20px auto 40px", lineHeight: 1.6 }}
        >
          POS, inventory, CRM, WhatsApp marketing, HR & payroll — all in one calm, connected
          platform. Each store gets its own private workspace, no setup needed.
        </Typography.Paragraph>

        <div style={{ display: "flex", gap: 14, justifyContent: "center", flexWrap: "wrap" }}>
          <Button
            type="primary" size="large" icon={<RocketOutlined />}
            onClick={() => navigate("/signup")}
            style={{ borderRadius: 24, height: 50, padding: "0 32px", fontSize: 16, fontWeight: 600 }}
          >
            Start free — 30 days
          </Button>
          <Button
            size="large"
            onClick={() => document.getElementById("pricing")?.scrollIntoView({ behavior: "smooth" })}
            style={{ borderRadius: 24, height: 50, padding: "0 28px", fontSize: 15 }}
          >
            See pricing
          </Button>
        </div>
        <Typography.Text type="secondary" style={{ marginTop: 14, fontSize: 12.5 }}>
          No credit card · No setup fee · Cancel any time
        </Typography.Text>
      </section>

      {/* Features */}
      <section style={{ background: "#faf8fb", padding: "80px 48px" }}>
        <Typography.Title level={2} style={{ textAlign: "center", marginBottom: 8 }}>
          Everything your store needs
        </Typography.Title>
        <Typography.Paragraph style={{ textAlign: "center", color: "#6b5a62", marginBottom: 52, fontSize: 16 }}>
          Built for fashion retail. Ready for boutiques with one outlet or ten.
        </Typography.Paragraph>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
            gap: 24, maxWidth: 1080, margin: "0 auto",
          }}
        >
          {FEATURES.map((f) => (
            <div
              key={f.title}
              style={{
                background: "#fff", borderRadius: 16, padding: "28px 24px",
                border: "1px solid #f0e8ec",
                boxShadow: "0 2px 10px rgba(0,0,0,0.04)",
              }}
            >
              <div
                style={{
                  width: 44, height: 44, borderRadius: 12,
                  background: `linear-gradient(135deg, ${BRAND}18, ${BRAND}08)`,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  color: BRAND, fontSize: 20, marginBottom: 16,
                }}
              >
                {f.icon}
              </div>
              <Typography.Title level={5} style={{ margin: 0, marginBottom: 6 }}>{f.title}</Typography.Title>
              <Typography.Text type="secondary" style={{ fontSize: 13.5, lineHeight: 1.55 }}>{f.body}</Typography.Text>
            </div>
          ))}
        </div>
      </section>

      {/* White-label highlight */}
      <section
        style={{
          background: `linear-gradient(135deg, ${BRAND_DARK}, ${BRAND})`,
          padding: "72px 48px", textAlign: "center",
        }}
      >
        <CrownOutlined style={{ color: "rgba(255,255,255,0.7)", fontSize: 36, marginBottom: 16 }} />
        <Typography.Title level={2} style={{ color: "#fff", marginBottom: 12 }}>
          Your store. Your brand.
        </Typography.Title>
        <Typography.Paragraph style={{ color: "rgba(255,255,255,0.8)", fontSize: 16, maxWidth: 540, margin: "0 auto 32px" }}>
          Every store gets its own subdomain (<strong style={{ color: "#fff" }}>yourstore.velora.app</strong>), custom theme color, logo, and
          invoice prefix. Your customers only see your brand — never ours.
        </Typography.Paragraph>
        <Button
          size="large" type="default"
          style={{
            borderRadius: 24, height: 48, padding: "0 32px",
            background: "rgba(255,255,255,0.15)", color: "#fff",
            border: "1px solid rgba(255,255,255,0.4)", fontSize: 15,
          }}
          onClick={() => navigate("/signup")}
        >
          Claim your store URL
        </Button>
      </section>

      {/* Pricing */}
      <section id="pricing" style={{ padding: "80px 48px", background: "#fff" }}>
        <Typography.Title level={2} style={{ textAlign: "center", marginBottom: 8 }}>
          Simple, honest pricing
        </Typography.Title>
        <Typography.Paragraph style={{ textAlign: "center", color: "#6b5a62", marginBottom: 52, fontSize: 16 }}>
          Start free for 30 days. No card required. Switch plans any time.
        </Typography.Paragraph>

        <div style={{ maxWidth: 1100, margin: "0 auto" }}>
          <PricingCards
            ctaLabel="Get started"
            onSelect={() => navigate("/signup")}
          />
        </div>

        <Typography.Text type="secondary" style={{ display: "block", textAlign: "center", marginTop: 32, fontSize: 13 }}>
          All prices in Indian Rupees (₹), billed annually.
          Need a custom plan?{" "}
          <a href="mailto:hello@velora.app" style={{ color: BRAND }}>Contact us</a>
        </Typography.Text>
      </section>

      {/* Footer CTA */}
      <section
        style={{ background: "#faf8fb", padding: "64px 48px", textAlign: "center", borderTop: "1px solid #f0e8ec" }}
      >
        <Typography.Title level={3} style={{ marginBottom: 8 }}>
          Ready to get started?
        </Typography.Title>
        <Typography.Paragraph type="secondary" style={{ marginBottom: 28, fontSize: 15 }}>
          Join boutiques already running on Velora. Free for 30 days.
        </Typography.Paragraph>
        <Button
          type="primary" size="large" icon={<RocketOutlined />}
          onClick={() => navigate("/signup")}
          style={{ borderRadius: 24, height: 50, padding: "0 36px", fontSize: 16, fontWeight: 600 }}
        >
          Start your free trial
        </Button>
      </section>

      <footer
        style={{
          background: "#221019", color: "rgba(255,255,255,0.5)",
          padding: "24px 48px", display: "flex",
          justifyContent: "space-between", alignItems: "center",
          flexWrap: "wrap", gap: 12,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <LogoMark size={28} />
          <span style={{ color: "rgba(255,255,255,0.7)", fontWeight: 700 }}>Velora</span>
        </div>
        <span style={{ fontSize: 12 }}>© 2026 Velora. Fashion retail, reimagined.</span>
        <div style={{ display: "flex", gap: 20, fontSize: 12 }}>
          <Link to="/login" style={{ color: "rgba(255,255,255,0.5)" }}>Sign in</Link>
          <Link to="/signup" style={{ color: "rgba(255,255,255,0.5)" }}>Sign up</Link>
        </div>
      </footer>
    </div>
  );
}
