"use client";
import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "../../lib/supabaseClient";
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell,
} from "recharts";

const COLORS = { teal: "#2DD4BF", coral: "#F0576B", amber: "#F5A524", blue: "#5B8DEF",
  bg: "#0D1117", panel: "#151B24", border: "#262F3C", muted: "#7C8797" };

const fmtMoney = (n) => {
  if (n == null) return "-";
  const a = Math.abs(n);
  if (a >= 1e6) return (n / 1e6).toFixed(2) + "M";
  if (a >= 1e3) return (n / 1e3).toFixed(1) + "K";
  return n.toFixed(0);
};

export default function DashboardPage() {
  const router = useRouter();
  const [session, setSession] = useState(null);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [chatOpen, setChatOpen] = useState(false);
  const [messages, setMessages] = useState([
    { role: "assistant", content: "Ask me anything about your data — revenue, margins, returns, ROI, whatever was detected in your upload." }
  ]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const scrollRef = useRef(null);

  useEffect(() => {
    (async () => {
      const { data: sessionData } = await supabase.auth.getSession();
      if (!sessionData.session) { router.push("/login"); return; }
      setSession(sessionData.session);

      const { data: biz } = await supabase.from("businesses").select("id, name").limit(1).single();
      const { data: snapshot } = await supabase
        .from("analysis_snapshots")
        .select("result")
        .eq("business_id", biz.id)
        .order("created_at", { ascending: false })
        .limit(1)
        .single();

      if (!snapshot) { router.push("/upload"); return; }
      setData(snapshot.result);
      setLoading(false);
    })();
  }, [router]);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages]);

  const sendMessage = async (text) => {
    const q = (text ?? input).trim();
    if (!q || sending) return;
    const newMessages = [...messages, { role: "user", content: q }];
    setMessages(newMessages);
    setInput("");
    setSending(true);
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: newMessages, analysisData: data }),
      });
      const json = await res.json();
      setMessages([...newMessages, { role: "assistant", content: json.text || "I couldn't generate a response." }]);
    } catch {
      setMessages([...newMessages, { role: "assistant", content: "Something went wrong. Please try again." }]);
    } finally {
      setSending(false);
    }
  };

  if (loading) return <div style={{ padding: 40 }}>Loading your dashboard…</div>;

  const h = data.headline || {};

  return (
    <div style={{ minHeight: "100vh", paddingBottom: 100 }}>
      <div style={{ padding: "18px", borderBottom: `1px solid ${COLORS.border}`, display: "flex",
        justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <div style={{ fontWeight: 700, fontSize: 17 }}>{data.business_name || "Pulse"}</div>
          <div style={{ fontSize: 11, color: COLORS.muted }}>{data.row_count} rows analyzed</div>
        </div>
        <button onClick={() => router.push("/upload")} style={{ ...buttonStyle, padding: "6px 12px", fontSize: 12 }}>
          Upload new data
        </button>
      </div>

      <div style={{ padding: 18, maxWidth: 900, margin: "0 auto", display: "flex", flexDirection: "column", gap: 20 }}>

        {data.fields_missing && data.fields_missing.length > 0 && (
          <div style={{ fontSize: 12, color: COLORS.muted, background: COLORS.panel, border: `1px solid ${COLORS.border}`,
            borderRadius: 8, padding: "8px 12px" }}>
            Not tracked in your upload: {data.fields_missing.join(", ")}. Add these columns for deeper insights.
          </div>
        )}

        {/* KPIs */}
        {h.total_revenue != null && (
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            <Kpi label="Total Revenue" value={fmtMoney(h.total_revenue)} />
            {h.total_profit != null && <Kpi label="Total Profit" value={fmtMoney(h.total_profit)} sub={`${h.overall_margin_pct}% margin`} />}
            {h.revenue_growth_pct_first3_vs_last3 != null && (
              <Kpi label="Revenue Growth" value={`${h.revenue_growth_pct_first3_vs_last3 > 0 ? "+" : ""}${h.revenue_growth_pct_first3_vs_last3}%`} />
            )}
            <Kpi label="Orders" value={h.total_orders?.toLocaleString()} />
          </div>
        )}

        {/* Signals */}
        {data.signals && data.signals.length > 0 && (
          <div>
            <SectionTitle>Signals — {data.signals.length} findings</SectionTitle>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {data.signals.map((s, i) => (
                <div key={i} style={{ background: COLORS.panel, border: `1px solid ${COLORS.border}`, borderRadius: 8,
                  borderLeft: `3px solid ${s.severity === "risk" ? COLORS.coral : COLORS.teal}`, padding: "10px 14px" }}>
                  <div style={{ fontSize: 11, color: s.severity === "risk" ? COLORS.coral : COLORS.teal, textTransform: "uppercase" }}>
                    {s.severity} · {s.area}
                  </div>
                  <div style={{ fontWeight: 600, fontSize: 14, margin: "3px 0" }}>{s.title}</div>
                  <div style={{ fontSize: 13, color: "#C3CAD4" }}>{s.detail}</div>
                  <div style={{ fontSize: 12.5, marginTop: 4 }}><strong style={{ color: COLORS.teal }}>Action: </strong>{s.action}</div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Monthly trend */}
        {data.monthly_trend && (
          <ChartCard title="Revenue by Month">
            <BarChart data={data.monthly_trend}>
              <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
              <XAxis dataKey="month" tick={{ fill: COLORS.muted, fontSize: 10 }} />
              <YAxis tick={{ fill: COLORS.muted, fontSize: 10 }} tickFormatter={fmtMoney} />
              <Tooltip contentStyle={{ background: COLORS.panel, border: `1px solid ${COLORS.border}` }} />
              <Bar dataKey="revenue" fill={COLORS.blue} radius={[3,3,0,0]} />
            </BarChart>
          </ChartCard>
        )}

        {/* By category */}
        {data.by_category && (
          <ChartCard title="Revenue by Category">
            <BarChart data={data.by_category} layout="vertical" margin={{ left: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} horizontal={false} />
              <XAxis type="number" tick={{ fill: COLORS.muted, fontSize: 10 }} tickFormatter={fmtMoney} />
              <YAxis type="category" dataKey="category" tick={{ fill: "#EAEDF2", fontSize: 11 }} width={110} />
              <Tooltip contentStyle={{ background: COLORS.panel, border: `1px solid ${COLORS.border}` }} />
              <Bar dataKey="revenue" fill={COLORS.teal} radius={[0,4,4,0]} />
            </BarChart>
          </ChartCard>
        )}

        {/* Return rates - dynamic key name */}
        {Object.keys(data).filter(k => k.startsWith("return_rate_by_")).map((key) => (
          <ChartCard key={key} title={`Return Rate by ${key.replace("return_rate_by_", "")}`}>
            <BarChart data={data[key]}>
              <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
              <XAxis dataKey={Object.keys(data[key][0]).find(k => k !== "total" && k !== "returns" && k !== "return_rate_pct")}
                tick={{ fill: COLORS.muted, fontSize: 9 }} angle={-20} textAnchor="end" height={60} />
              <YAxis tick={{ fill: COLORS.muted, fontSize: 10 }} unit="%" />
              <Tooltip contentStyle={{ background: COLORS.panel, border: `1px solid ${COLORS.border}` }} />
              <Bar dataKey="return_rate_pct" radius={[4,4,0,0]}>
                {data[key].map((r, i) => <Cell key={i} fill={r.return_rate_pct > 8 ? COLORS.coral : COLORS.teal} />)}
              </Bar>
            </BarChart>
          </ChartCard>
        ))}

      </div>

      {!chatOpen && (
        <button onClick={() => setChatOpen(true)} style={{
          position: "fixed", bottom: 20, right: 20, width: 56, height: 56, borderRadius: 28,
          background: `linear-gradient(135deg, ${COLORS.teal}, ${COLORS.blue})`, border: "none", cursor: "pointer",
        }}>💬</button>
      )}

      {chatOpen && (
        <div style={{ position: "fixed", inset: 0, background: COLORS.bg, zIndex: 30, display: "flex", flexDirection: "column" }}>
          <div style={{ display: "flex", justifyContent: "space-between", padding: 16, borderBottom: `1px solid ${COLORS.border}` }}>
            <strong>Ask Pulse</strong>
            <button onClick={() => setChatOpen(false)} style={{ background: "none", border: "none", color: COLORS.muted, cursor: "pointer" }}>✕</button>
          </div>
          <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", padding: 16, display: "flex", flexDirection: "column", gap: 10 }}>
            {messages.map((m, i) => (
              <div key={i} style={{ alignSelf: m.role === "user" ? "flex-end" : "flex-start", maxWidth: "85%",
                background: m.role === "user" ? "#5B8DEF20" : COLORS.panel, border: `1px solid ${COLORS.border}`,
                borderRadius: 10, padding: "8px 12px", fontSize: 13.5, whiteSpace: "pre-wrap" }}>
                {m.content}
              </div>
            ))}
            {sending && <div style={{ color: COLORS.muted, fontSize: 13 }}>Analyzing…</div>}
          </div>
          <div style={{ display: "flex", gap: 8, padding: 12, borderTop: `1px solid ${COLORS.border}` }}>
            <input value={input} onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && sendMessage()}
              placeholder="Ask a question…" style={{ ...inputStyle, flex: 1 }} />
            <button onClick={() => sendMessage()} style={buttonStyle} disabled={sending}>Send</button>
          </div>
        </div>
      )}
    </div>
  );
}

function Kpi({ label, value, sub }) {
  return (
    <div style={{ background: COLORS.panel, border: `1px solid ${COLORS.border}`, borderRadius: 10,
      padding: "14px 16px", flex: "1 1 140px", minWidth: 140 }}>
      <div style={{ fontSize: 11, color: COLORS.muted, textTransform: "uppercase" }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700, marginTop: 4 }}>{value}</div>
      {sub && <div style={{ fontSize: 12, color: COLORS.muted, marginTop: 2 }}>{sub}</div>}
    </div>
  );
}
function SectionTitle({ children }) {
  return <h2 style={{ fontSize: 14, textTransform: "uppercase", letterSpacing: "0.03em", marginBottom: 10 }}>{children}</h2>;
}
function ChartCard({ title, children }) {
  return (
    <div style={{ background: COLORS.panel, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 16 }}>
      <SectionTitle>{title}</SectionTitle>
      <ResponsiveContainer width="100%" height={220}>{children}</ResponsiveContainer>
    </div>
  );
}

const inputStyle = { background: "#151B24", border: `1px solid ${COLORS.border}`, borderRadius: 8,
  padding: "10px 12px", color: "#EAEDF2", fontSize: 13.5, outline: "none" };
const buttonStyle = { background: COLORS.teal, border: "none", borderRadius: 8, padding: "8px 14px",
  color: COLORS.bg, fontWeight: 600, cursor: "pointer" };
