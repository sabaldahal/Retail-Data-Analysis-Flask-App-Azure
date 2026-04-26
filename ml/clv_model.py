"""
Customer Lifetime Value prediction using Gradient Boosting.
Features: recency, frequency, monetary (RFM) + household demographics.
"""
import json
import os

USE_AZURE_SQL = bool(os.getenv("AZURE_SQL_CONNECTION_STRING") or os.getenv("AZURE_SQL_SERVER"))

if USE_AZURE_SQL:
    from db2 import get_db
else:
    from db import get_db


def _norm_category(value, default="UNKNOWN"):
    if value is None:
        return default
    text = str(value).strip().strip("'\"")
    if not text:
        return default
    if text.upper() in {"NULL", "NONE", "N/A", "NA"}:
        return default
    return text


def _safe_int(value, default=2):
    """Parse integer-like values while tolerating null-like strings from CSV uploads."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return int(value)

    text = str(value).strip().strip("'\"")
    if not text:
        return default

    if text.upper() in {"NULL", "NONE", "N/A", "NA"}:
        return default

    text = text.replace("+", "")
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return default

def run_clv():
    try:
        import numpy as np
        from sklearn.ensemble import GradientBoostingRegressor
        from sklearn.model_selection import train_test_split
        from sklearn.preprocessing import LabelEncoder
        from sklearn.metrics import r2_score, mean_absolute_error

        db = get_db()

        # Build RFM features per household
        rows = db.execute("""
            SELECT
                s.HSHD_NUM,
                s.last_week,
                s.frequency,
                s.monetary,
                h.INCOME_RANGE,
                h.HH_SIZE,
                h.CHILDREN,
                h.AGE_RANGE
            FROM (
                SELECT
                    HSHD_NUM,
                    MAX(WEEK_NUM + (YEAR-2018)*52) AS last_week,
                    COUNT(DISTINCT BASKET_NUM) AS frequency,
                    SUM(SPEND) AS monetary
                FROM transactions
                GROUP BY HSHD_NUM
            ) s
            LEFT JOIN households h ON s.HSHD_NUM = h.HSHD_NUM
        """).fetchall()

        if len(rows) < 20:
            return {
                "warning": "Not enough household data to train CLV yet.",
                "available_households": len(rows),
                "required_households": 20,
                "error": None,
            }

        data = [dict(r) for r in rows]
        max_week = max(d["last_week"] or 0 for d in data)

        income_map = {"UNDER 35K":1,"35-49K":2,"50-74K":3,"75-99K":4,"100-150K":5,"150K+":6}
        age_map = {"19-24":1,"25-34":2,"35-44":3,"45-54":4,"55-64":5,"65+":6}

        X, y = [], []
        for d in data:
            recency = max_week - (d["last_week"] or 0)
            freq = d["frequency"] or 1
            monetary = d["monetary"] or 0
            income = income_map.get(_norm_category(d["INCOME_RANGE"]), 3)
            hh_size = _safe_int(d["HH_SIZE"], default=2)
            children = 1 if d["CHILDREN"] == "Y" else 0
            age = age_map.get(_norm_category(d["AGE_RANGE"]), 3)
            X.append([recency, freq, monetary, income, hh_size, children, age])
            # CLV proxy = projected 1-year spend based on current rate
            weeks_active = max(1, 104 - recency)
            clv = (monetary / weeks_active) * 52
            y.append(clv)

        X = np.array(X)
        y = np.array(y)

        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        model = GradientBoostingRegressor(n_estimators=100, max_depth=4, learning_rate=0.1, random_state=42)
        model.fit(X_train, y_train)
        y_pred = model.predict(X_test)

        r2  = round(r2_score(y_test, y_pred), 3)
        mae = round(mean_absolute_error(y_test, y_pred), 2)

        feature_names = ["Recency","Frequency","Monetary","Income","HH Size","Children","Age"]
        importances = [round(float(v), 4) for v in model.feature_importances_]

        # Top 10 high-value customers
        all_pred = model.predict(X)
        top_idx = np.argsort(all_pred)[::-1][:10]
        top_customers = [
            {"hshd_num": int(data[i]["HSHD_NUM"]), "predicted_clv": round(float(all_pred[i]), 2)}
            for i in top_idx
        ]

        # Score distribution buckets
        buckets = {"<$500": 0, "$500-1000": 0, "$1000-2000": 0, "$2000+": 0}
        for v in all_pred:
            if v < 500: buckets["<$500"] += 1
            elif v < 1000: buckets["$500-1000"] += 1
            elif v < 2000: buckets["$1000-2000"] += 1
            else: buckets["$2000+"] += 1

        return {
            "model": "Gradient Boosting Regressor",
            "r2": r2,
            "mae": mae,
            "n_train": len(X_train),
            "n_test": len(X_test),
            "feature_names": feature_names,
            "importances": importances,
            "top_customers": top_customers,
            "score_distribution": buckets,
            "error": None
        }
    except Exception as e:
        return {"error": str(e), "model": "Gradient Boosting"}
