import { PlusOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Form, Input, Modal, Select, Space, Switch, Table, Tag, Typography, message } from "antd";
import { useState } from "react";
import { createUser, listOutlets, listUsers, updateUser } from "../api/endpoints";
import type { AppUser } from "../api/types";

const ROLE_COLORS: Record<string, string> = {
  tenant_owner: "purple",
  admin: "red",
  manager: "gold",
  sales: "cyan",
  inventory: "geekblue",
  outlet_staff: "blue",
  viewer: "default",
};

const ROLE_OPTIONS = [
  { value: "tenant_owner", label: "Tenant Owner" },
  { value: "admin", label: "Admin" },
  { value: "manager", label: "Manager" },
  { value: "sales", label: "Sales" },
  { value: "inventory", label: "Inventory" },
  { value: "outlet_staff", label: "Outlet Staff" },
  { value: "viewer", label: "Viewer" },
];

export default function Users() {
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();

  const { data: users, isLoading } = useQuery({ queryKey: ["users"], queryFn: () => listUsers().then((r) => r.data) });
  const { data: outlets } = useQuery({ queryKey: ["outlets"], queryFn: () => listOutlets().then((r) => r.data) });

  const createMutation = useMutation({
    mutationFn: createUser,
    onSuccess: () => {
      message.success("User created");
      setModalOpen(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ["users"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to create user"),
  });

  const toggleActive = useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) => updateUser(id, { is_active }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  });

  const columns = [
    { title: "Name", dataIndex: "name" },
    { title: "Email", dataIndex: "email" },
    {
      title: "Role",
      dataIndex: "role",
      render: (v: string) => (
        <Tag color={ROLE_COLORS[v]}>{ROLE_OPTIONS.find((o) => o.value === v)?.label ?? v}</Tag>
      ),
    },
    {
      title: "Outlet",
      dataIndex: "outlet_id",
      render: (v: number | null) => outlets?.find((o) => o.id === v)?.name || "-",
    },
    {
      title: "Active",
      dataIndex: "is_active",
      render: (v: boolean, r: AppUser) => (
        <Switch checked={v} onChange={(checked) => toggleActive.mutate({ id: r.id, is_active: checked })} />
      ),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16, width: "100%", justifyContent: "space-between" }}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          Users
        </Typography.Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
          New User
        </Button>
      </Space>

      <Table rowKey="id" loading={isLoading} columns={columns} dataSource={users} />

      <Modal
        title="New User"
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={createMutation.isPending}
      >
        <Form form={form} layout="vertical" onFinish={(values) => createMutation.mutate(values)} initialValues={{ role: "outlet_staff" }}>
          <Form.Item name="name" label="Name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="email" label="Email" rules={[{ required: true, type: "email" }]}>
            <Input />
          </Form.Item>
          <Form.Item name="password" label="Password" rules={[{ required: true, min: 6 }]}>
            <Input.Password />
          </Form.Item>
          <Form.Item name="role" label="Role" rules={[{ required: true }]}>
            <Select options={ROLE_OPTIONS} />
          </Form.Item>
          <Form.Item name="outlet_id" label="Outlet">
            <Select allowClear options={outlets?.map((o) => ({ value: o.id, label: o.name }))} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
