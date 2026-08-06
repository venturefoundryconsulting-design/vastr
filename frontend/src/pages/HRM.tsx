import { CheckCircleOutlined, LogoutOutlined, PlusOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Button,
  Card,
  DatePicker,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Table,
  Tabs,
  Tag,
  Typography,
  message,
} from "antd";
import dayjs from "dayjs";
import { useState } from "react";
import {
  checkIn,
  checkOut,
  createLeaveRequest,
  getMyAttendance,
  getMyLeaveRequests,
  listAttendance,
  listLeaveRequests,
  listStaff,
  reviewLeaveRequest,
} from "../api/endpoints";
import { useAuth } from "../context/AuthContext";
import { hasMinRole } from "../utils/roles";
import type { Attendance, LeaveRequest, LeaveStatus, LeaveType } from "../api/types";

const ATTENDANCE_STATUS_COLORS: Record<string, string> = {
  present: "green",
  absent: "red",
  half_day: "gold",
  on_leave: "blue",
};

const LEAVE_STATUS_COLORS: Record<string, string> = {
  pending: "gold",
  approved: "green",
  rejected: "red",
};

const LEAVE_TYPE_LABELS: Record<LeaveType, string> = {
  sick: "Sick",
  casual: "Casual",
  unpaid: "Unpaid",
  other: "Other",
};

function fmtTime(iso?: string | null) {
  return iso ? new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "-";
}

function MyAttendanceTab() {
  const queryClient = useQueryClient();
  const { data: records, isLoading } = useQuery({
    queryKey: ["my-attendance"],
    queryFn: () => getMyAttendance(30).then((r) => r.data),
  });

  const today = dayjs().format("YYYY-MM-DD");
  const todayRecord = records?.find((r) => r.date === today);

  const checkInMutation = useMutation({
    mutationFn: checkIn,
    onSuccess: () => {
      message.success("Checked in");
      queryClient.invalidateQueries({ queryKey: ["my-attendance"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to check in"),
  });

  const checkOutMutation = useMutation({
    mutationFn: checkOut,
    onSuccess: () => {
      message.success("Checked out");
      queryClient.invalidateQueries({ queryKey: ["my-attendance"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to check out"),
  });

  return (
    <div>
      <Card style={{ marginBottom: 16 }}>
        <Space size="large" align="center" wrap>
          <div>
            <Typography.Text type="secondary">Today</Typography.Text>
            <div>
              <Typography.Text strong>Check-in: </Typography.Text>
              {fmtTime(todayRecord?.check_in_at)}
              <Typography.Text strong style={{ marginLeft: 16 }}>Check-out: </Typography.Text>
              {fmtTime(todayRecord?.check_out_at)}
            </div>
          </div>
          <Button
            type="primary"
            icon={<CheckCircleOutlined />}
            loading={checkInMutation.isPending}
            disabled={!!todayRecord?.check_in_at}
            onClick={() => checkInMutation.mutate()}
          >
            Check In
          </Button>
          <Button
            icon={<LogoutOutlined />}
            loading={checkOutMutation.isPending}
            disabled={!todayRecord?.check_in_at || !!todayRecord?.check_out_at}
            onClick={() => checkOutMutation.mutate()}
          >
            Check Out
          </Button>
        </Space>
      </Card>

      <Table
        rowKey="id"
        loading={isLoading}
        dataSource={records}
        pagination={{ pageSize: 10 }}
        columns={[
          { title: "Date", dataIndex: "date" },
          { title: "Check-in", key: "in", render: (_: unknown, r: Attendance) => fmtTime(r.check_in_at) },
          { title: "Check-out", key: "out", render: (_: unknown, r: Attendance) => fmtTime(r.check_out_at) },
          {
            title: "Status",
            dataIndex: "status",
            render: (v: string) => <Tag color={ATTENDANCE_STATUS_COLORS[v]}>{v.replace("_", " ")}</Tag>,
          },
        ]}
      />
    </div>
  );
}

function TeamAttendanceTab() {
  const [month, setMonth] = useState(dayjs().format("YYYY-MM"));
  const { data: staff } = useQuery({ queryKey: ["hrm-staff"], queryFn: () => listStaff().then((r) => r.data) });
  const { data: records, isLoading } = useQuery({
    queryKey: ["team-attendance", month],
    queryFn: () => listAttendance({ month }).then((r) => r.data),
  });

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <DatePicker
          picker="month"
          value={dayjs(month, "YYYY-MM")}
          onChange={(d) => d && setMonth(d.format("YYYY-MM"))}
        />
      </Space>
      <Table
        rowKey="id"
        loading={isLoading}
        dataSource={records}
        pagination={{ pageSize: 15 }}
        columns={[
          { title: "Staff", dataIndex: "staff_name" },
          { title: "Outlet", dataIndex: "outlet_name" },
          { title: "Date", dataIndex: "date" },
          { title: "Check-in", key: "in", render: (_: unknown, r: Attendance) => fmtTime(r.check_in_at) },
          { title: "Check-out", key: "out", render: (_: unknown, r: Attendance) => fmtTime(r.check_out_at) },
          {
            title: "Status",
            dataIndex: "status",
            render: (v: string) => <Tag color={ATTENDANCE_STATUS_COLORS[v]}>{v.replace("_", " ")}</Tag>,
          },
        ]}
      />
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        {staff?.length ?? 0} staff members
      </Typography.Text>
    </div>
  );
}

function MyLeaveRequestsTab() {
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm();

  const { data: requests, isLoading } = useQuery({
    queryKey: ["my-leave-requests"],
    queryFn: () => getMyLeaveRequests().then((r) => r.data),
  });

  const createMutation = useMutation({
    mutationFn: createLeaveRequest,
    onSuccess: () => {
      message.success("Leave request submitted");
      setModalOpen(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ["my-leave-requests"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to submit request"),
  });

  return (
    <div>
      <Button type="primary" icon={<PlusOutlined />} style={{ marginBottom: 16 }} onClick={() => setModalOpen(true)}>
        Request Leave
      </Button>
      <Table
        rowKey="id"
        loading={isLoading}
        dataSource={requests}
        pagination={{ pageSize: 10 }}
        columns={[
          { title: "Type", dataIndex: "leave_type", render: (v: LeaveType) => LEAVE_TYPE_LABELS[v] },
          { title: "From", dataIndex: "start_date" },
          { title: "To", dataIndex: "end_date" },
          { title: "Reason", dataIndex: "reason" },
          {
            title: "Status",
            dataIndex: "status",
            render: (v: string, r: LeaveRequest) => (
              <Tag color={LEAVE_STATUS_COLORS[v]} title={r.review_note ?? undefined}>
                {v}
              </Tag>
            ),
          },
        ]}
      />

      <Modal
        title="Request Leave"
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()}
        confirmLoading={createMutation.isPending}
      >
        <Form
          form={form}
          layout="vertical"
          initialValues={{ leave_type: "casual" }}
          onFinish={(values) =>
            createMutation.mutate({
              ...values,
              start_date: values.dates[0].format("YYYY-MM-DD"),
              end_date: values.dates[1].format("YYYY-MM-DD"),
              dates: undefined,
            })
          }
        >
          <Form.Item name="leave_type" label="Leave type" rules={[{ required: true }]}>
            <Select
              options={Object.entries(LEAVE_TYPE_LABELS).map(([value, label]) => ({ value, label }))}
            />
          </Form.Item>
          <Form.Item name="dates" label="Dates" rules={[{ required: true }]}>
            <DatePicker.RangePicker style={{ width: "100%" }} />
          </Form.Item>
          <Form.Item name="reason" label="Reason (optional)">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

function LeaveApprovalsTab() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<LeaveStatus | undefined>("pending");

  const { data: requests, isLoading } = useQuery({
    queryKey: ["leave-approvals", statusFilter],
    queryFn: () => listLeaveRequests(statusFilter ? { status: statusFilter } : undefined).then((r) => r.data),
  });

  const reviewMutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: "approved" | "rejected" }) =>
      reviewLeaveRequest(id, { status }),
    onSuccess: () => {
      message.success("Request reviewed");
      queryClient.invalidateQueries({ queryKey: ["leave-approvals"] });
    },
    onError: (err: any) => message.error(err?.response?.data?.detail || "Failed to review request"),
  });

  return (
    <div>
      <Select
        allowClear
        placeholder="All statuses"
        style={{ width: 200, marginBottom: 16 }}
        value={statusFilter}
        onChange={setStatusFilter}
        options={[
          { value: "pending", label: "Pending" },
          { value: "approved", label: "Approved" },
          { value: "rejected", label: "Rejected" },
        ]}
      />
      <Table
        rowKey="id"
        loading={isLoading}
        dataSource={requests}
        pagination={{ pageSize: 10 }}
        columns={[
          { title: "Staff", dataIndex: "staff_name" },
          { title: "Type", dataIndex: "leave_type", render: (v: LeaveType) => LEAVE_TYPE_LABELS[v] },
          { title: "From", dataIndex: "start_date" },
          { title: "To", dataIndex: "end_date" },
          { title: "Reason", dataIndex: "reason" },
          {
            title: "Status",
            dataIndex: "status",
            render: (v: string) => <Tag color={LEAVE_STATUS_COLORS[v]}>{v}</Tag>,
          },
          {
            title: "",
            key: "actions",
            render: (_: unknown, r: LeaveRequest) =>
              r.status === "pending" ? (
                <Space>
                  <Button
                    size="small"
                    type="primary"
                    loading={reviewMutation.isPending}
                    onClick={() => reviewMutation.mutate({ id: r.id, status: "approved" })}
                  >
                    Approve
                  </Button>
                  <Button
                    size="small"
                    danger
                    loading={reviewMutation.isPending}
                    onClick={() => reviewMutation.mutate({ id: r.id, status: "rejected" })}
                  >
                    Reject
                  </Button>
                </Space>
              ) : null,
          },
        ]}
      />
    </div>
  );
}

export default function HRM() {
  const { user } = useAuth();
  const isManagerUp = hasMinRole(user?.role, "manager");

  const items = [
    { key: "my-attendance", label: "My Attendance", children: <MyAttendanceTab /> },
    ...(isManagerUp ? [{ key: "team-attendance", label: "Team Attendance", children: <TeamAttendanceTab /> }] : []),
    { key: "my-leave", label: "My Leave Requests", children: <MyLeaveRequestsTab /> },
    ...(isManagerUp ? [{ key: "leave-approvals", label: "Leave Approvals", children: <LeaveApprovalsTab /> }] : []),
  ];

  return (
    <div>
      <Typography.Title level={3}>HR Management</Typography.Title>
      <Tabs items={items} />
    </div>
  );
}
