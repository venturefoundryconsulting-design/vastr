import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Button,
  Card,
  Col,
  Form,
  Input,
  InputNumber,
  Modal,
  Row,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import { useState } from "react";
import {
  createTailor,
  getTailorWorkload,
  listTailors,
  updateTailor,
} from "../api/manufacturing-endpoints";
import type { PayModel, TailorOut } from "../api/manufacturing-types";

const PAY_MODEL_LABEL: Record<PayModel, string> = {
  per_garment: "Per garment",
  per_stage: "Per stage",
  per_piece: "Per piece",
  hourly: "Hourly",
  fixed: "Fixed",
};

export default function Tailors() {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<TailorOut | null>(null);
  const [creating, setCreating] = useState(false);
  const [form] = Form.useForm();

  const { data: tailors, isLoading } = useQuery({
    queryKey: ["tailors"],
    queryFn: () => listTailors().then((r) => r.data),
  });
  const { data: workload } = useQuery({
    queryKey: ["tailor-workload"],
    queryFn: () => getTailorWorkload().then((r) => r.data),
  });
  const workloadByTailor = new Map((workload ?? []).map((w) => [w.tailor_id, w]));

  const close = () => {
    setEditing(null);
    setCreating(false);
    form.resetFields();
  };

  const save = useMutation({
    mutationFn: (values: any) => (editing ? updateTailor(editing.id, values) : createTailor(values)),
    onSuccess: () => {
      message.success(editing ? "Tailor updated" : "Tailor added");
      queryClient.invalidateQueries({ queryKey: ["tailors"] });
      close();
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || "Could not save"),
  });

  const openCreate = () => {
    setCreating(true);
    form.setFieldsValue({ pay_model: "per_stage", default_rate: 0 });
  };
  const openEdit = (t: TailorOut) => {
    setEditing(t);
    form.setFieldsValue(t);
  };

  const columns = [
    { title: "Code", dataIndex: "code", width: 100, render: (v: string) => <code>{v}</code> },
    { title: "Name", dataIndex: "name" },
    { title: "Phone", dataIndex: "phone", render: (v: string | null) => v ?? "—" },
    {
      title: "Pay model",
      dataIndex: "pay_model",
      width: 130,
      render: (v: PayModel) => PAY_MODEL_LABEL[v] ?? v,
    },
    { title: "Rate", dataIndex: "default_rate", width: 100, align: "right" as const, render: (v: number) => `₹${Number(v).toFixed(2)}` },
    {
      title: "Active",
      key: "active",
      width: 90,
      render: (v: unknown, r: TailorOut) => <Tag color={r.is_active ? "green" : "default"}>{r.is_active ? "Active" : "Inactive"}</Tag>,
    },
    {
      title: "Workload",
      key: "workload",
      width: 220,
      render: (_: unknown, r: TailorOut) => {
        const w = workloadByTailor.get(r.id);
        if (!w) return "—";
        return (
          <Space size={4}>
            <Tag color="blue">{w.active} active</Tag>
            <Tag color="gold">{w.pending} pending</Tag>
            {w.overdue > 0 && <Tag color="red">{w.overdue} overdue</Tag>}
          </Space>
        );
      },
    },
    {
      title: "",
      key: "actions",
      width: 80,
      render: (_: unknown, r: TailorOut) => (
        <Button size="small" onClick={() => openEdit(r)}>
          Edit
        </Button>
      ),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16, width: "100%", justifyContent: "space-between" }}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          Tailors
        </Typography.Title>
        <Button type="primary" onClick={openCreate}>
          Add tailor
        </Button>
      </Space>

      <Card size="small" styles={{ body: { padding: 0 } }}>
        <Table rowKey="id" loading={isLoading} columns={columns} dataSource={tailors} pagination={{ pageSize: 20 }} scroll={{ x: "max-content" }} />
      </Card>

      <Modal
        title={editing ? `Edit ${editing.name}` : "Add tailor"}
        open={creating || !!editing}
        onCancel={close}
        onOk={() => form.submit()}
        confirmLoading={save.isPending}
      >
        <Form form={form} layout="vertical" onFinish={(v) => save.mutate(v)}>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="code" label="Code" rules={[{ required: true }]}>
                <Input disabled={!!editing} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="name" label="Name" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="phone" label="Phone">
            <Input />
          </Form.Item>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="pay_model" label="Pay model" rules={[{ required: true }]}>
                <Select
                  options={Object.entries(PAY_MODEL_LABEL).map(([value, label]) => ({ value, label }))}
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="default_rate" label="Default rate (₹)">
                <InputNumber min={0} step={1} precision={2} style={{ width: "100%" }} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="notes" label="Notes">
            <Input.TextArea rows={2} />
          </Form.Item>
          {editing && (
            <Form.Item name="is_active" label="Active" valuePropName="checked">
              <Switch />
            </Form.Item>
          )}
        </Form>
      </Modal>
    </div>
  );
}
