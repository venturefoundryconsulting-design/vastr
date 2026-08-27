import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Card, Empty, Select, Space, Table, Tag, Tooltip, Typography, message } from "antd";
import { useState } from "react";
import { listOutlets } from "../api/endpoints";
import { generateMrpPurchaseOrders, getMrpRequirements } from "../api/manufacturing-endpoints";
import type { MrpRequirementRow } from "../api/manufacturing-types";
import { formatQty } from "../utils/quantity";

/** Aggregated demand across every open production order, netted against
 * on-hand minus reserved. Read-only until "Generate draft POs" is pressed -
 * and even then, what it creates is a DRAFT, inert until a human sends it. */
export default function Mrp() {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<number[]>([]);
  const [outletId, setOutletId] = useState<number | undefined>();

  const { data: rows, isLoading } = useQuery({
    queryKey: ["mrp-requirements"],
    queryFn: () => getMrpRequirements().then((r) => r.data),
  });
  const { data: outlets } = useQuery({ queryKey: ["outlets"], queryFn: () => listOutlets().then((r) => r.data) });

  const generate = useMutation({
    mutationFn: () => generateMrpPurchaseOrders(outletId!, selected.length ? selected : undefined),
    onSuccess: (r: any) => {
      const pos = r.data as { po_number: string }[];
      message.success(`Created ${pos.length} draft purchase order${pos.length === 1 ? "" : "s"}`);
      setSelected([]);
      queryClient.invalidateQueries({ queryKey: ["mrp-requirements"] });
      queryClient.invalidateQueries({ queryKey: ["purchase-orders"] });
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || "Could not generate purchase orders"),
  });

  const shortRows = (rows ?? []).filter((r) => Number(r.shortage) > 0);

  const columns = [
    {
      title: "Material",
      key: "m",
      render: (_: unknown, r: MrpRequirementRow) => (
        <Space direction="vertical" size={0}>
          <Typography.Text>{r.name}</Typography.Text>
          <Typography.Text type="secondary" style={{ fontSize: 11 }}>
            <code>{r.sku}</code>
          </Typography.Text>
        </Space>
      ),
    },
    { title: "Required", dataIndex: "required", width: 100, align: "right" as const, render: (v: number, r: MrpRequirementRow) => `${formatQty(v)} ${r.uom_code ?? ""}` },
    { title: "On hand", dataIndex: "on_hand", width: 100, align: "right" as const, render: formatQty },
    { title: "Reserved", dataIndex: "reserved", width: 100, align: "right" as const, render: formatQty },
    { title: "Available", dataIndex: "available", width: 100, align: "right" as const, render: formatQty },
    {
      title: "Shortage",
      dataIndex: "shortage",
      width: 100,
      align: "right" as const,
      render: (v: number) =>
        Number(v) > 0 ? <Typography.Text type="danger" strong>{formatQty(v)}</Typography.Text> : <Typography.Text type="secondary">—</Typography.Text>,
    },
    {
      title: "Suggested purchase",
      dataIndex: "suggested_purchase_qty",
      width: 150,
      align: "right" as const,
      render: (v: number, r: MrpRequirementRow) =>
        Number(v) > 0 ? (
          <Tooltip title={r.min_order_qty ? `Vendor minimum order: ${formatQty(r.min_order_qty)}` : undefined}>
            <Typography.Text strong>{formatQty(v)}</Typography.Text>
          </Tooltip>
        ) : (
          "—"
        ),
    },
    {
      title: "Preferred vendor",
      key: "v",
      width: 150,
      render: (_: unknown, r: MrpRequirementRow) =>
        r.preferred_vendor_name ?? <Typography.Text type="warning">None set</Typography.Text>,
    },
    {
      title: "Contributing orders",
      key: "orders",
      render: (_: unknown, r: MrpRequirementRow) => (
        <Space size={4} wrap>
          {r.contributing_orders.map((o) => (
            <Tag key={o.production_order_id}>{o.po_number}</Tag>
          ))}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Typography.Title level={3} style={{ margin: "0 0 8px" }}>
        Material Requirement Planning
      </Typography.Title>
      <Typography.Paragraph type="secondary">
        Aggregated across every released or in-progress production order. Nothing here is committed
        automatically — select rows and generate draft purchase orders when you're ready to buy.
      </Typography.Paragraph>

      {!!shortRows.length && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message={`${shortRows.length} material${shortRows.length === 1 ? " is" : "s are"} short across open production`}
        />
      )}

      <Space style={{ marginBottom: 12 }} wrap>
        <Select
          placeholder="Outlet to receive against"
          style={{ width: 220 }}
          value={outletId}
          onChange={setOutletId}
          options={outlets?.map((o) => ({ value: o.id, label: o.name }))}
        />
        <Button
          type="primary"
          disabled={!outletId || !shortRows.length}
          loading={generate.isPending}
          onClick={() => generate.mutate()}
        >
          Generate draft purchase order{selected.length ? "s" : ""} {selected.length ? `(${selected.length} selected)` : "(all short items)"}
        </Button>
      </Space>

      <Card size="small" styles={{ body: { padding: 0 } }}>
        <Table<MrpRequirementRow>
          rowKey="item_id"
          loading={isLoading}
          columns={columns}
          dataSource={rows}
          pagination={{ pageSize: 25 }}
          scroll={{ x: "max-content" }}
          rowSelection={{
            selectedRowKeys: selected,
            onChange: (keys) => setSelected(keys as number[]),
            getCheckboxProps: (r) => ({ disabled: Number(r.shortage) <= 0 }),
          }}
          locale={{ emptyText: <Empty description="No open production orders need material right now" /> }}
        />
      </Card>
    </div>
  );
}
