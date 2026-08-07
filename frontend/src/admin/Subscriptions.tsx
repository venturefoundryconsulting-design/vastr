import { useQuery } from "@tanstack/react-query";
import { Card, Col, Row, Statistic, Table, Tag, Typography } from "antd";
import { useNavigate } from "react-router-dom";
import { listPayments, listTenants } from "../api/endpoints";
import type { Payment, Tenant } from "../api/types";

const PLAN_COLORS: Record<string, string> = {
  free: "default",
  starter: "blue",
  professional: "purple",
  enterprise: "gold",
};

const STATUS_COLORS: Record<string, string> = {
  trial: "blue",
  active: "green",
  suspended: "orange",
  cancelled: "red",
};

const PAYMENT_STATUS_COLORS: Record<string, string> = {
  created: "default",
  paid: "green",
  failed: "red",
};

export default function Subscriptions() {
  const navigate = useNavigate();
  const { data: tenants, isLoading: tenantsLoading } = useQuery({
    queryKey: ["admin-tenants-subs"],
    queryFn: () => listTenants().then((r) => r.data),
  });
  const { data: payments, isLoading: paymentsLoading } = useQuery({
    queryKey: ["admin-payments"],
    queryFn: () => listPayments(200).then((r) => r.data),
  });

  const tenantColumns = [
    {
      title: "Store",
      dataIndex: "company_name",
      render: (v: string, r: Tenant) => (
        <a onClick={() => navigate(`/platform-admin/tenants/${r.id}`)}>{v}</a>
      ),
    },
    { title: "Slug", dataIndex: "slug" },
    {
      title: "Plan",
      dataIndex: "subscription_plan",
      render: (v: string) => <Tag color={PLAN_COLORS[v]}>{v.toUpperCase()}</Tag>,
    },
    {
      title: "Status",
      dataIndex: "subscription_status",
      render: (v: string) => <Tag color={STATUS_COLORS[v]}>{v.toUpperCase()}</Tag>,
    },
    {
      title: "Trial ends",
      dataIndex: "trial_end",
      render: (v: string | null) => (v ? new Date(v).toLocaleDateString() : "-"),
    },
  ];

  const paymentColumns = [
    { title: "When", dataIndex: "created_at", render: (v: string) => new Date(v).toLocaleString() },
    {
      title: "Store",
      dataIndex: "tenant_name",
      render: (v: string | null, r: Payment) =>
        v && r.tenant_id ? <a onClick={() => navigate(`/platform-admin/tenants/${r.tenant_id}`)}>{v}</a> : "-",
    },
    { title: "Plan", dataIndex: "plan", render: (v: string) => <Tag color={PLAN_COLORS[v]}>{v.toUpperCase()}</Tag> },
    { title: "Amount", render: (_: unknown, r: Payment) => `₹${r.amount.toLocaleString()} ${r.currency}` },
    {
      title: "Status",
      dataIndex: "status",
      render: (v: string) => <Tag color={PAYMENT_STATUS_COLORS[v]}>{v.toUpperCase()}</Tag>,
    },
    { title: "Razorpay order", dataIndex: "razorpay_order_id" },
  ];

  const activeCount = tenants?.filter((t) => t.subscription_status === "active").length ?? 0;
  const trialCount = tenants?.filter((t) => t.subscription_status === "trial").length ?? 0;
  const paidTotal = payments?.filter((p) => p.status === "paid").reduce((sum, p) => sum + p.amount, 0) ?? 0;

  return (
    <div>
      <Typography.Title level={3} style={{ margin: 0, marginBottom: 20 }}>
        Subscriptions
      </Typography.Title>

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={8}>
          <Card><Statistic title="Active subscriptions" value={activeCount} /></Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card><Statistic title="On free trial" value={trialCount} /></Card>
        </Col>
        <Col xs={24} sm={8}>
          <Card><Statistic title="Collected via Razorpay" value={paidTotal} prefix="₹" precision={0} valueStyle={{ color: "#16a34a" }} /></Card>
        </Col>
      </Row>

      <Card title="Stores &amp; plans" style={{ marginBottom: 24 }}>
        <Table rowKey="id" loading={tenantsLoading} columns={tenantColumns} dataSource={tenants} scroll={{ x: "max-content" }} />
      </Card>

      <Card title="Payment history">
        <Table rowKey="id" loading={paymentsLoading} columns={paymentColumns} dataSource={payments} scroll={{ x: "max-content" }} />
      </Card>
    </div>
  );
}
