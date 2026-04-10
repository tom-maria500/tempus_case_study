"""Priority score = specialty × volume × engagement × Tempus-user status (normalized to 0–10).

Base score is computed from market_data.csv rows. Outcome logging adds a
`priority_adjustment` delta on top of the base (still clamped to 0–10).

The legacy `priority_score` column in CSV is ignored for ranking once this module is used.
"""

from __future__ import annotations

from datetime import date

import pandas as pd


def _specialty_weight(specialty: str) -> float:
    """Relative commercial/strategic weight by specialty line (0.82–1.0)."""
    s = (specialty or "").lower()
    if any(x in s for x in ("thoracic", "lung", "nsclc", "mesothelioma")):
        return 1.0
    if any(x in s for x in ("gi oncology", "gastrointestinal", "colorectal", "pancreatic")):
        return 0.96
    if "breast" in s:
        return 0.92
    if "medical oncology" in s or s.strip() == "medical oncology":
        return 0.94
    if any(x in s for x in ("hematology", "lymphoma", "melanoma")):
        return 0.88
    return 0.85


def _volume_weight(patients: int, df: pd.DataFrame) -> float:
    """Min–max annual patient volume across the cohort → 0.5–1.0."""
    col = df["estimated_annual_patients"].astype(float)
    pmin, pmax = float(col.min()), float(col.max())
    if pmax <= pmin:
        return 0.75
    p = float(patients)
    return 0.5 + 0.5 * (p - pmin) / (pmax - pmin)


def _engagement_weight(last_contact) -> float:
    """Recency of last CRM/market contact (proxy for engagement)."""
    if last_contact is None or (isinstance(last_contact, float) and pd.isna(last_contact)):
        return 0.68
    raw = str(last_contact).strip()
    if not raw:
        return 0.68
    try:
        d = date.fromisoformat(raw.split()[0])
    except (ValueError, TypeError):
        return 0.68
    days = (date.today() - d).days
    if days < 0:
        return 1.0
    if days <= 30:
        return 1.0
    if days <= 60:
        return 0.94
    if days <= 120:
        return 0.88
    if days <= 200:
        return 0.8
    return 0.7


def _tempus_user_weight(is_user: bool) -> float:
    """Favor net-new providers over existing Tempus users."""
    return 0.9 if is_user else 1.1


def row_priority_product(row: pd.Series, df: pd.DataFrame) -> float:
    """Raw multiplicative product before cohort normalization."""
    return (
        _specialty_weight(str(row["specialty"]))
        * _volume_weight(int(row["estimated_annual_patients"]), df)
        * _engagement_weight(row.get("last_contact_date"))
        * _tempus_user_weight(bool(row["current_tempus_user"]))
    )


def compute_base_score_series(df: pd.DataFrame) -> pd.Series:
    """Map specialty×volume×engagement×Tempus product to 0–10 within this dataframe."""
    products = df.apply(lambda r: row_priority_product(r, df), axis=1)
    pmin, pmax = float(products.min()), float(products.max())
    if pmax <= pmin:
        return pd.Series([5.0] * len(df), index=df.index, dtype=float)
    scaled = 10.0 * (products - pmin) / (pmax - pmin)
    return scaled


def row_effective_priority(row: pd.Series, df: pd.DataFrame, base_series: pd.Series) -> float:
    """Base (from formula) + optional CSV `priority_adjustment`, clamped to 0–10."""
    base = float(base_series.loc[row.name])
    adj = 0.0
    if "priority_adjustment" in row.index and row["priority_adjustment"] is not None:
        try:
            if not (isinstance(row["priority_adjustment"], float) and pd.isna(row["priority_adjustment"])):
                adj = float(row["priority_adjustment"])
        except (TypeError, ValueError):
            adj = 0.0
    return round(max(0.0, min(10.0, base + adj)), 1)


def explain_priority_row(row: pd.Series, df: pd.DataFrame, base_series: pd.Series) -> str:
    """Human-readable breakdown for docs/debug."""
    s = _specialty_weight(str(row["specialty"]))
    v = _volume_weight(int(row["estimated_annual_patients"]), df)
    e = _engagement_weight(row.get("last_contact_date"))
    t = _tempus_user_weight(bool(row["current_tempus_user"]))
    base = float(base_series.loc[row.name])
    prod = s * v * e * t
    return (
        f"specialty_w={s:.3f} × volume_w={v:.3f} × engagement_w={e:.3f} × tempus_w={t:.3f} "
        f"= product {prod:.4f} → base {base:.1f}/10"
    )
