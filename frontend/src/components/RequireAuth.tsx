import { Result, Spin } from "antd";
import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import type { UserRole } from "../api/types";
import { hasMinRole } from "../utils/roles";

export default function RequireAuth({
  children,
  minRole,
}: {
  children: ReactNode;
  /** Lowest role allowed to view this route. Omit to just require any authenticated user. */
  minRole?: UserRole;
}) {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100vh" }}>
        <Spin size="large" />
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (!hasMinRole(user.role, minRole)) {
    return (
      <Result
        status="403"
        title="Access restricted"
        subTitle="Your account doesn't have permission to view this page."
        style={{ marginTop: 80 }}
      />
    );
  }

  return <>{children}</>;
}
