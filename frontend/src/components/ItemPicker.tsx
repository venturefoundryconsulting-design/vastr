import { useQuery } from "@tanstack/react-query";
import { Empty, Input, Modal, Space, Table, Tag, Typography } from "antd";
import { useEffect, useMemo, useRef, useState } from "react";
import { listItems } from "../api/endpoints";
import type { Item, ItemType } from "../api/types";
import { formatQty } from "../utils/quantity";

const TYPE_LABEL: Record<ItemType, string> = {
  raw_material: "Raw material",
  semi_finished: "Semi-finished",
  finished_product: "Finished",
  packaging: "Packaging",
  service: "Service",
};

/**
 * Multi-select item search for the BOM builder.
 *
 * One shared picker rather than a dropdown per row: a 500-line BOM would
 * otherwise mount 500 searchable selects, and the realistic way people build a
 * BOM is "find six trims, add them all, then set quantities" - not one dialog
 * per material.
 *
 * Search is debounced and runs server-side against SKU, barcode and name, so
 * the whole catalogue never has to be shipped to the browser.
 */
export default function ItemPicker({
  open,
  onClose,
  onAdd,
  excludeItemIds = [],
  title = "Add materials",
}: {
  open: boolean;
  onClose: () => void;
  onAdd: (items: Item[]) => void;
  excludeItemIds?: number[];
  title?: string;
}) {
  const [term, setTerm] = useState("");
  const [debounced, setDebounced] = useState("");
  const [selected, setSelected] = useState<Item[]>([]);
  const searchRef = useRef<any>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(term), 250);
    return () => clearTimeout(t);
  }, [term]);

  useEffect(() => {
    if (open) {
      setTerm("");
      setDebounced("");
      setSelected([]);
      // Land the caret in the search box so the flow stays keyboard-only.
      setTimeout(() => searchRef.current?.focus(), 80);
    }
  }, [open]);

  const { data, isFetching } = useQuery({
    queryKey: ["item-picker", debounced],
    queryFn: () => listItems({ q: debounced || undefined, is_active: true }).then((r) => r.data),
    enabled: open,
  });

  const excluded = useMemo(() => new Set(excludeItemIds), [excludeItemIds]);
  const rows = useMemo(() => (data ?? []).filter((i) => i.is_stocked), [data]);

  const commit = (items: Item[]) => {
    if (!items.length) return;
    onAdd(items);
    onClose();
  };

  return (
    <Modal
      title={title}
      open={open}
      onCancel={onClose}
      onOk={() => commit(selected)}
      okText={selected.length ? `Add ${selected.length}` : "Add"}
      okButtonProps={{ disabled: !selected.length }}
      width={840}
      destroyOnClose
    >
      <Input
        ref={searchRef}
        allowClear
        size="large"
        placeholder="Search by name, SKU or barcode"
        value={term}
        onChange={(e) => setTerm(e.target.value)}
        style={{ marginBottom: 12 }}
      />
      <Table<Item>
        rowKey="id"
        size="small"
        loading={isFetching}
        dataSource={rows}
        pagination={{ pageSize: 8, size: "small", showSizeChanger: false }}
        scroll={{ y: 320 }}
        locale={{
          emptyText: (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={debounced ? `Nothing matches "${debounced}"` : "Start typing to search"}
            />
          ),
        }}
        rowSelection={{
          selectedRowKeys: selected.map((s) => s.id),
          onChange: (_keys, sel) => setSelected(sel),
          getCheckboxProps: (r) => ({ disabled: excluded.has(r.id) }),
        }}
        onRow={(r) => ({
          // Double-click adds just that one - the fast path for "I know what I want".
          onDoubleClick: () => !excluded.has(r.id) && commit([r]),
          style: excluded.has(r.id) ? { opacity: 0.45 } : undefined,
        })}
        columns={[
          {
            title: "Item",
            key: "name",
            render: (_: unknown, r: Item) => (
              <Space direction="vertical" size={0}>
                <Typography.Text strong>{r.display_name || r.name || r.sku}</Typography.Text>
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  <code>{r.sku}</code>
                  {excluded.has(r.id) && " · already in this BOM"}
                </Typography.Text>
              </Space>
            ),
          },
          {
            title: "Type",
            dataIndex: "item_type",
            width: 140,
            render: (t: ItemType) => <Tag>{TYPE_LABEL[t] ?? t}</Tag>,
          },
          { title: "Stock UoM", dataIndex: "stock_uom_code", width: 100 },
          {
            title: "In stock",
            dataIndex: "total_stock",
            width: 110,
            align: "right",
            render: (v: number, r: Item) => `${formatQty(v)} ${r.stock_uom_code ?? ""}`,
          },
        ]}
      />
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        Tip: double-click a row to add it immediately, or tick several and press Add.
      </Typography.Text>
    </Modal>
  );
}
