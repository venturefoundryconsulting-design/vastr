import {
  ArrowRightOutlined,
  BarChartOutlined,
  CheckCircleFilled,
  CloudUploadOutlined,
  ContactsOutlined,
  CrownOutlined,
  RocketOutlined,
  SafetyOutlined,
  ShopOutlined,
  ShoppingCartOutlined,
  TeamOutlined,
} from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Button, Collapse, Typography } from "antd";
import type { ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getPublicLandingContent } from "../api/endpoints";
import { useAuth } from "../context/AuthContext";
import { BRAND, BRAND_DARK } from "../theme";
import { homeRouteFor } from "../utils/roles";
import PricingCards from "./Pricing";

// Matches the `icon` key stored in LandingContent.features (see the Super
// Admin Landing Page settings editor) - a Super Admin picks from this same
// fixed set rather than entering arbitrary JSX.
const ICON_MAP: Record<string, ReactNode> = {
  "shopping-cart": <ShoppingCartOutlined />,
  shop: <ShopOutlined />,
  contacts: <ContactsOutlined />,
  "bar-chart": <BarChartOutlined />,
  team: <TeamOutlined />,
  safety: <SafetyOutlined />,
};

const DEFAULT_VALUE_STRIP = [
  "Built for multi-outlet fashion retailers",
  "WhatsApp-native customer marketing",
  "Live inventory across every store",
  "Your own white-labeled subdomain",
];

const DEFAULT_FEATURES = [
  {
    icon: "shopping-cart",
    title: "Point of sale",
    body: "Fast, barcode-driven checkout built for busy counters and multi-outlet stores.",
  },
  {
    icon: "shop",
    title: "Inventory & products",
    body: "Variants, stock transfers, purchase orders and reorder alerts, all in one place.",
  },
  {
    icon: "contacts",
    title: "Customers & loyalty",
    body: "Credit, loyalty points, and WhatsApp marketing campaigns that bring people back.",
  },
  {
    icon: "bar-chart",
    title: "Reports that matter",
    body: "Live sales trends, stock aging, and dead-stock insight without spreadsheets.",
  },
  {
    icon: "team",
    title: "HR & payroll",
    body: "Attendance, leave, salaries and payslips for every outlet's staff.",
  },
  {
    icon: "safety",
    title: "Fully isolated workspace",
    body: "Every store gets its own subdomain, users, and data — completely private by design.",
  },
];

const DEFAULT_STEPS = [
  {
    title: "Create your store",
    body: "Pick a store name and URL, add your details — takes under two minutes, no card required.",
  },
  {
    title: "Set up your catalog",
    body: "Import products in bulk, add variants and stock, invite your team to their outlets.",
  },
  {
    title: "Start selling",
    body: "Ring up sales at the counter, track inventory live, and message customers on WhatsApp.",
  },
];

const DEFAULT_FAQS = [
  {
    q: "Do I need a credit card to start the free trial?",
    a: "No. Every plan starts with a 30-day free trial with full feature access, and you're never asked for a card unless you choose to add one for after the trial.",
  },
  {
    q: "What happens when my trial ends?",
    a: "You'll be prompted to pick a plan and continue. If you don't, your store stays intact but read-only until you're ready — nothing is deleted.",
  },
  {
    q: "Can I change plans later?",
    a: "Yes, upgrade or downgrade any time from Settings. Changes apply immediately and billing is prorated.",
  },
  {
    q: "Is my store's data separated from other stores?",
    a: "Completely. Every store runs in its own isolated workspace with its own users, data, and subdomain — no other store can ever see it.",
  },
  {
    q: "Can I bring my own domain?",
    a: "Your store gets a free yourstore.vastr.space subdomain at signup. Custom domain support is on our roadmap — reach out and we'll help you get set up.",
  },
];

function LogoMark({ size = 44 }: { size?: number }) {
  return (
    <img
      src="/vastr.png"
      alt="Vastr"
      style={{ width: size, height: size, borderRadius: size * 0.27, objectFit: "contain", boxShadow: "0 4px 14px rgba(157, 23, 77, 0.3)" }}
    />
  );
}

const NAV_H = 64;

export default function Landing() {
  const navigate = useNavigate();
  const { user } = useAuth();
  // Super Admin-editable via Landing Page settings (see admin/LandingPageSettings.tsx);
  // any blank/empty field here just falls back to the hardcoded defaults above,
  // so the page always renders something complete even before it's configured.
  const { data: cms } = useQuery({
    queryKey: ["landing-content"],
    queryFn: () => getPublicLandingContent().then((r) => r.data),
    retry: false,
  });

  const heroEyebrow = cms?.hero_eyebrow || "Fashion retail, reimagined as SaaS";
  const heroLine1 = cms?.hero_title_line1 || "Run your boutique";
  const heroHighlight = cms?.hero_title_highlight || "like a flagship.";
  const heroSubtitle =
    cms?.hero_subtitle ||
    "POS, inventory, CRM, WhatsApp marketing, HR & payroll — all in one calm, connected " +
      "platform. Each store gets its own private workspace, live in minutes.";
  const ctaPrimary = cms?.hero_cta_primary || "Start free — 30 days";
  const ctaSecondary = cms?.hero_cta_secondary || "See pricing";
  const valueStrip = cms?.value_strip?.length ? cms.value_strip : DEFAULT_VALUE_STRIP;
  const features = cms?.features?.length ? cms.features : DEFAULT_FEATURES;
  const steps = cms?.how_it_works?.length ? cms.how_it_works : DEFAULT_STEPS;
  const faqs = cms?.faqs?.length ? cms.faqs : DEFAULT_FAQS;

  return (
    <div style={{ fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif", background: "#fff" }}>
      <style>{`
        @media (max-width: 900px) {
          .vastr-nav-link { display: none; }
          .vastr-hero { background-position: 78% center !important; padding-top: 100px !important; padding-bottom: 260px !important; }
          .vastr-hero-overlay { background: linear-gradient(180deg, rgba(10,8,20,0.82) 0%, rgba(10,8,20,0.6) 55%, rgba(10,8,20,0.88) 100%) !important; }
        }
        @media (max-width: 640px) {
          .vastr-section { padding-left: 20px !important; padding-right: 20px !important; }
          .vastr-nav { padding-left: 20px !important; padding-right: 20px !important; }
          .vastr-hero-title { font-size: 34px !important; }
        }
      `}</style>
      {/* Nav */}
      <nav
        className="vastr-nav"
        style={{
          position: "sticky", top: 0, zIndex: 100,
          height: NAV_H, display: "flex", alignItems: "center",
          padding: "0 48px", background: "rgba(255,255,255,0.92)",
          backdropFilter: "blur(12px)", borderBottom: "1px solid rgba(0,0,0,0.06)",
        }}
      >
        <div
          style={{ display: "flex", alignItems: "center", gap: 10, flex: 1, cursor: "pointer" }}
          onClick={() => navigate(homeRouteFor(user?.role))}
        >
          <LogoMark size={34} />
          <span style={{ fontWeight: 800, fontSize: 18, color: "#221019", letterSpacing: -0.3 }}>Vastr</span>
        </div>
        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <Button className="vastr-nav-link" onClick={() => document.getElementById("how")?.scrollIntoView({ behavior: "smooth" })}>
            How it works
          </Button>
          <Button className="vastr-nav-link" onClick={() => document.getElementById("pricing")?.scrollIntoView({ behavior: "smooth" })}>
            Pricing
          </Button>
          <Link to="/login"><Button>Sign in</Button></Link>
          <Button type="primary" icon={<RocketOutlined />} onClick={() => navigate("/signup")} style={{ borderRadius: 20 }}>
            Start free trial
          </Button>
        </div>
      </nav>

      {/* Hero — real product screenshot as a full-bleed dark banner */}
      <section
        className="vastr-section vastr-hero"
        style={{
          position: "relative",
          backgroundImage: "url(/hero-banner.png)",
          backgroundSize: "cover",
          backgroundPosition: "right center",
          backgroundColor: "#0c0a14",
          padding: "150px 48px 170px",
          overflow: "hidden",
        }}
      >
        <div
          className="vastr-hero-overlay"
          style={{
            position: "absolute", inset: 0,
            background: "linear-gradient(90deg, rgba(10,8,20,0.92) 0%, rgba(12,10,22,0.78) 32%, rgba(12,10,22,0.35) 55%, rgba(12,10,22,0.05) 75%)",
          }}
        />
        <div style={{ position: "relative", maxWidth: 1180, margin: "0 auto" }}>
          <div style={{ maxWidth: 560 }}>
            <div
              style={{
                display: "inline-flex", alignItems: "center", gap: 8,
                background: "rgba(255,255,255,0.1)", border: "1px solid rgba(255,255,255,0.18)",
                borderRadius: 20, padding: "5px 16px", marginBottom: 24,
                backdropFilter: "blur(6px)",
              }}
            >
              <RocketOutlined style={{ color: "#f9a8d4", fontSize: 13 }} />
              <Typography.Text style={{ color: "#f9d4e4", fontSize: 12.5, fontWeight: 600 }}>
                {heroEyebrow}
              </Typography.Text>
            </div>

            <Typography.Title
              className="vastr-hero-title"
              style={{
                fontSize: "clamp(34px, 4.2vw, 54px)", lineHeight: 1.1, fontWeight: 900,
                color: "#fff", margin: 0,
              }}
            >
              {heroLine1}
              <br />
              <span style={{ color: "#f472b6" }}>{heroHighlight}</span>
            </Typography.Title>
            <Typography.Paragraph
              style={{ fontSize: 17, color: "rgba(255,255,255,0.78)", maxWidth: 480, margin: "20px 0 32px", lineHeight: 1.65 }}
            >
              {heroSubtitle}
            </Typography.Paragraph>

            <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginBottom: 28 }}>
              <Button
                type="primary" size="large" icon={<RocketOutlined />}
                onClick={() => navigate("/signup")}
                style={{ borderRadius: 24, height: 50, padding: "0 32px", fontSize: 16, fontWeight: 600 }}
              >
                {ctaPrimary}
              </Button>
              <Button
                size="large"
                onClick={() => document.getElementById("pricing")?.scrollIntoView({ behavior: "smooth" })}
                style={{
                  borderRadius: 24, height: 50, padding: "0 28px", fontSize: 15,
                  background: "rgba(255,255,255,0.08)", color: "#fff",
                  border: "1px solid rgba(255,255,255,0.35)",
                }}
              >
                {ctaSecondary}
              </Button>
            </div>

            <div style={{ display: "flex", gap: 22, flexWrap: "wrap" }}>
              {["No credit card", "No setup fee", "Cancel any time"].map((t) => (
                <div key={t} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <CheckCircleFilled style={{ color: "#4ade80", fontSize: 13 }} />
                  <Typography.Text style={{ fontSize: 13, color: "rgba(255,255,255,0.72)" }}>{t}</Typography.Text>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Value strip */}
      <section className="vastr-section" style={{ background: "#221019", padding: "18px 48px" }}>
        <div
          style={{
            maxWidth: 1180, margin: "0 auto", display: "flex", justifyContent: "space-around",
            flexWrap: "wrap", gap: 16,
          }}
        >
          {valueStrip.map((t) => (
            <Typography.Text key={t} style={{ color: "rgba(255,255,255,0.75)", fontSize: 12.5, fontWeight: 500 }}>
              {t}
            </Typography.Text>
          ))}
        </div>
      </section>

      {/* Features */}
      <section className="vastr-section" style={{ background: "#faf8fb", padding: "88px 48px" }}>
        <Typography.Title level={2} style={{ textAlign: "center", marginBottom: 8 }}>
          Everything your store needs
        </Typography.Title>
        <Typography.Paragraph style={{ textAlign: "center", color: "#6b5a62", marginBottom: 56, fontSize: 16 }}>
          Built for fashion retail. Ready for boutiques with one outlet or ten.
        </Typography.Paragraph>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
            gap: 24, maxWidth: 1080, margin: "0 auto",
          }}
        >
          {features.map((f) => (
            <div
              key={f.title}
              style={{
                background: "#fff", borderRadius: 16, padding: "28px 24px",
                border: "1px solid #f0e8ec",
                boxShadow: "0 2px 10px rgba(0,0,0,0.04)",
                transition: "transform 0.18s, box-shadow 0.18s",
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
                {ICON_MAP[f.icon] || <ShopOutlined />}
              </div>
              <Typography.Title level={5} style={{ margin: 0, marginBottom: 6 }}>{f.title}</Typography.Title>
              <Typography.Text type="secondary" style={{ fontSize: 13.5, lineHeight: 1.55 }}>{f.body}</Typography.Text>
            </div>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section id="how" className="vastr-section" style={{ padding: "88px 48px", background: "#fff" }}>
        <Typography.Title level={2} style={{ textAlign: "center", marginBottom: 8 }}>
          Live in three steps
        </Typography.Title>
        <Typography.Paragraph style={{ textAlign: "center", color: "#6b5a62", marginBottom: 56, fontSize: 16 }}>
          No sales calls, no onboarding calls required. Most stores are ringing up sales the same day.
        </Typography.Paragraph>

        <div
          style={{
            display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
            gap: 32, maxWidth: 1000, margin: "0 auto", position: "relative",
          }}
        >
          {steps.map((s, i) => (
            <div key={s.title} style={{ position: "relative" }}>
              <div
                style={{
                  fontSize: 42, fontWeight: 900, color: "transparent",
                  WebkitTextStroke: `1.5px ${BRAND}55`, marginBottom: 8, lineHeight: 1,
                }}
              >
                {String(i + 1).padStart(2, "0")}
              </div>
              <Typography.Title level={5} style={{ margin: 0, marginBottom: 8 }}>{s.title}</Typography.Title>
              <Typography.Text type="secondary" style={{ fontSize: 13.5, lineHeight: 1.6 }}>{s.body}</Typography.Text>
            </div>
          ))}
        </div>

        <div style={{ textAlign: "center", marginTop: 48 }}>
          <Button
            type="primary" size="large" icon={<ArrowRightOutlined />} iconPosition="end"
            onClick={() => navigate("/signup")}
            style={{ borderRadius: 24, height: 48, padding: "0 30px", fontSize: 15 }}
          >
            Create your store
          </Button>
        </div>
      </section>

      {/* White-label highlight */}
      <section
        className="vastr-section"
        style={{
          background: `linear-gradient(135deg, ${BRAND_DARK}, ${BRAND})`,
          padding: "76px 48px", textAlign: "center",
        }}
      >
        <CrownOutlined style={{ color: "rgba(255,255,255,0.7)", fontSize: 36, marginBottom: 16 }} />
        <Typography.Title level={2} style={{ color: "#fff", marginBottom: 12 }}>
          Your store. Your brand.
        </Typography.Title>
        <Typography.Paragraph style={{ color: "rgba(255,255,255,0.8)", fontSize: 16, maxWidth: 540, margin: "0 auto 32px" }}>
          Every store gets its own subdomain (<strong style={{ color: "#fff" }}>yourstore.vastr.space</strong>), custom theme color, logo, and
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
      <section id="pricing" className="vastr-section" style={{ padding: "88px 48px", background: "#fff" }}>
        <Typography.Title level={2} style={{ textAlign: "center", marginBottom: 8 }}>
          Simple, honest pricing
        </Typography.Title>
        <Typography.Paragraph style={{ textAlign: "center", color: "#6b5a62", marginBottom: 56, fontSize: 16 }}>
          Start free for 30 days on any plan. No card required. Switch plans any time.
        </Typography.Paragraph>

        <div style={{ maxWidth: 1000, margin: "0 auto" }}>
          <PricingCards
            ctaLabel="Get started"
            onSelect={() => navigate("/signup")}
          />
        </div>

        <Typography.Text type="secondary" style={{ display: "block", textAlign: "center", marginTop: 32, fontSize: 13 }}>
          All prices in Indian Rupees (₹), billed annually.
          Need a custom plan?{" "}
          <a href="mailto:hello@vastr.space" style={{ color: BRAND }}>Contact us</a>
        </Typography.Text>
      </section>

      {/* FAQ */}
      <section className="vastr-section" style={{ padding: "88px 48px", background: "#faf8fb" }}>
        <Typography.Title level={2} style={{ textAlign: "center", marginBottom: 8 }}>
          Frequently asked questions
        </Typography.Title>
        <Typography.Paragraph style={{ textAlign: "center", color: "#6b5a62", marginBottom: 44, fontSize: 16 }}>
          Can't find what you're after?{" "}
          <a href="mailto:hello@vastr.space" style={{ color: BRAND }}>Ask us directly</a>.
        </Typography.Paragraph>

        <div style={{ maxWidth: 760, margin: "0 auto" }}>
          <Collapse
            bordered={false}
            style={{ background: "transparent" }}
            items={faqs.map((f, i) => ({
              key: String(i),
              label: <span style={{ fontWeight: 600, fontSize: 14.5 }}>{f.q}</span>,
              children: <Typography.Text type="secondary" style={{ fontSize: 13.5, lineHeight: 1.6 }}>{f.a}</Typography.Text>,
              style: { marginBottom: 12, background: "#fff", borderRadius: 12, border: "1px solid #f0e8ec", overflow: "hidden" },
            }))}
          />
        </div>
      </section>

      {/* Footer CTA */}
      <section
        className="vastr-section"
        style={{ background: "#fff", padding: "72px 48px", textAlign: "center", borderTop: "1px solid #f0e8ec" }}
      >
        <CloudUploadOutlined style={{ fontSize: 30, color: BRAND, marginBottom: 14 }} />
        <Typography.Title level={3} style={{ marginBottom: 8 }}>
          Ready to get started?
        </Typography.Title>
        <Typography.Paragraph type="secondary" style={{ marginBottom: 28, fontSize: 15 }}>
          Join boutiques already running on Vastr. Free for 30 days, on any plan.
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
          <span style={{ color: "rgba(255,255,255,0.7)", fontWeight: 700 }}>Vastr</span>
        </div>
        <span style={{ fontSize: 12 }}>© 2026 Vastr. Fashion retail, reimagined.</span>
        <div style={{ display: "flex", gap: 20, fontSize: 12 }}>
          <Link to="/terms" style={{ color: "rgba(255,255,255,0.5)" }}>Terms</Link>
          <Link to="/privacy" style={{ color: "rgba(255,255,255,0.5)" }}>Privacy</Link>
          <Link to="/login" style={{ color: "rgba(255,255,255,0.5)" }}>Sign in</Link>
          <Link to="/signup" style={{ color: "rgba(255,255,255,0.5)" }}>Sign up</Link>
        </div>
      </footer>
    </div>
  );
}
