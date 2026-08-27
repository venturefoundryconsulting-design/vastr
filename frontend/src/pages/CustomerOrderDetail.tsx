import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Col, Descriptions, Modal, Row, Space, Table, Tag, Typography, message } from "antd";
import { useNavigate, useParams } from "react-router-dom";
import {
  cancelCustomerOrder,
  confirmCustomerOrder,
  deliverCustomerOrder,
  getCustomerOrder,
  getCustomerOrderReadiness,
  markCustomerOrderReady,
} from "../api/manufacturing-endpoints";
import type { CustomerOrderItemOut, CustomerOrderStatus, ReadinessLine } from "../api/manufacturing-types";
import { formatQty } from "../utils/quantity";

const STATUS_META: Record<CustomerOrderStatus, { label: string; color: string }> = {
  draft: { label: "Draft", color: "default" },
  confirmed: { label: "Confirmed", color: "blue" },
  in_production: { label: "In production", color: "processing" },
  ready: { label: "Ready", color: "cyan" },
  delivered: { label: "Delivered", color: "green" },
  cancelled: { label: "Cancelled", color: "default" },
};

export default function CustomerOrderDetail() {
  const { id } = useParams();
  const orderId = Number(id);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: order, isLoading } = useQuery({
    queryKey: ["customer-order", orderId],
    queryFn: () => getCustomerOrder(orderId).then((r) => r.data),
    enabled: Number.isFinite(orderId),
  });
  const { data: readiness } = useQuery({
    queryKey: ["customer-order-readiness", orderId],
    queryFn: () => getCustomerOrderReadiness(orderId).then((r) => r.data),
    enabled: !!order && !["draft", "delivered", "cancelled"].includes(order.status),
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["customer-order", orderId] });
    queryClient.invalidateQueries({ queryKey: ["customer-order-readiness", orderId] });
    queryClient.invalidateQueries({ queryKey: ["customer-orders"] });
  };

  const act = (fn: () => Promise<unknown>, label: string) =>
    fn()
      .then(() => {
        message.success(label);
        refresh();
      })
      .catch((e: any) => message.error(e?.response?.data?.detail || `Could not ${label.toLowerCase()}`));

  const deliver = useMutation({
    mutationFn: () => deliverCustomerOrder(orderId),
    onSuccess: (r) => {
      message.success(`Delivered as invoice, sale #${r.data.sale_id}`);
      refresh();
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || "Could not deliver"),
  });

  if (isLoading) return <Card loading />;
  if (!order) return <Alert type="error" message="Customer order not found" />;

  const can = (s: string) => order.allowed_transitions.includes(s as any);

  return (
    <div>
      <Space style={{ width: "100%", justifyContent: "space-between", marginBottom: 12 }} wrap>
        <Space direction="vertical" size={0}>
          <Space wrap>
            <Button size="small" onClick={() => navigate("/customer-orders")}>
              ← All orders
            </Button>
            <Typography.Title level={4} style={{ margin: 0 }}>
              <code>{order.order_number}</code>
            </Typography.Title>
            <Tag color={STATUS_META[order.status]?.color}>{STATUS_META[order.status]?.label ?? order.status}</Tag>
          </Space>
          <Typography.Text type="secondary">{order.customer_name} · {order.outlet_name}</Typography.Text>
        </Space>

        <Space wrap>
          {can("confirmed") && (
            <Button type="primary" onClick={() => act(() => confirmCustomerOrder(orderId), "Confirmed")}>
              Confirm
            </Button>
          )}
          {can("ready") && (
            <Button
              type="primary"
              disabled={!readiness?.all_ready}
              onClick={() => act(() => markCustomerOrderReady(orderId), "Marked ready")}
            >
              Mark ready
            </Button>
          )}
          {order.status === "ready" && (
            <Button type="primary" onClick={() => deliver.mutate()} loading={deliver.isPending}>
              Deliver
            </Button>
          )}
          {can("cancelled") && (
            <Button
              danger
              onClick={() =>
                Modal.confirm({
                  title: "Cancel this order?",
                  content: "Any production it spawned will also be cancelled, releasing its material reservations.",
                  okText: "Cancel order",
                  okButtonProps: { danger: true },
                  cancelText: "Keep it",
                  onOk: () => act(() => cancelCustomerOrder(orderId), "Cancelled"),
                })
              }
            >
              Cancel
            </Button>
          )}
        </Space>
      </Space>

      {readiness && !readiness.all_ready && !["ready", "delivered", "cancelled"].includes(order.status) && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message="Not everything can be handed over yet"
          description="Check the readiness column below — a made-to-order line waits on its production order, a ready-stock line waits on physical stock."
        />
      )}
      {order.status === "delivered" && (
        <Alert
          type="success"
          showIcon
          style={{ marginBottom: 12 }}
          message="Delivered"
          description={`Settled as sale #${order.sale_id}.`}
        />
      )}

      <Row gutter={16}>
        <Col xs={24} xl={16}>
          <Card size="small" title="Items" styles={{ body: { padding: 0 } }}>
            <Table<CustomerOrderItemOut>
              rowKey="id"
              size="small"
              pagination={false}
              dataSource={order.items}
              scroll={{ x: "max-content" }}
              columns={[
                {
                  title: "Item",
                  key: "item",
                  render: (_: unknown, r: CustomerOrderItemOut) => (
                    <Space direction="vertical" size={0}>
                      <Typography.Text>{r.name}</Typography.Text>
                      <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                        <code>{r.sku}</code>
                      </Typography.Text>
                    </Space>
                  ),
                },
                { title: "Qty", dataIndex: "quantity", width: 80, align: "right" as const, render: formatQty },
                { title: "Price", dataIndex: "unit_price", width: 100, align: "right" as const, render: (v: number) => `₹${Number(v).toFixed(2)}` },
                { title: "Total", dataIndex: "line_total", width: 110, align: "right" as const, render: (v: number) => `₹${Number(v).toFixed(2)}` },
                {
                  title: "Fulfilment",
                  dataIndex: "fulfilment",
                  width: 130,
                  render: (v: string) => <Tag color={v === "made_to_order" ? "purple" : "default"}>{v.replace("_", " ")}</Tag>,
                },
                {
                  title: "Production",
                  key: "prod",
                  width: 160,
                  render: (_: unknown, r: CustomerOrderItemOut) =>
                    r.production_order_id ? (
                      <a onClick={() => navigate(`/production/${r.production_order_id}`)}>
                        {r.production_status} ({formatQty(r.produced_quantity ?? 0)}/{formatQty(r.quantity)})
                      </a>
                    ) : (
                      "—"
                    ),
                },
              ]}
            />
          </Card>

          {readiness && (
            <Card size="small" title="Readiness" style={{ marginTop: 12 }}>
              <Table<ReadinessLine>
                rowKey="item_id"
                size="small"
                pagination={false}
                dataSource={readiness.lines}
                columns={[
                  { title: "Item", dataIndex: "name" },
                  { title: "Needed", dataIndex: "quantity", width: 100, align: "right" as const, render: formatQty },
                  {
                    title: "Ready",
                    dataIndex: "is_ready",
                    width: 90,
                    render: (v: boolean) => <Tag color={v ? "green" : "gold"}>{v ? "Yes" : "No"}</Tag>,
                  },
                  { title: "Note", dataIndex: "note", render: (v: string | null) => v ?? "—" },
                ]}
              />
            </Card>
          )}
        </Col>

        <Col xs={24} xl={8}>
          <Card size="small" title="Order">
            <Descriptions column={1} size="small">
              <Descriptions.Item label="Total">₹{Number(order.total_amount).toFixed(2)}</Descriptions.Item>
              <Descriptions.Item label="Advance">₹{Number(order.advance_amount).toFixed(2)}</Descriptions.Item>
              <Descriptions.Item label="Balance due">₹{Number(order.balance_due).toFixed(2)}</Descriptions.Item>
              <Descriptions.Item label="Promised">{order.promised_date ?? "—"}</Descriptions.Item>
              {order.delivered_at && (
                <Descriptions.Item label="Delivered">{new Date(order.delivered_at).toLocaleString()}</Descriptions.Item>
              )}
              {order.cancel_reason && <Descriptions.Item label="Cancelled">{order.cancel_reason}</Descriptions.Item>}
            </Descriptions>
          </Card>
        </Col>
      </Row>
    </div>
  );
}
