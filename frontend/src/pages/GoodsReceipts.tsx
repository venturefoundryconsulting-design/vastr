import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
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
import { listItems, listOutlets, listVendors } from "../api/endpoints";
import {
  createGoodsReceipt,
  createPurchaseReturn,
  listGoodsReceipts,
  postGoodsReceipt,
} from "../api/manufacturing-endpoints";
import type { GoodsReceiptOut, ReceiptStatus } from "../api/manufacturing-types";
import { formatQty } from "../utils/quantity";

const STATUS_COLOR: Record<ReceiptStatus, string> = { draft: "gold", posted: "green", cancelled: "default" };

interface DraftLine {
  key: string;
  item_id?: number;
  quantity: number;
  unit_cost: number;
}

export default function GoodsReceipts() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<ReceiptStatus | undefined>();
  const [creating, setCreating] = useState(false);
  const [returning, setReturning] = useState<GoodsReceiptOut | null>(null);
  const [lines, setLines] = useState<DraftLine[]>([{ key: "l0", quantity: 1, unit_cost: 0 }]);
  const [returnQty, setReturnQty] = useState<Record<number, number>>({});
  const [returnReason, setReturnReason] = useState("");
  const [form] = Form.useForm();

  const { data: receipts, isLoading } = useQuery({
    queryKey: ["goods-receipts", statusFilter],
    queryFn: () => listGoodsReceipts({ status: statusFilter }).then((r) => r.data),
  });
  const { data: vendors } = useQuery({ queryKey: ["vendors"], queryFn: () => listVendors().then((r) => r.data), enabled: creating });
  const { data: outlets } = useQuery({ queryKey: ["outlets"], queryFn: () => listOutlets().then((r) => r.data), enabled: creating });
  const { data: items } = useQuery({
    queryKey: ["items-all"],
    queryFn: () => listItems({ is_active: true }).then((r) => r.data),
    enabled: creating,
  });

  const itemOptions = useMemo(
    () => (items ?? []).map((i) => ({ value: i.id, label: `${i.display_name || i.name || i.sku} — ${i.sku}` })),
    [items],
  );

  const close = () => {
    setCreating(false);
    setLines([{ key: "l0", quantity: 1, unit_cost: 0 }]);
    form.resetFields();
  };

  const create = useMutation({
    mutationFn: (header: any) =>
      createGoodsReceipt({
        vendor_id: header.vendor_id,
        outlet_id: header.outlet_id,
        vendor_invoice_ref: header.vendor_invoice_ref,
        notes: header.notes,
        lines: lines
          .filter((l) => l.item_id)
          .map((l) => ({ item_id: l.item_id!, quantity: l.quantity, unit_cost: l.unit_cost })),
      }),
    onSuccess: () => {
      message.success("Draft receipt created");
      queryClient.invalidateQueries({ queryKey: ["goods-receipts"] });
      close();
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || "Could not create the receipt"),
  });

  const post = useMutation({
    mutationFn: (id: number) => postGoodsReceipt(id),
    onSuccess: () => {
      message.success("Receipt posted — stock updated");
      queryClient.invalidateQueries({ queryKey: ["goods-receipts"] });
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || "Could not post the receipt"),
  });

  const doReturn = useMutation({
    mutationFn: () =>
      createPurchaseReturn({
        goods_receipt_id: returning!.id,
        vendor_id: returning!.vendor_id,
        outlet_id: returning!.outlet_id,
        reason: returnReason,
        lines: Object.entries(returnQty)
          .filter(([, q]) => q > 0)
          .map(([lineId, quantity]) => {
            const line = returning!.items.find((i) => i.id === Number(lineId))!;
            return { goods_receipt_item_id: line.id, item_id: line.item_id, quantity };
          }),
      }),
    onSuccess: () => {
      message.success("Return posted");
      setReturning(null);
      setReturnQty({});
      setReturnReason("");
      queryClient.invalidateQueries({ queryKey: ["goods-receipts"] });
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || "Could not post the return"),
  });

  const addLine = () => setLines((p) => [...p, { key: `l${p.length}${Date.now()}`, quantity: 1, unit_cost: 0 }]);
  const removeLine = (key: string) => setLines((p) => p.filter((l) => l.key !== key));
  const patchLine = (key: string, patch: Partial<DraftLine>) =>
    setLines((p) => p.map((l) => (l.key === key ? { ...l, ...patch } : l)));

  const columns = [
    { title: "Receipt", dataIndex: "receipt_number", width: 130, render: (v: string) => <code>{v}</code> },
    { title: "Vendor", dataIndex: "vendor_name", width: 160, render: (v: string | null) => v ?? "—" },
    { title: "PO", dataIndex: "po_number", width: 110, render: (v: string | null) => v ?? "—" },
    { title: "Total cost", dataIndex: "total_cost", width: 110, align: "right" as const, render: (v: number) => `₹${Number(v).toFixed(2)}` },
    { title: "Status", dataIndex: "status", width: 100, render: (v: ReceiptStatus) => <Tag color={STATUS_COLOR[v]}>{v}</Tag> },
    { title: "Date", dataIndex: "receipt_date", width: 110, render: (v: string | null) => v ?? "—" },
    {
      title: "",
      key: "act",
      width: 170,
      render: (_: unknown, r: GoodsReceiptOut) => (
        <Space>
          {r.status === "draft" && (
            <Button size="small" type="primary" onClick={() => post.mutate(r.id)} loading={post.isPending}>
              Post
            </Button>
          )}
          {r.status === "posted" && (
            <Button size="small" onClick={() => setReturning(r)}>
              Return
            </Button>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16, width: "100%", justifyContent: "space-between" }} wrap>
        <Typography.Title level={3} style={{ margin: 0 }}>
          Goods Receipts
        </Typography.Title>
        <Button type="primary" onClick={() => setCreating(true)}>
          New receipt
        </Button>
      </Space>

      <Select
        allowClear
        placeholder="All statuses"
        style={{ width: 180, marginBottom: 12 }}
        value={statusFilter}
        onChange={setStatusFilter}
        options={[
          { value: "draft", label: "Draft" },
          { value: "posted", label: "Posted" },
          { value: "cancelled", label: "Cancelled" },
        ]}
      />

      <Card size="small" styles={{ body: { padding: 0 } }}>
        <Table
          rowKey="id"
          loading={isLoading}
          columns={columns}
          dataSource={receipts}
          pagination={{ pageSize: 20 }}
          scroll={{ x: "max-content" }}
          expandable={{
            expandedRowRender: (r: GoodsReceiptOut) => (
              <Table
                size="small"
                rowKey="id"
                pagination={false}
                dataSource={r.items}
                columns={[
                  { title: "Item", key: "i", render: (_: unknown, x: any) => `${x.name} (${x.sku})` },
                  { title: "Counted", key: "c", render: (_: unknown, x: any) => `${formatQty(x.quantity)} ${x.uom_code ?? ""}` },
                  { title: "Into stock", dataIndex: "quantity_in_stock_uom", render: formatQty },
                  { title: "Unit cost", dataIndex: "unit_cost", render: (v: number) => `₹${Number(v).toFixed(2)}` },
                ]}
              />
            ),
          }}
          locale={{ emptyText: <Empty description="No goods receipts yet" /> }}
        />
      </Card>

      <Modal title="New goods receipt" open={creating} onCancel={close} onOk={() => form.submit()} confirmLoading={create.isPending} width={760}>
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="Stock does not move until this is posted"
          description="A draft can be checked and priced first."
        />
        <Form form={form} layout="vertical" onFinish={(v) => create.mutate(v)}>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="vendor_id" label="Vendor">
                <Select allowClear showSearch optionFilterProp="label" options={vendors?.map((v) => ({ value: v.id, label: v.name }))} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="outlet_id" label="Outlet" rules={[{ required: true }]}>
                <Select options={outlets?.map((o) => ({ value: o.id, label: o.name }))} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="vendor_invoice_ref" label="Vendor invoice #">
            <Input />
          </Form.Item>

          <Typography.Text strong>Lines</Typography.Text>
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
                  <Select size="small" showSearch optionFilterProp="label" style={{ width: 220 }} options={itemOptions} value={r.item_id} onChange={(v) => patchLine(r.key, { item_id: v })} />
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
                title: "Unit cost",
                key: "cost",
                width: 110,
                render: (_: unknown, r: DraftLine) => (
                  <InputNumber size="small" min={0} step={1} value={r.unit_cost} onChange={(v) => patchLine(r.key, { unit_cost: Number(v ?? 0) })} style={{ width: "100%" }} />
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
            + Add line
          </Button>
          <Form.Item name="notes" label="Notes" style={{ marginTop: 12 }}>
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={returning ? `Return goods — ${returning.receipt_number}` : ""}
        open={!!returning}
        onCancel={() => setReturning(null)}
        onOk={() => doReturn.mutate()}
        confirmLoading={doReturn.isPending}
      >
        {returning && (
          <>
            <Descriptions size="small" column={1} style={{ marginBottom: 12 }}>
              <Descriptions.Item label="Vendor">{returning.vendor_name ?? "—"}</Descriptions.Item>
            </Descriptions>
            <Table
              rowKey="id"
              size="small"
              pagination={false}
              dataSource={returning.items}
              columns={[
                { title: "Item", key: "i", render: (_: unknown, x: any) => `${x.name} (${x.sku})` },
                { title: "Received", dataIndex: "quantity_in_stock_uom", width: 90, align: "right", render: formatQty },
                {
                  title: "Return",
                  key: "r",
                  width: 110,
                  render: (_: unknown, x: any) => (
                    <InputNumber
                      size="small"
                      min={0}
                      max={Number(x.quantity_in_stock_uom)}
                      value={returnQty[x.id]}
                      onChange={(v) => setReturnQty((m) => ({ ...m, [x.id]: Number(v ?? 0) }))}
                      style={{ width: "100%" }}
                    />
                  ),
                },
              ]}
            />
            <Input
              placeholder="Reason"
              value={returnReason}
              onChange={(e) => setReturnReason(e.target.value)}
              style={{ marginTop: 12 }}
            />
          </>
        )}
      </Modal>
    </div>
  );
}
