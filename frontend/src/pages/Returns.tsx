import { DeleteOutlined, RollbackOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  Col,
  Divider,
  Form,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import dayjs from "dayjs";
import { useMemo, useState } from "react";
import { createReturn, listOutlets, listReturns, listSales, lookupBarcode } from "../api/endpoints";
import type { PaymentMode, RefundMode, Return, Sale } from "../api/types";

interface ReturnLine {
  sale_item_id: number;
  variant_id: number;
  sku: string;
  product_name: string;
  purchased_quantity: number;
  quantity: number;
  unit_price: number;
  tax_rate: number;
  restock: boolean;
}

interface ExchangeLine {
  variant_id: number;
  sku: string;
  product_name: string;
  quantity: number;
  unit_price: number;
  tax_rate: number;
  available_quantity: number;
}

function ReturnDetail({ ret }: { ret: Return }) {
  return (
    <div style={{ padding: "8px 16px" }}>
      {ret.return_items.length > 0 && (
        <>
          <Typography.Text strong>Returned</Typography.Text>
          <Table
            size="small"
            rowKey="id"
            pagination={false}
            dataSource={ret.return_items}
            style={{ marginBottom: 12, marginTop: 6 }}
            columns={[
              { title: "SKU", dataIndex: "sku" },
              { title: "Product", dataIndex: "product_name" },
              { title: "Qty", dataIndex: "quantity" },
              { title: "Restocked", dataIndex: "restock", render: (v: boolean) => (v ? "Yes" : "No") },
            ]}
          />
        </>
      )}
      {ret.exchange_items.length > 0 && (
        <>
          <Typography.Text strong>Exchanged for</Typography.Text>
          <Table
            size="small"
            rowKey="id"
            pagination={false}
            dataSource={ret.exchange_items}
            style={{ marginTop: 6 }}
            columns={[
              { title: "SKU", dataIndex: "sku" },
              { title: "Product", dataIndex: "product_name" },
              { title: "Qty", dataIndex: "quantity" },
            ]}
          />
        </>
      )}
    </div>
  );
}

export default function Returns() {
  const queryClient = useQueryClient();
  const [outletId, setOutletId] = useState<number | undefined>();
  const [searchText, setSearchText] = useState("");
  const [saleOptions, setSaleOptions] = useState<Sale[]>([]);
  const [selectedSale, setSelectedSale] = useState<Sale | null>(null);
  const [returnLines, setReturnLines] = useState<ReturnLine[]>([]);
  const [exchangeLines, setExchangeLines] = useState<ExchangeLine[]>([]);
  const [exchangeCode, setExchangeCode] = useState("");
  const [exchangeError, setExchangeError] = useState("");
  const [reason, setReason] = useState("");
  const [refundMode, setRefundMode] = useState<RefundMode>("cash");
  const [paymentMode, setPaymentMode] = useState<PaymentMode>("cash");

  const { data: outlets } = useQuery({ queryKey: ["outlets"], queryFn: () => listOutlets().then((r) => r.data) });
  const { data: existingReturns } = useQuery({
    queryKey: ["returns-for-sale", selectedSale?.id],
    queryFn: () => listReturns({ sale_id: selectedSale!.id }).then((r) => r.data),
    enabled: !!selectedSale,
  });
  const { data: recentReturns } = useQuery({
    queryKey: ["returns"],
    queryFn: () => listReturns().then((r) => r.data),
  });

  const alreadyReturned = useMemo(() => {
    const map: Record<number, number> = {};
    for (const ret of existingReturns || []) {
      for (const item of ret.return_items) {
        map[item.sale_item_id] = (map[item.sale_item_id] || 0) + item.quantity;
      }
    }
    return map;
  }, [existingReturns]);

  const resetForm = () => {
    setSelectedSale(null);
    setReturnLines([]);
    setExchangeLines([]);
    setReason("");
    setRefundMode("cash");
    setPaymentMode("cash");
    setSearchText("");
    setSaleOptions([]);
  };

  const returnMutation = useMutation({
    mutationFn: createReturn,
    onSuccess: (res) => {
      message.success(
        `${res.data.return_number} processed` +
          (res.data.difference < 0
            ? ` · ₹${Math.abs(res.data.difference).toFixed(2)} refunded via ${res.data.refund_mode}`
            : res.data.difference > 0
              ? ` · ₹${res.data.difference.toFixed(2)} collected via ${res.data.payment_mode}`
              : "")
      );
      resetForm();
      queryClient.invalidateQueries({ queryKey: ["returns"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to process return"),
  });

  const handleSearchSale = async (q: string) => {
    setSearchText(q);
    if (!q.trim()) return setSaleOptions([]);
    const res = await listSales({ search: q.trim() });
    setSaleOptions(res.data);
  };

  const selectSale = (saleId: number) => {
    const sale = saleOptions.find((s) => s.id === saleId);
    if (!sale) return;
    setSelectedSale(sale);
    setOutletId(sale.outlet_id);
    setReturnLines(
      sale.items.map((i) => ({
        sale_item_id: i.id,
        variant_id: i.variant_id,
        sku: i.sku || "",
        product_name: i.product_name || "",
        purchased_quantity: i.quantity,
        quantity: 0,
        unit_price: i.unit_price,
        tax_rate: i.tax_rate,
        restock: true,
      }))
    );
    setExchangeLines([]);
    setSaleOptions([]);
    setSearchText("");
  };

  const updateReturnQty = (saleItemId: number, qty: number) => {
    setReturnLines((prev) => prev.map((l) => (l.sale_item_id === saleItemId ? { ...l, quantity: qty } : l)));
  };

  const updateReturnRestock = (saleItemId: number, restock: boolean) => {
    setReturnLines((prev) => prev.map((l) => (l.sale_item_id === saleItemId ? { ...l, restock } : l)));
  };

  const handleScanExchange = async () => {
    if (!exchangeCode.trim() || !outletId) return;
    setExchangeError("");
    try {
      const res = await lookupBarcode(exchangeCode.trim(), outletId);
      const item = res.data;
      setExchangeLines((prev) => {
        const existing = prev.find((l) => l.variant_id === item.variant_id);
        if (existing) {
          return prev.map((l) => (l.variant_id === item.variant_id ? { ...l, quantity: l.quantity + 1 } : l));
        }
        return [
          ...prev,
          {
            variant_id: item.variant_id,
            sku: item.sku,
            product_name:
              item.product_name + (item.color || item.size ? ` (${[item.color, item.size].filter(Boolean).join("/")})` : ""),
            quantity: 1,
            unit_price: item.selling_price,
            tax_rate: item.tax_rate,
            available_quantity: item.available_quantity,
          },
        ];
      });
      setExchangeCode("");
    } catch (err: any) {
      setExchangeError(err?.response?.data?.detail || "Product not found");
    }
  };

  const updateExchangeQty = (variantId: number, qty: number) => {
    setExchangeLines((prev) => prev.map((l) => (l.variant_id === variantId ? { ...l, quantity: qty } : l)));
  };

  const removeExchangeLine = (variantId: number) => {
    setExchangeLines((prev) => prev.filter((l) => l.variant_id !== variantId));
  };

  const returnedValue = useMemo(
    () =>
      returnLines
        .filter((l) => l.quantity > 0)
        .reduce((sum, l) => sum + l.unit_price * l.quantity * (1 + l.tax_rate / 100), 0),
    [returnLines]
  );
  const exchangedValue = useMemo(
    () => exchangeLines.reduce((sum, l) => sum + l.unit_price * l.quantity * (1 + l.tax_rate / 100), 0),
    [exchangeLines]
  );
  const difference = Math.round((exchangedValue - returnedValue) * 100) / 100;

  const canSubmit = selectedSale && returnLines.some((l) => l.quantity > 0);

  const handleSubmit = () => {
    if (!selectedSale || !outletId) return;
    if (difference < 0 && refundMode === "store_credit" && !selectedSale.customer_id) {
      return message.error("Store credit refund needs a customer on the original sale");
    }
    returnMutation.mutate({
      sale_id: selectedSale.id,
      outlet_id: outletId,
      reason: reason || undefined,
      return_items: returnLines
        .filter((l) => l.quantity > 0)
        .map((l) => ({ sale_item_id: l.sale_item_id, quantity: l.quantity, restock: l.restock })),
      exchange_items: exchangeLines.map((l) => ({ variant_id: l.variant_id, quantity: l.quantity })),
      refund_mode: difference < 0 ? refundMode : undefined,
      payment_mode: difference > 0 ? paymentMode : undefined,
    });
  };

  return (
    <div>
      <Typography.Title level={3}>
        <RollbackOutlined /> Returns & Exchanges
      </Typography.Title>

      <Row gutter={[20, 20]}>
        <Col xs={24} xl={16}>
          <Card title="1. Find the original bill" style={{ marginBottom: 16 }}>
            {!selectedSale ? (
              <Select
                showSearch
                placeholder="Search by invoice number, customer name, or phone"
                style={{ width: "100%" }}
                filterOption={false}
                onSearch={handleSearchSale}
                onChange={(value) => selectSale(value as number)}
                options={saleOptions.map((s) => ({
                  value: s.id,
                  label: `${s.invoice_number} · ${s.customer_name || "Walk-in"} · ₹${s.total.toFixed(2)} · ${dayjs(s.created_at).format("DD MMM YYYY")}`,
                }))}
                notFoundContent={searchText.trim() ? "No matching bills" : null}
              />
            ) : (
              <Space direction="vertical" style={{ width: "100%" }}>
                <Space style={{ width: "100%", justifyContent: "space-between" }}>
                  <Typography.Text strong>
                    Invoice {selectedSale.invoice_number} · {selectedSale.customer_name || "Walk-in"} · ₹
                    {selectedSale.total.toFixed(2)}
                  </Typography.Text>
                  <Button size="small" onClick={resetForm}>
                    Change bill
                  </Button>
                </Space>

                <Typography.Text type="secondary">Select items to return</Typography.Text>
                <Table
                  size="small"
                  rowKey="sale_item_id"
                  dataSource={returnLines}
                  pagination={false}
                  scroll={{ x: 560 }}
                  columns={[
                    { title: "SKU", dataIndex: "sku" },
                    { title: "Product", dataIndex: "product_name" },
                    {
                      title: "Purchased",
                      dataIndex: "purchased_quantity",
                      render: (v: number, r: ReturnLine) => `${v} (${alreadyReturned[r.sale_item_id] || 0} returned)`,
                    },
                    {
                      title: "Return qty",
                      dataIndex: "quantity",
                      render: (v: number, r: ReturnLine) => {
                        const max = r.purchased_quantity - (alreadyReturned[r.sale_item_id] || 0);
                        return (
                          <InputNumber
                            min={0}
                            max={max}
                            value={v}
                            disabled={max <= 0}
                            onChange={(val) => updateReturnQty(r.sale_item_id, Math.min(val || 0, max))}
                          />
                        );
                      },
                    },
                    {
                      title: "Restock",
                      dataIndex: "restock",
                      render: (v: boolean, r: ReturnLine) => (
                        <Switch
                          checked={v}
                          disabled={r.quantity === 0}
                          onChange={(checked) => updateReturnRestock(r.sale_item_id, checked)}
                        />
                      ),
                    },
                  ]}
                />

                <Divider style={{ margin: "12px 0" }} />
                <Typography.Text type="secondary">
                  2. Give new items in exchange (optional) — outlet: {outlets?.find((o) => o.id === outletId)?.name}
                </Typography.Text>
                <Space.Compact style={{ width: "100%", maxWidth: 420 }}>
                  <Input
                    placeholder="Scan barcode or enter SKU, then press Enter"
                    value={exchangeCode}
                    onChange={(e) => setExchangeCode(e.target.value)}
                    onPressEnter={handleScanExchange}
                  />
                  <Button onClick={handleScanExchange}>Add</Button>
                </Space.Compact>
                {exchangeError && <Alert type="error" message={exchangeError} showIcon />}
                <Table
                  size="small"
                  rowKey="variant_id"
                  dataSource={exchangeLines}
                  pagination={false}
                  scroll={{ x: 480 }}
                  locale={{ emptyText: "No exchange items added" }}
                  columns={[
                    { title: "SKU", dataIndex: "sku" },
                    { title: "Product", dataIndex: "product_name" },
                    {
                      title: "Qty",
                      dataIndex: "quantity",
                      render: (v: number, r: ExchangeLine) => (
                        <InputNumber
                          min={1}
                          max={r.available_quantity}
                          value={v}
                          onChange={(val) => updateExchangeQty(r.variant_id, val || 1)}
                        />
                      ),
                    },
                    { title: "Price", dataIndex: "unit_price", render: (v: number) => `₹${v.toFixed(2)}` },
                    {
                      title: "",
                      key: "actions",
                      render: (_: unknown, r: ExchangeLine) => (
                        <Button danger size="small" icon={<DeleteOutlined />} onClick={() => removeExchangeLine(r.variant_id)} />
                      ),
                    },
                  ]}
                />

                <Form.Item label="Reason" style={{ marginTop: 12, marginBottom: 0 }}>
                  <Input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Wrong size, defect, changed mind..." />
                </Form.Item>
              </Space>
            )}
          </Card>
        </Col>

        <Col xs={24} xl={8}>
          <Card title="Summary">
            <Row justify="space-between">
              <Typography.Text>Returned value</Typography.Text>
              <Typography.Text>₹{returnedValue.toFixed(2)}</Typography.Text>
            </Row>
            <Row justify="space-between">
              <Typography.Text>Exchanged value</Typography.Text>
              <Typography.Text>₹{exchangedValue.toFixed(2)}</Typography.Text>
            </Row>
            <Divider />
            <Row justify="space-between">
              <Typography.Title level={4}>
                {difference > 0 ? "Customer pays" : difference < 0 ? "Refund due" : "Difference"}
              </Typography.Title>
              <Typography.Title level={4}>₹{Math.abs(difference).toFixed(2)}</Typography.Title>
            </Row>

            {difference > 0 && (
              <Select
                value={paymentMode}
                onChange={setPaymentMode}
                style={{ width: "100%", marginBottom: 12 }}
                options={[
                  { value: "cash", label: "Collect via Cash" },
                  { value: "card", label: "Collect via Card" },
                  { value: "upi", label: "Collect via UPI" },
                  { value: "other", label: "Collect via Other" },
                ]}
              />
            )}
            {difference < 0 && (
              <Select
                value={refundMode}
                onChange={setRefundMode}
                style={{ width: "100%", marginBottom: 12 }}
                options={[
                  { value: "cash", label: "Refund via Cash" },
                  { value: "store_credit", label: "Refund as Store Credit", disabled: !selectedSale?.customer_id },
                ]}
              />
            )}

            <Button
              type="primary"
              block
              size="large"
              disabled={!canSubmit}
              loading={returnMutation.isPending}
              onClick={handleSubmit}
            >
              Process Return
            </Button>
          </Card>
        </Col>
      </Row>

      <Card title="Recent returns" style={{ marginTop: 20 }}>
        <Table
          rowKey="id"
          scroll={{ x: 720 }}
          dataSource={recentReturns}
          columns={[
            { title: "Return #", dataIndex: "return_number" },
            { title: "Invoice", dataIndex: "sale_invoice_number" },
            { title: "Customer", dataIndex: "customer_name", render: (v: string | null) => v || "Walk-in" },
            { title: "Outlet", dataIndex: "outlet_name" },
            {
              title: "Difference",
              dataIndex: "difference",
              render: (v: number) =>
                v > 0 ? (
                  <Tag color="blue">Collected ₹{v.toFixed(2)}</Tag>
                ) : v < 0 ? (
                  <Tag color="orange">Refunded ₹{Math.abs(v).toFixed(2)}</Tag>
                ) : (
                  <Tag>Even swap</Tag>
                ),
            },
            { title: "Reason", dataIndex: "reason" },
            {
              title: "Date",
              dataIndex: "created_at",
              render: (v: string) => dayjs(v).format("DD MMM YYYY, h:mm A"),
            },
          ]}
          expandable={{ expandedRowRender: (ret) => <ReturnDetail ret={ret} /> }}
        />
      </Card>
    </div>
  );
}
