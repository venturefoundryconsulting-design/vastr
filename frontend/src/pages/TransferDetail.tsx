import { EditOutlined, InboxOutlined, PlusOutlined, PrinterOutlined, SendOutlined, StopOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Button,
  Card,
  Descriptions,
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
import { useParams } from "react-router-dom";
import { apiClient } from "../api/client";
import {
  cancelTransfer,
  dispatchTransfer,
  getTransfer,
  listOutlets,
  receiveTransfer,
  searchVariants,
  updateTransfer,
} from "../api/endpoints";
import type { VariantWithStock } from "../api/types";

export default function TransferDetail() {
  const { id } = useParams();
  const transferId = Number(id);
  const queryClient = useQueryClient();
  const [dispatchOpen, setDispatchOpen] = useState(false);
  const [receiveOpen, setReceiveOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [editOptions, setEditOptions] = useState<VariantWithStock[]>([]);
  const [dispatchForm] = Form.useForm();
  const [receiveForm] = Form.useForm();
  const [editForm] = Form.useForm();

  const { data: transfer, isLoading } = useQuery({
    queryKey: ["transfer", transferId],
    queryFn: () => getTransfer(transferId).then((r) => r.data),
  });

  const { data: outlets } = useQuery({ queryKey: ["outlets"], queryFn: () => listOutlets().then((r) => r.data) });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["transfer", transferId] });
    queryClient.invalidateQueries({ queryKey: ["transfers"] });
    queryClient.invalidateQueries({ queryKey: ["stock"] });
  };

  const dispatchMutation = useMutation({
    mutationFn: (items: { item_id: number; quantity_sent: number }[]) => dispatchTransfer(transferId, items),
    onSuccess: () => {
      message.success("Transfer dispatched, stock deducted from source outlet");
      setDispatchOpen(false);
      invalidate();
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to dispatch"),
  });

  const receiveMutation = useMutation({
    mutationFn: (items: { item_id: number; quantity_received: number }[]) => receiveTransfer(transferId, items),
    onSuccess: () => {
      message.success("Transfer received, stock added to destination outlet");
      setReceiveOpen(false);
      invalidate();
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to receive"),
  });

  const updateMutation = useMutation({
    mutationFn: (data: Record<string, unknown>) => updateTransfer(transferId, data),
    onSuccess: () => {
      message.success("Transfer updated");
      setEditOpen(false);
      invalidate();
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to update transfer"),
  });

  const cancelMutation = useMutation({
    mutationFn: () => cancelTransfer(transferId),
    onSuccess: () => {
      message.success("Transfer cancelled");
      invalidate();
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to cancel transfer"),
  });

  const openEdit = () => {
    if (!transfer) return;
    setEditOptions(
      transfer.items.map((i) => ({
        id: i.variant_id,
        sku: i.sku ?? "",
        product_name: i.product_name ?? "",
      })) as VariantWithStock[]
    );
    editForm.setFieldsValue({
      source_outlet_id: transfer.source_outlet_id,
      dest_outlet_id: transfer.dest_outlet_id,
      notes: transfer.notes,
      items: transfer.items.map((i) => ({
        variant_id: i.variant_id,
        quantity_requested: i.quantity_requested,
      })),
    });
    setEditOpen(true);
  };

  const handleEditSearch = async (q: string) => {
    if (!q) return;
    const res = await searchVariants(q);
    setEditOptions((prev) => [...prev, ...res.data]);
  };

  const printTransfer = async () => {
    const res = await apiClient.get(`/api/transfers/${transferId}/pdf`, { responseType: "blob" });
    const url = window.URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
    window.open(url, "_blank");
  };

  if (isLoading || !transfer) return null;

  return (
    <div>
      <Space style={{ marginBottom: 16, width: "100%", justifyContent: "space-between" }}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          {transfer.transfer_number}
        </Typography.Title>
        <Space>
          <Button icon={<PrinterOutlined />} onClick={printTransfer}>
            Print
          </Button>
          {transfer.status === "requested" && (
            <>
              <Button icon={<EditOutlined />} onClick={openEdit}>
                Edit
              </Button>
              <Button
                danger
                icon={<StopOutlined />}
                loading={cancelMutation.isPending}
                onClick={() =>
                  Modal.confirm({
                    title: "Cancel this transfer?",
                    content: "This cannot be undone. No stock has moved yet, so nothing needs to be reversed.",
                    okText: "Cancel transfer",
                    okButtonProps: { danger: true },
                    onOk: () => cancelMutation.mutate(),
                  })
                }
              >
                Cancel
              </Button>
              <Button type="primary" icon={<SendOutlined />} onClick={() => setDispatchOpen(true)}>
                Dispatch
              </Button>
            </>
          )}
          {transfer.status === "dispatched" && (
            <Button type="primary" icon={<InboxOutlined />} onClick={() => setReceiveOpen(true)}>
              Receive
            </Button>
          )}
        </Space>
      </Space>

      <Card style={{ marginBottom: 16 }}>
        <Descriptions column={3}>
          <Descriptions.Item label="From">{transfer.source_outlet_name}</Descriptions.Item>
          <Descriptions.Item label="To">{transfer.dest_outlet_name}</Descriptions.Item>
          <Descriptions.Item label="Status">
            <Tag>{transfer.status}</Tag>
          </Descriptions.Item>
          {transfer.notes && <Descriptions.Item label="Notes" span={3}>{transfer.notes}</Descriptions.Item>}
        </Descriptions>
      </Card>

      <Table
        rowKey="id"
        dataSource={transfer.items}
        pagination={false}
        columns={[
          { title: "SKU", dataIndex: "sku" },
          { title: "Item", dataIndex: "product_name" },
          { title: "Requested", dataIndex: "quantity_requested" },
          { title: "Sent", dataIndex: "quantity_sent" },
          { title: "Received", dataIndex: "quantity_received" },
        ]}
      />

      <Modal
        title="Dispatch Transfer"
        open={dispatchOpen}
        onCancel={() => setDispatchOpen(false)}
        onOk={() => dispatchForm.submit()}
        confirmLoading={dispatchMutation.isPending}
      >
        <Form
          form={dispatchForm}
          layout="vertical"
          onFinish={(values) => {
            const items = transfer.items.map((item) => ({
              item_id: item.id,
              quantity_sent: values[`item_${item.id}`] || 0,
            }));
            dispatchMutation.mutate(items.filter((i) => i.quantity_sent > 0));
          }}
        >
          {transfer.items.map((item) => (
            <Form.Item
              key={item.id}
              name={`item_${item.id}`}
              label={`${item.product_name} (${item.sku}) - requested ${item.quantity_requested}`}
              initialValue={item.quantity_requested}
            >
              <InputNumber min={0} style={{ width: "100%" }} />
            </Form.Item>
          ))}
        </Form>
      </Modal>

      <Modal
        title="Receive Transfer"
        open={receiveOpen}
        onCancel={() => setReceiveOpen(false)}
        onOk={() => receiveForm.submit()}
        confirmLoading={receiveMutation.isPending}
      >
        <Form
          form={receiveForm}
          layout="vertical"
          onFinish={(values) => {
            const items = transfer.items.map((item) => ({
              item_id: item.id,
              quantity_received: values[`item_${item.id}`] || 0,
            }));
            receiveMutation.mutate(items.filter((i) => i.quantity_received > 0));
          }}
        >
          {transfer.items.map((item) => (
            <Form.Item
              key={item.id}
              name={`item_${item.id}`}
              label={`${item.product_name} (${item.sku}) - sent ${item.quantity_sent}, remaining ${
                item.quantity_sent - item.quantity_received
              }`}
              initialValue={item.quantity_sent - item.quantity_received}
            >
              <InputNumber min={0} max={item.quantity_sent - item.quantity_received} style={{ width: "100%" }} />
            </Form.Item>
          ))}
        </Form>
      </Modal>

      <Modal
        title="Edit Transfer"
        open={editOpen}
        onCancel={() => setEditOpen(false)}
        onOk={() => editForm.submit()}
        confirmLoading={updateMutation.isPending}
        width={720}
      >
        <Form
          form={editForm}
          layout="vertical"
          onFinish={(values) => updateMutation.mutate(values)}
        >
          <Space style={{ width: "100%" }} size="large">
            <Form.Item name="source_outlet_id" label="From" rules={[{ required: true }]} style={{ width: 260 }}>
              <Select options={outlets?.map((o) => ({ value: o.id, label: o.name }))} />
            </Form.Item>
            <Form.Item name="dest_outlet_id" label="To" rules={[{ required: true }]} style={{ width: 260 }}>
              <Select options={outlets?.map((o) => ({ value: o.id, label: o.name }))} />
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
                        style={{ width: 300 }}
                        filterOption={false}
                        onSearch={handleEditSearch}
                        options={editOptions.map((o) => ({
                          value: o.id,
                          label: `${o.product_name} - ${[o.color, o.size].filter(Boolean).join("/")} (${o.sku})`,
                        }))}
                      />
                    </Form.Item>
                    <Form.Item name={[field.name, "quantity_requested"]} rules={[{ required: true }]}>
                      <InputNumber placeholder="Qty" style={{ width: 100 }} />
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
