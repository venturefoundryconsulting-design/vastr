import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, Form, Input, InputNumber, Modal, Select, Statistic, Table, message } from "antd";
import { useState } from "react";
import { listOrderWastage, listWastageReasons, recordWastage } from "../api/manufacturing-endpoints";
import type { WastageEntry } from "../api/manufacturing-types";
import type { ProductionOrderDetail } from "../api/types";
import { formatQty, qtyInputProps } from "../utils/quantity";

/** Material that will never become product. Writes no ledger row - it left
 * physical stock at issue time, same as consumption. */
export default function WastagePanel({ order }: { order: ProductionOrderDetail }) {
  const queryClient = useQueryClient();
  const [recording, setRecording] = useState(false);
  const [form] = Form.useForm();

  const { data, isLoading } = useQuery({
    queryKey: ["order-wastage", order.id],
    queryFn: () => listOrderWastage(order.id).then((r) => r.data),
  });
  const { data: reasons } = useQuery({
    queryKey: ["wastage-reasons"],
    queryFn: () => listWastageReasons().then((r) => r.data),
    enabled: recording,
  });

  const materialOptions = order.materials
    .filter((m) => !m.is_subassembly)
    .map((m) => ({ value: m.item_id, label: `${m.name} (${m.sku})` }));

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["order-wastage", order.id] });
    queryClient.invalidateQueries({ queryKey: ["production-cost", order.id] });
  };

  const submit = useMutation({
    mutationFn: (v: any) =>
      recordWastage(order.id, {
        material_id: v.material_id, quantity: v.quantity, reason_id: v.reason_id, notes: v.notes,
      }),
    onSuccess: () => {
      message.success("Wastage recorded");
      setRecording(false);
      form.resetFields();
      refresh();
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || "Could not record wastage"),
  });

  return (
    <Card
      size="small"
      title="Wastage"
      loading={isLoading}
      extra={
        <Button size="small" type="primary" onClick={() => setRecording(true)}>
          Record wastage
        </Button>
      }
    >
      {data && (
        <Statistic
          title="Total wastage cost"
          value={Number(data.total_cost)}
          precision={2}
          prefix="₹"
          style={{ marginBottom: 12 }}
        />
      )}
      <Table<WastageEntry>
        rowKey="id"
        size="small"
        pagination={false}
        dataSource={data?.entries ?? []}
        locale={{ emptyText: "No wastage recorded" }}
        columns={[
          {
            title: "Material",
            key: "m",
            render: (_: unknown, r: WastageEntry) => (
              <span>
                {r.name} <code style={{ fontSize: 11 }}>{r.sku}</code>
              </span>
            ),
          },
          { title: "Quantity", dataIndex: "quantity", width: 100, align: "right", render: formatQty },
          { title: "Reason", dataIndex: "reason", width: 140, render: (v: string | null) => v ?? "—" },
          { title: "Tailor", dataIndex: "tailor_name", width: 120, render: (v: string | null) => v ?? "—" },
          { title: "Notes", dataIndex: "notes", render: (v: string | null) => v ?? "—" },
        ]}
      />

      <Modal
        title="Record wastage"
        open={recording}
        onCancel={() => setRecording(false)}
        onOk={() => form.submit()}
        confirmLoading={submit.isPending}
      >
        <Form form={form} layout="vertical" onFinish={(v) => submit.mutate(v)}>
          <Form.Item name="material_id" label="Material" rules={[{ required: true }]}>
            <Select showSearch optionFilterProp="label" options={materialOptions} />
          </Form.Item>
          <Form.Item name="quantity" label="Quantity wasted" rules={[{ required: true }]}>
            <InputNumber {...qtyInputProps} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="reason_id" label="Reason">
            <Select
              allowClear
              options={(reasons ?? []).map((r) => ({ value: r.id, label: r.name }))}
            />
          </Form.Item>
          <Form.Item name="notes" label="Notes">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}
