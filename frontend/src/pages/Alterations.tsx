import { PlusOutlined, ScissorOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AutoComplete,
  Button,
  DatePicker,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import dayjs from "dayjs";
import { useMemo, useState } from "react";
import { createAlteration, listOutlets, listSales, updateAlteration, listAlterations } from "../api/endpoints";
import type { Alteration, AlterationStatus, Sale } from "../api/types";

const STATUS_LABELS: Record<AlterationStatus, string> = {
  requested: "Requested",
  assigned: "Assigned",
  in_progress: "In Progress",
  ready: "Ready",
  delivered: "Delivered",
  cancelled: "Cancelled",
};

const STATUS_COLORS: Record<AlterationStatus, string> = {
  requested: "default",
  assigned: "blue",
  in_progress: "gold",
  ready: "green",
  delivered: "purple",
  cancelled: "red",
};

const STATUS_OPTIONS = Object.entries(STATUS_LABELS).map(([value, label]) => ({ value, label }));

function NewAlterationModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [form] = Form.useForm();
  const [searchText, setSearchText] = useState("");
  const [saleOptions, setSaleOptions] = useState<Sale[]>([]);
  const [selectedSale, setSelectedSale] = useState<Sale | null>(null);
  const { data: outlets } = useQuery({ queryKey: ["outlets"], queryFn: () => listOutlets().then((r) => r.data) });
  const { data: existing } = useQuery({
    queryKey: ["alterations"],
    queryFn: () => listAlterations().then((r) => r.data),
  });
  const tailorSuggestions = useMemo(
    () => Array.from(new Set((existing ?? []).map((a) => a.tailor_name).filter(Boolean))) as string[],
    [existing]
  );

  const createMutation = useMutation({
    mutationFn: createAlteration,
    onSuccess: (res) => {
      message.success(`${res.data.alteration_number} created`);
      queryClient.invalidateQueries({ queryKey: ["alterations"] });
      onClose();
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to create alteration"),
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
    form.setFieldsValue({
      outlet_id: sale.outlet_id,
      sale_id: sale.id,
      customer_name: sale.customer_name,
      customer_phone: sale.customer_phone,
    });
  };

  return (
    <Modal
      title="New Alteration"
      open
      onCancel={onClose}
      onOk={() => form.submit()}
      confirmLoading={createMutation.isPending}
      width={640}
    >
      <Form
        form={form}
        layout="vertical"
        onFinish={(values) =>
          createMutation.mutate({
            ...values,
            expected_ready_date: values.expected_ready_date ? values.expected_ready_date.format("YYYY-MM-DD") : undefined,
          })
        }
      >
        <Form.Item label="Link to a bill (optional)">
          <Select
            showSearch
            allowClear
            placeholder="Search by invoice number, customer name, or phone"
            filterOption={false}
            onSearch={handleSearchSale}
            onChange={(value) => (value ? selectSale(value as number) : setSelectedSale(null))}
            options={saleOptions.map((s) => ({
              value: s.id,
              label: `${s.invoice_number} · ${s.customer_name || "Walk-in"} · ${dayjs(s.created_at).format("DD MMM YYYY")}`,
            }))}
            notFoundContent={searchText.trim() ? "No matching bills" : null}
          />
        </Form.Item>
        {selectedSale && (
          <Form.Item name="sale_item_id" label="Garment purchased">
            <Select
              allowClear
              placeholder="Which item needs alteration?"
              options={selectedSale.items.map((i) => ({ value: i.id, label: `${i.product_name} (${i.sku})` }))}
            />
          </Form.Item>
        )}
        <Form.Item name="sale_id" hidden>
          <Input />
        </Form.Item>

        <Space style={{ width: "100%" }} size="large">
          <Form.Item name="outlet_id" label="Outlet" rules={[{ required: true }]} style={{ width: 240 }}>
            <Select options={outlets?.map((o) => ({ value: o.id, label: o.name }))} />
          </Form.Item>
          <Form.Item name="expected_ready_date" label="Expected ready date" style={{ width: 200 }}>
            <DatePicker style={{ width: "100%" }} />
          </Form.Item>
        </Space>

        <Space style={{ width: "100%" }} size="large">
          <Form.Item name="customer_name" label="Customer name" style={{ width: 220 }}>
            <Input />
          </Form.Item>
          <Form.Item name="customer_phone" label="Customer phone" style={{ width: 200 }}>
            <Input />
          </Form.Item>
        </Space>

        <Form.Item name="description" label="Alteration needed" rules={[{ required: true }]}>
          <Input.TextArea rows={2} placeholder="e.g. Take in waist by 2 inches, hem length by 1 inch" />
        </Form.Item>

        <Form.Item name="tailor_name" label="Assign tailor (optional)">
          <AutoComplete
            options={tailorSuggestions.map((t) => ({ value: t }))}
            placeholder="e.g. Ramesh"
            filterOption={(inputValue, option) =>
              (option?.value as string).toLowerCase().includes(inputValue.toLowerCase())
            }
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}

export default function Alterations() {
  const queryClient = useQueryClient();
  const [outletId, setOutletId] = useState<number | undefined>();
  const [statusFilter, setStatusFilter] = useState<AlterationStatus | undefined>();
  const [modalOpen, setModalOpen] = useState(false);

  const { data: alterations, isLoading } = useQuery({
    queryKey: ["alterations", outletId, statusFilter],
    queryFn: () => listAlterations({ outlet_id: outletId, status: statusFilter }).then((r) => r.data),
  });
  const { data: outlets } = useQuery({ queryKey: ["outlets"], queryFn: () => listOutlets().then((r) => r.data) });

  const statusMutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: AlterationStatus }) => updateAlteration(id, { status }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alterations"] }),
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to update status"),
  });

  const tailorMutation = useMutation({
    mutationFn: ({ id, tailor_name }: { id: number; tailor_name: string }) =>
      updateAlteration(id, { tailor_name, status: "assigned" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alterations"] }),
  });

  const columns = [
    { title: "Alteration #", dataIndex: "alteration_number" },
    { title: "Customer", dataIndex: "customer_name", render: (v: string | null) => v || "Walk-in" },
    { title: "Item", dataIndex: "item_name", render: (v: string | null) => v || "-" },
    { title: "Description", dataIndex: "description", ellipsis: true },
    {
      title: "Tailor",
      dataIndex: "tailor_name",
      render: (v: string | null, r: Alteration) => (
        <Input
          size="small"
          placeholder="Unassigned"
          defaultValue={v || ""}
          style={{ width: 120 }}
          onBlur={(e) => {
            const value = e.target.value.trim();
            if (value && value !== v) tailorMutation.mutate({ id: r.id, tailor_name: value });
          }}
        />
      ),
    },
    {
      title: "Status",
      dataIndex: "status",
      render: (v: AlterationStatus, r: Alteration) => (
        <Select
          size="small"
          value={v}
          style={{ width: 130 }}
          onChange={(status) => statusMutation.mutate({ id: r.id, status })}
          popupMatchSelectWidth={false}
          options={STATUS_OPTIONS.map((o) => ({
            value: o.value,
            label: (
              <Tag color={STATUS_COLORS[o.value as AlterationStatus]} style={{ margin: 0 }}>
                {o.label}
              </Tag>
            ),
          }))}
        />
      ),
    },
    {
      title: "Expected ready",
      dataIndex: "expected_ready_date",
      render: (v: string | null) => (v ? dayjs(v).format("DD MMM YYYY") : "-"),
    },
    {
      title: "Created",
      dataIndex: "created_at",
      render: (v: string) => dayjs(v).format("DD MMM YYYY"),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16, width: "100%", justifyContent: "space-between" }}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          <ScissorOutlined /> Tailor & Alterations
        </Typography.Title>
        <Space>
          <Select
            allowClear
            placeholder="All outlets"
            style={{ width: 180 }}
            options={outlets?.map((o) => ({ value: o.id, label: o.name }))}
            onChange={setOutletId}
          />
          <Select
            allowClear
            placeholder="All statuses"
            style={{ width: 160 }}
            options={STATUS_OPTIONS}
            onChange={setStatusFilter}
          />
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
            New Alteration
          </Button>
        </Space>
      </Space>

      <Table rowKey="id" loading={isLoading} columns={columns} dataSource={alterations} pagination={{ pageSize: 15 }} />

      {modalOpen && <NewAlterationModal onClose={() => setModalOpen(false)} />}
    </div>
  );
}
