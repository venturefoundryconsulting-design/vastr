import { ArrowLeftOutlined, KeyOutlined, StopOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Button,
  Card,
  Col,
  Descriptions,
  Form,
  Input,
  Modal,
  Popconfirm,
  Row,
  Select,
  Statistic,
  Table,
  Tabs,
  Tag,
  Typography,
  message,
} from "antd";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  deleteTenant,
  getTenant,
  getTenantActivity,
  getTenantUsage,
  listTenantUsers,
  resetTenantUserPassword,
  suspendTenant,
  updateTenant,
} from "../api/endpoints";
import type { AppUser } from "../api/types";

export default function TenantDetail() {
  const { id } = useParams();
  const tenantId = Number(id);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [editForm] = Form.useForm();
  const [resetPasswordUser, setResetPasswordUser] = useState<AppUser | null>(null);
  const [newPassword, setNewPassword] = useState("");

  const { data: tenant, isLoading } = useQuery({
    queryKey: ["admin-tenant", tenantId],
    queryFn: () => getTenant(tenantId).then((r) => r.data),
  });
  const { data: usage } = useQuery({
    queryKey: ["admin-tenant-usage", tenantId],
    queryFn: () => getTenantUsage(tenantId).then((r) => r.data),
  });
  const { data: users } = useQuery({
    queryKey: ["admin-tenant-users", tenantId],
    queryFn: () => listTenantUsers(tenantId).then((r) => r.data),
  });
  const { data: activity } = useQuery({
    queryKey: ["admin-tenant-activity", tenantId],
    queryFn: () => getTenantActivity(tenantId).then((r) => r.data),
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["admin-tenant", tenantId] });
    queryClient.invalidateQueries({ queryKey: ["admin-tenants"] });
  };

  const updateMutation = useMutation({
    mutationFn: (values: Record<string, unknown>) => updateTenant(tenantId, values),
    onSuccess: () => {
      message.success("Tenant updated");
      invalidate();
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to update tenant"),
  });

  const suspendMutation = useMutation({
    mutationFn: () => suspendTenant(tenantId),
    onSuccess: () => {
      message.success("Tenant suspended - its users can no longer log in");
      invalidate();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteTenant(tenantId),
    onSuccess: () => {
      message.success("Tenant deactivated");
      invalidate();
    },
  });

  const resetPasswordMutation = useMutation({
    mutationFn: () => resetTenantUserPassword(tenantId, resetPasswordUser!.id, newPassword),
    onSuccess: () => {
      message.success(`Password reset for ${resetPasswordUser?.name}`);
      setResetPasswordUser(null);
      setNewPassword("");
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to reset password"),
  });

  if (isLoading || !tenant) return null;

  return (
    <div>
      <Button icon={<ArrowLeftOutlined />} type="text" onClick={() => navigate("/platform-admin/tenants")} style={{ marginBottom: 12 }}>
        Back to Tenants
      </Button>
      <Row justify="space-between" align="middle" style={{ marginBottom: 20 }}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          {tenant.company_name}
        </Typography.Title>
        <div style={{ display: "flex", gap: 8 }}>
          <Popconfirm
            title="Suspend this tenant?"
            description="Its users will be unable to log in until reactivated."
            onConfirm={() => suspendMutation.mutate()}
          >
            <Button icon={<StopOutlined />} danger disabled={tenant.subscription_status === "suspended"}>
              Suspend
            </Button>
          </Popconfirm>
          <Popconfirm
            title="Deactivate this tenant?"
            description="Deactivates and cancels the subscription. Data is kept, not deleted."
            onConfirm={() => deleteMutation.mutate()}
          >
            <Button danger disabled={!tenant.is_active}>
              Deactivate
            </Button>
          </Popconfirm>
        </div>
      </Row>

      <Row gutter={16} style={{ marginBottom: 20 }}>
        <Col span={6}>
          <Card><Statistic title="Users" value={usage?.user_count ?? "-"} suffix={usage ? `/ ${usage.active_user_count} active` : ""} /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="Outlets" value={usage?.outlet_count ?? "-"} /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="Products" value={usage?.product_count ?? "-"} /></Card>
        </Col>
        <Col span={6}>
          <Card>
            <Typography.Text type="secondary" style={{ fontSize: 13 }}>Plan / Status</Typography.Text>
            <div style={{ marginTop: 8 }}>
              <Tag color="gold">{tenant.subscription_plan.toUpperCase()}</Tag>
              <Tag color={tenant.subscription_status === "active" ? "green" : "orange"}>
                {tenant.subscription_status.toUpperCase()}
              </Tag>
            </div>
          </Card>
        </Col>
      </Row>

      <Tabs
        items={[
          {
            key: "details",
            label: "Details",
            children: (
              <Card style={{ maxWidth: 560 }}>
                <Form
                  form={editForm}
                  layout="vertical"
                  initialValues={tenant}
                  onFinish={(values) => updateMutation.mutate(values)}
                >
                  <Form.Item name="company_name" label="Company name">
                    <Input />
                  </Form.Item>
                  <Form.Item name="primary_color" label="Primary color">
                    <Input placeholder="#9d174d" />
                  </Form.Item>
                  <Form.Item name="timezone" label="Timezone">
                    <Input />
                  </Form.Item>
                  <Form.Item name="currency" label="Currency">
                    <Input />
                  </Form.Item>
                  <Form.Item name="country" label="Country">
                    <Input />
                  </Form.Item>
                  <Form.Item name="subscription_plan" label="Plan">
                    <Select
                      options={["free", "starter", "professional", "enterprise"].map((v) => ({ value: v, label: v }))}
                    />
                  </Form.Item>
                  <Form.Item name="subscription_status" label="Subscription status">
                    <Select
                      options={["trial", "active", "suspended", "cancelled"].map((v) => ({ value: v, label: v }))}
                    />
                  </Form.Item>
                  <Button type="primary" htmlType="submit" loading={updateMutation.isPending}>
                    Save
                  </Button>
                </Form>
              </Card>
            ),
          },
          {
            key: "users",
            label: "Users",
            children: (
              <Table
                rowKey="id"
                dataSource={users}
                scroll={{ x: "max-content" }}
                columns={[
                  { title: "Name", dataIndex: "name" },
                  { title: "Email", dataIndex: "email" },
                  { title: "Role", dataIndex: "role" },
                  {
                    title: "",
                    key: "actions",
                    render: (_: unknown, u: AppUser) => (
                      <Button size="small" icon={<KeyOutlined />} onClick={() => setResetPasswordUser(u)}>
                        Reset password
                      </Button>
                    ),
                  },
                ]}
              />
            ),
          },
          {
            key: "activity",
            label: "Activity",
            children: (
              <Table
                rowKey="id"
                dataSource={activity}
                scroll={{ x: "max-content" }}
                columns={[
                  { title: "When", dataIndex: "created_at", render: (v: string) => new Date(v).toLocaleString() },
                  { title: "Action", dataIndex: "action" },
                  { title: "Entity", render: (_: unknown, r: any) => (r.entity_type ? `${r.entity_type} #${r.entity_id}` : "-") },
                ]}
              />
            ),
          },
        ]}
      />

      <Descriptions size="small" column={2} style={{ marginTop: 24 }} bordered items={[
        { key: "slug", label: "Slug", children: tenant.slug },
        { key: "created", label: "Created", children: new Date(tenant.created_at).toLocaleString() },
      ]} />

      <Modal
        title={`Reset password for ${resetPasswordUser?.name}`}
        open={!!resetPasswordUser}
        onCancel={() => setResetPasswordUser(null)}
        onOk={() => resetPasswordMutation.mutate()}
        confirmLoading={resetPasswordMutation.isPending}
        okButtonProps={{ disabled: newPassword.length < 6 }}
      >
        <Input.Password
          placeholder="New password (min 6 characters)"
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
        />
      </Modal>
    </div>
  );
}
