import { CheckOutlined, DollarOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, DatePicker, Form, InputNumber, Space, Table, Tag, Typography, message } from "antd";
import dayjs from "dayjs";
import { useState } from "react";
import { generatePayslips, listPayslips, listSalaries, updatePayslip, updateSalary } from "../api/endpoints";
import type { Payslip, StaffSalary } from "../api/types";

const PAYSLIP_STATUS_COLORS: Record<string, string> = { draft: "gold", paid: "green" };

function SalarySetupTab() {
  const queryClient = useQueryClient();
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form] = Form.useForm();

  const { data: salaries, isLoading } = useQuery({
    queryKey: ["staff-salaries"],
    queryFn: () => listSalaries().then((r) => r.data),
  });

  const saveMutation = useMutation({
    mutationFn: ({ staffId, monthly_salary, notes }: { staffId: number; monthly_salary: number; notes?: string }) =>
      updateSalary(staffId, { monthly_salary, notes }),
    onSuccess: () => {
      message.success("Salary saved");
      setEditingId(null);
      queryClient.invalidateQueries({ queryKey: ["staff-salaries"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to save salary"),
  });

  return (
    <Table
      rowKey="staff_id"
      loading={isLoading}
      dataSource={salaries}
      pagination={{ pageSize: 15 }}
      columns={[
        { title: "Staff", dataIndex: "staff_name" },
        {
          title: "Monthly salary (₹)",
          key: "salary",
          render: (_: unknown, r: StaffSalary) =>
            editingId === r.staff_id ? (
              <Form form={form} layout="inline" initialValues={r}>
                <Form.Item name="monthly_salary" rules={[{ required: true }]} style={{ marginBottom: 0 }}>
                  <InputNumber min={0} style={{ width: 140 }} />
                </Form.Item>
              </Form>
            ) : (
              r.monthly_salary?.toLocaleString("en-IN", { style: "currency", currency: "INR" }) ?? (
                <Typography.Text type="secondary">Not set</Typography.Text>
              )
            ),
        },
        {
          title: "",
          key: "actions",
          render: (_: unknown, r: StaffSalary) =>
            editingId === r.staff_id ? (
              <Space>
                <Button
                  size="small"
                  type="primary"
                  loading={saveMutation.isPending}
                  onClick={() =>
                    form.validateFields().then((values) =>
                      saveMutation.mutate({ staffId: r.staff_id, monthly_salary: values.monthly_salary, notes: r.notes ?? undefined })
                    )
                  }
                >
                  Save
                </Button>
                <Button size="small" onClick={() => setEditingId(null)}>
                  Cancel
                </Button>
              </Space>
            ) : (
              <Button
                size="small"
                onClick={() => {
                  setEditingId(r.staff_id);
                  form.setFieldsValue(r);
                }}
              >
                Edit
              </Button>
            ),
        },
      ]}
    />
  );
}

function PayslipsTab() {
  const queryClient = useQueryClient();
  const [month, setMonth] = useState(dayjs().format("YYYY-MM"));

  const { data: payslips, isLoading } = useQuery({
    queryKey: ["payslips", month],
    queryFn: () => listPayslips({ month }).then((r) => r.data),
  });

  const generateMutation = useMutation({
    mutationFn: () => generatePayslips({ month }),
    onSuccess: (res) => {
      message.success(`Generated ${res.data.length} payslip${res.data.length === 1 ? "" : "s"} for ${month}`);
      queryClient.invalidateQueries({ queryKey: ["payslips"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to generate payslips"),
  });

  const markPaidMutation = useMutation({
    mutationFn: (id: number) => updatePayslip(id, { status: "paid" }),
    onSuccess: () => {
      message.success("Marked as paid");
      queryClient.invalidateQueries({ queryKey: ["payslips"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to update payslip"),
  });

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <DatePicker
          picker="month"
          value={dayjs(month, "YYYY-MM")}
          onChange={(d) => d && setMonth(d.format("YYYY-MM"))}
        />
        <Button
          type="primary"
          icon={<DollarOutlined />}
          loading={generateMutation.isPending}
          onClick={() => generateMutation.mutate()}
        >
          Generate payslips for {month}
        </Button>
      </Space>
      <Table
        rowKey="id"
        loading={isLoading}
        dataSource={payslips}
        pagination={{ pageSize: 15 }}
        columns={[
          { title: "Staff", dataIndex: "staff_name" },
          { title: "Basic", dataIndex: "basic_amount", render: (v: number) => `₹${v.toFixed(2)}` },
          { title: "Allowances", dataIndex: "allowances", render: (v: number) => `₹${v.toFixed(2)}` },
          { title: "Deductions", dataIndex: "deductions", render: (v: number) => `₹${v.toFixed(2)}` },
          { title: "Net", dataIndex: "net_amount", render: (v: number) => <b>₹{v.toFixed(2)}</b> },
          {
            title: "Status",
            dataIndex: "status",
            render: (v: string) => <Tag color={PAYSLIP_STATUS_COLORS[v]}>{v}</Tag>,
          },
          {
            title: "",
            key: "actions",
            render: (_: unknown, r: Payslip) =>
              r.status === "draft" ? (
                <Button size="small" icon={<CheckOutlined />} loading={markPaidMutation.isPending} onClick={() => markPaidMutation.mutate(r.id)}>
                  Mark paid
                </Button>
              ) : (
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  Paid {r.paid_at ? new Date(r.paid_at).toLocaleDateString() : ""}
                </Typography.Text>
              ),
          },
        ]}
      />
    </div>
  );
}

export default function Payroll() {
  return (
    <div>
      <Typography.Title level={3}>Payroll</Typography.Title>
      <Card>
        <Typography.Paragraph type="secondary">
          Set each staff member's monthly salary, then generate payslips for a given month. Generating is safe to
          re-run - it skips any staff who already have a payslip for that month, so adjustments to individual
          payslips (allowances/deductions) below aren't overwritten.
        </Typography.Paragraph>
      </Card>
      <div style={{ marginTop: 16 }}>
        <Typography.Title level={5}>Salary Setup</Typography.Title>
        <SalarySetupTab />
      </div>
      <div style={{ marginTop: 24 }}>
        <Typography.Title level={5}>Payslips</Typography.Title>
        <PayslipsTab />
      </div>
    </div>
  );
}
