import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Button,
  Card,
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
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { createBom, listBoms, listItems, listUoms } from "../api/endpoints";
import type { Bom } from "../api/types";

/** Only manufactured things can have a recipe. A raw material has no BOM by
 *  definition, and offering it in the picker just invites a confusing error. */
const MANUFACTURABLE = ["finished_product", "semi_finished"];

export default function Boms() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [creating, setCreating] = useState(false);
  const [form] = Form.useForm();

  const { data: boms, isLoading } = useQuery({
    queryKey: ["boms", search],
    queryFn: () => listBoms({ q: search.trim() || undefined }).then((r) => r.data),
  });

  const { data: items } = useQuery({
    queryKey: ["items-manufacturable"],
    queryFn: () => listItems({ is_active: true }).then((r) => r.data),
    enabled: creating,
  });
  const { data: uoms } = useQuery({
    queryKey: ["uoms"],
    queryFn: () => listUoms().then((r) => r.data),
    enabled: creating,
  });

  // An item may only have one BOM (uq_bom_tenant_item), so anything that already
  // has one is filtered out rather than offered and then rejected with a 409.
  const withBom = useMemo(() => new Set((boms ?? []).map((b) => b.item_id)), [boms]);
  const options = useMemo(
    () =>
      (items ?? [])
        .filter((i) => MANUFACTURABLE.includes(i.item_type) && !withBom.has(i.id))
        .map((i) => ({
          value: i.id,
          label: `${i.display_name || i.name || i.sku} — ${i.sku}`,
        })),
    [items, withBom],
  );

  const create = useMutation({
    mutationFn: (values: any) =>
      createBom({
        item_id: values.item_id,
        name: values.name,
        output_quantity: values.output_quantity ?? 1,
        output_uom_id: values.output_uom_id ?? null,
      }),
    onSuccess: (r) => {
      message.success("Bill of materials created — add its components next");
      queryClient.invalidateQueries({ queryKey: ["boms"] });
      setCreating(false);
      form.resetFields();
      navigate(`/boms/${r.data.id}`);
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || "Could not create the BOM"),
  });

  const columns = [
    {
      title: "Produces",
      key: "item",
      render: (_: unknown, r: Bom) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>{r.item_name ?? r.name}</Typography.Text>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            <code>{r.item_sku}</code>
          </Typography.Text>
        </Space>
      ),
    },
    { title: "Name", dataIndex: "name" },
    {
      title: "Active version",
      key: "active",
      width: 150,
      render: (_: unknown, r: Bom) =>
        r.active_version_no ? (
          <Tag color="green">V{r.active_version_no}</Tag>
        ) : (
          <Tag color="gold">draft only</Tag>
        ),
    },
    {
      title: "Versions",
      dataIndex: "version_count",
      width: 100,
      align: "right" as const,
    },
    {
      title: "",
      key: "actions",
      width: 90,
      render: (_: unknown, r: Bom) => (
        <Button size="small" type="primary" ghost onClick={() => navigate(`/boms/${r.id}`)}>
          Open
        </Button>
      ),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16, width: "100%", justifyContent: "space-between" }} wrap>
        <Typography.Title level={3} style={{ margin: 0 }}>
          Bills of Materials
        </Typography.Title>
        <Space>
          <Input.Search
            allowClear
            placeholder="Search by product or SKU"
            style={{ width: 260 }}
            onSearch={setSearch}
            onChange={(e) => !e.target.value && setSearch("")}
          />
          <Button type="primary" onClick={() => setCreating(true)}>
            New BOM
          </Button>
        </Space>
      </Space>

      <Card size="small" styles={{ body: { padding: 0 } }}>
        <Table
          rowKey="id"
          loading={isLoading}
          columns={columns}
          dataSource={boms}
          pagination={{ pageSize: 20, showSizeChanger: true }}
          scroll={{ x: "max-content" }}
          onRow={(r) => ({ onDoubleClick: () => navigate(`/boms/${r.id}`) })}
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="No bills of materials yet. Create one for a garment you manufacture."
              />
            ),
          }}
        />
      </Card>

      <Modal
        title="New bill of materials"
        open={creating}
        onCancel={() => setCreating(false)}
        onOk={() => form.submit()}
        confirmLoading={create.isPending}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={(v) => create.mutate(v)}
          initialValues={{ output_quantity: 1 }}
        >
          <Form.Item
            name="item_id"
            label="What does this recipe produce?"
            rules={[{ required: true, message: "Choose the item this BOM makes" }]}
            extra="Only finished and semi-finished items appear here, and only if they don't already have a BOM."
          >
            <Select
              showSearch
              optionFilterProp="label"
              placeholder="Search a garment or sub-assembly"
              options={options}
              onChange={(id) => {
                const item = items?.find((i) => i.id === id);
                if (item && !form.getFieldValue("name")) {
                  form.setFieldsValue({
                    name: `${item.display_name || item.name || item.sku} BOM`,
                    output_uom_id: item.stock_uom_id ?? undefined,
                  });
                }
              }}
            />
          </Form.Item>
          <Form.Item name="name" label="BOM name" rules={[{ required: true }]}>
            <Input placeholder="Designer Lehenga BOM" />
          </Form.Item>
          <Space>
            <Form.Item
              name="output_quantity"
              label="One batch makes"
              tooltip="Usually 1. Set higher when the recipe naturally yields several, e.g. 2 panels per cut."
            >
              <InputNumber min={0.0001} step={1} style={{ width: 160 }} />
            </Form.Item>
            <Form.Item name="output_uom_id" label="Unit">
              <Select
                style={{ width: 140 }}
                showSearch
                optionFilterProp="label"
                options={(uoms ?? []).map((u) => ({ value: u.id, label: u.code }))}
              />
            </Form.Item>
          </Space>
        </Form>
      </Modal>
    </div>
  );
}
