import {
  ArrowUpOutlined,
  CrownOutlined,
  RiseOutlined,
  ShopOutlined,
  StopOutlined,
  TeamOutlined,
} from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Card, Col, Row, Statistic, Table, Tag, Typography } from "antd";
import { useNavigate } from "react-router-dom";
import { getPlatformOverview } from "../api/endpoints";
import type { RecentSignup } from "../api/types";

const PLAN_COLORS: Record<string, string> = {
  free: "default",
  starter: "blue",
  professional: "purple",
  enterprise: "gold",
};

const PLATFORM_ACCENT = "#4c1d95";

function StatCard({
  title,
  value,
  icon,
  suffix,
  precision,
}: {
  title: string;
  value: number;
  icon: React.ReactNode;
  suffix?: string;
  precision?: number;
}) {
  return (
    <Card style={{ borderRadius: 14, border: "1px solid #e5e3ee" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
        <div
          style={{
            width: 40, height: 40, minWidth: 40, borderRadius: 11,
            background: `${PLATFORM_ACCENT}14`, color: PLATFORM_ACCENT,
            display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18,
          }}
        >
          {icon}
        </div>
        <Statistic title={title} value={value} suffix={suffix} precision={precision} />
      </div>
    </Card>
  );
}

export default function Overview() {
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({
    queryKey: ["admin-overview"],
    queryFn: () => getPlatformOverview().then((r) => r.data),
  });

  const columns = [
    {
      title: "Store",
      dataIndex: "company_name",
      render: (v: string, r: RecentSignup) => (
        <a onClick={() => navigate(`/platform-admin/tenants/${r.id}`)}>{v}</a>
      ),
    },
    { title: "Slug", dataIndex: "slug" },
    {
      title: "Plan",
      dataIndex: "subscription_plan",
      render: (v: string) => <Tag color={PLAN_COLORS[v]}>{v.toUpperCase()}</Tag>,
    },
    { title: "Signed up", dataIndex: "created_at", render: (v: string) => new Date(v).toLocaleString() },
  ];

  return (
    <div>
      <Typography.Title level={3} style={{ margin: 0, marginBottom: 20 }}>
        Platform Overview
      </Typography.Title>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} sm={12} lg={6}>
          <StatCard title="Total stores" value={data?.total_tenants ?? 0} icon={<ShopOutlined />} />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <StatCard title="On a free trial" value={data?.trialing_tenants ?? 0} icon={<RiseOutlined />} />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <StatCard title="Paying stores" value={data?.paying_tenants ?? 0} icon={<CrownOutlined />} />
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <StatCard title="Suspended" value={data?.suspended_tenants ?? 0} icon={<StopOutlined />} />
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} sm={12} lg={8}>
          <Card style={{ borderRadius: 14, border: "1px solid #e5e3ee" }}>
            <Statistic
              title="Estimated ARR"
              value={data?.estimated_arr ?? 0}
              prefix="₹"
              precision={0}
              valueStyle={{ color: "#16a34a" }}
            />
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              Active subscriptions only · Enterprise excluded (custom pricing)
            </Typography.Text>
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={8}>
          <Card style={{ borderRadius: 14, border: "1px solid #e5e3ee" }}>
            <Statistic
              title="New signups (7 days)"
              value={data?.new_signups_7d ?? 0}
              prefix={<ArrowUpOutlined style={{ fontSize: 14 }} />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={8}>
          <Card style={{ borderRadius: 14, border: "1px solid #e5e3ee" }}>
            <Statistic
              title="New signups (30 days)"
              value={data?.new_signups_30d ?? 0}
              icon={<TeamOutlined />}
            />
          </Card>
        </Col>
      </Row>

      {data?.plan_breakdown && data.plan_breakdown.length > 0 && (
        <Card style={{ borderRadius: 14, border: "1px solid #e5e3ee", marginBottom: 16 }}>
          <Typography.Text strong style={{ display: "block", marginBottom: 12 }}>
            Plan breakdown
          </Typography.Text>
          <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
            {data.plan_breakdown.map((p) => (
              <div key={p.plan} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Tag color={PLAN_COLORS[p.plan]}>{p.plan.toUpperCase()}</Tag>
                <Typography.Text strong>{p.count}</Typography.Text>
              </div>
            ))}
          </div>
        </Card>
      )}

      <Card style={{ borderRadius: 14, border: "1px solid #e5e3ee" }}>
        <Typography.Text strong style={{ display: "block", marginBottom: 12 }}>
          Recent signups
        </Typography.Text>
        <Table
          rowKey="id"
          size="small"
          loading={isLoading}
          columns={columns}
          dataSource={data?.recent_signups}
          pagination={false}
          scroll={{ x: "max-content" }}
        />
      </Card>
    </div>
  );
}
