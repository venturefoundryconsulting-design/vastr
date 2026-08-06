import { DownOutlined, ExportOutlined } from "@ant-design/icons";
import { Button, Dropdown, message } from "antd";
import { useState } from "react";
import { exportData, type ExportFormat } from "../api/endpoints";

const FORMAT_LABELS: Record<ExportFormat, string> = {
  xlsx: "Export as Excel (.xlsx)",
  csv: "Export as CSV",
  pdf: "Export as PDF",
};

/** Drop this on any list/report page's toolbar: <ExportButton url="/api/products/export" params={{search}} filenameBase="products" /> */
export default function ExportButton({
  url,
  params,
  filenameBase,
}: {
  url: string;
  params?: Record<string, unknown>;
  filenameBase: string;
}) {
  const [loading, setLoading] = useState<ExportFormat | null>(null);

  const runExport = async (format: ExportFormat) => {
    setLoading(format);
    try {
      const res = await exportData(url, params ?? {}, format);
      const blob = new Blob([res.data]);
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `${filenameBase}.${format}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(link.href);
    } catch {
      message.error("Export failed - please try again");
    } finally {
      setLoading(null);
    }
  };

  return (
    <Dropdown
      trigger={["click"]}
      menu={{
        items: (Object.keys(FORMAT_LABELS) as ExportFormat[]).map((fmt) => ({
          key: fmt,
          label: FORMAT_LABELS[fmt],
        })),
        onClick: ({ key }) => runExport(key as ExportFormat),
      }}
      disabled={!!loading}
    >
      <Button icon={<ExportOutlined />} loading={!!loading}>
        Export <DownOutlined style={{ fontSize: 10 }} />
      </Button>
    </Dropdown>
  );
}
