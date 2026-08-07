import { EditOutlined, PlusOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Button,
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
import {
  createVendor,
  linkVendorProduct,
  listVendorProducts,
  listVendors,
  searchVariants,
  unlinkVendorProduct,
  updateVendor,
} from "../api/endpoints";
import type { Vendor, VariantWithStock } from "../api/types";
import ExportButton from "../components/ExportButton";

function VendorProducts({ vendor }: { vendor: Vendor }) {
  const queryClient = useQueryClient();
  const [options, setOptions] = useState<VariantWithStock[]>([]);
  const [form] = Form.useForm();

  const { data: links } = useQuery({
    queryKey: ["vendor-products", vendor.id],
    queryFn: () => listVendorProducts(vendor.id).then((r) => r.data),
  });

  const linkMutation = useMutation({
    mutationFn: linkVendorProduct,
    onSuccess: () => {
      message.success("Product linked to vendor");
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ["vendor-products", vendor.id] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to link product"),
  });

  const unlinkMutation = useMutation({
    mutationFn: unlinkVendorProduct,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["vendor-products", vendor.id] }),
  });

  const handleSearch = async (q: string) => {
    if (!q) return setOptions([]);
    const res = await searchVariants(q);
    setOptions(res.data);
  };

  return (
    <div style={{ padding: "8px 16px" }}>
      <Space wrap style={{ marginBottom: 12 }}>
        {links?.map((l) => (
          <Tag key={l.id} closable onClose={() => unlinkMutation.mutate(l.id)}>
            {l.product_name ? `${l.product_name} (${l.sku})` : `Variant #${l.variant_id}`} - ₹{l.cost_price}
          </Tag>
        ))}
        {!links?.length && <Typography.Text type="secondary">No products linked yet.</Typography.Text>}
      </Space>
      <Form
        layout="inline"
        form={form}
        onFinish={(values) =>
          linkMutation.mutate({
            vendor_id: vendor.id,
            variant_id: values.variant_id,
            cost_price: values.cost_price,
            is_preferred: true,
          })
        }
      >
        <Form.Item name="variant_id" rules={[{ required: true }]}>
          <Select
            showSearch
            placeholder="Search product / SKU / barcode"
            style={{ width: 280 }}
            filterOption={false}
            onSearch={handleSearch}
            options={options.map((o) => ({
              value: o.id,
              label: `${o.product_name} - ${[o.color, o.size].filter(Boolean).join("/")} (${o.sku})`,
            }))}
          />
        </Form.Item>
        <Form.Item name="cost_price" rules={[{ required: true }]}>
          <InputNumber placeholder="Cost price" />
        </Form.Item>
        <Form.Item>
          <Button htmlType="submit" icon={<PlusOutlined />}>
            Link product
          </Button>
        </Form.Item>
      </Form>
    </div>
  );
}

export default function Vendors() {
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editingVendor, setEditingVendor] = useState<Vendor | null>(null);
  const [form] = Form.useForm();

  const { data: vendors, isLoading } = useQuery({
    queryKey: ["vendors"],
    queryFn: () => listVendors().then((r) => r.data),
  });

  const closeModal = () => {
    setModalOpen(false);
    setEditingVendor(null);
    form.resetFields();
  };

  const createMutation = useMutation({
    mutationFn: createVendor,
    onSuccess: () => {
      message.success("Vendor created");
      closeModal();
      queryClient.invalidateQueries({ queryKey: ["vendors"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to create vendor"),
  });

  const updateMutation = useMutation({
    mutationFn: (values: Partial<Vendor>) => updateVendor(editingVendor!.id, values),
    onSuccess: () => {
      message.success("Vendor updated");
      closeModal();
      queryClient.invalidateQueries({ queryKey: ["vendors"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to update vendor"),
  });

  const openEdit = (vendor: Vendor) => {
    setEditingVendor(vendor);
    form.setFieldsValue(vendor);
    setModalOpen(true);
  };

  const columns = [
    { title: "Vendor", dataIndex: "name" },
    { title: "Contact", dataIndex: "contact_person" },
    {
      title: "WhatsApp",
      dataIndex: "whatsapp_number",
      render: (v: string | null) => (v ? <Tag color="green">{v}</Tag> : <Tag>none</Tag>),
    },
    { title: "GSTIN", dataIndex: "gstin" },
    { title: "Payment terms", dataIndex: "payment_terms" },
    {
      title: "",
      key: "actions",
      render: (_: unknown, vendor: Vendor) => (
        <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(vendor)}>
          Edit
        </Button>
      ),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16, width: "100%", justifyContent: "space-between" }}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          Vendors
        </Typography.Title>
        <Space>
          <ExportButton url="/api/vendors/export" filenameBase="vendors" />
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              setEditingVendor(null);
              form.resetFields();
              setModalOpen(true);
            }}
          >
            New Vendor
          </Button>
        </Space>
      </Space>

      <Table
        rowKey="id"
        loading={isLoading}
        columns={columns}
        dataSource={vendors}
        expandable={{ expandedRowRender: (vendor) => <VendorProducts vendor={vendor} /> }}
        scroll={{ x: "max-content" }}
      />

      <Modal
        title={editingVendor ? `Edit Vendor - ${editingVendor.name}` : "New Vendor"}
        open={modalOpen}
        onCancel={closeModal}
        onOk={() => form.submit()}
        confirmLoading={createMutation.isPending || updateMutation.isPending}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={(values) =>
            editingVendor ? updateMutation.mutate(values) : createMutation.mutate(values)
          }
        >
          <Form.Item name="name" label="Vendor name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="contact_person" label="Contact person">
            <Input />
          </Form.Item>
          <Form.Item
            name="whatsapp_number"
            label="WhatsApp number"
            tooltip="Include country code, digits only, e.g. 919876543210"
            rules={[{ pattern: /^[0-9]{10,15}$/, message: "Digits only, with country code" }]}
          >
            <Input placeholder="919876543210" />
          </Form.Item>
          <Form.Item name="phone" label="Phone">
            <Input />
          </Form.Item>
          <Form.Item name="email" label="Email">
            <Input />
          </Form.Item>
          <Form.Item name="gstin" label="GSTIN">
            <Input />
          </Form.Item>
          <Form.Item name="payment_terms" label="Payment terms">
            <Input placeholder="e.g. Net 15" />
          </Form.Item>
          <Form.Item name="address" label="Address">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
