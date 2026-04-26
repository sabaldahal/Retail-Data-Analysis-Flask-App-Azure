"""
Basket analysis using association rules + Random Forest for cross-sell prediction.
"""
import os

USE_AZURE_SQL = bool(os.getenv("AZURE_SQL_CONNECTION_STRING") or os.getenv("AZURE_SQL_SERVER"))

if USE_AZURE_SQL:
    from db2 import get_db
else:
    from db import get_db

def run_basket():
    try:
        import numpy as np
        from collections import defaultdict, Counter

        db = get_db()
        rows = db.execute("""
            SELECT t.HSHD_NUM, t.BASKET_NUM, t.PURCHASE_DATE, TRIM(p.COMMODITY) AS COMMODITY
            FROM transactions t
            JOIN products p ON t.PRODUCT_NUM=p.PRODUCT_NUM
            WHERE p.COMMODITY IS NOT NULL AND UPPER(TRIM(p.COMMODITY)) NOT IN ('', 'NULL', 'NONE', 'N/A', 'NA')
        """).fetchall()

        if len(rows) < 50:
            return {
                "warning": "Not enough transaction detail to run basket analysis yet.",
                "available_rows": len(rows),
                "required_rows": 50,
                "error": None,
            }

        # Build basket sets
        baskets = defaultdict(set)
        for r in rows:
            basket_key = (r["HSHD_NUM"], r["BASKET_NUM"], r["PURCHASE_DATE"])
            baskets[basket_key].add(r["COMMODITY"])

        basket_list = [list(v) for v in baskets.values() if len(v) >= 2]
        total = len(basket_list)

        # Item support
        item_count = Counter()
        for b in basket_list:
            for item in b:
                item_count[item] += 1

        # Pair support (simple Apriori-style)
        pair_count = Counter()
        for b in basket_list:
            items = sorted(set(b))
            for i in range(len(items)):
                for j in range(i+1, len(items)):
                    pair_count[(items[i], items[j])] += 1

        min_support = max(2, int(total * 0.05))
        frequent_pairs = [(pair, cnt) for pair, cnt in pair_count.items() if cnt >= min_support]
        frequent_pairs.sort(key=lambda x: -x[1])

        # Association rules
        rules = []
        for (a, b), cnt in frequent_pairs[:30]:
            support    = round(cnt / total, 3)
            confidence_ab = round(cnt / item_count[a], 3) if item_count[a] else 0
            confidence_ba = round(cnt / item_count[b], 3) if item_count[b] else 0
            lift = round(support / ((item_count[a]/total) * (item_count[b]/total)), 2)
            if confidence_ab >= 0.1:
                rules.append({
                    "antecedent": a, "consequent": b,
                    "support": support, "confidence": confidence_ab, "lift": lift
                })
            if confidence_ba >= 0.1:
                rules.append({
                    "antecedent": b, "consequent": a,
                    "support": support, "confidence": confidence_ba, "lift": lift
                })

        rules.sort(key=lambda x: -x["lift"])
        top_rules = rules[:15]

        # Random Forest: predict if a basket will contain MILK given other items
        try:
            from sklearn.ensemble import RandomForestClassifier
            from sklearn.metrics import accuracy_score, classification_report

            all_items = sorted(item_count.keys())
            item_idx = {item: i for i, item in enumerate(all_items)}
            target_item = max(item_count, key=item_count.get)  # most frequent item

            X, y = [], []
            for b in basket_list:
                vec = [0] * len(all_items)
                for item in b:
                    if item in item_idx:
                        vec[item_idx[item]] = 1
                has_target = 1 if target_item in b else 0
                vec[item_idx[target_item]] = 0  # remove target from features
                X.append(vec)
                y.append(has_target)

            X = np.array(X)
            y = np.array(y)
            split = int(len(X) * 0.8)
            clf = RandomForestClassifier(n_estimators=50, random_state=42)
            clf.fit(X[:split], y[:split])
            y_pred = clf.predict(X[split:])
            acc = round(accuracy_score(y[split:], y_pred), 3)

            importances = sorted(
                zip(all_items, clf.feature_importances_),
                key=lambda x: -x[1]
            )[:8]
            rf_result = {
                "target": target_item,
                "accuracy": acc,
                "top_features": [{"item": a, "importance": round(float(b), 4)} for a, b in importances]
            }
        except Exception as e:
            rf_result = {"error": str(e)}

        top_items = [{"item": k, "count": v} for k, v in item_count.most_common(10)]

        return {
            "model": "Association Rules + Random Forest",
            "total_baskets": total,
            "frequent_pairs": [
                {"items": f"{p[0]} & {p[1]}", "count": c}
                for p, c in frequent_pairs[:10]
            ],
            "rules": top_rules,
            "top_items": top_items,
            "rf": rf_result,
            "error": None
        }
    except Exception as e:
        return {"error": str(e), "model": "Basket Analysis"}
