import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Button,
  Collapse,
  Drawer,
  Empty,
  Input,
  Space,
  Tag,
  Typography,
  theme,
} from "antd";
import { QuestionCircleOutlined, SendOutlined } from "@ant-design/icons";
import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { askHelp, getHelpContext, type HelpSource } from "../api/help-endpoints";

interface Exchange {
  question: string;
  answer: string;
  grounded: boolean;
  sources: HelpSource[];
}

const SCREEN_LABEL: Record<string, string> = {
  "core-retail": "Core Retail",
  manufacturing: "Manufacturing",
  "crm-marketing": "CRM & Marketing",
  "workforce-admin": "Workforce & Admin",
  platform: "Platform",
};

/** The global "?" help entry point - deliberately reads from the same
 * knowledge base the documentation guides were generated from (see
 * app/services/knowledge_base.py), never from a separate copy. An answer is
 * either grounded in a real KB entry or says plainly that it found nothing,
 * never a confident guess dressed up as one. */
export default function HelpWidget() {
  const { token } = theme.useToken();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [history, setHistory] = useState<Exchange[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  const { data: context } = useQuery({
    queryKey: ["help-context", location.pathname],
    queryFn: () => getHelpContext(location.pathname).then((r) => r.data),
    enabled: open,
  });

  const ask = useMutation({
    mutationFn: (q: string) => askHelp(q, location.pathname).then((r) => r.data),
    onSuccess: (data, q) => {
      setHistory((h) => [...h, { question: q, answer: data.answer, grounded: data.grounded, sources: data.sources }]);
      setQuestion("");
      requestAnimationFrame(() => scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" }));
    },
  });

  useEffect(() => {
    if (!open) {
      setHistory([]);
      setQuestion("");
    }
  }, [open]);

  const submit = () => {
    const q = question.trim();
    if (!q || ask.isPending) return;
    ask.mutate(q);
  };

  return (
    <>
      <Button
        shape="circle"
        size="large"
        icon={<QuestionCircleOutlined />}
        onClick={() => setOpen(true)}
        title="Help"
        style={{
          position: "fixed",
          right: 24,
          bottom: 24,
          zIndex: 1000,
          background: token.colorPrimary,
          color: "#fff",
          border: "none",
          boxShadow: "0 4px 14px rgba(0,0,0,0.2)",
          width: 52,
          height: 52,
        }}
      />

      <Drawer
        title="Help"
        open={open}
        onClose={() => setOpen(false)}
        width={420}
        styles={{ body: { display: "flex", flexDirection: "column", padding: 0 } }}
      >
        <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", padding: "16px 20px" }}>
          {context?.module && (
            <div style={{ marginBottom: 16 }}>
              <Tag color="magenta">{SCREEN_LABEL[context.module] ?? context.module}</Tag>
              {history.length === 0 && (
                <Typography.Paragraph type="secondary" style={{ marginTop: 8, fontSize: 13 }}>
                  Showing help for the screen you're on. Ask a question below, or browse what's documented here.
                </Typography.Paragraph>
              )}
            </div>
          )}

          {history.length === 0 && context && context.entries.length > 0 && (
            <Collapse
              ghost
              size="small"
              items={context.entries.map((e) => ({
                key: e.id,
                label: e.title,
                children: <Typography.Text style={{ fontSize: 13.5 }}>{e.answer}</Typography.Text>,
              }))}
            />
          )}

          {history.length === 0 && (!context || context.entries.length === 0) && (
            <Empty
              description="Ask a question about the screen you're on, or anything else in the app."
              style={{ marginTop: 40 }}
            />
          )}

          <Space direction="vertical" style={{ width: "100%", marginTop: 12 }} size={16}>
            {history.map((ex, i) => (
              <div key={i}>
                <Typography.Text strong style={{ fontSize: 13.5 }}>
                  {ex.question}
                </Typography.Text>
                <div
                  style={{
                    marginTop: 6,
                    padding: "10px 12px",
                    borderRadius: 8,
                    background: ex.grounded ? "#f6f2f4" : "#fff7e6",
                    border: `1px solid ${ex.grounded ? "#eee3ea" : "#ffe7ba"}`,
                    fontSize: 13.5,
                  }}
                >
                  {ex.answer}
                  {ex.sources.length > 0 && (
                    <div style={{ marginTop: 8, display: "flex", flexWrap: "wrap", gap: 4 }}>
                      {ex.sources.map((s) => (
                        <Tag key={s.id} style={{ fontSize: 11 }}>
                          {s.title}
                        </Tag>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {ask.isPending && (
              <Typography.Text type="secondary" style={{ fontSize: 13 }}>
                Thinking…
              </Typography.Text>
            )}
          </Space>
        </div>

        <div style={{ borderTop: "1px solid #eee3ea", padding: 12 }}>
          <Space.Compact style={{ width: "100%" }}>
            <Input
              placeholder="Ask a question…"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onPressEnter={submit}
              disabled={ask.isPending}
            />
            <Button type="primary" icon={<SendOutlined />} onClick={submit} loading={ask.isPending} />
          </Space.Compact>
        </div>
      </Drawer>
    </>
  );
}
