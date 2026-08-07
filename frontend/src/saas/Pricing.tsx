import { CheckOutlined, CloseOutlined, MailOutlined } from "@ant-design/icons";
import { Button, Card, Typography } from "antd";

export interface PlanDef {
  key: "starter" | "professional" | "enterprise";
  name: string;
  price: string;
  period: string;
  tagline: string;
  highlight?: boolean;
  trialNote?: string;
  contactSales?: boolean;
  features: { label: string; included: boolean }[];
}

export const PLANS: PlanDef[] = [
  {
    key: "starter",
    name: "Starter",
    price: "₹1,999",
    period: "per year",
    tagline: "Everything a single-store needs",
    trialNote: "30-day free trial - every feature unlocked, no card required",
    features: [
      { label: "Point of Sale", included: true },
      { label: "Inventory & Products", included: true },
      { label: "Customer CRM", included: true },
      { label: "2 outlets, up to 5 users", included: true },
      { label: "Sales Reports", included: true },
      { label: "WhatsApp Marketing", included: false },
      { label: "HR & Payroll", included: false },
      { label: "Multi-outlet", included: false },
    ],
  },
  {
    key: "professional",
    name: "Professional",
    price: "₹4,999",
    period: "per year",
    tagline: "Growing stores with a team",
    highlight: true,
    trialNote: "30-day free trial included",
    features: [
      { label: "Point of Sale", included: true },
      { label: "Inventory & Products", included: true },
      { label: "Customer CRM", included: true },
      { label: "5 outlets, up to 15 users", included: true },
      { label: "Sales Reports & Analytics", included: true },
      { label: "WhatsApp Marketing", included: true },
      { label: "HR & Payroll", included: true },
      { label: "Multi-outlet transfers", included: true },
    ],
  },
  {
    key: "enterprise",
    name: "Enterprise",
    price: "Custom",
    period: "pricing",
    tagline: "Unlimited everything, always",
    contactSales: true,
    features: [
      { label: "Point of Sale", included: true },
      { label: "Inventory & Products", included: true },
      { label: "Customer CRM", included: true },
      { label: "Unlimited outlets & users", included: true },
      { label: "Sales Reports & Analytics", included: true },
      { label: "WhatsApp Marketing", included: true },
      { label: "HR & Payroll", included: true },
      { label: "Priority support", included: true },
    ],
  },
];

const BRAND = "#9d174d";

interface PricingCardsProps {
  selectedPlan?: string;
  onSelect?: (plan: PlanDef) => void;
  onContactSales?: () => void;
  ctaLabel?: string;
  compact?: boolean;
}

export default function PricingCards({
  selectedPlan,
  onSelect,
  onContactSales,
  ctaLabel = "Get started",
  compact = false,
}: PricingCardsProps) {
  const handleContactSales = () => {
    if (onContactSales) onContactSales();
    else window.location.href = "mailto:hello@vastr.space?subject=Enterprise plan enquiry";
  };

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: `repeat(auto-fit, minmax(${compact ? 200 : 240}px, 1fr))`,
        gap: 20,
        width: "100%",
      }}
    >
      {PLANS.map((plan) => {
        const selected = selectedPlan === plan.key;
        return (
          <Card
            key={plan.key}
            onClick={() => (plan.contactSales ? handleContactSales() : onSelect?.(plan))}
            style={{
              borderRadius: 16,
              border: selected
                ? `2px solid ${BRAND}`
                : plan.highlight
                ? `2px solid ${BRAND}33`
                : "1px solid #e8e0e5",
              boxShadow: plan.highlight
                ? "0 8px 32px rgba(157,23,77,0.12)"
                : selected
                ? "0 4px 20px rgba(157,23,77,0.18)"
                : "0 2px 8px rgba(0,0,0,0.06)",
              cursor: onSelect || plan.contactSales ? "pointer" : "default",
              position: "relative",
              transition: "box-shadow 0.2s, border-color 0.2s",
              background: selected ? "#fef6fa" : "#fff",
            }}
            styles={{ body: { padding: compact ? 20 : 28 } }}
          >
            {plan.highlight && (
              <div
                style={{
                  position: "absolute",
                  top: -12,
                  left: "50%",
                  transform: "translateX(-50%)",
                  background: BRAND,
                  color: "#fff",
                  fontSize: 11,
                  fontWeight: 700,
                  letterSpacing: 1,
                  padding: "3px 14px",
                  borderRadius: 20,
                  whiteSpace: "nowrap",
                }}
              >
                MOST POPULAR
              </div>
            )}

            <Typography.Title level={5} style={{ margin: 0, color: plan.highlight ? BRAND : undefined }}>
              {plan.name}
            </Typography.Title>
            <Typography.Text type="secondary" style={{ fontSize: 12, display: "block", marginBottom: 12 }}>
              {plan.tagline}
            </Typography.Text>

            <div style={{ display: "flex", alignItems: "baseline", gap: 4, marginBottom: 4 }}>
              <span style={{ fontSize: compact ? 22 : 30, fontWeight: 800, color: "#221019" }}>{plan.price}</span>
              <span style={{ fontSize: 13, color: "#9c8a92" }}>{plan.period}</span>
            </div>
            {plan.trialNote && (
              <Typography.Text style={{ fontSize: 11, color: BRAND, display: "block", marginBottom: 8 }}>
                {plan.trialNote}
              </Typography.Text>
            )}

            {plan.contactSales ? (
              <Button
                block
                icon={<MailOutlined />}
                style={{ marginBottom: 16, marginTop: 8, borderRadius: 10 }}
                onClick={(e) => {
                  e.stopPropagation();
                  handleContactSales();
                }}
              >
                Contact us
              </Button>
            ) : (
              onSelect && (
                <Button
                  type={plan.highlight || selected ? "primary" : "default"}
                  block
                  style={{ marginBottom: 16, marginTop: 8, borderRadius: 10 }}
                  onClick={(e) => {
                    e.stopPropagation();
                    onSelect(plan);
                  }}
                >
                  {selected ? "Selected" : ctaLabel}
                </Button>
              )
            )}

            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: onSelect || plan.contactSales ? 0 : 16 }}>
              {plan.features.map((f) => (
                <div key={f.label} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  {f.included ? (
                    <CheckOutlined style={{ color: "#16a34a", fontSize: 13, flexShrink: 0 }} />
                  ) : (
                    <CloseOutlined style={{ color: "#d1bcc5", fontSize: 12, flexShrink: 0 }} />
                  )}
                  <Typography.Text
                    style={{ fontSize: 13, color: f.included ? "#221019" : "#9c8a92" }}
                  >
                    {f.label}
                  </Typography.Text>
                </div>
              ))}
            </div>
          </Card>
        );
      })}
    </div>
  );
}
