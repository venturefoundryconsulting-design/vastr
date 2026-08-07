import { EditOutlined, PlusOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Form, Input, Modal, Space, Switch, Table, Tag, Typography, message } from "antd";
import { useState } from "react";
import { createOutlet, listOutlets, updateOutlet } from "../api/endpoints";
import type { Outlet } from "../api/types";

export default function Outlets() {
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editingOutlet, setEditingOutlet] = useState<Outlet | null>(null);
  const [form] = Form.useForm();

  const { data: outlets, isLoading } = useQuery({
    queryKey: ["outlets"],
    queryFn: () => listOutlets().then((r) => r.data),
  });

  const createMutation = useMutation({
    mutationFn: createOutlet,
    onSuccess: () => {
      message.success("Outlet created");
      closeModal();
      queryClient.invalidateQueries({ queryKey: ["outlets"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to create outlet"),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<Outlet> }) => updateOutlet(id, data),
    onSuccess: () => {
      message.success("Outlet updated");
      closeModal();
      queryClient.invalidateQueries({ queryKey: ["outlets"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to update outlet"),
  });

  const toggleActive = useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) => updateOutlet(id, { is_active }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["outlets"] }),
  });

  const closeModal = () => {
    setModalOpen(false);
    setEditingOutlet(null);
    form.resetFields();
  };

  const openCreate = () => {
    form.resetFields();
    setEditingOutlet(null);
    setModalOpen(true);
  };

  const openEdit = (outlet: Outlet) => {
    setEditingOutlet(outlet);
    form.setFieldsValue(outlet);
    setModalOpen(true);
  };

  const columns = [
    { title: "Name", dataIndex: "name" },
    { title: "Code", dataIndex: "code" },
    { title: "Address", dataIndex: "address" },
    {
      title: "Type",
      dataIndex: "is_warehouse",
      render: (v: boolean) => (v ? <Tag color="purple">Warehouse</Tag> : <Tag color="blue">Store</Tag>),
    },
    {
      title: "Active",
      dataIndex: "is_active",
      render: (v: boolean, r: Outlet) => (
        <Switch checked={v} onChange={(checked) => toggleActive.mutate({ id: r.id, is_active: checked })} />
      ),
    },
    {
      title: "",
      key: "actions",
      render: (_: unknown, r: Outlet) => (
        <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(r)}>
          Edit
        </Button>
      ),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16, width: "100%", justifyContent: "space-between" }}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          Outlets
        </Typography.Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          New Outlet
        </Button>
      </Space>

      <Table rowKey="id" loading={isLoading} columns={columns} dataSource={outlets} scroll={{ x: "max-content" }} />

      <Modal
        title={editingOutlet ? "Edit Outlet" : "New Outlet"}
        open={modalOpen}
        onCancel={closeModal}
        onOk={() => form.submit()}
        confirmLoading={createMutation.isPending || updateMutation.isPending}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={(values) =>
            editingOutlet
              ? updateMutation.mutate({ id: editingOutlet.id, data: values })
              : createMutation.mutate(values)
          }
        >
          <Form.Item name="name" label="Name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item
            name="code"
            label="Code"
            rules={[{ required: true }]}
            tooltip={
              editingOutlet
                ? "Code can't be changed once created - it's referenced by existing stock and transfer records"
                : "Short unique code, e.g. ST-03"
            }
          >
            <Input disabled={!!editingOutlet} />
          </Form.Item>
          <Form.Item name="address" label="Address">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="phone" label="Phone">
            <Input />
          </Form.Item>
          <Form.Item name="is_warehouse" label="Is this a warehouse?" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
