import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Col,
  Descriptions,
  Divider,
  Drawer,
  Input,
  InputNumber,
  Modal,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  activateBomVersion,
  archiveBomVersion,
  createBomVersion,
  getBom,
  getBomCost,
  getBomVersion,
  listItems,
  listUoms,
  replaceBomComponents,
} from "../api/endpoints";
import type { BomStatus, BomVersion, Item, Uom } from "../api/types";
import ItemPicker from "../components/ItemPicker";
import {
  type DraftRow,
  diffVersions,
  findDuplicateItemIds,
  itemToRow,
  newRowKey,
  parsePaste,
  plannedRequirement,
  toPayload,
  validateRow,
} from "../utils/bom";
import { formatQty } from "../utils/quantity";

const STATUS_COLOR: Record<BomStatus, string> = {
  draft: "gold",
  active: "green",
  archived: "default",
};

/** Rows rendered at once. The table virtualizes, so a 500-line BOM mounts only
 *  what fits on screen - which is what makes a per-row unit selector affordable. */
const GRID_HEIGHT = 460;

export default function BomBuilder() {
  const { id } = useParams();
  const bomId = Number(id);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [rows, setRows] = useState<DraftRow[]>([]);
  const [dirty, setDirty] = useState(false);
  const [selectedKeys, setSelectedKeys] = useState<React.Key[]>([]);
  const [activeVersionId, setActiveVersionId] = useState<number | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pasteOpen, setPasteOpen] = useState(false);
  const [pasteText, setPasteText] = useState("");
  const [compareWith, setCompareWith] = useState<number | null>(null);
  const [substituteFor, setSubstituteFor] = useState<DraftRow | null>(null);
  const loadedVersionRef = useRef<number | null>(null);

  const { data: bom, isLoading } = useQuery({
    queryKey: ["bom", bomId],
    queryFn: () => getBom(bomId).then((r) => r.data),
    enabled: Number.isFinite(bomId),
  });

  const { data: uoms } = useQuery({ queryKey: ["uoms"], queryFn: () => listUoms().then((r) => r.data) });
  const { data: allItems } = useQuery({
    queryKey: ["items-all"],
    queryFn: () => listItems({ is_active: true }).then((r) => r.data),
  });

  // Which version the grid is editing. Defaults to the newest draft, else active.
  const currentVersion: BomVersion | undefined = useMemo(() => {
    if (!bom?.versions?.length) return undefined;
    if (activeVersionId) return bom.versions.find((v) => v.id === activeVersionId);
    return (
      [...bom.versions].reverse().find((v) => v.status === "draft") ??
      bom.versions.find((v) => v.status === "active") ??
      bom.versions[bom.versions.length - 1]
    );
  }, [bom, activeVersionId]);

  const { data: versionDetail } = useQuery({
    queryKey: ["bom-version", bomId, currentVersion?.id],
    queryFn: () => getBomVersion(bomId, currentVersion!.id).then((r) => r.data),
    enabled: !!currentVersion?.id,
  });

  const { data: compareDetail } = useQuery({
    queryKey: ["bom-version", bomId, compareWith],
    queryFn: () => getBomVersion(bomId, compareWith!).then((r) => r.data),
    enabled: !!compareWith,
  });

  // Cost comes from the backend in Decimal. Deliberately not recomputed in JS:
  // money must not go through floating point (see app/core/money.py).
  const { data: cost, isFetching: costLoading } = useQuery({
    queryKey: ["bom-cost", bomId, currentVersion?.id],
    queryFn: () => getBomCost(bomId, { version_id: currentVersion!.id }).then((r) => r.data),
    enabled: !!currentVersion?.id,
  });

  const itemById = useMemo(() => new Map((allItems ?? []).map((i) => [i.id, i])), [allItems]);
  const uomById = useMemo(() => new Map((uoms ?? []).map((u) => [u.id, u])), [uoms]);
  const uomOptions = useMemo(
    () => (uoms ?? []).filter((u) => u.is_active).map((u) => ({ value: u.id, label: u.code })),
    [uoms],
  );

  // Load the grid from the server exactly once per version, so re-fetches
  // triggered elsewhere never clobber unsaved edits.
  useEffect(() => {
    if (!versionDetail) return;
    if (loadedVersionRef.current === versionDetail.id) return;
    loadedVersionRef.current = versionDetail.id;
    setRows(
      versionDetail.components.map((c, i) => {
        const item = itemById.get(c.item_id);
        return {
          key: newRowKey(),
          item_id: c.item_id,
          sku: c.sku,
          name: c.name,
          quantity: Number(c.quantity),
          uom_id: c.uom_id,
          uom_code: c.uom_code,
          stock_uom_id: item?.stock_uom_id ?? null,
          stock_uom_code: item?.stock_uom_code ?? null,
          scrap_pct: Number(c.scrap_pct),
          is_optional: c.is_optional,
          sequence: i,
          notes: c.notes,
          substitutes: c.substitutes ?? [],
        };
      }),
    );
    setDirty(false);
    setSelectedKeys([]);
  }, [versionDetail, itemById]);

  const editable = !!currentVersion?.is_editable;

  // ------------------------------------------------------ unsaved protection
  useEffect(() => {
    if (!dirty) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);

  const confirmLeave = (action: () => void) => {
    if (!dirty) return action();
    Modal.confirm({
      title: "Leave without saving?",
      content: "This bill of materials has changes that haven't been saved yet.",
      okText: "Discard changes",
      okButtonProps: { danger: true },
      cancelText: "Stay",
      onOk: action,
    });
  };

  // -------------------------------------------------------------- row edits
  const patchRow = useCallback((key: string, patch: Partial<DraftRow>) => {
    setRows((prev) => prev.map((r) => (r.key === key ? { ...r, ...patch } : r)));
    setDirty(true);
  }, []);

  const addItems = (items: Item[]) => {
    setRows((prev) => [...prev, ...items.map((it, i) => itemToRow(it, prev.length + i))]);
    setDirty(true);
  };

  const removeRows = (keys: React.Key[]) => {
    const set = new Set(keys.map(String));
    setRows((prev) => prev.filter((r) => !set.has(r.key)));
    setSelectedKeys([]);
    setDirty(true);
  };

  const duplicateRow = (row: DraftRow) => {
    setRows((prev) => {
      const i = prev.findIndex((r) => r.key === row.key);
      const copy = { ...row, key: newRowKey(), substitutes: [...(row.substitutes ?? [])] };
      return [...prev.slice(0, i + 1), copy, ...prev.slice(i + 1)];
    });
    setDirty(true);
  };

  const moveRow = (row: DraftRow, delta: number) => {
    setRows((prev) => {
      const i = prev.findIndex((r) => r.key === row.key);
      const j = i + delta;
      if (i < 0 || j < 0 || j >= prev.length) return prev;
      const next = [...prev];
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });
    setDirty(true);
  };

  // ------------------------------------------------------------- validation
  const duplicateItemIds = useMemo(() => findDuplicateItemIds(rows), [rows]);
  const issuesByKey = useMemo(() => {
    const m = new Map<string, ReturnType<typeof validateRow>>();
    for (const r of rows) m.set(r.key, validateRow(r, { uomById, duplicateItemIds, itemById }));
    return m;
  }, [rows, uomById, duplicateItemIds, itemById]);

  const errorCount = useMemo(
    () => [...issuesByKey.values()].filter((v) => v.some((i) => i.severity === "error")).length,
    [issuesByKey],
  );
  const warningCount = useMemo(
    () => [...issuesByKey.values()].filter((v) => v.some((i) => i.severity === "warning")).length,
    [issuesByKey],
  );

  // ------------------------------------------------------------------ saves
  const save = useMutation({
    mutationFn: () => replaceBomComponents(bomId, currentVersion!.id, toPayload(rows)),
    onSuccess: () => {
      message.success("Draft saved");
      setDirty(false);
      loadedVersionRef.current = null;
      queryClient.invalidateQueries({ queryKey: ["bom", bomId] });
      queryClient.invalidateQueries({ queryKey: ["bom-version", bomId] });
      queryClient.invalidateQueries({ queryKey: ["bom-cost", bomId] });
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || "Could not save the draft"),
  });

  const doActivate = useMutation({
    mutationFn: () => activateBomVersion(bomId, currentVersion!.id),
    onSuccess: () => {
      message.success("Version activated");
      loadedVersionRef.current = null;
      queryClient.invalidateQueries({ queryKey: ["bom", bomId] });
      queryClient.invalidateQueries({ queryKey: ["bom-version", bomId] });
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || "Could not activate"),
  });

  const doArchive = useMutation({
    mutationFn: () => archiveBomVersion(bomId, currentVersion!.id),
    onSuccess: () => {
      message.success("Version archived");
      loadedVersionRef.current = null;
      queryClient.invalidateQueries({ queryKey: ["bom", bomId] });
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || "Could not archive"),
  });

  const newVersion = useMutation({
    mutationFn: () =>
      createBomVersion(bomId, {
        output_quantity: Number(currentVersion?.output_quantity ?? 1),
        output_uom_id: currentVersion?.output_uom_id ?? null,
        copy_from_version_id: currentVersion?.id ?? null,
      }),
    onSuccess: (r) => {
      message.success(`Version ${r.data.version_no} created as a draft`);
      loadedVersionRef.current = null;
      setActiveVersionId(r.data.id);
      queryClient.invalidateQueries({ queryKey: ["bom", bomId] });
    },
    onError: (e: any) => message.error(e?.response?.data?.detail || "Could not create a version"),
  });

  // ------------------------------------------------------------ bulk paste
  const pasteRows = useMemo(
    () => (pasteText.trim() ? parsePaste(pasteText, allItems ?? [], uoms ?? []) : []),
    [pasteText, allItems, uoms],
  );
  const pasteOk = pasteRows.filter((r) => r.matchedItem && !r.error);

  const applyPaste = () => {
    setRows((prev) => [
      ...prev,
      ...pasteOk.map((p, i) => {
        const base = itemToRow(p.matchedItem!, prev.length + i);
        return {
          ...base,
          quantity: p.quantity ?? 1,
          uom_id: p.matchedUom?.id ?? base.uom_id,
          uom_code: p.matchedUom?.code ?? base.uom_code,
        };
      }),
    ]);
    setDirty(true);
    setPasteOpen(false);
    setPasteText("");
    message.success(`Added ${pasteOk.length} row${pasteOk.length === 1 ? "" : "s"}`);
  };

  // ----------------------------------------------------------------- render
  const columns = useMemo(
    () => [
      {
        title: "#",
        key: "seq",
        width: 56,
        render: (_: unknown, __: DraftRow, index: number) => (
          <Typography.Text type="secondary">{index + 1}</Typography.Text>
        ),
      },
      {
        title: "Material",
        key: "item",
        width: 260,
        render: (_: unknown, r: DraftRow) => {
          const issues = issuesByKey.get(r.key) ?? [];
          const itemIssue = issues.find((i) => i.field === "item");
          return (
            <Space direction="vertical" size={0} style={{ lineHeight: 1.3 }}>
              <Typography.Text strong>{r.name}</Typography.Text>
              <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                <code>{r.sku}</code>
              </Typography.Text>
              {itemIssue && (
                <Typography.Text
                  type={itemIssue.severity === "error" ? "danger" : "warning"}
                  style={{ fontSize: 11 }}
                >
                  {itemIssue.message}
                </Typography.Text>
              )}
            </Space>
          );
        },
      },
      {
        title: "Qty",
        key: "quantity",
        width: 110,
        render: (_: unknown, r: DraftRow) => {
          const err = (issuesByKey.get(r.key) ?? []).find(
            (i) => i.field === "quantity" && i.severity === "error",
          );
          return (
            <Tooltip title={err?.message} open={err ? undefined : false}>
              <InputNumber
                size="small"
                min={0}
                step={1}
                status={err ? "error" : undefined}
                value={r.quantity}
                disabled={!editable}
                onChange={(v) => patchRow(r.key, { quantity: Number(v ?? 0) })}
                style={{ width: "100%" }}
              />
            </Tooltip>
          );
        },
      },
      {
        title: "UoM",
        key: "uom",
        width: 110,
        render: (_: unknown, r: DraftRow) => {
          const warn = (issuesByKey.get(r.key) ?? []).find((i) => i.field === "uom_id");
          return (
            <Tooltip title={warn?.message} open={warn ? undefined : false}>
              <Select
                size="small"
                showSearch
                optionFilterProp="label"
                status={warn?.severity === "error" ? "error" : undefined}
                value={r.uom_id || undefined}
                disabled={!editable}
                options={uomOptions}
                onChange={(v) => patchRow(r.key, { uom_id: v, uom_code: uomById.get(v)?.code ?? null })}
                style={{ width: "100%" }}
              />
            </Tooltip>
          );
        },
      },
      {
        title: "Stock UoM",
        key: "stock_uom",
        width: 96,
        render: (_: unknown, r: DraftRow) => (
          <Typography.Text type="secondary">{r.stock_uom_code ?? "—"}</Typography.Text>
        ),
      },
      {
        title: "Wastage %",
        key: "scrap",
        width: 110,
        render: (_: unknown, r: DraftRow) => (
          <InputNumber
            size="small"
            min={0}
            max={99.9}
            step={1}
            value={r.scrap_pct}
            disabled={!editable}
            onChange={(v) => patchRow(r.key, { scrap_pct: Number(v ?? 0) })}
            style={{ width: "100%" }}
          />
        ),
      },
      {
        title: "Planned issue",
        key: "planned",
        width: 130,
        align: "right" as const,
        render: (_: unknown, r: DraftRow) => (
          <Tooltip title={`Base ${formatQty(r.quantity)} + ${r.scrap_pct || 0}% wastage`}>
            <Typography.Text strong>
              {formatQty(plannedRequirement(r.quantity, r.scrap_pct))} {r.uom_code ?? ""}
            </Typography.Text>
          </Tooltip>
        ),
      },
      {
        title: "Opt.",
        key: "optional",
        width: 64,
        align: "center" as const,
        render: (_: unknown, r: DraftRow) => (
          <Checkbox
            checked={r.is_optional}
            disabled={!editable}
            onChange={(e) => patchRow(r.key, { is_optional: e.target.checked })}
          />
        ),
      },
      {
        title: "Subs",
        key: "subs",
        width: 78,
        align: "center" as const,
        render: (_: unknown, r: DraftRow) => (
          <Button size="small" type={r.substitutes?.length ? "primary" : "default"} ghost={!!r.substitutes?.length}
            onClick={() => setSubstituteFor(r)} disabled={!editable}>
            {r.substitutes?.length ?? 0}
          </Button>
        ),
      },
      {
        title: "Notes",
        key: "notes",
        width: 180,
        render: (_: unknown, r: DraftRow) => (
          <Input
            size="small"
            value={r.notes ?? ""}
            disabled={!editable}
            placeholder="—"
            onChange={(e) => patchRow(r.key, { notes: e.target.value })}
          />
        ),
      },
      {
        title: "",
        key: "actions",
        width: 128,
        render: (_: unknown, r: DraftRow) => (
          <Space size={2}>
            <Tooltip title="Move up">
              <Button size="small" disabled={!editable} onClick={() => moveRow(r, -1)}>↑</Button>
            </Tooltip>
            <Tooltip title="Move down">
              <Button size="small" disabled={!editable} onClick={() => moveRow(r, 1)}>↓</Button>
            </Tooltip>
            <Tooltip title="Duplicate row">
              <Button size="small" disabled={!editable} onClick={() => duplicateRow(r)}>⧉</Button>
            </Tooltip>
            <Tooltip title="Remove">
              <Button size="small" danger disabled={!editable} onClick={() => removeRows([r.key])}>×</Button>
            </Tooltip>
          </Space>
        ),
      },
    ],
    [editable, issuesByKey, patchRow, uomOptions, uomById],
  );

  if (isLoading) return <Card loading />;
  if (!bom) return <Alert type="error" message="Bill of materials not found" />;

  const versions = bom.versions ?? [];

  return (
    <div>
      <Space style={{ width: "100%", justifyContent: "space-between", marginBottom: 12 }} wrap>
        <Space direction="vertical" size={0}>
          <Space>
            <Button size="small" onClick={() => confirmLeave(() => navigate("/boms"))}>
              ← All BOMs
            </Button>
            <Typography.Title level={4} style={{ margin: 0 }}>
              {bom.name}
            </Typography.Title>
            {dirty && <Tag color="orange">Unsaved changes</Tag>}
          </Space>
          <Typography.Text type="secondary">
            Produces <code>{bom.item_sku}</code> — {bom.item_name}
          </Typography.Text>
        </Space>

        <Space wrap>
          <Select
            size="small"
            style={{ width: 210 }}
            value={currentVersion?.id}
            onChange={(v) => confirmLeave(() => { loadedVersionRef.current = null; setActiveVersionId(v); })}
            options={versions.map((v) => ({
              value: v.id,
              label: `V${v.version_no} — ${v.status}${v.is_locked ? " (locked)" : ""}`,
            }))}
          />
          <Button size="small" onClick={() => newVersion.mutate()} loading={newVersion.isPending}>
            New version
          </Button>
          {currentVersion?.status === "draft" && (
            <Button
              size="small"
              type="primary"
              ghost
              disabled={dirty || errorCount > 0 || !rows.length}
              onClick={() => doActivate.mutate()}
              loading={doActivate.isPending}
            >
              Activate
            </Button>
          )}
          {currentVersion?.status === "active" && (
            <Button size="small" danger onClick={() => doArchive.mutate()} loading={doArchive.isPending}>
              Archive
            </Button>
          )}
          <Button
            type="primary"
            size="small"
            disabled={!editable || !dirty || errorCount > 0}
            onClick={() => save.mutate()}
            loading={save.isPending}
          >
            Save draft
          </Button>
        </Space>
      </Space>

      {!editable && currentVersion && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message={
            currentVersion.is_locked
              ? `Version ${currentVersion.version_no} has been used by production and can never be changed.`
              : `Version ${currentVersion.version_no} is ${currentVersion.status} and is read-only.`
          }
          description="Create a new version to make changes — earlier versions stay exactly as production saw them."
          action={
            <Button size="small" onClick={() => newVersion.mutate()}>
              New version from this
            </Button>
          }
        />
      )}

      {errorCount > 0 && (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 12 }}
          message={`${errorCount} row${errorCount === 1 ? "" : "s"} need attention before this can be saved`}
        />
      )}
      {warningCount > 0 && errorCount === 0 && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message={`${warningCount} row${warningCount === 1 ? "" : "s"} have warnings`}
          description="Duplicated materials and cross-unit conversions are allowed, but worth a second look. Nothing is merged automatically."
        />
      )}

      <Row gutter={16}>
        <Col xs={24} xl={18}>
          <Card
            size="small"
            styles={{ body: { padding: 8 } }}
            title={
              <Space wrap>
                <Button type="primary" size="small" disabled={!editable} onClick={() => setPickerOpen(true)}>
                  Add materials
                </Button>
                <Button size="small" disabled={!editable} onClick={() => setPasteOpen(true)}>
                  Paste from spreadsheet
                </Button>
                <Button
                  size="small"
                  danger
                  disabled={!editable || !selectedKeys.length}
                  onClick={() => removeRows(selectedKeys)}
                >
                  Remove {selectedKeys.length || ""}
                </Button>
                <Typography.Text type="secondary">{rows.length} components</Typography.Text>
              </Space>
            }
          >
            <Table<DraftRow>
              rowKey="key"
              size="small"
              virtual
              pagination={false}
              scroll={{ y: GRID_HEIGHT, x: 1360 }}
              dataSource={rows}
              columns={columns as any}
              rowSelection={{
                selectedRowKeys: selectedKeys,
                onChange: setSelectedKeys,
                columnWidth: 40,
              }}
              locale={{ emptyText: "No components yet — add materials to get started" }}
            />
          </Card>
        </Col>

        <Col xs={24} xl={6}>
          <Card size="small" title="Estimated material cost">
            {dirty && (
              <Alert
                type="warning"
                showIcon
                style={{ marginBottom: 10 }}
                message="Save to refresh"
                description="Costs are calculated on the server in exact decimals, so they update after saving."
              />
            )}
            <Statistic
              title="Estimated material cost"
              value={cost ? Number(cost.total_cost) : 0}
              precision={2}
              prefix="₹"
              loading={costLoading}
            />
            <Divider style={{ margin: "12px 0" }} />
            <Descriptions column={1} size="small">
              <Descriptions.Item label="Components">{rows.length}</Descriptions.Item>
              <Descriptions.Item label="Optional">
                {rows.filter((r) => r.is_optional).length}
              </Descriptions.Item>
              <Descriptions.Item label="With wastage">
                {rows.filter((r) => (r.scrap_pct ?? 0) > 0).length}
              </Descriptions.Item>
              <Descriptions.Item label="Output">
                {formatQty(Number(currentVersion?.output_quantity ?? 1))}{" "}
                {currentVersion?.output_uom_code ?? ""}
              </Descriptions.Item>
            </Descriptions>
          </Card>

          <Card size="small" title="Versions" style={{ marginTop: 12 }}>
            <Space direction="vertical" style={{ width: "100%" }} size={6}>
              {versions.map((v) => (
                <Space key={v.id} style={{ width: "100%", justifyContent: "space-between" }}>
                  <Space size={6}>
                    <Tag color={STATUS_COLOR[v.status]}>V{v.version_no}</Tag>
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      {v.status}
                      {v.is_locked && " · locked"}
                    </Typography.Text>
                  </Space>
                  <Space size={4}>
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      {v.component_count}
                    </Typography.Text>
                    {v.id !== currentVersion?.id && (
                      <Button size="small" type="link" onClick={() => setCompareWith(v.id)}>
                        Compare
                      </Button>
                    )}
                  </Space>
                </Space>
              ))}
            </Space>
          </Card>
        </Col>
      </Row>

      <ItemPicker
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        onAdd={addItems}
        excludeItemIds={[]}
      />

      {/* ---------------------------------------------------------- paste */}
      <Modal
        title="Paste from a spreadsheet"
        open={pasteOpen}
        onCancel={() => setPasteOpen(false)}
        onOk={applyPaste}
        okText={pasteOk.length ? `Add ${pasteOk.length} rows` : "Add"}
        okButtonProps={{ disabled: !pasteOk.length }}
        width={720}
      >
        <Typography.Paragraph type="secondary">
          One material per line: <b>name or SKU</b>, quantity, unit — separated by tabs or commas.
          Copying straight out of Excel or Google Sheets works.
        </Typography.Paragraph>
        <Input.TextArea
          rows={8}
          value={pasteText}
          onChange={(e) => setPasteText(e.target.value)}
          placeholder={"Silk Fabric\t4.5\tm\nGold Lace\t8\tm\nPearl Button\t18\tpc"}
        />
        {pasteRows.length > 0 && (
          <Table
            size="small"
            style={{ marginTop: 12 }}
            rowKey={(_, i) => String(i)}
            dataSource={pasteRows}
            pagination={{ pageSize: 6, size: "small" }}
            columns={[
              {
                title: "Matched",
                key: "m",
                render: (_: unknown, r: any) =>
                  r.matchedItem ? (
                    <Space direction="vertical" size={0}>
                      <Typography.Text>{r.matchedItem.name}</Typography.Text>
                      <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                        <code>{r.matchedItem.sku}</code>
                      </Typography.Text>
                    </Space>
                  ) : (
                    <Typography.Text type="danger">{r.error}</Typography.Text>
                  ),
              },
              { title: "Qty", dataIndex: "quantity", width: 90 },
              {
                title: "Unit",
                key: "u",
                width: 90,
                render: (_: unknown, r: any) => r.matchedUom?.code ?? r.uomCode ?? "—",
              },
            ]}
          />
        )}
      </Modal>

      {/* ------------------------------------------------------ substitutes */}
      <Drawer
        title={substituteFor ? `Substitutes for ${substituteFor.name}` : "Substitutes"}
        open={!!substituteFor}
        onClose={() => setSubstituteFor(null)}
        width={520}
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="Substitutes are never swapped in automatically"
          description="They record what a tailor is allowed to reach for. What was actually used gets recorded against the production order."
        />
        <Space direction="vertical" style={{ width: "100%" }}>
          {(substituteFor?.substitutes ?? []).map((s, i) => (
            <Space key={i} style={{ width: "100%", justifyContent: "space-between" }}>
              <Space direction="vertical" size={0}>
                <Typography.Text>{s.name ?? `Item ${s.item_id}`}</Typography.Text>
                <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                  <code>{s.sku}</code>
                </Typography.Text>
              </Space>
              <Button
                size="small"
                danger
                onClick={() => {
                  if (!substituteFor) return;
                  const next = (substituteFor.substitutes ?? []).filter((_, j) => j !== i);
                  patchRow(substituteFor.key, { substitutes: next });
                  setSubstituteFor({ ...substituteFor, substitutes: next });
                }}
              >
                Remove
              </Button>
            </Space>
          ))}
          {!substituteFor?.substitutes?.length && (
            <Typography.Text type="secondary">No substitutes yet.</Typography.Text>
          )}
          <SubstitutePicker
            onPick={(item) => {
              if (!substituteFor) return;
              const next = [
                ...(substituteFor.substitutes ?? []),
                { item_id: item.id, priority: (substituteFor.substitutes?.length ?? 0) + 1, sku: item.sku, name: item.name },
              ];
              patchRow(substituteFor.key, { substitutes: next });
              setSubstituteFor({ ...substituteFor, substitutes: next });
            }}
          />
        </Space>
      </Drawer>

      {/* -------------------------------------------------------- compare */}
      <Modal
        title={`Compare V${compareDetail?.version_no ?? ""} → V${currentVersion?.version_no ?? ""}`}
        open={!!compareWith}
        onCancel={() => setCompareWith(null)}
        footer={null}
        width={860}
      >
        {compareDetail && versionDetail && (
          <Table
            size="small"
            rowKey={(r: any) => `${r.item_id}-${r.kind}`}
            dataSource={diffVersions(compareDetail.components, versionDetail.components).filter(
              (d) => d.kind !== "unchanged",
            )}
            pagination={{ pageSize: 12, size: "small" }}
            locale={{ emptyText: "These two versions have identical components" }}
            columns={[
              {
                title: "Change",
                dataIndex: "kind",
                width: 130,
                render: (k: string) => {
                  const color =
                    k === "added" ? "green" : k === "removed" ? "red" : k === "quantity" ? "blue" : "gold";
                  return <Tag color={color}>{k}</Tag>;
                },
              },
              {
                title: "Material",
                key: "item",
                render: (_: unknown, r: any) => (
                  <Space direction="vertical" size={0}>
                    <Typography.Text>{r.name}</Typography.Text>
                    <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                      <code>{r.sku}</code>
                    </Typography.Text>
                  </Space>
                ),
              },
              {
                title: "Before",
                key: "from",
                render: (_: unknown, r: any) =>
                  r.from ? `${formatQty(r.from.quantity)} ${r.from.uom_code ?? ""} · ${r.from.scrap_pct}%` : "—",
              },
              {
                title: "After",
                key: "to",
                render: (_: unknown, r: any) =>
                  r.to ? `${formatQty(r.to.quantity)} ${r.to.uom_code ?? ""} · ${r.to.scrap_pct}%` : "—",
              },
            ]}
          />
        )}
      </Modal>
    </div>
  );
}

/** Small inline search used inside the substitutes drawer. */
function SubstitutePicker({ onPick }: { onPick: (item: Item) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button type="dashed" block onClick={() => setOpen(true)}>
        + Add substitute
      </Button>
      <ItemPicker
        open={open}
        onClose={() => setOpen(false)}
        onAdd={(items) => items.forEach(onPick)}
        title="Choose a substitute material"
      />
    </>
  );
}
