import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Input, InputNumber, Modal, Space, Table, Typography, message } from "antd";
import { useState } from "react";
import { completeProductionOrder, listOutputs, recordOutput } from "../api/manufacturing-endpoints";
import type { ProductionOutputOut } from "../api/manufacturing-types";
import type { ProductionOrderDetail } from "../api/types";
import { formatQty, qtyInputProps } from "../utils/quantity";

/**
 * Records finished goods against a production order.
 *
 * Reaching the planned quantity completes the order automatically on the
 * server - nothing is being abandoned, so there's no decision to record.
 * Falling short leaves it PARTIALLY_COMPLETED, which the header's "Close
 * short" action (in ProductionOrderDetail) is what deliberately ends.
 */
export default function ProductionOutputPanel({ order }: { order: ProductionOrderDetail }) {
  const queryClient = useQueryClient();
  const [recording, setRecording] = useState(false);
  const [qty, setQty] = useState<number | null>(null);
  const [note, setNote] = useState("");

  const { data: outputs, isLoading } = useQuery({
    queryKey: ["production-outputs", order.id],
    queryFn: () => listOutputs(order.id).then((r) => r.data),
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["production-outputs", order.id] });
    queryClient.invalidateQueries({ queryKey: ["production-order", order.id] });
    queryClient.invalidateQueries({ queryKey: ["production-history", order.id] });
    queryClient.invalidateQueries({ queryKey: ["production-orders"] });
  };

  const record = useMutation({
    mutationFn: () => recordOutput(order.id, Number(qty), note || undefined),
    onSuccess: () => {
      message.success("Output recorded");
      setRecording(false);
      setQty(null);
      setNote("");
      refresh();
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || "Could not record output"),
  });

  const complete = useMutation({
    mutationFn: () => completeProductionOrder(order.id),
    onSuccess: () => {
      message.success("Production order completed");
      refresh();
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || "Could not complete"),
  });

  const canRecord = ["released", "in_progress", "partially_completed"].includes(order.status);
  const remaining = Number(order.remaining_quantity);

  return (
    <Card
      size="small"
      title="Output"
      loading={isLoading}
      extra={
        canRecord && (
          <Space>
            <Button size="small" type="primary" onClick={() => setRecording(true)}>
              Record output
            </Button>
            {Number(order.produced_quantity) >= Number(order.planned_quantity) &&
              order.status !== "completed" && (
                <Button size="small" onClick={() => complete.mutate()} loading={complete.isPending}>
                  Complete
                </Button>
              )}
          </Space>
        )
      }
    >
      <Space style={{ marginBottom: 10 }} size="large">
        <Typography.Text>
          Produced <b>{formatQty(order.produced_quantity)}</b> of {formatQty(order.planned_quantity)}{" "}
          {order.uom_code}
        </Typography.Text>
        {remaining > 0 && (
          <Typography.Text type="secondary">{formatQty(remaining)} remaining</Typography.Text>
        )}
      </Space>

      <Table<ProductionOutputOut>
        rowKey="id"
        size="small"
        pagination={false}
        dataSource={outputs ?? []}
        locale={{ emptyText: "No output recorded yet" }}
        columns={[
          {
            title: "Quantity",
            dataIndex: "quantity",
            width: 120,
            render: (v: number, r) => `${formatQty(v)} ${r.uom_code ?? ""}`,
          },
          { title: "Note", dataIndex: "note", render: (v: string | null) => v ?? "—" },
          {
            title: "When",
            dataIndex: "created_at",
            width: 170,
            render: (v: string | null) => (v ? new Date(v).toLocaleString() : "—"),
          },
        ]}
      />

      <Modal
        title="Record output"
        open={recording}
        onCancel={() => setRecording(false)}
        onOk={() => record.mutate()}
        confirmLoading={record.isPending}
        okButtonProps={{ disabled: !qty || qty <= 0 }}
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="This puts finished goods into stock"
          description={`Up to ${formatQty(remaining)} ${order.uom_code ?? ""} remains on this order.`}
        />
        <Typography.Paragraph>Quantity produced</Typography.Paragraph>
        <InputNumber
          {...qtyInputProps}
          max={remaining || undefined}
          value={qty}
          onChange={setQty}
          style={{ width: "100%", marginBottom: 12 }}
        />
        <Typography.Paragraph>Note (optional)</Typography.Paragraph>
        <Input value={note} onChange={(e) => setNote(e.target.value)} />
      </Modal>
    </Card>
  );
}
