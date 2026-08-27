import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Button,
  Card,
  Col,
  DatePicker,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { listCustomers, listItems, listOutlets } from "../api/endpoints";
import {
  createCustomerOrder,
  createMeasurementProfile,
  listCustomerMeasurements,
  listCustomerOrders,
  listMeasurementFields,
} from "../api/manufacturing-endpoints";
import type { CustomerOrderOut, CustomerOrderStatus, Fulfilment } from "../api/manufacturing-types";

const STATUS_META: Record<CustomerOrderStatus, { label: string; color: string }> = {
  draft: { label: "Draft", color: "default" },
  confirmed: { label: "Confirmed", color: "blue" },
  in_production: { label: "In production", color: "processing" },
  ready: { label: "Ready", color: "cyan" },
  delivered: { label: "Delivered", color: "green" },
  cancelled: { label: "Cancelled", color: "default" },
};

interface DraftLine {
  key: string;
  item_id?: number;
  quantity: number;
  unit_price: number;
  fulfilment: Fulfilment;
  measurement_profile_id?: number | null;
}

export default function CustomerOrders() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [statusFilter, setStatusFilter] = useState<CustomerOrderStatus | undefined>();
  const [creating, setCreating] = useState(false);
  const [customerId, setCustomerId] = useState<number | undefined>();
  const [lines, setLines] = useState<DraftLine[]>([{ key: "l0", quantity: 1, unit_price: 0, fulfilment: "ready_stock" }]);
  const [headerForm] = Form.useForm();
  const [measuring, setMeasuring] = useState(false);
  const [measureName, setMeasureName] = useState("");
  const [measureValues, setMeasureValues] = useState<Record<number, number>>({});

  const { data: orders, isLoading } = useQuery({
    queryKey: ["customer-orders", statusFilter],
    queryFn: () => listCustomerOrders({ status: statusFilter }).then((r) => r.data),
  });
  const { data: customers } = useQuery({
    queryKey: ["customers-search"],
    queryFn: () => listCustomers().then((r) => r.data),
    enabled: creating,
  });
  const { data: outlets } = useQuery({
    queryKey: ["outlets"],
    queryFn: () => listOutlets().then((r) => r.data),
    enabled: creating,
  });
  const { data: items } = useQuery({
    queryKey: ["items-all"],
    queryFn: () => listItems({ is_active: true }).then((r) => r.data),
    enabled: creating,
  });
  const { data: profiles } = useQuery({
    queryKey: ["customer-measurements", customerId],
    queryFn: () => listCustomerMeasurements(customerId!).then((r) => r.data),
    enabled: !!customerId,
  });
  const { data: fields } = useQuery({
    queryKey: ["measurement-fields"],
    queryFn: () => listMeasurementFields().then((r) => r.data),
    enabled: measuring,
  });

  const saveMeasurements = useMutation({
    mutationFn: () =>
      createMeasurementProfile({
        customer_id: customerId!,
        name: measureName,
        values: Object.entries(measureValues)
          .filter(([, v]) => v > 0)
          .map(([field_id, value]) => ({ field_id: Number(field_id), value })),
      }),
    onSuccess: () => {
      message.success("Measurements saved");
      setMeasuring(false);
      setMeasureName("");
      setMeasureValues({});
      queryClient.invalidateQueries({ queryKey: ["customer-measurements", customerId] });
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || "Could not save measurements"),
  });

  const itemOptions = useMemo(
    () => (items ?? []).map((i) => ({ value: i.id, label: `${i.display_name || i.name || i.sku} — ${i.sku}` })),
    [items],
  );

  const close = () => {
    setCreating(false);
    setCustomerId(undefined);
    setLines([{ key: "l0", quantity: 1, unit_price: 0, fulfilment: "ready_stock" }]);
    headerForm.resetFields();
  };

  const create = useMutation({
    mutationFn: (header: any) =>
      createCustomerOrder({
        customer_id: header.customer_id,
        outlet_id: header.outlet_id,
        promised_date: header.promised_date ? header.promised_date.format("YYYY-MM-DD") : null,
        advance_amount: header.advance_amount ?? 0,
        notes: header.notes,
        items: lines
          .filter((l) => l.item_id)
          .map((l) => ({
            item_id: l.item_id!,
            quantity: l.quantity,
            unit_price: l.unit_price,
            fulfilment: l.fulfilment,
            measurement_profile_id: l.measurement_profile_id ?? null,
          })),
      }),
    onSuccess: (r) => {
      message.success(`${r.data.order_number} created`);
      queryClient.invalidateQueries({ queryKey: ["customer-orders"] });
      close();
      navigate(`/customer-orders/${r.data.id}`);
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || "Could not create the order"),
  });

  const addLine = () =>
    setLines((prev) => [...prev, { key: `l${prev.length}${Date.now()}`, quantity: 1, unit_price: 0, fulfilment: "ready_stock" }]);
  const removeLine = (key: string) => setLines((prev) => prev.filter((l) => l.key !== key));
  const patchLine = (key: string, patch: Partial<DraftLine>) =>
    setLines((prev) => prev.map((l) => (l.key === key ? { ...l, ...patch } : l)));

  const columns = [
    {
      title: "Order",
      key: "o",
      render: (_: unknown, r: CustomerOrderOut) => (
        <Space direction="vertical" size={0}>
          <code>{r.order_number}</code>
          {r.has_made_to_order && <Tag color="purple" style={{ marginTop: 2 }}>made to order</Tag>}
        </Space>
      ),
    },
    { title: "Customer", dataIndex: "customer_name", width: 160 },
    {
      title: "Total",
      key: "total",
      width: 130,
      align: "right" as const,
      render: (_: unknown, r: CustomerOrderOut) => `₹${Number(r.total_amount).toFixed(2)}`,
    },
    {
      title: "Balance due",
      key: "balance",
      width: 120,
      align: "right" as const,
      render: (_: unknown, r: CustomerOrderOut) => `₹${Number(r.balance_due).toFixed(2)}`,
    },
    { title: "Status", dataIndex: "status", width: 140, render: (v: CustomerOrderStatus) => <Tag color={STATUS_META[v]?.color}>{STATUS_META[v]?.label ?? v}</Tag> },
    { title: "Promised", dataIndex: "promised_date", width: 110, render: (v: string | null) => v ?? "—" },
    {
      title: "",
      key: "act",
      width: 80,
      render: (_: unknown, r: CustomerOrderOut) => (
        <Button size="small" type="primary" ghost onClick={() => navigate(`/customer-orders/${r.id}`)}>
          Open
        </Button>
      ),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16, width: "100%", justifyContent: "space-between" }} wrap>
        <Typography.Title level={3} style={{ margin: 0 }}>
          Customer Orders
        </Typography.Title>
        <Button type="primary" onClick={() => setCreating(true)}>
          New order
        </Button>
      </Space>

      <Select
        allowClear
        placeholder="All statuses"
        style={{ width: 190, marginBottom: 12 }}
        value={statusFilter}
        onChange={setStatusFilter}
        options={Object.entries(STATUS_META).map(([v, m]) => ({ value: v, label: m.label }))}
      />

      <Card size="small" styles={{ body: { padding: 0 } }}>
        <Table
          rowKey="id"
          loading={isLoading}
          columns={columns}
          dataSource={orders}
          pagination={{ pageSize: 20 }}
          scroll={{ x: "max-content" }}
          onRow={(r) => ({ onDoubleClick: () => navigate(`/customer-orders/${r.id}`) })}
          locale={{ emptyText: <Empty description="No customer orders yet" /> }}
        />
      </Card>

      <Modal
        title="New customer order"
        open={creating}
        onCancel={close}
        onOk={() => headerForm.submit()}
        confirmLoading={create.isPending}
        width={760}
      >
        <Typography.Paragraph type="secondary">
          Ready-stock and made-to-order items can sit on the same order. Confirming spawns
          production only for the made-to-order lines.
        </Typography.Paragraph>
        <Form form={headerForm} layout="vertical" onFinish={(v) => create.mutate(v)} initialValues={{ advance_amount: 0 }}>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="customer_id" label="Customer" rules={[{ required: true }]}>
                <Space.Compact style={{ width: "100%" }}>
                  <Select
                    showSearch
                    optionFilterProp="label"
                    style={{ width: "100%" }}
                    options={customers?.map((c) => ({ value: c.id, label: `${c.name}${c.phone ? ` (${c.phone})` : ""}` }))}
                    onChange={setCustomerId}
                  />
                </Space.Compact>
              </Form.Item>
              {customerId && (
                <Button size="small" style={{ marginTop: -18, marginBottom: 8 }} onClick={() => setMeasuring(true)}>
                  Take new measurements
                </Button>
              )}
            </Col>
            <Col span={12}>
              <Form.Item name="outlet_id" label="Outlet" rules={[{ required: true }]}>
                <Select options={outlets?.map((o) => ({ value: o.id, label: o.name }))} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="promised_date" label="Promised date">
                <DatePicker style={{ width: "100%" }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="advance_amount" label="Advance taken (₹)">
                <InputNumber min={0} step={1} precision={2} style={{ width: "100%" }} />
              </Form.Item>
            </Col>
          </Row>

          <Typography.Text strong>Items</Typography.Text>
          <Table
            rowKey="key"
            size="small"
            pagination={false}
            dataSource={lines}
            style={{ marginTop: 8, marginBottom: 8 }}
            columns={[
              {
                title: "Item",
                key: "item",
                render: (_: unknown, r: DraftLine) => (
                  <Select
                    size="small"
                    showSearch
                    optionFilterProp="label"
                    style={{ width: 220 }}
                    options={itemOptions}
                    value={r.item_id}
                    onChange={(v) => patchLine(r.key, { item_id: v })}
                  />
                ),
              },
              {
                title: "Qty",
                key: "qty",
                width: 90,
                render: (_: unknown, r: DraftLine) => (
                  <InputNumber size="small" min={0.0001} step={1} value={r.quantity} onChange={(v) => patchLine(r.key, { quantity: Number(v ?? 1) })} style={{ width: "100%" }} />
                ),
              },
              {
                title: "Price",
                key: "price",
                width: 110,
                render: (_: unknown, r: DraftLine) => (
                  <InputNumber size="small" min={0} step={1} value={r.unit_price} onChange={(v) => patchLine(r.key, { unit_price: Number(v ?? 0) })} style={{ width: "100%" }} />
                ),
              },
              {
                title: "Fulfilment",
                key: "fulfilment",
                width: 160,
                render: (_: unknown, r: DraftLine) => (
                  <Select
                    size="small"
                    style={{ width: "100%" }}
                    value={r.fulfilment}
                    onChange={(v) => patchLine(r.key, { fulfilment: v, measurement_profile_id: v === "ready_stock" ? null : r.measurement_profile_id })}
                    options={[
                      { value: "ready_stock", label: "Ready stock" },
                      { value: "made_to_order", label: "Made to order" },
                    ]}
                  />
                ),
              },
              {
                title: "Measurements",
                key: "profile",
                width: 160,
                render: (_: unknown, r: DraftLine) =>
                  r.fulfilment === "made_to_order" ? (
                    <Select
                      size="small"
                      allowClear
                      placeholder={customerId ? "Optional" : "Pick a customer first"}
                      style={{ width: "100%" }}
                      disabled={!customerId}
                      value={r.measurement_profile_id ?? undefined}
                      onChange={(v) => patchLine(r.key, { measurement_profile_id: v ?? null })}
                      options={profiles?.map((p) => ({ value: p.id, label: p.name }))}
                    />
                  ) : (
                    <Typography.Text type="secondary">—</Typography.Text>
                  ),
              },
              {
                title: "",
                key: "rm",
                width: 40,
                render: (_: unknown, r: DraftLine) => (
                  <Button size="small" danger onClick={() => removeLine(r.key)}>
                    ×
                  </Button>
                ),
              },
            ]}
          />
          <Button size="small" type="dashed" onClick={addLine} block>
            + Add item
          </Button>
          <Form.Item name="notes" label="Notes" style={{ marginTop: 12 }}>
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="Take measurements"
        open={measuring}
        onCancel={() => setMeasuring(false)}
        onOk={() => saveMeasurements.mutate()}
        confirmLoading={saveMeasurements.isPending}
        okButtonProps={{ disabled: !measureName.trim() }}
      >
        <Typography.Paragraph type="secondary">
          Creates a new named profile — a re-measure never overwrites an old one, so a garment
          already cut stays explainable.
        </Typography.Paragraph>
        <Input
          placeholder="Profile name, e.g. Bridal 2026"
          value={measureName}
          onChange={(e) => setMeasureName(e.target.value)}
          style={{ marginBottom: 12 }}
        />
        <Row gutter={[8, 8]}>
          {(fields ?? []).map((f) => (
            <Col span={12} key={f.id}>
              <Typography.Text style={{ fontSize: 12 }}>
                {f.name} ({f.unit})
              </Typography.Text>
              <InputNumber
                min={0}
                step={0.5}
                style={{ width: "100%" }}
                value={measureValues[f.id]}
                onChange={(v) => setMeasureValues((m) => ({ ...m, [f.id]: Number(v ?? 0) }))}
              />
            </Col>
          ))}
        </Row>
      </Modal>
    </div>
  );
}
