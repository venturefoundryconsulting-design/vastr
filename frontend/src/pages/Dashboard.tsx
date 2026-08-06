import {
  AppstoreOutlined,
  ArrowDownOutlined,
  ArrowUpOutlined,
  DeleteOutlined,
  SettingOutlined,
  ShopOutlined,
  SwapOutlined,
  TruckOutlined,
  WalletOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import {
  Button,
  Calendar,
  Card,
  Checkbox,
  Col,
  Empty,
  Input,
  List,
  Modal,
  Radio,
  Row,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import dayjs, { type Dayjs } from "dayjs";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { getDashboardSummary, getPaymentModeBreakdown, getSalesTrend } from "../api/endpoints";
import type { DashboardSummary } from "../api/types";
import { BRAND } from "../theme";

const STORAGE_KEY = "tanisi_dashboard_widgets";
const NOTES_KEY = "tanisi_dashboard_notes";
const PAYMENT_COLORS: Record<string, string> = { cash: "#16a34a", card: "#2563eb", upi: "#7c3aed", other: "#94a3b8" };

type WidgetWidth = 100 | 50 | 25;
interface LayoutItem {
  id: string;
  visible: boolean;
  width: WidgetWidth;
}
interface WidgetDef {
  id: string;
  title: string;
  defaultWidth: WidgetWidth;
}

interface MetricDef {
  id: string;
  title: string;
  icon: ReactNode;
  color: string;
  dataKey: keyof DashboardSummary;
  path: string;
  prefix?: string;
  precision?: number;
}

const METRIC_DEFS: MetricDef[] = [
  { id: "metric-outlets", title: "Outlets", icon: <ShopOutlined />, color: "#9d174d", dataKey: "total_outlets", path: "/outlets" },
  { id: "metric-products", title: "Products", icon: <AppstoreOutlined />, color: "#7c3aed", dataKey: "total_products", path: "/products" },
  { id: "metric-low-stock", title: "Low stock alerts", icon: <WarningOutlined />, color: "#cf1322", dataKey: "low_stock_count", path: "/inventory" },
  { id: "metric-open-pos", title: "Open POs", icon: <TruckOutlined />, color: "#2563eb", dataKey: "open_purchase_orders", path: "/purchase-orders" },
  { id: "metric-transfers", title: "Transfers in-transit", icon: <SwapOutlined />, color: "#0891b2", dataKey: "in_transit_transfers", path: "/transfers" },
  { id: "metric-sales-today", title: "Sales today", icon: <WalletOutlined />, color: "#15803d", dataKey: "sales_today_total", path: "/pos", prefix: "₹", precision: 2 },
];
const METRIC_IDS = METRIC_DEFS.map((m) => m.id);

const WIDGETS: WidgetDef[] = [
  ...METRIC_DEFS.map((m) => ({ id: m.id, title: m.title, defaultWidth: 25 as WidgetWidth })),
  { id: "sales-trend", title: "Sales trend (30 days)", defaultWidth: 100 },
  { id: "payment-mix", title: "Payment mode mix", defaultWidth: 100 },
  { id: "calendar-notes", title: "Calendar & Quick Notes", defaultWidth: 50 },
  { id: "low-stock", title: "Low stock items", defaultWidth: 100 },
  { id: "recent-pos", title: "Recent purchase orders", defaultWidth: 100 },
  { id: "recent-transfers", title: "Recent stock transfers", defaultWidth: 100 },
];
const DEFAULT_LAYOUT: LayoutItem[] = WIDGETS.map((w) => ({ id: w.id, visible: true, width: w.defaultWidth }));
const SPAN_FOR_WIDTH: Record<WidgetWidth, number> = { 100: 24, 50: 12, 25: 6 };

function loadLayout(): LayoutItem[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_LAYOUT;
    let saved: Partial<LayoutItem>[] = JSON.parse(raw);

    // Migrate the old single combined "metrics" widget (pre-split) into the individual metric cards.
    const oldMetricsIndex = saved.findIndex((s) => s.id === "metrics");
    if (oldMetricsIndex !== -1) {
      const old = saved[oldMetricsIndex];
      const replacements = METRIC_IDS.map((id) => ({ id, visible: old.visible ?? true, width: 25 as WidgetWidth }));
      saved = [...saved.slice(0, oldMetricsIndex), ...replacements, ...saved.slice(oldMetricsIndex + 1)];
    }

    const defsById = Object.fromEntries(WIDGETS.map((w) => [w.id, w]));
    const knownIds = new Set(WIDGETS.map((w) => w.id));
    const cleaned: LayoutItem[] = saved
      .filter((s) => s.id && knownIds.has(s.id))
      .map((s) => ({
        id: s.id!,
        visible: s.visible ?? true,
        width: s.width ?? defsById[s.id!].defaultWidth,
      }));
    for (const w of WIDGETS) {
      if (!cleaned.some((s) => s.id === w.id)) cleaned.push({ id: w.id, visible: true, width: w.defaultWidth });
    }
    return cleaned;
  } catch {
    return DEFAULT_LAYOUT;
  }
}

function loadNotes(): Record<string, string> {
  try {
    const raw = localStorage.getItem(NOTES_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function CustomizeModal({
  layout,
  onChange,
  onClose,
}: {
  layout: LayoutItem[];
  onChange: (l: LayoutItem[]) => void;
  onClose: () => void;
}) {
  const move = (index: number, dir: -1 | 1) => {
    const next = [...layout];
    const target = index + dir;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    onChange(next);
  };

  const titleFor = (id: string) => WIDGETS.find((w) => w.id === id)?.title ?? id;

  return (
    <Modal title="Customize dashboard" open onCancel={onClose} footer={null} width={560}>
      <List
        dataSource={layout}
        renderItem={(item, index) => (
          <List.Item
            actions={[
              <Button key="up" size="small" icon={<ArrowUpOutlined />} disabled={index === 0} onClick={() => move(index, -1)} />,
              <Button
                key="down"
                size="small"
                icon={<ArrowDownOutlined />}
                disabled={index === layout.length - 1}
                onClick={() => move(index, 1)}
              />,
            ]}
          >
            <Space direction="vertical" size={4} style={{ width: "100%" }}>
              <Checkbox
                checked={item.visible}
                onChange={(e) =>
                  onChange(layout.map((l) => (l.id === item.id ? { ...l, visible: e.target.checked } : l)))
                }
              >
                {titleFor(item.id)}
              </Checkbox>
              <Radio.Group
                size="small"
                disabled={!item.visible}
                value={item.width}
                onChange={(e) =>
                  onChange(layout.map((l) => (l.id === item.id ? { ...l, width: e.target.value } : l)))
                }
                style={{ marginLeft: 24 }}
                options={[
                  { label: "100%", value: 100 },
                  { label: "50%", value: 50 },
                  { label: "25%", value: 25 },
                ]}
                optionType="button"
                buttonStyle="solid"
              />
            </Space>
          </List.Item>
        )}
      />
      <Button style={{ marginTop: 12 }} onClick={() => onChange(DEFAULT_LAYOUT)}>
        Reset to default
      </Button>
    </Modal>
  );
}

interface StatCardProps {
  title: string;
  value?: number;
  prefix?: string;
  precision?: number;
  icon: ReactNode;
  color: string;
  loading: boolean;
  onClick?: () => void;
}

function StatCard({ title, value, prefix, precision, icon, color, loading, onClick }: StatCardProps) {
  return (
    <Card
      loading={loading}
      className={onClick ? "tanisi-card-link" : undefined}
      onClick={onClick}
      styles={{ body: { padding: "18px 20px" } }}
    >
      <div style={{ display: "flex", alignItems: "flex-start", gap: 14 }}>
        <div
          style={{
            width: 40,
            height: 40,
            minWidth: 40,
            borderRadius: 10,
            background: `${color}1a`,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color,
            fontSize: 18,
          }}
        >
          {icon}
        </div>
        <Statistic title={title} value={value} prefix={prefix} precision={precision} valueStyle={{ fontSize: 22, fontWeight: 700 }} />
      </div>
    </Card>
  );
}

function CalendarNotesWidget() {
  const [notes, setNotes] = useState<Record<string, string>>(loadNotes);
  const [selected, setSelected] = useState<Dayjs>(dayjs());
  const [draft, setDraft] = useState("");

  useEffect(() => {
    localStorage.setItem(NOTES_KEY, JSON.stringify(notes));
  }, [notes]);

  useEffect(() => {
    setDraft(notes[selected.format("YYYY-MM-DD")] || "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected]);

  const key = selected.format("YYYY-MM-DD");
  const hasNote = !!notes[key];

  const saveNote = () => {
    setNotes((prev) => {
      const next = { ...prev };
      if (draft.trim()) next[key] = draft.trim();
      else delete next[key];
      return next;
    });
    message.success(draft.trim() ? "Note saved" : "Note cleared");
  };

  const clearNote = () => {
    setDraft("");
    setNotes((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };

  return (
    <Card title="Calendar & Quick Notes" styles={{ body: { padding: 12 } }}>
      <Row gutter={16}>
        <Col xs={24} md={13}>
          <Calendar
            fullscreen={false}
            value={selected}
            onSelect={setSelected}
            cellRender={(date, info) => {
              // antd renders the date number / month name itself (.ant-picker-calendar-date-value) -
              // this slot is only for extra content below it, so returning info.originNode here (for
              // any cell type, not just "date") would duplicate that label. Only "date" cells have
              // extra content (a note dot) in this widget; every other type gets nothing.
              if (info.type !== "date") return null;
              if (!notes[date.format("YYYY-MM-DD")]) return null;
              return (
                <div style={{ display: "flex", justifyContent: "center" }}>
                  <span style={{ width: 5, height: 5, borderRadius: "50%", background: BRAND, display: "inline-block" }} />
                </div>
              );
            }}
          />
        </Col>
        <Col xs={24} md={11} style={{ paddingTop: 8 }}>
          <Typography.Text strong>{selected.format("dddd, DD MMM YYYY")}</Typography.Text>
          <Input.TextArea
            rows={5}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Add a quick note for this day..."
            style={{ marginTop: 8 }}
          />
          <Space style={{ marginTop: 8 }}>
            <Button type="primary" onClick={saveNote}>
              Save
            </Button>
            {hasNote && (
              <Button danger icon={<DeleteOutlined />} onClick={clearNote}>
                Clear
              </Button>
            )}
          </Space>
        </Col>
      </Row>
    </Card>
  );
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [layout, setLayout] = useState<LayoutItem[]>(loadLayout);
  const [customizeOpen, setCustomizeOpen] = useState(false);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(layout));
  }, [layout]);

  const { data, isLoading } = useQuery({
    queryKey: ["dashboard-summary"],
    queryFn: () => getDashboardSummary().then((r) => r.data),
  });
  const { data: trend, isLoading: trendLoading } = useQuery({
    queryKey: ["sales-trend", 30],
    queryFn: () => getSalesTrend({ days: 30 }).then((r) => r.data),
  });
  const { data: paymentMix, isLoading: paymentLoading } = useQuery({
    queryKey: ["payment-mode-breakdown", 30],
    queryFn: () => getPaymentModeBreakdown({ days: 30 }).then((r) => r.data),
  });

  const visibleWidgets = layout.filter((l) => l.visible);

  const widgetContent: Record<string, ReactNode> = {
    ...Object.fromEntries(
      METRIC_DEFS.map((m) => [
        m.id,
        <StatCard
          title={m.title}
          value={data?.[m.dataKey] as number | undefined}
          prefix={m.prefix}
          precision={m.precision}
          icon={m.icon}
          color={m.color}
          loading={isLoading}
          onClick={() => navigate(m.path)}
        />,
      ])
    ),
    "sales-trend": (
      <Card title="Sales trend (last 30 days)" loading={trendLoading}>
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={trend}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="date" tickFormatter={(d) => dayjs(d).format("DD MMM")} minTickGap={24} fontSize={12} />
            <YAxis fontSize={12} />
            <Tooltip
              labelFormatter={(d) => dayjs(d as string).format("DD MMM YYYY")}
              formatter={(v) => [`₹${Number(v).toFixed(2)}`, "Revenue"]}
            />
            <Line type="monotone" dataKey="total" stroke={BRAND} strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </Card>
    ),
    "payment-mix": (
      <Card title="Payment mode mix (last 30 days)" loading={paymentLoading}>
        {paymentMix?.length ? (
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie data={paymentMix} dataKey="total" nameKey="payment_mode" innerRadius={50} outerRadius={90} paddingAngle={2}>
                {paymentMix.map((entry) => (
                  <Cell key={entry.payment_mode} fill={PAYMENT_COLORS[entry.payment_mode] || "#94a3b8"} />
                ))}
              </Pie>
              <Tooltip formatter={(v) => `₹${Number(v).toFixed(2)}`} />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        ) : (
          <Empty description="No sales in this period" />
        )}
      </Card>
    ),
    "calendar-notes": <CalendarNotesWidget />,
    "low-stock": (
      <Card title="Low stock items" loading={isLoading}>
        {data?.low_stock_items.length ? (
          <List
            dataSource={data.low_stock_items}
            renderItem={(item) => (
              <List.Item>
                <List.Item.Meta
                  title={`${item.product_name} (${item.sku}) @ ${item.outlet_name}`}
                  description={item.preferred_vendor_name ? `Preferred vendor: ${item.preferred_vendor_name}` : "No preferred vendor linked"}
                />
                <Tag color="red">
                  {item.quantity} / {item.reorder_level}
                </Tag>
              </List.Item>
            )}
          />
        ) : (
          <Empty description="All stocked up" />
        )}
      </Card>
    ),
    "recent-pos": (
      <Card title="Recent purchase orders" loading={isLoading}>
        <Table
          rowKey="id"
          size="small"
          pagination={false}
          scroll={{ x: true }}
          dataSource={data?.recent_purchase_orders}
          onRow={(r) => ({ onClick: () => navigate(`/purchase-orders/${r.id}`) })}
          columns={[
            { title: "PO", dataIndex: "po_number" },
            { title: "Vendor", dataIndex: "vendor_name" },
            { title: "Status", dataIndex: "status", render: (s: string) => <Tag>{s}</Tag> },
            { title: "Total", dataIndex: "total_amount", render: (v: number) => `₹${v.toFixed(2)}` },
          ]}
        />
      </Card>
    ),
    "recent-transfers": (
      <Card title="Recent stock transfers" loading={isLoading}>
        <Table
          rowKey="id"
          size="small"
          pagination={false}
          scroll={{ x: true }}
          dataSource={data?.recent_transfers}
          onRow={(r) => ({ onClick: () => navigate(`/transfers/${r.id}`) })}
          columns={[
            { title: "Transfer #", dataIndex: "transfer_number" },
            { title: "From", dataIndex: "source_outlet_name" },
            { title: "To", dataIndex: "dest_outlet_name" },
            { title: "Status", dataIndex: "status", render: (s: string) => <Tag>{s}</Tag> },
          ]}
        />
      </Card>
    ),
  };

  return (
    <div>
      <Space style={{ width: "100%", justifyContent: "space-between", marginBottom: 8 }}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          Dashboard
        </Typography.Title>
        <Button icon={<SettingOutlined />} onClick={() => setCustomizeOpen(true)}>
          Customize
        </Button>
      </Space>

      {visibleWidgets.length === 0 ? (
        <Empty description="All widgets hidden — use Customize to add some back" />
      ) : (
        <Row gutter={[20, 20]}>
          {visibleWidgets.map((item) => (
            <Col key={item.id} xs={item.id.startsWith("metric-") ? 12 : 24} md={SPAN_FOR_WIDTH[item.width]}>
              {widgetContent[item.id]}
            </Col>
          ))}
        </Row>
      )}

      {customizeOpen && <CustomizeModal layout={layout} onChange={setLayout} onClose={() => setCustomizeOpen(false)} />}
    </div>
  );
}
