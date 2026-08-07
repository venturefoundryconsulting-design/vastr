import { CloseCircleFilled, RocketOutlined } from "@ant-design/icons";
import { Button, Card, Typography } from "antd";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { verifyEmail } from "../api/endpoints";
import { useAuth } from "../context/AuthContext";
import { BRAND, BRAND_DARK } from "../theme";

const CONFETTI_COLORS = ["#9d174d", "#c2185b", "#f472b6", "#fbbf24", "#34d399", "#60a5fa"];

function Confetti() {
  const pieces = useMemo(
    () =>
      Array.from({ length: 90 }, (_, i) => ({
        id: i,
        left: Math.random() * 100,
        delay: Math.random() * 0.6,
        duration: 2.4 + Math.random() * 1.6,
        color: CONFETTI_COLORS[i % CONFETTI_COLORS.length],
        size: 6 + Math.random() * 6,
        rotate: Math.random() * 360,
        drift: (Math.random() - 0.5) * 160,
      })),
    []
  );

  return (
    <div style={{ position: "fixed", inset: 0, pointerEvents: "none", overflow: "hidden", zIndex: 50 }}>
      <style>{`
        @keyframes confetti-fall {
          0% { transform: translateY(-10vh) translateX(0) rotate(0deg); opacity: 1; }
          100% { transform: translateY(110vh) translateX(var(--drift)) rotate(720deg); opacity: 0.9; }
        }
      `}</style>
      {pieces.map((p) => (
        <div
          key={p.id}
          style={{
            position: "absolute",
            top: 0,
            left: `${p.left}%`,
            width: p.size,
            height: p.size * 0.4,
            background: p.color,
            borderRadius: 2,
            transform: `rotate(${p.rotate}deg)`,
            animation: `confetti-fall ${p.duration}s ease-in ${p.delay}s 1 forwards`,
            // @ts-expect-error custom property consumed by the keyframe above
            "--drift": `${p.drift}px`,
          }}
        />
      ))}
    </div>
  );
}

type Status = "verifying" | "success" | "error";

export default function VerifyEmail() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { setToken } = useAuth();
  const [status, setStatus] = useState<Status>("verifying");
  const [errorMessage, setErrorMessage] = useState("");
  // The verification token is single-use server-side, so this call isn't
  // idempotent - a ref (not state) guard is required to survive React 18
  // StrictMode's intentional double-invoke of effects in development,
  // which would otherwise fire this twice and turn the second, now-stale
  // call into a false "invalid link" error.
  const hasVerified = useRef(false);

  useEffect(() => {
    if (hasVerified.current) return;
    hasVerified.current = true;

    const token = searchParams.get("token");
    if (!token) {
      setStatus("error");
      setErrorMessage("This verification link is missing its token.");
      return;
    }
    verifyEmail(token)
      .then((res) => {
        setToken(res.data.access_token);
        setStatus("success");
      })
      .catch((err) => {
        setStatus("error");
        setErrorMessage(err?.response?.data?.detail || "This verification link is invalid or has expired.");
      });
    // Only ever run once per mount - re-running on searchParams identity
    // churn would re-verify (and fail, since the token is single-use).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div
      style={{
        minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center",
        background: "#f7f5f8", padding: 24,
      }}
    >
      {status === "success" && <Confetti />}
      <Card style={{ width: 460, maxWidth: "100%", borderRadius: 20, border: "none", textAlign: "center" }} styles={{ body: { padding: "48px 36px" } }}>
        {status === "verifying" && (
          <>
            <div
              style={{
                width: 76, height: 76, borderRadius: "50%", margin: "0 auto 20px",
                background: `linear-gradient(135deg, ${BRAND_DARK}, ${BRAND})`,
                display: "flex", alignItems: "center", justifyContent: "center",
                animation: "pulse 1.4s ease-in-out infinite",
              }}
            >
              <style>{`@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.5; } }`}</style>
              <RocketOutlined style={{ fontSize: 32, color: "#fff" }} />
            </div>
            <Typography.Title level={4}>Verifying your email…</Typography.Title>
          </>
        )}

        {status === "success" && (
          <>
            <div
              style={{
                width: 76, height: 76, borderRadius: "50%", margin: "0 auto 20px",
                background: "linear-gradient(135deg, #16a34a, #22c55e)",
                display: "flex", alignItems: "center", justifyContent: "center",
                boxShadow: "0 8px 24px rgba(22,163,74,0.35)",
              }}
            >
              <RocketOutlined style={{ fontSize: 32, color: "#fff" }} />
            </div>
            <Typography.Title level={2} style={{ marginBottom: 8 }}>Welcome to Vastr!</Typography.Title>
            <Typography.Text type="secondary" style={{ fontSize: 15, display: "block", marginBottom: 32 }}>
              Your email is verified and your store is live. Let's set up your first sale.
            </Typography.Text>
            <Button
              type="primary" size="large"
              style={{ borderRadius: 10, minWidth: 220, height: 46 }}
              onClick={() => navigate("/dashboard")}
            >
              Go to my dashboard
            </Button>
          </>
        )}

        {status === "error" && (
          <>
            <CloseCircleFilled style={{ fontSize: 56, color: "#dc2626", marginBottom: 20 }} />
            <Typography.Title level={4} style={{ marginBottom: 8 }}>Verification failed</Typography.Title>
            <Typography.Text type="secondary" style={{ display: "block", marginBottom: 28 }}>
              {errorMessage}
            </Typography.Text>
            <Button type="primary" style={{ borderRadius: 10 }} onClick={() => navigate("/login")}>
              Go to sign in
            </Button>
          </>
        )}
      </Card>
    </div>
  );
}
