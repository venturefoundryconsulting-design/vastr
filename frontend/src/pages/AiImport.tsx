import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Empty,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
  Typography,
  Upload,
  message,
} from "antd";
import { InboxOutlined } from "@ant-design/icons";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { listItems, listOutlets, listUoms, listVendors } from "../api/endpoints";
import {
  approveAiImportBatch,
  extractAiImportInvoice,
  getAiImportBatch,
  listAiImportBatches,
  patchAiImportRow,
  rejectAiImportBatch,
} from "../api/manufacturing-endpoints";
import type { AiImportRowOut, AiImportStatus } from "../api/manufacturing-types";
import { formatQty } from "../utils/quantity";

const STATUS_COLOR: Record<AiImportStatus, string> = { pending: "gold", approved: "green", rejected: "default" };

function ConfidenceTag({ value }: { value: number | null | undefined }) {
  if (value == null) return <Typography.Text type="secondary">—</Typography.Text>;
  const pct = Math.round(value * 100);
  const color = value >= 0.8 ? "green" : value >= 0.5 ? "gold" : "red";
  return <Tag color={color}>{pct}%</Tag>;
}

/** Upload an invoice photo, let the model propose lines, a human corrects and
 * approves. Approval only ever creates a DRAFT goods receipt - it never posts
 * one, so nothing here can move stock without a second, separate action in
 * Goods Receipts. */
export default function AiImport() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [statusFilter, setStatusFilter] = useState<AiImportStatus | undefined>();
  const [uploading, setUploading] = useState(false);
  const [uploadOutlet, setUploadOutlet] = useState<number | undefined>();
  const [uploadVendor, setUploadVendor] = useState<number | undefined>();
  const [openBatchId, setOpenBatchId] = useState<number | null>(null);

  const { data: batches, isLoading } = useQuery({
    queryKey: ["ai-import-batches", statusFilter],
    queryFn: () => listAiImportBatches(statusFilter).then((r) => r.data),
  });
  const { data: outlets } = useQuery({ queryKey: ["outlets"], queryFn: () => listOutlets().then((r) => r.data) });
  const { data: vendors } = useQuery({ queryKey: ["vendors"], queryFn: () => listVendors().then((r) => r.data) });

  const extract = useMutation({
    mutationFn: (file: File) => extractAiImportInvoice(file, uploadOutlet!, uploadVendor),
    onSuccess: (r) => {
      message.success(`Extracted ${r.data.rows.length} line${r.data.rows.length === 1 ? "" : "s"}`);
      queryClient.invalidateQueries({ queryKey: ["ai-import-batches"] });
      setUploading(false);
      setOpenBatchId(r.data.id);
    },
    onError: (e: any) => {
      message.error(e?.response?.data?.detail || "Extraction failed");
      setUploading(false);
    },
  });

  const columns = [
    { title: "File", dataIndex: "source_filename", ellipsis: true },
    { title: "Outlet", dataIndex: "outlet_name", width: 140, render: (v: string | null) => v ?? "—" },
    { title: "Vendor", dataIndex: "vendor_name", width: 160, render: (v: string | null) => v ?? <Typography.Text type="secondary">unmatched</Typography.Text> },
    { title: "Lines", dataIndex: "line_count", width: 80, align: "center" as const },
    { title: "Status", dataIndex: "status", width: 100, render: (v: AiImportStatus) => <Tag color={STATUS_COLOR[v]}>{v}</Tag> },
    { title: "Uploaded", dataIndex: "created_at", width: 160, render: (v: string) => new Date(v).toLocaleString() },
    {
      title: "",
      key: "act",
      width: 90,
      render: (_: unknown, r: any) => <Button size="small" onClick={() => setOpenBatchId(r.id)}>Review</Button>,
    },
  ];

  return (
    <div>
      <Space style={{ width: "100%", justifyContent: "space-between", marginBottom: 16 }} wrap>
        <Typography.Title level={3} style={{ margin: 0 }}>
          AI Invoice Import
        </Typography.Title>
        <Button type="primary" onClick={() => setUploading(true)}>
          Upload invoice
        </Button>
      </Space>
      <Typography.Paragraph type="secondary">
        Upload a photo of a vendor invoice. The model proposes line items, matched against your
        existing materials where it can — nothing is created until you review and approve it into a
        draft goods receipt, and that receipt still needs its own separate "Post" before any stock moves.
      </Typography.Paragraph>

      <Select
        allowClear
        placeholder="All statuses"
        style={{ width: 180, marginBottom: 12 }}
        value={statusFilter}
        onChange={setStatusFilter}
        options={[
          { value: "pending", label: "Pending review" },
          { value: "approved", label: "Approved" },
          { value: "rejected", label: "Rejected" },
        ]}
      />

      <Card size="small" styles={{ body: { padding: 0 } }}>
        <Table
          rowKey="id"
          loading={isLoading}
          columns={columns}
          dataSource={batches}
          pagination={{ pageSize: 20 }}
          scroll={{ x: "max-content" }}
          locale={{ emptyText: <Empty description="No invoices imported yet" /> }}
        />
      </Card>

      <Modal
        title="Upload an invoice"
        open={uploading}
        onCancel={() => setUploading(false)}
        footer={null}
      >
        <Space direction="vertical" style={{ width: "100%" }} size="middle">
          <div>
            <Typography.Text strong>Outlet receiving the goods</Typography.Text>
            <Select
              style={{ width: "100%", marginTop: 4 }}
              placeholder="Select outlet"
              value={uploadOutlet}
              onChange={setUploadOutlet}
              options={outlets?.map((o) => ({ value: o.id, label: o.name }))}
            />
          </div>
          <div>
            <Typography.Text strong>Vendor (optional — helps if known)</Typography.Text>
            <Select
              allowClear
              style={{ width: "100%", marginTop: 4 }}
              placeholder="Select vendor"
              value={uploadVendor}
              onChange={setUploadVendor}
              options={vendors?.map((v) => ({ value: v.id, label: v.name }))}
            />
          </div>
          <Upload.Dragger
            accept="image/jpeg,image/png,image/webp"
            multiple={false}
            showUploadList={false}
            disabled={!uploadOutlet || extract.isPending}
            beforeUpload={(file) => {
              extract.mutate(file);
              return false;
            }}
          >
            <p className="ant-upload-drag-icon">
              <InboxOutlined />
            </p>
            <p className="ant-upload-text">
              {extract.isPending ? "Extracting…" : "Click or drag a JPEG/PNG/WebP photo of the invoice"}
            </p>
            {!uploadOutlet && <p className="ant-upload-hint">Pick an outlet first</p>}
          </Upload.Dragger>
        </Space>
      </Modal>

      {openBatchId != null && (
        <BatchReview batchId={openBatchId} onClose={() => setOpenBatchId(null)} onApproved={(receiptId) => navigate(`/goods-receipts`)} />
      )}
    </div>
  );
}

function BatchReview({
  batchId,
  onClose,
  onApproved,
}: {
  batchId: number;
  onClose: () => void;
  onApproved: (receiptId: number) => void;
}) {
  const queryClient = useQueryClient();
  const { data: batch, isLoading } = useQuery({
    queryKey: ["ai-import-batch", batchId],
    queryFn: () => getAiImportBatch(batchId).then((r) => r.data),
  });
  const { data: items } = useQuery({
    queryKey: ["items-all"],
    queryFn: () => listItems({ is_active: true }).then((r) => r.data),
  });
  const { data: uoms } = useQuery({ queryKey: ["uoms"], queryFn: () => listUoms().then((r) => r.data) });

  const itemOptions = useMemo(
    () => (items ?? []).map((i) => ({ value: i.id, label: `${i.display_name || i.name || i.sku} — ${i.sku}` })),
    [items],
  );

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["ai-import-batch", batchId] });
    queryClient.invalidateQueries({ queryKey: ["ai-import-batches"] });
  };

  const patchRow = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<AiImportRowOut> }) => patchAiImportRow(id, data as any),
    onSuccess: refresh,
    onError: (e: any) => message.error(e?.response?.data?.detail || "Could not update the line"),
  });

  const approve = useMutation({
    mutationFn: () => approveAiImportBatch(batchId),
    onSuccess: (r) => {
      message.success(`Draft goods receipt ${r.data.goods_receipt_number} created`);
      refresh();
      onApproved(r.data.goods_receipt_id!);
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || "Could not approve this batch"),
  });

  const reject = useMutation({
    mutationFn: () => rejectAiImportBatch(batchId),
    onSuccess: () => {
      message.success("Batch rejected");
      refresh();
      onClose();
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || "Could not reject this batch"),
  });

  const isPending = batch?.status === "pending";

  return (
    <Modal
      title={batch ? `Review — ${batch.source_filename}` : "Review"}
      open
      onCancel={onClose}
      width={960}
      footer={
        isPending
          ? [
              <Button key="reject" danger onClick={() => reject.mutate()} loading={reject.isPending}>
                Reject
              </Button>,
              <Button key="approve" type="primary" onClick={() => approve.mutate()} loading={approve.isPending}>
                Approve → create draft receipt
              </Button>,
            ]
          : null
      }
    >
      {isLoading || !batch ? (
        <Card loading />
      ) : (
        <>
          {batch.status !== "pending" && (
            <Alert
              style={{ marginBottom: 12 }}
              type={batch.status === "approved" ? "success" : "warning"}
              showIcon
              message={
                batch.status === "approved"
                  ? `Approved — draft receipt ${batch.goods_receipt_number}`
                  : "Rejected"
              }
            />
          )}
          <Space style={{ marginBottom: 12 }} wrap>
            <Typography.Text type="secondary">Vendor on invoice:</Typography.Text>
            <Typography.Text>{batch.vendor_name_guess ?? batch.vendor_name ?? "unrecognised"}</Typography.Text>
            {batch.invoice_ref_guess && (
              <>
                <Typography.Text type="secondary">Ref:</Typography.Text>
                <Typography.Text code>{batch.invoice_ref_guess}</Typography.Text>
              </>
            )}
          </Space>
          <Table
            rowKey="id"
            size="small"
            pagination={false}
            dataSource={batch.rows}
            scroll={{ x: "max-content" }}
            columns={[
              {
                title: "Include",
                key: "inc",
                width: 60,
                render: (_: unknown, r: AiImportRowOut) => (
                  <Checkbox
                    checked={!r.excluded}
                    disabled={!isPending}
                    onChange={(e) => patchRow.mutate({ id: r.id, data: { excluded: !e.target.checked } })}
                  />
                ),
              },
              {
                title: "As read",
                dataIndex: "raw_description",
                width: 180,
                render: (v: string, r: AiImportRowOut) => (
                  <Space direction="vertical" size={0}>
                    <Typography.Text>{v}</Typography.Text>
                    <ConfidenceTag value={r.description_confidence} />
                  </Space>
                ),
              },
              {
                title: "Match",
                key: "match",
                width: 220,
                render: (_: unknown, r: AiImportRowOut) =>
                  isPending ? (
                    <Space direction="vertical" size={4} style={{ width: "100%" }}>
                      <Select
                        size="small"
                        allowClear
                        showSearch
                        optionFilterProp="label"
                        style={{ width: "100%" }}
                        placeholder="Match an existing item"
                        value={r.matched_item_id ?? undefined}
                        options={itemOptions}
                        onChange={(v) =>
                          patchRow.mutate({ id: r.id, data: { matched_item_id: v ?? null, is_new_item: !v } })
                        }
                      />
                      {r.is_new_item && (
                        <Input
                          size="small"
                          placeholder="New item SKU"
                          defaultValue={r.proposed_sku ?? ""}
                          onBlur={(e) => patchRow.mutate({ id: r.id, data: { proposed_sku: e.target.value } })}
                        />
                      )}
                      {!r.is_new_item && r.match_confidence != null && <ConfidenceTag value={r.match_confidence} />}
                    </Space>
                  ) : (
                    <Typography.Text>{r.matched_item_name ?? `New: ${r.proposed_sku ?? "—"}`}</Typography.Text>
                  ),
              },
              {
                title: "Qty",
                key: "qty",
                width: 130,
                render: (_: unknown, r: AiImportRowOut) =>
                  isPending ? (
                    <Space direction="vertical" size={4} style={{ width: "100%" }}>
                      <InputNumber
                        size="small"
                        min={0}
                        style={{ width: "100%" }}
                        value={r.quantity}
                        onChange={(v) => patchRow.mutate({ id: r.id, data: { quantity: Number(v ?? 0) } })}
                      />
                      <Select
                        size="small"
                        style={{ width: "100%" }}
                        placeholder="Unit"
                        status={r.uom_id ? undefined : "error"}
                        value={r.uom_id ?? undefined}
                        options={uoms?.map((u) => ({ value: u.id, label: u.code }))}
                        onChange={(v) => patchRow.mutate({ id: r.id, data: { uom_id: v } })}
                      />
                      <ConfidenceTag value={r.quantity_confidence} />
                    </Space>
                  ) : (
                    `${formatQty(r.quantity)} ${r.uom_code ?? ""}`
                  ),
              },
              {
                title: "Unit cost",
                key: "cost",
                width: 130,
                render: (_: unknown, r: AiImportRowOut) =>
                  isPending ? (
                    <Space direction="vertical" size={0}>
                      <InputNumber
                        size="small"
                        min={0}
                        style={{ width: "100%" }}
                        prefix="₹"
                        value={r.unit_cost}
                        onChange={(v) => patchRow.mutate({ id: r.id, data: { unit_cost: Number(v ?? 0) } })}
                      />
                      <ConfidenceTag value={r.cost_confidence} />
                    </Space>
                  ) : (
                    `₹${Number(r.unit_cost).toFixed(2)}`
                  ),
              },
              {
                title: "",
                key: "warn",
                width: 40,
                render: (_: unknown, r: AiImportRowOut) =>
                  !r.uom_id && !r.excluded ? (
                    <Tooltip title="No unit of measure recognised — this line needs one before approval">
                      <Tag color="red">?</Tag>
                    </Tooltip>
                  ) : null,
              },
            ]}
          />
        </>
      )}
    </Modal>
  );
}
