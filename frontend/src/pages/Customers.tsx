import { EditOutlined, PlusOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AutoComplete,
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
  Tabs,
  Tag,
  Typography,
  message,
} from "antd";
import dayjs from "dayjs";
import { useState } from "react";
import {
  adjustCustomerBalance,
  adjustCustomerLoyalty,
  createCustomer,
  createCustomerAddress,
  deleteCustomerAddress,
  listCustomerAddresses,
  listCustomerBalanceAdjustments,
  listCustomerLoyaltyAdjustments,
  listCustomerPurchases,
  listCustomers,
  receiptPdfUrl,
  updateCustomer,
} from "../api/endpoints";
import type { Customer } from "../api/types";
import ExportButton from "../components/ExportButton";

const TAG_COLORS: Record<string, string> = {
  VIP: "gold",
  Wholesale: "purple",
  Regular: "blue",
};

function AddressesTab({ customer }: { customer: Customer }) {
  const queryClient = useQueryClient();
  const [form] = Form.useForm();

  const { data: addresses } = useQuery({
    queryKey: ["customer-addresses", customer.id],
    queryFn: () => listCustomerAddresses(customer.id).then((r) => r.data),
  });

  const createMutation = useMutation({
    mutationFn: createCustomerAddress,
    onSuccess: () => {
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ["customer-addresses", customer.id] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to add address"),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteCustomerAddress,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["customer-addresses", customer.id] }),
  });

  const columns = [
    { title: "Label", dataIndex: "label" },
    { title: "Address", dataIndex: "line1" },
    { title: "City", dataIndex: "city" },
    { title: "State", dataIndex: "state" },
    { title: "Pincode", dataIndex: "pincode" },
    {
      title: "Default",
      dataIndex: "is_default",
      render: (v: boolean) => (v ? <Tag color="green">Default</Tag> : null),
    },
    {
      title: "",
      key: "actions",
      render: (_: unknown, a: { id: number }) => (
        <Button size="small" danger onClick={() => deleteMutation.mutate(a.id)}>
          Remove
        </Button>
      ),
    },
  ];

  return (
    <div>
      <Table
        size="small"
        rowKey="id"
        columns={columns}
        dataSource={addresses}
        pagination={false}
        style={{ marginBottom: 12 }}
      />
      <Form
        layout="inline"
        form={form}
        onFinish={(values) => createMutation.mutate({ ...values, customer_id: customer.id })}
      >
        <Form.Item name="label">
          <Input placeholder="Label (Home/Work)" style={{ width: 130 }} />
        </Form.Item>
        <Form.Item name="line1" rules={[{ required: true }]}>
          <Input placeholder="Address line" style={{ width: 220 }} />
        </Form.Item>
        <Form.Item name="city">
          <Input placeholder="City" style={{ width: 120 }} />
        </Form.Item>
        <Form.Item name="state">
          <Input placeholder="State" style={{ width: 120 }} />
        </Form.Item>
        <Form.Item name="pincode">
          <Input placeholder="Pincode" style={{ width: 100 }} />
        </Form.Item>
        <Form.Item name="is_default" valuePropName="checked">
          <Switch checkedChildren="Default" unCheckedChildren="Default" />
        </Form.Item>
        <Form.Item>
          <Button htmlType="submit" icon={<PlusOutlined />}>
            Add address
          </Button>
        </Form.Item>
      </Form>
    </div>
  );
}

function PurchaseHistoryTab({ customer }: { customer: Customer }) {
  const { data: purchases, isLoading } = useQuery({
    queryKey: ["customer-purchases", customer.id],
    queryFn: () => listCustomerPurchases(customer.id).then((r) => r.data),
  });

  const columns = [
    { title: "Invoice #", dataIndex: "invoice_number" },
    { title: "Outlet", dataIndex: "outlet_name" },
    {
      title: "Date",
      dataIndex: "created_at",
      render: (v: string) => dayjs(v).format("DD MMM YYYY, h:mm A"),
    },
    { title: "Payment", dataIndex: "payment_mode" },
    { title: "Total", dataIndex: "total", render: (v: number) => `₹${v.toFixed(2)}` },
    {
      title: "",
      key: "actions",
      render: (_: unknown, p: { sale_id: number }) => (
        <a href={receiptPdfUrl(p.sale_id)} target="_blank" rel="noreferrer">
          View receipt
        </a>
      ),
    },
  ];

  return (
    <Table
      size="small"
      rowKey="sale_id"
      loading={isLoading}
      columns={columns}
      dataSource={purchases}
      pagination={false}
      locale={{ emptyText: "No purchases yet" }}
    />
  );
}

function BalanceTab({ customer }: { customer: Customer }) {
  const queryClient = useQueryClient();
  const [form] = Form.useForm();

  const { data: adjustments } = useQuery({
    queryKey: ["customer-balance-adjustments", customer.id],
    queryFn: () => listCustomerBalanceAdjustments(customer.id).then((r) => r.data),
  });

  const adjustMutation = useMutation({
    mutationFn: (values: { balance_type: "credit" | "outstanding"; amount_delta: number; reason?: string }) =>
      adjustCustomerBalance(customer.id, values),
    onSuccess: () => {
      message.success("Balance adjusted");
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ["customer-balance-adjustments", customer.id] });
      queryClient.invalidateQueries({ queryKey: ["customers"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to adjust balance"),
  });

  const columns = [
    {
      title: "Date",
      dataIndex: "created_at",
      render: (v: string) => dayjs(v).format("DD MMM YYYY, h:mm A"),
    },
    { title: "Type", dataIndex: "balance_type" },
    {
      title: "Amount",
      dataIndex: "amount_delta",
      render: (v: number) => (v >= 0 ? `+₹${v.toFixed(2)}` : `-₹${Math.abs(v).toFixed(2)}`),
    },
    { title: "Reason", dataIndex: "reason" },
  ];

  return (
    <div>
      <Typography.Text strong style={{ display: "block", marginBottom: 12 }}>
        Current credit balance: ₹{Number(customer.credit_balance).toFixed(2)} · Loyalty points:{" "}
        {customer.loyalty_points}
      </Typography.Text>
      <Form
        layout="inline"
        form={form}
        style={{ marginBottom: 12 }}
        initialValues={{ balance_type: "credit" }}
        onFinish={(values) => adjustMutation.mutate(values)}
      >
        <Form.Item name="balance_type">
          <Select
            style={{ width: 130 }}
            options={[
              { value: "credit", label: "Credit" },
              { value: "outstanding", label: "Outstanding" },
            ]}
          />
        </Form.Item>
        <Form.Item name="amount_delta" rules={[{ required: true }]}>
          <InputNumber placeholder="Amount (+/-)" />
        </Form.Item>
        <Form.Item name="reason">
          <Input placeholder="Reason" style={{ width: 200 }} />
        </Form.Item>
        <Form.Item>
          <Button htmlType="submit" loading={adjustMutation.isPending}>
            Adjust balance
          </Button>
        </Form.Item>
      </Form>
      <Table
        size="small"
        rowKey="id"
        columns={columns}
        dataSource={adjustments}
        pagination={false}
        locale={{ emptyText: "No balance adjustments yet" }}
      />
    </div>
  );
}

function LoyaltyTab({ customer }: { customer: Customer }) {
  const queryClient = useQueryClient();
  const [form] = Form.useForm();

  const { data: adjustments } = useQuery({
    queryKey: ["customer-loyalty-adjustments", customer.id],
    queryFn: () => listCustomerLoyaltyAdjustments(customer.id).then((r) => r.data),
  });

  const adjustMutation = useMutation({
    mutationFn: (values: { points_delta: number; reason?: string }) =>
      adjustCustomerLoyalty(customer.id, values),
    onSuccess: () => {
      message.success("Loyalty points adjusted");
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ["customer-loyalty-adjustments", customer.id] });
      queryClient.invalidateQueries({ queryKey: ["customers"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to adjust loyalty points"),
  });

  const columns = [
    {
      title: "Date",
      dataIndex: "created_at",
      render: (v: string) => dayjs(v).format("DD MMM YYYY, h:mm A"),
    },
    {
      title: "Points",
      dataIndex: "points_delta",
      render: (v: number) => (v >= 0 ? `+${v}` : v),
    },
    { title: "Reason", dataIndex: "reason" },
  ];

  return (
    <div>
      <Typography.Text strong style={{ display: "block", marginBottom: 12 }}>
        Current loyalty points: {customer.loyalty_points}
        {customer.is_vip && (
          <Tag color="gold" style={{ marginLeft: 8 }}>
            VIP · earns 2x points
          </Tag>
        )}
      </Typography.Text>
      <Form
        layout="inline"
        form={form}
        style={{ marginBottom: 12 }}
        onFinish={(values) => adjustMutation.mutate(values)}
      >
        <Form.Item name="points_delta" rules={[{ required: true }]}>
          <InputNumber placeholder="Points (+/-)" />
        </Form.Item>
        <Form.Item name="reason">
          <AutoComplete
            placeholder="Reason"
            style={{ width: 200 }}
            options={[
              { value: "Birthday bonus" },
              { value: "Festival bonus" },
              { value: "Referral bonus" },
              { value: "Correction" },
            ]}
          />
        </Form.Item>
        <Form.Item>
          <Button htmlType="submit" loading={adjustMutation.isPending}>
            Adjust points
          </Button>
        </Form.Item>
      </Form>
      <Table
        size="small"
        rowKey="id"
        columns={columns}
        dataSource={adjustments}
        pagination={false}
        locale={{ emptyText: "No loyalty adjustments yet" }}
      />
    </div>
  );
}

function CustomerDetail({ customer }: { customer: Customer }) {
  return (
    <div style={{ padding: "8px 16px" }}>
      <Tabs
        items={[
          { key: "addresses", label: "Addresses", children: <AddressesTab customer={customer} /> },
          { key: "purchases", label: "Purchase History", children: <PurchaseHistoryTab customer={customer} /> },
          { key: "balance", label: "Balance", children: <BalanceTab customer={customer} /> },
          { key: "loyalty", label: "Loyalty", children: <LoyaltyTab customer={customer} /> },
        ]}
      />
    </div>
  );
}

export default function Customers() {
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editingCustomer, setEditingCustomer] = useState<Customer | null>(null);
  const [isGstCustomer, setIsGstCustomer] = useState(false);
  const [form] = Form.useForm();

  const { data: customers, isLoading } = useQuery({
    queryKey: ["customers"],
    queryFn: () => listCustomers().then((r) => r.data),
  });

  const closeModal = () => {
    setModalOpen(false);
    setEditingCustomer(null);
    setIsGstCustomer(false);
    form.resetFields();
  };

  const createMutation = useMutation({
    mutationFn: createCustomer,
    onSuccess: () => {
      message.success("Customer created");
      closeModal();
      queryClient.invalidateQueries({ queryKey: ["customers"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to create customer"),
  });

  const updateMutation = useMutation({
    mutationFn: (values: Record<string, unknown>) => updateCustomer(editingCustomer!.id, values),
    onSuccess: () => {
      message.success("Customer updated");
      closeModal();
      queryClient.invalidateQueries({ queryKey: ["customers"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to update customer"),
  });

  const openCreate = () => {
    setEditingCustomer(null);
    setIsGstCustomer(false);
    form.resetFields();
    setModalOpen(true);
  };

  const openEdit = (customer: Customer) => {
    setEditingCustomer(customer);
    setIsGstCustomer(customer.is_gst_customer);
    form.setFieldsValue({
      ...customer,
      birthday: customer.birthday ? dayjs(customer.birthday) : undefined,
      anniversary: customer.anniversary ? dayjs(customer.anniversary) : undefined,
    });
    setModalOpen(true);
  };

  const handleFinish = (values: Record<string, any>) => {
    const payload = {
      ...values,
      birthday: values.birthday ? values.birthday.format("YYYY-MM-DD") : null,
      anniversary: values.anniversary ? values.anniversary.format("YYYY-MM-DD") : null,
    };
    if (editingCustomer) {
      updateMutation.mutate(payload);
    } else {
      createMutation.mutate(payload);
    }
  };

  const columns = [
    {
      title: "Name",
      dataIndex: "name",
      render: (v: string, customer: Customer) => (
        <>
          {v}
          {customer.is_vip && (
            <Tag color="gold" style={{ marginLeft: 6 }}>
              VIP
            </Tag>
          )}
        </>
      ),
    },
    { title: "Phone", dataIndex: "phone" },
    { title: "Email", dataIndex: "email" },
    {
      title: "Tags",
      dataIndex: "tags",
      render: (tags: string[]) => (
        <>
          {tags?.map((t) => (
            <Tag key={t} color={TAG_COLORS[t] || "default"}>
              {t}
            </Tag>
          ))}
        </>
      ),
    },
    {
      title: "Credit Balance",
      dataIndex: "credit_balance",
      render: (v: number) => `₹${Number(v).toFixed(2)}`,
    },
    { title: "Loyalty Points", dataIndex: "loyalty_points" },
    {
      title: "",
      key: "actions",
      render: (_: unknown, customer: Customer) => (
        <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(customer)}>
          Edit
        </Button>
      ),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16, width: "100%", justifyContent: "space-between" }}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          Customers
        </Typography.Title>
        <Space>
          <ExportButton url="/api/customers/export" filenameBase="customers" />
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
            New Customer
          </Button>
        </Space>
      </Space>

      <Table
        rowKey="id"
        sticky
        loading={isLoading}
        columns={columns}
        dataSource={customers}
        expandable={{ expandedRowRender: (customer) => <CustomerDetail customer={customer} /> }}
      />

      <Modal
        title={editingCustomer ? `Edit Customer - ${editingCustomer.name}` : "New Customer"}
        open={modalOpen}
        onCancel={closeModal}
        onOk={() => form.submit()}
        confirmLoading={createMutation.isPending || updateMutation.isPending}
        width={640}
      >
        <Form form={form} layout="vertical" onFinish={handleFinish}>
          <Form.Item name="name" label="Name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Space style={{ width: "100%" }} size="large">
            <Form.Item name="phone" label="Phone" style={{ width: 200 }}>
              <Input />
            </Form.Item>
            <Form.Item name="email" label="Email" style={{ width: 240 }}>
              <Input />
            </Form.Item>
          </Space>
          <Form.Item
            name="whatsapp_number"
            label="WhatsApp number"
            tooltip="Include country code, digits only, e.g. 919876543210"
            rules={[{ pattern: /^[0-9]{10,15}$/, message: "Digits only, with country code" }]}
          >
            <Input placeholder="919876543210" />
          </Form.Item>
          <Space style={{ width: "100%" }} size="large">
            <Form.Item name="birthday" label="Birthday">
              <DatePicker />
            </Form.Item>
            <Form.Item name="anniversary" label="Anniversary">
              <DatePicker />
            </Form.Item>
          </Space>
          <Space style={{ width: "100%" }} size="large">
            <Form.Item name="is_gst_customer" label="GST Customer" valuePropName="checked">
              <Switch onChange={setIsGstCustomer} />
            </Form.Item>
            {isGstCustomer && (
              <Form.Item name="gstin" label="GSTIN" style={{ width: 240 }}>
                <Input />
              </Form.Item>
            )}
            <Form.Item
              name="is_vip"
              label="VIP member"
              valuePropName="checked"
              tooltip="VIP members earn loyalty points at 2x the normal rate"
            >
              <Switch />
            </Form.Item>
          </Space>
          <Form.Item name="tags" label="Tags">
            <Select
              mode="tags"
              placeholder="VIP, Wholesale, Regular, or your own..."
              options={[
                { value: "VIP", label: "VIP" },
                { value: "Wholesale", label: "Wholesale" },
                { value: "Regular", label: "Regular" },
              ]}
            />
          </Form.Item>
          <Form.Item name="preferred_sizes" label="Preferred sizes">
            <Select mode="tags" placeholder="S, M, L..." />
          </Form.Item>
          <Form.Item name="preferred_colors" label="Preferred colors">
            <Select mode="tags" placeholder="Red, Blue..." />
          </Form.Item>
          <Form.Item name="favorite_brands" label="Favorite brands">
            <Select mode="tags" placeholder="Tanisi..." />
          </Form.Item>
          <Form.Item name="notes" label="Notes">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
