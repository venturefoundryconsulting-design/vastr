import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Input,
  InputNumber,
  Modal,
  Space,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import { useMemo, useState } from "react";
import {
  consumeMaterials,
  getOrderMaterials,
  issueMaterials,
  listMaterialConsumption,
  listMaterialIssues,
  listMaterialReturns,
  listReservations,
  releaseReservations,
  reserveMaterials,
  returnMaterials,
} from "../api/endpoints";
import type { MaterialPosition, MaterialReservation, MaterialTxn } from "../api/types";
import { formatQty, roundQty } from "../utils/quantity";

type Action = "reserve" | "issue" | "consume" | "return";

const ACTION_META: Record<
  Action,
  { title: string; verb: string; column: string; help: string; danger?: boolean }
> = {
  reserve: {
    title: "Reserve materials",
    verb: "Reserve",
    column: "Reserve now",
    help: "Reserving commits stock to this order. Nothing moves physically and stock levels don't change — the material simply stops being available to other orders.",
  },
  issue: {
    title: "Issue materials to production",
    verb: "Issue",
    column: "Issue now",
    help: "Issuing hands material to the floor. Physical stock goes down and a ledger entry is written. You can only issue what's reserved.",
  },
  consume: {
    title: "Record material consumption",
    verb: "Record",
    column: "Consumed",
    help: "This records what was actually used. Stock is not deducted again — it already left when the material was issued.",
  },
  return: {
    title: "Return unused material",
    verb: "Return",
    column: "Return now",
    help: "Unused material goes back to stock as a separate compensating entry. The original issue is never edited.",
  },
};

/** Which column bounds each action, so the form can't propose an invalid number. */
const LIMIT: Record<Action, (r: MaterialPosition) => number> = {
  reserve: (r) => Math.min(Number(r.remaining_to_reserve), Math.max(Number(r.available), 0)),
  issue: (r) => Math.min(Number(r.remaining_to_issue), Number(r.reserved) - Number(r.issued)),
  consume: (r) => Number(r.issued) - Number(r.consumed) - Number(r.returned),
  return: (r) => Number(r.returnable),
};

export default function MaterialFlowPanel({ orderId }: { orderId: number }) {
  const queryClient = useQueryClient();
  const [action, setAction] = useState<Action | null>(null);
  const [amounts, setAmounts] = useState<Record<number, number>>({});
  const [reasons, setReasons] = useState<Record<number, string>>({});
  const [overrides, setOverrides] = useState<Record<number, boolean>>({});
  const [restock, setRestock] = useState<Record<number, boolean>>({});

  const { data: summary, isLoading } = useQuery({
    queryKey: ["order-materials", orderId],
    queryFn: () => getOrderMaterials(orderId).then((r) => r.data),
  });
  const { data: reservations } = useQuery({
    queryKey: ["order-reservations", orderId],
    queryFn: () => listReservations(orderId).then((r) => r.data),
  });
  const { data: issues } = useQuery({
    queryKey: ["order-issues", orderId],
    queryFn: () => listMaterialIssues(orderId).then((r) => r.data),
  });
  const { data: consumption } = useQuery({
    queryKey: ["order-consumption", orderId],
    queryFn: () => listMaterialConsumption(orderId).then((r) => r.data),
  });
  const { data: returns } = useQuery({
    queryKey: ["order-returns", orderId],
    queryFn: () => listMaterialReturns(orderId).then((r) => r.data),
  });

  const refresh = () => {
    for (const k of [
      "order-materials", "order-reservations", "order-issues",
      "order-consumption", "order-returns", "production-order", "production-history",
    ]) {
      queryClient.invalidateQueries({ queryKey: [k, orderId] });
    }
  };

  const close = () => {
    setAction(null);
    setAmounts({});
    setReasons({});
    setOverrides({});
    setRestock({});
  };

  const submit = useMutation({
    mutationFn: () => {
      const lines = Object.entries(amounts)
        .filter(([, qty]) => Number(qty) > 0)
        .map(([id, qty]) => {
          const materialId = Number(id);
          const base = { material_id: materialId, quantity: roundQty(Number(qty)) };
          if (action === "issue") {
            return {
              ...base,
              allow_unreserved: !!overrides[materialId],
              unreserved_reason: reasons[materialId] || null,
            };
          }
          if (action === "consume") {
            return {
              ...base,
              allow_over_consumption: !!overrides[materialId],
              over_consumption_reason: reasons[materialId] || null,
            };
          }
          if (action === "return") {
            return {
              ...base,
              reason: reasons[materialId] || null,
              restock: restock[materialId] !== false,
            };
          }
          return base;
        });
      if (!lines.length) return Promise.reject(new Error("Enter at least one quantity"));
      if (action === "reserve") return reserveMaterials(orderId, lines as any);
      if (action === "issue") return issueMaterials(orderId, lines as any);
      if (action === "consume") return consumeMaterials(orderId, lines as any);
      return returnMaterials(orderId, lines as any);
    },
    onSuccess: () => {
      message.success(`${ACTION_META[action!].verb}d successfully`);
      refresh();
      close();
    },
    onError: (e: any) =>
      message.error(e?.response?.data?.detail || e?.message || "That didn't work"),
  });

  const releaseAll = useMutation({
    mutationFn: () => releaseReservations(orderId, { reason: "Released by production manager" }),
    onSuccess: () => {
      message.success("Unused reservations released");
      refresh();
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || "Could not release"),
  });

  const lines = summary?.lines ?? [];
  const anyReserved = lines.some((l) => Number(l.reserved) > 0);

  const positionColumns = [
    {
      title: "Material",
      key: "item",
      render: (_: unknown, r: MaterialPosition) => (
        <Space direction="vertical" size={0}>
          <Typography.Text>{r.name}</Typography.Text>
          <Typography.Text type="secondary" style={{ fontSize: 11 }}>
            <code>{r.sku}</code>
          </Typography.Text>
        </Space>
      ),
    },
    ...(["planned", "reserved", "issued", "consumed", "returned"] as const).map((k) => ({
      title: k[0].toUpperCase() + k.slice(1),
      dataIndex: k,
      width: 100,
      align: "right" as const,
      render: (v: number, r: MaterialPosition) => (
        <span>
          {formatQty(v)}{" "}
          <Typography.Text type="secondary" style={{ fontSize: 11 }}>
            {r.uom_code}
          </Typography.Text>
        </span>
      ),
    })),
    {
      title: "Still with production",
      dataIndex: "still_with_production",
      width: 130,
      align: "right" as const,
      render: (v: number) =>
        Number(v) > 0 ? (
          <Tooltip title="Issued but neither consumed nor returned — physically on the floor">
            <Tag color="gold">{formatQty(v)}</Tag>
          </Tooltip>
        ) : (
          <Typography.Text type="secondary">—</Typography.Text>
        ),
    },
    {
      title: "Available",
      dataIndex: "available",
      width: 110,
      align: "right" as const,
      render: (v: number, r: MaterialPosition) => (
        <Tooltip title={`On hand ${formatQty(r.on_hand)} minus what's reserved elsewhere`}>
          <Typography.Text type={Number(v) <= 0 ? "danger" : undefined}>
            {formatQty(v)}
          </Typography.Text>
        </Tooltip>
      ),
    },
  ];

  const txnColumns = (extra?: { title: string; key: keyof MaterialTxn }[]) => [
    {
      title: "Material",
      key: "m",
      render: (_: unknown, r: MaterialTxn) => (
        <Space direction="vertical" size={0}>
          <Typography.Text>{r.name}</Typography.Text>
          <Typography.Text type="secondary" style={{ fontSize: 11 }}>
            <code>{r.sku}</code>
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: "Quantity",
      dataIndex: "quantity",
      width: 120,
      align: "right" as const,
      render: (v: number, r: MaterialTxn) => `${formatQty(v)} ${r.uom_code ?? ""}`,
    },
    {
      title: "When",
      dataIndex: "created_at",
      width: 160,
      render: (v: string) => (v ? new Date(v).toLocaleString() : "—"),
    },
    ...(extra ?? []).map((e) => ({
      title: e.title,
      dataIndex: e.key as string,
      render: (v: unknown) => (v ? String(v) : <Typography.Text type="secondary">—</Typography.Text>),
    })),
  ];

  return (
    <Card
      size="small"
      title="Materials"
      loading={isLoading}
      extra={
        <Space wrap>
          <Button size="small" type="primary" onClick={() => setAction("reserve")}>
            Reserve
          </Button>
          <Button size="small" onClick={() => setAction("issue")}>
            Issue
          </Button>
          <Button size="small" onClick={() => setAction("consume")}>
            Record consumption
          </Button>
          <Button size="small" onClick={() => setAction("return")}>
            Return
          </Button>
          {anyReserved && (
            <Button size="small" danger onClick={() => releaseAll.mutate()} loading={releaseAll.isPending}>
              Release unused
            </Button>
          )}
        </Space>
      }
    >
      {summary && (
        <Space style={{ marginBottom: 10 }} wrap>
          <Tag color={summary.fully_reserved ? "green" : anyReserved ? "gold" : "default"}>
            {summary.fully_reserved ? "Fully reserved" : anyReserved ? "Partially reserved" : "Not reserved"}
          </Tag>
          <Tag color={summary.fully_issued ? "green" : lines.some((l) => Number(l.issued) > 0) ? "gold" : "default"}>
            {summary.fully_issued
              ? "Fully issued"
              : lines.some((l) => Number(l.issued) > 0)
                ? "Partially issued"
                : "Not issued"}
          </Tag>
        </Space>
      )}

      <Tabs
        size="small"
        items={[
          {
            key: "position",
            label: "Position",
            children: (
              <Table
                rowKey="material_id"
                size="small"
                pagination={false}
                columns={positionColumns}
                dataSource={lines}
                scroll={{ x: "max-content" }}
              />
            ),
          },
          {
            key: "reservations",
            label: `Reservations (${reservations?.length ?? 0})`,
            children: (
              <Table<MaterialReservation>
                rowKey="id"
                size="small"
                pagination={false}
                dataSource={reservations ?? []}
                scroll={{ x: "max-content" }}
                columns={[
                  {
                    title: "Material",
                    key: "m",
                    render: (_: unknown, r) => (
                      <Space direction="vertical" size={0}>
                        <Typography.Text>{r.name}</Typography.Text>
                        <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                          <code>{r.sku}</code>
                        </Typography.Text>
                      </Space>
                    ),
                  },
                  {
                    title: "Reserved",
                    dataIndex: "quantity",
                    width: 110,
                    align: "right",
                    render: (v: number, r) => `${formatQty(v)} ${r.uom_code ?? ""}`,
                  },
                  {
                    title: "Drawn down",
                    dataIndex: "issued_quantity",
                    width: 110,
                    align: "right",
                    render: (v: number) => formatQty(v),
                  },
                  {
                    title: "Outstanding",
                    dataIndex: "outstanding",
                    width: 110,
                    align: "right",
                    render: (v: number) => <Typography.Text strong>{formatQty(v)}</Typography.Text>,
                  },
                  {
                    title: "Status",
                    dataIndex: "status",
                    width: 140,
                    render: (s: string) => (
                      <Tag color={s === "active" ? "blue" : s === "released" ? "default" : "gold"}>
                        {s.replace("_", " ")}
                      </Tag>
                    ),
                  },
                ]}
              />
            ),
          },
          {
            key: "issues",
            label: `Issues (${issues?.length ?? 0})`,
            children: (
              <Table
                rowKey="id"
                size="small"
                pagination={false}
                dataSource={issues ?? []}
                scroll={{ x: "max-content" }}
                columns={txnColumns([{ title: "Unreserved reason", key: "unreserved_reason" }])}
              />
            ),
          },
          {
            key: "consumption",
            label: `Consumption (${consumption?.length ?? 0})`,
            children: (
              <Table
                rowKey="id"
                size="small"
                pagination={false}
                dataSource={consumption ?? []}
                scroll={{ x: "max-content" }}
                columns={txnColumns([{ title: "Over-consumption reason", key: "over_consumption_reason" }])}
              />
            ),
          },
          {
            key: "returns",
            label: `Returns (${returns?.length ?? 0})`,
            children: (
              <Table
                rowKey="id"
                size="small"
                pagination={false}
                dataSource={returns ?? []}
                scroll={{ x: "max-content" }}
                columns={txnColumns([{ title: "Reason", key: "reason" }])}
              />
            ),
          },
        ]}
      />

      <Modal
        title={action ? ACTION_META[action].title : ""}
        open={!!action}
        onCancel={close}
        onOk={() => submit.mutate()}
        confirmLoading={submit.isPending}
        okText={action ? ACTION_META[action].verb : "OK"}
        width={860}
      >
        {action && (
          <>
            <Alert
              type={action === "issue" || action === "return" ? "warning" : "info"}
              showIcon
              style={{ marginBottom: 12 }}
              message={
                action === "issue"
                  ? "This changes physical stock"
                  : action === "return"
                    ? "This puts material back into stock"
                    : action === "consume"
                      ? "This does not change stock again"
                      : "This does not change physical stock"
              }
              description={ACTION_META[action].help}
            />
            <Table
              rowKey="material_id"
              size="small"
              pagination={false}
              dataSource={lines}
              scroll={{ x: "max-content" }}
              columns={[
                {
                  title: "Material",
                  key: "m",
                  render: (_: unknown, r: MaterialPosition) => (
                    <Space direction="vertical" size={0}>
                      <Typography.Text>{r.name}</Typography.Text>
                      <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                        <code>{r.sku}</code>
                      </Typography.Text>
                    </Space>
                  ),
                },
                {
                  title: "Planned",
                  dataIndex: "planned",
                  width: 90,
                  align: "right",
                  render: (v: number) => formatQty(v),
                },
                {
                  title: "Reserved",
                  dataIndex: "reserved",
                  width: 90,
                  align: "right",
                  render: (v: number) => formatQty(v),
                },
                {
                  title: "Issued",
                  dataIndex: "issued",
                  width: 90,
                  align: "right",
                  render: (v: number) => formatQty(v),
                },
                {
                  title: "Max",
                  key: "max",
                  width: 90,
                  align: "right",
                  render: (_: unknown, r: MaterialPosition) => (
                    <Typography.Text type="secondary">
                      {formatQty(Math.max(LIMIT[action](r), 0))}
                    </Typography.Text>
                  ),
                },
                {
                  title: ACTION_META[action].column,
                  key: "input",
                  width: 200,
                  render: (_: unknown, r: MaterialPosition) => {
                    const max = Math.max(LIMIT[action](r), 0);
                    const overridden = !!overrides[r.material_id];
                    return (
                      <Space size={4}>
                        <InputNumber
                          size="small"
                          min={0}
                          step={1}
                          max={overridden ? undefined : max}
                          value={amounts[r.material_id]}
                          onChange={(v) =>
                            setAmounts((a) => ({ ...a, [r.material_id]: Number(v ?? 0) }))
                          }
                          style={{ width: 100 }}
                        />
                        {max > 0 && (
                          <Button
                            size="small"
                            type="link"
                            onClick={() =>
                              setAmounts((a) => ({ ...a, [r.material_id]: roundQty(max) }))
                            }
                          >
                            Max
                          </Button>
                        )}
                      </Space>
                    );
                  },
                },
                ...(action === "issue" || action === "consume"
                  ? [
                      {
                        title: action === "issue" ? "Beyond reserved" : "Beyond plan",
                        key: "override",
                        width: 210,
                        render: (_: unknown, r: MaterialPosition) => (
                          <Space direction="vertical" size={2} style={{ width: "100%" }}>
                            <Checkbox
                              checked={!!overrides[r.material_id]}
                              onChange={(e) =>
                                setOverrides((o) => ({ ...o, [r.material_id]: e.target.checked }))
                              }
                            >
                              <Typography.Text style={{ fontSize: 12 }}>Allow</Typography.Text>
                            </Checkbox>
                            {overrides[r.material_id] && (
                              <Input
                                size="small"
                                placeholder="Reason (required)"
                                value={reasons[r.material_id] ?? ""}
                                onChange={(e) =>
                                  setReasons((x) => ({ ...x, [r.material_id]: e.target.value }))
                                }
                              />
                            )}
                          </Space>
                        ),
                      },
                    ]
                  : []),
                ...(action === "return"
                  ? [
                      {
                        title: "Back into stock?",
                        key: "restock",
                        width: 220,
                        render: (_: unknown, r: MaterialPosition) => (
                          <Space direction="vertical" size={2} style={{ width: "100%" }}>
                            <Checkbox
                              checked={restock[r.material_id] !== false}
                              onChange={(e) =>
                                setRestock((x) => ({ ...x, [r.material_id]: e.target.checked }))
                              }
                            >
                              <Typography.Text style={{ fontSize: 12 }}>Restock</Typography.Text>
                            </Checkbox>
                            <Input
                              size="small"
                              placeholder="Reason"
                              value={reasons[r.material_id] ?? ""}
                              onChange={(e) =>
                                setReasons((x) => ({ ...x, [r.material_id]: e.target.value }))
                              }
                            />
                          </Space>
                        ),
                      },
                    ]
                  : []),
              ]}
            />
            {action === "issue" && (
              <Typography.Paragraph type="secondary" style={{ marginTop: 10, fontSize: 12 }}>
                Issuing beyond what's reserved needs the unreserved-issue permission. Without it the
                server will refuse, whatever this form allows.
              </Typography.Paragraph>
            )}
          </>
        )}
      </Modal>
    </Card>
  );
}
