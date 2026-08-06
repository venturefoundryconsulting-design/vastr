import { theme as antdTheme, type ThemeConfig } from "antd";

// Default brand anchor - matches the PDF letterhead color (app/services/pdf.py
// BRAND) so printed documents read as the same identity when a tenant hasn't
// set their own primary_color yet. Still exported for the pages that
// deliberately don't take tenant theming (Login/Landing render before a
// tenant is authenticated; the Super Admin portal is intentionally a
// different, non-tenant brand - see admin/SuperAdminLayout.tsx).
export const BRAND = "#9d174d";
export const BRAND_DARK = "#6b1038";
export const INK = "#221019";

/** Builds the antd theme for the authenticated tenant app. Called with the
 * current tenant's primary_color (see context/TenantContext.tsx) so the
 * whole app re-themes at runtime; omitting it (or passing an invalid value)
 * falls back to the same BRAND used everywhere else - a tenant that hasn't
 * set a color sees exactly what Tanisi always saw. */
export function buildTheme(primaryColor?: string | null, darkMode?: boolean): ThemeConfig {
  const color = primaryColor || BRAND;
  return {
    algorithm: darkMode ? antdTheme.darkAlgorithm : undefined,
    token: {
      colorPrimary: color,
      colorLink: color,
      colorLinkHover: "#c2185b",
      colorInfo: color,
      colorSuccess: "#16a34a",
      colorWarning: "#d97706",
      colorError: "#dc2626",
      borderRadius: 10,
      borderRadiusLG: 14,
      borderRadiusSM: 8,
      fontFamily:
        "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif",
      fontSize: 14,
      colorBgLayout: darkMode ? "#161018" : "#f7f5f8",
      colorBorderSecondary: darkMode ? "#3a2c34" : "#eee3ea",
      boxShadowTertiary: "0 2px 8px rgba(157, 23, 77, 0.06)",
      // Softer, brand-tinted elevation for floating surfaces (Modal/Drawer/Dropdown/
      // Popover all derive from this) instead of antd's default flat gray shadow.
      boxShadow: "0 6px 16px rgba(34, 16, 25, 0.08), 0 3px 6px rgba(34, 16, 25, 0.05)",
      boxShadowSecondary: "0 10px 28px rgba(34, 16, 25, 0.12), 0 4px 10px rgba(34, 16, 25, 0.06)",
    },
    components: {
      Layout: {
        siderBg: "#221019",
        headerBg: darkMode ? "#1f171c" : "#ffffff",
        bodyBg: darkMode ? "#161018" : "#f7f5f8",
        headerHeight: 56,
      },
      Modal: {
        borderRadiusLG: 16,
        headerBg: "transparent",
      },
      Dropdown: {
        borderRadiusLG: 12,
      },
      Popover: {
        borderRadiusLG: 12,
      },
      Tooltip: {
        borderRadius: 8,
      },
      Menu: {
        darkItemBg: "transparent",
        darkItemSelectedBg: color,
        darkItemHoverBg: "rgba(255,255,255,0.06)",
        darkItemColor: "rgba(255,255,255,0.72)",
        darkItemSelectedColor: "#ffffff",
        itemBorderRadius: 8,
        itemMarginInline: 12,
      },
      Card: {
        borderRadiusLG: 16,
        boxShadowTertiary: "0 2px 10px rgba(34, 16, 25, 0.06)",
        headerFontSize: 15,
      },
      Button: {
        borderRadius: 8,
        controlHeight: 36,
        fontWeight: 600,
      },
      Table: {
        borderRadiusLG: 12,
        headerBg: darkMode ? "#241a20" : "#faf7f8",
        headerColor: darkMode ? "#c9b8c0" : "#6b5560",
        rowHoverBg: darkMode ? "#241a20" : "#fdf5f8",
        cellPaddingBlock: 10,
        cellPaddingInline: 12,
        cellFontSize: 13.5,
        headerSplitColor: "transparent",
      },
      Statistic: {
        titleFontSize: 13,
      },
      Input: {
        controlHeight: 36,
        borderRadius: 8,
      },
      Select: {
        controlHeight: 36,
        borderRadius: 8,
      },
      Tag: {
        borderRadiusSM: 6,
      },
    },
  };
}

// Static default - still used by Login.tsx, Landing.tsx, and anywhere else
// rendered outside the tenant-themed app (see buildTheme's docstring).
const theme: ThemeConfig = buildTheme();

export default theme;
