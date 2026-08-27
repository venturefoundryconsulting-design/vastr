import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Form,
  Input,
  InputNumber,
  Modal,
  Row,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  Timeline,
  Tooltip,
  Typography,
  message,
} from "antd";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  cancelProductionOrder,
  closeShortProductionOrder,
  getProductionHistory,
  getProductionOrder,
  getProductionTrace,
  holdProductionOrder,
  planProductionOrder,
  releaseProductionOrder,
  resumeProductionOrder,
  startProductionOrder,
} from "../api/endpoints";
import type {
  MaterialAvailabilityStatus,
  OrderAvailabilityStatus,
  ProductionMaterialLine,
  ProductionSnapshotLine,
} from "../api/types";
import MaterialFlowPanel from "../components/MaterialFlowPanel";
import ProductionCostPanel from "../components/ProductionCostPanel";
import ProductionOutputPanel from "../components/ProductionOutputPanel";
import QualityPanel from "../components/QualityPanel";
import WastagePanel from "../components/WastagePanel";
import { formatQty } from "../utils/quantity";
import { STATUS_META } from "./ProductionOrders";

const MATERIAL_META: Record<MaterialAvailabilityStatus, { label: string; color: string }> = {
  available: { label: "Available", color: "green" },
  partial: { label: "Partial", color: "gold" },
  short: { label: "Short", color: "red" },
  not_stocked: { label: "Not stocked", color: "default" },
  invalid: { label: "Invalid", color: "volcano" },
};

const OVERALL_META: Record<
  OrderAvailabilityStatus,
  { type: "success" | "warning" | "error" | "info"; message: string; description: string }
> = {
  ready: {
    type: "success",
    message: "All materials are available",
    description: "Nothing is reserved yet — reservation happens when materials are committed.",
  },
  partial_material: {
    type: "warning",
    message: "Some materials are only partly available",
    description: "This order can still be released, but it may not be possible to commit every material.",
  },
  material_shortage: {
    type: "error",
    message: "Material shortage",
    description:
      "This production order can be released, but material reservation may not be possible until stock arrives.",
  },
  invalid_material: {
    type: "error",
    message: "A material can't be resolved",
    description: "Check the units and item setup on the flagged lines before releasing.",
  },
};

export default function ProductionOrderDetail() {
  const { id } = useParams();
  const orderId = Number(id);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [closeShortOpen, setCloseShortOpen] = useState(false);
  const [traceFor, setTraceFor] = useState<ProductionMaterialLine | null>(null);
  const [closeForm] = Form.useForm();

  const { data: order, isLoading } = useQuery({
    queryKey: ["production-order", orderId],
    queryFn: () => getProductionOrder(orderId).then((r) => r.data),
    enabled: Number.isFinite(orderId),
  });

  const { data: history } = useQuery({
    queryKey: ["production-history", orderId],
    queryFn: () => getProductionHistory(orderId).then((r) => r.data),
    enabled: Number.isFinite(orderId),
  });

  const { data: trace } = useQuery({
    queryKey: ["production-trace", orderId, traceFor?.item_id],
    queryFn: () => getProductionTrace(orderId, traceFor!.item_id).then((r) => r.data),
    enabled: !!traceFor,
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["production-order", orderId] });
    queryClient.invalidateQueries({ queryKey: ["production-history", orderId] });
    queryClient.invalidateQueries({ queryKey: ["production-orders"] });
  };

  const act = (fn: () => Promise<unknown>, label: string) =>
    fn()
      .then(() => {
        message.success(label);
        refresh();
      })
      .catch((e: any) =>
        message.error(e?.response?.data?.detail || `Could not ${label.toLowerCase()}`),
      );

  const closeShort = useMutation({
    mutationFn: (v: any) =>
      closeShortProductionOrder(orderId, {
        produced_quantity: v.produced_quantity,
        reason: v.reason,
      }),
    onSuccess: () => {
      message.success("Production order closed short");
      setCloseShortOpen(false);
      closeForm.resetFields();
      refresh();
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || "Could not close short"),
  });

  if (isLoading) return <Card loading />;
  if (!order) return <Alert type="error" message="Production order not found" />;

  const can = (s: string) => order.allowed_transitions.includes(s as any);
  const avail = order.availability;
  const overall = avail ? OVERALL_META[avail.overall] : null;

  const materialColumns = [
    {
      title: "Material",
      key: "item",
      render: (_: unknown, r: ProductionMaterialLine) => (
        <Space direction="vertical" size={0}>
          <Space size={6}>
            <Typography.Text>{r.name}</Typography.Text>
            {r.is_optional && <Tag>optional</Tag>}
          </Space>
          <Typography.Text type="secondary" style={{ fontSize: 11 }}>
            <code>{r.sku}</code>
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: "Required",
      key: "required",
      width: 130,
      align: "right" as const,
      render: (_: unknown, r: ProductionMaterialLine) => (
        <Tooltip
          title={`Base ${formatQty(r.base_quantity)} + wastage ${formatQty(r.expected_wastage)}`}
        >
          <Typography.Text strong>
            {formatQty(r.required)} {r.uom_code ?? ""}
          </Typography.Text>
        </Tooltip>
      ),
    },
    {
      title: "Wastage",
      key: "wastage",
      width: 100,
      align: "right" as const,
      render: (_: unknown, r: ProductionMaterialLine) =>
        Number(r.expected_wastage) > 0 ? (
          <Typography.Text type="warning">+{formatQty(r.expected_wastage)}</Typography.Text>
        ) : (
          <Typography.Text type="secondary">—</Typography.Text>
        ),
    },
    {
      title: "On hand",
      dataIndex: "on_hand",
      width: 100,
      align: "right" as const,
      render: (v: number) => formatQty(v),
    },
    {
      title: "Reserved",
      dataIndex: "reserved",
      width: 100,
      align: "right" as const,
      render: (v: number) => formatQty(v),
    },
    {
      title: "Available",
      dataIndex: "available",
      width: 100,
      align: "right" as const,
      render: (v: number) => <Typography.Text strong>{formatQty(v)}</Typography.Text>,
    },
    {
      title: "Shortage",
      dataIndex: "shortage",
      width: 110,
      align: "right" as const,
      render: (v: number) =>
        Number(v) > 0 ? (
          <Typography.Text type="danger" strong>
            {formatQty(v)}
          </Typography.Text>
        ) : (
          <Typography.Text type="secondary">—</Typography.Text>
        ),
    },
    {
      title: "Status",
      dataIndex: "status",
      width: 130,
      render: (s: MaterialAvailabilityStatus, r: ProductionMaterialLine) => (
        <Tooltip title={r.note}>
          <Tag color={MATERIAL_META[s]?.color}>{MATERIAL_META[s]?.label ?? s}</Tag>
        </Tooltip>
      ),
    },
    {
      title: "",
      key: "why",
      width: 70,
      render: (_: unknown, r: ProductionMaterialLine) => (
        <Button size="small" type="link" onClick={() => setTraceFor(r)}>
          Why?
        </Button>
      ),
    },
  ];

  return (
    <div>
      <Space style={{ width: "100%", justifyContent: "space-between", marginBottom: 12 }} wrap>
        <Space direction="vertical" size={0}>
          <Space wrap>
            <Button size="small" onClick={() => navigate("/production")}>
              ← All orders
            </Button>
            <Typography.Title level={4} style={{ margin: 0 }}>
              <code>{order.po_number}</code>
            </Typography.Title>
            <Tag color={STATUS_META[order.status]?.color}>
              {STATUS_META[order.status]?.label ?? order.status}
            </Tag>
          </Space>
          <Typography.Text type="secondary">
            {order.item_name} · <code>{order.item_sku}</code>
            {order.bom_version_no != null && ` · BOM V${order.bom_version_no}`}
          </Typography.Text>
        </Space>

        <Space wrap>
          {can("planned") && (
            <Button size="small" onClick={() => act(() => planProductionOrder(orderId), "Planned")}>
              Mark planned
            </Button>
          )}
          {can("released") && order.status !== "on_hold" && (
            <Button
              size="small"
              type="primary"
              onClick={() => act(() => releaseProductionOrder(orderId), "Released")}
            >
              Release
            </Button>
          )}
          {can("in_progress") && order.status === "released" && (
            <Button size="small" onClick={() => act(() => startProductionOrder(orderId), "Started")}>
              Start
            </Button>
          )}
          {can("on_hold") && (
            <Button size="small" onClick={() => act(() => holdProductionOrder(orderId), "On hold")}>
              Put on hold
            </Button>
          )}
          {order.status === "on_hold" && (
            <Button
              size="small"
              type="primary"
              onClick={() => act(() => resumeProductionOrder(orderId), "Resumed")}
            >
              Resume
            </Button>
          )}
          {can("closed_short") && (
            <Button size="small" danger onClick={() => setCloseShortOpen(true)}>
              Close short
            </Button>
          )}
          {can("cancelled") && (
            <Button
              size="small"
              danger
              onClick={() =>
                Modal.confirm({
                  title: "Cancel this production order?",
                  content: "It will stop here and cannot be restarted.",
                  okText: "Cancel order",
                  okButtonProps: { danger: true },
                  cancelText: "Keep it",
                  onOk: () => act(() => cancelProductionOrder(orderId), "Cancelled"),
                })
              }
            >
              Cancel
            </Button>
          )}
        </Space>
      </Space>

      {overall && (
        <Alert
          type={overall.type}
          showIcon
          style={{ marginBottom: 12 }}
          message={overall.message}
          description={overall.description}
        />
      )}

      <Row gutter={16}>
        <Col xs={24} xl={18}>
          <Tabs
            size="small"
            items={[
              {
                key: "materials",
                label: "Materials",
                children: (
                  <>
                    <Card size="small" title="Material requirements" styles={{ body: { padding: 0 } }}>
                      <Table
                        rowKey="item_id"
                        size="small"
                        columns={materialColumns}
                        dataSource={avail?.lines ?? []}
                        pagination={avail && avail.lines.length > 25 ? { pageSize: 25 } : false}
                        scroll={{ x: "max-content" }}
                      />
                    </Card>

                    {["released", "in_progress", "partially_completed", "on_hold", "completed", "closed_short"].includes(
                      order.status,
                    ) && (
                      <div style={{ marginTop: 12 }}>
                        <MaterialFlowPanel orderId={orderId} />
                      </div>
                    )}

                    {order.materials.some((m) => m.is_subassembly) && (
                      <Card size="small" title="Bill of materials hierarchy" style={{ marginTop: 12 }}>
                        <Table<ProductionSnapshotLine>
                          rowKey="id"
                          size="small"
                          pagination={false}
                          dataSource={order.materials}
                          scroll={{ x: "max-content" }}
                          columns={[
                            {
                              title: "Component",
                              key: "c",
                              render: (_: unknown, r: ProductionSnapshotLine) => (
                                <span style={{ paddingLeft: r.level * 20 }}>
                                  {r.level > 0 && (
                                    <Typography.Text type="secondary">↳ </Typography.Text>
                                  )}
                                  {r.name}{" "}
                                  <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                                    <code>{r.sku}</code>
                                  </Typography.Text>
                                  {r.is_subassembly && <Tag style={{ marginLeft: 6 }}>sub-assembly</Tag>}
                                </span>
                              ),
                            },
                            {
                              title: "Per unit",
                              key: "pu",
                              width: 110,
                              align: "right",
                              render: (_: unknown, r: ProductionSnapshotLine) =>
                                `${formatQty(r.quantity_per_unit)} ${r.uom_code ?? ""}`,
                            },
                            {
                              title: "Planned",
                              key: "pl",
                              width: 130,
                              align: "right",
                              render: (_: unknown, r: ProductionSnapshotLine) => (
                                <Typography.Text strong>
                                  {formatQty(r.planned_quantity)} {r.uom_code ?? ""}
                                </Typography.Text>
                              ),
                            },
                          ]}
                        />
                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                          Sub-assembly rows are shown for context. Their own components are listed
                          separately, so material totals above count each raw material once.
                        </Typography.Text>
                      </Card>
                    )}
                  </>
                ),
              },
              {
                key: "output",
                label: "Output",
                children: <ProductionOutputPanel order={order} />,
              },
              {
                key: "quality",
                label: "Quality & rework",
                children: <QualityPanel order={order} />,
              },
              {
                key: "wastage",
                label: "Wastage",
                children: <WastagePanel order={order} />,
              },
              {
                key: "cost",
                label: "Cost",
                children: <ProductionCostPanel orderId={orderId} />,
              },
            ]}
          />
        </Col>

        <Col xs={24} xl={6}>
          <Card size="small" title="Order">
            <Statistic
              title="Planned quantity"
              value={Number(order.planned_quantity)}
              suffix={order.uom_code ?? ""}
              precision={0}
            />
            <Descriptions column={1} size="small" style={{ marginTop: 12 }}>
              <Descriptions.Item label="Produced">
                {formatQty(order.produced_quantity)}
              </Descriptions.Item>
              <Descriptions.Item label="Remaining">
                {formatQty(order.remaining_quantity)}
              </Descriptions.Item>
              {Number(order.cancelled_quantity) > 0 && (
                <Descriptions.Item label="Cancelled">
                  {formatQty(order.cancelled_quantity)}
                </Descriptions.Item>
              )}
              <Descriptions.Item label="Location">{order.location_name}</Descriptions.Item>
              <Descriptions.Item label="Planned start">
                {order.planned_start ?? "—"}
              </Descriptions.Item>
              <Descriptions.Item label="Due">{order.planned_completion ?? "—"}</Descriptions.Item>
              <Descriptions.Item label="Materials">{order.material_count}</Descriptions.Item>
            </Descriptions>
            {order.close_short_reason && (
              <Alert
                type="warning"
                style={{ marginTop: 8 }}
                message="Closed short"
                description={order.close_short_reason}
              />
            )}
          </Card>

          <Card size="small" title="History" style={{ marginTop: 12 }}>
            <Timeline
              items={(history ?? []).map((h) => ({
                children: (
                  <Space direction="vertical" size={0}>
                    <Typography.Text>{h.action.replace("production.", "")}</Typography.Text>
                    <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                      {new Date(h.created_at).toLocaleString()}
                    </Typography.Text>
                    {typeof h.details?.reason === "string" && (
                      <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                        {h.details.reason as string}
                      </Typography.Text>
                    )}
                  </Space>
                ),
              }))}
            />
            {!history?.length && <Typography.Text type="secondary">No events yet.</Typography.Text>}
          </Card>
        </Col>
      </Row>

      <Modal
        title="Close this production order short"
        open={closeShortOpen}
        onCancel={() => setCloseShortOpen(false)}
        onOk={() => closeForm.submit()}
        confirmLoading={closeShort.isPending}
      >
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message="This ends the order below its planned quantity"
          description="The remainder is recorded as cancelled, against your name and the reason you give. This cannot be undone."
        />
        <Form
          form={closeForm}
          layout="vertical"
          onFinish={(v) => closeShort.mutate(v)}
          initialValues={{ produced_quantity: Number(order.produced_quantity) }}
        >
          <Form.Item
            name="produced_quantity"
            label={`How many were actually produced? (planned ${formatQty(order.planned_quantity)})`}
            rules={[{ required: true }]}
          >
            <InputNumber
              min={0}
              max={Number(order.planned_quantity)}
              step={1}
              style={{ width: "100%" }}
            />
          </Form.Item>
          <Form.Item
            name="reason"
            label="Why is it being closed short?"
            rules={[{ required: true, message: "A reason is required" }]}
          >
            <Input.TextArea rows={3} placeholder="e.g. remaining fabric was damaged in finishing" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={traceFor ? `Why do we need ${traceFor.name}?` : "Requirement trace"}
        open={!!traceFor}
        onCancel={() => setTraceFor(null)}
        footer={null}
        width={620}
      >
        {traceFor && (
          <>
            <Typography.Paragraph>
              <b>
                {formatQty(traceFor.required)} {traceFor.uom_code}
              </b>{" "}
              of <code>{traceFor.sku}</code> for this order.
            </Typography.Paragraph>
            {(trace ?? []).map((chain, i) => (
              <Timeline
                key={i}
                items={[
                  {
                    color: "blue",
                    children: (
                      <Typography.Text>
                        <b>
                          {formatQty(order.planned_quantity)} {order.uom_code}
                        </b>{" "}
                        of {order.item_name}
                      </Typography.Text>
                    ),
                  },
                  ...chain.map((step) => ({
                    children: (
                      <Space direction="vertical" size={0}>
                        <Typography.Text>
                          {formatQty(step.quantity_per_unit)} per unit
                          {step.parent_sku ? ` of ${step.parent_sku}` : ""}
                          {Number(step.scrap_pct) > 0 && ` · +${step.scrap_pct}% wastage`}
                        </Typography.Text>
                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                          → {formatQty(step.planned_quantity)} required at level {step.level}
                        </Typography.Text>
                      </Space>
                    ),
                  })),
                ]}
              />
            ))}
          </>
        )}
      </Modal>
    </div>
  );
}
