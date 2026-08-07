import { PlusOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Form, Input, InputNumber, Modal, Select, Space, Table, Tag, Typography, message } from "antd";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { createTransfer, listOutlets, listTransfers, searchVariants } from "../api/endpoints";
import type { Transfer, TransferStatus, VariantWithStock } from "../api/types";

const STATUS_COLORS: Record<TransferStatus, string> = {
  requested: "default",
  dispatched: "blue",
  received: "green",
  cancelled: "red",
};

export default function Transfers() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();
  const [options, setOptions] = useState<VariantWithStock[]>([]);

  const { data: transfers, isLoading } = useQuery({
    queryKey: ["transfers"],
    queryFn: () => listTransfers().then((r) => r.data),
  });
  const { data: outlets } = useQuery({ queryKey: ["outlets"], queryFn: () => listOutlets().then((r) => r.data) });

  const createMutation = useMutation({
    mutationFn: createTransfer,
    onSuccess: (res) => {
      message.success("Transfer request created");
      setModalOpen(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ["transfers"] });
      navigate(`/transfers/${res.data.id}`);
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to create transfer"),
  });

  const handleSearch = async (q: string) => {
    if (!q) return;
    const res = await searchVariants(q);
    setOptions(res.data);
  };

  const columns = [
    {
      title: "Transfer #",
      dataIndex: "transfer_number",
      render: (v: string, r: Transfer) => <a onClick={() => navigate(`/transfers/${r.id}`)}>{v}</a>,
    },
    { title: "From", dataIndex: "source_outlet_name" },
    { title: "To", dataIndex: "dest_outlet_name" },
    {
      title: "Status",
      dataIndex: "status",
      render: (s: TransferStatus) => <Tag color={STATUS_COLORS[s]}>{s}</Tag>,
    },
    { title: "Items", key: "items", render: (_: unknown, r: Transfer) => r.items.length },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16, width: "100%", justifyContent: "space-between" }}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          Stock Transfers
        </Typography.Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
          New Transfer
        </Button>
      </Space>

      <Table rowKey="id" loading={isLoading} columns={columns} dataSource={transfers} pagination={{ pageSize: 15 }} scroll={{ x: "max-content" }} />

      <Modal
        title="New Stock Transfer"
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={createMutation.isPending}
        width={720}
      >
        <Form form={form} layout="vertical" onFinish={(values) => createMutation.mutate(values)} initialValues={{ items: [{}] }}>
          <Space style={{ width: "100%" }} size="large">
            <Form.Item name="source_outlet_id" label="From" rules={[{ required: true }]} style={{ width: 260 }}>
              <Select options={outlets?.map((o) => ({ value: o.id, label: o.name }))} />
            </Form.Item>
            <Form.Item name="dest_outlet_id" label="To" rules={[{ required: true }]} style={{ width: 260 }}>
              <Select options={outlets?.map((o) => ({ value: o.id, label: o.name }))} />
            </Form.Item>
          </Space>
          <Form.Item name="notes" label="Notes">
            <Input.TextArea rows={2} />
          </Form.Item>

          <Typography.Title level={5}>Items</Typography.Title>
          <Form.List name="items">
            {(fields, { add, remove }) => (
              <>
                {fields.map((field) => (
                  <Space key={field.key} align="baseline" wrap style={{ marginBottom: 8 }}>
                    <Form.Item name={[field.name, "variant_id"]} rules={[{ required: true }]}>
                      <Select
                        showSearch
                        placeholder="Search product / SKU"
                        style={{ width: 300 }}
                        filterOption={false}
                        onSearch={handleSearch}
                        options={options.map((o) => ({
                          value: o.id,
                          label: `${o.product_name} - ${[o.color, o.size].filter(Boolean).join("/")} (${o.sku}) - stock: ${o.total_stock}`,
                        }))}
                      />
                    </Form.Item>
                    <Form.Item name={[field.name, "quantity_requested"]} rules={[{ required: true }]}>
                      <InputNumber placeholder="Qty" style={{ width: 100 }} />
                    </Form.Item>
                    {fields.length > 1 && (
                      <Button danger onClick={() => remove(field.name)}>
                        Remove
                      </Button>
                    )}
                  </Space>
                ))}
                <Button onClick={() => add()} icon={<PlusOutlined />}>
                  Add item
                </Button>
              </>
            )}
          </Form.List>
        </Form>
      </Modal>
    </div>
  );
}
