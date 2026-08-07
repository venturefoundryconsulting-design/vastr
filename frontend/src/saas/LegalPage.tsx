import { useQuery } from "@tanstack/react-query";
import { Typography } from "antd";
import { Link } from "react-router-dom";
import { getPublicLegalPage } from "../api/endpoints";

const FALLBACKS: Record<string, string> = {
  terms: `These Terms of Service govern your use of Vastr ("we", "us", "our") and the boutique retail ERP platform we provide.

1. Your account
You're responsible for keeping your login credentials secure and for all activity under your store's account. Each store's data is isolated from every other store on the platform.

2. Your data
You own the data you put into your store - products, customers, sales records, and everything else. We don't sell it or share it with other tenants. You can export it or request deletion at any time.

3. Subscriptions and billing
Every plan starts with a 30-day free trial. After the trial, continued use of a paid plan requires an active subscription. You can upgrade, downgrade, or cancel at any time from your account settings.

4. Acceptable use
Don't use the platform to store or process anything illegal, to abuse or attack the service, or to resell access without our agreement.

5. Availability
We aim for high uptime but don't guarantee the service will be uninterrupted or error-free. We'll do our best to give notice of planned maintenance.

6. Changes
We may update these terms as the product evolves. Material changes will be communicated to store owners.

This is a template and should be reviewed by qualified legal counsel before being relied upon as a binding agreement.`,
  privacy: `This Privacy Policy explains what information Vastr collects and how it's used.

1. Information we collect
Account details (name, email, store information) you provide at signup, and usage data generated as you use the platform (products, sales, customer records you enter for your own store).

2. How we use it
To operate and improve the platform, to communicate with you about your account (including transactional emails like email verification), and to provide customer support.

3. Data isolation
Every store's data is isolated from every other store. Platform staff access data only as needed for support or to maintain the service.

4. Third parties
We use payment processors (Razorpay) to handle billing and may use email delivery providers to send transactional email. We don't sell your data to advertisers.

5. Your rights
You can request a copy of your data or ask us to delete your account and associated data at any time.

6. Contact
Questions about this policy can be sent to our support email.

This is a template and should be reviewed by qualified legal counsel before being relied upon as a binding policy.`,
};

export default function LegalPage({ slug, fallbackTitle }: { slug: string; fallbackTitle: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["legal-page", slug],
    queryFn: () => getPublicLegalPage(slug).then((r) => r.data).catch(() => null),
  });

  const title = data?.title || fallbackTitle;
  const content = data?.content || FALLBACKS[slug] || "";

  return (
    <div style={{ minHeight: "100vh", background: "#fff" }}>
      <nav
        style={{
          height: 64, display: "flex", alignItems: "center", padding: "0 48px",
          borderBottom: "1px solid rgba(0,0,0,0.06)",
        }}
      >
        <Link to="/" style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <img
            src="/vastr.png"
            alt="Vastr"
            style={{ width: 34, height: 34, borderRadius: 9, objectFit: "contain", boxShadow: "0 4px 14px rgba(157, 23, 77, 0.3)" }}
          />
          <span style={{ fontWeight: 800, fontSize: 17, color: "#221019" }}>Vastr</span>
        </Link>
      </nav>

      <div style={{ maxWidth: 760, margin: "0 auto", padding: "56px 24px 100px" }}>
        {!isLoading && (
          <>
            <Typography.Title level={2} style={{ marginBottom: 32 }}>{title}</Typography.Title>
            {content.split("\n\n").map((para, i) => (
              <Typography.Paragraph key={i} style={{ fontSize: 14.5, lineHeight: 1.75, color: "#4a3d43", whiteSpace: "pre-line" }}>
                {para}
              </Typography.Paragraph>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
