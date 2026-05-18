import app as liga_app
from conftest import FakeCursor, FakeConnection, FakeRow


def test_strzelcy_requires_role(client):
    response = client.get("/strzelcy", follow_redirects=False)

    assert response.status_code in [302, 303]


def test_strzelcy_allowed_for_trener(monkeypatch, logged_trener):
    cursor = FakeCursor(fetchall_results=[
        [
            FakeRow("Jan", "Kowalski", "Orły", 3),
            FakeRow("Adam", "Nowak", "Pogoń", 2),
        ]
    ])
    conn = FakeConnection(cursor)

    monkeypatch.setattr(liga_app, "get_db_conn", lambda: conn)

    response = logged_trener.get("/strzelcy")

    assert response.status_code == 200


def test_admin_panel_requires_admin(client):
    response = client.get("/admin", follow_redirects=False)

    assert response.status_code in [302, 303]


def test_admin_panel_allowed_for_admin(monkeypatch, logged_admin):
    cursor = FakeCursor(fetchall_results=[
        [
            FakeRow(1, "admin", "Administrator"),
            FakeRow(2, "trener", "Trener"),
        ]
    ])
    conn = FakeConnection(cursor)

    monkeypatch.setattr(liga_app, "get_db_conn", lambda: conn)

    response = logged_admin.get("/admin")

    assert response.status_code == 200


def test_terminarz_public_route(monkeypatch, client):
    cursor = FakeCursor(
        fetchone_results=[
            FakeRow(1, "Sezon 2025/2026", "2025-09-01", "2026-06-30", "aktywny")
        ],
        fetchall_results=[
            [
                FakeRow("2025-09-01", "Orły", "Pogoń", 2, 1, "zakończony")
            ]
        ]
    )
    conn = FakeConnection(cursor)

    monkeypatch.setattr(liga_app, "get_db_conn", lambda: conn)

    response = client.get("/terminarz")

    assert response.status_code == 200


def test_admin_terminarze_get(monkeypatch, logged_admin):
    cursor = FakeCursor(fetchall_results=[
        [
            FakeRow(1, "Sezon 2025/2026", "2025-09-01", "2026-06-30", "aktywny", 0)
        ]
    ])
    conn = FakeConnection(cursor)

    monkeypatch.setattr(liga_app, "get_db_conn", lambda: conn)

    response = logged_admin.get("/admin/terminarze")

    assert response.status_code == 200


def test_admin_terminarze_post_creates_schedule(monkeypatch, logged_admin):
    cursor = FakeCursor(fetchall_results=[[]])
    conn = FakeConnection(cursor)

    monkeypatch.setattr(liga_app, "get_db_conn", lambda: conn)

    response = logged_admin.post("/admin/terminarze", data={
        "nazwa_sezonu": "Sezon testowy",
        "data_rozpoczecia": "2025-09-01",
        "data_zakonczenia": "2026-06-30",
        "status": "aktywny"
    }, follow_redirects=True)

    assert response.status_code == 200
    assert conn.committed is True

    insert_queries = [q for q in cursor.queries if "INSERT INTO TerminarzRozgrywek" in q]
    assert len(insert_queries) == 1


def test_admin_mecze_post_rejects_same_team(monkeypatch, logged_admin):
    cursor = FakeCursor(
        fetchall_results=[
            [],
            [FakeRow(1, "Orły"), FakeRow(2, "Pogoń")],
            [FakeRow(1, "Sezon", "aktywny")]
        ]
    )
    conn = FakeConnection(cursor)

    monkeypatch.setattr(liga_app, "get_db_conn", lambda: conn)

    response = logged_admin.post("/admin/mecze", data={
        "gospodarz_id": "1",
        "gosc_id": "1",
        "data": "2025-09-01",
        "wynik_g": "1",
        "wynik_gosc": "0",
        "status_meczu": "zakończony",
        "terminarz_id": "1"
    }, follow_redirects=False)

    assert response.status_code in [302, 303]


def test_admin_mecz_delete_recalculates_points(monkeypatch, logged_admin):
    cursor = FakeCursor(fetchall_results=[[]])
    conn = FakeConnection(cursor)

    monkeypatch.setattr(liga_app, "get_db_conn", lambda: conn)

    response = logged_admin.get("/admin/mecz/1/delete", follow_redirects=False)

    assert response.status_code in [302, 303]
    assert conn.committed is True

    delete_queries = [q for q in cursor.queries if "DELETE FROM Mecz" in q]
    update_queries = [q for q in cursor.queries if "UPDATE Druzyna SET Punkty = 0" in q]

    assert len(delete_queries) == 1
    assert len(update_queries) == 1
