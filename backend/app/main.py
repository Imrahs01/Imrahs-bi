"""
Pulse BI — Analysis Backend
----------------------------
Endpoints:
  POST /api/detect-columns   -> upload a file, get back the auto-detected mapping (for user confirmation)
  POST /api/analyze          -> upload a file + confirmed mapping, get back full KPI/signal JSON
  GET  /api/health           -> health check

Auth: every request must include a Supabase JWT in the Authorization header.
We verify it against Supabase's auth server before doing any work, and use
the authenticated user's business_id (from Supabase) to keep each business's
data isolated. No database writes happen in this file for the MVP — the
frontend is responsible for persisting the returned JSON to Supabase.
"""

import io
import os
import pandas as pd
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
import httpx

from engine import detect_columns, analyze_transactions

app = FastAPI(title="Pulse BI Analysis Engine")

# Allow requests from your deployed frontend. Set FRONTEND_URL as an env var
# in Railway/Render once you know your Vercel domain.
FRONTEND_URL = os.environ.get("FRONTEND_URL", "*")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL] if FRONTEND_URL != "*" else ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")


async def verify_user(authorization: str | None) -> dict:
    """Verifies the Supabase JWT and returns the user object. Raises 401 if invalid."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")
    token = authorization.removeprefix("Bearer ")

    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise HTTPException(status_code=500, detail="Server misconfigured: SUPABASE_URL/SUPABASE_ANON_KEY not set")

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={"Authorization": f"Bearer {token}", "apikey": SUPABASE_ANON_KEY},
        )
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return resp.json()


def read_uploaded_file(file: UploadFile, raw_bytes: bytes) -> pd.DataFrame:
    name = file.filename.lower()
    if name.endswith(".csv"):
        return pd.read_csv(io.BytesIO(raw_bytes))
    elif name.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(raw_bytes))
    else:
        raise HTTPException(status_code=400, detail="Unsupported file type. Please upload .csv or .xlsx")


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/detect-columns")
async def api_detect_columns(
    file: UploadFile = File(...),
    authorization: str | None = Header(None),
):
    await verify_user(authorization)
    raw = await file.read()
    df = read_uploaded_file(file, raw)
    mapping = detect_columns(df)
    return {
        "columns_found_in_file": list(df.columns),
        "auto_detected_mapping": mapping,
        "unmapped_fields": [f for f in [
            "date","revenue","cost","quantity","unit_price","product","category","store",
            "region","channel","employee","customer","segment","campaign","spend",
            "return_flag","delivery_partner","on_time","rating","stock","reorder_point","target","discount"
        ] if f not in mapping],
        "row_preview": df.head(5).fillna("").to_dict(orient="records"),
    }


@app.post("/api/analyze")
async def api_analyze(
    file: UploadFile = File(...),
    mapping_json: str = Form(...),   # JSON string, e.g. {"revenue": "Net_Sales_USD", ...}
    business_name: str = Form("Business"),
    authorization: str | None = Header(None),
):
    await verify_user(authorization)
    import json
    raw = await file.read()
    df = read_uploaded_file(file, raw)
    try:
        mapping = json.loads(mapping_json)
    except Exception:
        raise HTTPException(status_code=400, detail="mapping_json must be valid JSON")

    result = analyze_transactions(df, mapping, business_name=business_name)
    return result
