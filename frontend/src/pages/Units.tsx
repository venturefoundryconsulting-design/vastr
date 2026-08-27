import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
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
import { useMemo, useState } from "react";
import {
  convertUom,
  createUom,
  createUomCategory,
  listUomCategories,
  listUoms,
  updateUom,
} from "../api/endpoints";
import type { Uom } from "../api/types";

export default function Units() {
  const queryClient = useQueryClient();
  const [unitOpen, setUnitOpen] = useState(false);
  const [categoryOpen, setCategoryOpen] = useState(false);
  const [unitForm] = Form.useForm();
  const [categoryForm] = Form.useForm();
  const [tryForm] = Form.useForm();
  const [tryResult, setTryResult] = useState<string | null>(null);
  const [tryError, setTryError] = useState<string | null>(null);

  const { data: categories } = useQuery({
    queryKey: ["uom-categories"],
    queryFn: () => listUomCategories().then((r) => r.data),
  });
  const { data: units, isLoading } = useQuery({
    queryKey: ["uoms"],
    queryFn: () => listUoms().then((r) => r.data),
  });

  const unitOptions = useMemo(
    () => (units ?? []).map((u) => ({ value: u.id, label: `${u.name} (${u.code})` })),
    [units],
  );

  const saveUnit = useMutation({
    mutationFn: (values: Partial<Uom>) => createUom(values),
    onSuccess: () => {
      message.success("Unit created");
      queryClient.invalidateQueries({ queryKey: ["uoms"] });
      setUnitOpen(false);
      unitForm.resetFields();
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Could not create the unit"),
  });

  const saveCategory = useMutation({
    mutationFn: (values: { code: string; name: string }) => createUomCategory(values),
    onSuccess: () => {
      message.success("Category created");
      queryClient.invalidateQueries({ queryKey: ["uom-categories"] });
      setCategoryOpen(false);
      categoryForm.resetFields();
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Could not create the category"),
  });

  const toggleActive = useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) => updateUom(id, { is_active }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["uoms"] }),
    onError: (err: any) => message.error(err?.response?.data?.detail || "Could not update the unit"),
  });

  /** The conversion tester doubles as the validation surface: incompatible pairs
   * come back as a 400 whose message explains why and what to do instead, so the
   * user learns the rule by trying rather than by reading documentation. */
  const tryConvert = useMutation({
    mutationFn: (v: { quantity: number; from_uom_id: number; to_uom_id: number }) => convertUom(v),
    onSuccess: (r) => {
      setTryError(null);
      setTryResult(`${r.data.quantity} ${r.data.to_uom}`);
    },
    onError: (err: any) => {
      setTryResult(null);
      setTryError(err?.response?.data?.detail || "That conversion isn't defined");
    },
  });

  const columns = [
    { title: "Code", dataIndex: "code", width: 100, render: (v: string) => <code>{v}</code> },
    { title: "Name", dataIndex: "name" },
    { title: "Symbol", dataIndex: "symbol", width: 90 },
    {
      title: "Measures",
      dataIndex: "category_code",
      width: 130,
      render: (v: string) => <Tag>{v}</Tag>,
    },
    {
      title: "Factor to base",
      dataIndex: "factor_to_base",
      width: 150,
      align: "right" as const,
      render: (v: number, r: Uom) =>
        r.is_base ? <Tag color="blue">base unit</Tag> : Number(v).toString(),
    },
    { title: "Decimals", dataIndex: "decimal_precision", width: 100, align: "right" as const },
    {
      title: "Active",
      key: "active",
      width: 90,
      render: (_: unknown, r: Uom) => (
        <Switch
          size="small"
          checked={r.is_active}
          disabled={r.is_base}
          onChange={(checked) => toggleActive.mutate({ id: r.id, is_active: checked })}
        />
      ),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16, width: "100%", justifyContent: "space-between" }} wrap>
        <Typography.Title level={3} style={{ margin: 0 }}>
          Units of Measure
        </Typography.Title>
        <Space>
          <Button onClick={() => setCategoryOpen(true)}>New category</Button>
          <Button type="primary" onClick={() => setUnitOpen(true)}>
            New unit
          </Button>
        </Space>
      </Space>

      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="Units only convert within what they measure"
        description={
          <>
            Metres convert to centimetres, and kilograms to grams, because each is anchored to its
            category's base unit. Pieces do not convert to metres &mdash; that depends on the item. To
            record something like <b>1 roll = 25&nbsp;m</b>, add a conversion on the item itself, where it
            can also differ per vendor.
          </>
        }
      />

      <Table
        rowKey="id"
        sticky
        loading={isLoading}
        columns={columns}
        dataSource={units}
        pagination={false}
        scroll={{ x: "max-content" }}
      />

      <Card size="small" title="Try a conversion" style={{ marginTop: 24, maxWidth: 720 }}>
        <Form
          form={tryForm}
          layout="inline"
          onFinish={(v) => tryConvert.mutate(v)}
          initialValues={{ quantity: 1 }}
        >
          <Form.Item name="quantity" rules={[{ required: true }]}>
            <InputNumber min={0} step={1} style={{ width: 110 }} />
          </Form.Item>
          <Form.Item name="from_uom_id" rules={[{ required: true }]}>
            <Select showSearch optionFilterProp="label" placeholder="From" style={{ width: 190 }} options={unitOptions} />
          </Form.Item>
          <Form.Item name="to_uom_id" rules={[{ required: true }]}>
            <Select showSearch optionFilterProp="label" placeholder="To" style={{ width: 190 }} options={unitOptions} />
          </Form.Item>
          <Form.Item>
            <Button htmlType="submit" loading={tryConvert.isPending}>
              Convert
            </Button>
          </Form.Item>
        </Form>
        {tryResult && (
          <Alert type="success" showIcon style={{ marginTop: 12 }} message={`= ${tryResult}`} />
        )}
        {tryError && <Alert type="warning" showIcon style={{ marginTop: 12 }} message={tryError} />}
      </Card>

      <Modal
        title="New unit"
        open={unitOpen}
        onCancel={() => setUnitOpen(false)}
        onOk={() => unitForm.submit()}
        confirmLoading={saveUnit.isPending}
      >
        <Form
          form={unitForm}
          layout="vertical"
          onFinish={(v) => saveUnit.mutate(v)}
          initialValues={{ factor_to_base: 1, decimal_precision: 2, is_base: false }}
        >
          <Form.Item name="code" label="Code" rules={[{ required: true }]}>
            <Input placeholder="YD" />
          </Form.Item>
          <Form.Item name="name" label="Name" rules={[{ required: true }]}>
            <Input placeholder="Yard" />
          </Form.Item>
          <Form.Item name="symbol" label="Symbol">
            <Input placeholder="yd" />
          </Form.Item>
          <Form.Item name="category_id" label="What it measures" rules={[{ required: true }]}>
            <Select options={categories?.map((c) => ({ value: c.id, label: c.name }))} />
          </Form.Item>
          <Form.Item
            name="factor_to_base"
            label="How many base units is one of these?"
            tooltip="A yard is 0.9144 metres, so enter 0.9144. Every conversion in this category is worked out from this number."
            rules={[{ required: true }]}
          >
            <InputNumber min={0.0000000001} step={0.1} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="decimal_precision" label="Decimal places to show">
            <InputNumber min={0} max={4} style={{ width: "100%" }} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="New category"
        open={categoryOpen}
        onCancel={() => setCategoryOpen(false)}
        onOk={() => categoryForm.submit()}
        confirmLoading={saveCategory.isPending}
      >
        <Typography.Paragraph type="secondary">
          A category groups units that measure the same thing. After creating one, add its base unit
          first &mdash; every other unit's factor is relative to it.
        </Typography.Paragraph>
        <Form form={categoryForm} layout="vertical" onFinish={(v) => saveCategory.mutate(v)}>
          <Form.Item name="code" label="Code" rules={[{ required: true }]}>
            <Input placeholder="AREA" />
          </Form.Item>
          <Form.Item name="name" label="Name" rules={[{ required: true }]}>
            <Input placeholder="Area" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
