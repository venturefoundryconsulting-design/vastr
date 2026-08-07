import { PlusOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Form, Input, Space, Tag, Typography, message } from "antd";
import { useState } from "react";
import { getPlatformDomainConfig, updatePlatformDomainConfig } from "../api/endpoints";

const HARDCODED_RESERVED = ["admin", "api", "www", "app", "vastr", "platform", "static", "assets"];

export default function SubdomainSettings() {
  const queryClient = useQueryClient();
  const [newSlug, setNewSlug] = useState("");
  const { data, isLoading } = useQuery({
    queryKey: ["platform-domain-config"],
    queryFn: () => getPlatformDomainConfig().then((r) => r.data),
  });

  const saveMutation = useMutation({
    mutationFn: updatePlatformDomainConfig,
    onSuccess: () => {
      message.success("Sub-domain settings saved");
      queryClient.invalidateQueries({ queryKey: ["platform-domain-config"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to save"),
  });

  if (isLoading || !data) return null;

  const addReserved = () => {
    const slug = newSlug.trim().toLowerCase();
    if (!slug) return;
    if (data.reserved_slugs.includes(slug)) {
      message.warning("Already reserved");
      return;
    }
    saveMutation.mutate({ reserved_slugs: [...data.reserved_slugs, slug] });
    setNewSlug("");
  };

  const removeReserved = (slug: string) => {
    saveMutation.mutate({ reserved_slugs: data.reserved_slugs.filter((s) => s !== slug) });
  };

  return (
    <div>
      <Typography.Title level={3} style={{ margin: 0, marginBottom: 20 }}>
        Sub-domain Config &amp; Settings
      </Typography.Title>

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 20 }}
        message="How store URLs work"
        description="Every new store claims a subdomain of the base domain below (e.g. yourstore.vastr.space) at signup. Reserved slugs can never be claimed by a store, on top of a small built-in list."
      />

      <Card title="Base domain" style={{ marginBottom: 20, maxWidth: 480 }}>
        <Form
          layout="vertical"
          initialValues={{ base_domain: data.base_domain }}
          onFinish={(values) => saveMutation.mutate(values)}
        >
          <Form.Item name="base_domain" label="Base domain" rules={[{ required: true }]}>
            <Input placeholder="vastr.space" />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={saveMutation.isPending}>
            Save
          </Button>
        </Form>
      </Card>

      <Card title="Reserved slugs" style={{ maxWidth: 640 }}>
        <Typography.Text type="secondary" style={{ display: "block", marginBottom: 12 }}>
          Always blocked, regardless of this list: {HARDCODED_RESERVED.join(", ")}
        </Typography.Text>
        <Space wrap style={{ marginBottom: 16 }}>
          {data.reserved_slugs.length === 0 && (
            <Typography.Text type="secondary">No extra reserved slugs yet</Typography.Text>
          )}
          {data.reserved_slugs.map((slug) => (
            <Tag key={slug} closable onClose={() => removeReserved(slug)}>
              {slug}
            </Tag>
          ))}
        </Space>
        <Space>
          <Input
            placeholder="e.g. support"
            value={newSlug}
            onChange={(e) => setNewSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""))}
            onPressEnter={addReserved}
            style={{ width: 220 }}
          />
          <Button icon={<PlusOutlined />} onClick={addReserved} loading={saveMutation.isPending}>
            Add
          </Button>
        </Space>
      </Card>
    </div>
  );
}
