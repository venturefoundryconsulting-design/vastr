import { CheckCircleFilled, CloseCircleFilled } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert, Button, Card, Form, Input, InputNumber, Space, Switch, Tabs, Tag, Tooltip, Typography, message,
} from "antd";
import { useState } from "react";
import {
  getPlatformEmailConfig,
  getPlatformPaymentConfig,
  getPlatformWebsiteConfig,
  testPlatformEmailConfig,
  testPlatformPaymentConfig,
  updatePlatformEmailConfig,
  updatePlatformPaymentConfig,
  updatePlatformWebsiteConfig,
} from "../api/endpoints";

function StatusTags({ configured, testStatus, testError, testAt }: {
  configured: boolean; testStatus?: string | null; testError?: string | null; testAt?: string | null;
}) {
  return (
    <Space size={4}>
      {configured ? <Tag color="green">Configured</Tag> : <Tag>Not set up</Tag>}
      {testStatus === "success" && (
        <Tooltip title={testAt ? `Last tested ${new Date(testAt).toLocaleString()}` : undefined}>
          <Tag icon={<CheckCircleFilled />} color="success">Test passed</Tag>
        </Tooltip>
      )}
      {testStatus === "failed" && (
        <Tooltip title={testError || "Last test failed"}>
          <Tag icon={<CloseCircleFilled />} color="error">Test failed</Tag>
        </Tooltip>
      )}
    </Space>
  );
}

function PaymentGatewayTab() {
  const queryClient = useQueryClient();
  const [form] = Form.useForm();
  const { data, isLoading } = useQuery({
    queryKey: ["platform-payment-config"],
    queryFn: () => getPlatformPaymentConfig().then((r) => r.data),
  });

  const saveMutation = useMutation({
    mutationFn: updatePlatformPaymentConfig,
    onSuccess: () => {
      message.success("Payment gateway settings saved");
      queryClient.invalidateQueries({ queryKey: ["platform-payment-config"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to save"),
  });

  const toggleMutation = useMutation({
    mutationFn: updatePlatformPaymentConfig,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["platform-payment-config"] }),
  });

  const testMutation = useMutation({
    mutationFn: testPlatformPaymentConfig,
    onSuccess: (res) => {
      message.success(res.data.detail);
      queryClient.invalidateQueries({ queryKey: ["platform-payment-config"] });
    },
    onError: (err: any) => {
      message.error(err?.response?.data?.detail || "Connection test failed");
      queryClient.invalidateQueries({ queryKey: ["platform-payment-config"] });
    },
  });

  if (isLoading || !data) return null;

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Alert
        type="info"
        showIcon
        message="Razorpay - platform billing"
        description="One Razorpay merchant account bills every store on Vastr. Store owners see a real Razorpay checkout when they choose to activate their subscription immediately instead of waiting out the free trial. Get your Key ID and Key Secret from the Razorpay Dashboard under Settings > API Keys."
      />
      <Card
        title={<Space>Razorpay <StatusTags configured={data.is_configured} testStatus={data.last_test_status} testError={data.last_test_error} testAt={data.last_test_at} /></Space>}
        extra={
          <Switch
            checked={data.is_enabled}
            onChange={(checked) => toggleMutation.mutate({ is_enabled: checked })}
            checkedChildren="Enabled"
            unCheckedChildren="Disabled"
          />
        }
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{
            razorpay_key_id: data.razorpay_key_id,
            razorpay_key_secret: "",
            razorpay_webhook_secret: "",
            is_live: data.is_live,
          }}
          onFinish={(values) => saveMutation.mutate(values)}
        >
          <Space wrap style={{ width: "100%" }}>
            <Form.Item name="razorpay_key_id" label="Key ID" style={{ width: 320 }}>
              <Input placeholder="rzp_test_xxxxxxxxxxxx" />
            </Form.Item>
            <Form.Item name="is_live" label="Live mode" valuePropName="checked">
              <Switch checkedChildren="Live" unCheckedChildren="Test" />
            </Form.Item>
          </Space>
          <Space wrap style={{ width: "100%" }}>
            <Form.Item
              name="razorpay_key_secret"
              label={`Key secret${data.razorpay_key_secret_set ? " (leave blank to keep current)" : ""}`}
              style={{ width: 320 }}
            >
              <Input.Password placeholder={data.razorpay_key_secret_set ? "••••••••" : "Key secret"} />
            </Form.Item>
            <Form.Item
              name="razorpay_webhook_secret"
              label={`Webhook secret${data.razorpay_webhook_secret_set ? " (leave blank to keep current)" : ""} (optional)`}
              style={{ width: 320 }}
            >
              <Input.Password placeholder={data.razorpay_webhook_secret_set ? "••••••••" : "Webhook secret"} />
            </Form.Item>
          </Space>
          <Space wrap>
            <Button type="primary" htmlType="submit" loading={saveMutation.isPending}>Save</Button>
            <Button disabled={!data.is_configured} loading={testMutation.isPending} onClick={() => testMutation.mutate()}>
              Test connection
            </Button>
          </Space>
        </Form>
      </Card>
    </Space>
  );
}

function EmailTab() {
  const queryClient = useQueryClient();
  const [form] = Form.useForm();
  const [testEmail, setTestEmail] = useState("");
  const { data, isLoading } = useQuery({
    queryKey: ["platform-email-config"],
    queryFn: () => getPlatformEmailConfig().then((r) => r.data),
  });

  const saveMutation = useMutation({
    mutationFn: updatePlatformEmailConfig,
    onSuccess: () => {
      message.success("Email settings saved");
      queryClient.invalidateQueries({ queryKey: ["platform-email-config"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to save"),
  });

  const toggleMutation = useMutation({
    mutationFn: updatePlatformEmailConfig,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["platform-email-config"] }),
  });

  const testMutation = useMutation({
    mutationFn: () => testPlatformEmailConfig(testEmail),
    onSuccess: (res) => {
      message.success(res.data.detail);
      queryClient.invalidateQueries({ queryKey: ["platform-email-config"] });
    },
    onError: (err: any) => {
      message.error(err?.response?.data?.detail || "Test email failed");
      queryClient.invalidateQueries({ queryKey: ["platform-email-config"] });
    },
  });

  if (isLoading || !data) return null;

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Alert
        type="info"
        showIcon
        message="System email (SMTP)"
        description="This SMTP account sends Vastr's own transactional emails - signup verification links and password resets. It's separate from a tenant's own Email Integrations (which they use to email their customers)."
      />
      <Card
        title={<Space>SMTP <StatusTags configured={data.is_configured} testStatus={data.last_test_status} testError={data.last_test_error} testAt={data.last_test_at} /></Space>}
        extra={
          <Switch
            checked={data.is_enabled}
            onChange={(checked) => toggleMutation.mutate({ is_enabled: checked })}
            checkedChildren="Enabled"
            unCheckedChildren="Disabled"
          />
        }
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{
            sender_name: data.sender_name,
            sender_email: data.sender_email,
            smtp_host: data.smtp_host,
            smtp_port: data.smtp_port,
            smtp_username: data.smtp_username,
            smtp_password: "",
            smtp_use_tls: data.smtp_use_tls,
          }}
          onFinish={(values) => saveMutation.mutate(values)}
        >
          <Space wrap style={{ width: "100%" }}>
            <Form.Item name="sender_name" label="Sender name" style={{ width: 220 }}>
              <Input placeholder="Vastr" />
            </Form.Item>
            <Form.Item name="sender_email" label="Sender email" style={{ width: 260 }}>
              <Input placeholder="noreply@vastr.space" />
            </Form.Item>
          </Space>
          <Space wrap style={{ width: "100%" }}>
            <Form.Item name="smtp_host" label="SMTP host" style={{ width: 240 }}>
              <Input placeholder="smtp.example.com" />
            </Form.Item>
            <Form.Item
              name="smtp_port"
              label="Port"
              style={{ width: 100 }}
              tooltip="465 = implicit SSL (auto-detected, TLS toggle is ignored). 587 = STARTTLS - uses the toggle below."
            >
              <InputNumber style={{ width: "100%" }} />
            </Form.Item>
            <Form.Item name="smtp_use_tls" label="Use TLS" valuePropName="checked" tooltip="Only applies on port 587/25 (STARTTLS). Port 465 always connects encrypted.">
              <Switch />
            </Form.Item>
          </Space>
          <Space wrap style={{ width: "100%" }}>
            <Form.Item name="smtp_username" label="SMTP username" style={{ width: 260 }}>
              <Input placeholder="you@vastr.space" />
            </Form.Item>
            <Form.Item
              name="smtp_password"
              label={`SMTP password${data.smtp_password_set ? " (leave blank to keep current)" : ""}`}
              style={{ width: 260 }}
            >
              <Input.Password placeholder={data.smtp_password_set ? "••••••••" : "App password"} />
            </Form.Item>
          </Space>
          <Space wrap>
            <Button type="primary" htmlType="submit" loading={saveMutation.isPending}>Save</Button>
          </Space>
        </Form>
        <div style={{ marginTop: 16, paddingTop: 16, borderTop: "1px solid #f0f0f0" }}>
          <Space wrap>
            <Input
              placeholder="test-recipient@example.com"
              style={{ width: 240 }}
              value={testEmail}
              onChange={(e) => setTestEmail(e.target.value)}
            />
            <Button disabled={!data.is_configured || !testEmail} loading={testMutation.isPending} onClick={() => testMutation.mutate()}>
              Send test email
            </Button>
          </Space>
        </div>
      </Card>
    </Space>
  );
}

function WebsiteTab() {
  const queryClient = useQueryClient();
  const [form] = Form.useForm();
  const { data, isLoading } = useQuery({
    queryKey: ["platform-website-config"],
    queryFn: () => getPlatformWebsiteConfig().then((r) => r.data),
  });

  const saveMutation = useMutation({
    mutationFn: updatePlatformWebsiteConfig,
    onSuccess: () => {
      message.success("Website configuration saved");
      queryClient.invalidateQueries({ queryKey: ["platform-website-config"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to save"),
  });

  if (isLoading || !data) return null;

  return (
    <Card title="Website configuration">
      <Form
        form={form}
        layout="vertical"
        initialValues={{
          site_name: data.site_name,
          support_email: data.support_email,
          support_phone: data.support_phone,
          footer_text: data.footer_text,
          twitter: data.social_links?.twitter,
          linkedin: data.social_links?.linkedin,
          instagram: data.social_links?.instagram,
        }}
        onFinish={(values) => {
          const { twitter, linkedin, instagram, ...rest } = values;
          const social_links: Record<string, string> = {};
          if (twitter) social_links.twitter = twitter;
          if (linkedin) social_links.linkedin = linkedin;
          if (instagram) social_links.instagram = instagram;
          saveMutation.mutate({ ...rest, social_links });
        }}
      >
        <Space wrap style={{ width: "100%" }}>
          <Form.Item name="site_name" label="Site name" style={{ width: 240 }}>
            <Input placeholder="Vastr" />
          </Form.Item>
          <Form.Item name="support_email" label="Support email" style={{ width: 280 }}>
            <Input placeholder="hello@vastr.space" />
          </Form.Item>
          <Form.Item name="support_phone" label="Support phone" style={{ width: 200 }}>
            <Input placeholder="+91 98765 43210" />
          </Form.Item>
        </Space>
        <Form.Item name="footer_text" label="Footer text">
          <Input placeholder="© 2026 Vastr. Fashion retail, reimagined." />
        </Form.Item>
        <Typography.Text strong style={{ display: "block", marginBottom: 8 }}>Social links (optional)</Typography.Text>
        <Space wrap style={{ width: "100%" }}>
          <Form.Item name="twitter" label="Twitter / X" style={{ width: 260 }}>
            <Input placeholder="https://x.com/vastr" />
          </Form.Item>
          <Form.Item name="linkedin" label="LinkedIn" style={{ width: 260 }}>
            <Input placeholder="https://linkedin.com/company/vastr" />
          </Form.Item>
          <Form.Item name="instagram" label="Instagram" style={{ width: 260 }}>
            <Input placeholder="https://instagram.com/vastr" />
          </Form.Item>
        </Space>
        <Button type="primary" htmlType="submit" loading={saveMutation.isPending}>Save</Button>
      </Form>
    </Card>
  );
}

export default function GlobalSettings() {
  return (
    <div>
      <Typography.Title level={3} style={{ margin: 0, marginBottom: 20 }}>
        Global Settings
      </Typography.Title>
      <Tabs
        items={[
          { key: "payment", label: "Payment Gateway", children: <PaymentGatewayTab /> },
          { key: "email", label: "Email", children: <EmailTab /> },
          { key: "website", label: "Website Configuration", children: <WebsiteTab /> },
        ]}
      />
    </div>
  );
}
