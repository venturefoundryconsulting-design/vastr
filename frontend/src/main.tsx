import { InboxOutlined } from "@ant-design/icons";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConfigProvider, Empty } from "antd";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { AuthProvider } from "./context/AuthContext";
import { TenantProvider, useTenant } from "./context/TenantContext";
import { buildTheme } from "./theme";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

// Replaces antd's bare "No data" default across every Table/List/Select in the
// app with one consistent, friendlier empty state - a single change here beats
// hand-customizing empty text on every individual table.
function renderEmpty() {
  return (
    <Empty
      image={<InboxOutlined style={{ fontSize: 36, color: "#d1c0c8" }} />}
      description={<span style={{ color: "#9c8a92" }}>Nothing here yet</span>}
      styles={{ image: { height: 36, marginBottom: 8 } }}
    />
  );
}

// Reads the current tenant's branding (once known) and the local dark-mode
// preference, and re-themes the whole app at runtime. Before a tenant is
// known (logged out, or still loading) this renders with the same static
// default theme the app always used - zero visual change for anyone who
// hasn't set a color.
function ThemedApp() {
  const { tenant, darkMode } = useTenant();
  // antd's cssinjs style cache doesn't always pick up a token-only change
  // (colorPrimary) on an already-mounted ConfigProvider - a `key` tied to
  // the actual theme inputs forces a clean remount so every descendant
  // (including portaled content like modals) re-registers its styles
  // against the current tenant color instead of serving stale cached CSS.
  const themeKey = `${tenant?.primary_color ?? "default"}-${darkMode ? "dark" : "light"}`;
  return (
    <ConfigProvider key={themeKey} theme={buildTheme(tenant?.primary_color, darkMode)} renderEmpty={renderEmpty}>
      <App />
    </ConfigProvider>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter basename={import.meta.env.BASE_URL.replace(/\/$/, "")}>
        <AuthProvider>
          <TenantProvider>
            <ThemedApp />
          </TenantProvider>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
);
