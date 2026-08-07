import type { UserRole } from "../api/types";

// The original three (outlet_staff/manager/admin) keep their original ranks
// unchanged - every existing minRole check in the app still behaves exactly
// as before. The four newer roles are specializations more than a strict
// "higher/lower" fit (see app/permissions/catalog.py on the backend for the
// real capability grants each gets), so this ladder is a coarse best-effort
// mapping for nav-visibility purposes only - it is NOT how access is
// actually enforced (the backend is the source of truth for that): sales/
// inventory/viewer sit at the same floor as outlet_staff (day-to-day
// operational roles), and tenant_owner sits with admin (the backend's
// require_admin/require_manager_up already treat the two as equivalent).
const ROLE_RANK: Record<UserRole, number> = {
  viewer: 0,
  outlet_staff: 0,
  sales: 0,
  inventory: 0,
  manager: 1,
  admin: 2,
  tenant_owner: 2,
};

export function hasMinRole(role: UserRole | undefined, minRole: UserRole | undefined): boolean {
  if (!minRole) return true;
  if (!role) return false;
  return ROLE_RANK[role] >= ROLE_RANK[minRole];
}

// super_admin is intentionally outside the UserRole type (see api/types.ts) -
// checked as a raw string here since it never appears in the tenant rank
// ladder above. Used anywhere a logo/brand click needs to land on "the
// user's own home" (Landing, Login, Signup) rather than a hardcoded route.
export function homeRouteFor(role: string | undefined): string {
  if (!role) return "/";
  return role === "super_admin" ? "/platform-admin/overview" : "/dashboard";
}
