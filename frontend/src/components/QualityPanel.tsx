import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Button,
  Card,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
  message,
} from "antd";
import { useState } from "react";
import {
  createQualityCheck,
  createRework,
  listDefectCategories,
  listQualityChecks,
  listRework,
  resolveRework,
} from "../api/manufacturing-endpoints";
import type { QcResult, QualityCheckOut, ReworkOut } from "../api/manufacturing-types";
import type { ProductionOrderDetail } from "../api/types";
import { formatQty, qtyInputProps } from "../utils/quantity";

const QC_COLOR: Record<QcResult, string> = { pass: "green", fail: "red", partial: "gold" };
const REWORK_COLOR: Record<string, string> = {
  open: "gold", in_progress: "blue", resolved: "green", cancelled: "default",
};

/** Quality checks and the rework they can trigger.
 *
 * A failed check does not un-make a garment or touch stock. Rework is tracked
 * against the *same* production order rather than spawning a duplicate one -
 * duplicating the order would be the wrong fix unless there's a real business
 * reason to split the run. */
export default function QualityPanel({ order }: { order: ProductionOrderDetail }) {
  const queryClient = useQueryClient();
  const [checking, setChecking] = useState(false);
  const [reworking, setReworking] = useState<QualityCheckOut | null>(null);
  const [checkForm] = Form.useForm();
  const [reworkForm] = Form.useForm();

  const { data: checks, isLoading: checksLoading } = useQuery({
    queryKey: ["quality-checks", order.id],
    queryFn: () => listQualityChecks(order.id).then((r) => r.data),
  });
  const { data: rework, isLoading: reworkLoading } = useQuery({
    queryKey: ["rework", order.id],
    queryFn: () => listRework(order.id).then((r) => r.data),
  });
  const { data: defectCategories } = useQuery({
    queryKey: ["defect-categories"],
    queryFn: () => listDefectCategories().then((r) => r.data),
    enabled: checking,
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["quality-checks", order.id] });
    queryClient.invalidateQueries({ queryKey: ["rework", order.id] });
    queryClient.invalidateQueries({ queryKey: ["production-history", order.id] });
  };

  const submitCheck = useMutation({
    mutationFn: (v: any) =>
      createQualityCheck(order.id, {
        result: v.result,
        checked_quantity: v.checked_quantity,
        failed_quantity: v.failed_quantity || 0,
        notes: v.notes,
      }),
    onSuccess: () => {
      message.success("Quality check recorded");
      setChecking(false);
      checkForm.resetFields();
      refresh();
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || "Could not record the check"),
  });

  const submitRework = useMutation({
    mutationFn: (v: any) =>
      createRework(order.id, {
        quantity: v.quantity,
        reason: v.reason,
        quality_check_id: reworking?.id ?? null,
      }),
    onSuccess: () => {
      message.success("Rework raised");
      setReworking(null);
      reworkForm.resetFields();
      refresh();
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || "Could not raise rework"),
  });

  const resolve = useMutation({
    mutationFn: (id: number) => resolveRework(id),
    onSuccess: () => {
      message.success("Rework resolved");
      refresh();
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || "Could not resolve"),
  });

  return (
    <Card
      size="small"
      title="Quality"
      extra={
        <Button size="small" type="primary" onClick={() => setChecking(true)}>
          New quality check
        </Button>
      }
    >
      <Tabs
        size="small"
        items={[
          {
            key: "checks",
            label: `Checks (${checks?.length ?? 0})`,
            children: (
              <Table<QualityCheckOut>
                rowKey="id"
                size="small"
                loading={checksLoading}
                pagination={false}
                dataSource={checks ?? []}
                locale={{ emptyText: "No checks yet" }}
                columns={[
                  { title: "Result", dataIndex: "result", width: 90, render: (v: QcResult) => <Tag color={QC_COLOR[v]}>{v}</Tag> },
                  { title: "Checked", dataIndex: "checked_quantity", width: 90, align: "right", render: formatQty },
                  { title: "Failed", dataIndex: "failed_quantity", width: 90, align: "right", render: (v: number) => Number(v) > 0 ? formatQty(v) : "—" },
                  { title: "Notes", dataIndex: "notes", render: (v: string | null) => v ?? "—" },
                  {
                    title: "When",
                    dataIndex: "checked_at",
                    width: 160,
                    render: (v: string | null) => (v ? new Date(v).toLocaleString() : "—"),
                  },
                  {
                    title: "",
                    key: "act",
                    width: 110,
                    render: (_: unknown, r: QualityCheckOut) =>
                      r.result !== "pass" && (
                        <Button size="small" onClick={() => setReworking(r)}>
                          Raise rework
                        </Button>
                      ),
                  },
                ]}
              />
            ),
          },
          {
            key: "rework",
            label: `Rework (${rework?.length ?? 0})`,
            children: (
              <Table<ReworkOut>
                rowKey="id"
                size="small"
                loading={reworkLoading}
                pagination={false}
                dataSource={rework ?? []}
                locale={{ emptyText: "No rework raised" }}
                columns={[
                  { title: "Number", dataIndex: "rework_number", width: 110, render: (v: string) => <code>{v}</code> },
                  { title: "Quantity", dataIndex: "quantity", width: 90, align: "right", render: formatQty },
                  { title: "Reason", dataIndex: "reason" },
                  { title: "Status", dataIndex: "status", width: 110, render: (v: string) => <Tag color={REWORK_COLOR[v]}>{v}</Tag> },
                  {
                    title: "",
                    key: "act",
                    width: 100,
                    render: (_: unknown, r: ReworkOut) =>
                      r.status !== "resolved" && r.status !== "cancelled" && (
                        <Button size="small" onClick={() => resolve.mutate(r.id)} loading={resolve.isPending}>
                          Resolve
                        </Button>
                      ),
                  },
                ]}
              />
            ),
          },
        ]}
      />

      <Modal
        title="Record a quality check"
        open={checking}
        onCancel={() => setChecking(false)}
        onOk={() => checkForm.submit()}
        confirmLoading={submitCheck.isPending}
      >
        <Form form={checkForm} layout="vertical" onFinish={(v) => submitCheck.mutate(v)}>
          <Form.Item name="result" label="Result" rules={[{ required: true }]}>
            <Select
              options={[
                { value: "pass", label: "Pass" },
                { value: "fail", label: "Fail" },
                { value: "partial", label: "Partial" },
              ]}
            />
          </Form.Item>
          <Form.Item name="checked_quantity" label="Quantity checked" rules={[{ required: true }]}>
            <InputNumber {...qtyInputProps} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="failed_quantity" label="Quantity failed">
            <InputNumber {...qtyInputProps} min={0} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="notes" label="Notes">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
        {!!defectCategories?.length && (
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            Defect categories are configured under Wastage &amp; Defect settings.
          </Typography.Text>
        )}
      </Modal>

      <Modal
        title={`Raise rework${reworking ? ` for check #${reworking.id}` : ""}`}
        open={!!reworking}
        onCancel={() => setReworking(null)}
        onOk={() => reworkForm.submit()}
        confirmLoading={submitRework.isPending}
      >
        <Typography.Paragraph type="secondary">
          Tracked against this production order — never a duplicate order — so history stays
          on one thread.
        </Typography.Paragraph>
        <Form
          form={reworkForm}
          layout="vertical"
          onFinish={(v) => submitRework.mutate(v)}
          initialValues={{ quantity: reworking?.failed_quantity ? Number(reworking.failed_quantity) : 1 }}
        >
          <Form.Item name="quantity" label="Quantity" rules={[{ required: true }]}>
            <InputNumber {...qtyInputProps} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="reason" label="Reason" rules={[{ required: true, message: "A reason is required" }]}>
            <Input.TextArea rows={2} placeholder="e.g. loose stitching on the sleeve seam" />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}
