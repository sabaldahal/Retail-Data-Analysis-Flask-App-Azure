from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import threading
import uuid
import time
from dotenv import load_dotenv
load_dotenv()

USE_AZURE_SQL = bool(os.getenv("AZURE_SQL_CONNECTION_STRING") or os.getenv("AZURE_SQL_SERVER"))
# if USE_AZURE_SQL:
from db2 import load_csv_to_table, get_db, init_db, init_app as init_db_app
close_db = None
# else:
#     from db import load_csv_to_table, get_db, init_db, close_db
#     init_db_app = None

from ml.clv_model import run_clv
from ml.basket_model import run_basket
from ml.churn_model import run_churn
from ml.dashboard_data import get_dashboard_data

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-prod")
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
ALLOWED_EXTENSIONS = {"csv"}

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
UPLOAD_PROGRESS = {}
UPLOAD_PROGRESS_LOCK = threading.Lock()
if init_db_app is not None:
    init_db_app(app)
elif close_db is not None:
    app.teardown_appcontext(close_db)


def _set_upload_progress(upload_id, **fields):
    with UPLOAD_PROGRESS_LOCK:
        entry = UPLOAD_PROGRESS.get(upload_id, {})
        entry.update(fields)
        UPLOAD_PROGRESS[upload_id] = entry

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# ---------- Auth ----------
@app.route("/", methods=["GET", "POST"])
def login():
    if "user" in session:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session["user"] = username
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.")
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        email    = request.form.get("email", "").strip()
        if not username or not password or not email:
            flash("All fields are required.")
            return render_template("register.html")
        db = get_db()
        existing = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
        if existing:
            flash("Username already taken.")
            return render_template("register.html")
        db.execute(
            "INSERT INTO users (username, password_hash, email) VALUES (?,?,?)",
            (username, generate_password_hash(password), email)
        )
        db.commit()
        flash("Account created — please log in.")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect(url_for("login"))

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

# ---------- Dashboard ----------
@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")

# ---------- Data Pull (Req 3 & 4) ----------
@app.route("/data-pull", methods=["GET"])
@login_required
def data_pull():
    hshd_num = request.args.get("hshd_num", "10")
    page = request.args.get("page", "1")
    try:
        hshd_num = int(hshd_num)
    except ValueError:
        hshd_num = 10
    try:
        page = int(page)
    except ValueError:
        page = 1
    return render_template("data_pull.html", hshd_num=hshd_num, page=page)


def _get_data_pull_rows(hshd_num, page=1, per_page=50):
    db = get_db()
    total = db.execute(
        "SELECT COUNT(*) AS c FROM transactions WHERE HSHD_NUM = ?",
        (hshd_num,),
    ).fetchone()["c"]

    offset = max(page - 1, 0) * per_page
    if USE_AZURE_SQL:
        query = """
            SELECT
                t.id, t.HSHD_NUM, t.BASKET_NUM, t.PURCHASE_DATE,
                t.PRODUCT_NUM, p.DEPARTMENT, p.COMMODITY,
                t.SPEND, t.UNITS, t.STORE_REGION,
                h.L, h.AGE_RANGE, h.MARITAL, h.INCOME_RANGE,
                h.HOMEOWNER, h.HSHD_COMPOSITION, h.HH_SIZE, h.CHILDREN,
                p.BRAND_TY, p.NATURAL_ORGANIC_FLAG
            FROM transactions t
            LEFT JOIN households h ON t.HSHD_NUM = h.HSHD_NUM
            LEFT JOIN products   p ON t.PRODUCT_NUM = p.PRODUCT_NUM
            WHERE t.HSHD_NUM = ?
            ORDER BY t.HSHD_NUM, t.BASKET_NUM, t.PURCHASE_DATE, t.PRODUCT_NUM, p.DEPARTMENT, p.COMMODITY
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
        """
        params = (hshd_num, offset, per_page)
    else:
        query = """
            SELECT
                t.id, t.HSHD_NUM, t.BASKET_NUM, t.PURCHASE_DATE,
                t.PRODUCT_NUM, p.DEPARTMENT, p.COMMODITY,
                t.SPEND, t.UNITS, t.STORE_REGION,
                h.L, h.AGE_RANGE, h.MARITAL, h.INCOME_RANGE,
                h.HOMEOWNER, h.HSHD_COMPOSITION, h.HH_SIZE, h.CHILDREN,
                p.BRAND_TY, p.NATURAL_ORGANIC_FLAG
            FROM transactions t
            LEFT JOIN households h ON t.HSHD_NUM = h.HSHD_NUM
            LEFT JOIN products   p ON t.PRODUCT_NUM = p.PRODUCT_NUM
            WHERE t.HSHD_NUM = ?
            ORDER BY t.HSHD_NUM, t.BASKET_NUM, t.PURCHASE_DATE, t.PRODUCT_NUM, p.DEPARTMENT, p.COMMODITY
            LIMIT ? OFFSET ?
        """
        params = (hshd_num, per_page, offset)

    return db.execute(query, params).fetchall(), total


@app.route("/data-pull/content", methods=["GET"])
@login_required
def data_pull_content():
    hshd_num = request.args.get("hshd_num", "10")
    page = request.args.get("page", "1")
    try:
        hshd_num = int(hshd_num)
    except ValueError:
        hshd_num = 10
    try:
        page = int(page)
    except ValueError:
        page = 1
    rows, total = _get_data_pull_rows(hshd_num, page=page, per_page=50)
    total_pages = max(1, (total + 49) // 50)
    page = max(1, min(page, total_pages))
    if request.args.get("page", "1") != str(page):
        rows, total = _get_data_pull_rows(hshd_num, page=page, per_page=50)
        total_pages = max(1, (total + 49) // 50)
    if total:
        start_entry = (page - 1) * 50 + 1
        end_entry = min(page * 50, total)
    else:
        start_entry = 0
        end_entry = 0
    return render_template(
        "partials/data_pull_content.html",
        rows=rows,
        hshd_num=hshd_num,
        page=page,
        total=total,
        total_pages=total_pages,
        per_page=50,
        start_entry=start_entry,
        end_entry=end_entry,
    )

# ---------- Upload (Req 5) ----------
@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    if request.method == "POST":
        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
        upload_id = request.form.get("upload_id") or str(uuid.uuid4())
        started_at = time.monotonic()

        mode = request.form.get("mode", "upsert").strip().lower()
        if mode not in {"clear_load", "upsert"}:
            mode = "upsert"

        table_inputs = [("transactions", "transactions"), ("households", "households"), ("products", "products")]
        requested_files = [item for item in table_inputs if (request.files.get(item[0]) and allowed_file(request.files.get(item[0]).filename))]
        total_files = max(1, len(requested_files))

        _set_upload_progress(
            upload_id,
            status="running",
            percent=0,
            message="Preparing upload...",
            table=None,
            processed=0,
            total=0,
            started_at=started_at,
            eta_seconds=None,
        )

        results = []
        db = get_db()
        try:
            if mode == "clear_load":
                _set_upload_progress(upload_id, message="Clearing existing database rows...", percent=2)
                for table in ["transactions", "households", "products"]:
                    db.execute(f"DELETE FROM {table}")
                    db.commit()
                results.append("database: cleared existing rows from transactions, households, and products")

            for file_index, (file_key, table) in enumerate(table_inputs, start=1):
                f = request.files.get(file_key)
                if not (f and allowed_file(f.filename)):
                    continue

                filename = secure_filename(f.filename)
                path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                f.save(path)

                def progress_hook(processed, total, message, _table=table, _file_index=file_index):
                    file_fraction = (processed / total) if total else 1.0
                    overall = ((_file_index - 1) + file_fraction) / total_files
                    percent = max(2, min(99, int(overall * 100)))
                    elapsed = max(0.001, time.monotonic() - started_at)
                    eta_seconds = None
                    if percent > 0 and percent < 100:
                        eta_seconds = max(0, int(elapsed * (100 - percent) / percent))
                    _set_upload_progress(
                        upload_id,
                        status="running",
                        percent=percent,
                        message=message,
                        table=_table,
                        processed=processed,
                        total=total,
                        eta_seconds=eta_seconds,
                    )

                _set_upload_progress(upload_id, message=f"Uploading {table}...", table=table)
                summary = load_csv_to_table(db, path, table, mode="upsert", progress_hook=progress_hook)
                results.append(
                    f"{table}: {summary['applied']} rows applied (processed {summary['processed']} info: {summary['info']})"
                )

            db.commit()
            _set_upload_progress(
                upload_id,
                status="completed",
                percent=100,
                message="Upload completed.",
                eta_seconds=0,
            )
            return jsonify({"status": "ok", "mode": mode, "results": results, "upload_id": upload_id})
        except Exception as exc:
            _set_upload_progress(
                upload_id,
                status="failed",
                message=f"Upload failed: {exc}",
                eta_seconds=None,
            )
            raise
    return render_template("upload.html")


@app.route("/upload/progress", methods=["GET"])
@login_required
def upload_progress():
    upload_id = request.args.get("upload_id", "").strip()
    if not upload_id:
        return jsonify({"status": "missing", "message": "upload_id is required"}), 400

    with UPLOAD_PROGRESS_LOCK:
        info = UPLOAD_PROGRESS.get(upload_id)

    if not info:
        return jsonify({"status": "unknown", "message": "Upload id not found"}), 404

    return jsonify(info)


# ---------- ML endpoints ----------
@app.route("/ml/clv")
@login_required
def ml_clv():
    return render_template("ml_clv.html")

@app.route("/ml/clv/content")
@login_required
def ml_clv_content():
    result = run_clv()
    return render_template("partials/ml_clv_content.html", result=result)

@app.route("/ml/basket")
@login_required
def ml_basket():
    return render_template("ml_basket.html")

@app.route("/ml/basket/content")
@login_required
def ml_basket_content():
    result = run_basket()
    return render_template("partials/ml_basket_content.html", result=result)

@app.route("/ml/churn")
@login_required
def ml_churn():
    return render_template("ml_churn.html")

@app.route("/ml/churn/content")
@login_required
def ml_churn_content():
    result = run_churn()
    return render_template("partials/ml_churn_content.html", result=result)

# ---------- API for charts ----------
@app.route("/api/dashboard-data")
@login_required
def api_dashboard_data():
    return jsonify(get_dashboard_data())

if __name__ == "__main__":
    with app.app_context():
        if not USE_AZURE_SQL:
            init_db()
    app.run(debug=True, host="0.0.0.0", port=5500)
