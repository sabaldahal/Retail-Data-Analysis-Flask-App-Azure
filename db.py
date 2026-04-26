import csv
import os
import sqlite3

from flask import g

DATABASE = os.path.join(os.path.dirname(__file__), "retail.db")


def _data_path(filename):
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "8451", filename))


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT    UNIQUE NOT NULL,
            password_hash TEXT    NOT NULL,
            email         TEXT    NOT NULL
        );
    """)
        # DROP TABLE IF EXISTS transactions;
        # DROP TABLE IF EXISTS households;
        # DROP TABLE IF EXISTS products;
    db.executescript("""


        CREATE TABLE IF NOT EXISTS households (
            HSHD_NUM         INTEGER PRIMARY KEY,
            L                TEXT,
            AGE_RANGE        TEXT,
            MARITAL          TEXT,
            INCOME_RANGE     TEXT,
            HOMEOWNER        TEXT,
            HSHD_COMPOSITION TEXT,
            HH_SIZE          TEXT,
            CHILDREN         TEXT
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            HSHD_NUM      INTEGER,
            BASKET_NUM    TEXT,
            PURCHASE_DATE TEXT,
            PRODUCT_NUM   INTEGER,
            SPEND         REAL,
            UNITS         INTEGER,
            STORE_REGION  TEXT,
            WEEK_NUM      INTEGER,
            YEAR          INTEGER
        );

        CREATE TABLE IF NOT EXISTS products (
            PRODUCT_NUM          INTEGER PRIMARY KEY,
            DEPARTMENT           TEXT,
            COMMODITY            TEXT,
            BRAND_TY             TEXT,
            NATURAL_ORGANIC_FLAG TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_tx_hshd ON transactions(HSHD_NUM);
        CREATE INDEX IF NOT EXISTS idx_tx_product ON transactions(PRODUCT_NUM);
        CREATE INDEX IF NOT EXISTS idx_tx_date ON transactions(PURCHASE_DATE);
    """)
    #check if the dataset is already loaded
    existing = db.execute("SELECT COUNT(*) AS c FROM transactions").fetchone()["c"]
    if existing == 0:
        add_actual_data(db)
    db.commit()
    db.close()


def add_actual_data(db):
    households_path = _data_path("400_households.csv")
    transactions_path = _data_path("400_transactions.csv")
    products_path = _data_path("400_products.csv")

    load_csv_to_table(db, households_path, "households")
    load_csv_to_table(db, transactions_path, "transactions")
    load_csv_to_table(db, products_path, "products")


def load_csv_to_table(db, path, table, mode="upsert", progress_hook=None):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)

    if not rows:
        return {"processed": 0, "applied": 0, "info": "No rows found in CSV."}
    
    mode = mode.strip().lower()
    if mode not in {"upsert"}:
        mode = "upsert"

    def normalize(value):
        if isinstance(value, str):
            value = value.strip()
            return value if value else None
        return value

    def normalized_row(row):
        return {str(key).strip().upper().replace(" ", "_"): normalize(value) for key, value in row.items()}

    if table == "transactions":
        rows_to_insert = []
        for row in rows:
            normalized = normalized_row(row)
            rows_to_insert.append(
                (
                    normalized.get("HSHD_NUM"),
                    normalized.get("BASKET_NUM"),
                    normalized.get("PURCHASE_") or normalized.get("PURCHASE_DATE"),
                    normalized.get("PRODUCT_NUM"),
                    normalized.get("SPEND"),
                    normalized.get("UNITS"),
                    normalized.get("STORE_R") or normalized.get("STORE_REGION"),
                    normalized.get("WEEK_NUM"),
                    normalized.get("YEAR"),
                )
            )
        db.executemany(
            "INSERT OR REPLACE INTO transactions (HSHD_NUM, BASKET_NUM, PURCHASE_DATE, PRODUCT_NUM, SPEND, UNITS, STORE_REGION, WEEK_NUM, YEAR) VALUES (?,?,?,?,?,?,?,?,?)",
            rows_to_insert,
        )
        return {"processed": len(rows_to_insert), "applied": len(rows_to_insert), "info": ""}

    if table == "households":
        rows_to_insert = []
        for row in rows:
            normalized = normalized_row(row)
            rows_to_insert.append(
                (
                    normalized.get("HSHD_NUM"),
                    normalized.get("L"),
                    normalized.get("AGE_RANGE"),
                    normalized.get("MARITAL"),
                    normalized.get("INCOME_RANGE"),
                    normalized.get("HOMEOWNER"),
                    normalized.get("HSHD_COMPOSITION"),
                    normalized.get("HH_SIZE"),
                    normalized.get("CHILDREN"),
                )
            )
        db.executemany(
            "INSERT OR REPLACE INTO households (HSHD_NUM, L, AGE_RANGE, MARITAL, INCOME_RANGE, HOMEOWNER, HSHD_COMPOSITION, HH_SIZE, CHILDREN) VALUES (?,?,?,?,?,?,?,?,?)",
            rows_to_insert,
        )
        return {"processed": len(rows_to_insert), "applied": len(rows_to_insert), "info": ""}

    if table == "products":
        rows_to_insert = []
        for row in rows:
            normalized = normalized_row(row)
            rows_to_insert.append(
                (
                    normalized.get("PRODUCT_NUM"),
                    normalized.get("DEPARTMENT"),
                    normalized.get("COMMODITY"),
                    normalized.get("BRAND_TY"),
                    normalized.get("NATURAL_ORGANIC_FLAG"),
                )
            )
        db.executemany(
            "INSERT OR REPLACE INTO products (PRODUCT_NUM, DEPARTMENT, COMMODITY, BRAND_TY, NATURAL_ORGANIC_FLAG) VALUES (?,?,?,?,?)",
            rows_to_insert,
        )
        return {"processed": len(rows_to_insert), "applied": len(rows_to_insert), "info": ""}

    raise ValueError(f"Unsupported table: {table}")