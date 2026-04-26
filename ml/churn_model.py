"""
Churn prediction: classify households as churned (no purchase in last 12 weeks).
Uses logistic regression with RFM features + demographics.
"""
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

def run_churn():
    try:
        import numpy as np
        from sklearn.linear_model import LogisticRegression
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.metrics import accuracy_score, roc_auc_score, classification_report
        from sklearn.preprocessing import StandardScaler

        db = get_db()

        rows = db.execute("""
            SELECT
                s.HSHD_NUM,
                s.last_week,
                s.first_week,
                s.frequency,
                s.monetary,
                s.active_weeks,
                h.INCOME_RANGE,
                h.HH_SIZE,
                h.CHILDREN,
                h.AGE_RANGE,
                h.L
            FROM (
                SELECT
                    HSHD_NUM,
                    MAX(WEEK_NUM + (YEAR-2018)*52) AS last_week,
                    MIN(WEEK_NUM + (YEAR-2018)*52) AS first_week,
                    COUNT(DISTINCT BASKET_NUM) AS frequency,
                    SUM(SPEND) AS monetary,
                    COUNT(DISTINCT WEEK_NUM) AS active_weeks
                FROM transactions
                GROUP BY HSHD_NUM
            ) s
            LEFT JOIN households h ON s.HSHD_NUM = h.HSHD_NUM
        """).fetchall()

        if len(rows) < 20:
            return {
                "warning": "Not enough household data to train churn models yet.",
                "available_households": len(rows),
                "required_households": 20,
                "error": None,
            }

        data = [dict(r) for r in rows]
        max_week = max(d["last_week"] or 0 for d in data)
        CHURN_THRESHOLD = 12

        income_map = {"UNDER 35K":1,"35-49K":2,"50-74K":3,"75-99K":4,"100-150K":5,"150K+":6}
        age_map = {"19-24":1,"25-34":2,"35-44":3,"45-54":4,"55-64":5,"65+":6}

        X, y, hshd_nums = [], [], []
        for d in data:
            recency = max_week - (d["last_week"] or 0)
            churn = 1 if recency >= CHURN_THRESHOLD else 0
            freq = d["frequency"] or 1
            monetary = d["monetary"] or 0
            active_weeks = d["active_weeks"] or 1
            tenure = (d["last_week"] or 0) - (d["first_week"] or 0) + 1
            avg_spend = monetary / freq
            income_key = _norm_category(d["INCOME_RANGE"])
            income = income_map.get(income_key, 3)
            hh_size = _safe_int(d["HH_SIZE"], default=2)
            children = 1 if d["CHILDREN"] == "Y" else 0
            age = age_map.get(_norm_category(d["AGE_RANGE"]), 3)
            loyal = 1 if d["L"] == "Y" else 0
            X.append([recency, freq, monetary, avg_spend, active_weeks, tenure, income, hh_size, children, age, loyal])
            y.append(churn)
            hshd_nums.append(d["HSHD_NUM"])

        X = np.array(X, dtype=float)
        y = np.array(y)

        split = int(len(X) * 0.8)
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        # Logistic Regression
        lr = LogisticRegression(random_state=42, max_iter=500)
        lr.fit(X_scaled[:split], y[:split])
        lr_pred = lr.predict(X_scaled[split:])
        lr_proba = lr.predict_proba(X_scaled[split:])[:,1]
        lr_acc = round(accuracy_score(y[split:], lr_pred), 3)
        lr_auc = round(roc_auc_score(y[split:], lr_proba), 3) if len(set(y[split:])) > 1 else 0

        # Random Forest
        rf = RandomForestClassifier(n_estimators=100, random_state=42)
        rf.fit(X[:split], y[:split])
        rf_pred = rf.predict(X[split:])
        rf_proba = rf.predict_proba(X[split:])[:,1]
        rf_acc = round(accuracy_score(y[split:], rf_pred), 3)
        rf_auc = round(roc_auc_score(y[split:], rf_proba), 3) if len(set(y[split:])) > 1 else 0

        feature_names = ["Recency","Frequency","Monetary","Avg Spend","Active Weeks","Tenure","Income","HH Size","Children","Age","Loyalty"]
        importances = [{"feature": f, "importance": round(float(v), 4)}
                       for f, v in sorted(zip(feature_names, rf.feature_importances_), key=lambda x: -x[1])]

        # At-risk customers (predicted churn with high probability)
        all_proba = rf.predict_proba(X)[:,1]
        at_risk_idx = np.argsort(all_proba)[::-1][:10]
        at_risk = [
            {"hshd_num": int(hshd_nums[i]), "churn_probability": round(float(all_proba[i]), 3),
             "last_purchase_weeks_ago": int(X[i][0])}
            for i in at_risk_idx
        ]

        churn_by_income = {}
        for d, churn_label in zip(data, y):
            key = _norm_category(d["INCOME_RANGE"])
            if key not in churn_by_income:
                churn_by_income[key] = {"churned": 0, "total": 0}
            churn_by_income[key]["total"] += 1
            if churn_label:
                churn_by_income[key]["churned"] += 1
        income_order = {
            "UNDER 35K": 1,
            "35-49K": 2,
            "50-74K": 3,
            "75-99K": 4,
            "100-150K": 5,
            "150K+": 6,
            "UNKNOWN": 99,
        }
        churn_rate_income = [
            {"income": k, "churn_rate": round(v["churned"]/v["total"], 3)}
            for k, v in sorted(churn_by_income.items(), key=lambda kv: income_order.get(kv[0], 98))
        ]

        total = len(y)
        churned = int(y.sum())
        return {
            "model": "Logistic Regression + Random Forest",
            "total_households": total,
            "churned": churned,
            "churn_rate": round(churned / total, 3),
            "lr": {"accuracy": lr_acc, "auc": lr_auc},
            "rf": {"accuracy": rf_acc, "auc": rf_auc},
            "feature_importances": importances,
            "at_risk": at_risk,
            "churn_by_income": churn_rate_income,
            "error": None
        }
    except Exception as e:
        return {"error": str(e), "model": "Churn Prediction"}
