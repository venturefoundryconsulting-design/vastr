import { PlusOutlined, SearchOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Form, Input, Modal, Select, Space, Table, Tag, Typography, message } from "antd";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { createTenant, listTenants } from "../api/endpoints";
import type { Tenant } from "../api/types";

const PLAN_COLORS: Record<string, string> = {
  free: "default",
  starter: "blue",
  professional: "purple",
  enterprise: "gold",
};

const STATUS_COLORS: Record<string, string> = {
  trial: "blue",
  active: "green",
  suspended: "orange",
  cancelled: "red",
};

export default function TenantsList() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();

  const { data: tenants, isLoading } = useQuery({
    queryKey: ["admin-tenants", search],
    queryFn: () => listTenants(search || undefined).then((r) => r.data),
  });

  const createMutation = useMutation({
    mutationFn: createTenant,
    onSuccess: () => {
      message.success("Tenant created");
      setModalOpen(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ["admin-tenants"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to create tenant"),
  });

  const columns = [
    {
      title: "Company",
      dataIndex: "company_name",
      render: (v: string, r: Tenant) => (
        <a onClick={() => navigate(`/platform-admin/tenants/${r.id}`)}>{v}</a>
      ),
    },
    { title: "Slug", dataIndex: "slug" },
    {
      title: "Plan",
      dataIndex: "subscription_plan",
      render: (v: string) => <Tag color={PLAN_COLORS[v]}>{v.toUpperCase()}</Tag>,
    },
    {
      title: "Status",
      dataIndex: "subscription_status",
      render: (v: string) => <Tag color={STATUS_COLORS[v]}>{v.toUpperCase()}</Tag>,
    },
    {
      title: "Active",
      dataIndex: "is_active",
      render: (v: boolean) => (v ? <Tag color="green">Yes</Tag> : <Tag color="red">No</Tag>),
    },
    { title: "Created", dataIndex: "created_at", render: (v: string) => new Date(v).toLocaleDateString() },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16, width: "100%", justifyContent: "space-between" }}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          Tenants
        </Typography.Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
          New Tenant
        </Button>
      </Space>

      <Input
        placeholder="Search by company name or slug"
        prefix={<SearchOutlined />}
        style={{ maxWidth: 360, marginBottom: 16 }}
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        allowClear
      />

      <Table rowKey="id" loading={isLoading} columns={columns} dataSource={tenants} scroll={{ x: "max-content" }} />

      <Modal
        title="New Tenant"
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={createMutation.isPending}
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{ subscription_plan: "free" }}
          onFinish={(values) => createMutation.mutate(values)}
        >
          <Form.Item name="company_name" label="Company name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item
            name="slug"
            label="Slug"
            tooltip="Short unique identifier, e.g. kavya-boutique"
            rules={[{ required: true, pattern: /^[a-z0-9-]+$/, message: "Lowercase letters, numbers, and hyphens only" }]}
          >
            <Input />
          </Form.Item>
          <Form.Item name="subscription_plan" label="Plan">
            <Select
              options={[
                { value: "free", label: "Free" },
                { value: "starter", label: "Starter" },
                { value: "professional", label: "Professional" },
                { value: "enterprise", label: "Enterprise" },
              ]}
            />
          </Form.Item>
          <Typography.Text type="secondary" style={{ display: "block", marginBottom: 12 }}>
            The tenant's first user, created as its Owner:
          </Typography.Text>
          <Form.Item name="owner_name" label="Owner name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="owner_email" label="Owner email" rules={[{ required: true, type: "email" }]}>
            <Input />
          </Form.Item>
          <Form.Item name="owner_password" label="Owner password" rules={[{ required: true, min: 6 }]}>
            <Input.Password />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
