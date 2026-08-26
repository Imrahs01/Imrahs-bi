"""
Generalized BI Analysis Engine
-------------------------------
Works for ANY business (fashion, electronics, food, services, etc).
Takes raw uploaded tables with arbitrary column names and:
  1. Auto-detects what each column represents (date, revenue, cost, category, etc.)
  2. Computes a standard set of KPIs from whatever fields are actually present
  3. Detects anomalies/signals the same way as the retail prototype

Design principle: never assume a fixed schema. Every KPI is computed
defensively — if a required field wasn't found, that KPI/signal is skipped
rather than crashing, so partial data still produces useful output.
"""

import pandas as pd
import numpy as np
import re
from difflib import SequenceMatcher


# ---------------------------------------------------------------
# 1. COLUMN AUTO-DETECTION
# ---------------------------------------------------------------
# Each "field" we care about has a list of likely name patterns.
# We match uploaded column names against these using fuzzy + keyword logic.

FIELD_SYNONYMS = {
    "date":        ["date", "order_date", "sale_date", "transaction_date", "created_at", "day"],
    "revenue":      ["revenue", "sales", "amount", "total", "price_total", "net_sales",
                     "sale_amount", "total_price", "gross_sales"],
    "cost":         ["cost", "unit_cost", "cogs", "cost_of_goods", "cost_price"],
    "quantity":     ["quantity", "qty", "units", "units_sold", "qty_sold", "count"],
    "unit_price":   ["unit_price", "price", "selling_price", "list_price"],
    "product":      ["product", "product_name", "item", "item_name", "sku", "product_id"],
    "category":     ["category", "product_category", "type", "collection", "product_type",
                     "department", "class"],
    "store":        ["store", "store_id", "store_name", "location", "branch", "outlet"],
    "region":       ["region", "area", "territory", "zone", "state", "province"],
    "channel":      ["channel", "sales_channel", "platform", "source"],
    "employee":     ["employee", "employee_id", "employee_name", "staff", "salesperson", "agent"],
    "customer":     ["customer", "customer_id", "client", "client_id", "buyer"],
    "segment":      ["segment", "customer_segment", "customer_type", "tier", "membership"],
    "campaign":     ["campaign", "campaign_id", "campaign_name", "promo", "promotion"],
    "spend":        ["spend", "budget", "ad_spend", "marketing_spend", "cost_spend"],
    "return_flag":  ["return", "returned", "is_return", "refund", "return_reason", "reason"],
    "delivery_partner": ["delivery_partner", "courier", "carrier", "shipper", "logistics_partner"],
    "on_time":      ["on_time", "delivered_on_time", "late", "delay"],
    "rating":       ["rating", "review_score", "csat", "customer_rating", "satisfaction"],
    "stock":        ["stock", "stock_on_hand", "inventory", "quantity_on_hand", "on_hand"],
    "reorder_point":["reorder_point", "reorder_level", "min_stock", "safety_stock"],
    "target":       ["target", "goal", "quota", "revenue_target"],
    "discount":     ["discount", "discount_pct", "discount_percent", "markdown"],
}


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


MATCH_THRESHOLD = 0.72
SUBSTRING_MIN_LEN = 5  # only treat "X in Y" as a strong signal if X is at least this long


def detect_columns(df: pd.DataFrame) -> dict:
    """
    Returns a mapping like {"revenue": "Net_Sales_USD", "date": "Order Date", ...}
    Only includes fields that were confidently matched. Uses a global greedy
    assignment so a single source column can't be claimed by multiple fields,
    and only the single best-fitting column is kept per field.
    """
    normalized_cols = {_normalize(c): c for c in df.columns}

    # Build all candidate (field, column, score) triples above threshold
    candidates = []
    for field, synonyms in FIELD_SYNONYMS.items():
        for syn in synonyms:
            syn_norm = _normalize(syn)
            for col_norm, original_col in normalized_cols.items():
                if syn_norm == col_norm:
                    score = 1.0
                else:
                    score = _similarity(syn_norm, col_norm)
                    if len(syn_norm) >= SUBSTRING_MIN_LEN and syn_norm in col_norm:
                        score = max(score, 0.9)
                    elif len(col_norm) >= SUBSTRING_MIN_LEN and col_norm in syn_norm:
                        score = max(score, 0.9)
                if score >= MATCH_THRESHOLD:
                    candidates.append((score, field, original_col))

    # Greedy assignment: highest-confidence matches win first; each field and
    # each column can only be used once.
    candidates.sort(key=lambda x: x[0], reverse=True)
    mapping = {}
    used_cols = set()
    for score, field, col in candidates:
        if field in mapping or col in used_cols:
            continue
        mapping[field] = col
        used_cols.add(col)

    # dtype sanity check: date field must be parseable as a date
    if "date" in mapping:
        try:
            pd.to_datetime(df[mapping["date"]], errors="raise")
        except Exception:
            del mapping["date"]

    # numeric sanity check for numeric fields
    for f in ["revenue", "cost", "quantity", "unit_price", "spend", "stock",
              "reorder_point", "target", "discount", "rating"]:
        if f in mapping:
            col = mapping[f]
            numeric = pd.to_numeric(df[col], errors="coerce")
            if numeric.notna().mean() < 0.5:  # less than half the values are numeric
                del mapping[f]

    return mapping


def apply_mapping(df: pd.DataFrame, mapping: dict) -> pd.DataFrame:
    """Renames columns to standard field names and derives revenue/cost if needed."""
    std = df.rename(columns={v: k for k, v in mapping.items()})
    std = std.loc[:, ~std.columns.duplicated()]

    if "date" in std.columns:
        std["date"] = pd.to_datetime(std["date"], errors="coerce")

    for f in ["revenue", "cost", "quantity", "unit_price", "spend", "stock",
              "reorder_point", "target", "discount", "rating"]:
        if f in std.columns:
            std[f] = pd.to_numeric(std[f], errors="coerce")

    # Derive revenue if missing but unit_price * quantity available
    if "revenue" not in std.columns and {"unit_price", "quantity"}.issubset(std.columns):
        std["revenue"] = std["unit_price"] * std["quantity"]

    # Derive cost if missing but we at least have revenue (assume unknown margin -> skip)
    return std


# ---------------------------------------------------------------
# 2. GENERALIZED KPI + SIGNAL ENGINE
# ---------------------------------------------------------------

def analyze_transactions(df: pd.DataFrame, mapping: dict, business_name: str = "Business") -> dict:
    """
    Main entry point. df = raw uploaded transactions table.
    mapping = output of detect_columns (or a manually-confirmed mapping from the UI).
    Returns the same shape of JSON the dashboard expects, built only from
    whatever fields are actually present.
    """
    std = apply_mapping(df, mapping)
    out = {"business_name": business_name, "fields_detected": list(mapping.keys()),
           "fields_missing": [f for f in FIELD_SYNONYMS if f not in mapping],
           "row_count": int(len(std))}

    has = lambda *fields: all(f in std.columns for f in fields)

    # ---- Headline + monthly trend ----
    if has("date", "revenue"):
        std["month"] = std["date"].dt.to_period("M").astype(str)
        monthly = std.groupby("month").agg(revenue=("revenue", "sum")).reset_index()
        if "cost" in std.columns:
            monthly["profit"] = std.groupby("month")["revenue"].sum().values - std.groupby("month")["cost"].sum().values
            monthly["margin_pct"] = round(monthly["profit"] / monthly["revenue"] * 100, 2)
        monthly["orders"] = std.groupby("month").size().values
        monthly = monthly.sort_values("month")
        out["monthly_trend"] = monthly.round(2).to_dict(orient="records")

        total_revenue = std["revenue"].sum()
        headline = {"total_revenue": round(float(total_revenue), 2), "total_orders": int(len(std))}
        if "cost" in std.columns:
            total_profit = total_revenue - std["cost"].sum()
            headline["total_profit"] = round(float(total_profit), 2)
            headline["overall_margin_pct"] = round(float(total_profit / total_revenue * 100), 2)
        if len(monthly) >= 6:
            f3, l3 = monthly.head(3), monthly.tail(3)
            headline["revenue_growth_pct_first3_vs_last3"] = round(
                float((l3["revenue"].mean() - f3["revenue"].mean()) / f3["revenue"].mean() * 100), 2)
            if "margin_pct" in monthly.columns:
                headline["margin_change_points_first3_vs_last3"] = round(
                    float(l3["margin_pct"].mean() - f3["margin_pct"].mean()), 2)
        out["headline"] = headline

    # ---- By category ----
    if has("category", "revenue"):
        agg = {"revenue": ("revenue", "sum")}
        if "cost" in std.columns:
            agg["profit"] = ("revenue", "sum")  # placeholder, computed below
        by_cat = std.groupby("category").agg(revenue=("revenue", "sum")).reset_index()
        if "cost" in std.columns:
            cost_by_cat = std.groupby("category")["cost"].sum()
            by_cat["profit"] = by_cat["revenue"] - by_cat["category"].map(cost_by_cat)
            by_cat["margin_pct"] = round(by_cat["profit"] / by_cat["revenue"] * 100, 2)
        out["by_category"] = by_cat.sort_values("revenue", ascending=False).round(2).to_dict(orient="records")

    # ---- By product ----
    if has("product", "revenue"):
        by_prod = std.groupby("product").agg(revenue=("revenue", "sum")).reset_index()
        if "quantity" in std.columns:
            by_prod["units"] = std.groupby("product")["quantity"].sum().values
        out["top_products"] = by_prod.sort_values("revenue", ascending=False).head(10).round(2).to_dict(orient="records")
        out["bottom_products"] = by_prod.sort_values("revenue", ascending=True).head(5).round(2).to_dict(orient="records")

    # ---- By store / region ----
    for dim in ["store", "region"]:
        if has(dim, "revenue"):
            g = std.groupby(dim).agg(revenue=("revenue", "sum")).reset_index()
            if "cost" in std.columns:
                cost_g = std.groupby(dim)["cost"].sum()
                g["profit"] = g["revenue"] - g[dim].map(cost_g)
                g["margin_pct"] = round(g["profit"] / g["revenue"] * 100, 2)
            out[f"by_{dim}"] = g.sort_values("revenue", ascending=False).round(2).to_dict(orient="records")

    # ---- Returns / quality ----
    if has("return_flag", "category") or has("return_flag", "product"):
        dim = "category" if "category" in std.columns else "product"
        ret_col = std["return_flag"]
        is_return = ret_col.astype(str).str.lower().isin(["1", "true", "yes", "y"]) | pd.notna(ret_col) & (ret_col.astype(str) != "")
        total_by = std.groupby(dim).size()
        ret_by = std[is_return].groupby(dim).size()
        combo = pd.concat([total_by.rename("total"), ret_by.rename("returns")], axis=1).fillna(0)
        combo["return_rate_pct"] = round(combo["returns"] / combo["total"] * 100, 2)
        out["return_rate_by_" + dim] = combo.reset_index().sort_values("return_rate_pct", ascending=False).to_dict(orient="records")

    # ---- Marketing campaign ROI ----
    if has("campaign", "revenue", "spend"):
        camp = std.groupby("campaign").agg(revenue=("revenue", "sum"), spend=("spend", "first")).reset_index()
        camp["revenue_per_spend"] = round(camp["revenue"] / camp["spend"], 2)
        out["campaign_roi"] = camp.sort_values("revenue_per_spend", ascending=False).round(2).to_dict(orient="records")

    # ---- Inventory ----
    if has("store", "stock", "reorder_point") or has("product", "stock", "reorder_point"):
        dim = "store" if "store" in std.columns else "product"
        inv = std[[c for c in [dim, "product", "stock", "reorder_point"] if c in std.columns]].drop_duplicates()
        inv["status"] = np.where(inv["stock"] <= inv["reorder_point"] * 0.3, "Stockout risk",
                          np.where(inv["stock"] >= inv["reorder_point"] * 4, "Excess inventory", "Healthy"))
        out["stockout_risk_items"] = inv[inv["status"] == "Stockout risk"].round(2).to_dict(orient="records")[:30]
        out["excess_inventory_items"] = inv[inv["status"] == "Excess inventory"].round(2).to_dict(orient="records")[:30]

    # ---- Delivery partner performance ----
    if has("delivery_partner"):
        g = std.groupby("delivery_partner")
        perf = pd.DataFrame({"deliveries": g.size()})
        if "on_time" in std.columns:
            ontime = std["on_time"].astype(str).str.lower().isin(["1", "true", "yes", "y", "on time", "on-time"])
            perf["on_time_rate_pct"] = round(std.assign(_ot=ontime).groupby("delivery_partner")["_ot"].mean() * 100, 1)
        if "rating" in std.columns:
            perf["avg_rating"] = round(g["rating"].mean(), 2)
        out["delivery_partner_performance"] = perf.reset_index().sort_values(
            perf.columns[0] if "on_time_rate_pct" not in perf.columns else "on_time_rate_pct"
        ).round(2).to_dict(orient="records")

    # ---- Customer segment value ----
    if has("segment", "revenue"):
        agg = {"revenue": ("revenue", "sum"), "orders": ("revenue", "count")}
        seg = std.groupby("segment").agg(**agg).reset_index()
        if "customer" in std.columns:
            seg["customers"] = std.groupby("segment")["customer"].nunique().values
            seg["revenue_per_customer"] = round(seg["revenue"] / seg["customers"], 2)
        out["customer_segment_value"] = seg.sort_values("revenue", ascending=False).round(2).to_dict(orient="records")

    # ---- Employee performance ----
    if has("employee", "revenue"):
        emp = std.groupby("employee").agg(revenue=("revenue", "sum")).reset_index()
        if "cost" in std.columns:
            cost_e = std.groupby("employee")["cost"].sum()
            emp["profit"] = emp["revenue"] - emp["employee"].map(cost_e)
            emp["margin_pct"] = round(emp["profit"] / emp["revenue"] * 100, 2)
        out["top_employees_by_revenue"] = emp.sort_values("revenue", ascending=False).head(10).round(2).to_dict(orient="records")

    # ---- Targets ----
    if has("target", "revenue") and "region" in std.columns:
        g = std.groupby("region").agg(revenue=("revenue", "sum"), target=("target", "mean")).reset_index()
        g["attainment_pct"] = round(g["revenue"] / g["target"] * 100, 1)
        out["target_attainment_by_region"] = g.sort_values("attainment_pct").round(2).to_dict(orient="records")

    out["signals"] = generate_signals(out)
    return out


# ---------------------------------------------------------------
# 3. SIGNAL / ANOMALY GENERATION (dimension-agnostic)
# ---------------------------------------------------------------

def generate_signals(out: dict) -> list:
    signals = []
    h = out.get("headline", {})

    if "revenue_growth_pct_first3_vs_last3" in h and "margin_change_points_first3_vs_last3" in h:
        if h["revenue_growth_pct_first3_vs_last3"] > 5 and h["margin_change_points_first3_vs_last3"] < -0.5:
            signals.append({
                "severity": "risk", "area": "Profitability",
                "title": "Revenue growth is outpacing profitability",
                "detail": f"Revenue grew {h['revenue_growth_pct_first3_vs_last3']:.1f}% while margin fell "
                          f"{abs(h['margin_change_points_first3_vs_last3']):.1f} points over the same period.",
                "action": "Audit discounting and cost trends before scaling further."})

    for key in [k for k in out if k.startswith("return_rate_by_")]:
        for row in out[key]:
            if row.get("return_rate_pct", 0) > 8:
                label = row.get("category") or row.get("product") or "Item"
                signals.append({
                    "severity": "risk", "area": "Product quality",
                    "title": f"{label} has an unusually high return rate",
                    "detail": f"{label} shows a {row['return_rate_pct']}% return rate.",
                    "action": "Investigate quality/fit issues with the supplier before the next reorder."})

    if "campaign_roi" in out and len(out["campaign_roi"]) >= 2:
        sorted_camps = sorted(out["campaign_roi"], key=lambda r: r["revenue_per_spend"])
        worst, best = sorted_camps[0], sorted_camps[-1]
        signals.append({"severity": "risk", "area": "Marketing ROI",
            "title": f"Weakest campaign: {worst.get('campaign')}",
            "detail": f"Returned only {worst['revenue_per_spend']}x revenue per dollar spent.",
            "action": "Reallocate this budget toward better-performing campaigns."})
        signals.append({"severity": "opportunity", "area": "Marketing ROI",
            "title": f"Strongest campaign: {best.get('campaign')}",
            "detail": f"Returned {best['revenue_per_spend']}x revenue per dollar spent — the most efficient.",
            "action": "Consider increasing budget allocation here."})

    if out.get("stockout_risk_items"):
        signals.append({"severity": "risk", "area": "Inventory",
            "title": "Stockout risk detected",
            "detail": f"{len(out['stockout_risk_items'])} item/location combinations are near stockout.",
            "action": "Trigger expedited replenishment for flagged items."})
    if out.get("excess_inventory_items"):
        signals.append({"severity": "risk", "area": "Inventory",
            "title": "Excess inventory tying up capital",
            "detail": f"{len(out['excess_inventory_items'])} item/location combinations are overstocked.",
            "action": "Run a clearance promotion or transfer stock to higher-demand locations."})

    if "delivery_partner_performance" in out:
        for row in out["delivery_partner_performance"]:
            if row.get("on_time_rate_pct", 100) < 70 or row.get("avg_rating", 5) < 3.5:
                signals.append({"severity": "risk", "area": "Delivery/Logistics",
                    "title": f"{row['delivery_partner']} underperforming",
                    "detail": f"On-time rate {row.get('on_time_rate_pct','-')}%, rating {row.get('avg_rating','-')}.",
                    "action": "Review this partner's SLA or shift volume elsewhere."})

    if "target_attainment_by_region" in out:
        for row in out["target_attainment_by_region"]:
            if row["attainment_pct"] < 90:
                signals.append({"severity": "risk", "area": "Targets",
                    "title": f"{row['region']} missing revenue targets",
                    "detail": f"Averaging {row['attainment_pct']}% of target.",
                    "action": "Diagnose root cause or reassess whether the target is realistic."})

    if "customer_segment_value" in out and out["customer_segment_value"]:
        top = out["customer_segment_value"][0]
        signals.append({"severity": "opportunity", "area": "Customer segments",
            "title": f"{top['segment']} is the top revenue segment",
            "detail": f"Generates {top['revenue']:.0f} in total revenue — the highest of any segment.",
            "action": f"Prioritize retention and personalized offers for {top['segment']} customers."})

    return signals
