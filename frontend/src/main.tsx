import { InboxOutlined } from "@ant-design/icons";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConfigProvider, Empty } from "antd";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { AuthProvider } from "./context/AuthContext";
import theme from "./theme";
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

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ConfigProvider theme={theme} renderEmpty={renderEmpty}>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter basename={import.meta.env.BASE_URL.replace(/\/$/, "")}>
          <AuthProvider>
            <App />
          </AuthProvider>
        </BrowserRouter>
      </QueryClientProvider>
    </ConfigProvider>
  </React.StrictMode>
);
