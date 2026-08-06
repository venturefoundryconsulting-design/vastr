import { Result, Spin } from "antd";
import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

/**
 * Super Admin is a platform-level role, not a member of any tenant, so it
 * doesn't fit the tenant rank ladder in utils/roles.ts (hasMinRole) - this is
 * a separate, simple guard rather than reusing RequireAuth's minRole prop.
 * The role check is a plain string compare since the shared UserRole type
 * (used for the tenant-scoped minRole props everywhere else) doesn't model
 * this role yet.
 */
export default function RequireSuperAdmin({ children }: { children: ReactNode }) {
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

  if ((user.role as string) !== "super_admin") {
    return (
      <Result
        status="403"
        title="Access restricted"
        subTitle="This area is for platform administrators only."
        style={{ marginTop: 80 }}
      />
    );
  }

  return <>{children}</>;
}
