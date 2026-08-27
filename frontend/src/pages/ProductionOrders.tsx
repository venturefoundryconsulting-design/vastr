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
  Statistic,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  createProductionOrder,
  listBoms,
  listItems,
  listOutlets,
  listProductionOrders,
} from "../api/endpoints";
import type { ProductionOrder, ProductionPriority, ProductionStatus } from "../api/types";
import { formatQty } from "../utils/quantity";

export const STATUS_META: Record<ProductionStatus, { label: string; color: string }> = {
  draft: { label: "Draft", color: "default" },
  planned: { label: "Planned", color: "blue" },
  released: { label: "Released", color: "cyan" },
  in_progress: { label: "In progress", color: "processing" },
  partially_completed: { label: "Partially completed", color: "gold" },
  completed: { label: "Completed", color: "green" },
  on_hold: { label: "On hold", color: "orange" },
  cancelled: { label: "Cancelled", color: "default" },
  closed_short: { label: "Closed short", color: "volcano" },
};

const PRIORITY_META: Record<ProductionPriority, { label: string; color: string }> = {
  low: { label: "Low", color: "default" },
  normal: { label: "Normal", color: "blue" },
  high: { label: "High", color: "orange" },
  urgent: { label: "Urgent", color: "red" },
};

/** The statuses worth surfacing as counters. Terminal states are reachable via
 *  the filter but don't earn a tile - a manager cares about work in flight. */
const TILE_ORDER: ProductionStatus[] = [
  "draft", "planned", "released", "in_progress", "partially_completed", "on_hold",
];

export default function ProductionOrders() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<ProductionStatus | undefined>();
  const [locationFilter, setLocationFilter] = useState<number | undefined>();
  const [priorityFilter, setPriorityFilter] = useState<ProductionPriority | undefined>();
  const [search, setSearch] = useState("");
  const [creating, setCreating] = useState(false);
  const [form] = Form.useForm();

  const { data: orders, isLoading } = useQuery({
    queryKey: ["production-orders", statusFilter, locationFilter, priorityFilter, search],
    queryFn: () =>
      listProductionOrders({
        status: statusFilter,
        location_id: locationFilter,
        priority: priorityFilter,
        q: search.trim() || undefined,
      }).then((r) => r.data),
  });

  // Unfiltered, so the tiles always show the true picture rather than counting
  // whatever filter happens to be applied.
  const { data: allOrders } = useQuery({
    queryKey: ["production-orders", "all"],
    queryFn: () => listProductionOrders({}).then((r) => r.data),
  });

  const { data: outlets } = useQuery({
    queryKey: ["outlets"],
    queryFn: () => listOutlets().then((r) => r.data),
  });
  const { data: boms } = useQuery({
    queryKey: ["boms"],
    queryFn: () => listBoms().then((r) => r.data),
    enabled: creating,
  });
  const { data: items } = useQuery({
    queryKey: ["items-all"],
    queryFn: () => listItems({ is_active: true }).then((r) => r.data),
    enabled: creating,
  });

  const counts = useMemo(() => {
    const c: Partial<Record<ProductionStatus, number>> = {};
    for (const o of allOrders ?? []) c[o.status] = (c[o.status] ?? 0) + 1;
    return c;
  }, [allOrders]);

  // Only items with an active BOM can be produced - the server rejects the rest,
  // so don't offer them.
  const producible = useMemo(
    () =>
      (boms ?? [])
        .filter((b) => b.active_version_no != null)
        .map((b) => ({ value: b.item_id, label: `${b.item_name ?? b.name} — ${b.item_sku}` })),
    [boms],
  );

  const create = useMutation({
    mutationFn: (v: any) =>
      createProductionOrder({
        item_id: v.item_id,
        planned_quantity: v.planned_quantity,
        location_id: v.location_id,
        planned_start: v.planned_start ? v.planned_start.format("YYYY-MM-DD") : null,
        planned_completion: v.planned_completion ? v.planned_completion.format("YYYY-MM-DD") : null,
        priority: v.priority ?? "normal",
        notes: v.notes ?? null,
      }),
    onSuccess: (r) => {
      message.success(`${r.data.po_number} created as a draft`);
      queryClient.invalidateQueries({ queryKey: ["production-orders"] });
      setCreating(false);
      form.resetFields();
      navigate(`/production/${r.data.id}`);
    },
    onError: (e: any) =>
      message.error(e?.response?.data?.detail || "Could not create the production order"),
  });

  const columns = [
    {
      title: "Order",
      key: "po",
      width: 170,
      render: (_: unknown, r: ProductionOrder) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>
            <code>{r.po_number}</code>
          </Typography.Text>
          {r.bom_version_no != null && (
            <Typography.Text type="secondary" style={{ fontSize: 11 }}>
              BOM V{r.bom_version_no}
            </Typography.Text>
          )}
        </Space>
      ),
    },
    {
      title: "Producing",
      key: "item",
      render: (_: unknown, r: ProductionOrder) => (
        <Space direction="vertical" size={0}>
          <Typography.Text>{r.item_name}</Typography.Text>
          <Typography.Text type="secondary" style={{ fontSize: 11 }}>
            <code>{r.item_sku}</code>
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: "Quantity",
      key: "qty",
      width: 150,
      align: "right" as const,
      render: (_: unknown, r: ProductionOrder) => (
        <Space direction="vertical" size={0} style={{ alignItems: "flex-end" }}>
          <Typography.Text strong>
            {formatQty(r.planned_quantity)} {r.uom_code ?? ""}
          </Typography.Text>
          {Number(r.produced_quantity) > 0 && (
            <Typography.Text type="secondary" style={{ fontSize: 11 }}>
              {formatQty(r.produced_quantity)} made · {formatQty(r.remaining_quantity)} left
            </Typography.Text>
          )}
        </Space>
      ),
    },
    { title: "Location", dataIndex: "location_name", width: 150 },
    {
      title: "Status",
      dataIndex: "status",
      width: 160,
      render: (s: ProductionStatus) => (
        <Tag color={STATUS_META[s]?.color}>{STATUS_META[s]?.label ?? s}</Tag>
      ),
    },
    {
      title: "Priority",
      dataIndex: "priority",
      width: 100,
      render: (p: ProductionPriority) => (
        <Tag color={PRIORITY_META[p]?.color}>{PRIORITY_META[p]?.label ?? p}</Tag>
      ),
    },
    { title: "Due", dataIndex: "planned_completion", width: 110 },
    {
      title: "",
      key: "actions",
      width: 90,
      render: (_: unknown, r: ProductionOrder) => (
        <Button size="small" type="primary" ghost onClick={() => navigate(`/production/${r.id}`)}>
          Open
        </Button>
      ),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16, width: "100%", justifyContent: "space-between" }} wrap>
        <Typography.Title level={3} style={{ margin: 0 }}>
          Production
        </Typography.Title>
        <Button type="primary" onClick={() => setCreating(true)}>
          New production order
        </Button>
      </Space>

      <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
        {TILE_ORDER.map((s) => (
          <Col key={s} xs={12} sm={8} md={4}>
            <Card
              size="small"
              hoverable
              onClick={() => setStatusFilter(statusFilter === s ? undefined : s)}
              style={statusFilter === s ? { outline: "2px solid var(--ant-color-primary)" } : undefined}
            >
              <Statistic
                title={STATUS_META[s].label}
                value={counts[s] ?? 0}
                valueStyle={{ fontSize: 22, fontWeight: 700 }}
              />
            </Card>
          </Col>
        ))}
      </Row>

      <Space style={{ marginBottom: 12 }} wrap>
        <Input.Search
          allowClear
          placeholder="Search order number, SKU or product"
          style={{ width: 280 }}
          onSearch={setSearch}
          onChange={(e) => !e.target.value && setSearch("")}
        />
        <Select
          allowClear
          placeholder="All statuses"
          style={{ width: 190 }}
          value={statusFilter}
          onChange={setStatusFilter}
          options={Object.entries(STATUS_META).map(([v, m]) => ({ value: v, label: m.label }))}
        />
        <Select
          allowClear
          placeholder="All locations"
          style={{ width: 190 }}
          value={locationFilter}
          onChange={setLocationFilter}
          options={outlets?.map((o) => ({ value: o.id, label: o.name }))}
        />
        <Select
          allowClear
          placeholder="Any priority"
          style={{ width: 150 }}
          value={priorityFilter}
          onChange={setPriorityFilter}
          options={Object.entries(PRIORITY_META).map(([v, m]) => ({ value: v, label: m.label }))}
        />
      </Space>

      <Card size="small" styles={{ body: { padding: 0 } }}>
        <Table
          rowKey="id"
          loading={isLoading}
          columns={columns}
          dataSource={orders}
          pagination={{ pageSize: 20, showSizeChanger: true }}
          scroll={{ x: "max-content" }}
          onRow={(r) => ({ onDoubleClick: () => navigate(`/production/${r.id}`) })}
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="No production orders match these filters"
              />
            ),
          }}
        />
      </Card>

      <Modal
        title="New production order"
        open={creating}
        onCancel={() => setCreating(false)}
        onOk={() => form.submit()}
        confirmLoading={create.isPending}
        width={560}
      >
        <Typography.Paragraph type="secondary">
          The order is created as a <b>draft</b> and its material requirements are calculated
          immediately. Nothing is reserved — a shortage is reported, not blocked.
        </Typography.Paragraph>
        <Form
          form={form}
          layout="vertical"
          onFinish={(v) => create.mutate(v)}
          initialValues={{ planned_quantity: 1, priority: "normal" }}
        >
          <Form.Item
            name="item_id"
            label="What are you producing?"
            rules={[{ required: true, message: "Choose the item to produce" }]}
            extra="Only items with an active bill of materials can be produced."
          >
            <Select
              showSearch
              optionFilterProp="label"
              placeholder="Search a garment or sub-assembly"
              options={producible}
              notFoundContent={
                producible.length === 0 ? "No items have an active BOM yet" : undefined
              }
            />
          </Form.Item>
          <Space align="start">
            <Form.Item name="planned_quantity" label="Quantity" rules={[{ required: true }]}>
              <InputNumber min={0.0001} step={1} style={{ width: 160 }} />
            </Form.Item>
            <Form.Item name="location_id" label="Location" rules={[{ required: true }]}>
              <Select
                style={{ width: 240 }}
                options={outlets?.map((o) => ({ value: o.id, label: o.name }))}
              />
            </Form.Item>
          </Space>
          <Space align="start">
            <Form.Item name="planned_start" label="Planned start">
              <DatePicker style={{ width: 180 }} />
            </Form.Item>
            <Form.Item name="planned_completion" label="Planned completion">
              <DatePicker style={{ width: 180 }} />
            </Form.Item>
          </Space>
          <Form.Item name="priority" label="Priority">
            <Select
              options={Object.entries(PRIORITY_META).map(([v, m]) => ({ value: v, label: m.label }))}
            />
          </Form.Item>
          <Form.Item name="notes" label="Notes">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
