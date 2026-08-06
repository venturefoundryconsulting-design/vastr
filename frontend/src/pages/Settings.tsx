import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  ColorPicker,
  Descriptions,
  Form,
  Input,
  Select,
  Space,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography,
  Upload,
  message,
} from "antd";
import { DeleteOutlined, UploadOutlined } from "@ant-design/icons";
import { getAppSettings, listOutlets, removeLogo, updateAppSettings, updateMyTenant, updateOutlet, uploadLogo } from "../api/endpoints";
import type { Outlet, PaperSize } from "../api/types";
import { useTenant } from "../context/TenantContext";
import EmailIntegrationsSettings from "./settings/EmailIntegrations";
import HardwareAiSettings from "./settings/HardwareAiSettings";
import SmsIntegrationsSettings from "./settings/SmsIntegrations";

const PAPER_SIZE_OPTIONS: { value: PaperSize; label: string }[] = [
  { value: "a4", label: "A4 (standard printer)" },
  { value: "thermal_80", label: "Thermal 80mm" },
  { value: "thermal_58", label: "Thermal 58mm" },
];

function PrintingSettings() {
  const queryClient = useQueryClient();
  const { data: outlets, isLoading } = useQuery({
    queryKey: ["outlets"],
    queryFn: () => listOutlets().then((r) => r.data),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<Outlet> }) => updateOutlet(id, data),
    onSuccess: () => {
      message.success("Printing preference saved");
      queryClient.invalidateQueries({ queryKey: ["outlets"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to save"),
  });

  return (
    <div>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="How printer selection works"
        description={
          <>
            Pick the paper format each outlet's printer takes below. When staff hit Print, the
            receipt or transfer document is laid out for that format and your browser's normal
            print dialog opens - from there staff choose whichever physical printer is installed
            on that till's computer (A4 laser printer, 80mm thermal, 58mm thermal, etc). Any
            printer with an OS driver - USB, network, or Bluetooth - works this way; there is
            nothing separate to "install" in the app itself.
          </>
        }
      />
      <Table
        rowKey="id"
        loading={isLoading}
        dataSource={outlets}
        pagination={false}
        columns={[
          { title: "Outlet", dataIndex: "name" },
          {
            title: "Customer receipt paper size",
            key: "receipt_paper_size",
            render: (_: unknown, outlet: Outlet) => (
              <Select
                style={{ width: 220 }}
                value={outlet.receipt_paper_size}
                options={PAPER_SIZE_OPTIONS}
                onChange={(value) => updateMutation.mutate({ id: outlet.id, data: { receipt_paper_size: value } })}
              />
            ),
          },
          {
            title: "Stock transfer document paper size",
            key: "transfer_paper_size",
            render: (_: unknown, outlet: Outlet) => (
              <Select
                style={{ width: 220 }}
                value={outlet.transfer_paper_size}
                options={PAPER_SIZE_OPTIONS}
                onChange={(value) => updateMutation.mutate({ id: outlet.id, data: { transfer_paper_size: value } })}
              />
            ),
          },
        ]}
      />
    </div>
  );
}

function BusinessProfileSettings() {
  const queryClient = useQueryClient();
  const [form] = Form.useForm();

  const { data: settings, isLoading } = useQuery({
    queryKey: ["app-settings"],
    queryFn: () => getAppSettings().then((r) => r.data),
  });

  const saveMutation = useMutation({
    mutationFn: updateAppSettings,
    onSuccess: () => {
      message.success("Business profile saved");
      queryClient.invalidateQueries({ queryKey: ["app-settings"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to save"),
  });

  const invalidateBranding = () => {
    queryClient.invalidateQueries({ queryKey: ["app-settings"] });
    queryClient.invalidateQueries({ queryKey: ["public-branding"] });
  };

  const uploadLogoMutation = useMutation({
    mutationFn: (file: File) => uploadLogo(file),
    onSuccess: () => {
      message.success("Logo updated");
      invalidateBranding();
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to upload logo"),
  });

  const removeLogoMutation = useMutation({
    mutationFn: removeLogo,
    onSuccess: () => {
      message.success("Logo removed");
      invalidateBranding();
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to remove logo"),
  });

  if (isLoading || !settings) return null;

  return (
    <div>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="Controls how every printed document looks"
        description={
          'This name, address, and GSTIN are printed at the top of every purchase order, customer receipt, ' +
          'and stock transfer document - exactly as you enter them here. Leave a field blank to leave it off ' +
          'the printout. Set a GSTIN and receipts automatically print as "Tax Invoice" instead of "Receipt".'
        }
      />
      <Card title="Logo" style={{ marginBottom: 16 }}>
        <Typography.Paragraph type="secondary" style={{ marginBottom: 12 }}>
          Shown in the top-left corner of the app and on the login page. JPEG, PNG, WebP, or SVG, up to 2MB.
        </Typography.Paragraph>
        <Space align="center" size="large">
          <div
            style={{
              width: 64,
              height: 64,
              borderRadius: 12,
              border: "1px solid #eee3ea",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              overflow: "hidden",
              background: "#faf7f8",
            }}
          >
            {settings.logo_url ? (
              <img src={settings.logo_url} alt="Current logo" style={{ width: "100%", height: "100%", objectFit: "contain" }} />
            ) : (
              <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                No logo
              </Typography.Text>
            )}
          </div>
          <Space>
            <Upload
              showUploadList={false}
              accept="image/jpeg,image/png,image/webp,image/svg+xml"
              customRequest={({ file, onSuccess, onError }) => {
                uploadLogoMutation.mutate(file as File, {
                  onSuccess: () => onSuccess?.({}),
                  onError: (err) => onError?.(err as Error),
                });
              }}
            >
              <Button icon={<UploadOutlined />} loading={uploadLogoMutation.isPending}>
                {settings.logo_url ? "Replace logo" : "Upload logo"}
              </Button>
            </Upload>
            {settings.logo_url && (
              <Button danger icon={<DeleteOutlined />} loading={removeLogoMutation.isPending} onClick={() => removeLogoMutation.mutate()}>
                Remove
              </Button>
            )}
          </Space>
        </Space>
      </Card>
      <Card>
        <Form
          form={form}
          layout="vertical"
          initialValues={settings}
          onFinish={(values) => saveMutation.mutate(values)}
        >
          <Form.Item name="business_name" label="Business name">
            <Input placeholder="e.g. Tanisi by Deepa Goyal" style={{ maxWidth: 420 }} />
          </Form.Item>
          <Form.Item name="business_address" label="Address">
            <Input.TextArea rows={2} style={{ maxWidth: 420 }} placeholder="Shown under the business name on every printout" />
          </Form.Item>
          <Space wrap style={{ width: "100%" }}>
            <Form.Item name="business_gstin" label="GSTIN" style={{ width: 220 }}>
              <Input placeholder="29ABCDE1234F1Z5" />
            </Form.Item>
            <Form.Item name="business_phone" label="Phone" style={{ width: 200 }}>
              <Input placeholder="9876543210" />
            </Form.Item>
            <Form.Item name="business_email" label="Email" style={{ width: 260 }}>
              <Input placeholder="hello@yourbrand.com" />
            </Form.Item>
          </Space>
          <Form.Item
            name="invoice_footer_text"
            label="Footer text"
            tooltip="Printed at the bottom of every document. Defaults to a generic thank-you line if left blank."
          >
            <Input.TextArea rows={2} style={{ maxWidth: 420 }} placeholder="e.g. Exchange within 7 days with receipt. Thank you!" />
          </Form.Item>
          <Form.Item
            name="invoice_prefix"
            label="Invoice number prefix"
            tooltip='New sales get numbered like "PREFIX-202608-0001" - change the prefix here.'
          >
            <Input placeholder="INV" style={{ width: 140 }} />
          </Form.Item>
          <Form.Item
            name="show_hsn_on_documents"
            label="Show HSN code column on printed item tables"
            valuePropName="checked"
          >
            <Switch />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={saveMutation.isPending}>
            Save
          </Button>
        </Form>
      </Card>
    </div>
  );
}

function WhatsAppCloudApiSettings() {
  const queryClient = useQueryClient();
  const [whatsappForm] = Form.useForm();

  const { data: settings, isLoading } = useQuery({
    queryKey: ["app-settings"],
    queryFn: () => getAppSettings().then((r) => r.data),
  });

  const saveMutation = useMutation({
    mutationFn: updateAppSettings,
    onSuccess: () => {
      message.success("Settings saved");
      queryClient.invalidateQueries({ queryKey: ["app-settings"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to save settings"),
  });

  if (isLoading || !settings) return null;

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card
        title={
          <Space>
            WhatsApp Business (Cloud API)
            {settings.whatsapp_token_set ? <Tag color="green">configured</Tag> : <Tag>not set up</Tag>}
          </Space>
        }
      >
        <Typography.Paragraph type="secondary">
          Optional - without this, "Send via WhatsApp" still works everywhere in the app using a
          pre-filled wa.me link that staff tap to send manually. Fill this in only if you want
          receipts and vendor POs to send automatically, no tap required. Needs a Meta Business
          account with WhatsApp Business Platform access.
        </Typography.Paragraph>
        <Form
          form={whatsappForm}
          layout="vertical"
          initialValues={settings}
          onFinish={(values) => saveMutation.mutate(values)}
        >
          <Space wrap style={{ width: "100%" }}>
            <Form.Item name="whatsapp_phone_number_id" label="Phone number ID" style={{ width: 260 }}>
              <Input placeholder="From Meta developer console" />
            </Form.Item>
            <Form.Item
              name="whatsapp_cloud_api_token"
              label={`Access token${settings.whatsapp_token_set ? " (leave blank to keep current)" : ""}`}
              style={{ width: 320 }}
            >
              <Input.Password placeholder={settings.whatsapp_token_set ? "••••••••" : "Permanent access token"} />
            </Form.Item>
            <Form.Item name="whatsapp_api_version" label="API version" style={{ width: 140 }}>
              <Input placeholder="v20.0" />
            </Form.Item>
          </Space>
          <Button type="primary" htmlType="submit" loading={saveMutation.isPending}>
            Save
          </Button>
        </Form>
      </Card>
    </Space>
  );
}

function OrganizationSettings() {
  const { tenant, loading, refresh, darkMode, setDarkMode } = useTenant();
  const [form] = Form.useForm();

  const saveMutation = useMutation({
    mutationFn: updateMyTenant,
    onSuccess: async () => {
      message.success("Organization settings saved");
      await refresh();
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to save"),
  });

  if (loading || !tenant) return null;

  return (
    <div>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="This is separate from your Business Profile"
        description={
          "Company name and theme color here control your Velora workspace identity (sidebar, buttons, " +
          "links). Business Profile (the previous tab) controls what's printed on receipts and purchase " +
          "orders - the two can differ, e.g. a legal name vs. a storefront brand name."
        }
      />
      <Card style={{ maxWidth: 480, marginBottom: 16 }}>
        <Form
          form={form}
          layout="vertical"
          initialValues={tenant}
          onFinish={(values) => saveMutation.mutate(values)}
        >
          <Form.Item name="company_name" label="Company name">
            <Input />
          </Form.Item>
          <Form.Item
            name="primary_color"
            label="Theme color"
            tooltip="Recolors buttons, links, and the sidebar highlight across the whole app."
            getValueFromEvent={(color) => (typeof color === "string" ? color : color?.toHexString())}
          >
            <ColorPicker format="hex" showText />
          </Form.Item>
          <Space wrap style={{ width: "100%" }}>
            <Form.Item name="timezone" label="Timezone" style={{ width: 220 }}>
              <Input placeholder="Asia/Kolkata" />
            </Form.Item>
            <Form.Item name="currency" label="Currency" style={{ width: 120 }}>
              <Input placeholder="INR" />
            </Form.Item>
            <Form.Item name="country" label="Country" style={{ width: 160 }}>
              <Input placeholder="India" />
            </Form.Item>
          </Space>
          <Button type="primary" htmlType="submit" loading={saveMutation.isPending}>
            Save
          </Button>
        </Form>
      </Card>
      <Card title="Dark mode" style={{ maxWidth: 480 }}>
        <Typography.Paragraph type="secondary" style={{ marginBottom: 12 }}>
          A display preference for this browser only - it isn't shared with other people at your
          organization or synced across devices.
        </Typography.Paragraph>
        <Switch checked={darkMode} onChange={setDarkMode} checkedChildren="Dark" unCheckedChildren="Light" />
      </Card>
    </div>
  );
}

const PLAN_LABELS: Record<string, string> = {
  free: "Free",
  starter: "Starter",
  professional: "Professional",
  enterprise: "Enterprise",
};

const STATUS_COLORS: Record<string, string> = {
  trial: "blue",
  active: "green",
  suspended: "orange",
  cancelled: "red",
};

function SubscriptionSettings() {
  const { tenant, loading } = useTenant();
  if (loading || !tenant) return null;

  return (
    <Card style={{ maxWidth: 480 }}>
      <Descriptions
        column={1}
        bordered
        items={[
          { key: "plan", label: "Plan", children: PLAN_LABELS[tenant.subscription_plan] ?? tenant.subscription_plan },
          {
            key: "status",
            label: "Status",
            children: <Tag color={STATUS_COLORS[tenant.subscription_status]}>{tenant.subscription_status.toUpperCase()}</Tag>,
          },
          {
            key: "trial_end",
            label: "Trial ends",
            children: tenant.trial_end ? new Date(tenant.trial_end).toLocaleDateString() : "—",
          },
        ]}
      />
      <Typography.Paragraph type="secondary" style={{ marginTop: 16, marginBottom: 0 }}>
        Billing isn't set up yet - contact your platform administrator to change plans.
      </Typography.Paragraph>
    </Card>
  );
}

export default function Settings() {
  return (
    <div>
      <Typography.Title level={3}>Settings</Typography.Title>
      <Tabs
        defaultActiveKey="business"
        items={[
          { key: "business", label: "Business Profile", children: <BusinessProfileSettings /> },
          { key: "organization", label: "Organization", children: <OrganizationSettings /> },
          { key: "subscription", label: "Subscription", children: <SubscriptionSettings /> },
          { key: "printing", label: "Printing", children: <PrintingSettings /> },
          { key: "whatsapp", label: "WhatsApp", children: <WhatsAppCloudApiSettings /> },
          { key: "email-integrations", label: "Email Integrations", children: <EmailIntegrationsSettings /> },
          { key: "sms-integrations", label: "SMS Integrations", children: <SmsIntegrationsSettings /> },
          { key: "hardware-ai", label: "Hardware & AI", children: <HardwareAiSettings /> },
        ]}
      />
    </div>
  );
}
