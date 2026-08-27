import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, Select, Space, Table, Tag, Typography, message } from "antd";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { assignWorkOrder, listTailors, listWorkOrders } from "../api/manufacturing-endpoints";
import type { WorkOrderOut, WorkOrderStatus } from "../api/manufacturing-types";
import { formatQty } from "../utils/quantity";

const STATUS_COLOR: Record<WorkOrderStatus, string> = {
  pending: "default", assigned: "blue", in_progress: "processing",
  paused: "orange", completed: "green", rework: "volcano", cancelled: "default",
};

/** The manager's view across every tailor's queue. Assignment happens here;
 * starting, pausing and completing happen on the tailor's own "My Work" screen. */
export default function WorkOrders() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [statusFilter, setStatusFilter] = useState<WorkOrderStatus | undefined>();
  const [tailorFilter, setTailorFilter] = useState<number | undefined>();
  const [assigningId, setAssigningId] = useState<number | null>(null);

  const { data: orders, isLoading } = useQuery({
    queryKey: ["work-orders", statusFilter, tailorFilter],
    queryFn: () => listWorkOrders({ status: statusFilter, tailor_id: tailorFilter }).then((r) => r.data),
  });
  const { data: tailors } = useQuery({
    queryKey: ["tailors"],
    queryFn: () => listTailors({ is_active: true }).then((r) => r.data),
  });

  const assign = useMutation({
    mutationFn: ({ id, tailorId }: { id: number; tailorId: number }) => assignWorkOrder(id, tailorId),
    onSuccess: () => {
      message.success("Assigned");
      setAssigningId(null);
      queryClient.invalidateQueries({ queryKey: ["work-orders"] });
      queryClient.invalidateQueries({ queryKey: ["tailor-workload"] });
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || "Could not assign"),
  });

  const columns = [
    { title: "WO", dataIndex: "wo_number", width: 110, render: (v: string) => <code>{v}</code> },
    {
      title: "Order",
      key: "order",
      render: (_: unknown, r: WorkOrderOut) => (
        <Space direction="vertical" size={0}>
          <a onClick={() => navigate(`/production/${r.production_order_id}`)}>{r.po_number}</a>
          <Typography.Text type="secondary" style={{ fontSize: 11 }}>{r.item_name}</Typography.Text>
        </Space>
      ),
    },
    { title: "Stage", dataIndex: "stage_name", width: 120 },
    {
      title: "Tailor",
      key: "tailor",
      width: 200,
      render: (_: unknown, r: WorkOrderOut) =>
        assigningId === r.id ? (
          <Select
            autoFocus
            size="small"
            style={{ width: 160 }}
            placeholder="Choose a tailor"
            options={tailors?.map((t) => ({ value: t.id, label: t.name }))}
            onChange={(tailorId) => assign.mutate({ id: r.id, tailorId })}
            onBlur={() => setAssigningId(null)}
          />
        ) : (
          <Button size="small" type="text" onClick={() => setAssigningId(r.id)}>
            {r.tailor_name ?? <Typography.Text type="secondary">Unassigned</Typography.Text>}
          </Button>
        ),
    },
    {
      title: "Quantity",
      key: "qty",
      width: 130,
      align: "right" as const,
      render: (_: unknown, r: WorkOrderOut) => `${formatQty(r.completed_quantity)} / ${formatQty(r.quantity)}`,
    },
    {
      title: "Status",
      dataIndex: "status",
      width: 120,
      render: (v: WorkOrderStatus, r: WorkOrderOut) => (
        <Space size={4}>
          <Tag color={STATUS_COLOR[v]}>{v.replace("_", " ")}</Tag>
          {r.is_overdue && <Tag color="red">overdue</Tag>}
        </Space>
      ),
    },
    { title: "Due", dataIndex: "due_date", width: 110, render: (v: string | null) => v ?? "—" },
    { title: "Labour cost", dataIndex: "labour_cost", width: 100, align: "right" as const, render: (v: number) => `₹${Number(v).toFixed(2)}` },
  ];

  return (
    <div>
      <Typography.Title level={3} style={{ margin: "0 0 16px" }}>
        Work Orders
      </Typography.Title>
      <Space style={{ marginBottom: 12 }} wrap>
        <Select
          allowClear
          placeholder="All statuses"
          style={{ width: 170 }}
          value={statusFilter}
          onChange={setStatusFilter}
          options={Object.keys(STATUS_COLOR).map((v) => ({ value: v, label: v.replace("_", " ") }))}
        />
        <Select
          allowClear
          placeholder="All tailors"
          style={{ width: 180 }}
          value={tailorFilter}
          onChange={setTailorFilter}
          options={tailors?.map((t) => ({ value: t.id, label: t.name }))}
        />
      </Space>
      <Card size="small" styles={{ body: { padding: 0 } }}>
        <Table rowKey="id" loading={isLoading} columns={columns} dataSource={orders} pagination={{ pageSize: 25 }} scroll={{ x: "max-content" }} />
      </Card>
    </div>
  );
}
