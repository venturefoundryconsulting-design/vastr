import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Form, Input, Space, Switch, Tag, Tooltip, Typography, message } from "antd";
import { CheckCircleFilled, CloseCircleFilled } from "@ant-design/icons";
import { listSmsProviders, testSmsProvider, updateSmsProvider } from "../../api/endpoints";
import type { SmsProviderOut, SmsProviderType } from "../../api/types";

const PROVIDER_META: Record<SmsProviderType, { label: string; hint: string; kind: "simple" | "twilio" | "generic" }> = {
  msg91: { label: "MSG91", hint: "Auth key + a registered sender ID (6 chars, e.g. TANISI)", kind: "simple" },
  textlocal_india: { label: "Textlocal (India)", hint: "API key + a registered sender ID", kind: "simple" },
  two_factor: { label: "2Factor", hint: "API key + a registered sender ID", kind: "simple" },
  twilio: { label: "Twilio", hint: "Account SID as API key, Auth token, and a Twilio phone number as sender ID", kind: "twilio" },
  generic_http: { label: "Generic HTTP API", hint: "POSTs {to, message} as JSON to a webhook URL you provide - works with most custom SMS gateways", kind: "generic" },
};

const PROVIDER_ORDER: SmsProviderType[] = ["msg91", "textlocal_india", "two_factor", "generic_http", "twilio"];

function StatusTags({ p }: { p: SmsProviderOut }) {
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

function SmsProviderCard({ provider }: { provider: SmsProviderOut }) {
  const queryClient = useQueryClient();
  const [form] = Form.useForm();
  const [testNumber, setTestNumber] = useState("");
  const meta = PROVIDER_META[provider.provider];

  const saveMutation = useMutation({
    mutationFn: (data: Record<string, unknown>) => updateSmsProvider(provider.provider, data),
    onSuccess: () => {
      message.success(`${meta.label} settings saved`);
      queryClient.invalidateQueries({ queryKey: ["sms-providers"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to save"),
  });

  const toggleMutation = useMutation({
    mutationFn: (data: Record<string, unknown>) => updateSmsProvider(provider.provider, data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sms-providers"] }),
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to update"),
  });

  const testMutation = useMutation({
    mutationFn: () => testSmsProvider(provider.provider, testNumber),
    onSuccess: (res) => {
      message.success(res.data.detail);
      queryClient.invalidateQueries({ queryKey: ["sms-providers"] });
    },
    onError: (err: any) => {
      message.error(err?.response?.data?.detail || "Test SMS failed");
      queryClient.invalidateQueries({ queryKey: ["sms-providers"] });
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
          api_key: "",
          auth_token: "",
          sender_id: provider.sender_id,
          webhook_url: (provider.extra_config as any)?.webhook_url,
        }}
        onFinish={(values) => {
          const { webhook_url, ...rest } = values;
          const payload: Record<string, unknown> = { ...rest };
          if (meta.kind === "generic") {
            payload.extra_config = { webhook_url };
          }
          saveMutation.mutate(payload);
        }}
      >
        {meta.kind !== "generic" && (
          <Space wrap style={{ width: "100%" }}>
            <Form.Item
              name="api_key"
              label={`${meta.kind === "twilio" ? "Account SID" : "API key"}${
                provider.api_key_set ? " (leave blank to keep current)" : ""
              }`}
              style={{ width: 280 }}
            >
              <Input.Password placeholder={provider.api_key_set ? "••••••••" : meta.kind === "twilio" ? "ACxxxxxxxx" : "API key"} />
            </Form.Item>
            {meta.kind === "twilio" && (
              <Form.Item
                name="auth_token"
                label={`Auth token${provider.auth_token_set ? " (leave blank to keep current)" : ""}`}
                style={{ width: 260 }}
              >
                <Input.Password placeholder={provider.auth_token_set ? "••••••••" : "Auth token"} />
              </Form.Item>
            )}
            <Form.Item name="sender_id" label={meta.kind === "twilio" ? "From number" : "Sender ID"} style={{ width: 180 }}>
              <Input placeholder={meta.kind === "twilio" ? "+1415..." : "TANISI"} />
            </Form.Item>
          </Space>
        )}

        {meta.kind === "generic" && (
          <Space wrap style={{ width: "100%" }}>
            <Form.Item name="webhook_url" label="Webhook URL" style={{ width: 340 }}>
              <Input placeholder="https://your-sms-gateway.example/send" />
            </Form.Item>
            <Form.Item
              name="auth_token"
              label={`Authorization header${provider.auth_token_set ? " (leave blank to keep current)" : ""}`}
              style={{ width: 280 }}
            >
              <Input.Password placeholder={provider.auth_token_set ? "••••••••" : "Bearer ..."} />
            </Form.Item>
          </Space>
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
            placeholder="9876543210"
            style={{ width: 200 }}
            value={testNumber}
            onChange={(e) => setTestNumber(e.target.value)}
          />
          <Button
            disabled={!provider.is_configured || !testNumber}
            loading={testMutation.isPending}
            onClick={() => testMutation.mutate()}
          >
            Send test SMS
          </Button>
        </Space>
      </div>
    </Card>
  );
}

export default function SmsIntegrationsSettings() {
  const { data: providers, isLoading } = useQuery({
    queryKey: ["sms-providers"],
    queryFn: () => listSmsProviders().then((r) => r.data),
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
        message="How SMS sending works"
        description="Enable one or more providers, fill in their credentials, and mark exactly one as Default - that's the one used whenever the app sends an SMS. Use the test button to confirm credentials work before relying on a provider."
      />
      {sorted.map((p) => (
        <SmsProviderCard key={p.provider} provider={p} />
      ))}
    </Space>
  );
}
