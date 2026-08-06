import { DownloadOutlined, InboxOutlined, WhatsAppOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Card, Descriptions, Form, InputNumber, Modal, Space, Table, Tag, Typography, message } from "antd";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { apiClient } from "../api/client";
import { getPurchaseOrder, receiveGoods, sendPurchaseOrderWhatsApp } from "../api/endpoints";

export default function PurchaseOrderDetail() {
  const { id } = useParams();
  const poId = Number(id);
  const queryClient = useQueryClient();
  const [receiveOpen, setReceiveOpen] = useState(false);
  const [form] = Form.useForm();

  const { data: po, isLoading } = useQuery({
    queryKey: ["purchase-order", poId],
    queryFn: () => getPurchaseOrder(poId).then((r) => r.data),
  });

  const sendMutation = useMutation({
    mutationFn: () => sendPurchaseOrderWhatsApp(poId),
    onSuccess: (res) => {
      message.success(res.data.note);
      window.open(res.data.whatsapp_link, "_blank");
      queryClient.invalidateQueries({ queryKey: ["purchase-order", poId] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to send"),
  });

  const receiveMutation = useMutation({
    mutationFn: (items: { item_id: number; quantity_received: number }[]) => receiveGoods(poId, items),
    onSuccess: () => {
      message.success("Goods received, stock updated");
      setReceiveOpen(false);
      queryClient.invalidateQueries({ queryKey: ["purchase-order", poId] });
      queryClient.invalidateQueries({ queryKey: ["stock"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to receive goods"),
  });

  const downloadPdf = async () => {
    const res = await apiClient.get(`/api/purchase-orders/${poId}/pdf`, { responseType: "blob" });
    const url = window.URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
    window.open(url, "_blank");
  };

  if (isLoading || !po) return null;

  const remainingItems = po.items.filter((i) => i.quantity_received < i.quantity_ordered);

  return (
    <div>
      <Space style={{ marginBottom: 16, width: "100%", justifyContent: "space-between" }}>
        <Typography.Title level={3} style={{ margin: 0 }}>
          {po.po_number}
        </Typography.Title>
        <Space>
          <Button icon={<DownloadOutlined />} onClick={downloadPdf}>
            Download PDF
          </Button>
          <Button
            icon={<WhatsAppOutlined />}
            style={{ background: "#25D366", color: "white", border: "none" }}
            onClick={() => sendMutation.mutate()}
            loading={sendMutation.isPending}
            disabled={!po.vendor_name}
          >
            Send via WhatsApp
          </Button>
          {remainingItems.length > 0 && (
            <Button type="primary" icon={<InboxOutlined />} onClick={() => setReceiveOpen(true)}>
              Receive Goods
            </Button>
          )}
        </Space>
      </Space>

      <Card style={{ marginBottom: 16 }}>
        <Descriptions column={3}>
          <Descriptions.Item label="Vendor">{po.vendor_name}</Descriptions.Item>
          <Descriptions.Item label="Deliver to">{po.outlet_name}</Descriptions.Item>
          <Descriptions.Item label="Status">
            <Tag>{po.status.replace("_", " ")}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="Order date">{new Date(po.order_date).toLocaleDateString()}</Descriptions.Item>
          <Descriptions.Item label="Expected date">
            {po.expected_date ? new Date(po.expected_date).toLocaleDateString() : "-"}
          </Descriptions.Item>
          <Descriptions.Item label="Total">₹{po.total_amount.toFixed(2)}</Descriptions.Item>
          {po.notes && <Descriptions.Item label="Notes" span={3}>{po.notes}</Descriptions.Item>}
        </Descriptions>
      </Card>

      <Table
        rowKey="id"
        dataSource={po.items}
        pagination={false}
        columns={[
          { title: "SKU", dataIndex: "sku" },
          { title: "Item", dataIndex: "product_name" },
          { title: "Ordered", dataIndex: "quantity_ordered" },
          { title: "Received", dataIndex: "quantity_received" },
          { title: "Unit cost", dataIndex: "unit_cost", render: (v: number) => `₹${v.toFixed(2)}` },
          { title: "Tax %", dataIndex: "tax_rate" },
          { title: "Amount", dataIndex: "amount", render: (v: number) => `₹${v.toFixed(2)}` },
        ]}
      />

      <Modal
        title="Receive Goods"
        open={receiveOpen}
        onCancel={() => setReceiveOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={receiveMutation.isPending}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={(values) => {
            const items = remainingItems.map((item) => ({
              item_id: item.id,
              quantity_received: values[`item_${item.id}`] || 0,
            }));
            receiveMutation.mutate(items.filter((i) => i.quantity_received > 0));
          }}
        >
          {remainingItems.map((item) => (
            <Form.Item
              key={item.id}
              name={`item_${item.id}`}
              label={`${item.product_name} (${item.sku}) - remaining ${item.quantity_ordered - item.quantity_received}`}
              initialValue={item.quantity_ordered - item.quantity_received}
            >
              <InputNumber min={0} max={item.quantity_ordered - item.quantity_received} style={{ width: "100%" }} />
            </Form.Item>
          ))}
        </Form>
      </Modal>
    </div>
  );
}
