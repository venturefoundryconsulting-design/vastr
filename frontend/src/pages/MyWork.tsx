import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, Col, Empty, Form, Input, InputNumber, Modal, Row, Space, Tag, Typography, message } from "antd";
import { useState } from "react";
import {
  cancelWorkOrder,
  completeWorkOrder,
  listMyWorkOrders,
  pauseWorkOrder,
  reportWorkOrderIssue,
  startWorkOrder,
} from "../api/manufacturing-endpoints";
import type { WorkOrderOut, WorkOrderStatus } from "../api/manufacturing-types";
import { formatQty, qtyInputProps } from "../utils/quantity";

const STATUS_COLOR: Record<WorkOrderStatus, string> = {
  pending: "default", assigned: "blue", in_progress: "processing",
  paused: "orange", completed: "green", rework: "volcano", cancelled: "default",
};

/** A tailor's own queue - deliberately not the full ERP. Start, pause,
 * complete and report-issue on their own jobs only; the server scopes this to
 * the caller's own tailor record. */
export default function MyWork() {
  const queryClient = useQueryClient();
  const [completing, setCompleting] = useState<WorkOrderOut | null>(null);
  const [reporting, setReporting] = useState<WorkOrderOut | null>(null);
  const [completeForm] = Form.useForm();
  const [issueForm] = Form.useForm();

  const { data: orders, isLoading } = useQuery({
    queryKey: ["my-work-orders"],
    queryFn: () => listMyWorkOrders().then((r) => r.data),
    refetchInterval: 30000,
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["my-work-orders"] });

  const act = (fn: () => Promise<unknown>, label: string) =>
    fn()
      .then(() => {
        message.success(label);
        refresh();
      })
      .catch((e: any) => message.error(e?.response?.data?.detail || `Could not ${label.toLowerCase()}`));

  const complete = useMutation({
    mutationFn: (v: any) => completeWorkOrder(completing!.id, v.completed_quantity, v.hours),
    onSuccess: () => {
      message.success("Marked complete");
      setCompleting(null);
      completeForm.resetFields();
      refresh();
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || "Could not complete"),
  });

  const report = useMutation({
    mutationFn: (v: any) => reportWorkOrderIssue(reporting!.id, v.reason),
    onSuccess: () => {
      message.success("Issue reported");
      setReporting(null);
      issueForm.resetFields();
      refresh();
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || "Could not report the issue"),
  });

  const active = (orders ?? []).filter((o) => !["completed", "cancelled"].includes(o.status));

  return (
    <div style={{ maxWidth: 640 }}>
      <Typography.Title level={3} style={{ margin: "0 0 16px" }}>
        My Work
      </Typography.Title>

      {isLoading && <Card loading />}
      {!isLoading && !active.length && (
        <Empty description="Nothing assigned right now" />
      )}

      <Row gutter={[12, 12]}>
        {active.map((wo) => (
          <Col span={24} key={wo.id}>
            <Card size="small">
              <Space style={{ width: "100%", justifyContent: "space-between" }} align="start">
                <Space direction="vertical" size={2}>
                  <Space>
                    <Typography.Text strong>{wo.item_name}</Typography.Text>
                    <Tag color={STATUS_COLOR[wo.status]}>{wo.status.replace("_", " ")}</Tag>
                    {wo.is_overdue && <Tag color="red">overdue</Tag>}
                  </Space>
                  <Typography.Text type="secondary">
                    {wo.stage_name} · <code>{wo.po_number}</code> · {formatQty(wo.quantity)} pcs
                  </Typography.Text>
                  {wo.due_date && (
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      Due {wo.due_date}
                    </Typography.Text>
                  )}
                  {wo.issue_note && (
                    <Typography.Text type="warning" style={{ fontSize: 12 }}>
                      Reported: {wo.issue_note}
                    </Typography.Text>
                  )}
                </Space>
              </Space>

              <Space style={{ marginTop: 12 }} wrap>
                {wo.status === "assigned" && (
                  <Button type="primary" onClick={() => act(() => startWorkOrder(wo.id), "Started")}>
                    Start
                  </Button>
                )}
                {wo.status === "in_progress" && (
                  <>
                    <Button onClick={() => act(() => pauseWorkOrder(wo.id), "Paused")}>Pause</Button>
                    <Button type="primary" onClick={() => setCompleting(wo)}>
                      Complete
                    </Button>
                    <Button danger onClick={() => setReporting(wo)}>
                      Report issue
                    </Button>
                  </>
                )}
                {wo.status === "paused" && (
                  <Button type="primary" onClick={() => act(() => startWorkOrder(wo.id), "Resumed")}>
                    Resume
                  </Button>
                )}
                {["assigned", "in_progress", "paused"].includes(wo.status) && (
                  <Button
                    danger
                    type="text"
                    onClick={() =>
                      Modal.confirm({
                        title: "Cancel this job?",
                        okText: "Cancel job",
                        okButtonProps: { danger: true },
                        cancelText: "Keep it",
                        onOk: () => act(() => cancelWorkOrder(wo.id), "Cancelled"),
                      })
                    }
                  >
                    Cancel
                  </Button>
                )}
              </Space>
            </Card>
          </Col>
        ))}
      </Row>

      <Modal
        title="Complete this job"
        open={!!completing}
        onCancel={() => setCompleting(null)}
        onOk={() => completeForm.submit()}
        confirmLoading={complete.isPending}
      >
        <Form
          form={completeForm}
          layout="vertical"
          onFinish={(v) => complete.mutate(v)}
          initialValues={{ completed_quantity: completing ? Number(completing.quantity) : 1 }}
        >
          <Form.Item name="completed_quantity" label="Quantity completed">
            <InputNumber {...qtyInputProps} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="hours" label="Hours worked (if paid hourly)">
            <InputNumber min={0} step={0.5} style={{ width: "100%" }} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="Report an issue"
        open={!!reporting}
        onCancel={() => setReporting(null)}
        onOk={() => issueForm.submit()}
        confirmLoading={report.isPending}
      >
        <Form form={issueForm} layout="vertical" onFinish={(v) => report.mutate(v)}>
          <Form.Item name="reason" label="What's wrong?" rules={[{ required: true }]}>
            <Input.TextArea rows={3} placeholder="e.g. the fabric doesn't match the sample" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
