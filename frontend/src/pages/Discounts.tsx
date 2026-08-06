import { EditOutlined, PlusOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Button,
  DatePicker,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import dayjs from "dayjs";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  createDiscountRule,
  listCategories,
  listDiscountRules,
  listProducts,
  updateDiscountRule,
} from "../api/endpoints";
import type { DiscountRule } from "../api/types";

const TYPE_LABELS: Record<string, string> = {
  percentage: "Percentage",
  flat: "Flat amount",
  bogo: "Buy X Get Y",
};

const SCOPE_LABELS: Record<string, string> = {
  all: "Whole cart",
  category: "Category",
  brand: "Brand",
  product: "Specific product",
};

export default function Discounts() {
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<DiscountRule | null>(null);
  const [form] = Form.useForm();
  const discountType = Form.useWatch("discount_type", form);
  const scope = Form.useWatch("scope", form);
  const [searchParams, setSearchParams] = useSearchParams();

  useEffect(() => {
    const productId = searchParams.get("product_id");
    const productName = searchParams.get("product_name");
    if (productId) {
      setEditing(null);
      form.resetFields();
      form.setFieldsValue({
        name: productName ? `Clearance - ${productName}` : "Clearance discount",
        scope: "product",
        product_id: Number(productId),
        discount_type: "percentage",
      });
      setModalOpen(true);
      setSearchParams({}, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const { data: rules, isLoading } = useQuery({
    queryKey: ["discount-rules"],
    queryFn: () => listDiscountRules().then((r) => r.data),
  });
  const { data: categories } = useQuery({
    queryKey: ["categories"],
    queryFn: () => listCategories().then((r) => r.data),
  });
  const { data: products } = useQuery({
    queryKey: ["products"],
    queryFn: () => listProducts().then((r) => r.data),
  });

  const closeModal = () => {
    setModalOpen(false);
    setEditing(null);
    form.resetFields();
  };

  const toPayload = (values: any) => ({
    ...values,
    start_date: values.start_date ? values.start_date.format("YYYY-MM-DD") : null,
    end_date: values.end_date ? values.end_date.format("YYYY-MM-DD") : null,
  });

  const createMutation = useMutation({
    mutationFn: createDiscountRule,
    onSuccess: () => {
      message.success("Discount rule created");
      closeModal();
      queryClient.invalidateQueries({ queryKey: ["discount-rules"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to create discount rule"),
  });

  const updateMutation = useMutation({
    mutationFn: (values: Record<string, unknown>) => updateDiscountRule(editing!.id, values),
    onSuccess: () => {
      message.success("Discount rule updated");
      closeModal();
      queryClient.invalidateQueries({ queryKey: ["discount-rules"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to update discount rule"),
  });

  const openEdit = (rule: DiscountRule) => {
    setEditing(rule);
    form.setFieldsValue({
      ...rule,
      start_date: rule.start_date ? dayjs(rule.start_date) : undefined,
      end_date: rule.end_date ? dayjs(rule.end_date) : undefined,
    });
    setModalOpen(true);
  };

  const columns = [
    { title: "Name", dataIndex: "name" },
    {
      title: "Trigger",
      key: "trigger",
      render: (_: unknown, r: DiscountRule) =>
        r.code ? <Tag color="blue">Coupon: {r.code}</Tag> : <Tag color="green">Automatic</Tag>,
    },
    { title: "Type", key: "type", render: (_: unknown, r: DiscountRule) => TYPE_LABELS[r.discount_type] },
    {
      title: "Value",
      key: "value",
      render: (_: unknown, r: DiscountRule) =>
        r.discount_type === "percentage"
          ? `${r.value}%`
          : r.discount_type === "flat"
            ? `₹${r.value}`
            : `Buy ${r.buy_quantity} get ${r.get_quantity}`,
    },
    { title: "Scope", key: "scope", render: (_: unknown, r: DiscountRule) => SCOPE_LABELS[r.scope] },
    {
      title: "VIP only",
      key: "vip",
      render: (_: unknown, r: DiscountRule) => (r.vip_only ? <Tag color="gold">VIP</Tag> : null),
    },
    {
      title: "Usage",
      key: "usage",
      render: (_: unknown, r: DiscountRule) => `${r.times_used}${r.usage_limit ? ` / ${r.usage_limit}` : ""}`,
    },
    {
      title: "Status",
      key: "status",
      render: (_: unknown, r: DiscountRule) =>
        r.is_active ? <Tag color="green">Active</Tag> : <Tag>Inactive</Tag>,
    },
    {
      title: "",
      key: "actions",
      render: (_: unknown, r: DiscountRule) => (
        <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(r)}>
          Edit
        </Button>
      ),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16, width: "100%", justifyContent: "space-between" }}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          Discounts & Coupons
        </Typography.Title>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => {
            setEditing(null);
            form.resetFields();
            setModalOpen(true);
          }}
        >
          New Discount
        </Button>
      </Space>

      <Table rowKey="id" loading={isLoading} columns={columns} dataSource={rules} pagination={{ pageSize: 15 }} />

      <Modal
        title={editing ? `Edit Discount - ${editing.name}` : "New Discount"}
        open={modalOpen}
        onCancel={closeModal}
        onOk={() => form.submit()}
        confirmLoading={createMutation.isPending || updateMutation.isPending}
        width={640}
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{ discount_type: "percentage", scope: "all", vip_only: false, min_purchase_amount: 0 }}
          onFinish={(values) => {
            const payload = toPayload(values);
            editing ? updateMutation.mutate(payload) : createMutation.mutate(payload);
          }}
        >
          <Space wrap style={{ width: "100%" }} size="large">
            <Form.Item name="name" label="Name" rules={[{ required: true }]} style={{ width: 260 }}>
              <Input placeholder="e.g. Festive Sale" />
            </Form.Item>
            <Form.Item
              name="code"
              label="Coupon code (leave blank for automatic)"
              style={{ width: 220 }}
            >
              <Input placeholder="e.g. DIWALI10" style={{ textTransform: "uppercase" }} />
            </Form.Item>
          </Space>

          <Space wrap style={{ width: "100%" }} size="large">
            <Form.Item name="discount_type" label="Discount type" rules={[{ required: true }]} style={{ width: 200 }}>
              <Select
                options={[
                  { value: "percentage", label: "Percentage off" },
                  { value: "flat", label: "Flat amount off" },
                  { value: "bogo", label: "Buy X Get Y free" },
                ]}
              />
            </Form.Item>
            {discountType === "bogo" ? (
              <>
                <Form.Item name="buy_quantity" label="Buy quantity" rules={[{ required: true }]} style={{ width: 140 }}>
                  <InputNumber min={1} style={{ width: "100%" }} />
                </Form.Item>
                <Form.Item name="get_quantity" label="Get free" rules={[{ required: true }]} style={{ width: 140 }}>
                  <InputNumber min={1} style={{ width: "100%" }} />
                </Form.Item>
              </>
            ) : (
              <Form.Item
                name="value"
                label={discountType === "flat" ? "Amount off (₹)" : "Percent off (%)"}
                rules={[{ required: true }]}
                style={{ width: 160 }}
              >
                <InputNumber min={0} max={discountType === "percentage" ? 100 : undefined} style={{ width: "100%" }} />
              </Form.Item>
            )}
            {discountType === "percentage" && (
              <Form.Item name="max_discount_amount" label="Max discount cap (₹, optional)" style={{ width: 200 }}>
                <InputNumber min={0} style={{ width: "100%" }} />
              </Form.Item>
            )}
          </Space>

          <Space wrap style={{ width: "100%" }} size="large">
            <Form.Item name="scope" label="Applies to" rules={[{ required: true }]} style={{ width: 200 }}>
              <Select
                options={[
                  { value: "all", label: "Whole cart" },
                  { value: "category", label: "Specific category" },
                  { value: "brand", label: "Specific brand" },
                  { value: "product", label: "Specific product" },
                ]}
              />
            </Form.Item>
            {scope === "category" && (
              <Form.Item name="category_id" label="Category" rules={[{ required: true }]} style={{ width: 220 }}>
                <Select options={categories?.map((c) => ({ value: c.id, label: c.name }))} />
              </Form.Item>
            )}
            {scope === "brand" && (
              <Form.Item name="brand" label="Brand" rules={[{ required: true }]} style={{ width: 220 }}>
                <Input placeholder="e.g. Tanisi" />
              </Form.Item>
            )}
            {scope === "product" && (
              <Form.Item name="product_id" label="Product" rules={[{ required: true }]} style={{ width: 260 }}>
                <Select
                  showSearch
                  optionFilterProp="label"
                  options={products?.map((p) => ({ value: p.id, label: p.name }))}
                />
              </Form.Item>
            )}
            <Form.Item name="vip_only" label="VIP customers only" valuePropName="checked">
              <Switch />
            </Form.Item>
          </Space>

          <Space wrap style={{ width: "100%" }} size="large">
            <Form.Item name="min_purchase_amount" label="Minimum cart value (₹)" style={{ width: 200 }}>
              <InputNumber min={0} style={{ width: "100%" }} />
            </Form.Item>
            <Form.Item name="usage_limit" label="Usage limit (optional)" style={{ width: 180 }}>
              <InputNumber min={1} style={{ width: "100%" }} />
            </Form.Item>
            <Form.Item name="start_date" label="Start date (optional)" style={{ width: 160 }}>
              <DatePicker style={{ width: "100%" }} />
            </Form.Item>
            <Form.Item name="end_date" label="End date (optional)" style={{ width: 160 }}>
              <DatePicker style={{ width: "100%" }} />
            </Form.Item>
          </Space>

          {editing && (
            <Form.Item name="is_active" label="Active" valuePropName="checked">
              <Switch />
            </Form.Item>
          )}
        </Form>
      </Modal>
    </div>
  );
}
