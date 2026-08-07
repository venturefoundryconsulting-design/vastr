import { TagOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Card, Col, Row, Select, Statistic, Table, Tabs, Tag, Typography } from "antd";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getDeadStock, getStockAging, listOutlets } from "../api/endpoints";
import type { StockAgingItem } from "../api/types";
import ExportButton from "../components/ExportButton";

const BUCKETS = [
  { label: "0-30 days", min: 0, max: 30, color: "green", hex: "#389e0d" },
  { label: "31-60 days", min: 31, max: 60, color: "blue", hex: "#1677ff" },
  { label: "61-90 days", min: 61, max: 90, color: "gold", hex: "#d4b106" },
  { label: "91-180 days", min: 91, max: 180, color: "orange", hex: "#d46b08" },
  { label: "180+ days", min: 181, max: Infinity, color: "red", hex: "#cf1322" },
];

function bucketFor(days: number) {
  return BUCKETS.find((b) => days >= b.min && days <= b.max) ?? BUCKETS[BUCKETS.length - 1];
}

function variantColumns() {
  return [
    { title: "SKU", dataIndex: "sku" },
    { title: "Product", dataIndex: "product_name" },
    {
      title: "Variant",
      key: "variant",
      render: (_: unknown, r: StockAgingItem) => [r.color, r.size].filter(Boolean).join(" / "),
    },
    { title: "Outlet", dataIndex: "outlet_name" },
    { title: "Qty", dataIndex: "quantity" },
    { title: "Stock value", dataIndex: "stock_value", render: (v: number) => `₹${v.toFixed(2)}` },
    {
      title: "Last sold",
      dataIndex: "last_sold_at",
      render: (v: string | null) => (v ? new Date(v).toLocaleDateString() : "Never"),
    },
    { title: "Days idle", dataIndex: "days_since_last_sale" },
  ];
}

function StockAgingTab({ outletId }: { outletId?: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ["stock-aging", outletId],
    queryFn: () => getStockAging(outletId ? { outlet_id: outletId } : undefined).then((r) => r.data),
  });

  const bucketCounts = useMemo(() => {
    const counts = Object.fromEntries(BUCKETS.map((b) => [b.label, { count: 0, value: 0 }]));
    (data ?? []).forEach((item) => {
      const b = bucketFor(item.days_since_last_sale);
      counts[b.label].count += 1;
      counts[b.label].value += item.stock_value;
    });
    return counts;
  }, [data]);

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 12 }}>
        <ExportButton
          url="/api/reports/stock-aging/export"
          params={{ outlet_id: outletId }}
          filenameBase="stock_aging"
        />
      </div>
      <Row gutter={12} style={{ marginBottom: 20 }}>
        {BUCKETS.map((b) => (
          <Col key={b.label} xs={12} sm={8} md={4} style={{ marginBottom: 12 }}>
            <Card size="small">
              <Statistic
                title={b.label}
                value={bucketCounts[b.label].count}
                suffix="items"
                valueStyle={{ color: b.hex }}
              />
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                ₹{bucketCounts[b.label].value.toFixed(0)} tied up
              </Typography.Text>
            </Card>
          </Col>
        ))}
      </Row>
      <Table
        rowKey={(r) => `${r.variant_id}-${r.outlet_id}`}
        loading={isLoading}
        dataSource={data}
        pagination={{ pageSize: 20 }}
        scroll={{ x: "max-content" }}
        columns={[
          ...variantColumns(),
          {
            title: "Bucket",
            key: "bucket",
            render: (_: unknown, r: StockAgingItem) => {
              const b = bucketFor(r.days_since_last_sale);
              return <Tag color={b.color}>{b.label}</Tag>;
            },
          },
        ]}
      />
    </div>
  );
}

function DeadStockTab({ outletId }: { outletId?: number }) {
  const navigate = useNavigate();
  const [days, setDays] = useState(90);

  const { data, isLoading } = useQuery({
    queryKey: ["dead-stock", outletId, days],
    queryFn: () => getDeadStock({ outlet_id: outletId, days }).then((r) => r.data),
  });

  const totalValue = (data ?? []).reduce((sum, i) => sum + i.stock_value, 0);

  return (
    <div>
      <Card size="small" style={{ marginBottom: 16 }}>
        <Row justify="space-between" align="middle">
          <Typography.Text>
            No sale in at least{" "}
            <Select
              size="small"
              value={days}
              onChange={setDays}
              style={{ width: 100 }}
              options={[30, 60, 90, 180].map((d) => ({ value: d, label: `${d} days` }))}
            />
          </Typography.Text>
          <Statistic title="Dead stock value" value={totalValue} precision={2} prefix="₹" />
        </Row>
      </Card>
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 12 }}>
        <ExportButton
          url="/api/reports/dead-stock/export"
          params={{ outlet_id: outletId, days }}
          filenameBase="dead_stock"
        />
      </div>
      <Table
        rowKey={(r) => `${r.variant_id}-${r.outlet_id}`}
        loading={isLoading}
        dataSource={data}
        pagination={{ pageSize: 20 }}
        locale={{ emptyText: `No dead stock — everything has sold within the last ${days} days` }}
        scroll={{ x: "max-content" }}
        columns={[
          ...variantColumns(),
          {
            title: "",
            key: "actions",
            render: (_: unknown, r: StockAgingItem) => (
              <a
                onClick={() =>
                  navigate(
                    `/discounts?product_id=${r.product_id}&product_name=${encodeURIComponent(r.product_name)}`
                  )
                }
              >
                <TagOutlined /> Create clearance discount
              </a>
            ),
          },
        ]}
      />
    </div>
  );
}

export default function Reports() {
  const [outletId, setOutletId] = useState<number | undefined>();
  const { data: outlets } = useQuery({ queryKey: ["outlets"], queryFn: () => listOutlets().then((r) => r.data) });

  return (
    <div>
      <Row justify="space-between" align="middle" style={{ marginBottom: 16 }}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          Reports
        </Typography.Title>
        <Select
          allowClear
          placeholder="All outlets"
          style={{ width: 220 }}
          options={outlets?.map((o) => ({ value: o.id, label: o.name }))}
          onChange={setOutletId}
        />
      </Row>
      <Tabs
        items={[
          { key: "aging", label: "Stock Aging", children: <StockAgingTab outletId={outletId} /> },
          { key: "dead", label: "Dead Stock", children: <DeadStockTab outletId={outletId} /> },
        ]}
      />
    </div>
  );
}
