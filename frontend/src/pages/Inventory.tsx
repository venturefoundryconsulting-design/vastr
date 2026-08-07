import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Form, InputNumber, Modal, Select, Space, Table, Tag, Typography, Input, message } from "antd";
import { useState } from "react";
import { adjustStock, listOutlets, listStock } from "../api/endpoints";
import type { StockLevelDetail } from "../api/types";
import ExportButton from "../components/ExportButton";

export default function Inventory() {
  const queryClient = useQueryClient();
  const [outletId, setOutletId] = useState<number | undefined>();
  const [adjustTarget, setAdjustTarget] = useState<StockLevelDetail | null>(null);
  const [form] = Form.useForm();

  const { data: outlets } = useQuery({ queryKey: ["outlets"], queryFn: () => listOutlets().then((r) => r.data) });
  const { data: stock, isLoading } = useQuery({
    queryKey: ["stock", outletId],
    queryFn: () => listStock(outletId ? { outlet_id: outletId } : undefined).then((r) => r.data),
  });

  const adjustMutation = useMutation({
    mutationFn: adjustStock,
    onSuccess: () => {
      message.success("Stock adjusted");
      setAdjustTarget(null);
      queryClient.invalidateQueries({ queryKey: ["stock"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Adjustment failed"),
  });

  const columns = [
    { title: "SKU", dataIndex: "sku" },
    { title: "Product", dataIndex: "product_name" },
    {
      title: "Variant",
      key: "variant",
      render: (_: unknown, r: StockLevelDetail) => [r.color, r.size].filter(Boolean).join(" / "),
    },
    { title: "Outlet", dataIndex: "outlet_name" },
    {
      title: "Quantity",
      dataIndex: "quantity",
      render: (qty: number, r: StockLevelDetail) => (
        <Tag color={qty <= r.reorder_level ? "red" : "green"}>{qty}</Tag>
      ),
    },
    { title: "Reorder level", dataIndex: "reorder_level" },
    {
      title: "",
      key: "actions",
      render: (_: unknown, r: StockLevelDetail) => (
        <Button size="small" onClick={() => setAdjustTarget(r)}>
          Adjust
        </Button>
      ),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16, width: "100%", justifyContent: "space-between" }}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          Inventory
        </Typography.Title>
        <Space>
          <Select
            allowClear
            placeholder="Filter by outlet"
            style={{ width: 240 }}
            options={outlets?.map((o) => ({ value: o.id, label: o.name }))}
            onChange={setOutletId}
          />
          <ExportButton url="/api/inventory/export" params={{ outlet_id: outletId }} filenameBase="inventory" />
        </Space>
      </Space>

      <Table rowKey="id" sticky loading={isLoading} columns={columns} dataSource={stock} pagination={{ pageSize: 20 }} scroll={{ x: "max-content" }} />

      <Modal
        title={`Adjust stock - ${adjustTarget?.sku ?? ""}`}
        open={!!adjustTarget}
        onCancel={() => setAdjustTarget(null)}
        onOk={() => form.submit()}
        confirmLoading={adjustMutation.isPending}
      >
        <Typography.Paragraph type="secondary">
          Current quantity at {adjustTarget?.outlet_name}: <b>{adjustTarget?.quantity}</b>
        </Typography.Paragraph>
        <Form
          form={form}
          layout="vertical"
          onFinish={(values) =>
            adjustTarget &&
            adjustMutation.mutate({
              variant_id: adjustTarget.variant_id,
              outlet_id: adjustTarget.outlet_id,
              quantity_delta: values.quantity_delta,
              note: values.note,
            })
          }
        >
          <Form.Item
            name="quantity_delta"
            label="Change (use negative to reduce)"
            rules={[{ required: true }]}
          >
            <InputNumber style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="note" label="Reason">
            <Input placeholder="e.g. damaged stock, physical count correction" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
