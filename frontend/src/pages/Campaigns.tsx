import {
  DeleteOutlined,
  EyeOutlined,
  FileTextOutlined,
  PaperClipOutlined,
  PlusOutlined,
  SaveOutlined,
  SendOutlined,
  UploadOutlined,
  WhatsAppOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  DatePicker,
  Descriptions,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
  Upload,
  message,
} from "antd";
import dayjs from "dayjs";
import { useState } from "react";
import {
  createCampaign,
  createMessageTemplate,
  deleteMessageTemplate,
  getCampaign,
  getCampaignReport,
  listCampaignPlaceholders,
  listCampaigns,
  listCategories,
  listMessageTemplates,
  previewSegment,
  uploadCampaignMedia,
} from "../api/endpoints";
import type {
  Campaign,
  CampaignButton,
  CampaignButtonType,
  CampaignDetail,
  CampaignReport,
  MediaUploadResult,
  SegmentParams,
  SegmentPreviewResult,
  SegmentType,
} from "../api/types";

const SEGMENT_LABELS: Record<SegmentType, string> = {
  all: "All customers",
  vip: "VIP customers",
  tag: "Customers with tag",
  category_purchase: "Purchased a category recently",
  brand_purchase: "Purchased a brand recently",
  inactive: "Inactive customers",
  birthday_month: "Birthday this month",
};

const STATUS_COLORS: Record<string, string> = {
  sent: "green",
  delivered: "cyan",
  read: "purple",
  link_generated: "blue",
  failed: "red",
};

const CAMPAIGN_STATUS_COLORS: Record<string, string> = {
  scheduled: "gold",
  sent: "green",
  failed: "red",
};

const BUTTON_PRESETS: { label: string; type: CampaignButtonType; valuePlaceholder: string }[] = [
  { label: "Visit Website", type: "url", valuePlaceholder: "https://yourbrand.com" },
  { label: "Shop Now", type: "url", valuePlaceholder: "https://yourbrand.com/shop" },
  { label: "View Catalog", type: "catalog", valuePlaceholder: "https://yourbrand.com/catalog" },
  { label: "Call Now", type: "phone", valuePlaceholder: "+919900000000" },
  { label: "Reply Button", type: "quick_reply", valuePlaceholder: "Yes, I'm interested" },
];

function RecipientsView({ campaign }: { campaign: CampaignDetail }) {
  return (
    <Table
      rowKey="id"
      size="small"
      dataSource={campaign.recipients}
      pagination={{ pageSize: 10 }}
      scroll={{ x: "max-content" }}
      columns={[
        { title: "Customer", dataIndex: "customer_name" },
        { title: "Phone", dataIndex: "phone_number" },
        {
          title: "Status",
          dataIndex: "status",
          render: (v: string) => <Tag color={STATUS_COLORS[v]}>{v.replace("_", " ")}</Tag>,
        },
        {
          title: "",
          key: "action",
          render: (_: unknown, r: CampaignDetail["recipients"][number]) =>
            r.whatsapp_link ? (
              <Button
                size="small"
                icon={<WhatsAppOutlined />}
                style={{ background: "#25D366", color: "white", border: "none" }}
                onClick={() => window.open(r.whatsapp_link!, "_blank")}
              >
                Send
              </Button>
            ) : r.status === "failed" ? (
              <Typography.Text type="danger" style={{ fontSize: 12 }}>
                {r.error}
              </Typography.Text>
            ) : null,
        },
      ]}
    />
  );
}

function ReportView({ campaignId }: { campaignId: number }) {
  const { data: report, isLoading } = useQuery({
    queryKey: ["campaign-report", campaignId],
    queryFn: () => getCampaignReport(campaignId).then((r) => r.data),
  });
  if (isLoading || !report) return null;
  const rows: { label: string; value: number; color: string }[] = [
    { label: "Recipients", value: report.recipient_count, color: "default" },
    { label: "Manual link (unsent)", value: report.link_generated_count, color: "blue" },
    { label: "Sent", value: report.sent_count, color: "green" },
    { label: "Delivered", value: report.delivered_count, color: "cyan" },
    { label: "Read", value: report.read_count, color: "purple" },
    { label: "Failed", value: report.failed_count, color: "red" },
  ];
  return (
    <Space wrap style={{ marginBottom: 12 }}>
      {rows.map((r) => (
        <Tag key={r.label} color={r.color === "default" ? undefined : r.color} style={{ padding: "4px 10px" }}>
          {r.label}: {r.value}
        </Tag>
      ))}
    </Space>
  );
}

export default function Campaigns() {
  const queryClient = useQueryClient();
  const [form] = Form.useForm();
  const segmentType = Form.useWatch("segment_type", form);
  const scheduledAt = Form.useWatch("scheduled_at", form);
  const [preview, setPreview] = useState<SegmentPreviewResult | null>(null);
  const [viewingCampaign, setViewingCampaign] = useState<CampaignDetail | null>(null);
  const [media, setMedia] = useState<MediaUploadResult | null>(null);
  const [buttons, setButtons] = useState<CampaignButton[]>([]);
  const [saveTemplateOpen, setSaveTemplateOpen] = useState(false);
  const [templateName, setTemplateName] = useState("");

  const { data: campaigns, isLoading } = useQuery({
    queryKey: ["campaigns"],
    queryFn: () => listCampaigns().then((r) => r.data),
  });
  const { data: categories } = useQuery({
    queryKey: ["categories"],
    queryFn: () => listCategories().then((r) => r.data),
  });
  const { data: placeholders } = useQuery({
    queryKey: ["campaign-placeholders"],
    queryFn: () => listCampaignPlaceholders().then((r) => r.data),
  });
  const { data: templates } = useQuery({
    queryKey: ["message-templates"],
    queryFn: () => listMessageTemplates().then((r) => r.data),
  });

  const previewMutation = useMutation({
    mutationFn: (params: SegmentParams) => previewSegment(params),
    onSuccess: (res) => setPreview(res.data),
    onError: (err: any) => {
      setPreview(null);
      message.error(err?.response?.data?.detail || "Failed to preview segment");
    },
  });

  const uploadMutation = useMutation({
    mutationFn: (file: File) => uploadCampaignMedia(file),
    onSuccess: (res) => {
      setMedia(res.data);
      message.success("Media attached");
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to upload media"),
  });

  const saveTemplateMutation = useMutation({
    mutationFn: () => createMessageTemplate({ name: templateName, body: form.getFieldValue("message_template") || "" }),
    onSuccess: () => {
      message.success("Template saved");
      setSaveTemplateOpen(false);
      setTemplateName("");
      queryClient.invalidateQueries({ queryKey: ["message-templates"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to save template"),
  });

  const deleteTemplateMutation = useMutation({
    mutationFn: (id: number) => deleteMessageTemplate(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["message-templates"] }),
  });

  const createMutation = useMutation({
    mutationFn: createCampaign,
    onSuccess: (res) => {
      message.success(
        res.data.status === "scheduled"
          ? `Campaign scheduled for ${res.data.recipient_count} customers`
          : `Campaign sent to ${res.data.recipient_count} customers`
      );
      setViewingCampaign(res.data.status === "scheduled" ? null : res.data);
      setPreview(null);
      setMedia(null);
      setButtons([]);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ["campaigns"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to send campaign"),
  });

  const viewMutation = useMutation({
    mutationFn: (id: number) => getCampaign(id),
    onSuccess: (res) => setViewingCampaign(res.data),
  });

  const buildParams = (): SegmentParams => {
    const values = form.getFieldsValue();
    return {
      segment_type: values.segment_type,
      segment_tag: values.segment_tag,
      segment_category_id: values.segment_category_id,
      segment_brand: values.segment_brand,
      segment_days: values.segment_days,
    };
  };

  const insertPlaceholder = (token: string) => {
    const current = form.getFieldValue("message_template") || "";
    form.setFieldValue("message_template", `${current}{${token}}`);
  };

  const updateButton = (index: number, patch: Partial<CampaignButton>) => {
    setButtons((prev) => prev.map((b, i) => (i === index ? { ...b, ...patch } : b)));
  };

  const columns = [
    { title: "Campaign", dataIndex: "name" },
    { title: "Segment", key: "segment", render: (_: unknown, c: Campaign) => SEGMENT_LABELS[c.segment_type] },
    {
      title: "Status",
      key: "status",
      render: (_: unknown, c: Campaign) => <Tag color={CAMPAIGN_STATUS_COLORS[c.status]}>{c.status}</Tag>,
    },
    {
      title: "When",
      key: "when",
      render: (_: unknown, c: Campaign) =>
        c.status === "scheduled" && c.scheduled_at
          ? `Scheduled: ${new Date(c.scheduled_at).toLocaleString()}`
          : new Date(c.created_at).toLocaleString(),
    },
    { title: "Recipients", dataIndex: "recipient_count" },
    { title: "Auto-sent", dataIndex: "sent_count" },
    {
      title: "",
      key: "actions",
      render: (_: unknown, c: Campaign) => (
        <Button size="small" icon={<EyeOutlined />} loading={viewMutation.isPending} onClick={() => viewMutation.mutate(c.id)}>
          View
        </Button>
      ),
    },
  ];

  return (
    <div>
      <Typography.Title level={3} style={{ marginBottom: 16 }}>
        WhatsApp Marketing
      </Typography.Title>

      <Card title="New Campaign" style={{ marginBottom: 24 }}>
        <Form
          form={form}
          layout="vertical"
          initialValues={{ segment_type: "all" }}
          onValuesChange={() => setPreview(null)}
          onFinish={(values) =>
            createMutation.mutate({
              ...values,
              media_url: media?.url,
              media_type: media?.media_type,
              buttons: buttons.filter((b) => b.label && b.value),
              scheduled_at: values.scheduled_at ? values.scheduled_at.toISOString() : undefined,
            })
          }
        >
          <Space style={{ width: "100%" }} size="large" wrap>
            <Form.Item name="name" label="Campaign name" rules={[{ required: true }]} style={{ width: 260 }}>
              <Input placeholder="e.g. Diwali Sale Announcement" />
            </Form.Item>
            <Form.Item name="segment_type" label="Send to" rules={[{ required: true }]} style={{ width: 260 }}>
              <Select options={Object.entries(SEGMENT_LABELS).map(([value, label]) => ({ value, label }))} />
            </Form.Item>
            <Form.Item name="scheduled_at" label="Schedule for (optional)" style={{ width: 260 }}>
              <DatePicker showTime format="DD MMM YYYY, h:mm A" disabledDate={(d) => d && d < dayjs().startOf("day")} />
            </Form.Item>
          </Space>

          <Space style={{ width: "100%" }} size="large">
            {segmentType === "tag" && (
              <Form.Item name="segment_tag" label="Tag" rules={[{ required: true }]} style={{ width: 220 }}>
                <Input placeholder="e.g. VIP" />
              </Form.Item>
            )}
            {segmentType === "category_purchase" && (
              <>
                <Form.Item name="segment_category_id" label="Category" rules={[{ required: true }]} style={{ width: 220 }}>
                  <Select options={categories?.map((c) => ({ value: c.id, label: c.name }))} />
                </Form.Item>
                <Form.Item name="segment_days" label="In the last N days" initialValue={30} style={{ width: 180 }}>
                  <InputNumber min={1} style={{ width: "100%" }} />
                </Form.Item>
              </>
            )}
            {segmentType === "brand_purchase" && (
              <>
                <Form.Item name="segment_brand" label="Brand" rules={[{ required: true }]} style={{ width: 220 }}>
                  <Input placeholder="e.g. Tanisi" />
                </Form.Item>
                <Form.Item name="segment_days" label="In the last N days" initialValue={30} style={{ width: 180 }}>
                  <InputNumber min={1} style={{ width: "100%" }} />
                </Form.Item>
              </>
            )}
            {segmentType === "inactive" && (
              <Form.Item name="segment_days" label="No purchase in the last N days" initialValue={60} style={{ width: 220 }}>
                <InputNumber min={1} style={{ width: "100%" }} />
              </Form.Item>
            )}
          </Space>

          <Space wrap style={{ width: "100%" }}>
            <Form.Item name="offer_code" label="Offer code (optional)" style={{ width: 200 }}>
              <Input placeholder="SAVE10" />
            </Form.Item>
            <Form.Item name="product_name" label="Featured product (optional)" style={{ width: 260 }}>
              <Input placeholder="Banarasi Silk Saree" />
            </Form.Item>
            <Form.Item label="Load template" style={{ width: 240 }}>
              <Select
                allowClear
                placeholder="Choose a saved template"
                options={templates?.map((t) => ({ value: t.id, label: t.name }))}
                onChange={(id) => {
                  const t = templates?.find((tpl) => tpl.id === id);
                  if (t) form.setFieldValue("message_template", t.body);
                }}
                popupRender={(menu) => (
                  <>
                    {menu}
                    {templates?.length ? (
                      <div style={{ borderTop: "1px solid #f0f0f0", padding: 4 }}>
                        {templates.map((t) => (
                          <div key={t.id} style={{ display: "flex", justifyContent: "space-between", padding: "2px 8px" }}>
                            <Typography.Text style={{ fontSize: 12 }}>{t.name}</Typography.Text>
                            <Button
                              size="small"
                              type="text"
                              danger
                              icon={<DeleteOutlined />}
                              onClick={(e) => {
                                e.stopPropagation();
                                deleteTemplateMutation.mutate(t.id);
                              }}
                            />
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </>
                )}
              />
            </Form.Item>
          </Space>

          <Form.Item
            name="message_template"
            label="Message"
            rules={[{ required: true }]}
            extra={
              <Space wrap style={{ marginTop: 4 }}>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  Insert placeholder:
                </Typography.Text>
                {Object.keys(placeholders || { customer_name: "", store_name: "" }).map((token) => (
                  <Tooltip key={token} title={placeholders?.[token]}>
                    <Tag style={{ cursor: "pointer" }} onClick={() => insertPlaceholder(token)}>
                      {`{${token}}`}
                    </Tag>
                  </Tooltip>
                ))}
                <Button
                  size="small"
                  type="link"
                  icon={<SaveOutlined />}
                  onClick={() => {
                    setTemplateName(form.getFieldValue("name") || "");
                    setSaveTemplateOpen(true);
                  }}
                >
                  Save as template
                </Button>
              </Space>
            }
          >
            <Input.TextArea
              rows={3}
              placeholder="Hi {customer_name}, our Diwali Sale starts tomorrow - use code {offer_code} for 30% off {product_name}!"
            />
          </Form.Item>

          <Form.Item label="Media attachment (optional)">
            {media ? (
              <Space>
                <Tag icon={<PaperClipOutlined />} color="blue">
                  {media.media_type} attached
                </Tag>
                <Typography.Link href={media.url} target="_blank">
                  Preview
                </Typography.Link>
                <Button size="small" danger icon={<DeleteOutlined />} onClick={() => setMedia(null)}>
                  Remove
                </Button>
              </Space>
            ) : (
              <Upload
                showUploadList={false}
                accept="image/jpeg,image/png,image/webp,video/mp4,application/pdf"
                customRequest={({ file, onSuccess, onError }) => {
                  uploadMutation.mutate(file as File, {
                    onSuccess: () => onSuccess?.({}),
                    onError: (err) => onError?.(err as Error),
                  });
                }}
              >
                <Button icon={<UploadOutlined />} loading={uploadMutation.isPending}>
                  Attach image, video, or PDF
                </Button>
              </Upload>
            )}
          </Form.Item>

          <Form.Item label="Interactive buttons (optional, up to 3)">
            <Space direction="vertical" style={{ width: "100%" }}>
              {buttons.map((b, i) => (
                <Space key={i} wrap>
                  <Select
                    style={{ width: 160 }}
                    value={b.label}
                    options={BUTTON_PRESETS.map((p) => ({ value: p.label, label: p.label }))}
                    onChange={(label) => {
                      const preset = BUTTON_PRESETS.find((p) => p.label === label)!;
                      updateButton(i, { label: preset.label, type: preset.type, value: "" });
                    }}
                  />
                  <Input
                    style={{ width: 260 }}
                    placeholder={BUTTON_PRESETS.find((p) => p.label === b.label)?.valuePlaceholder}
                    value={b.value}
                    onChange={(e) => updateButton(i, { value: e.target.value })}
                  />
                  {b.type !== "quick_reply" && (
                    <Tooltip title="URL/call/catalog buttons need an approved Meta Message Template to render as real buttons - this will be appended as a text line instead">
                      <Tag color="orange">appended as text</Tag>
                    </Tooltip>
                  )}
                  <Button danger icon={<DeleteOutlined />} onClick={() => setButtons((prev) => prev.filter((_, idx) => idx !== i))} />
                </Space>
              ))}
              {buttons.length < 3 && (
                <Button
                  icon={<PlusOutlined />}
                  onClick={() => setButtons((prev) => [...prev, { type: "quick_reply", label: "Reply Button", value: "" }])}
                >
                  Add button
                </Button>
              )}
            </Space>
          </Form.Item>

          <Space>
            <Button loading={previewMutation.isPending} onClick={() => previewMutation.mutate(buildParams())}>
              Preview audience
            </Button>
            <Button
              type="primary"
              icon={scheduledAt ? <FileTextOutlined /> : <SendOutlined />}
              htmlType="submit"
              loading={createMutation.isPending}
              disabled={!preview || preview.count === 0}
            >
              {scheduledAt ? "Schedule Campaign" : "Send Campaign"}
            </Button>
          </Space>

          {preview && (
            <Alert
              style={{ marginTop: 16 }}
              type={preview.count > 0 ? "info" : "warning"}
              message={
                preview.count > 0
                  ? `${preview.count} customer${preview.count === 1 ? "" : "s"} match this segment: ${preview.customers
                      .slice(0, 8)
                      .map((c) => c.name)
                      .join(", ")}${preview.count > 8 ? ", ..." : ""}`
                  : "No customers match this segment."
              }
            />
          )}
        </Form>
      </Card>

      <Typography.Title level={4}>Past Campaigns</Typography.Title>
      <Table rowKey="id" loading={isLoading} columns={columns} dataSource={campaigns} pagination={{ pageSize: 10 }} scroll={{ x: "max-content" }} />

      <Modal
        title={viewingCampaign ? `${viewingCampaign.name} - ${viewingCampaign.recipient_count} recipients` : ""}
        open={!!viewingCampaign}
        onCancel={() => setViewingCampaign(null)}
        footer={null}
        width={760}
      >
        {viewingCampaign && (
          <>
            <Descriptions size="small" column={2} style={{ marginBottom: 12 }}>
              {viewingCampaign.offer_code && <Descriptions.Item label="Offer code">{viewingCampaign.offer_code}</Descriptions.Item>}
              {viewingCampaign.product_name && (
                <Descriptions.Item label="Featured product">{viewingCampaign.product_name}</Descriptions.Item>
              )}
              {viewingCampaign.media_url && (
                <Descriptions.Item label="Media">
                  <Typography.Link href={viewingCampaign.media_url} target="_blank">
                    {viewingCampaign.media_type}
                  </Typography.Link>
                </Descriptions.Item>
              )}
            </Descriptions>
            <Typography.Paragraph type="secondary">{viewingCampaign.message_template}</Typography.Paragraph>
            <ReportView campaignId={viewingCampaign.id} />
            <RecipientsView campaign={viewingCampaign} />
          </>
        )}
      </Modal>

      <Modal
        title="Save as template"
        open={saveTemplateOpen}
        onCancel={() => setSaveTemplateOpen(false)}
        onOk={() => saveTemplateMutation.mutate()}
        confirmLoading={saveTemplateMutation.isPending}
        okButtonProps={{ disabled: !templateName.trim() }}
      >
        <Input placeholder="Template name" value={templateName} onChange={(e) => setTemplateName(e.target.value)} />
      </Modal>
    </div>
  );
}
