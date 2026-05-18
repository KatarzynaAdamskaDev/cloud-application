import app as liga_app
from conftest import FakeCursor, FakeConnection, FakeRow


def test_register_creates_user(monkeypatch, client):
    cursor = FakeCursor(fetchone_results=[None])
    conn = FakeConnection(cursor)

    monkeypatch.setattr(liga_app, "get_db_conn", lambda: conn)

    response = client.post("/register", data={
        "login": "nowy",
        "password": "haslo123"
    }, follow_redirects=False)

    assert response.status_code in [302, 303]
    assert conn.committed is True

    insert_queries = [q for q in cursor.queries if "INSERT INTO Uzytkownik" in q]
    assert len(insert_queries) == 1


def test_register_rejects_existing_login(monkeypatch, client):
    cursor = FakeCursor(fetchone_results=[FakeRow("admin")])
    conn = FakeConnection(cursor)

    monkeypatch.setattr(liga_app, "get_db_conn", lambda: conn)

    response = client.post("/register", data={
        "login": "admin",
        "password": "haslo123"
    }, follow_redirects=True)

    assert response.status_code == 200
    assert conn.committed is False


def test_login_success(monkeypatch, client):
    password = "admin123"
    hashed = liga_app.hash_password(password)

    cursor = FakeCursor(fetchone_results=[FakeRow(1, hashed, "Administrator")])
    conn = FakeConnection(cursor)

    monkeypatch.setattr(liga_app, "get_db_conn", lambda: conn)

    response = client.post("/login", data={
        "login": "admin",
        "password": password
    }, follow_redirects=False)

    assert response.status_code in [302, 303]
    assert conn.committed is True

    with client.session_transaction() as sess:
        assert sess["user_login"] == "admin"
        assert sess["rola"] == "Administrator"
        assert "token" in sess


def test_login_wrong_password(monkeypatch, client):
    password = "admin123"
    hashed = liga_app.hash_password(password)

    cursor = FakeCursor(fetchone_results=[FakeRow(1, hashed, "Administrator")])
    conn = FakeConnection(cursor)

    monkeypatch.setattr(liga_app, "get_db_conn", lambda: conn)

    response = client.post("/login", data={
        "login": "admin",
        "password": "zlehaslo"
    }, follow_redirects=True)

    assert response.status_code == 200
    assert conn.committed is False

    with client.session_transaction() as sess:
        assert "user_login" not in sess


def test_logout_clears_session(client):
    with client.session_transaction() as sess:
        sess["user_login"] = "admin"
        sess["rola"] = "Administrator"

    response = client.get("/logout", follow_redirects=False)

    assert response.status_code in [302, 303]

    with client.session_transaction() as sess:
        assert "user_login" not in sess
        assert "rola" not in sess
