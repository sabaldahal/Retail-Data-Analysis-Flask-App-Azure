import datetime
import os
import random
import re

from flask import g
from werkzeug.security import generate_password_hash

try:
    import pyodbc
except ImportError as exc:  # pragma: no cover - dependency error is surfaced at runtime
    pyodbc = None
    _PYODBC_IMPORT_ERROR = exc
else:
    _PYODBC_IMPORT_ERROR = None

AZURE_DB_G_KEY = "azure_db"


def _require_pyodbc():
    if pyodbc is None:
        raise RuntimeError(
            "pyodbc is required for db2.py. Install it with `pip install pyodbc` and make sure "
            "the Microsoft ODBC Driver for SQL Server is available on the host."
        ) from _PYODBC_IMPORT_ERROR


def _get_connection_string():
    direct_connection_string = os.getenv("AZURE_SQL_CONNECTION_STRING")
    if direct_connection_string:
        return direct_connection_string

    server = os.getenv("AZURE_SQL_SERVER")
    database = os.getenv("AZURE_SQL_DATABASE") or os.getenv("SQL_DATABASE")
    username = os.getenv("AZURE_SQL_USERNAME") or os.getenv("SQL_USER")
    password = os.getenv("AZURE_SQL_PASSWORD") or os.getenv("SQL_PASSWORD")
    driver = os.getenv("AZURE_SQL_DRIVER", "ODBC Driver 18 for SQL Server")

    missing = [
        name
        for name, value in (
            ("AZURE_SQL_SERVER", server),
            ("AZURE_SQL_DATABASE", database),
            ("AZURE_SQL_USERNAME", username),
            ("AZURE_SQL_PASSWORD", password),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Azure SQL is not configured. Set AZURE_SQL_CONNECTION_STRING or provide: "
            + ", ".join(missing)
        )

    return (
        f"DRIVER={{{driver}}};"
        f"SERVER={server},1433;"
        f"DATABASE={database};"
        f"UID={username};"
        f"PWD={password};"
        "Encrypt=yes;"
        "TrustServerCertificate=no;"
        "Connection Timeout=30;"
    )


def _translate_sql(sql):
    if re.search(r"(?i)INSERT\s+OR\s+REPLACE\s+INTO", sql):
        return re.sub(r"(?i)INSERT\s+OR\s+REPLACE\s+INTO", "INSERT INTO", sql, count=1)
    return sql


class AzureRow:
    def __init__(self, columns, values):
        self._columns = list(columns)
        self._data = {column: value for column, value in zip(self._columns, values)}
        self._lookup = {}
        for column, value in self._data.items():
            self._lookup[column] = value
            self._lookup[column.lower()] = value
            self._lookup[column.upper()] = value

    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self._data.values())[key]
        key = str(key)
        if key in self._lookup:
            return self._lookup[key]
        raise KeyError(key)

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def keys(self):
        return list(self._data.keys())

    def as_dict(self):
        return dict(self._data)


class AzureResult:
    def __init__(self, cursor):
        self._cursor = cursor
        self._columns = [column[0] for column in cursor.description] if cursor.description else []

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None:
            return None
        return AzureRow(self._columns, row)

    def fetchall(self):
        return [AzureRow(self._columns, row) for row in self._cursor.fetchall()]

    def __iter__(self):
        return iter(self.fetchall())


class AzureConnection:
    def __init__(self, connection):
        self._connection = connection

    def execute(self, sql, params=()):
        cursor = self._connection.cursor()
        cursor.execute(_translate_sql(sql), params)
        return AzureResult(cursor)

    def executemany(self, sql, seq_of_params):
        cursor = self._connection.cursor()
        if hasattr(cursor, "fast_executemany"):
            cursor.fast_executemany = True
        cursor.executemany(_translate_sql(sql), seq_of_params)
        return cursor

    def commit(self):
        self._connection.commit()

    def close(self):
        self._connection.close()


# def get_db():
#     _require_pyodbc()
#     if AZURE_DB_G_KEY not in g:
#         g[AZURE_DB_G_KEY] = AzureConnection(pyodbc.connect(_get_connection_string(), autocommit=False))
#     return g[AZURE_DB_G_KEY]

def get_db():
    _require_pyodbc()

    if not hasattr(g, AZURE_DB_G_KEY):
        conn = pyodbc.connect(_get_connection_string(), autocommit=False)
        setattr(g, AZURE_DB_G_KEY, AzureConnection(conn))

    return getattr(g, AZURE_DB_G_KEY)

def close_db(_exc=None):
    db = g.pop(AZURE_DB_G_KEY, None)
    if db is not None:
        db.close()


def init_app(app):
    app.teardown_appcontext(close_db)

def init_db():
    return

def load_csv_to_table(db, path, table, mode="upsert", progress_hook=None):
    import csv
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)

    if not rows:
        return {"processed": 0, "applied": 0, "info": "No rows found in CSV."}
    
    mode = mode.strip().lower()
    if mode not in {"upsert"}:
        mode = "upsert"

    null_like = {"", "null", "none", "n/a", "na"}

    def normalize(value):
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip()
            return None if value.lower() in null_like else value
        return value

    def to_int(value):
        value = normalize(value)
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            try:
                return int(float(value))
            except (TypeError, ValueError):
                return None

    def to_float(value):
        value = normalize(value)
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def to_date(value):
        value = normalize(value)
        if value is None:
            return None
        if isinstance(value, datetime.date):
            return value
        for fmt in ("%d-%b-%y", "%d-%b-%Y", "%Y-%m-%d"):
            try:
                return datetime.datetime.strptime(value, fmt).date()
            except (TypeError, ValueError):
                continue
        return value

    def normalized_row(row):
        return {str(key).strip().upper().replace(" ", "_"): normalize(value) for key, value in row.items()}

    def batched(sequence, batch_size):
        for index in range(0, len(sequence), batch_size):
            yield sequence[index:index + batch_size]

    if table == "transactions":
        rows_to_insert = []
        for row in rows:
            normalized = normalized_row(row)
            rows_to_insert.append(
                (
                    to_int(normalized.get("HSHD_NUM")),
                    normalized.get("BASKET_NUM"),
                    to_date(normalized.get("PURCHASE_") or normalized.get("PURCHASE_DATE")),
                    to_int(normalized.get("PRODUCT_NUM")),
                    to_float(normalized.get("SPEND")),
                    to_int(normalized.get("UNITS")),
                    normalized.get("STORE_R") or normalized.get("STORE_REGION"),
                    to_int(normalized.get("WEEK_NUM")),
                    to_int(normalized.get("YEAR")),
                )
            )
        statement = "INSERT INTO transactions (HSHD_NUM, BASKET_NUM, PURCHASE_DATE, PRODUCT_NUM, SPEND, UNITS, STORE_REGION, WEEK_NUM, YEAR) VALUES (?,?,?,?,?,?,?,?,?)"
        applied = 0
        total_rows = len(rows_to_insert)
        if progress_hook:
            progress_hook(0, total_rows, "Starting transactions insert")
        for chunk in batched(rows_to_insert, 5000):
            db.executemany(statement, chunk)
            db.commit()
            applied += len(chunk)
            print(f"Inserted {applied}/{len(rows_to_insert)} transaction rows")
            if progress_hook:
                progress_hook(applied, total_rows, "Inserting transactions")
        print(f"processed {len(rows_to_insert)}")
        return {"processed": len(rows_to_insert), "applied": applied, "info": ""}

    if table == "households":
        rows_to_insert = []
        seen_keys = set()
        for row in rows:
            normalized = normalized_row(row)
            hshd_num = to_int(normalized.get("HSHD_NUM"))
            # if hshd_num is None:
            #     continue
            # if hshd_num not in seen_keys:
            #     db.execute("DELETE FROM households WHERE HSHD_NUM = ?", (hshd_num,))
            #     seen_keys.add(hshd_num)
            rows_to_insert.append(
                (
                    hshd_num,
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
        statement = "INSERT INTO households (HSHD_NUM, L, AGE_RANGE, MARITAL, INCOME_RANGE, HOMEOWNER, HSHD_COMPOSITION, HH_SIZE, CHILDREN) VALUES (?,?,?,?,?,?,?,?,?)"
        applied = 0
        total_rows = len(rows_to_insert)
        if progress_hook:
            progress_hook(0, total_rows, "Starting households insert")
        for chunk in batched(rows_to_insert, 1000):
            db.executemany(statement, chunk)
            db.commit()
            applied += len(chunk)
            print(f"Inserted {applied}/{len(rows_to_insert)} household rows")
            if progress_hook:
                progress_hook(applied, total_rows, "Inserting households")
        print(f"processed {len(rows_to_insert)}")
        return {"processed": len(rows_to_insert), "applied": applied, "info": ""}

    if table == "products":
        rows_to_insert = []
        seen_keys = set()
        for row in rows:
            normalized = normalized_row(row)
            product_num = to_int(normalized.get("PRODUCT_NUM"))
            # if product_num is None:
            #     continue
            # if product_num not in seen_keys:
            #     db.execute("DELETE FROM products WHERE PRODUCT_NUM = ?", (product_num,))
            #     seen_keys.add(product_num)
            rows_to_insert.append(
                (
                    product_num,
                    normalized.get("DEPARTMENT"),
                    normalized.get("COMMODITY"),
                    normalized.get("BRAND_TY"),
                    normalized.get("NATURAL_ORGANIC_FLAG"),
                )
            )
        statement = "INSERT INTO products (PRODUCT_NUM, DEPARTMENT, COMMODITY, BRAND_TY, NATURAL_ORGANIC_FLAG) VALUES (?,?,?,?,?)"
        applied = 0
        total_rows = len(rows_to_insert)
        if progress_hook:
            progress_hook(0, total_rows, "Starting products insert")
        for chunk in batched(rows_to_insert, 1000):
            db.executemany(statement, chunk)
            db.commit()
            applied += len(chunk)
            print(f"Inserted {applied}/{len(rows_to_insert)} product rows")
            if progress_hook:
                progress_hook(applied, total_rows, "Inserting products")
        print(f"processed {len(rows_to_insert)}")
        return {"processed": len(rows_to_insert), "applied": applied, "info": ""}

    raise ValueError(f"Unsupported table: {table}")