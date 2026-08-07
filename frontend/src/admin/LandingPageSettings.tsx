import { DeleteOutlined, PlusOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Form, Input, Select, Space, Tabs, Typography, message } from "antd";
import {
  getAdminLandingContent,
  listAdminLegalPages,
  updateLandingContent,
  upsertLegalPage,
} from "../api/endpoints";

const ICON_OPTIONS = [
  { value: "shopping-cart", label: "Shopping cart" },
  { value: "shop", label: "Shop" },
  { value: "contacts", label: "Contacts" },
  { value: "bar-chart", label: "Bar chart" },
  { value: "team", label: "Team" },
  { value: "safety", label: "Safety" },
];

function HeroTab() {
  const queryClient = useQueryClient();
  const [form] = Form.useForm();
  const { data, isLoading } = useQuery({
    queryKey: ["admin-landing-content"],
    queryFn: () => getAdminLandingContent().then((r) => r.data),
  });

  const saveMutation = useMutation({
    mutationFn: updateLandingContent,
    onSuccess: () => {
      message.success("Hero content saved");
      queryClient.invalidateQueries({ queryKey: ["admin-landing-content"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to save"),
  });

  if (isLoading || !data) return null;

  return (
    <Card>
      <Form
        form={form}
        layout="vertical"
        initialValues={{
          hero_eyebrow: data.hero_eyebrow,
          hero_title_line1: data.hero_title_line1,
          hero_title_highlight: data.hero_title_highlight,
          hero_subtitle: data.hero_subtitle,
          hero_cta_primary: data.hero_cta_primary,
          hero_cta_secondary: data.hero_cta_secondary,
        }}
        onFinish={(values) => saveMutation.mutate(values)}
      >
        <Form.Item name="hero_eyebrow" label="Eyebrow badge text">
          <Input placeholder="Fashion retail, reimagined as SaaS" />
        </Form.Item>
        <Space wrap style={{ width: "100%" }}>
          <Form.Item name="hero_title_line1" label="Headline - first line" style={{ width: 320 }}>
            <Input placeholder="Run your boutique" />
          </Form.Item>
          <Form.Item name="hero_title_highlight" label="Headline - highlighted line" style={{ width: 320 }}>
            <Input placeholder="like a flagship." />
          </Form.Item>
        </Space>
        <Form.Item name="hero_subtitle" label="Subtitle">
          <Input.TextArea rows={3} placeholder="POS, inventory, CRM..." />
        </Form.Item>
        <Space wrap style={{ width: "100%" }}>
          <Form.Item name="hero_cta_primary" label="Primary button label" style={{ width: 260 }}>
            <Input placeholder="Start free — 30 days" />
          </Form.Item>
          <Form.Item name="hero_cta_secondary" label="Secondary button label" style={{ width: 260 }}>
            <Input placeholder="See pricing" />
          </Form.Item>
        </Space>
        <Button type="primary" htmlType="submit" loading={saveMutation.isPending}>Save</Button>
      </Form>
    </Card>
  );
}

function ValueStripTab() {
  const queryClient = useQueryClient();
  const [form] = Form.useForm();
  const { data, isLoading } = useQuery({
    queryKey: ["admin-landing-content"],
    queryFn: () => getAdminLandingContent().then((r) => r.data),
  });

  const saveMutation = useMutation({
    mutationFn: updateLandingContent,
    onSuccess: () => {
      message.success("Value strip saved");
      queryClient.invalidateQueries({ queryKey: ["admin-landing-content"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to save"),
  });

  if (isLoading || !data) return null;

  return (
    <Card>
      <Typography.Paragraph type="secondary">
        The dark strip of short claims shown right under the hero banner.
      </Typography.Paragraph>
      <Form
        form={form}
        layout="vertical"
        initialValues={{ value_strip: data.value_strip.length ? data.value_strip : [""] }}
        onFinish={(values) => saveMutation.mutate({ value_strip: values.value_strip.filter((v: string) => v?.trim()) })}
      >
        <Form.List name="value_strip">
          {(fields, { add, remove }) => (
            <>
              {fields.map((field) => (
                <Space key={field.key} style={{ display: "flex", marginBottom: 8 }} align="baseline">
                  <Form.Item {...field} style={{ width: 420, marginBottom: 0 }}>
                    <Input placeholder="Built for multi-outlet fashion retailers" />
                  </Form.Item>
                  <Button icon={<DeleteOutlined />} onClick={() => remove(field.name)} />
                </Space>
              ))}
              <Button type="dashed" icon={<PlusOutlined />} onClick={() => add("")} style={{ marginBottom: 16 }}>
                Add line
              </Button>
            </>
          )}
        </Form.List>
        <div>
          <Button type="primary" htmlType="submit" loading={saveMutation.isPending}>Save</Button>
        </div>
      </Form>
    </Card>
  );
}

function FeaturesTab() {
  const queryClient = useQueryClient();
  const [form] = Form.useForm();
  const { data, isLoading } = useQuery({
    queryKey: ["admin-landing-content"],
    queryFn: () => getAdminLandingContent().then((r) => r.data),
  });

  const saveMutation = useMutation({
    mutationFn: updateLandingContent,
    onSuccess: () => {
      message.success("Features saved");
      queryClient.invalidateQueries({ queryKey: ["admin-landing-content"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to save"),
  });

  if (isLoading || !data) return null;

  return (
    <Card>
      <Typography.Paragraph type="secondary">
        The "Everything your store needs" feature grid.
      </Typography.Paragraph>
      <Form
        form={form}
        layout="vertical"
        initialValues={{ features: data.features.length ? data.features : [{ icon: "shop", title: "", body: "" }] }}
        onFinish={(values) =>
          saveMutation.mutate({ features: values.features.filter((f: any) => f?.title?.trim()) })
        }
      >
        <Form.List name="features">
          {(fields, { add, remove }) => (
            <>
              {fields.map((field) => (
                <Card key={field.key} size="small" style={{ marginBottom: 12 }}
                  extra={<Button icon={<DeleteOutlined />} size="small" onClick={() => remove(field.name)} />}
                >
                  <Space wrap style={{ width: "100%" }}>
                    <Form.Item name={[field.name, "icon"]} label="Icon" style={{ width: 180 }}>
                      <Select options={ICON_OPTIONS} />
                    </Form.Item>
                    <Form.Item name={[field.name, "title"]} label="Title" style={{ width: 240 }}>
                      <Input placeholder="Point of sale" />
                    </Form.Item>
                  </Space>
                  <Form.Item name={[field.name, "body"]} label="Description">
                    <Input.TextArea rows={2} placeholder="Fast, barcode-driven checkout..." />
                  </Form.Item>
                </Card>
              ))}
              <Button type="dashed" icon={<PlusOutlined />} onClick={() => add({ icon: "shop", title: "", body: "" })} style={{ marginBottom: 16 }}>
                Add feature
              </Button>
            </>
          )}
        </Form.List>
        <div>
          <Button type="primary" htmlType="submit" loading={saveMutation.isPending}>Save</Button>
        </div>
      </Form>
    </Card>
  );
}

function HowItWorksTab() {
  const queryClient = useQueryClient();
  const [form] = Form.useForm();
  const { data, isLoading } = useQuery({
    queryKey: ["admin-landing-content"],
    queryFn: () => getAdminLandingContent().then((r) => r.data),
  });

  const saveMutation = useMutation({
    mutationFn: updateLandingContent,
    onSuccess: () => {
      message.success("Steps saved");
      queryClient.invalidateQueries({ queryKey: ["admin-landing-content"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to save"),
  });

  if (isLoading || !data) return null;

  return (
    <Card>
      <Typography.Paragraph type="secondary">
        The "Live in three steps" section. Numbered automatically in order.
      </Typography.Paragraph>
      <Form
        form={form}
        layout="vertical"
        initialValues={{ how_it_works: data.how_it_works.length ? data.how_it_works : [{ title: "", body: "" }] }}
        onFinish={(values) =>
          saveMutation.mutate({ how_it_works: values.how_it_works.filter((s: any) => s?.title?.trim()) })
        }
      >
        <Form.List name="how_it_works">
          {(fields, { add, remove }) => (
            <>
              {fields.map((field, i) => (
                <Card key={field.key} size="small" title={`Step ${i + 1}`} style={{ marginBottom: 12 }}
                  extra={<Button icon={<DeleteOutlined />} size="small" onClick={() => remove(field.name)} />}
                >
                  <Form.Item name={[field.name, "title"]} label="Title">
                    <Input placeholder="Create your store" />
                  </Form.Item>
                  <Form.Item name={[field.name, "body"]} label="Description">
                    <Input.TextArea rows={2} placeholder="Pick a store name and URL..." />
                  </Form.Item>
                </Card>
              ))}
              <Button type="dashed" icon={<PlusOutlined />} onClick={() => add({ title: "", body: "" })} style={{ marginBottom: 16 }}>
                Add step
              </Button>
            </>
          )}
        </Form.List>
        <div>
          <Button type="primary" htmlType="submit" loading={saveMutation.isPending}>Save</Button>
        </div>
      </Form>
    </Card>
  );
}

function FaqTab() {
  const queryClient = useQueryClient();
  const [form] = Form.useForm();
  const { data, isLoading } = useQuery({
    queryKey: ["admin-landing-content"],
    queryFn: () => getAdminLandingContent().then((r) => r.data),
  });

  const saveMutation = useMutation({
    mutationFn: updateLandingContent,
    onSuccess: () => {
      message.success("FAQs saved");
      queryClient.invalidateQueries({ queryKey: ["admin-landing-content"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to save"),
  });

  if (isLoading || !data) return null;

  return (
    <Card>
      <Form
        form={form}
        layout="vertical"
        initialValues={{ faqs: data.faqs.length ? data.faqs : [{ q: "", a: "" }] }}
        onFinish={(values) => saveMutation.mutate({ faqs: values.faqs.filter((f: any) => f?.q?.trim()) })}
      >
        <Form.List name="faqs">
          {(fields, { add, remove }) => (
            <>
              {fields.map((field) => (
                <Card key={field.key} size="small" style={{ marginBottom: 12 }}
                  extra={<Button icon={<DeleteOutlined />} size="small" onClick={() => remove(field.name)} />}
                >
                  <Form.Item name={[field.name, "q"]} label="Question">
                    <Input placeholder="Do I need a credit card to start the free trial?" />
                  </Form.Item>
                  <Form.Item name={[field.name, "a"]} label="Answer">
                    <Input.TextArea rows={2} />
                  </Form.Item>
                </Card>
              ))}
              <Button type="dashed" icon={<PlusOutlined />} onClick={() => add({ q: "", a: "" })} style={{ marginBottom: 16 }}>
                Add question
              </Button>
            </>
          )}
        </Form.List>
        <div>
          <Button type="primary" htmlType="submit" loading={saveMutation.isPending}>Save</Button>
        </div>
      </Form>
    </Card>
  );
}

function LegalPagesTab() {
  const queryClient = useQueryClient();
  const [termsForm] = Form.useForm();
  const [privacyForm] = Form.useForm();
  const { data, isLoading } = useQuery({
    queryKey: ["admin-legal-pages"],
    queryFn: () => listAdminLegalPages().then((r) => r.data),
  });

  const termsSaveMutation = useMutation({
    mutationFn: (values: { title: string; content: string }) => upsertLegalPage("terms", values),
    onSuccess: () => {
      message.success("Terms of Service saved");
      queryClient.invalidateQueries({ queryKey: ["admin-legal-pages"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to save"),
  });

  const privacySaveMutation = useMutation({
    mutationFn: (values: { title: string; content: string }) => upsertLegalPage("privacy", values),
    onSuccess: () => {
      message.success("Privacy Policy saved");
      queryClient.invalidateQueries({ queryKey: ["admin-legal-pages"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to save"),
  });

  if (isLoading || !data) return null;

  const terms = data.find((p) => p.slug === "terms");
  const privacy = data.find((p) => p.slug === "privacy");

  return (
    <Space direction="vertical" size="large" style={{ width: "100%" }}>
      <Alert
        type="info"
        showIcon
        message="Legal pages"
        description="Leave blank to keep showing the built-in template copy at /terms and /privacy. Publishing here overrides it."
      />
      <Card title="Terms of Service">
        <Form
          form={termsForm}
          layout="vertical"
          initialValues={{ title: terms?.title || "Terms of Service", content: terms?.content || "" }}
          onFinish={(values) => termsSaveMutation.mutate(values)}
        >
          <Form.Item name="title" label="Page title">
            <Input />
          </Form.Item>
          <Form.Item name="content" label="Content (plain text, blank lines separate paragraphs)">
            <Input.TextArea rows={10} placeholder="Leave blank to use the built-in template" />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={termsSaveMutation.isPending}>Save</Button>
        </Form>
      </Card>
      <Card title="Privacy Policy">
        <Form
          form={privacyForm}
          layout="vertical"
          initialValues={{ title: privacy?.title || "Privacy Policy", content: privacy?.content || "" }}
          onFinish={(values) => privacySaveMutation.mutate(values)}
        >
          <Form.Item name="title" label="Page title">
            <Input />
          </Form.Item>
          <Form.Item name="content" label="Content (plain text, blank lines separate paragraphs)">
            <Input.TextArea rows={10} placeholder="Leave blank to use the built-in template" />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={privacySaveMutation.isPending}>Save</Button>
        </Form>
      </Card>
    </Space>
  );
}

export default function LandingPageSettings() {
  return (
    <div>
      <Typography.Title level={3} style={{ margin: 0, marginBottom: 20 }}>
        Landing Page Settings
      </Typography.Title>
      <Tabs
        items={[
          { key: "hero", label: "Hero", children: <HeroTab /> },
          { key: "value-strip", label: "Value strip", children: <ValueStripTab /> },
          { key: "features", label: "Features", children: <FeaturesTab /> },
          { key: "how-it-works", label: "How it works", children: <HowItWorksTab /> },
          { key: "faq", label: "FAQ", children: <FaqTab /> },
          { key: "legal", label: "Legal pages", children: <LegalPagesTab /> },
        ]}
      />
    </div>
  );
}
