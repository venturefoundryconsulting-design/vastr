import {
  CheckCircleOutlined,
  DeleteOutlined,
  DownloadOutlined,
  MailOutlined,
  MessageOutlined,
  PrinterOutlined,
  ShoppingCartOutlined,
  TagOutlined,
  WhatsAppOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  Col,
  Divider,
  Form,
  Input,
  InputNumber,
  Modal,
  Row,
  Select,
  Space,
  Table,
  Typography,
  message,
} from "antd";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiClient } from "../api/client";
import {
  applyDiscount,
  checkout,
  createCustomer,
  getAppSettings,
  listCustomers,
  listOutlets,
  lookupBarcode,
  searchProductsForPos,
  sendReceiptEmail,
  sendReceiptSms,
  sendReceiptWhatsApp,
} from "../api/endpoints";
import { useAuth } from "../context/AuthContext";
import type { BarcodeLookupResult, Customer, DiscountApplyResult, PaymentMode, Sale } from "../api/types";

interface CartLine {
  variant_id: number;
  sku: string;
  product_name: string;
  quantity: number;
  unit_price: number;
  tax_rate: number;
  available_quantity: number;
}

export default function POS() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { data: appSettings } = useQuery({
    queryKey: ["app-settings"],
    queryFn: () => getAppSettings().then((r) => r.data),
  });
  const [outletId, setOutletId] = useState<number | undefined>(user?.outlet_id ?? undefined);
  const [code, setCode] = useState("");
  const [cart, setCart] = useState<CartLine[]>([]);
  const [customerId, setCustomerId] = useState<number | undefined>();
  const [selectedCustomer, setSelectedCustomer] = useState<Customer | null>(null);
  const [customerOptions, setCustomerOptions] = useState<Customer[]>([]);
  const [customerSearchText, setCustomerSearchText] = useState("");
  const [newCustomerModalOpen, setNewCustomerModalOpen] = useState(false);
  const [newCustomerForm] = Form.useForm();
  const [discount, setDiscount] = useState(0);
  const [couponInput, setCouponInput] = useState("");
  const [appliedCoupon, setAppliedCoupon] = useState<DiscountApplyResult | null>(null);
  const [couponError, setCouponError] = useState("");
  const [autoDiscount, setAutoDiscount] = useState<DiscountApplyResult | null>(null);
  const [redeemCredit, setRedeemCredit] = useState(0);
  const [redeemPoints, setRedeemPoints] = useState(0);
  const [paymentMode, setPaymentMode] = useState<PaymentMode>("cash");
  const [receipt, setReceipt] = useState<Sale | null>(null);
  const [scanError, setScanError] = useState("");

  const { data: outlets } = useQuery({ queryKey: ["outlets"], queryFn: () => listOutlets().then((r) => r.data) });

  useEffect(() => {
    if (!outletId && user?.outlet_id) setOutletId(user.outlet_id);
  }, [user, outletId]);

  useEffect(() => {
    if (appliedCoupon || cart.length === 0) {
      setAutoDiscount(null);
      return;
    }
    const timer = setTimeout(() => {
      applyDiscount({
        items: cart.map((l) => ({ variant_id: l.variant_id, quantity: l.quantity, unit_price: l.unit_price })),
        customer_id: customerId,
      })
        .then((res) => setAutoDiscount(res.data.applied ? res.data : null))
        .catch(() => setAutoDiscount(null));
    }, 350);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cart, customerId, appliedCoupon]);

  const checkoutMutation = useMutation({
    mutationFn: checkout,
    onSuccess: (res) => {
      setReceipt(res.data);
      setCart([]);
      setCustomerId(undefined);
      setSelectedCustomer(null);
      setCustomerOptions([]);
      setDiscount(0);
      setCouponInput("");
      setAppliedCoupon(null);
      setCouponError("");
      setAutoDiscount(null);
      setRedeemCredit(0);
      setRedeemPoints(0);
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Checkout failed"),
  });

  const couponMutation = useMutation({
    mutationFn: () =>
      applyDiscount({
        items: cart.map((l) => ({ variant_id: l.variant_id, quantity: l.quantity, unit_price: l.unit_price })),
        customer_id: customerId,
        coupon_code: couponInput.trim(),
      }),
    onSuccess: (res) => {
      if (res.data.applied) {
        setAppliedCoupon(res.data);
        setCouponError("");
      } else {
        setAppliedCoupon(null);
        setCouponError(res.data.message);
      }
    },
    onError: (err: any) => {
      setAppliedCoupon(null);
      setCouponError(err?.response?.data?.detail || "Failed to apply coupon");
    },
  });

  const createCustomerMutation = useMutation({
    mutationFn: createCustomer,
    onSuccess: (res) => {
      message.success("Customer added");
      setCustomerId(res.data.id);
      setSelectedCustomer(res.data);
      setCustomerOptions((prev) => [res.data, ...prev]);
      setNewCustomerModalOpen(false);
      newCustomerForm.resetFields();
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to add customer"),
  });

  const handleCustomerSearch = async (q: string) => {
    setCustomerSearchText(q);
    if (!q.trim()) return setCustomerOptions([]);
    const res = await listCustomers({ search: q.trim() });
    setCustomerOptions(res.data);
  };

  const handleCustomerSelect = (value: number | string) => {
    if (value === "__new__") {
      newCustomerForm.setFieldsValue({ name: customerSearchText });
      setNewCustomerModalOpen(true);
      return;
    }
    setCustomerId(value as number);
    setSelectedCustomer(customerOptions.find((c) => c.id === value) ?? null);
  };

  const printMutation = useMutation({
    mutationFn: async (saleId: number) => {
      const res = await apiClient.get(`/api/sales/${saleId}/receipt/pdf`, { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      window.open(url, "_blank");
    },
  });

  const downloadMutation = useMutation({
    mutationFn: async ({ saleId, invoiceNumber }: { saleId: number; invoiceNumber: string }) => {
      const res = await apiClient.get(`/api/sales/${saleId}/receipt/pdf`, { responseType: "blob" });
      const url = window.URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      const link = document.createElement("a");
      link.href = url;
      link.download = `${invoiceNumber}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    },
  });

  const whatsappMutation = useMutation({
    mutationFn: (saleId: number) => sendReceiptWhatsApp(saleId),
    onSuccess: (res) => {
      if (res.data.ok) message.success(res.data.detail, res.data.needs_setup ? 8 : undefined);
      else message.warning(res.data.detail, 8);
      if (res.data.whatsapp_link) window.open(res.data.whatsapp_link, "_blank");
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to send WhatsApp receipt"),
  });

  const handleWhatsAppClick = (saleId: number) => {
    if (appSettings && !appSettings.whatsapp_token_set) {
      Modal.confirm({
        title: "WhatsApp isn't fully set up",
        icon: <WhatsAppOutlined style={{ color: "#25D366" }} />,
        content:
          "Without WhatsApp Cloud API configured, the invoice PDF can't be attached automatically - " +
          "only a text message can be sent via a tap-to-chat link. You can continue with the text-only " +
          "link now, or set up Cloud API in Settings first for automatic sending with the PDF attached.",
        okText: "Continue with link",
        cancelText: "Go to Settings",
        onOk: () => whatsappMutation.mutate(saleId),
        onCancel: () => navigate("/settings"),
      });
      return;
    }
    whatsappMutation.mutate(saleId);
  };

  const smsMutation = useMutation({
    mutationFn: (saleId: number) => sendReceiptSms(saleId),
    onSuccess: (res) => message.success(res.data.detail),
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to send SMS receipt"),
  });

  const emailMutation = useMutation({
    mutationFn: (saleId: number) => sendReceiptEmail(saleId),
    onSuccess: (res) => message.success(res.data.detail),
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to send email receipt"),
  });

  const addItemToCart = (item: BarcodeLookupResult) => {
    setCart((prev) => {
      const existing = prev.find((l) => l.variant_id === item.variant_id);
      if (existing) {
        return prev.map((l) =>
          l.variant_id === item.variant_id ? { ...l, quantity: l.quantity + 1 } : l
        );
      }
      return [
        ...prev,
        {
          variant_id: item.variant_id,
          sku: item.sku,
          product_name: item.product_name + (item.color || item.size ? ` (${[item.color, item.size].filter(Boolean).join("/")})` : ""),
          quantity: 1,
          unit_price: item.selling_price,
          tax_rate: item.tax_rate,
          available_quantity: item.available_quantity,
        },
      ];
    });
  };

  const handleScan = async () => {
    if (!code.trim() || !outletId) return;
    setScanError("");
    try {
      const res = await lookupBarcode(code.trim(), outletId);
      addItemToCart(res.data);
      setCode("");
    } catch (err: any) {
      setScanError(err?.response?.data?.detail || "Product not found");
    }
  };

  const [nameSearchText, setNameSearchText] = useState("");
  const [nameSearchResults, setNameSearchResults] = useState<BarcodeLookupResult[]>([]);
  const [nameSearchLoading, setNameSearchLoading] = useState(false);
  const [nameSearchKey, setNameSearchKey] = useState(0);

  const handleNameSearch = async (value: string) => {
    setNameSearchText(value);
    if (!value.trim() || !outletId) {
      setNameSearchResults([]);
      return;
    }
    setNameSearchLoading(true);
    try {
      const res = await searchProductsForPos(value.trim(), outletId);
      setNameSearchResults(res.data);
    } finally {
      setNameSearchLoading(false);
    }
  };

  const handleNameSearchSelect = (variantId: number) => {
    const item = nameSearchResults.find((r) => r.variant_id === variantId);
    if (item) addItemToCart(item);
    setNameSearchText("");
    setNameSearchResults([]);
    // antd Select otherwise keeps showing the picked option's label as its value;
    // remounting via key resets it to an empty search field, ready for the next add.
    setNameSearchKey((k) => k + 1);
  };

  const updateQty = (variantId: number, qty: number) => {
    setCart((prev) => prev.map((l) => (l.variant_id === variantId ? { ...l, quantity: qty } : l)));
  };

  const removeLine = (variantId: number) => {
    setCart((prev) => prev.filter((l) => l.variant_id !== variantId));
  };

  const subtotal = useMemo(() => cart.reduce((sum, l) => sum + l.unit_price * l.quantity, 0), [cart]);
  const tax = useMemo(
    () => cart.reduce((sum, l) => sum + (l.unit_price * l.quantity * l.tax_rate) / 100, 0),
    [cart]
  );
  const effectiveDiscount = appliedCoupon?.applied ? appliedCoupon : autoDiscount;
  const ruleDiscountAmount = effectiveDiscount?.discount_amount ?? 0;
  const afterDiscount = Math.max(subtotal + tax - discount - ruleDiscountAmount, 0);
  const maxRedeemable = selectedCustomer
    ? Math.min(Number(selectedCustomer.credit_balance), afterDiscount)
    : 0;
  const effectiveRedeemCredit = Math.min(redeemCredit, maxRedeemable);
  const afterCredit = Math.max(afterDiscount - effectiveRedeemCredit, 0);
  const maxRedeemablePoints = selectedCustomer
    ? Math.min(selectedCustomer.loyalty_points, Math.floor(afterCredit))
    : 0;
  const effectiveRedeemPoints = Math.min(redeemPoints, maxRedeemablePoints);
  const total = Math.max(afterCredit - effectiveRedeemPoints, 0);

  const handleCheckout = () => {
    if (!outletId) return message.warning("Select an outlet first");
    if (!cart.length) return message.warning("Cart is empty");
    checkoutMutation.mutate({
      outlet_id: outletId,
      customer_id: customerId,
      customer_name: selectedCustomer?.name || undefined,
      customer_phone: selectedCustomer?.phone || undefined,
      customer_email: selectedCustomer?.email || undefined,
      discount_amount: discount,
      coupon_code: appliedCoupon?.applied ? couponInput.trim() : undefined,
      redeem_credit_amount: effectiveRedeemCredit,
      redeem_points: effectiveRedeemPoints,
      payment_mode: paymentMode,
      items: cart.map((l) => ({
        variant_id: l.variant_id,
        quantity: l.quantity,
        unit_price: l.unit_price,
        tax_rate: l.tax_rate,
      })),
    });
  };

  return (
    <div>
      <Typography.Title level={3}>
        <ShoppingCartOutlined /> Point of Sale
      </Typography.Title>

      <Row gutter={[20, 20]}>
        <Col xs={24} xl={16}>
          <Card style={{ marginBottom: 16 }}>
            <Row gutter={[10, 10]} align="middle">
              <Col xs={24} sm={8} md={7}>
                <Select
                  placeholder="Outlet"
                  style={{ width: "100%" }}
                  value={outletId}
                  options={outlets?.map((o) => ({ value: o.id, label: o.name }))}
                  onChange={setOutletId}
                />
              </Col>
              <Col xs={18} sm={12} md={13}>
                <Input
                  placeholder="Scan barcode or enter SKU, then press Enter"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  onPressEnter={handleScan}
                  autoFocus
                />
              </Col>
              <Col xs={6} sm={4} md={4}>
                <Button type="primary" block onClick={handleScan}>
                  Add
                </Button>
              </Col>
            </Row>
            {scanError && <Alert type="error" message={scanError} style={{ marginTop: 12 }} showIcon />}
            <Row style={{ marginTop: 10 }}>
              <Col span={24}>
                <Select
                  key={nameSearchKey}
                  showSearch
                  allowClear
                  style={{ width: "100%" }}
                  placeholder="Or search products by name"
                  filterOption={false}
                  searchValue={nameSearchText}
                  onSearch={handleNameSearch}
                  onSelect={handleNameSearchSelect}
                  onClear={() => setNameSearchResults([])}
                  loading={nameSearchLoading}
                  notFoundContent={nameSearchText.trim() ? "No matching products" : null}
                  options={nameSearchResults.map((r) => ({
                    value: r.variant_id,
                    label: `${r.product_name}${r.color || r.size ? ` (${[r.color, r.size].filter(Boolean).join("/")})` : ""} - ${r.sku} - ₹${r.selling_price.toFixed(2)} - ${r.available_quantity > 0 ? `${r.available_quantity} in stock` : "out of stock"}`,
                  }))}
                  disabled={!outletId}
                />
              </Col>
            </Row>
          </Card>

          <Table
            rowKey="variant_id"
            dataSource={cart}
            pagination={false}
            scroll={{ x: 640 }}
            locale={{ emptyText: "Cart is empty - scan a product to begin" }}
            columns={[
              { title: "SKU", dataIndex: "sku" },
              { title: "Product", dataIndex: "product_name" },
              {
                title: "Qty",
                dataIndex: "quantity",
                render: (v: number, r: CartLine) => (
                  <InputNumber
                    min={1}
                    max={r.available_quantity}
                    value={v}
                    onChange={(val) => updateQty(r.variant_id, val || 1)}
                  />
                ),
              },
              { title: "Price", dataIndex: "unit_price", render: (v: number) => `₹${v.toFixed(2)}` },
              { title: "Tax %", dataIndex: "tax_rate" },
              {
                title: "Line total",
                key: "total",
                render: (_: unknown, r: CartLine) =>
                  `₹${(r.unit_price * r.quantity * (1 + r.tax_rate / 100)).toFixed(2)}`,
              },
              {
                title: "",
                key: "actions",
                render: (_: unknown, r: CartLine) => (
                  <Button danger icon={<DeleteOutlined />} onClick={() => removeLine(r.variant_id)} />
                ),
              },
            ]}
          />
        </Col>

        <Col xs={24} xl={8}>
          <Card title="Checkout">
            <Select
              showSearch
              allowClear
              placeholder="Search customer by name / phone / email (optional)"
              style={{ width: "100%", marginBottom: 6 }}
              filterOption={false}
              value={customerId}
              onSearch={handleCustomerSearch}
              onChange={(value) => (value === undefined ? undefined : handleCustomerSelect(value))}
              onClear={() => {
                setCustomerId(undefined);
                setSelectedCustomer(null);
                setRedeemCredit(0);
                setRedeemPoints(0);
              }}
              options={[
                ...(customerSearchText.trim() &&
                !customerOptions.some((c) => c.name.toLowerCase() === customerSearchText.trim().toLowerCase())
                  ? [{ value: "__new__", label: `+ Add "${customerSearchText.trim()}" as new customer` }]
                  : []),
                ...customerOptions.map((c) => ({
                  value: c.id,
                  label: `${c.name}${c.phone ? " · " + c.phone : ""}`,
                })),
              ]}
            />
            {selectedCustomer && (
              <Typography.Text type="secondary" style={{ display: "block", marginBottom: 10 }}>
                Credit balance: ₹{Number(selectedCustomer.credit_balance).toFixed(2)} · Loyalty points:{" "}
                {selectedCustomer.loyalty_points}
                {selectedCustomer.is_vip && " · VIP (2x points)"}
              </Typography.Text>
            )}
            <Select
              value={paymentMode}
              onChange={setPaymentMode}
              style={{ width: "100%", marginBottom: 10 }}
              options={[
                { value: "cash", label: "Cash" },
                { value: "card", label: "Card" },
                { value: "upi", label: "UPI" },
                { value: "other", label: "Other" },
              ]}
            />
            <Space style={{ width: "100%", justifyContent: "space-between" }}>
              <span>Discount</span>
              <InputNumber min={0} value={discount} onChange={(v) => setDiscount(v || 0)} />
            </Space>

            <Space.Compact style={{ width: "100%", marginTop: 10 }}>
              <Input
                placeholder="Coupon code"
                value={couponInput}
                disabled={!!appliedCoupon?.applied}
                onChange={(e) => {
                  setCouponInput(e.target.value.toUpperCase());
                  setCouponError("");
                }}
                onPressEnter={() => couponInput.trim() && couponMutation.mutate()}
              />
              {appliedCoupon?.applied ? (
                <Button
                  danger
                  onClick={() => {
                    setAppliedCoupon(null);
                    setCouponInput("");
                    setCouponError("");
                  }}
                >
                  Remove
                </Button>
              ) : (
                <Button
                  icon={<TagOutlined />}
                  loading={couponMutation.isPending}
                  disabled={!couponInput.trim() || !cart.length}
                  onClick={() => couponMutation.mutate()}
                >
                  Apply
                </Button>
              )}
            </Space.Compact>
            {appliedCoupon?.applied && (
              <Typography.Text type="success" style={{ display: "block", marginTop: 4 }}>
                <CheckCircleOutlined /> {appliedCoupon.message}
              </Typography.Text>
            )}
            {couponError && (
              <Typography.Text type="danger" style={{ display: "block", marginTop: 4 }}>
                {couponError}
              </Typography.Text>
            )}
            {!appliedCoupon?.applied && autoDiscount?.applied && (
              <Typography.Text type="success" style={{ display: "block", marginTop: 4 }}>
                <TagOutlined /> {autoDiscount.message} (-₹{autoDiscount.discount_amount.toFixed(2)})
              </Typography.Text>
            )}

            {selectedCustomer && maxRedeemable > 0 && (
              <Space style={{ width: "100%", justifyContent: "space-between", marginTop: 10 }}>
                <span>Redeem credit (max ₹{maxRedeemable.toFixed(2)})</span>
                <InputNumber
                  min={0}
                  max={maxRedeemable}
                  value={redeemCredit}
                  onChange={(v) => setRedeemCredit(Math.min(v || 0, maxRedeemable))}
                />
              </Space>
            )}
            {selectedCustomer && maxRedeemablePoints > 0 && (
              <Space style={{ width: "100%", justifyContent: "space-between", marginTop: 10 }}>
                <span>Redeem points (max {maxRedeemablePoints}, 1pt = ₹1)</span>
                <InputNumber
                  min={0}
                  max={maxRedeemablePoints}
                  value={redeemPoints}
                  onChange={(v) => setRedeemPoints(Math.min(v || 0, maxRedeemablePoints))}
                />
              </Space>
            )}

            <Divider />
            <Row justify="space-between"><Typography.Text>Subtotal</Typography.Text><Typography.Text>₹{subtotal.toFixed(2)}</Typography.Text></Row>
            <Row justify="space-between"><Typography.Text>Tax</Typography.Text><Typography.Text>₹{tax.toFixed(2)}</Typography.Text></Row>
            <Row justify="space-between"><Typography.Text>Discount</Typography.Text><Typography.Text>-₹{discount.toFixed(2)}</Typography.Text></Row>
            {ruleDiscountAmount > 0 && (
              <Row justify="space-between">
                <Typography.Text>
                  {appliedCoupon?.applied ? `Coupon (${appliedCoupon.code})` : effectiveDiscount?.rule_name}
                </Typography.Text>
                <Typography.Text>-₹{ruleDiscountAmount.toFixed(2)}</Typography.Text>
              </Row>
            )}
            {effectiveRedeemCredit > 0 && (
              <Row justify="space-between"><Typography.Text>Credit applied</Typography.Text><Typography.Text>-₹{effectiveRedeemCredit.toFixed(2)}</Typography.Text></Row>
            )}
            {effectiveRedeemPoints > 0 && (
              <Row justify="space-between"><Typography.Text>Points redeemed</Typography.Text><Typography.Text>-₹{effectiveRedeemPoints.toFixed(2)}</Typography.Text></Row>
            )}
            <Divider />
            <Row justify="space-between">
              <Typography.Title level={4}>Total</Typography.Title>
              <Typography.Title level={4}>₹{total.toFixed(2)}</Typography.Title>
            </Row>

            <Button
              type="primary"
              block
              size="large"
              onClick={handleCheckout}
              loading={checkoutMutation.isPending}
              disabled={!cart.length}
            >
              Complete Sale
            </Button>
          </Card>
        </Col>
      </Row>

      <Modal
        title="Sale complete"
        open={!!receipt}
        onCancel={() => setReceipt(null)}
        footer={[
          <Button key="close" type="primary" onClick={() => setReceipt(null)}>
            New Sale
          </Button>,
        ]}
      >
        {receipt && (
          <div>
            <Typography.Paragraph>
              Invoice <b>{receipt.invoice_number}</b>
            </Typography.Paragraph>
            <Table
              rowKey="id"
              dataSource={receipt.items}
              pagination={false}
              size="small"
              scroll={{ x: "max-content" }}
              columns={[
                { title: "Item", dataIndex: "product_name" },
                { title: "Qty", dataIndex: "quantity" },
                { title: "Price", dataIndex: "unit_price", render: (v: number) => `₹${v.toFixed(2)}` },
              ]}
            />
            {receipt.rule_discount_amount > 0 && (
              <Row justify="space-between">
                <Typography.Text>{receipt.coupon_code ? `Coupon (${receipt.coupon_code})` : receipt.discount_rule_name}</Typography.Text>
                <Typography.Text>-₹{receipt.rule_discount_amount.toFixed(2)}</Typography.Text>
              </Row>
            )}
            {receipt.credit_applied > 0 && (
              <Row justify="space-between">
                <Typography.Text>Credit applied</Typography.Text>
                <Typography.Text>-₹{receipt.credit_applied.toFixed(2)}</Typography.Text>
              </Row>
            )}
            {receipt.points_redeemed > 0 && (
              <Row justify="space-between">
                <Typography.Text>Points redeemed</Typography.Text>
                <Typography.Text>-₹{receipt.points_redeemed.toFixed(2)}</Typography.Text>
              </Row>
            )}
            <Divider />
            <Row justify="space-between">
              <Typography.Title level={4}>Total</Typography.Title>
              <Typography.Title level={4}>₹{receipt.total.toFixed(2)}</Typography.Title>
            </Row>
            {receipt.loyalty_points_earned > 0 && (
              <Typography.Text type="secondary">
                +{receipt.loyalty_points_earned} loyalty points earned
              </Typography.Text>
            )}
            <Divider />
            <Space wrap>
              <Button
                icon={<PrinterOutlined />}
                loading={printMutation.isPending}
                onClick={() => printMutation.mutate(receipt.id)}
              >
                Print
              </Button>
              <Button
                icon={<DownloadOutlined />}
                loading={downloadMutation.isPending}
                onClick={() => downloadMutation.mutate({ saleId: receipt.id, invoiceNumber: receipt.invoice_number })}
              >
                Download PDF
              </Button>
              <Button
                icon={<WhatsAppOutlined />}
                style={{ background: "#25D366", color: "white", border: "none" }}
                loading={whatsappMutation.isPending}
                disabled={!receipt.customer_phone}
                title={receipt.customer_phone ? "" : "No customer phone number on this sale"}
                onClick={() => handleWhatsAppClick(receipt.id)}
              >
                WhatsApp
              </Button>
              <Button
                icon={<MessageOutlined />}
                loading={smsMutation.isPending}
                disabled={!receipt.customer_phone}
                title={receipt.customer_phone ? "" : "No customer phone number on this sale"}
                onClick={() => smsMutation.mutate(receipt.id)}
              >
                SMS
              </Button>
              <Button
                icon={<MailOutlined />}
                loading={emailMutation.isPending}
                disabled={!receipt.customer_email}
                title={receipt.customer_email ? "" : "No customer email on this sale"}
                onClick={() => emailMutation.mutate(receipt.id)}
              >
                Email
              </Button>
            </Space>
          </div>
        )}
      </Modal>

      <Modal
        title="New customer"
        open={newCustomerModalOpen}
        onCancel={() => setNewCustomerModalOpen(false)}
        onOk={() => newCustomerForm.submit()}
        confirmLoading={createCustomerMutation.isPending}
      >
        <Form
          form={newCustomerForm}
          layout="vertical"
          onFinish={(values) => createCustomerMutation.mutate(values)}
        >
          <Form.Item name="name" label="Name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="phone" label="Phone">
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
