import type { ThemeConfig } from "antd";

// Brand anchor matches the PDF letterhead color (app/services/pdf.py BRAND) so
// printed documents and the on-screen app read as the same identity.
export const BRAND = "#9d174d";
export const BRAND_DARK = "#6b1038";
export const INK = "#221019";

const theme: ThemeConfig = {
  token: {
    colorPrimary: BRAND,
    colorLink: BRAND,
    colorLinkHover: "#c2185b",
    colorInfo: BRAND,
    colorSuccess: "#16a34a",
    colorWarning: "#d97706",
    colorError: "#dc2626",
    borderRadius: 10,
    borderRadiusLG: 14,
    borderRadiusSM: 8,
    fontFamily:
      "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif",
    fontSize: 14,
    colorBgLayout: "#f7f5f8",
    colorBorderSecondary: "#eee3ea",
    boxShadowTertiary: "0 2px 8px rgba(157, 23, 77, 0.06)",
    // Softer, brand-tinted elevation for floating surfaces (Modal/Drawer/Dropdown/
    // Popover all derive from this) instead of antd's default flat gray shadow.
    boxShadow: "0 6px 16px rgba(34, 16, 25, 0.08), 0 3px 6px rgba(34, 16, 25, 0.05)",
    boxShadowSecondary: "0 10px 28px rgba(34, 16, 25, 0.12), 0 4px 10px rgba(34, 16, 25, 0.06)",
  },
  components: {
    Layout: {
      siderBg: "#221019",
      headerBg: "#ffffff",
      bodyBg: "#f7f5f8",
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
      darkItemSelectedBg: BRAND,
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
      headerBg: "#faf7f8",
      headerColor: "#6b5560",
      rowHoverBg: "#fdf5f8",
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

export default theme;
