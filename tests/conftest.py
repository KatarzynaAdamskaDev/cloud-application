import os
import sys
import types
import pytest

# Główny katalog projektu, czyli folder z app.py
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Mock pyodbc przed importem app.py.
# Dzięki temu testy nie wymagają unixODBC ani sterowników SQL Server na Macu.
fake_pyodbc = types.ModuleType("pyodbc")

def fake_connect(*args, **kwargs):
    raise RuntimeError("pyodbc.connect nie powinien być używany w testach jednostkowych")

fake_pyodbc.connect = fake_connect
sys.modules["pyodbc"] = fake_pyodbc

import app as liga_app


@pytest.fixture
def app():
    liga_app.app.config.update({
        "TESTING": True,
        "SECRET_KEY": "test-secret-key"
    })
    return liga_app.app


@pytest.fixture
def client(app):
    return app.test_client()


class FakeRow:
    """
    Prosty obiekt do testów, który działa jak tuple/lista przez indeksy.
    """
    def __init__(self, *values):
        self.values = values

    def __getitem__(self, index):
        return self.values[index]

    def __iter__(self):
        return iter(self.values)

    def __repr__(self):
        return f"FakeRow{self.values}"


class FakeCursor:
    """
    Mock kursora SQL.
    Pozwala testować funkcje bez połączenia z Azure SQL.
    """
    def __init__(self, fetchone_results=None, fetchall_results=None):
        self.queries = []
        self.params = []
        self.fetchone_results = fetchone_results or []
        self.fetchall_results = fetchall_results or []
        self.executed_updates = []

    def execute(self, query, params=None):
        self.queries.append(query)
        self.params.append(params)

        query_upper = query.strip().upper()
        if query_upper.startswith(("UPDATE", "INSERT", "DELETE")):
            self.executed_updates.append((query, params))

        return self

    def fetchone(self):
        if self.fetchone_results:
            return self.fetchone_results.pop(0)
        return None

    def fetchall(self):
        if self.fetchall_results:
            return self.fetchall_results.pop(0)
        return []


class FakeConnection:
    """
    Mock połączenia z bazą.
    """
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False
        self.closed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True

    def close(self):
        self.closed = True


@pytest.fixture
def logged_admin(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["user_login"] = "admin"
        sess["rola"] = "Administrator"
        sess["token"] = "test-token"
    return client


@pytest.fixture
def logged_trener(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 2
        sess["user_login"] = "trener"
        sess["rola"] = "Trener"
        sess["token"] = "test-token"
    return client


@pytest.fixture
def logged_user(client):
    with client.session_transaction() as sess:
        sess["user_id"] = 3
        sess["user_login"] = "user"
        sess["rola"] = "Uzytkownik"
        sess["token"] = "test-token"
    return client
