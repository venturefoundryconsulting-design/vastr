import { useQuery } from "@tanstack/react-query";
import { Table, Tag, Typography } from "antd";
import { useNavigate } from "react-router-dom";
import { getGlobalActivity } from "../api/endpoints";
import type { GlobalAuditLogEntry } from "../api/types";

export default function Activity() {
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({
    queryKey: ["admin-global-activity"],
    queryFn: () => getGlobalActivity(200).then((r) => r.data),
  });

  const columns = [
    { title: "When", dataIndex: "created_at", render: (v: string) => new Date(v).toLocaleString() },
    {
      title: "Store",
      dataIndex: "tenant_name",
      render: (v: string | null, r: GlobalAuditLogEntry) =>
        v ? <a onClick={() => navigate(`/platform-admin/tenants/${r.tenant_id}`)}>{v}</a> : "-",
    },
    { title: "By", dataIndex: "user_name", render: (v: string | null) => v || "System" },
    { title: "Action", dataIndex: "action", render: (v: string) => <Tag>{v}</Tag> },
    {
      title: "Entity",
      render: (_: unknown, r: GlobalAuditLogEntry) => (r.entity_type ? `${r.entity_type} #${r.entity_id}` : "-"),
    },
  ];

  return (
    <div>
      <Typography.Title level={3} style={{ margin: 0, marginBottom: 20 }}>
        Platform Activity
      </Typography.Title>
      <Typography.Text type="secondary" style={{ display: "block", marginBottom: 16 }}>
        The latest actions across every store - registrations, plan changes, logins, and admin actions.
      </Typography.Text>
      <Table rowKey="id" loading={isLoading} columns={columns} dataSource={data} scroll={{ x: "max-content" }} />
    </div>
  );
}
