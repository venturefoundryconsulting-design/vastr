import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Form, Input, InputNumber, Space, Switch, Tag, Typography, message } from "antd";
import { getHardwareAiSettings, updateHardwareAiSettings } from "../../api/endpoints";

export default function HardwareAiSettings() {
  const queryClient = useQueryClient();
  const [barcodeForm] = Form.useForm();
  const [printerForm] = Form.useForm();
  const [biometricForm] = Form.useForm();
  const [aiForm] = Form.useForm();

  const { data: settings, isLoading } = useQuery({
    queryKey: ["hardware-ai-settings"],
    queryFn: () => getHardwareAiSettings().then((r) => r.data),
  });

  const saveMutation = useMutation({
    mutationFn: updateHardwareAiSettings,
    onSuccess: () => {
      message.success("Saved");
      queryClient.invalidateQueries({ queryKey: ["hardware-ai-settings"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to save"),
  });

  if (isLoading || !settings) return null;

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Card title="Barcode scanner">
        <Typography.Paragraph type="secondary">
          Barcode scanners already work today with no setup - every USB, Bluetooth, or handheld scanner
          types like a keyboard, so scanning into the barcode field in POS or Products works automatically.
          These settings just tune that behavior.
        </Typography.Paragraph>
        <Form
          form={barcodeForm}
          layout="vertical"
          initialValues={settings}
          onFinish={(values) => saveMutation.mutate(values)}
        >
          <Space wrap style={{ width: "100%" }}>
            <Form.Item
              name="barcode_min_length"
              label="Minimum barcode length"
              tooltip="Scans shorter than this are ignored - helps filter out accidental keystrokes on shared till keyboards"
              style={{ width: 240 }}
            >
              <InputNumber min={1} style={{ width: "100%" }} placeholder="e.g. 6" />
            </Form.Item>
            <Form.Item name="barcode_beep_on_scan" label="Beep on successful scan" valuePropName="checked">
              <Switch />
            </Form.Item>
          </Space>
          <Button type="primary" htmlType="submit" loading={saveMutation.isPending}>
            Save
          </Button>
        </Form>
      </Card>

      <Card title="Thermal printer">
        <Typography.Paragraph type="secondary">
          Paper size (which controls the actual receipt/document layout) is set per-outlet under Settings
          &gt; Printing. Browsers don't let a webpage pick a specific printer for security reasons - staff
          always choose the physical printer from the browser's own print dialog. These fields are just a
          label for which printer that should be, shown to staff as a reminder.
        </Typography.Paragraph>
        <Form
          form={printerForm}
          layout="vertical"
          initialValues={settings}
          onFinish={(values) => saveMutation.mutate(values)}
        >
          <Space wrap style={{ width: "100%" }}>
            <Form.Item name="thermal_printer_name" label="Printer name" style={{ width: 260 }}>
              <Input placeholder="e.g. Epson TM-T82 (Counter 1)" />
            </Form.Item>
            <Form.Item name="thermal_printer_ip" label="Network IP (if applicable)" style={{ width: 200 }}>
              <Input placeholder="192.168.1.50" />
            </Form.Item>
          </Space>
          <Button type="primary" htmlType="submit" loading={saveMutation.isPending}>
            Save
          </Button>
        </Form>
      </Card>

      <Card
        title={
          <Space>
            Biometric attendance
            <Tag>for future use</Tag>
          </Space>
        }
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="Not yet connected to a feature"
          description="There's no Attendance module in the app yet (see the roadmap in features.md). These fields just store the device connection details now, so they're ready when that module is built."
        />
        <Form
          form={biometricForm}
          layout="vertical"
          initialValues={settings}
          onFinish={(values) => saveMutation.mutate(values)}
        >
          <Form.Item name="biometric_enabled" label="Enable" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Space wrap style={{ width: "100%" }}>
            <Form.Item name="biometric_device_api_url" label="Device API URL" style={{ width: 320 }}>
              <Input placeholder="https://device.local/api" />
            </Form.Item>
            <Form.Item
              name="biometric_api_key"
              label={`API key${settings.biometric_api_key_set ? " (leave blank to keep current)" : ""}`}
              style={{ width: 260 }}
            >
              <Input.Password placeholder={settings.biometric_api_key_set ? "••••••••" : "Device API key"} />
            </Form.Item>
          </Space>
          <Button type="primary" htmlType="submit" loading={saveMutation.isPending}>
            Save
          </Button>
        </Form>
      </Card>

      <Card
        title={
          <Space>
            OpenAI (for AI features)
            <Tag>for future use</Tag>
          </Space>
        }
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="Not yet connected to a feature"
          description="None of the AI features on the roadmap (see features.md - sales summaries, restock suggestions, product descriptions, etc) are built yet. This just stores the API key now, so they're ready to wire up when those features are built."
        />
        <Form
          form={aiForm}
          layout="vertical"
          initialValues={settings}
          onFinish={(values) => saveMutation.mutate(values)}
        >
          <Space wrap style={{ width: "100%" }}>
            <Form.Item
              name="openai_api_key"
              label={`API key${settings.openai_api_key_set ? " (leave blank to keep current)" : ""}`}
              style={{ width: 320 }}
            >
              <Input.Password placeholder={settings.openai_api_key_set ? "••••••••" : "sk-..."} />
            </Form.Item>
            <Form.Item name="openai_model" label="Model" style={{ width: 200 }}>
              <Input placeholder="gpt-4o-mini" />
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
