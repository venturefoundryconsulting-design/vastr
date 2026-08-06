import { CheckCircleFilled, ShopOutlined } from "@ant-design/icons";
import { useMutation } from "@tanstack/react-query";
import {
  Button, Card, Col, Form, Input, Row, Steps, Typography, message,
} from "antd";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { checkSlug, registerStore } from "../api/endpoints";
import { useAuth } from "../context/AuthContext";
import { BRAND, BRAND_DARK } from "../theme";
import PricingCards, { type PlanDef, PLANS } from "./Pricing";

const STEPS = ["Store details", "Choose a plan", "You're in!"];

function slugify(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9 -]/g, "")
    .trim()
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .slice(0, 40);
}

export default function Signup() {
  const navigate = useNavigate();
  const { setToken } = useAuth();
  const [step, setStep] = useState(0);
  const [form] = Form.useForm();
  const [selectedPlan, setSelectedPlan] = useState<PlanDef>(PLANS[0]);
  const [slugStatus, setSlugStatus] = useState<"idle" | "checking" | "ok" | "taken">("idle");

  const registerMutation = useMutation({
    mutationFn: registerStore,
    onSuccess: (res) => {
      setToken(res.data.access_token);
      setStep(2);
    },
    onError: (err: any) => {
      const detail = err?.response?.data?.detail || "Registration failed";
      message.error(detail);
    },
  });

  const checkSlugAvailability = async (slug: string) => {
    if (!slug || slug.length < 3) return;
    setSlugStatus("checking");
    try {
      const res = await checkSlug(slug);
      setSlugStatus(res.data.available ? "ok" : "taken");
    } catch {
      setSlugStatus("idle");
    }
  };

  const handleStoreNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const generated = slugify(e.target.value);
    form.setFieldValue("slug", generated);
    setSlugStatus("idle");
    if (generated.length >= 3) checkSlugAvailability(generated);
  };

  const handleSlugChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "");
    form.setFieldValue("slug", v);
    setSlugStatus("idle");
    if (v.length >= 3) checkSlugAvailability(v);
  };

  const goToPlanStep = async () => {
    try {
      await form.validateFields(["company_name", "slug", "owner_name", "email", "password"]);
      if (slugStatus === "taken") { message.error("That store URL is already taken"); return; }
      if (slugStatus === "idle") {
        const slug = form.getFieldValue("slug");
        await checkSlugAvailability(slug);
        const current = await checkSlug(slug);
        if (!current.data.available) { message.error("That store URL is already taken"); return; }
      }
      setStep(1);
    } catch {
      // form validation errors shown inline
    }
  };

  const submit = () => {
    const values = form.getFieldsValue();
    registerMutation.mutate({
      company_name: values.company_name,
      slug: values.slug,
      owner_name: values.owner_name,
      email: values.email,
      password: values.password,
      plan: selectedPlan.key,
    });
  };

  return (
    <Row style={{ minHeight: "100vh" }}>
      {/* Left branding panel */}
      <Col
        xs={0}
        lg={10}
        style={{
          background: `linear-gradient(155deg, ${BRAND_DARK} 0%, ${BRAND} 65%, #c2185b 130%)`,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          padding: "0 56px",
          position: "relative",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            position: "absolute", top: "-10%", right: "-8%", width: 360, height: 360,
            borderRadius: "50%", background: "rgba(255,255,255,0.07)", filter: "blur(10px)",
          }}
        />
        <div
          style={{
            position: "absolute", bottom: "-15%", left: "-8%", width: 420, height: 420,
            borderRadius: "50%", background: "rgba(0,0,0,0.10)", filter: "blur(18px)",
          }}
        />
        <div
          style={{
            position: "absolute", inset: 0,
            backgroundImage: "radial-gradient(rgba(255,255,255,0.12) 1.5px, transparent 1.5px)",
            backgroundSize: "28px 28px", opacity: 0.5,
          }}
        />
        <div style={{ position: "relative", zIndex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 40 }}>
            <div
              style={{
                width: 44, height: 44, borderRadius: 13,
                background: "rgba(255,255,255,0.18)",
                display: "flex", alignItems: "center", justifyContent: "center",
              }}
            >
              <ShopOutlined style={{ color: "#fff", fontSize: 22 }} />
            </div>
            <div>
              <div style={{ color: "#fff", fontWeight: 700, fontSize: 20 }}>Velora</div>
              <div style={{ color: "rgba(255,255,255,0.6)", fontSize: 11, letterSpacing: 1.5 }}>FASHION ERP</div>
            </div>
          </div>
          <Typography.Title level={2} style={{ color: "#fff", margin: 0, lineHeight: 1.25 }}>
            Your store, your rules.
          </Typography.Title>
          <Typography.Paragraph style={{ color: "rgba(255,255,255,0.75)", fontSize: 15, marginTop: 14, maxWidth: 360 }}>
            Set up your boutique ERP in minutes. Inventory, sales, customers and
            marketing — all in one white-labeled workspace that's yours alone.
          </Typography.Paragraph>
          <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 32 }}>
            {[
              "Your own subdomain — yourstore.velora.app",
              "Isolated data — no other store can see yours",
              "30-day free trial, no credit card needed",
              "Upgrade or cancel any time",
            ].map((t) => (
              <div key={t} style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                <CheckCircleFilled style={{ color: "rgba(255,255,255,0.7)", marginTop: 2, flexShrink: 0 }} />
                <Typography.Text style={{ color: "rgba(255,255,255,0.85)", fontSize: 14 }}>{t}</Typography.Text>
              </div>
            ))}
          </div>
        </div>
      </Col>

      {/* Right: form */}
      <Col
        xs={24}
        lg={14}
        style={{
          minHeight: "100vh", display: "flex", alignItems: "center",
          justifyContent: "center", padding: "40px 24px", background: "#f7f5f8",
        }}
      >
        <div style={{ width: "100%", maxWidth: step === 1 ? 900 : 480 }}>
          <Steps
            current={step}
            size="small"
            items={STEPS.map((t) => ({ title: t }))}
            style={{ marginBottom: 32 }}
          />

          {step === 0 && (
            <Card style={{ borderRadius: 20, border: "none" }} styles={{ body: { padding: "36px 36px" } }}>
              <Typography.Title level={4} style={{ marginBottom: 4 }}>Create your store</Typography.Title>
              <Typography.Text type="secondary" style={{ display: "block", marginBottom: 24 }}>
                Start your 30-day free trial — no credit card required.
              </Typography.Text>

              <Form form={form} layout="vertical">
                <Form.Item
                  name="company_name"
                  label="Store name"
                  rules={[{ required: true, message: "Enter your store name" }]}
                >
                  <Input
                    size="large"
                    placeholder="e.g. Priya Boutique"
                    onChange={handleStoreNameChange}
                  />
                </Form.Item>

                <Form.Item
                  name="slug"
                  label="Store URL"
                  rules={[
                    { required: true, message: "Choose a store URL" },
                    { pattern: /^[a-z0-9][a-z0-9-]{1,38}[a-z0-9]$/, message: "Use lowercase letters, numbers and hyphens (min 3 chars)" },
                  ]}
                  validateStatus={slugStatus === "taken" ? "error" : slugStatus === "ok" ? "success" : undefined}
                  help={
                    slugStatus === "taken" ? "Already taken — try another" :
                    slugStatus === "ok" ? "Available!" :
                    slugStatus === "checking" ? "Checking…" : undefined
                  }
                >
                  <Input
                    size="large"
                    prefix={<span style={{ color: "#9c8a92", fontSize: 12, marginRight: 2 }}>velora.app/</span>}
                    placeholder="yourstore"
                    onChange={handleSlugChange}
                  />
                </Form.Item>

                <Row gutter={12}>
                  <Col span={12}>
                    <Form.Item
                      name="owner_name"
                      label="Your name"
                      rules={[{ required: true, message: "Enter your name" }]}
                    >
                      <Input size="large" placeholder="Priya Sharma" />
                    </Form.Item>
                  </Col>
                  <Col span={12}>
                    <Form.Item
                      name="email"
                      label="Email"
                      rules={[{ required: true, type: "email", message: "Enter a valid email" }]}
                    >
                      <Input size="large" placeholder="priya@example.com" />
                    </Form.Item>
                  </Col>
                </Row>

                <Form.Item
                  name="password"
                  label="Password"
                  rules={[{ required: true, min: 8, message: "At least 8 characters" }]}
                >
                  <Input.Password size="large" placeholder="At least 8 characters" />
                </Form.Item>

                <Button
                  type="primary"
                  size="large"
                  block
                  style={{ borderRadius: 10, height: 46, marginTop: 4 }}
                  onClick={goToPlanStep}
                >
                  Continue — Choose a plan
                </Button>
              </Form>

              <Typography.Text type="secondary" style={{ display: "block", textAlign: "center", marginTop: 16, fontSize: 13 }}>
                Already have a store?{" "}
                <Link to="/login" style={{ color: BRAND }}>Sign in</Link>
              </Typography.Text>
            </Card>
          )}

          {step === 1 && (
            <div>
              <Typography.Title level={4} style={{ textAlign: "center", marginBottom: 6 }}>
                Choose your plan
              </Typography.Title>
              <Typography.Text type="secondary" style={{ display: "block", textAlign: "center", marginBottom: 24 }}>
                All plans start with a 30-day free trial. You can upgrade any time.
              </Typography.Text>

              <PricingCards
                selectedPlan={selectedPlan.key}
                onSelect={setSelectedPlan}
                ctaLabel="Select"
              />

              <div style={{ display: "flex", gap: 12, marginTop: 28, justifyContent: "center" }}>
                <Button size="large" onClick={() => setStep(0)} style={{ borderRadius: 10, minWidth: 120 }}>
                  Back
                </Button>
                <Button
                  type="primary"
                  size="large"
                  loading={registerMutation.isPending}
                  style={{ borderRadius: 10, minWidth: 200 }}
                  onClick={submit}
                >
                  Start free trial with {selectedPlan.name}
                </Button>
              </div>
            </div>
          )}

          {step === 2 && (
            <Card style={{ borderRadius: 20, border: "none", textAlign: "center" }} styles={{ body: { padding: "56px 36px" } }}>
              <CheckCircleFilled style={{ fontSize: 64, color: "#16a34a", marginBottom: 20 }} />
              <Typography.Title level={3} style={{ marginBottom: 8 }}>
                Your store is ready!
              </Typography.Title>
              <Typography.Text type="secondary" style={{ fontSize: 15, display: "block", marginBottom: 32 }}>
                You're on the{" "}
                <strong>{selectedPlan.name}</strong> plan with a{" "}
                <strong>30-day free trial</strong>. No credit card needed.
              </Typography.Text>
              <Button
                type="primary"
                size="large"
                style={{ borderRadius: 10, minWidth: 200 }}
                onClick={() => navigate("/dashboard")}
              >
                Go to my dashboard
              </Button>
            </Card>
          )}
        </div>
      </Col>
    </Row>
  );
}
