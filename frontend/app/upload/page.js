"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "../../lib/supabaseClient";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL;

export default function UploadPage() {
  const router = useRouter();
  const [session, setSession] = useState(null);
  const [file, setFile] = useState(null);
  const [step, setStep] = useState("select"); // select -> mapping -> analyzing -> done
  const [detectResult, setDetectResult] = useState(null);
  const [mapping, setMapping] = useState({});
  const [businessName, setBusinessName] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      if (!data.session) router.push("/login");
      else setSession(data.session);
    });
  }, [router]);

  const authHeader = () => ({ Authorization: `Bearer ${session?.access_token}` });

  const handleFileSelect = async (e) => {
    const f = e.target.files[0];
    if (!f) return;
    setFile(f);
    setError("");
    setStep("detecting");
    try {
      const formData = new FormData();
      formData.append("file", f);
      const res = await fetch(`${BACKEND_URL}/api/detect-columns`, {
        method: "POST",
        headers: authHeader(),
        body: formData,
      });
      if (!res.ok) throw new Error(`Backend error: ${res.status}`);
      const data = await res.json();
      setDetectResult(data);
      setMapping(data.auto_detected_mapping);
      setStep("mapping");
    } catch (err) {
      setError(err.message);
      setStep("select");
    }
  };

  const runAnalysis = async () => {
    setStep("analyzing");
    setError("");
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("mapping_json", JSON.stringify(mapping));
      formData.append("business_name", businessName || "My Business");
      const res = await fetch(`${BACKEND_URL}/api/analyze`, {
        method: "POST",
        headers: authHeader(),
        body: formData,
      });
      if (!res.ok) throw new Error(`Analysis failed: ${res.status}`);
      const result = await res.json();

      // Persist to Supabase so the dashboard can load it
      const { data: biz } = await supabase.from("businesses").select("id").limit(1).single();
      await supabase.from("analysis_snapshots").insert({
        business_id: biz.id,
        source_filename: file.name,
        column_mapping: mapping,
        result,
      });

      setStep("done");
      router.push("/dashboard");
    } catch (err) {
      setError(err.message);
      setStep("mapping");
    }
  };

  if (!session) return null;

  return (
    <div style={{ maxWidth: 640, margin: "40px auto", padding: 24 }}>
      <h1 style={{ fontSize: 22, marginBottom: 4 }}>Upload your business data</h1>
      <p style={{ color: "#7C8797", fontSize: 14, marginBottom: 24 }}>
        A CSV or Excel export of your sales/transactions works best. Pulse will auto-detect what each column means.
      </p>

      {step === "select" && (
        <div>
          <input
            type="text"
            placeholder="Business name"
            value={businessName}
            onChange={(e) => setBusinessName(e.target.value)}
            style={{ ...inputStyle, marginBottom: 12, width: "100%" }}
          />
          <label style={dropzoneStyle}>
            <input type="file" accept=".csv,.xlsx,.xls" onChange={handleFileSelect} style={{ display: "none" }} />
            Click to select a .csv or .xlsx file
          </label>
        </div>
      )}

      {step === "detecting" && <p>Reading your file and detecting columns…</p>}

      {step === "mapping" && detectResult && (
        <div>
          <h3 style={{ fontSize: 15, marginBottom: 8 }}>Confirm what we detected</h3>
          <p style={{ color: "#7C8797", fontSize: 13, marginBottom: 12 }}>
            {Object.keys(mapping).length} of {detectResult.columns_found_in_file.length} columns matched automatically.
            Adjust anything below, or leave blank if not applicable.
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 360, overflowY: "auto" }}>
            {Object.entries({ ...mapping, ...Object.fromEntries(detectResult.unmapped_fields.map(f => [f, ""])) }).map(
              ([field, col]) => (
                <div key={field} style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <span style={{ width: 130, fontSize: 12.5, color: "#7C8797", textTransform: "capitalize" }}>
                    {field.replace("_", " ")}
                  </span>
                  <select
                    value={col || ""}
                    onChange={(e) => setMapping({ ...mapping, [field]: e.target.value || undefined })}
                    style={{ ...inputStyle, flex: 1, padding: "6px 8px" }}
                  >
                    <option value="">— not in this file —</option>
                    {detectResult.columns_found_in_file.map((c) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                </div>
              )
            )}
          </div>
          <button onClick={runAnalysis} style={{ ...buttonStyle, marginTop: 18 }}>Run analysis</button>
        </div>
      )}

      {step === "analyzing" && <p>Computing KPIs and detecting signals…</p>}

      {error && <div style={{ color: "#F0576B", fontSize: 13, marginTop: 12 }}>{error}</div>}
    </div>
  );
}

const inputStyle = {
  background: "#151B24", border: "1px solid #262F3C", borderRadius: 8,
  padding: "10px 12px", color: "#EAEDF2", fontSize: 14, outline: "none",
};
const buttonStyle = {
  background: "#2DD4BF", border: "none", borderRadius: 8, padding: "10px 16px",
  color: "#0D1117", fontWeight: 600, cursor: "pointer", fontSize: 14,
};
const dropzoneStyle = {
  display: "block", textAlign: "center", padding: "40px 20px", borderRadius: 10,
  border: "1.5px dashed #262F3C", color: "#7C8797", cursor: "pointer", fontSize: 14,
};
