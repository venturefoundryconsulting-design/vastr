import {
  MailOutlined,
  MessageOutlined,
  PrinterOutlined,
  ShoppingOutlined,
  WhatsAppOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Button, Card, Col, DatePicker, Input, Row, Select, Space, Statistic, Table, Tag, Typography, message } from "antd";
import dayjs, { type Dayjs } from "dayjs";
import { useMemo, useState } from "react";
import { apiClient } from "../api/client";
import {
  listOutlets,
  listSales,
  sendReceiptEmail,
  sendReceiptSms,
  sendReceiptWhatsApp,
} from "../api/endpoints";
import type { PaymentMode, Sale } from "../api/types";
import ExportButton from "../components/ExportButton";

const { RangePicker } = DatePicker;

const PAYMENT_COLORS: Record<PaymentMode, string> = { cash: "green", card: "blue", upi: "purple", other: "default" };

function SaleActions({ sale }: { sale: Sale }) {
  const printMutation = useMutation({
    mutationFn: async () => {
      const res = await apiClient.get(`/api/sales/${sale.id}/receipt/pdf`, { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      window.open(url, "_blank");
    },
  });
  const whatsappMutation = useMutation({
    mutationFn: () => sendReceiptWhatsApp(sale.id),
    onSuccess: (res) => {
      message.success(res.data.detail);
      if (res.data.whatsapp_link) window.open(res.data.whatsapp_link, "_blank");
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to send WhatsApp receipt"),
  });
  const smsMutation = useMutation({
    mutationFn: () => sendReceiptSms(sale.id),
    onSuccess: (res) => message.success(res.data.detail),
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to send SMS receipt"),
  });
  const emailMutation = useMutation({
    mutationFn: () => sendReceiptEmail(sale.id),
    onSuccess: (res) => message.success(res.data.detail),
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to send email receipt"),
  });

  return (
    <Space>
      <Button size="small" icon={<PrinterOutlined />} loading={printMutation.isPending} onClick={() => printMutation.mutate()} />
      <Button
        size="small"
        icon={<WhatsAppOutlined />}
        style={{ background: "#25D366", color: "white", border: "none" }}
        loading={whatsappMutation.isPending}
        disabled={!sale.customer_phone}
        onClick={() => whatsappMutation.mutate()}
      />
      <Button
        size="small"
        icon={<MessageOutlined />}
        loading={smsMutation.isPending}
        disabled={!sale.customer_phone}
        onClick={() => smsMutation.mutate()}
      />
      <Button
        size="small"
        icon={<MailOutlined />}
        loading={emailMutation.isPending}
        disabled={!sale.customer_email}
        onClick={() => emailMutation.mutate()}
      />
    </Space>
  );
}

export default function Sales() {
  const [outletId, setOutletId] = useState<number | undefined>();
  const [search, setSearch] = useState("");
  const [paymentMode, setPaymentMode] = useState<PaymentMode | undefined>();
  const [dateRange, setDateRange] = useState<[Dayjs, Dayjs] | null>([dayjs().subtract(29, "day"), dayjs()]);

  const { data: outlets } = useQuery({ queryKey: ["outlets"], queryFn: () => listOutlets().then((r) => r.data) });
  const { data: sales, isLoading } = useQuery({
    queryKey: ["sales", outletId, search, paymentMode, dateRange?.[0]?.format(), dateRange?.[1]?.format()],
    queryFn: () =>
      listSales({
        outlet_id: outletId,
        search: search || undefined,
        payment_mode: paymentMode,
        start_date: dateRange?.[0]?.format("YYYY-MM-DD"),
        end_date: dateRange?.[1]?.format("YYYY-MM-DD"),
      }).then((r) => r.data),
  });

  const totals = useMemo(() => {
    const list = sales ?? [];
    return {
      count: list.length,
      revenue: list.reduce((sum, s) => sum + s.total, 0),
      items: list.reduce((sum, s) => sum + s.items.reduce((n, i) => n + i.quantity, 0), 0),
    };
  }, [sales]);

  return (
    <div>
      <Typography.Title level={3}>
        <ShoppingOutlined /> Sales
      </Typography.Title>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={8} md={6}>
          <Card size="small">
            <Statistic title="Sales" value={totals.count} />
          </Card>
        </Col>
        <Col xs={12} sm={8} md={6}>
          <Card size="small">
            <Statistic title="Revenue" value={totals.revenue} precision={2} prefix="₹" />
          </Card>
        </Col>
        <Col xs={12} sm={8} md={6}>
          <Card size="small">
            <Statistic title="Items sold" value={totals.items} />
          </Card>
        </Col>
      </Row>

      <Space wrap style={{ marginBottom: 16 }}>
        <RangePicker
          value={dateRange}
          onChange={(v) => setDateRange(v as [Dayjs, Dayjs] | null)}
          allowClear
        />
        <Select
          allowClear
          placeholder="All outlets"
          style={{ width: 180 }}
          options={outlets?.map((o) => ({ value: o.id, label: o.name }))}
          onChange={setOutletId}
        />
        <Select
          allowClear
          placeholder="All payment modes"
          style={{ width: 170 }}
          options={[
            { value: "cash", label: "Cash" },
            { value: "card", label: "Card" },
            { value: "upi", label: "UPI" },
            { value: "other", label: "Other" },
          ]}
          onChange={setPaymentMode}
        />
        <Input.Search
          placeholder="Search invoice, customer, phone..."
          allowClear
          style={{ width: 260 }}
          onSearch={setSearch}
        />
        <ExportButton
          url="/api/sales/export"
          params={{
            outlet_id: outletId,
            search: search || undefined,
            payment_mode: paymentMode,
            start_date: dateRange?.[0]?.format("YYYY-MM-DD"),
            end_date: dateRange?.[1]?.format("YYYY-MM-DD"),
          }}
          filenameBase="sales"
        />
      </Space>

      <Table
        rowKey="id"
        loading={isLoading}
        dataSource={sales}
        pagination={{ pageSize: 20 }}
        scroll={{ x: 900 }}
        columns={[
          { title: "Invoice #", dataIndex: "invoice_number" },
          { title: "Date", dataIndex: "created_at", render: (v: string) => dayjs(v).format("DD MMM YYYY, h:mm A") },
          { title: "Outlet", dataIndex: "outlet_name" },
          { title: "Customer", dataIndex: "customer_name", render: (v: string | null) => v || "Walk-in" },
          {
            title: "Items",
            key: "items",
            render: (_: unknown, s: Sale) => s.items.reduce((n, i) => n + i.quantity, 0),
          },
          {
            title: "Payment",
            dataIndex: "payment_mode",
            render: (v: PaymentMode) => <Tag color={PAYMENT_COLORS[v]}>{v.toUpperCase()}</Tag>,
          },
          { title: "Total", dataIndex: "total", render: (v: number) => `₹${v.toFixed(2)}` },
          { title: "", key: "actions", render: (_: unknown, s: Sale) => <SaleActions sale={s} /> },
        ]}
        expandable={{
          expandedRowRender: (sale) => (
            <Table
              size="small"
              rowKey="id"
              pagination={false}
              dataSource={sale.items}
              columns={[
                { title: "SKU", dataIndex: "sku" },
                { title: "Product", dataIndex: "product_name" },
                { title: "Qty", dataIndex: "quantity" },
                { title: "Price", dataIndex: "unit_price", render: (v: number) => `₹${v.toFixed(2)}` },
                { title: "Tax %", dataIndex: "tax_rate" },
              ]}
            />
          ),
        }}
      />
    </div>
  );
}
