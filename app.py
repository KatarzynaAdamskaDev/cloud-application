from flask import Flask, render_template, request, redirect, url_for, session, flash
import pyodbc
import os
import hashlib
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "projekt-liga-2026-bezpieczny-klucz")

CACHED_DRIVER = None

# =========================
# POŁĄCZENIE Z BAZĄ DANYCH
# =========================

def get_db_conn():
    """Połączenie z Azure SQL, z cache'owaniem sterownika."""
    global CACHED_DRIVER
    raw_conn_str = os.environ.get("DATABASE_URL")
    if not raw_conn_str:
        return None

    drivers = [CACHED_DRIVER] if CACHED_DRIVER else [
        '{ODBC Driver 18 for SQL Server}',
        '{ODBC Driver 17 for SQL Server}'
    ]

    for driver in drivers:
        if not driver:
            continue
        try:
            conn_str = raw_conn_str.replace("{ODBC Driver 17 for SQL Server}", driver)
            if "18" in driver:
                conn_str += ";Encrypt=yes;TrustServerCertificate=yes;"
                conn_str = conn_str.replace("TrustServerCertificate=no", "TrustServerCertificate=yes")

            conn = pyodbc.connect(conn_str, timeout=3)
            CACHED_DRIVER = driver
            return conn
        except:
            continue
    return None

# =========================
# POMOCNICZE
# =========================

def hash_password(pwd: str) -> str:
    """Proste hashowanie haseł (SHA-256)."""
    return hashlib.sha256(pwd.encode("utf-8")).hexdigest()

def normalize_role(role: str) -> str:
    """Normalizuje rolę, aby dekorator działał poprawnie."""
    if not role:
        return ""
    return role.strip().capitalize()

def role_required(*roles):
    """Dekorator do kontroli ról (Administrator, Trener, Uzytkownik)."""
    normalized = [normalize_role(r) for r in roles]

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            user_role = normalize_role(session.get("rola", ""))
            if user_role not in normalized:
                flash("Brak uprawnień do tego zasobu.", "danger")
                return redirect(url_for("index"))
            return f(*args, **kwargs)
        return wrapper
    return decorator

def analiza_skutecznosci(zawodnicy):
    """Proste drzewo decyzyjne dla zawodników."""
    if not zawodnicy:
        return None
    najlepszy = None
    max_score = -1
    for z in zawodnicy:
        imie, nazwisko, gole, asysty = z[0], z[1], z[2], z[3]
        score = (gole * 3) + (asysty * 1)
        if score > max_score:
            max_score = score
            najlepszy = {
                "nazwa": f"{imie} {nazwisko}",
                "gole": gole,
                "asysty": asysty,
                "score": score
            }
    return najlepszy

# =========================
# LOGOWANIE / REJESTRACJA
# =========================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        l_val = request.form.get("login")
        p_val = request.form.get("password")
        hashed = hash_password(p_val)
        conn = get_db_conn()
        if not conn:
            flash("Brak połączenia z bazą danych.", "danger")
            return render_template("login.html")
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT UzytkownikID, Rola FROM Uzytkownik WHERE Login = ? AND HasloHash = ?", (l_val, hashed))
            user = cursor.fetchone()
        finally:
            conn.close()
        if user:
            session.update({
                "user_id": user[0],
                "user_login": l_val,
                "rola": normalize_role(user[1])
            })
            flash("Zalogowano pomyślnie!", "success")
            return redirect(url_for("index"))
        else:
            flash("Błędny login lub hasło!", "danger")
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        l_val = request.form.get("login")
        p_val = request.form.get("password")
        hashed = hash_password(p_val)
        conn = get_db_conn()
        if not conn:
            flash("Brak połączenia z bazą danych.", "danger")
            return render_template("register.html")
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT Login FROM Uzytkownik WHERE Login = ?", (l_val,))
            if cursor.fetchone():
                flash("Ten login jest już zajęty!", "warning")
            else:
                cursor.execute("INSERT INTO Uzytkownik (Login, HasloHash, Rola) VALUES (?, ?, 'Uzytkownik')", (l_val, hashed))
                conn.commit()
                flash("Konto utworzone!", "success")
                return redirect(url_for("login"))
        finally:
            conn.close()
    return render_template("register.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Wylogowano.", "info")
    return redirect(url_for("login"))

# =========================
# PANEL ADMINA
# =========================

@app.route("/admin")
@role_required("Administrator")
def admin_panel():
    conn = get_db_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT UzytkownikID, Login, Rola FROM Uzytkownik")
        users = cursor.fetchall()
    finally:
        conn.close()
    return render_template("admin.html", users=users)

@app.route("/promote/<int:uid>/<string:role>")
@role_required("Administrator")
def promote(uid, role):
    new_role = normalize_role(role)
    conn = get_db_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE Uzytkownik SET Rola = ? WHERE UzytkownikID = ?", (new_role, uid))
        conn.commit()
        flash(f"Zmieniono rolę na: {new_role}", "info")
    finally:
        conn.close()
    return redirect(url_for("admin_panel"))

# =========================
# ZARZĄDZANIE MECZAMI (DODAWANIE / EDYCJA / USUWANIE)
# =========================

@app.route("/admin/mecze", methods=["GET", "POST"])
@role_required("Administrator")
def admin_mecze():
    conn = get_db_conn()
    if request.method == "POST":
        gosp = request.form.get("gospodarz_id")
        gosc = request.form.get("gosc_id")
        data = request.form.get("data")
        wg = request.form.get("wynik_g")
        wgo = request.form.get("wynik_gosc")
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO Mecz (DruzynaGospodarzID, DruzynaGoscID, WynikGospodarz, WynikGosc, DataMeczu, StatusMeczu, TerminarzID)
                VALUES (?, ?, ?, ?, ?, 'zakończony', 1)
            """, (int(gosp), int(gosc), int(wg) if wg else None, int(wgo) if wgo else None, data))
            conn.commit()
            flash("Dodano mecz.", "success")
        except Exception as e:
            flash(f"Błąd: {e}", "danger")
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT m.MeczID, m.DataMeczu, d1.Nazwa, d2.Nazwa, m.WynikGospodarz, m.WynikGosc
            FROM Mecz m
            JOIN Druzyna d1 ON m.DruzynaGospodarzID = d1.DruzynaID
            JOIN Druzyna d2 ON m.DruzynaGoscID = d2.DruzynaID
            ORDER BY m.DataMeczu DESC
        """)
        matches = cursor.fetchall()
        cursor.execute("SELECT DruzynaID, Nazwa FROM Druzyna ORDER BY Nazwa")
        teams = cursor.fetchall()
    finally:
        conn.close()
    return render_template("admin_mecze.html", matches=matches, teams=teams)

@app.route("/admin/mecz/<int:mecz_id>/edit", methods=["GET", "POST"])
@role_required("Administrator")
def admin_mecz_edit(mecz_id):
    """Edycja danych meczu."""
    conn = get_db_conn()
    try:
        cursor = conn.cursor()
        if request.method == "POST":
            data = request.form.get("data")
            wg = request.form.get("wynik_g")
            wgo = request.form.get("wynik_gosc")
            cursor.execute("""
                UPDATE Mecz SET DataMeczu = ?, WynikGospodarz = ?, WynikGosc = ?
                WHERE MeczID = ?
            """, (data, int(wg) if wg else None, int(wgo) if wgo else None, mecz_id))
            conn.commit()
            flash("Zaktualizowano mecz.", "success")
            return redirect(url_for("admin_mecze"))
        
        cursor.execute("""
            SELECT m.MeczID, m.DataMeczu, d1.Nazwa, d2.Nazwa, m.WynikGospodarz, m.WynikGosc
            FROM Mecz m
            JOIN Druzyna d1 ON m.DruzynaGospodarzID = d1.DruzynaID
            JOIN Druzyna d2 ON m.DruzynaGoscID = d2.DruzynaID
            WHERE m.MeczID = ?
        """, (mecz_id,))
        match = cursor.fetchone()
    finally:
        conn.close()
    return render_template("admin_mecz_edit.html", match=match)

@app.route("/admin/mecz/<int:mecz_id>/delete")
@role_required("Administrator")
def admin_mecz_delete(mecz_id):
    conn = get_db_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM Gol WHERE MeczID = ?", (mecz_id,))
        cursor.execute("DELETE FROM Mecz WHERE MeczID = ?", (mecz_id,))
        conn.commit()
        flash("Usunięto mecz.", "info")
    finally:
        conn.close()
    return redirect(url_for("admin_mecze"))

# =========================
# POZOSTAŁE FUNKCJE (Główne, Trener, API)
# =========================

@app.route("/")
def index():
    conn = get_db_conn()
    if not conn: return render_template("index.html", data={})
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT z.Imie, z.Nazwisko, COUNT(g.GolID), 0 FROM Zawodnik z LEFT JOIN Gol g ON g.ZawodnikID = z.ZawodnikID GROUP BY z.Imie, z.Nazwisko")
        best_player = analiza_skutecznosci(cursor.fetchall())
        cursor.execute("SELECT TOP 1 Nazwa, Punkty FROM Druzyna ORDER BY Punkty DESC")
        lider = cursor.fetchone()
        cursor.execute("SELECT TOP 1 NazwaSezonu, Status FROM TerminarzRozgrywek ORDER BY DataRozpoczecia DESC")
        sezon = cursor.fetchone()
        cursor.execute("SELECT m.DataMeczu, d1.Nazwa, d2.Nazwa, m.WynikGospodarz, m.WynikGosc FROM Mecz m JOIN Druzyna d1 ON m.DruzynaGospodarzID = d1.DruzynaID JOIN Druzyna d2 ON m.DruzynaGoscID = d2.DruzynaID ORDER BY m.DataMeczu DESC")
        matches = cursor.fetchall()
        data = {'team': lider, 'player': best_player, 'season': sezon, 'matches': matches}
    finally:
        conn.close()
    return render_template("index.html", data=data)

# Tutaj możesz dokleić resztę swoich tras (/druzyny, /trener, /api/lost_goals itp.) z Twojego pliku.

if __name__ == "__main__":
    app.run(debug=True)
