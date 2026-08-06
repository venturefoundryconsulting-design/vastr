import { PlusOutlined, ThunderboltOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Button,
  Card,
  DatePicker,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  createPurchaseOrder,
  getReorderSuggestions,
  listOutlets,
  listPurchaseOrders,
  listVendors,
  searchVariants,
} from "../api/endpoints";
import type { PurchaseOrder, PurchaseOrderStatus, VariantWithStock } from "../api/types";
import ExportButton from "../components/ExportButton";

const STATUS_COLORS: Record<PurchaseOrderStatus, string> = {
  draft: "default",
  sent: "blue",
  confirmed: "cyan",
  partially_received: "orange",
  received: "green",
  cancelled: "red",
};

export default function PurchaseOrders() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();
  const [options, setOptions] = useState<VariantWithStock[]>([]);

  const { data: pos, isLoading } = useQuery({
    queryKey: ["purchase-orders"],
    queryFn: () => listPurchaseOrders().then((r) => r.data),
  });
  const { data: vendors } = useQuery({ queryKey: ["vendors"], queryFn: () => listVendors().then((r) => r.data) });
  const { data: outlets } = useQuery({ queryKey: ["outlets"], queryFn: () => listOutlets().then((r) => r.data) });
  const { data: suggestions, isLoading: suggestionsLoading } = useQuery({
    queryKey: ["reorder-suggestions"],
    queryFn: () => getReorderSuggestions().then((r) => r.data),
  });

  const createMutation = useMutation({
    mutationFn: createPurchaseOrder,
    onSuccess: (res) => {
      message.success("Purchase order created");
      setModalOpen(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ["purchase-orders"] });
      navigate(`/purchase-orders/${res.data.id}`);
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to create PO"),
  });

  const openFromSuggestion = (
    vendorId: number,
    items: {
      variant_id: number;
      suggested_quantity: number;
      cost_price: number;
      outlet_id: number;
      sku: string;
      product_name: string;
      color?: string | null;
      size?: string | null;
    }[]
  ) => {
    setModalOpen(true);
    setOptions((prev) => [
      ...prev,
      ...items.map((i) => ({
        id: i.variant_id,
        sku: i.sku,
        product_name: i.product_name,
        color: i.color,
        size: i.size,
      })) as VariantWithStock[],
    ]);
    form.setFieldsValue({
      vendor_id: vendorId,
      outlet_id: items[0]?.outlet_id,
      items: items.map((i) => ({
        variant_id: i.variant_id,
        quantity_ordered: i.suggested_quantity,
        unit_cost: i.cost_price,
        tax_rate: 0,
      })),
    });
  };

  const handleSearch = async (q: string) => {
    if (!q) return;
    const res = await searchVariants(q);
    setOptions(res.data);
  };

  const columns = [
    {
      title: "PO Number",
      dataIndex: "po_number",
      render: (v: string, r: PurchaseOrder) => (
        <a onClick={() => navigate(`/purchase-orders/${r.id}`)}>{v}</a>
      ),
    },
    { title: "Vendor", dataIndex: "vendor_name" },
    { title: "Deliver to", dataIndex: "outlet_name" },
    {
      title: "Status",
      dataIndex: "status",
      render: (s: PurchaseOrderStatus) => <Tag color={STATUS_COLORS[s]}>{s.replace("_", " ")}</Tag>,
    },
    { title: "Total", dataIndex: "total_amount", render: (v: number) => `₹${v.toFixed(2)}` },
    {
      title: "Order date",
      dataIndex: "order_date",
      render: (v: string) => new Date(v).toLocaleDateString(),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16, width: "100%", justifyContent: "space-between" }}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          Purchase Orders
        </Typography.Title>
        <Space>
          <ExportButton url="/api/purchase-orders/export" filenameBase="purchase_orders" />
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
            New Purchase Order
          </Button>
        </Space>
      </Space>

      <Card
        title={
          <Space>
            <ThunderboltOutlined /> Reorder suggestions (low stock)
          </Space>
        }
        style={{ marginBottom: 20 }}
        loading={suggestionsLoading}
      >
        {suggestions?.length ? (
          <Space direction="vertical" style={{ width: "100%" }}>
            {suggestions.map((s) => (
              <Card key={s.vendor_id} type="inner" title={s.vendor_name}>
                <Space wrap style={{ marginBottom: 8 }}>
                  {s.items.map((i) => (
                    <Tag key={i.variant_id} color="orange">
                      {i.product_name} ({i.sku}) @ {i.outlet_name}: {i.current_quantity} left, suggest{" "}
                      {i.suggested_quantity}
                    </Tag>
                  ))}
                </Space>
                <Button size="small" type="primary" onClick={() => openFromSuggestion(s.vendor_id, s.items)}>
                  Create PO from suggestion
                </Button>
              </Card>
            ))}
          </Space>
        ) : (
          <Empty description="No low-stock items right now" />
        )}
      </Card>

      <Table rowKey="id" loading={isLoading} columns={columns} dataSource={pos} pagination={{ pageSize: 15 }} />

      <Modal
        title="New Purchase Order"
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={createMutation.isPending}
        width={800}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={(values) =>
            createMutation.mutate({
              ...values,
              expected_date: values.expected_date?.toISOString(),
            })
          }
          initialValues={{ items: [{}] }}
        >
          <Space style={{ width: "100%" }} size="large">
            <Form.Item name="vendor_id" label="Vendor" rules={[{ required: true }]} style={{ width: 260 }}>
              <Select options={vendors?.map((v) => ({ value: v.id, label: v.name }))} />
            </Form.Item>
            <Form.Item name="outlet_id" label="Deliver to" rules={[{ required: true }]} style={{ width: 260 }}>
              <Select options={outlets?.map((o) => ({ value: o.id, label: o.name }))} />
            </Form.Item>
            <Form.Item name="expected_date" label="Expected date">
              <DatePicker />
            </Form.Item>
          </Space>
          <Form.Item name="notes" label="Notes">
            <Input.TextArea rows={2} />
          </Form.Item>

          <Typography.Title level={5}>Items</Typography.Title>
          <Form.List name="items">
            {(fields, { add, remove }) => (
              <>
                {fields.map((field) => (
                  <Space key={field.key} align="baseline" wrap style={{ marginBottom: 8 }}>
                    <Form.Item name={[field.name, "variant_id"]} rules={[{ required: true }]}>
                      <Select
                        showSearch
                        placeholder="Search product / SKU"
                        style={{ width: 260 }}
                        filterOption={false}
                        onSearch={handleSearch}
                        options={options.map((o) => ({
                          value: o.id,
                          label: `${o.product_name} - ${[o.color, o.size].filter(Boolean).join("/")} (${o.sku})`,
                        }))}
                      />
                    </Form.Item>
                    <Form.Item name={[field.name, "quantity_ordered"]} rules={[{ required: true }]}>
                      <InputNumber placeholder="Qty" style={{ width: 90 }} />
                    </Form.Item>
                    <Form.Item name={[field.name, "unit_cost"]} rules={[{ required: true }]}>
                      <InputNumber placeholder="Unit cost" style={{ width: 110 }} />
                    </Form.Item>
                    <Form.Item name={[field.name, "tax_rate"]} initialValue={0}>
                      <InputNumber placeholder="Tax %" style={{ width: 90 }} />
                    </Form.Item>
                    {fields.length > 1 && (
                      <Button danger onClick={() => remove(field.name)}>
                        Remove
                      </Button>
                    )}
                  </Space>
                ))}
                <Button onClick={() => add()} icon={<PlusOutlined />}>
                  Add item
                </Button>
              </>
            )}
          </Form.List>
        </Form>
      </Modal>
    </div>
  );
}
