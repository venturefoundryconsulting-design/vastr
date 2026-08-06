import type { UserRole } from "../api/types";

const ROLE_RANK: Record<UserRole, number> = { outlet_staff: 0, manager: 1, admin: 2 };

export function hasMinRole(role: UserRole | undefined, minRole: UserRole | undefined): boolean {
  if (!minRole) return true;
  if (!role) return false;
  return ROLE_RANK[role] >= ROLE_RANK[minRole];
}
