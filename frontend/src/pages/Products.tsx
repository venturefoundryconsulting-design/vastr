import {
  DeleteOutlined,
  DownloadOutlined,
  EditOutlined,
  ImportOutlined,
  PictureOutlined,
  PlusOutlined,
  PrinterOutlined,
  StarFilled,
  StarOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Avatar,
  Button,
  Empty,
  Form,
  Image,
  Input,
  InputNumber,
  List,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
  Upload,
  message,
} from "antd";
import { useState } from "react";
import {
  addVariant,
  bulkImportProducts,
  bulkImportTemplateUrl,
  createCategory,
  createProduct,
  deleteProductImage,
  getProduct,
  listCategories,
  listProducts,
  printLabels,
  productImageUrl,
  updateProduct,
  updateProductImage,
  updateVariant,
  uploadProductImage,
} from "../api/endpoints";
import type { BulkImportResult, ImageAngle, Product, ProductImage } from "../api/types";
import { useAuth } from "../context/AuthContext";
import { hasMinRole } from "../utils/roles";
import ExportButton from "../components/ExportButton";

const ANGLE_OPTIONS: { value: ImageAngle; label: string }[] = [
  { value: "front", label: "Front" },
  { value: "back", label: "Back" },
  { value: "side", label: "Side" },
  { value: "detail", label: "Detail / zoom" },
  { value: "other", label: "Other" },
];

function ProductImagesModal({ product, onClose }: { product: Product; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [color, setColor] = useState<string | undefined>();
  const [angle, setAngle] = useState<ImageAngle>("front");

  const { data: current } = useQuery({
    queryKey: ["product", product.id],
    queryFn: () => getProduct(product.id).then((r) => r.data),
    initialData: product,
  });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["product", product.id] });
    queryClient.invalidateQueries({ queryKey: ["products"] });
  };

  const uploadMutation = useMutation({
    mutationFn: (file: File) => uploadProductImage(product.id, file, { color, angle }),
    onSuccess: () => invalidate(),
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to upload image"),
  });

  const setPrimaryMutation = useMutation({
    mutationFn: (imageId: number) => updateProductImage(imageId, { is_primary: true }),
    onSuccess: () => invalidate(),
  });

  const deleteMutation = useMutation({
    mutationFn: (imageId: number) => deleteProductImage(imageId),
    onSuccess: () => invalidate(),
  });

  const colorOptions = Array.from(new Set(product.variants.map((v) => v.color).filter(Boolean))) as string[];
  const images = current?.images ?? [];
  const groups = new Map<string, ProductImage[]>();
  for (const img of images) {
    const key = img.color || "General";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(img);
  }

  return (
    <Modal title={`Photos — ${product.name}`} open onCancel={onClose} footer={null} width={760}>
      <Space wrap style={{ marginBottom: 16 }}>
        <Select
          placeholder="Color (optional)"
          allowClear
          showSearch
          style={{ width: 160 }}
          value={color}
          onChange={setColor}
          options={colorOptions.map((c) => ({ value: c, label: c }))}
        />
        <Select
          value={angle}
          onChange={setAngle}
          style={{ width: 160 }}
          options={ANGLE_OPTIONS}
        />
        <Upload
          showUploadList={false}
          accept="image/jpeg,image/png,image/webp"
          customRequest={({ file, onSuccess, onError }) => {
            uploadMutation.mutate(file as File, {
              onSuccess: () => onSuccess?.({}),
              onError: (err) => onError?.(err as Error),
            });
          }}
        >
          <Button icon={<UploadOutlined />} loading={uploadMutation.isPending} type="primary">
            Upload image
          </Button>
        </Upload>
      </Space>

      {images.length === 0 ? (
        <Empty description="No photos yet" />
      ) : (
        <Image.PreviewGroup>
          {Array.from(groups.entries()).map(([groupName, groupImages]) => (
            <div key={groupName} style={{ marginBottom: 20 }}>
              <Typography.Text strong>{groupName}</Typography.Text>
              <Space wrap style={{ marginTop: 8 }}>
                {groupImages.map((img) => (
                  <div
                    key={img.id}
                    style={{
                      position: "relative",
                      border: img.is_primary ? "2px solid #d4380d" : "1px solid #eee",
                      borderRadius: 8,
                      padding: 4,
                    }}
                  >
                    <Image src={productImageUrl(img.url)} width={110} height={110} style={{ objectFit: "cover", borderRadius: 4 }} />
                    <div style={{ marginTop: 4, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <Tag style={{ margin: 0 }}>{img.angle}</Tag>
                      <Space size={4}>
                        <Button
                          size="small"
                          type="text"
                          title={img.is_primary ? "Primary photo" : "Set as primary"}
                          icon={img.is_primary ? <StarFilled style={{ color: "#d4380d" }} /> : <StarOutlined />}
                          onClick={() => setPrimaryMutation.mutate(img.id)}
                          disabled={img.is_primary}
                        />
                        <Popconfirm title="Delete this photo?" onConfirm={() => deleteMutation.mutate(img.id)}>
                          <Button size="small" type="text" danger icon={<DeleteOutlined />} />
                        </Popconfirm>
                      </Space>
                    </div>
                  </div>
                ))}
              </Space>
            </div>
          ))}
        </Image.PreviewGroup>
      )}
    </Modal>
  );
}

function PrintLabelsModal({ product, onClose }: { product: Product; onClose: () => void }) {
  const [quantities, setQuantities] = useState<Record<number, number>>(
    Object.fromEntries(product.variants.map((v) => [v.id, 1]))
  );
  const [layout, setLayout] = useState<"thermal_50x25" | "a4_sheet">("thermal_50x25");

  const printMutation = useMutation({
    mutationFn: () =>
      printLabels({
        items: product.variants
          .filter((v) => (quantities[v.id] || 0) > 0)
          .map((v) => ({ variant_id: v.id, quantity: quantities[v.id] })),
        layout,
      }),
    onSuccess: (res) => {
      const url = window.URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      window.open(url, "_blank");
      onClose();
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to generate labels"),
  });

  const totalLabels = Object.values(quantities).reduce((sum, q) => sum + (q || 0), 0);

  return (
    <Modal
      title={`Print labels — ${product.name}`}
      open
      onCancel={onClose}
      onOk={() => printMutation.mutate()}
      okText={`Print ${totalLabels} label${totalLabels === 1 ? "" : "s"}`}
      okButtonProps={{ disabled: totalLabels === 0, loading: printMutation.isPending }}
      width={640}
    >
      <Select
        value={layout}
        onChange={setLayout}
        style={{ width: "100%", marginBottom: 16 }}
        options={[
          { value: "thermal_50x25", label: "Thermal roll — 50 × 25mm, one label per print" },
          { value: "a4_sheet", label: "A4 sheet — grid of labels to print on a regular printer" },
        ]}
      />
      <Table
        size="small"
        rowKey="id"
        pagination={false}
        dataSource={product.variants}
        columns={[
          {
            title: "Variant",
            key: "variant",
            render: (_: unknown, v: Product["variants"][number]) =>
              [v.color, v.size].filter(Boolean).join(" / ") || v.sku,
          },
          { title: "SKU", dataIndex: "sku" },
          { title: "MRP", dataIndex: "mrp", render: (v: number) => `₹${Number(v).toFixed(2)}` },
          {
            title: "Copies",
            key: "quantity",
            render: (_: unknown, v: Product["variants"][number]) => (
              <InputNumber
                min={0}
                value={quantities[v.id]}
                onChange={(val) => setQuantities((prev) => ({ ...prev, [v.id]: val || 0 }))}
              />
            ),
          },
        ]}
      />
    </Modal>
  );
}

function BulkImportModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [result, setResult] = useState<BulkImportResult | null>(null);

  const importMutation = useMutation({
    mutationFn: (file: File) => bulkImportProducts(file),
    onSuccess: (res) => {
      setResult(res.data);
      queryClient.invalidateQueries({ queryKey: ["products"] });
      queryClient.invalidateQueries({ queryKey: ["categories"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Import failed"),
  });

  return (
    <Modal title="Bulk Import Products" open onCancel={onClose} footer={null} width={560}>
      <Typography.Paragraph type="secondary">
        Upload a CSV or Excel file with columns: product_name, brand, category, hsn_code, tax_rate, sku,
        barcode, size, color, cost_price, selling_price, mrp, reorder_level. Rows sharing the same
        product_name + brand become variants of one product; SKUs that already exist are updated in place.
      </Typography.Paragraph>
      <Button icon={<DownloadOutlined />} href={bulkImportTemplateUrl()} style={{ marginBottom: 16 }}>
        Download template
      </Button>

      <Upload.Dragger
        accept=".csv,.xlsx"
        showUploadList={false}
        disabled={importMutation.isPending}
        customRequest={({ file, onSuccess, onError }) => {
          setResult(null);
          importMutation.mutate(file as File, {
            onSuccess: () => onSuccess?.({}),
            onError: (err) => onError?.(err as Error),
          });
        }}
      >
        <p className="ant-upload-drag-icon">
          <ImportOutlined />
        </p>
        <p className="ant-upload-text">
          {importMutation.isPending ? "Importing..." : "Click or drag a .csv / .xlsx file here"}
        </p>
      </Upload.Dragger>

      {result && (
        <div style={{ marginTop: 16 }}>
          <Alert
            type={result.errors.length ? "warning" : "success"}
            message={`${result.created_products} product(s) created, ${result.updated_products} updated · ${result.created_variants} variant(s) created, ${result.updated_variants} updated (${result.total_rows} row${result.total_rows === 1 ? "" : "s"} processed)`}
            showIcon
          />
          {result.errors.length > 0 && (
            <List
              size="small"
              style={{ marginTop: 8 }}
              header={<Typography.Text strong>Skipped rows</Typography.Text>}
              dataSource={result.errors}
              renderItem={(e) => (
                <List.Item>
                  Row {e.row}: {e.message}
                </List.Item>
              )}
            />
          )}
        </div>
      )}
    </Modal>
  );
}

export default function Products() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [labelProduct, setLabelProduct] = useState<Product | null>(null);
  const [imagesProduct, setImagesProduct] = useState<Product | null>(null);
  const [importModalOpen, setImportModalOpen] = useState(false);
  const [editingProduct, setEditingProduct] = useState<Product | null>(null);
  const [form] = Form.useForm();
  const [search, setSearch] = useState("");

  const { data: products, isLoading } = useQuery({
    queryKey: ["products", search],
    queryFn: () => listProducts(search ? { search } : undefined).then((r) => r.data),
  });

  const { data: categories } = useQuery({
    queryKey: ["categories"],
    queryFn: () => listCategories().then((r) => r.data),
  });

  const closeModal = () => {
    setModalOpen(false);
    setEditingProduct(null);
    form.resetFields();
  };

  const createMutation = useMutation({
    mutationFn: createProduct,
    onSuccess: () => {
      message.success("Product created");
      closeModal();
      queryClient.invalidateQueries({ queryKey: ["products"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to create product"),
  });

  const quickCreateCategory = async (name: string) => {
    const res = await createCategory({ name });
    queryClient.invalidateQueries({ queryKey: ["categories"] });
    return res.data;
  };

  const updateMutation = useMutation({
    mutationFn: async (values: any) => {
      const productId = editingProduct!.id;
      await updateProduct(productId, {
        name: values.name,
        brand: values.brand,
        tax_rate: values.tax_rate,
        category_id: values.category_id,
        hsn_code: values.hsn_code,
        description: values.description,
      });
      for (const v of values.variants || []) {
        const payload = {
          sku: v.sku,
          barcode: v.barcode,
          color: v.color,
          size: v.size,
          cost_price: v.cost_price,
          selling_price: v.selling_price,
          mrp: v.mrp,
          reorder_level: v.reorder_level,
        };
        if (v.id) {
          await updateVariant(v.id, { ...payload, is_active: v.is_active });
        } else {
          await addVariant(productId, payload);
        }
      }
    },
    onSuccess: () => {
      message.success("Product updated");
      closeModal();
      queryClient.invalidateQueries({ queryKey: ["products"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to update product"),
  });

  const openEdit = (product: Product) => {
    setEditingProduct(product);
    form.setFieldsValue({
      name: product.name,
      brand: product.brand,
      tax_rate: product.tax_rate,
      category_id: product.category_id,
      hsn_code: product.hsn_code,
      description: product.description,
      variants: product.variants,
    });
    setModalOpen(true);
  };

  const columns = [
    {
      title: "",
      key: "photo",
      width: 56,
      render: (_: unknown, record: Product) => {
        const primary = record.images.find((i) => i.is_primary) || record.images[0];
        return primary ? (
          <Avatar shape="square" size={40} src={productImageUrl(primary.url)} />
        ) : (
          <Avatar shape="square" size={40} icon={<PictureOutlined />} />
        );
      },
    },
    { title: "Product", dataIndex: "name" },
    { title: "Brand", dataIndex: "brand" },
    { title: "Tax %", dataIndex: "tax_rate", width: 80 },
    {
      title: "Variants",
      key: "variants",
      render: (_: unknown, record: Product) => (
        <Space wrap>
          {record.variants.map((v) => (
            <Tag key={v.id}>
              {[v.color, v.size].filter(Boolean).join(" / ") || v.sku} · ₹{v.selling_price}
            </Tag>
          ))}
        </Space>
      ),
    },
    {
      title: "",
      key: "actions",
      render: (_: unknown, record: Product) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>
            Edit
          </Button>
          <Button size="small" icon={<PictureOutlined />} onClick={() => setImagesProduct(record)}>
            Photos
          </Button>
          <Button
            size="small"
            icon={<PrinterOutlined />}
            disabled={!record.variants.length}
            onClick={() => setLabelProduct(record)}
          >
            Print labels
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16, width: "100%", justifyContent: "space-between" }}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          Products
        </Typography.Title>
        <Space>
          <Input.Search
            placeholder="Search products..."
            allowClear
            onSearch={setSearch}
            style={{ width: 240 }}
          />
          <ExportButton url="/api/products/export" params={{ search }} filenameBase="products" />
          {hasMinRole(user?.role, "manager") && (
            <Button icon={<ImportOutlined />} onClick={() => setImportModalOpen(true)}>
              Bulk Import
            </Button>
          )}
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              setEditingProduct(null);
              form.resetFields();
              setModalOpen(true);
            }}
          >
            New Product
          </Button>
        </Space>
      </Space>

      <Table
        rowKey="id"
        sticky
        loading={isLoading}
        columns={columns}
        dataSource={products}
        pagination={{ pageSize: 15 }}
      />

      <Modal
        title={editingProduct ? `Edit Product — ${editingProduct.name}` : "New Product"}
        open={modalOpen}
        onCancel={closeModal}
        onOk={() => form.submit()}
        confirmLoading={createMutation.isPending || updateMutation.isPending}
        width={720}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={(values) =>
            editingProduct ? updateMutation.mutate(values) : createMutation.mutate(values)
          }
          initialValues={{ tax_rate: 5, variants: [{}] }}
        >
          <Space style={{ width: "100%" }} size="large">
            <Form.Item name="name" label="Product name" rules={[{ required: true }]} style={{ width: 260 }}>
              <Input placeholder="e.g. Banarasi Silk Saree" />
            </Form.Item>
            <Form.Item name="brand" label="Brand" style={{ width: 160 }}>
              <Input />
            </Form.Item>
            <Form.Item name="tax_rate" label="Tax %" style={{ width: 100 }}>
              <InputNumber min={0} max={28} style={{ width: "100%" }} />
            </Form.Item>
          </Space>
          <Space style={{ width: "100%" }} size="large">
            <Form.Item name="category_id" label="Category" style={{ width: 260 }}>
              <Select
                allowClear
                placeholder="Select category"
                options={categories?.map((c) => ({ value: c.id, label: c.name }))}
                dropdownRender={(menu) => (
                  <>
                    {menu}
                    <div style={{ display: "flex", padding: 8, gap: 8 }}>
                      <Input
                        placeholder="New category"
                        onKeyDown={(e) => e.stopPropagation()}
                        id="new-category-input"
                      />
                      <Button
                        onClick={async () => {
                          const el = document.getElementById("new-category-input") as HTMLInputElement;
                          if (el?.value) await quickCreateCategory(el.value);
                          el.value = "";
                        }}
                      >
                        Add
                      </Button>
                    </div>
                  </>
                )}
              />
            </Form.Item>
            <Form.Item name="hsn_code" label="HSN Code" style={{ width: 160 }}>
              <Input />
            </Form.Item>
          </Space>
          <Form.Item name="description" label="Description">
            <Input.TextArea rows={2} />
          </Form.Item>

          <Typography.Title level={5}>Variants (size / color)</Typography.Title>
          <Form.List name="variants">
            {(fields, { add, remove }) => (
              <>
                {fields.map((field) => {
                  const isExisting = !!editingProduct && field.name < editingProduct.variants.length;
                  return (
                    <Space key={field.key} align="baseline" wrap style={{ marginBottom: 8 }}>
                      <Form.Item name={[field.name, "id"]} hidden>
                        <Input />
                      </Form.Item>
                      <Form.Item name={[field.name, "sku"]} rules={[{ required: true, message: "SKU" }]}>
                        <Input placeholder="SKU" style={{ width: 140 }} />
                      </Form.Item>
                      <Form.Item name={[field.name, "barcode"]}>
                        <Input placeholder="Barcode" style={{ width: 140 }} />
                      </Form.Item>
                      <Form.Item name={[field.name, "color"]}>
                        <Input placeholder="Color" style={{ width: 100 }} />
                      </Form.Item>
                      <Form.Item name={[field.name, "size"]}>
                        <Input placeholder="Size" style={{ width: 90 }} />
                      </Form.Item>
                      <Form.Item name={[field.name, "cost_price"]}>
                        <InputNumber placeholder="Cost" style={{ width: 100 }} />
                      </Form.Item>
                      <Form.Item name={[field.name, "selling_price"]}>
                        <InputNumber placeholder="Selling" style={{ width: 100 }} />
                      </Form.Item>
                      <Form.Item name={[field.name, "mrp"]}>
                        <InputNumber placeholder="MRP" style={{ width: 100 }} />
                      </Form.Item>
                      <Form.Item name={[field.name, "reorder_level"]} initialValue={5}>
                        <InputNumber placeholder="Reorder lvl" style={{ width: 110 }} />
                      </Form.Item>
                      {isExisting ? (
                        <Form.Item
                          name={[field.name, "is_active"]}
                          valuePropName="checked"
                          initialValue={true}
                          tooltip="Deactivate instead of deleting — keeps sales history intact"
                        >
                          <Switch checkedChildren="Active" unCheckedChildren="Inactive" />
                        </Form.Item>
                      ) : (
                        fields.length > 1 && (
                          <Button danger onClick={() => remove(field.name)}>
                            Remove
                          </Button>
                        )
                      )}
                    </Space>
                  );
                })}
                <Button onClick={() => add()} icon={<PlusOutlined />}>
                  Add variant
                </Button>
              </>
            )}
          </Form.List>
        </Form>
      </Modal>

      {labelProduct && <PrintLabelsModal product={labelProduct} onClose={() => setLabelProduct(null)} />}
      {imagesProduct && (
        <ProductImagesModal product={imagesProduct} onClose={() => setImagesProduct(null)} />
      )}
      {importModalOpen && <BulkImportModal onClose={() => setImportModalOpen(false)} />}
    </div>
  );
}
