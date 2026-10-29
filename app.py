from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    abort,
)
import os
import re
import psycopg2

from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor

load_dotenv()
from datetime import date, datetime
from werkzeug.security import generate_password_hash, check_password_hash

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL belum diatur. "
        "Tambahkan connection string Neon di file .env."
    )
app = Flask(__name__)
_secret_key = os.getenv("EDUTASK_SECRET_KEY")
if not _secret_key:
    if os.getenv("VERCEL") == "1":
        raise RuntimeError(
            "EDUTASK_SECRET_KEY belum diatur di Vercel Environment Variables."
        )
    _secret_key = "edutask-local-dev-only-change-before-deploy"
app.secret_key = _secret_key
PRODI = [
    "Teknik Pertambangan",
    "Teknik Perminyakan",
    "Teknik Metalurgi",
    "Teknik Sipil",
    "Perencanaan Wilayah dan Kota",
    "Bisnis Digital",
    "Desain Produk",
    "Informatika",
]
COURSES = [
    "Sistem Informasi Manajemen",
    "Basis Data",
    "Pemrograman Web",
    "Kecerdasan Bisnis",
    "Statistika",
    "Akuntansi Keuangan",
    "Manajemen Operasi",
    "Jaringan Komputer",
]



class DBResult:
    """Menyediakan hasil query yang kompatibel dengan pola SQLite lama."""

    def __init__(self, cursor, lastrowid=None):
        self.cursor = cursor
        self.lastrowid = lastrowid

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()

    def __iter__(self):
        return iter(self.cursor)

    def __getattr__(self, name):
        return getattr(self.cursor, name)


class DBConnection:
    """Adapter sementara agar pola query app.py lama tetap dapat dipakai."""

    def __init__(self):
        self.connection = psycopg2.connect(
            DATABASE_URL,
            cursor_factory=RealDictCursor,
            connect_timeout=10,
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            if exc_type is None:
                self.connection.commit()
            else:
                self.connection.rollback()
        finally:
            self.connection.close()
        return False

    def execute(self, sql, params=()):
        sql = sql.strip()
        upper_sql = sql.upper()

        if upper_sql.startswith("PRAGMA"):
            raise RuntimeError(
                "PRAGMA SQLite tidak didukung PostgreSQL. "
                "Hapus perintah PRAGMA dari kode."
            )

        # Konversi INSERT OR IGNORE menjadi INSERT ... ON CONFLICT.
        ignore_insert = bool(
            re.match(r"INSERT\s+OR\s+IGNORE\s+INTO\b", sql, re.I)
        )

        if ignore_insert:
            sql = re.sub(
                r"INSERT\s+OR\s+IGNORE\s+INTO\b",
                "INSERT INTO",
                sql,
                count=1,
                flags=re.I,
            )

            if "ON CONFLICT" not in sql.upper():
                sql = sql.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"

        # Query lama memakai kutip ganda untuk literal SQLite, misalnya role="mahasiswa".
        # PostgreSQL memerlukan kutip tunggal untuk literal string. Query ini tidak
        # menggunakan quoted identifiers, jadi konversi ini sesuai untuk SQL aplikasi.
        sql = re.sub(
            r'"([^"]*)"',
            lambda match: "'" + match.group(1).replace("'", "''") + "'",
            sql,
        )
        # Konversi placeholder SQLite (?) ke placeholder psycopg2 (%s).
        sql = sql.replace("?", "%s")

        upper_sql = sql.upper()
        is_insert = upper_sql.startswith("INSERT INTO")
        auto_returning = (
            is_insert
            and "RETURNING" not in upper_sql
            and "ON CONFLICT" not in upper_sql
        )

        if auto_returning:
            sql = sql.rstrip().rstrip(";") + " RETURNING id"

        cursor = self.connection.cursor()
        cursor.execute(sql, params)

        lastrowid = None

        if auto_returning:
            row = cursor.fetchone()
            if row is not None:
                lastrowid = row["id"]

        return DBResult(cursor, lastrowid)

    def executescript(self, script):
        # Ubah tipe kolom khusus SQLite ke tipe PostgreSQL.
        script = re.sub(
            r"\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b",
            "BIGSERIAL PRIMARY KEY",
            script,
            flags=re.I,
        )
        script = re.sub(r"\bINTEGER\b", "BIGINT", script, flags=re.I)

        for statement in script.split(";"):
            statement = statement.strip()
            if statement:
                self.execute(statement)

    def close(self):
        self.connection.close()


def db():
    return DBConnection()

def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, prodi TEXT NOT NULL,
          nim TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL,
          payment_status TEXT NOT NULL DEFAULT 'aktif', created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS lecturer_courses (
          id INTEGER PRIMARY KEY AUTOINCREMENT, lecturer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          prodi TEXT NOT NULL, course TEXT NOT NULL, UNIQUE(lecturer_id, prodi, course)
        );
        CREATE TABLE IF NOT EXISTS tasks (
          id INTEGER PRIMARY KEY AUTOINCREMENT, lecturer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          prodi TEXT NOT NULL, course TEXT NOT NULL, title TEXT NOT NULL, description TEXT NOT NULL,
          deadline TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS submissions (
          id INTEGER PRIMARY KEY AUTOINCREMENT, task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
          student_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, progress INTEGER NOT NULL DEFAULT 0,
          status TEXT NOT NULL DEFAULT 'Belum dikerjakan', submitted_at TEXT, updated_at TEXT NOT NULL,
          UNIQUE(task_id, student_id)
        );
        CREATE TABLE IF NOT EXISTS exams (
          id INTEGER PRIMARY KEY AUTOINCREMENT, lecturer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          prodi TEXT NOT NULL, course TEXT NOT NULL, title TEXT NOT NULL, exam_date TEXT NOT NULL,
          location TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS notifications (
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          title TEXT NOT NULL, message TEXT NOT NULL, created_at TEXT NOT NULL, seen INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS activity_logs (
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          action TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL
        );
        """)
        # Akun demo hanya dibuat jika diaktifkan secara eksplisit.
        # Jangan aktifkan SEED_DEMO_USERS di deployment publik karena password demo diketahui.
        if os.getenv("SEED_DEMO_USERS", "false").lower() == "true":
            # Demo lecturer for first run
            row = c.execute("SELECT id FROM users WHERE nim=?", ("dosen001",)).fetchone()
            if not row:
                cur = c.execute(
                    "INSERT INTO users(name,prodi,nim,password_hash,role,payment_status,created_at) VALUES(?,?,?,?,?,?,?)",
                    (
                        "Dosen Demo",
                        PRODI[0],
                        "dosen001",
                        generate_password_hash("dosen123"),
                        "dosen",
                        "aktif",
                        datetime.now().isoformat(timespec="seconds"),
                    ),
                )
                lid = cur.lastrowid
                c.execute(
                    "INSERT INTO lecturer_courses(lecturer_id,prodi,course) VALUES(?,?,?)",
                    (lid, PRODI[0], COURSES[0]),
                )
            if not c.execute("SELECT id FROM users WHERE nim=?", ("admin",)).fetchone():
                c.execute(
                    "INSERT INTO users(name,prodi,nim,password_hash,role,payment_status,created_at) VALUES(?,?,?,?,?,?,?)",
                    (
                        "Administrator",
                        PRODI[0],
                        "admin",
                        generate_password_hash("admin123"),
                        "admin",
                        "aktif",
                        datetime.now().isoformat(timespec="seconds"),
                    ),
                )


def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    with db() as c:
        return c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()


def login_required(role=None):
    u = current_user()
    if not u:
        flash("Silakan masuk terlebih dahulu.", "error")
        return redirect(url_for("index"))
    if role and u["role"] != role:
        abort(403)
    return None


def log_action(user_id, action, detail=""):
    with db() as c:
        c.execute(
            "INSERT INTO activity_logs(user_id,action,detail,created_at) VALUES(?,?,?,?)",
            (user_id, action, detail, datetime.now().isoformat(timespec="seconds")),
        )


def notify(user_id, title, message):
    with db() as c:
        c.execute(
            "INSERT INTO notifications(user_id,title,message,created_at) VALUES(?,?,?,?)",
            (user_id, title, message, datetime.now().isoformat(timespec="seconds")),
        )


def student_tasks(student):
    today = date.today().isoformat()
    with db() as c:
        rows = c.execute(
            """SELECT t.*, s.progress, s.status, s.submitted_at, s.updated_at, u.name AS lecturer_name
          FROM tasks t JOIN users u ON u.id=t.lecturer_id
          LEFT JOIN submissions s ON s.task_id=t.id AND s.student_id=?
          WHERE t.prodi=? AND EXISTS (SELECT 1 FROM lecturer_courses lc WHERE lc.lecturer_id=t.lecturer_id AND lc.prodi=t.prodi AND lc.course=t.course)
          ORDER BY t.deadline ASC""",
            (student["id"], student["prodi"]),
        ).fetchall()
    result = []
    for r in rows:
        x = dict(r)
        x["progress"] = x["progress"] if x["progress"] is not None else 0
        x["status"] = x["status"] or "Belum dikerjakan"
        x["days_left"] = (date.fromisoformat(x["deadline"]) - date.today()).days
        if x["status"] != "Selesai" and x["days_left"] < 0:
            x["display_status"] = "Terlambat"
        elif x["status"] == "Selesai":
            x["display_status"] = "Selesai"
        elif x["progress"] > 0:
            x["display_status"] = "Sedang dikerjakan"
        else:
            x["display_status"] = "Belum dikerjakan"
        result.append(x)
    return result


@app.context_processor
def common_context():
    u = current_user()
    return {
        "user": u,
        "today": date.today().isoformat(),
        "PRODI": PRODI,
        "COURSES": COURSES,
    }


@app.route("/")
def index():
    if current_user():
        u = current_user()
        return redirect(
            url_for(
                {
                    "mahasiswa": "m_dashboard",
                    "dosen": "d_dashboard",
                    "admin": "admin_dashboard",
                }[u["role"]]
            )
        )
    return render_template("landing.html")


@app.route("/register/mahasiswa", methods=["GET", "POST"])
def m_register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        prodi = request.form.get("prodi", "")
        nim = request.form.get("nim", "").strip()
        pw = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if (
            not name
            or prodi not in PRODI
            or not nim.isdigit()
            or not (5 <= len(nim) <= 20)
        ):
            flash("Lengkapi data. NIM harus 5–20 digit angka.", "error")
        elif len(pw) < 6:
            flash("Password minimal 6 karakter.", "error")
        elif pw != confirm:
            flash("Konfirmasi password tidak sama.", "error")
        else:
            try:
                with db() as c:
                    cur = c.execute(
                        "INSERT INTO users(name,prodi,nim,password_hash,role,payment_status,created_at) VALUES(?,?,?,?,?,?,?)",
                        (
                            name,
                            prodi,
                            nim,
                            generate_password_hash(pw),
                            "mahasiswa",
                            "menunggu",
                            datetime.now().isoformat(timespec="seconds"),
                        ),
                    )
                    uid = cur.lastrowid
                session["pending_payment"] = uid
                return redirect(url_for("payment"))
            except psycopg2.IntegrityError:
                flash("NIM sudah terdaftar. Silakan masuk.", "error")
    return render_template("pages/mahasiswa/register.html")


@app.route("/register/dosen", methods=["GET", "POST"])
def d_register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        prodi = request.form.getlist("prodi")
        courses = request.form.getlist("course")
        nim = request.form.get("nim", "").strip()
        pw = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if (
            not name
            or not nim
            or not (nim.isalnum() and 5 <= len(nim) <= 20)
            or not prodi
            or not courses
        ):
            flash("Isi data dan pilih minimal satu prodi serta mata kuliah.", "error")
        elif len(pw) < 6:
            flash("Password minimal 6 karakter.", "error")
        elif pw != confirm:
            flash("Konfirmasi password tidak sama.", "error")
        else:
            try:
                with db() as c:
                    cur = c.execute(
                        "INSERT INTO users(name,prodi,nim,password_hash,role,payment_status,created_at) VALUES(?,?,?,?,?,?,?)",
                        (
                            name,
                            prodi[0],
                            nim,
                            generate_password_hash(pw),
                            "dosen",
                            "aktif",
                            datetime.now().isoformat(timespec="seconds"),
                        ),
                    )
                    uid = cur.lastrowid
                    for p in prodi:
                        for course in courses:
                            c.execute(
                                "INSERT OR IGNORE INTO lecturer_courses(lecturer_id,prodi,course) VALUES(?,?,?)",
                                (uid, p, course),
                            )
                session["user_id"] = uid
                log_action(uid, "Registrasi dosen", "Akun dosen dibuat")
                flash("Akun dosen berhasil dibuat.", "success")
                return redirect(url_for("d_dashboard"))
            except psycopg2.IntegrityError:
                flash("NIM/ID dosen sudah terdaftar.", "error")
    return render_template("pages/dosen/register.html")


@app.route("/payment", methods=["GET", "POST"])
def payment():
    uid = session.get("pending_payment")
    if not uid:
        return redirect(url_for("m_register"))
    with db() as c:
        student = c.execute(
            'SELECT * FROM users WHERE id=? AND role="mahasiswa"', (uid,)
        ).fetchone()
    if not student:
        session.pop("pending_payment", None)
        return redirect(url_for("m_register"))
    if request.method == "POST":
        method = request.form.get("method", "")
        if method not in ["Virtual Account", "QRIS", "E-Wallet"]:
            flash("Pilih metode pembayaran.", "error")
        else:
            with db() as c:
                c.execute("UPDATE users SET payment_status='aktif' WHERE id=?", (uid,))
            session.pop("pending_payment", None)
            session["user_id"] = uid
            log_action(uid, "Pembayaran simulasi", method)
            flash("Pembayaran simulasi berhasil. Akun mahasiswa aktif.", "success")
            return redirect(url_for("m_dashboard"))
    return render_template("pages/mahasiswa/payment.html", student=student)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        nim = request.form.get("nim", "").strip()
        pw = request.form.get("password", "")
        with db() as c:
            u = c.execute("SELECT * FROM users WHERE nim=?", (nim,)).fetchone()
        if not u or not check_password_hash(u["password_hash"], pw):
            flash("NIM/ID atau password salah.", "error")
        elif u["payment_status"] != "aktif":
            session["pending_payment"] = u["id"]
            return redirect(url_for("payment"))
        else:
            session.clear()
            session["user_id"] = u["id"]
            log_action(u["id"], "Masuk", "Login berhasil")
            return redirect(
                url_for(
                    {
                        "mahasiswa": "m_dashboard",
                        "dosen": "d_dashboard",
                        "admin": "admin_dashboard",
                    }[u["role"]]
                )
            )
    return render_template("login.html")


@app.route("/logout")
def logout():
    u = current_user()
    if u:
        log_action(u["id"], "Keluar", "Logout")
    session.clear()
    flash("Anda berhasil keluar.", "success")
    return redirect(url_for("index"))


@app.route("/mahasiswa")
def m_dashboard():
    r = login_required("mahasiswa")
    if r:
        return r
    u = current_user()
    tasks = student_tasks(u)
    stats = {
        "total": len(tasks),
        "open": sum(t["display_status"] != "Selesai" for t in tasks),
        "soon": sum(
            t["display_status"] != "Selesai" and 0 <= t["days_left"] <= 3 for t in tasks
        ),
        "late": sum(t["display_status"] == "Terlambat" for t in tasks),
        "done": sum(t["display_status"] == "Selesai" for t in tasks),
    }
    return render_template("pages/mahasiswa/dashboard.html", tasks=tasks, stats=stats)


@app.route("/mahasiswa/tugas")
def m_tasks():
    r = login_required("mahasiswa")
    if r:
        return r
    return render_template(
        "pages/mahasiswa/tugas.html", tasks=student_tasks(current_user())
    )


@app.route("/mahasiswa/tugas/<int:task_id>/progres", methods=["POST"])
def m_progress(task_id):
    r = login_required("mahasiswa")
    if r:
        return r
    u = current_user()
    progress = max(0, min(100, int(request.form.get("progress", 0))))
    tasks = student_tasks(u)
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        abort(404)
    status = (
        "Selesai"
        if progress == 100
        else ("Sedang dikerjakan" if progress > 0 else "Belum dikerjakan")
    )
    submitted = (
        datetime.now().isoformat(timespec="seconds") if progress == 100 else None
    )
    with db() as c:
        c.execute(
            """INSERT INTO submissions(task_id,student_id,progress,status,submitted_at,updated_at) VALUES(?,?,?,?,?,?)
          ON CONFLICT(task_id,student_id) DO UPDATE SET progress=excluded.progress,status=excluded.status,submitted_at=excluded.submitted_at,updated_at=excluded.updated_at""",
            (
                task_id,
                u["id"],
                progress,
                status,
                submitted,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        lecturer_id = task["lecturer_id"]
        lecturer = c.execute(
            "SELECT id FROM users WHERE id=?", (lecturer_id,)
        ).fetchone()
    notify(
        lecturer_id,
        "Pembaruan tugas mahasiswa",
        f"{u['name']} memperbarui progres '{task['title']}' menjadi {progress}%.",
    )
    log_action(u["id"], "Perbarui progres", task["title"] + " — " + str(progress) + "%")
    flash("Progres tugas diperbarui.", "success")
    return redirect(url_for("m_tasks"))


@app.route("/mahasiswa/kalender")
def m_calendar():
    r = login_required("mahasiswa")
    if r:
        return r
    u = current_user()
    with db() as c:
        exams = c.execute(
            "SELECT e.*,u.name AS lecturer_name FROM exams e JOIN users u ON u.id=e.lecturer_id WHERE e.prodi=? ORDER BY e.exam_date",
            (u["prodi"],),
        ).fetchall()
    return render_template(
        "pages/mahasiswa/calendar.html", exams=exams, tasks=student_tasks(u)
    )


@app.route("/mahasiswa/notifikasi")
def m_notifications():
    r = login_required("mahasiswa")
    if r:
        return r
    u = current_user()
    tasks = student_tasks(u)
    with db() as c:
        personal = c.execute(
            "SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC",
            (u["id"],),
        ).fetchall()
        exams = c.execute(
            "SELECT * FROM exams WHERE prodi=? AND exam_date>=? ORDER BY exam_date",
            (u["prodi"], date.today().isoformat()),
        ).fetchall()
    return render_template(
        "pages/mahasiswa/notifications.html",
        notifications=personal,
        tasks=tasks,
        exams=exams,
    )


@app.route("/mahasiswa/riwayat")
def m_history():
    r = login_required("mahasiswa")
    if r:
        return r
    u = current_user()
    with db() as c:
        logs = c.execute(
            "SELECT * FROM activity_logs WHERE user_id=? ORDER BY created_at DESC",
            (u["id"],),
        ).fetchall()
        subs = c.execute(
            "SELECT s.*,t.title,t.course,t.deadline FROM submissions s JOIN tasks t ON t.id=s.task_id WHERE s.student_id=? ORDER BY s.updated_at DESC",
            (u["id"],),
        ).fetchall()
    return render_template("pages/mahasiswa/history.html", logs=logs, submissions=subs)


@app.route("/dosen")
def d_dashboard():
    r = login_required("dosen")
    if r:
        return r
    u = current_user()
    with db() as c:
        courses = c.execute(
            "SELECT * FROM lecturer_courses WHERE lecturer_id=? ORDER BY prodi,course",
            (u["id"],),
        ).fetchall()
        tasks = c.execute(
            "SELECT * FROM tasks WHERE lecturer_id=? ORDER BY deadline", (u["id"],)
        ).fetchall()
        students = c.execute(
            'SELECT * FROM users WHERE role="mahasiswa" AND payment_status="aktif" AND prodi IN (SELECT prodi FROM lecturer_courses WHERE lecturer_id=?) ORDER BY prodi,name',
            (u["id"],),
        ).fetchall()
        stats = {
            "students": len(students),
            "tasks": len(tasks),
            "submitted": c.execute(
                'SELECT COUNT(*) n FROM submissions s JOIN tasks t ON t.id=s.task_id WHERE t.lecturer_id=? AND s.status="Selesai"',
                (u["id"],),
            ).fetchone()["n"],
            "pending": c.execute(
                'SELECT COUNT(*) n FROM tasks t JOIN users st ON st.role="mahasiswa" AND st.prodi=t.prodi LEFT JOIN submissions s ON s.task_id=t.id AND s.student_id=st.id WHERE t.lecturer_id=? AND (s.status IS NULL OR s.status!="Selesai")',
                (u["id"],),
            ).fetchone()["n"],
            "late": c.execute(
                'SELECT COUNT(*) n FROM tasks t JOIN users st ON st.role="mahasiswa" AND st.prodi=t.prodi LEFT JOIN submissions s ON s.task_id=t.id AND s.student_id=st.id WHERE t.lecturer_id=? AND t.deadline<? AND (s.status IS NULL OR s.status!="Selesai")',
                (u["id"], date.today().isoformat()),
            ).fetchone()["n"],
        }
        student_rows = c.execute(
            """SELECT st.name,st.nim,st.prodi,t.title,t.course,t.deadline,COALESCE(s.progress,0) progress,COALESCE(s.status,'Belum dikerjakan') status FROM tasks t JOIN users st ON st.role='mahasiswa' AND st.prodi=t.prodi LEFT JOIN submissions s ON s.task_id=t.id AND s.student_id=st.id WHERE t.lecturer_id=? ORDER BY t.deadline,st.name""",
            (u["id"],),
        ).fetchall()
    return render_template(
        "pages/dosen/dashboard.html",
        stats=stats,
        students=students,
        tasks=tasks,
        student_rows=student_rows,
        courses=courses,
    )


@app.route("/dosen/tugas", methods=["GET", "POST"])
def d_tasks():
    r = login_required("dosen")
    if r:
        return r
    u = current_user()
    with db() as c:
        courses = c.execute(
            "SELECT * FROM lecturer_courses WHERE lecturer_id=? ORDER BY prodi,course",
            (u["id"],),
        ).fetchall()
    if request.method == "POST":
        action = request.form.get("action", "create")
        if action == "delete":
            tid = request.form.get("task_id", type=int)
            with db() as c:
                c.execute(
                    "DELETE FROM tasks WHERE id=? AND lecturer_id=?", (tid, u["id"])
                )
            flash("Tugas dihapus.", "success")
            return redirect(url_for("d_tasks"))
        title = request.form.get("title", "").strip()
        desc = request.form.get("description", "").strip()
        deadline = request.form.get("deadline", "")
        course = request.form.get("course", "")
        prodi = request.form.get("prodi", "")
        if (
            not title
            or not deadline
            or not any(x["course"] == course and x["prodi"] == prodi for x in courses)
        ):
            flash("Pilih mata kuliah yang terdaftar dan isi data tugas.", "error")
        else:
            try:
                date.fromisoformat(deadline)
            except ValueError:
                flash("Format deadline tidak valid.", "error")
            else:
                with db() as c:
                    if action == "edit":
                        tid = request.form.get("task_id", type=int)
                        c.execute(
                            "UPDATE tasks SET prodi=?,course=?,title=?,description=?,deadline=? WHERE id=? AND lecturer_id=?",
                            (prodi, course, title, desc, deadline, tid, u["id"]),
                        )
                        tid = tid
                    else:
                        cur = c.execute(
                            "INSERT INTO tasks(lecturer_id,prodi,course,title,description,deadline,created_at) VALUES(?,?,?,?,?,?,?)",
                            (
                                u["id"],
                                prodi,
                                course,
                                title,
                                desc,
                                deadline,
                                datetime.now().isoformat(timespec="seconds"),
                            ),
                        )
                        tid = cur.lastrowid
                        students = c.execute(
                            'SELECT id FROM users WHERE role="mahasiswa" AND prodi=? AND payment_status="aktif"',
                            (prodi,),
                        ).fetchall()
                        for st in students:
                            c.execute(
                                "INSERT INTO notifications(user_id,title,message,created_at) VALUES(?,?,?,?)",
                                (
                                    st["id"],
                                    "Tugas baru",
                                    f"{course}: {title} — deadline {deadline}",
                                    datetime.now().isoformat(timespec="seconds"),
                                ),
                            )
                log_action(u["id"], "Kelola tugas", title)
                flash("Tugas berhasil disimpan.", "success")
                return redirect(url_for("d_tasks"))
    with db() as c:
        tasks = c.execute(
            "SELECT * FROM tasks WHERE lecturer_id=? ORDER BY deadline", (u["id"],)
        ).fetchall()
        subs = c.execute(
            "SELECT s.*,st.name,st.nim,t.title,t.deadline FROM submissions s JOIN users st ON st.id=s.student_id JOIN tasks t ON t.id=s.task_id WHERE t.lecturer_id=? ORDER BY s.updated_at DESC",
            (u["id"],),
        ).fetchall()
    return render_template(
        "pages/dosen/tugas.html", courses=courses, tasks=tasks, submissions=subs
    )


@app.route("/dosen/kalender", methods=["GET", "POST"])
def d_calendar():
    r = login_required("dosen")
    if r:
        return r
    u = current_user()
    with db() as c:
        courses = c.execute(
            "SELECT * FROM lecturer_courses WHERE lecturer_id=? ORDER BY prodi,course",
            (u["id"],),
        ).fetchall()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        prodi = request.form.get("prodi", "")
        course = request.form.get("course", "")
        exam_date = request.form.get("exam_date", "")
        location = request.form.get("location", "").strip()
        notes = request.form.get("notes", "").strip()
        if (
            not title
            or not exam_date
            or not any(x["prodi"] == prodi and x["course"] == course for x in courses)
        ):
            flash(
                "Lengkapi jadwal ujian dengan prodi dan mata kuliah yang sesuai.",
                "error",
            )
        else:
            with db() as c:
                c.execute(
                    "INSERT INTO exams(lecturer_id,prodi,course,title,exam_date,location,notes,created_at) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        u["id"],
                        prodi,
                        course,
                        title,
                        exam_date,
                        location,
                        notes,
                        datetime.now().isoformat(timespec="seconds"),
                    ),
                )
                students = c.execute(
                    'SELECT id FROM users WHERE role="mahasiswa" AND prodi=? AND payment_status="aktif"',
                    (prodi,),
                ).fetchall()
                for st in students:
                    c.execute(
                        "INSERT INTO notifications(user_id,title,message,created_at) VALUES(?,?,?,?)",
                        (
                            st["id"],
                            "Jadwal ujian baru",
                            f"{title} ({course}) dijadwalkan {exam_date}. {location}",
                            datetime.now().isoformat(timespec="seconds"),
                        ),
                    )
            log_action(u["id"], "Tambah jadwal ujian", title)
            flash(
                "Jadwal ujian ditambahkan dan mahasiswa prodi terkait diberi notifikasi.",
                "success",
            )
            return redirect(url_for("d_calendar"))
    with db() as c:
        exams = c.execute(
            "SELECT * FROM exams WHERE lecturer_id=? ORDER BY exam_date", (u["id"],)
        ).fetchall()
    return render_template("pages/dosen/calendar.html", courses=courses, exams=exams)


@app.route("/dosen/notifikasi")
def d_notifications():
    r = login_required("dosen")
    if r:
        return r
    u = current_user()
    with db() as c:
        notifications = c.execute(
            "SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC",
            (u["id"],),
        ).fetchall()
        subs = c.execute(
            "SELECT s.*,st.name,st.nim,t.title,t.deadline,t.course FROM submissions s JOIN users st ON st.id=s.student_id JOIN tasks t ON t.id=s.task_id WHERE t.lecturer_id=? ORDER BY s.updated_at DESC",
            (u["id"],),
        ).fetchall()
    return render_template(
        "pages/dosen/notifications.html", notifications=notifications, submissions=subs
    )


@app.route("/dosen/riwayat")
def d_history():
    r = login_required("dosen")
    if r:
        return r
    u = current_user()
    with db() as c:
        logs = c.execute(
            'SELECT l.*,u.name,u.nim FROM activity_logs l JOIN users u ON u.id=l.user_id WHERE u.role="dosen" OR (u.role="mahasiswa" AND u.prodi IN (SELECT prodi FROM lecturer_courses WHERE lecturer_id=?)) ORDER BY l.created_at DESC LIMIT 150',
            (u["id"],),
        ).fetchall()
        subs = c.execute(
            "SELECT s.*,st.name,st.nim,t.title,t.course,t.deadline FROM submissions s JOIN users st ON st.id=s.student_id JOIN tasks t ON t.id=s.task_id WHERE t.lecturer_id=? ORDER BY s.updated_at DESC",
            (u["id"],),
        ).fetchall()
    return render_template("pages/dosen/history.html", logs=logs, submissions=subs)


@app.route("/admin")
def admin_dashboard():
    r = login_required("admin")
    if r:
        return r
    with db() as c:
        students = c.execute(
            'SELECT * FROM users WHERE role="mahasiswa" ORDER BY created_at DESC'
        ).fetchall()
        lecturers = c.execute(
            'SELECT * FROM users WHERE role="dosen" ORDER BY created_at DESC'
        ).fetchall()
        tasks = c.execute(
            "SELECT t.*,u.name lecturer_name FROM tasks t JOIN users u ON u.id=t.lecturer_id ORDER BY t.deadline DESC"
        ).fetchall()
        logs = c.execute(
            "SELECT l.*,u.name,u.nim FROM activity_logs l JOIN users u ON u.id=l.user_id ORDER BY l.created_at DESC LIMIT 100"
        ).fetchall()
    return render_template(
        "admin.html", students=students, lecturers=lecturers, tasks=tasks, logs=logs
    )


@app.errorhandler(403)
def forbidden(e):
    return (
        render_template(
            "error.html", code=403, message="Anda tidak memiliki akses ke halaman ini."
        ),
        403,
    )


@app.errorhandler(404)
def not_found(e):
    return (
        render_template(
            "error.html", code=404, message="Halaman atau data tidak ditemukan."
        ),
        404,
    )


init_db()
if __name__ == "__main__":
    app.run(debug=True, port=5000)
