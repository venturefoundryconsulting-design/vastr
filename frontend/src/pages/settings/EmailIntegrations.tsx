import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Space,
  Switch,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import { CheckCircleFilled, CloseCircleFilled } from "@ant-design/icons";
import { listEmailProviders, testEmailProvider, updateEmailProvider } from "../../api/endpoints";
import type { EmailProviderOut, EmailProviderType } from "../../api/types";

const PROVIDER_META: Record<EmailProviderType, { label: string; hint: string; kind: "api" | "emailjs" | "smtp" }> = {
  brevo: { label: "Brevo", hint: "API key from Brevo > SMTP & API > API Keys", kind: "api" },
  resend: { label: "Resend", hint: "API key from the Resend dashboard", kind: "api" },
  emailjs: { label: "EmailJS", hint: "Browser-friendly email API - needs a Service ID and Template ID from your EmailJS account", kind: "emailjs" },
  smtp_generic: { label: "SMTP (Generic)", hint: "Any SMTP server - host, port, username, password", kind: "smtp" },
  gmail_smtp: { label: "Gmail SMTP", hint: "smtp.gmail.com, port 587 - use a Google App Password, not your regular password", kind: "smtp" },
  outlook_smtp: { label: "Outlook SMTP", hint: "smtp.office365.com, port 587", kind: "smtp" },
};

const PROVIDER_ORDER: EmailProviderType[] = ["brevo", "resend", "emailjs", "smtp_generic", "gmail_smtp", "outlook_smtp"];

function StatusTags({ p }: { p: EmailProviderOut }) {
  return (
    <Space size={4}>
      {p.is_default && <Tag color="blue">Default</Tag>}
      {p.is_configured ? <Tag color="green">Configured</Tag> : <Tag>Not set up</Tag>}
      {p.last_test_status === "success" && (
        <Tooltip title={p.last_test_at ? `Last tested ${new Date(p.last_test_at).toLocaleString()}` : undefined}>
          <Tag icon={<CheckCircleFilled />} color="success">Test passed</Tag>
        </Tooltip>
      )}
      {p.last_test_status === "failed" && (
        <Tooltip title={p.last_test_error || "Last test failed"}>
          <Tag icon={<CloseCircleFilled />} color="error">Test failed</Tag>
        </Tooltip>
      )}
    </Space>
  );
}

function EmailProviderCard({ provider }: { provider: EmailProviderOut }) {
  const queryClient = useQueryClient();
  const [form] = Form.useForm();
  const [testEmail, setTestEmail] = useState("");
  const meta = PROVIDER_META[provider.provider];

  const saveMutation = useMutation({
    mutationFn: (data: Record<string, unknown>) => updateEmailProvider(provider.provider, data),
    onSuccess: () => {
      message.success(`${meta.label} settings saved`);
      queryClient.invalidateQueries({ queryKey: ["email-providers"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to save"),
  });

  const toggleMutation = useMutation({
    mutationFn: (data: Record<string, unknown>) => updateEmailProvider(provider.provider, data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["email-providers"] }),
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to update"),
  });

  const testMutation = useMutation({
    mutationFn: () => testEmailProvider(provider.provider, testEmail),
    onSuccess: (res) => {
      message.success(res.data.detail);
      queryClient.invalidateQueries({ queryKey: ["email-providers"] });
    },
    onError: (err: any) => {
      message.error(err?.response?.data?.detail || "Test email failed");
      queryClient.invalidateQueries({ queryKey: ["email-providers"] });
    },
  });

  return (
    <Card
      title={
        <Space>
          {meta.label}
          <StatusTags p={provider} />
        </Space>
      }
      extra={
        <Switch
          checked={provider.is_enabled}
          onChange={(checked) => toggleMutation.mutate({ is_enabled: checked })}
          checkedChildren="Enabled"
          unCheckedChildren="Disabled"
        />
      }
    >
      <Typography.Paragraph type="secondary" style={{ marginBottom: 12 }}>
        {meta.hint}
      </Typography.Paragraph>
      <Form
        form={form}
        layout="vertical"
        initialValues={{
          sender_name: provider.sender_name,
          sender_email: provider.sender_email,
          api_key: "",
          secret_key: "",
          smtp_host: provider.smtp_host,
          smtp_port: provider.smtp_port,
          smtp_username: provider.smtp_username,
          smtp_password: "",
          smtp_use_tls: provider.smtp_use_tls,
          service_id: (provider.extra_config as any)?.service_id,
          template_id: (provider.extra_config as any)?.template_id,
        }}
        onFinish={(values) => {
          const { service_id, template_id, ...rest } = values;
          const payload: Record<string, unknown> = { ...rest };
          if (meta.kind === "emailjs") {
            payload.extra_config = { service_id, template_id };
          }
          saveMutation.mutate(payload);
        }}
      >
        <Space wrap style={{ width: "100%" }}>
          <Form.Item name="sender_name" label="Sender name" style={{ width: 220 }}>
            <Input placeholder="Tanisi" />
          </Form.Item>
          <Form.Item name="sender_email" label="Sender email" style={{ width: 260 }}>
            <Input placeholder="receipts@yourbrand.com" />
          </Form.Item>
        </Space>

        {(meta.kind === "api" || meta.kind === "emailjs") && (
          <Space wrap style={{ width: "100%" }}>
            <Form.Item
              name="api_key"
              label={`API key${provider.api_key_set ? " (leave blank to keep current)" : ""}`}
              style={{ width: 300 }}
            >
              <Input.Password placeholder={provider.api_key_set ? "••••••••" : "API key"} />
            </Form.Item>
            {meta.kind === "emailjs" && (
              <Form.Item
                name="secret_key"
                label={`Access token${provider.secret_key_set ? " (leave blank to keep current)" : ""}`}
                style={{ width: 260 }}
              >
                <Input.Password placeholder={provider.secret_key_set ? "••••••••" : "Private key"} />
              </Form.Item>
            )}
          </Space>
        )}

        {meta.kind === "emailjs" && (
          <Space wrap style={{ width: "100%" }}>
            <Form.Item name="service_id" label="Service ID" style={{ width: 220 }}>
              <Input placeholder="service_xxxxxxx" />
            </Form.Item>
            <Form.Item name="template_id" label="Template ID" style={{ width: 220 }}>
              <Input placeholder="template_xxxxxxx" />
            </Form.Item>
          </Space>
        )}

        {meta.kind === "smtp" && (
          <>
            <Space wrap style={{ width: "100%" }}>
              <Form.Item name="smtp_host" label="SMTP host" style={{ width: 240 }}>
                <Input placeholder="smtp.example.com" />
              </Form.Item>
              <Form.Item name="smtp_port" label="Port" style={{ width: 100 }}>
                <InputNumber style={{ width: "100%" }} />
              </Form.Item>
              <Form.Item name="smtp_use_tls" label="Use TLS" valuePropName="checked">
                <Switch />
              </Form.Item>
            </Space>
            <Space wrap style={{ width: "100%" }}>
              <Form.Item name="smtp_username" label="SMTP username" style={{ width: 260 }}>
                <Input placeholder="you@yourbrand.com" />
              </Form.Item>
              <Form.Item
                name="smtp_password"
                label={`SMTP password${provider.smtp_password_set ? " (leave blank to keep current)" : ""}`}
                style={{ width: 260 }}
              >
                <Input.Password placeholder={provider.smtp_password_set ? "••••••••" : "App password"} />
              </Form.Item>
            </Space>
          </>
        )}

        <Space wrap>
          <Button type="primary" htmlType="submit" loading={saveMutation.isPending}>
            Save
          </Button>
          <Button
            disabled={!provider.is_enabled || provider.is_default}
            onClick={() => toggleMutation.mutate({ is_default: true })}
          >
            Set as default
          </Button>
        </Space>
      </Form>

      <div style={{ marginTop: 16, paddingTop: 16, borderTop: "1px solid var(--border-color, #f0f0f0)" }}>
        <Space wrap>
          <Input
            placeholder="test-recipient@example.com"
            style={{ width: 240 }}
            value={testEmail}
            onChange={(e) => setTestEmail(e.target.value)}
          />
          <Button
            disabled={!provider.is_configured || !testEmail}
            loading={testMutation.isPending}
            onClick={() => testMutation.mutate()}
          >
            Send test email
          </Button>
        </Space>
      </div>
    </Card>
  );
}

export default function EmailIntegrationsSettings() {
  const { data: providers, isLoading } = useQuery({
    queryKey: ["email-providers"],
    queryFn: () => listEmailProviders().then((r) => r.data),
  });

  if (isLoading || !providers) return null;

  const sorted = [...providers].sort(
    (a, b) => PROVIDER_ORDER.indexOf(a.provider) - PROVIDER_ORDER.indexOf(b.provider)
  );

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Alert
        type="info"
        showIcon
        message="How email sending works"
        description="Enable one or more providers, fill in their credentials, and mark exactly one as Default - that's the one used whenever the app sends an email (receipts, reports, etc). Use the test button to confirm credentials work before relying on a provider."
      />
      {sorted.map((p) => (
        <EmailProviderCard key={p.provider} provider={p} />
      ))}
    </Space>
  );
}
