import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Button,
  Drawer,
  Form,
  Input,
  InputNumber,
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
  createItem,
  listItems,
  listUoms,
  updateItem,
} from "../api/endpoints";
import { listCategories } from "../api/endpoints";
import type { Item, ItemType } from "../api/types";
import ExportButton from "../components/ExportButton";
import { formatQty, qtyInputProps } from "../utils/quantity";

/** Item types, with the colour and the field behaviour each implies.
 *
 * `stocked`/`purchasable`/`sellable` here are the *defaults* the form applies
 * when the type is chosen - the user can still override any of them, because
 * real catalogues always have an exception (a service you resell, a packaging
 * item you also sell). They also drive which sections of the form are shown at
 * all, so a service item is not asked for a reorder level it will never use.
 */
const ITEM_TYPES: Record<
  ItemType,
  { label: string; color: string; stocked: boolean; purchasable: boolean; sellable: boolean }
> = {
  raw_material: { label: "Raw material", color: "purple", stocked: true, purchasable: true, sellable: false },
  semi_finished: { label: "Semi-finished", color: "geekblue", stocked: true, purchasable: false, sellable: false },
  finished_product: { label: "Finished product", color: "green", stocked: true, purchasable: true, sellable: true },
  packaging: { label: "Packaging", color: "orange", stocked: true, purchasable: true, sellable: false },
  service: { label: "Service", color: "default", stocked: false, purchasable: false, sellable: false },
};

export default function Items() {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<Item | null>(null);
  const [creating, setCreating] = useState(false);
  const [form] = Form.useForm();

  const [typeFilter, setTypeFilter] = useState<ItemType | undefined>();
  const [categoryFilter, setCategoryFilter] = useState<number | undefined>();
  const [activeFilter, setActiveFilter] = useState<boolean | undefined>();
  const [lowStock, setLowStock] = useState(false);
  const [search, setSearch] = useState("");

  // Watched so the form can adapt as the type changes, before anything is saved.
  const selectedType: ItemType = Form.useWatch("item_type", form) ?? "finished_product";
  const behaviour = ITEM_TYPES[selectedType] ?? ITEM_TYPES.finished_product;

  const { data: items, isLoading } = useQuery({
    queryKey: ["items", typeFilter, categoryFilter, activeFilter, lowStock, search],
    queryFn: () =>
      listItems({
        item_type: typeFilter,
        category_id: categoryFilter,
        is_active: activeFilter,
        low_stock: lowStock || undefined,
        q: search.trim() || undefined,
      }).then((r) => r.data),
  });
  const { data: uoms } = useQuery({ queryKey: ["uoms"], queryFn: () => listUoms().then((r) => r.data) });
  const { data: categories } = useQuery({
    queryKey: ["categories"],
    queryFn: () => listCategories().then((r) => r.data),
  });

  const uomOptions = useMemo(
    () => (uoms ?? []).filter((u) => u.is_active).map((u) => ({ value: u.id, label: `${u.name} (${u.code})` })),
    [uoms],
  );

  const close = () => {
    setEditing(null);
    setCreating(false);
    form.resetFields();
  };

  const save = useMutation({
    mutationFn: (values: Partial<Item>) =>
      editing ? updateItem(editing.id, values) : createItem(values),
    onSuccess: () => {
      message.success(editing ? "Item updated" : "Item created");
      queryClient.invalidateQueries({ queryKey: ["items"] });
      close();
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Could not save the item"),
  });

  const openCreate = () => {
    setEditing(null);
    setCreating(true);
    form.setFieldsValue({
      item_type: "finished_product",
      is_active: true,
      ...ITEM_TYPES.finished_product,
      is_sellable: true,
      is_purchasable: true,
      is_stocked: true,
      tax_rate: 0,
      cost_price: 0,
      selling_price: 0,
      mrp: 0,
      reorder_level: 0,
      min_stock: 0,
    });
  };

  const openEdit = (item: Item) => {
    setCreating(false);
    setEditing(item);
    form.setFieldsValue(item);
  };

  /** Applying a type resets the three behaviour flags to that type's defaults -
   * switching an item to "service" should not leave it flagged as stocked. */
  const onTypeChange = (value: ItemType) => {
    const d = ITEM_TYPES[value];
    form.setFieldsValue({ is_stocked: d.stocked, is_purchasable: d.purchasable, is_sellable: d.sellable });
  };

  const columns = [
    { title: "SKU", dataIndex: "sku", width: 160, render: (v: string) => <code>{v}</code> },
    {
      title: "Item",
      key: "name",
      render: (_: unknown, r: Item) => r.display_name || r.name || r.product_name || "-",
    },
    {
      title: "Type",
      dataIndex: "item_type",
      width: 150,
      render: (t: ItemType) => <Tag color={ITEM_TYPES[t]?.color}>{ITEM_TYPES[t]?.label ?? t}</Tag>,
    },
    { title: "Category", dataIndex: "category_name", width: 130 },
    {
      title: "Stock",
      key: "stock",
      width: 130,
      align: "right" as const,
      render: (_: unknown, r: Item) =>
        r.is_stocked ? (
          <Tag color={r.total_stock <= r.reorder_level ? "red" : "green"}>
            {formatQty(r.total_stock)} {r.stock_uom_code ?? ""}
          </Tag>
        ) : (
          <Typography.Text type="secondary">n/a</Typography.Text>
        ),
    },
    {
      title: "Cost",
      dataIndex: "cost_price",
      width: 110,
      align: "right" as const,
      render: (v: number) => `₹${Number(v).toFixed(2)}`,
    },
    {
      title: "",
      key: "actions",
      width: 80,
      render: (_: unknown, r: Item) => (
        <Button size="small" onClick={() => openEdit(r)}>
          Edit
        </Button>
      ),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16, width: "100%", justifyContent: "space-between" }} wrap>
        <Typography.Title level={3} style={{ margin: 0 }}>
          Item Master
        </Typography.Title>
        <Space wrap>
          <ExportButton url="/api/items/export" params={{ item_type: typeFilter }} filenameBase="items" />
          <Button type="primary" onClick={openCreate}>
            New item
          </Button>
        </Space>
      </Space>

      <Space style={{ marginBottom: 16 }} wrap>
        <Input.Search
          allowClear
          placeholder="Search SKU, barcode or name"
          style={{ width: 280 }}
          onSearch={setSearch}
          onChange={(e) => !e.target.value && setSearch("")}
        />
        <Select
          allowClear
          placeholder="All item types"
          style={{ width: 190 }}
          value={typeFilter}
          onChange={setTypeFilter}
          options={Object.entries(ITEM_TYPES).map(([v, c]) => ({ value: v, label: c.label }))}
        />
        <Select
          allowClear
          placeholder="All categories"
          style={{ width: 180 }}
          value={categoryFilter}
          onChange={setCategoryFilter}
          options={categories?.map((c) => ({ value: c.id, label: c.name }))}
        />
        <Select
          allowClear
          placeholder="Active & inactive"
          style={{ width: 170 }}
          value={activeFilter}
          onChange={setActiveFilter}
          options={[
            { value: true, label: "Active only" },
            { value: false, label: "Inactive only" },
          ]}
        />
        <Button type={lowStock ? "primary" : "default"} danger={lowStock} onClick={() => setLowStock((v) => !v)}>
          Low stock
        </Button>
      </Space>

      <Table
        rowKey="id"
        sticky
        loading={isLoading}
        columns={columns}
        dataSource={items}
        pagination={{ pageSize: 25, showSizeChanger: true }}
        scroll={{ x: "max-content" }}
      />

      <Drawer
        title={editing ? `Edit ${editing.sku}` : "New item"}
        open={creating || !!editing}
        onClose={close}
        width={560}
        extra={
          <Space>
            <Button onClick={close}>Cancel</Button>
            <Button type="primary" loading={save.isPending} onClick={() => form.submit()}>
              Save
            </Button>
          </Space>
        }
      >
        <Form form={form} layout="vertical" onFinish={(v) => save.mutate(v)}>
          <Form.Item name="item_type" label="Item type" rules={[{ required: true }]}>
            <Select
              onChange={onTypeChange}
              options={Object.entries(ITEM_TYPES).map(([v, c]) => ({ value: v, label: c.label }))}
            />
          </Form.Item>

          <Form.Item name="sku" label="SKU" rules={[{ required: true, message: "An SKU is required" }]}>
            <Input placeholder="FAB-SLK-RED-001" disabled={!!editing} />
          </Form.Item>
          {editing && (
            <Typography.Paragraph type="secondary" style={{ marginTop: -12, fontSize: 12 }}>
              SKUs can't be changed once stock and sales reference them.
            </Typography.Paragraph>
          )}

          <Form.Item name="name" label="Name" rules={[{ required: true }]}>
            <Input placeholder="Gold Lace 2 inch" />
          </Form.Item>
          <Form.Item name="category_id" label="Category">
            <Select allowClear options={categories?.map((c) => ({ value: c.id, label: c.name }))} />
          </Form.Item>
          <Form.Item name="brand" label="Brand">
            <Input />
          </Form.Item>
          <Form.Item name="barcode" label="Barcode">
            <Input placeholder="Scan or type" />
          </Form.Item>

          {behaviour.stocked && (
            <>
              <Form.Item name="stock_uom_id" label="Stock unit" tooltip="The unit inventory is held in. Every ledger entry uses this.">
                <Select showSearch optionFilterProp="label" options={uomOptions} />
              </Form.Item>
              <Form.Item name="reorder_level" label="Reorder level">
                <InputNumber {...qtyInputProps} min={0} style={{ width: "100%" }} />
              </Form.Item>
              <Form.Item name="min_stock" label="Minimum stock">
                <InputNumber {...qtyInputProps} min={0} style={{ width: "100%" }} />
              </Form.Item>
            </>
          )}

          {behaviour.purchasable && (
            <Form.Item
              name="purchase_uom_id"
              label="Purchase unit"
              tooltip="What vendors sell in. If it differs from the stock unit, add a conversion on the item."
            >
              <Select showSearch optionFilterProp="label" allowClear options={uomOptions} />
            </Form.Item>
          )}

          {behaviour.sellable && (
            <>
              <Form.Item name="sales_uom_id" label="Sales unit">
                <Select showSearch optionFilterProp="label" allowClear options={uomOptions} />
              </Form.Item>
              <Form.Item name="selling_price" label="Selling price">
                <InputNumber min={0} step={1} precision={2} prefix="₹" style={{ width: "100%" }} />
              </Form.Item>
              <Form.Item name="mrp" label="MRP">
                <InputNumber min={0} step={1} precision={2} prefix="₹" style={{ width: "100%" }} />
              </Form.Item>
            </>
          )}

          <Form.Item name="cost_price" label="Cost price">
            <InputNumber min={0} step={1} precision={2} prefix="₹" style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="tax_rate" label="Tax %">
            <InputNumber min={0} max={100} step={1} precision={2} style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="hsn_code" label="HSN / SAC">
            <Input />
          </Form.Item>
          <Form.Item name="notes" label="Notes">
            <Input.TextArea rows={2} />
          </Form.Item>

          <Space size="large" wrap>
            <Form.Item name="is_stocked" label="Tracked in stock" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item name="is_purchasable" label="Purchasable" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item name="is_sellable" label="Sellable in POS" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item name="is_active" label="Active" valuePropName="checked">
              <Switch />
            </Form.Item>
          </Space>
        </Form>
      </Drawer>
    </div>
  );
}
