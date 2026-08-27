import { useQuery } from "@tanstack/react-query";
import { Card, Col, Row, Statistic, Table, Tag, Typography } from "antd";
import { getOrderCost } from "../api/manufacturing-endpoints";
import type { CostLabourLine, CostMaterialLine } from "../api/manufacturing-types";
import { formatQty } from "../utils/quantity";

/** Estimated (BOM x standard cost) versus actual (real consumption + real
 * labour + real wastage). The variance is the number that tells a boutique
 * whether its BOM is honest - never back-filled from the other side. */
export default function ProductionCostPanel({ orderId }: { orderId: number }) {
  const { data: cost, isLoading } = useQuery({
    queryKey: ["production-cost", orderId],
    queryFn: () => getOrderCost(orderId).then((r) => r.data),
  });

  if (isLoading) return <Card loading />;
  if (!cost) return null;

  const variance = Number(cost.variance);

  return (
    <Card size="small" title="Cost">
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}>
          <Statistic title="Estimated" value={Number(cost.estimated_total_cost)} precision={2} prefix="₹" />
        </Col>
        <Col span={6}>
          <Statistic title="Actual" value={Number(cost.actual_total_cost)} precision={2} prefix="₹" />
        </Col>
        <Col span={6}>
          <Statistic
            title="Variance"
            value={Math.abs(variance)}
            precision={2}
            prefix={variance > 0 ? "+₹" : variance < 0 ? "-₹" : "₹"}
            valueStyle={{ color: variance > 0 ? "#dc2626" : variance < 0 ? "#16a34a" : undefined }}
          />
        </Col>
        <Col span={6}>
          <Statistic
            title="Actual / unit"
            value={cost.actual_unit_cost != null ? Number(cost.actual_unit_cost) : undefined}
            precision={2}
            prefix="₹"
            formatter={cost.actual_unit_cost == null ? () => "—" : undefined}
          />
        </Col>
      </Row>

      <Typography.Text strong>Material</Typography.Text>
      <Table<CostMaterialLine>
        rowKey="material_id"
        size="small"
        pagination={false}
        dataSource={cost.material_lines}
        style={{ marginBottom: 16, marginTop: 8 }}
        columns={[
          {
            title: "Material",
            key: "m",
            render: (_: unknown, r: CostMaterialLine) => (
              <span>
                {r.name} <code style={{ fontSize: 11 }}>{r.sku}</code>
              </span>
            ),
          },
          { title: "Unit cost", dataIndex: "unit_cost", width: 100, align: "right", render: (v: number) => `₹${Number(v).toFixed(2)}` },
          { title: "Planned", dataIndex: "planned_quantity", width: 90, align: "right", render: formatQty },
          { title: "Consumed", dataIndex: "consumed_quantity", width: 90, align: "right", render: formatQty },
          { title: "Wasted", dataIndex: "wasted_quantity", width: 90, align: "right", render: formatQty },
          { title: "Estimated", dataIndex: "estimated_cost", width: 100, align: "right", render: (v: number) => `₹${Number(v).toFixed(2)}` },
          { title: "Actual", dataIndex: "actual_cost", width: 100, align: "right", render: (v: number) => `₹${Number(v).toFixed(2)}` },
          {
            title: "Variance",
            dataIndex: "variance",
            width: 100,
            align: "right",
            render: (v: number) => (
              <Typography.Text type={Number(v) > 0 ? "danger" : Number(v) < 0 ? "success" : undefined}>
                {Number(v) > 0 ? "+" : ""}
                {Number(v).toFixed(2)}
              </Typography.Text>
            ),
          },
        ]}
      />

      <Typography.Text strong>Labour</Typography.Text>
      <Table<CostLabourLine>
        rowKey="work_order_id"
        size="small"
        pagination={false}
        dataSource={cost.labour_lines}
        style={{ marginTop: 8 }}
        locale={{ emptyText: "No work orders yet" }}
        columns={[
          { title: "Work order", dataIndex: "wo_number", width: 120, render: (v: string) => <code>{v}</code> },
          { title: "Stage", dataIndex: "stage_name", width: 110 },
          { title: "Tailor", dataIndex: "tailor_name", width: 130, render: (v: string | null) => v ?? "—" },
          { title: "Status", dataIndex: "status", width: 110, render: (v: string) => <Tag>{v}</Tag> },
          { title: "Estimated", dataIndex: "estimated_cost", width: 100, align: "right", render: (v: number) => `₹${Number(v).toFixed(2)}` },
          { title: "Actual", dataIndex: "actual_cost", width: 100, align: "right", render: (v: number) => `₹${Number(v).toFixed(2)}` },
        ]}
      />
    </Card>
  );
}
