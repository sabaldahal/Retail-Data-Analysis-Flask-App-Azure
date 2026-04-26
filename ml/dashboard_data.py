import os

USE_AZURE_SQL = bool(os.getenv("AZURE_SQL_CONNECTION_STRING") or os.getenv("AZURE_SQL_SERVER"))

if USE_AZURE_SQL:
    from db2 import get_db
else:
    from db import get_db


def _limit_clause(limit, offset=0):
    if USE_AZURE_SQL:
        return f"OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY"
    return f"LIMIT {limit}"


def _year_week_expr():
    if USE_AZURE_SQL:
        return "CAST(YEAR AS VARCHAR(10)) + '-W' + RIGHT('0' + CAST(WEEK_NUM AS VARCHAR(2)), 2)"
    return "printf('%d-W%02d', YEAR, WEEK_NUM)"

def get_dashboard_data():
    db = get_db()
    spend_limit = _limit_clause(200)
    dept_limit = _limit_clause(10)
    year_week_expr = _year_week_expr()

    # Spend over time by year/week
    spend_time = db.execute("""
        SELECT YEAR, WEEK_NUM,
               %s AS year_week,
               ROUND(SUM(SPEND),2) as total_spend
        FROM transactions
        GROUP BY YEAR, WEEK_NUM
        ORDER BY YEAR, WEEK_NUM
         %s
    """ % (year_week_expr, spend_limit)).fetchall()

    # Spend by department
    dept_spend = db.execute("""
        SELECT p.DEPARTMENT, ROUND(SUM(t.SPEND),2) as total
        FROM transactions t JOIN products p ON t.PRODUCT_NUM = p.PRODUCT_NUM
        GROUP BY p.DEPARTMENT ORDER BY total DESC %s
    """ % dept_limit).fetchall()

    # Income vs avg basket size
    income_basket = db.execute("""
        SELECT
               CASE
                   WHEN h.INCOME_RANGE IS NULL OR UPPER(TRIM(h.INCOME_RANGE)) IN ('', 'NULL', 'NONE', 'N/A', 'NA')
                   THEN 'UNKNOWN'
                   ELSE TRIM(h.INCOME_RANGE)
               END AS INCOME_RANGE,
               ROUND(AVG(basket_totals.basket_spend),2) as avg_basket
        FROM households h
        JOIN (
            SELECT HSHD_NUM, BASKET_NUM, SUM(SPEND) as basket_spend
            FROM transactions GROUP BY HSHD_NUM, BASKET_NUM
        ) basket_totals ON h.HSHD_NUM = basket_totals.HSHD_NUM
        GROUP BY CASE
                   WHEN h.INCOME_RANGE IS NULL OR UPPER(TRIM(h.INCOME_RANGE)) IN ('', 'NULL', 'NONE', 'N/A', 'NA')
                   THEN 'UNKNOWN'
                   ELSE TRIM(h.INCOME_RANGE)
                 END
        ORDER BY avg_basket DESC
    """).fetchall()

    # Brand preference
    brand_pref = db.execute("""
        SELECT
            CASE
                WHEN p.BRAND_TY IS NULL OR UPPER(TRIM(p.BRAND_TY)) IN ('', 'NULL', 'NONE', 'N/A', 'NA')
                THEN 'UNKNOWN'
                ELSE TRIM(p.BRAND_TY)
            END AS BRAND_TY,
            COUNT(*) as cnt,
            ROUND(SUM(t.SPEND),2) as total
        FROM transactions t JOIN products p ON t.PRODUCT_NUM=p.PRODUCT_NUM
        GROUP BY CASE
                   WHEN p.BRAND_TY IS NULL OR UPPER(TRIM(p.BRAND_TY)) IN ('', 'NULL', 'NONE', 'N/A', 'NA')
                   THEN 'UNKNOWN'
                   ELSE TRIM(p.BRAND_TY)
                 END
        ORDER BY total DESC
    """).fetchall()

    # Organic vs non-organic
    organic = db.execute("""
        SELECT
            CASE
                WHEN p.NATURAL_ORGANIC_FLAG IS NULL OR UPPER(TRIM(p.NATURAL_ORGANIC_FLAG)) IN ('', 'NULL', 'NONE', 'N/A', 'NA')
                THEN 'UNKNOWN'
                ELSE UPPER(TRIM(p.NATURAL_ORGANIC_FLAG))
            END AS NATURAL_ORGANIC_FLAG,
            ROUND(SUM(t.SPEND),2) as total
        FROM transactions t JOIN products p ON t.PRODUCT_NUM=p.PRODUCT_NUM
        GROUP BY CASE
                   WHEN p.NATURAL_ORGANIC_FLAG IS NULL OR UPPER(TRIM(p.NATURAL_ORGANIC_FLAG)) IN ('', 'NULL', 'NONE', 'N/A', 'NA')
                   THEN 'UNKNOWN'
                   ELSE UPPER(TRIM(p.NATURAL_ORGANIC_FLAG))
                 END
        ORDER BY total DESC
    """).fetchall()

    # Regional spend
    regional = db.execute("""
        SELECT
            CASE
                WHEN STORE_REGION IS NULL OR UPPER(TRIM(STORE_REGION)) IN ('', 'NULL', 'NONE', 'N/A', 'NA')
                THEN 'UNKNOWN'
                ELSE TRIM(STORE_REGION)
            END AS STORE_REGION,
            ROUND(SUM(SPEND),2) as total
        FROM transactions
        GROUP BY CASE
                   WHEN STORE_REGION IS NULL OR UPPER(TRIM(STORE_REGION)) IN ('', 'NULL', 'NONE', 'N/A', 'NA')
                   THEN 'UNKNOWN'
                   ELSE TRIM(STORE_REGION)
                 END
        ORDER BY total DESC
    """).fetchall()

    # Household size vs spend
    hh_spend = db.execute("""
                SELECT
                        CASE
                                WHEN h.HH_SIZE IS NULL OR UPPER(TRIM(h.HH_SIZE)) IN ('', 'NULL', 'NONE', 'N/A', 'NA')
                                THEN 'UNKNOWN'
                                ELSE TRIM(h.HH_SIZE)
                        END AS HH_SIZE,
                        ROUND(AVG(s.total),2) as avg_spend
        FROM households h
        JOIN (SELECT HSHD_NUM, SUM(SPEND) as total FROM transactions GROUP BY HSHD_NUM) s
          ON h.HSHD_NUM = s.HSHD_NUM
                GROUP BY CASE
                                     WHEN h.HH_SIZE IS NULL OR UPPER(TRIM(h.HH_SIZE)) IN ('', 'NULL', 'NONE', 'N/A', 'NA')
                                     THEN 'UNKNOWN'
                                     ELSE TRIM(h.HH_SIZE)
                                 END
                ORDER BY CASE
                                     WHEN CASE WHEN h.HH_SIZE IS NULL OR UPPER(TRIM(h.HH_SIZE)) IN ('', 'NULL', 'NONE', 'N/A', 'NA') THEN 'UNKNOWN' ELSE TRIM(h.HH_SIZE) END = '1' THEN 1
                                     WHEN CASE WHEN h.HH_SIZE IS NULL OR UPPER(TRIM(h.HH_SIZE)) IN ('', 'NULL', 'NONE', 'N/A', 'NA') THEN 'UNKNOWN' ELSE TRIM(h.HH_SIZE) END = '2' THEN 2
                                     WHEN CASE WHEN h.HH_SIZE IS NULL OR UPPER(TRIM(h.HH_SIZE)) IN ('', 'NULL', 'NONE', 'N/A', 'NA') THEN 'UNKNOWN' ELSE TRIM(h.HH_SIZE) END = '3' THEN 3
                                     WHEN CASE WHEN h.HH_SIZE IS NULL OR UPPER(TRIM(h.HH_SIZE)) IN ('', 'NULL', 'NONE', 'N/A', 'NA') THEN 'UNKNOWN' ELSE TRIM(h.HH_SIZE) END = '4' THEN 4
                                     WHEN CASE WHEN h.HH_SIZE IS NULL OR UPPER(TRIM(h.HH_SIZE)) IN ('', 'NULL', 'NONE', 'N/A', 'NA') THEN 'UNKNOWN' ELSE TRIM(h.HH_SIZE) END = '5+' THEN 5
                                     ELSE 99
                                 END
    """).fetchall()

    # KPIs
    kpis = db.execute("""
        SELECT
            (SELECT COUNT(*) FROM households) AS households,
            COUNT(*) AS transactions,
            ROUND(SUM(SPEND), 2) AS total_spend,
            ROUND(AVG(SPEND), 2) AS avg_spend
        FROM transactions
    """).fetchone()

    def rows_to_list(rows):
        return [dict(r) for r in rows]

    return {
        "spend_time": rows_to_list(spend_time),
        "dept_spend": rows_to_list(dept_spend),
        "income_basket": rows_to_list(income_basket),
        "brand_pref": rows_to_list(brand_pref),
        "organic": rows_to_list(organic),
        "regional": rows_to_list(regional),
        "hh_spend": rows_to_list(hh_spend),
        "kpis": dict(kpis) if kpis else {}
    }
