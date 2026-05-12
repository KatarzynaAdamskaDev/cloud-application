from flask import Flask, render_template, request, redirect, url_for, session, flash
import pyodbc
import os
import hashlib
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "projekt-liga-2026-bezpieczny-klucz")

CACHED_DRIVER = None


def get_db_conn():
    """Połączenie z Azure SQL, z cache'owaniem sterownika (pseudo-singleton)."""
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


def hash_password(pwd: str) -> str:
    """Proste hashowanie haseł (SHA-256)."""
    return hashlib.sha256(pwd.encode("utf-8")).hexdigest()


def role_required(*roles):
    """Dekorator do kontroli ról (Administrator, Trener, Uzytkownik)."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if session.get("rola") not in roles:
                flash("Brak uprawnień do tego zasobu.", "danger")
                return redirect(url_for("index"))
            return f(*args, **kwargs)
        return wrapper
    return decorator


def analiza_skutecznosci(zawodnicy):
    """
    Proste drzewo decyzyjne:
    - główne kryterium: liczba goli (waga 3)
    - dodatkowe kryterium: asysty (waga 1, tu 0 – brak tabeli Asysta w ERD)
    """
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


@app.route("/")
def index():
    """
    Widok główny:
    - publiczny (Gość też widzi)
    - lider rozgrywek, najlepszy zawodnik, tabela meczów.
    """
    conn = get_db_conn()
    data = {"team": None, "player": None, "season": None, "matches": []}

    if not conn:
        flash("Brak połączenia z bazą danych.", "danger")
        return render_template("index.html", data=data)

    try:
        cursor = conn.cursor()

        # Najlepszy zawodnik (drzewo decyzyjne)
        cursor.execute("""
            SELECT 
                z.Imie,
                z.Nazwisko,
                COUNT(g.GolID) AS Gole,
                0 AS Asysty
            FROM Zawodnik z
            LEFT JOIN Gol g ON g.ZawodnikID = z.ZawodnikID
            GROUP BY z.Imie, z.Nazwisko
        """)
        data["player"] = analiza_skutecznosci(cursor.fetchall())

        # Lider tabeli (na podstawie pola Punkty)
        cursor.execute("""
            SELECT TOP 1 Nazwa, Punkty 
            FROM Druzyna 
            ORDER BY Punkty DESC
        """)
        data["team"] = cursor.fetchone()

        # Status sezonu
        cursor.execute("""
            SELECT TOP 1 NazwaSezonu, Status 
            FROM TerminarzRozgrywek 
            ORDER BY DataRozpoczecia DESC
        """)
        data["season"] = cursor.fetchone()

        # Wszystkie mecze
        cursor.execute("""
            SELECT 
                m.DataMeczu,
                d1.Nazwa AS Gospodarz,
                d2.Nazwa AS Gosc,
                m.WynikGospodarz,
                m.WynikGosc
            FROM Mecz m
            JOIN Druzyna d1 ON m.DruzynaGospodarzID = d1.DruzynaID
            JOIN Druzyna d2 ON m.DruzynaGoscID = d2.DruzynaID
            ORDER BY m.DataMeczu DESC
        """)
        data["matches"] = cursor.fetchall()
    finally:
        conn.close()

    return render_template("index.html", data=data)


@app.route("/login", methods=["GET", "POST"])
def login():
    """
    Logowanie użytkownika:
    - po sukcesie przekierowanie na index
    - hasło porównywane po SHA-256
    """
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
            cursor.execute("""
                SELECT UzytkownikID, Rola 
                FROM Uzytkownik 
                WHERE Login = ? AND HasloHash = ?
            """, (l_val, hashed))
            user = cursor.fetchone()
        finally:
            conn.close()

        if user:
            session.update({
                "user_id": user[0],
                "user_login": l_val,
                "rola": user[1]
            })
            flash("Zalogowano pomyślnie!", "success")
            return redirect(url_for("index"))
        else:
            flash("Błędny login lub hasło!", "danger")

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """
    Rejestracja nowego konta:
    - po sukcesie przekierowanie na /login
    - hasło zapisywane jako SHA-256
    """
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
                cursor.execute("""
                    INSERT INTO Uzytkownik (Login, HasloHash, Rola) 
                    VALUES (?, ?, 'Uzytkownik')
                """, (l_val, hashed))
                conn.commit()
                flash("Konto utworzone! Możesz się zalogować.", "success")
                return redirect(url_for("login"))
        finally:
            conn.close()

    return render_template("register.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Wylogowano.", "info")
    return redirect(url_for("login"))


# ---------- WIDOKI UŻYTKOWNIKA ----------

@app.route("/druzyny")
def druzyny_list():
    conn = get_db_conn()
    teams = []
    if not conn:
        flash("Brak połączenia z bazą danych.", "danger")
        return render_template("druzyny.html", teams=teams)

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DruzynaID, Nazwa, Miasto, Punkty FROM Druzyna ORDER BY Punkty DESC")
        teams = cursor.fetchall()
    finally:
        conn.close()

    return render_template("druzyny.html", teams=teams)


@app.route("/druzyna/<int:team_id>")
def druzyna_detail(team_id):
    conn = get_db_conn()
    team = None
    players = []
    matches = []

    if not conn:
        flash("Brak połączenia z bazą danych.", "danger")
        return render_template("druzyna.html", team=team, players=players, matches=matches)

    try:
        cursor = conn.cursor()

        cursor.execute("SELECT DruzynaID, Nazwa, Miasto, Punkty FROM Druzyna WHERE DruzynaID = ?", (team_id,))
        team = cursor.fetchone()

        cursor.execute("""
            SELECT ZawodnikID, Imie, Nazwisko, Pozycja
            FROM Zawodnik
            WHERE DruzynaID = ?
            ORDER BY Nazwisko, Imie
        """, (team_id,))
        players = cursor.fetchall()

        cursor.execute("""
            SELECT 
                m.DataMeczu,
                d1.Nazwa AS Gospodarz,
                d2.Nazwa AS Gosc,
                m.WynikGospodarz,
                m.WynikGosc
            FROM Mecz m
            JOIN Druzyna d1 ON m.DruzynaGospodarzID = d1.DruzynaID
            JOIN Druzyna d2 ON m.DruzynaGoscID = d2.DruzynaID
            WHERE m.DruzynaGospodarzID = ? OR m.DruzynaGoscID = ?
            ORDER BY m.DataMeczu DESC
        """, (team_id, team_id))
        matches = cursor.fetchall()
    finally:
        conn.close()

    return render_template("druzyna.html", team=team, players=players, matches=matches)


@app.route("/zawodnicy")
def zawodnicy_list():
    conn = get_db_conn()
    players = []
    if not conn:
        flash("Brak połączenia z bazą danych.", "danger")
        return render_template("zawodnicy.html", players=players)

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT z.ZawodnikID, z.Imie, z.Nazwisko, z.Pozycja, d.Nazwa
            FROM Zawodnik z
            JOIN Druzyna d ON z.DruzynaID = d.DruzynaID
            ORDER BY d.Nazwa, z.Nazwisko, z.Imie
        """)
        players = cursor.fetchall()
    finally:
        conn.close()

    return render_template("zawodnicy.html", players=players)


@app.route("/zawodnik/<int:player_id>")
def zawodnik_detail(player_id):
    conn = get_db_conn()
    player = None
    stats = {"gole": 0}
    if not conn:
        flash("Brak połączenia z bazą danych.", "danger")
        return render_template("zawodnik.html", player=player, stats=stats)

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT z.ZawodnikID, z.Imie, z.Nazwisko, z.Pozycja, d.Nazwa
            FROM Zawodnik z
            JOIN Druzyna d ON z.DruzynaID = d.DruzynaID
            WHERE z.ZawodnikID = ?
        """, (player_id,))
        player = cursor.fetchone()

        cursor.execute("SELECT COUNT(*) FROM Gol WHERE ZawodnikID = ?", (player_id,))
        stats["gole"] = cursor.fetchone()[0]
    finally:
        conn.close()

    return render_template("zawodnik.html", player=player, stats=stats)


@app.route("/mecze")
def mecze_list():
    conn = get_db_conn()
    matches = []
    if not conn:
        flash("Brak połączenia z bazą danych.", "danger")
        return render_template("mecze.html", matches=matches)

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                m.MeczID,
                m.DataMeczu,
                d1.Nazwa AS Gospodarz,
                d2.Nazwa AS Gosc,
                m.WynikGospodarz,
                m.WynikGosc
            FROM Mecz m
            JOIN Druzyna d1 ON m.DruzynaGospodarzID = d1.DruzynaID
            JOIN Druzyna d2 ON m.DruzynaGoscID = d2.DruzynaID
            ORDER BY m.DataMeczu DESC
        """)
        matches = cursor.fetchall()
    finally:
        conn.close()

    return render_template("mecze.html", matches=matches)


# ---------- PANEL TRENERA ----------

@app.route("/trener")
@role_required("Trener", "Administrator")
def trener_select():
    conn = get_db_conn()
    teams = []
    if not conn:
        flash("Brak połączenia z bazą danych.", "danger")
        return render_template("trener_select.html", teams=teams)

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DruzynaID, Nazwa FROM Druzyna ORDER BY Nazwa")
        teams = cursor.fetchall()
    finally:
        conn.close()

    return render_template("trener_select.html", teams=teams)


@app.route("/trener/<int:team_id>")
@role_required("Trener", "Administrator")
def trener_view(team_id):
    """
    Widok trenera:
    - najskuteczniejszy zawodnik przeciwko wskazanej drużynie (RB8, PU3).
    """
    conn = get_db_conn()
    if not conn:
        flash("Brak połączenia z bazą danych.", "danger")
        return render_template("trener.html", team=None, player=None)

    team = None
    player = None

    try:
        cursor = conn.cursor()

        cursor.execute("SELECT Nazwa FROM Druzyna WHERE DruzynaID = ?", (team_id,))
        team = cursor.fetchone()

        cursor.execute("""
            SELECT TOP 1 
                z.Imie,
                z.Nazwisko,
                COUNT(g.GolID) AS Gole
            FROM Gol g
            JOIN Mecz m ON g.MeczID = m.MeczID
            JOIN Zawodnik z ON g.ZawodnikID = z.ZawodnikID
            WHERE 
                (m.DruzynaGospodarzID = ? AND z.DruzynaID = m.DruzynaGoscID)
                OR
                (m.DruzynaGoscID = ? AND z.DruzynaID = m.DruzynaGospodarzID)
            GROUP BY z.Imie, z.Nazwisko
            ORDER BY Gole DESC
        """, (team_id, team_id))
        player = cursor.fetchone()
    finally:
        conn.close()

    return render_template("trener.html", team=team, player=player)

@app.route("/trener/historia/<int:team_id>")
@role_required("Trener", "Administrator")
def trener_historia(team_id):
    conn = get_db_conn()
    team = None
    mecze = []
    if not conn:
        flash("Brak połączenia z bazą danych.", "danger")
        return render_template("trener_historia.html", team=team, mecze=mecze)

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT Nazwa FROM Druzyna WHERE DruzynaID = ?", (team_id,))
        team = cursor.fetchone()

        cursor.execute("""
            SELECT 
                m.DataMeczu,
                d1.Nazwa AS Gospodarz,
                d2.Nazwa AS Gosc,
                m.WynikGospodarz,
                m.WynikGosc
            FROM Mecz m
            JOIN Druzyna d1 ON m.DruzynaGospodarzID = d1.DruzynaID
            JOIN Druzyna d2 ON m.DruzynaGoscID = d2.DruzynaID
            WHERE m.DruzynaGospodarzID = ? OR m.DruzynaGoscID = ?
            ORDER BY m.DataMeczu DESC
        """, (team_id, team_id))
        mecze = cursor.fetchall()
    finally:
        conn.close()

    return render_template("trener_historia.html", team=team, mecze=mecze)



# ---------- PANEL ADMINA: ROLE ----------

@app.route("/admin")
@role_required("Administrator")
def admin_panel():
    """
    Panel administratora:
    - zarządzanie rolami użytkowników
    """
    conn = get_db_conn()
    if not conn:
        flash("Brak połączenia z bazą danych.", "danger")
        return redirect(url_for("index"))

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
    """
    Zmiana roli użytkownika (Administrator / Trener / Uzytkownik).
    """
    conn = get_db_conn()
    if not conn:
        flash("Brak połączenia z bazą danych.", "danger")
        return redirect(url_for("admin_panel"))

    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE Uzytkownik 
            SET Rola = ? 
            WHERE UzytkownikID = ?
        """, (role, uid))
        conn.commit()
        flash("Zaktualizowano rolę!", "info")
    finally:
        conn.close()

    return redirect(url_for("admin_panel"))


# ---------- PANEL ADMINA: DRUŻYNY ----------

@app.route("/admin/druzyny", methods=["GET", "POST"])
@role_required("Administrator")
def admin_druzyny():
    conn = get_db_conn()
    if not conn:
        flash("Brak połączenia z bazą danych.", "danger")
        return redirect(url_for("index"))

    if request.method == "POST":
        nazwa = request.form.get("nazwa")
        miasto = request.form.get("miasto")
        punkty = request.form.get("punkty") or 0

        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO Druzyna (Nazwa, Miasto, Punkty)
                VALUES (?, ?, ?)
            """, (nazwa, miasto, int(punkty)))
            conn.commit()
            flash("Dodano drużynę.", "success")
        except Exception as e:
            flash(f"Błąd przy dodawaniu drużyny: {e}", "danger")

    teams = []
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT DruzynaID, Nazwa, Miasto, Punkty FROM Druzyna ORDER BY DruzynaID")
        teams = cursor.fetchall()
    finally:
        conn.close()

    return render_template("admin_druzyny.html", teams=teams)


@app.route("/admin/druzyna/<int:team_id>/delete")
@role_required("Administrator")
def admin_druzyna_delete(team_id):
    conn = get_db_conn()
    if not conn:
        flash("Brak połączenia z bazą danych.", "danger")
        return redirect(url_for("admin_druzyny"))

    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM Druzyna WHERE DruzynaID = ?", (team_id,))
        conn.commit()
        flash("Usunięto drużynę (upewnij się, że nie ma powiązanych meczów/zawodników).", "info")
    finally:
        conn.close()

    return redirect(url_for("admin_druzyny"))


# ---------- PANEL ADMINA: ZAWODNICY ----------

@app.route("/admin/zawodnicy", methods=["GET", "POST"])
@role_required("Administrator")
def admin_zawodnicy():
    conn = get_db_conn()
    if not conn:
        flash("Brak połączenia z bazą danych.", "danger")
        return redirect(url_for("index"))

    if request.method == "POST":
        imie = request.form.get("imie")
        nazwisko = request.form.get("nazwisko")
        pozycja = request.form.get("pozycja")
        druzyna_id = request.form.get("druzyna_id")

        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO Zawodnik (Imie, Nazwisko, Pozycja, DruzynaID)
                VALUES (?, ?, ?, ?)
            """, (imie, nazwisko, pozycja, int(druzyna_id)))
            conn.commit()
            flash("Dodano zawodnika.", "success")
        except Exception as e:
            flash(f"Błąd przy dodawaniu zawodnika: {e}", "danger")

    players = []
    teams = []
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT z.ZawodnikID, z.Imie, z.Nazwisko, z.Pozycja, d.Nazwa
            FROM Zawodnik z
            JOIN Druzyna d ON z.DruzynaID = d.DruzynaID
            ORDER BY d.Nazwa, z.Nazwisko
        """)
        players = cursor.fetchall()

        cursor.execute("SELECT DruzynaID, Nazwa FROM Druzyna ORDER BY Nazwa")
        teams = cursor.fetchall()
    finally:
        conn.close()

    return render_template("admin_zawodnicy.html", players=players, teams=teams)


@app.route("/admin/zawodnik/<int:player_id>/delete")
@role_required("Administrator")
def admin_zawodnik_delete(player_id):
    conn = get_db_conn()
    if not conn:
        flash("Brak połączenia z bazą danych.", "danger")
        return redirect(url_for("admin_zawodnicy"))

    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM Gol WHERE ZawodnikID = ?", (player_id,))
        cursor.execute("DELETE FROM Zawodnik WHERE ZawodnikID = ?", (player_id,))
        conn.commit()
        flash("Usunięto zawodnika (i jego gole).", "info")
    finally:
        conn.close()

    return redirect(url_for("admin_zawodnicy"))

def aktualizuj_punkty_po_meczu(cursor, gosp_id, gosc_id, wynik_g, wynik_gosc):
    """
    RB1: 3 pkt za zwycięstwo, 1 za remis, 0 za porażkę.
    Aktualizuje pole Punkty w tabeli Druzyna.
    """
    if wynik_g is None or wynik_gosc is None:
        return  # mecz bez wyniku – nie naliczamy

    gosp = int(wynik_g)
    gosc = int(wynik_gosc)

    if gosp > gosc:
        # gospodarz wygrywa
        cursor.execute("UPDATE Druzyna SET Punkty = Punkty + 3 WHERE DruzynaID = ?", (gosp_id,))
    elif gosc > gosp:
        # gość wygrywa
        cursor.execute("UPDATE Druzyna SET Punkty = Punkty + 3 WHERE DruzynaID = ?", (gosc_id,))
    else:
        # remis
        cursor.execute("UPDATE Druzyna SET Punkty = Punkty + 1 WHERE DruzynaID = ?", (gosp_id,))
        cursor.execute("UPDATE Druzyna SET Punkty = Punkty + 1 WHERE DruzynaID = ?", (gosc_id,))

# ---------- PANEL ADMINA: MECZE ----------

@app.route("/admin/mecze", methods=["GET", "POST"])
@role_required("Administrator")
def admin_mecze():
    conn = get_db_conn()
    if not conn:
        flash("Brak połączenia z bazą danych.", "danger")
        return redirect(url_for("index"))

    if request.method == "POST":
        gosp = request.form.get("gospodarz_id")
        gosc = request.form.get("gosc_id")
        data = request.form.get("data")
        wynik_g = request.form.get("wynik_g") or None
        wynik_gosc = request.form.get("wynik_gosc") or None
        terminarz_id = request.form.get("terminarz_id") or 1

        # RB2 - drużyny muszą być różne
        if int(gosp) == int(gosc):
            flash("Drużyna gospodarzy i gości muszą być różne (RB2).", "danger")
            return redirect(url_for("admin_mecze"))

        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO Mecz (DruzynaGospodarzID, DruzynaGoscID, WynikGospodarz, WynikGosc, DataMeczu, StatusMeczu, TerminarzID)
                VALUES (?, ?, ?, ?, ?, 'zakończony', ?)
            """, (int(gosp), int(gosc),
                  int(wynik_g) if wynik_g is not None else None,
                  int(wynik_gosc) if wynik_gosc is not None else None,
                  data,
                  int(terminarz_id)))
            
            mecz_id = cursor.execute("SELECT SCOPE_IDENTITY()").fetchone()[0]
            aktualizuj_punkty_po_meczu(
                cursor,
                int(gosp),
                int(gosc),
                int(wynik_g) if wynik_g is not None else None,
                int(wynik_gosc) if wynik_gosc is not None else None
            )
            conn.commit()
            flash("Dodano mecz i zaktualizowano punkty.", "success")
        except Exception as e:
            flash(f"Błąd przy dodawaniu meczu: {e}", "danger")

    matches = []
    teams = []
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                m.MeczID,
                m.DataMeczu,
                d1.Nazwa AS Gospodarz,
                d2.Nazwa AS Gosc,
                m.WynikGospodarz,
                m.WynikGosc
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


@app.route("/mecz/<int:mecz_id>")
def mecz_detail(mecz_id):
    conn = get_db_conn()
    mecz = None
    gole = []
    if not conn:
        flash("Brak połączenia z bazą danych.", "danger")
        return render_template("mecz.html", mecz=mecz, gole=gole)

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                m.MeczID,
                m.DataMeczu,
                d1.Nazwa AS Gospodarz,
                d2.Nazwa AS Gosc,
                m.WynikGospodarz,
                m.WynikGosc
            FROM Mecz m
            JOIN Druzyna d1 ON m.DruzynaGospodarzID = d1.DruzynaID
            JOIN Druzyna d2 ON m.DruzynaGoscID = d2.DruzynaID
            WHERE m.MeczID = ?
        """, (mecz_id,))
        mecz = cursor.fetchone()

        cursor.execute("""
            SELECT 
                g.Minuta,
                g.Typ,
                z.Imie,
                z.Nazwisko
            FROM Gol g
            JOIN Zawodnik z ON g.ZawodnikID = z.ZawodnikID
            WHERE g.MeczID = ?
            ORDER BY g.Minuta
        """, (mecz_id,))
        gole = cursor.fetchall()
    finally:
        conn.close()

    return render_template("mecz.html", mecz=mecz, gole=gole)


@app.route("/admin/mecz/<int:mecz_id>/delete")
@role_required("Administrator")
def admin_mecz_delete(mecz_id):
    conn = get_db_conn()
    if not conn:
        flash("Brak połączenia z bazą danych.", "danger")
        return redirect(url_for("admin_mecze"))

    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM Gol WHERE MeczID = ?", (mecz_id,))
        cursor.execute("DELETE FROM Mecz WHERE MeczID = ?", (mecz_id,))
        conn.commit()
        flash("Usunięto mecz (i jego gole).", "info")
    finally:
        conn.close()

    return redirect(url_for("admin_mecze"))

@app.route("/admin/raport_spojnosc")
@role_required("Administrator")
def admin_raport_spojnosc():
    """
    RB5: raport spójności – suma goli z tabeli Gol vs wynik meczu.
    """
    conn = get_db_conn()
    if not conn:
        flash("Brak połączenia z bazą danych.", "danger")
        return redirect(url_for("admin_panel"))

    raport = []
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                m.MeczID,
                m.DataMeczu,
                d1.Nazwa AS Gospodarz,
                d2.Nazwa AS Gosc,
                m.WynikGospodarz,
                m.WynikGosc,
                ISNULL((
                    SELECT COUNT(*) 
                    FROM Gol g 
                    WHERE g.MeczID = m.MeczID
                ), 0) AS LiczbaGoli
            FROM Mecz m
            JOIN Druzyna d1 ON m.DruzynaGospodarzID = d1.DruzynaID
            JOIN Druzyna d2 ON m.DruzynaGoscID = d2.DruzynaID
            ORDER BY m.DataMeczu DESC
        """)
        for row in cursor.fetchall():
            mecz_id, data, gosp, gosc, wg, wgo, liczba_goli = row
            suma_wyniku = (wg or 0) + (wgo or 0)
            zgodny = (suma_wyniku == liczba_goli)
            raport.append((mecz_id, data, gosp, gosc, wg, wgo, liczba_goli, zgodny))
    finally:
        conn.close()

    return render_template("admin_raport_spojnosc.html", raport=raport)


# ---------- PANEL ADMINA: GOLE ----------

@app.route("/admin/gole", methods=["GET", "POST"])
@role_required("Administrator")
def admin_gole():
    conn = get_db_conn()
    if not conn:
        flash("Brak połączenia z bazą danych.", "danger")
        return redirect(url_for("index"))

    if request.method == "POST":
        mecz_id = request.form.get("mecz_id")
        zawodnik_id = request.form.get("zawodnik_id")
        minuta = request.form.get("minuta")
        typ = request.form.get("typ") or "normalny"

        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO Gol (MeczID, ZawodnikID, Minuta, Typ)
                VALUES (?, ?, ?, ?)
            """, (int(mecz_id), int(zawodnik_id), int(minuta), typ))
            conn.commit()
            flash("Dodano gola.", "success")
        except Exception as e:
            flash(f"Błąd przy dodawaniu gola: {e}", "danger")

    goals = []
    matches = []
    players = []
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                g.GolID,
                g.MeczID,
                m.DataMeczu,
                d1.Nazwa AS Gospodarz,
                d2.Nazwa AS Gosc,
                z.Imie,
                z.Nazwisko,
                g.Minuta,
                g.Typ
            FROM Gol g
            JOIN Mecz m ON g.MeczID = m.MeczID
            JOIN Druzyna d1 ON m.DruzynaGospodarzID = d1.DruzynaID
            JOIN Druzyna d2 ON m.DruzynaGoscID = d2.DruzynaID
            JOIN Zawodnik z ON g.ZawodnikID = z.ZawodnikID
            ORDER BY m.DataMeczu DESC, g.Minuta
        """)
        goals = cursor.fetchall()

        cursor.execute("""
            SELECT m.MeczID, m.DataMeczu, d1.Nazwa, d2.Nazwa
            FROM Mecz m
            JOIN Druzyna d1 ON m.DruzynaGospodarzID = d1.DruzynaID
            JOIN Druzyna d2 ON m.DruzynaGoscID = d2.DruzynaID
            ORDER BY m.DataMeczu DESC
        """)
        matches = cursor.fetchall()

        cursor.execute("""
            SELECT z.ZawodnikID, z.Imie, z.Nazwisko, d.Nazwa
            FROM Zawodnik z
            JOIN Druzyna d ON z.DruzynaID = d.DruzynaID
            ORDER BY d.Nazwa, z.Nazwisko
        """)
        players = cursor.fetchall()
    finally:
        conn.close()

    return render_template("admin_gole.html", goals=goals, matches=matches, players=players)


@app.route("/admin/gol/<int:gol_id>/delete")
@role_required("Administrator")
def admin_gol_delete(gol_id):
    conn = get_db_conn()
    if not conn:
        flash("Brak połączenia z bazą danych.", "danger")
        return redirect(url_for("admin_gole"))

    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM Gol WHERE GolID = ?", (gol_id,))
        conn.commit()
        flash("Usunięto gola.", "info")
    finally:
        conn.close()

    return redirect(url_for("admin_gole"))


@app.route("/strzelcy")
def strzelcy():
    conn = get_db_conn()
    rows = []
    if not conn:
        flash("Brak połączenia z bazą danych.", "danger")
        return render_template("strzelcy.html", rows=rows)

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                z.Imie,
                z.Nazwisko,
                d.Nazwa,
                COUNT(g.GolID) AS Gole
            FROM Zawodnik z
            JOIN Druzyna d ON z.DruzynaID = d.DruzynaID
            LEFT JOIN Gol g ON g.ZawodnikID = z.ZawodnikID
            GROUP BY z.Imie, z.Nazwisko, d.Nazwa
            ORDER BY Gole DESC
        """)
        rows = cursor.fetchall()
    finally:
        conn.close()

    return render_template("strzelcy.html", rows=rows)

@app.route("/tabela")
def tabela_ligowa():
    conn = get_db_conn()
    rows = []
    if not conn:
        flash("Brak połączenia z bazą danych.", "danger")
        return render_template("tabela.html", rows=rows)

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                d.DruzynaID,
                d.Nazwa,
                d.Miasto,
                d.Punkty
            FROM Druzyna d
            ORDER BY d.Punkty DESC, d.Nazwa
        """)
        rows = cursor.fetchall()
    finally:
        conn.close()

    return render_template("tabela.html", rows=rows)

@app.route("/terminarz")
def terminarz():
    conn = get_db_conn()
    sezon = None
    mecze = []
    if not conn:
        flash("Brak połączenia z bazą danych.", "danger")
        return render_template("terminarz.html", sezon=sezon, mecze=mecze)

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT TOP 1 TerminarzID, NazwaSezonu, DataRozpoczecia, DataZakonczenia, Status
            FROM TerminarzRozgrywek
            ORDER BY DataRozpoczecia DESC
        """)
        sezon = cursor.fetchone()

        cursor.execute("""
            SELECT 
                m.DataMeczu,
                d1.Nazwa,
                d2.Nazwa,
                m.WynikGospodarz,
                m.WynikGosc
            FROM Mecz m
            JOIN Druzyna d1 ON m.DruzynaGospodarzID = d1.DruzynaID
            JOIN Druzyna d2 ON m.DruzynaGoscID = d2.DruzynaID
            ORDER BY m.DataMeczu
        """)
        mecze = cursor.fetchall()
    finally:
        conn.close()

    return render_template("terminarz.html", sezon=sezon, mecze=mecze)



if __name__ == "__main__":
    app.run(debug=True)
