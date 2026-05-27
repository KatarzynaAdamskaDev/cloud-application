import app as liga_app
from conftest import FakeCursor, FakeConnection, FakeRow


def test_api_najlepsza_druzyna(monkeypatch, client):
    cursor = FakeCursor(
        fetchall_results=[
            [FakeRow(1, "Orły", "Stargard"), FakeRow(2, "Pogoń", "Szczecin")],
            [FakeRow(1, 2, 3, 1)]
        ]
    )
    conn = FakeConnection(cursor)
    monkeypatch.setattr(liga_app, "get_db_conn", lambda: conn)

    response = client.get("/api/najlepsza-druzyna")
    assert response.status_code == 200

    data = response.get_json()
    assert data["nazwa"] == "Orły"
    assert data["punkty"] == 3


def test_api_najlepszy_zawodnik_requires_role(client):
    response = client.get("/api/najlepszy-zawodnik", follow_redirects=False)
    assert response.status_code in [302, 303]


def test_api_najskuteczniejszy_algorytm(monkeypatch, logged_trener):
    """Test zaawansowanego algorytmu analitycznego: Najskuteczniejszy gracz przeciwko danej drużynie."""
    cursor = FakeCursor(fetchone_results=[
        FakeRow(7, "Robert", "Lewandowski", "FC Barcelona", 4)
    ])
    conn = FakeConnection(cursor)
    monkeypatch.setattr(liga_app, "get_db_conn", lambda: conn)

    response = logged_trener.get("/api/najskuteczniejszy/1")
    
    assert response.status_code == 200
    data = response.get_json()
    assert data["imie"] == "Robert"
    assert data["gole"] == 4