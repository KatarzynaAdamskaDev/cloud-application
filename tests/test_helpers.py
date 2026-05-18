import app as liga_app
from conftest import FakeCursor, FakeRow


def test_hash_password_and_verify_password():
    password = "tajnehaslo123"
    hashed = liga_app.hash_password(password)

    assert hashed != password
    assert liga_app.verify_password(hashed, password) is True
    assert liga_app.verify_password(hashed, "zlehaslo") is False


def test_verify_password_supports_old_sha256():
    import hashlib

    password = "admin123"
    old_hash = hashlib.sha256(password.encode("utf-8")).hexdigest()

    assert liga_app.verify_password(old_hash, password) is True
    assert liga_app.verify_password(old_hash, "inne") is False


def test_generate_user_token_returns_string():
    token = liga_app.generate_user_token()

    assert isinstance(token, str)
    assert len(token) > 20


def test_parse_int_field_valid_value():
    value, error = liga_app.parse_int_field("10", "liczba", required=True, min_value=0)

    assert value == 10
    assert error is None


def test_parse_int_field_required_missing():
    value, error = liga_app.parse_int_field("", "liczba", required=True)

    assert value is None
    assert "wymagane" in error


def test_parse_int_field_not_number():
    value, error = liga_app.parse_int_field("abc", "liczba", required=True)

    assert value is None
    assert "musi być liczbą" in error


def test_parse_int_field_below_minimum():
    value, error = liga_app.parse_int_field("-1", "wynik", required=True, min_value=0)

    assert value is None
    assert "nie może być mniejsze" in error


def test_aktualizuj_punkty_po_meczu_home_win():
    cursor = FakeCursor()

    liga_app.aktualizuj_punkty_po_meczu(cursor, 1, 2, 3, 1)

    assert len(cursor.executed_updates) == 1
    assert cursor.executed_updates[0][1] == (1,)


def test_aktualizuj_punkty_po_meczu_away_win():
    cursor = FakeCursor()

    liga_app.aktualizuj_punkty_po_meczu(cursor, 1, 2, 0, 2)

    assert len(cursor.executed_updates) == 1
    assert cursor.executed_updates[0][1] == (2,)


def test_aktualizuj_punkty_po_meczu_draw():
    cursor = FakeCursor()

    liga_app.aktualizuj_punkty_po_meczu(cursor, 1, 2, 1, 1)

    assert len(cursor.executed_updates) == 2
    assert cursor.executed_updates[0][1] == (1,)
    assert cursor.executed_updates[1][1] == (2,)


def test_policz_tabele_z_meczow_with_tiebreakers():
    cursor = FakeCursor(
        fetchall_results=[
            [
                FakeRow(1, "Alpha", "Miasto A"),
                FakeRow(2, "Beta", "Miasto B"),
                FakeRow(3, "Gamma", "Miasto C"),
            ],
            [
                FakeRow(1, 2, 2, 0),
                FakeRow(3, 1, 1, 1),
                FakeRow(2, 3, 3, 0),
            ]
        ]
    )

    tabela = liga_app.policz_tabele_z_meczow(cursor)

    assert tabela[0]["nazwa"] == "Alpha"
    assert tabela[0]["punkty"] == 4
    assert tabela[0]["bilans"] == 2

    assert tabela[1]["nazwa"] == "Beta"
    assert tabela[1]["punkty"] == 3
    assert tabela[1]["bilans"] == 1

    assert tabela[2]["nazwa"] == "Gamma"
    assert tabela[2]["punkty"] == 1
    assert tabela[2]["bilans"] == -3


def test_validate_match_form_rejects_same_team():
    cursor = FakeCursor()

    data, error = liga_app.validate_match_form(
        gosp="1",
        gosc="1",
        data="2025-09-01",
        wynik_g="1",
        wynik_gosc="0",
        status_meczu="zakończony",
        terminarz_id="1",
        cursor=cursor
    )

    assert data is None
    assert "muszą być różne" in error


def test_validate_match_form_rejects_negative_score():
    cursor = FakeCursor()

    data, error = liga_app.validate_match_form(
        gosp="1",
        gosc="2",
        data="2025-09-01",
        wynik_g="-1",
        wynik_gosc="0",
        status_meczu="zakończony",
        terminarz_id="1",
        cursor=cursor
    )

    assert data is None
    assert "nie może być mniejsze" in error


def test_validate_match_form_requires_score_when_finished():
    cursor = FakeCursor()

    data, error = liga_app.validate_match_form(
        gosp="1",
        gosc="2",
        data="2025-09-01",
        wynik_g="",
        wynik_gosc="0",
        status_meczu="zakończony",
        terminarz_id="1",
        cursor=cursor
    )

    assert data is None
    assert "wymagane" in error


def test_validate_match_form_rejects_inactive_schedule():
    cursor = FakeCursor(fetchone_results=[FakeRow("zakończony")])

    data, error = liga_app.validate_match_form(
        gosp="1",
        gosc="2",
        data="2025-09-01",
        wynik_g="1",
        wynik_gosc="0",
        status_meczu="zakończony",
        terminarz_id="1",
        cursor=cursor
    )

    assert data is None
    assert "aktywnym terminarzu" in error


def test_validate_match_form_accepts_valid_finished_match():
    cursor = FakeCursor(fetchone_results=[FakeRow("aktywny")])

    data, error = liga_app.validate_match_form(
        gosp="1",
        gosc="2",
        data="2025-09-01",
        wynik_g="1",
        wynik_gosc="0",
        status_meczu="zakończony",
        terminarz_id="1",
        cursor=cursor
    )

    assert error is None
    assert data["gosp_id"] == 1
    assert data["gosc_id"] == 2
    assert data["wynik_g"] == 1
    assert data["wynik_gosc"] == 0
    assert data["status_meczu"] == "zakończony"
    assert data["terminarz_id"] == 1


def test_validate_match_form_accepts_planned_match_without_score():
    cursor = FakeCursor(fetchone_results=[FakeRow("aktywny")])

    data, error = liga_app.validate_match_form(
        gosp="1",
        gosc="2",
        data="2025-09-01",
        wynik_g="",
        wynik_gosc="",
        status_meczu="planowany",
        terminarz_id="1",
        cursor=cursor
    )

    assert error is None
    assert data["gosp_id"] == 1
    assert data["gosc_id"] == 2
    assert data["wynik_g"] is None
    assert data["wynik_gosc"] is None
    assert data["status_meczu"] == "planowany"


def test_validate_match_form_rejects_invalid_status():
    cursor = FakeCursor()

    data, error = liga_app.validate_match_form(
        gosp="1",
        gosc="2",
        data="2025-09-01",
        wynik_g="1",
        wynik_gosc="0",
        status_meczu="zly-status",
        terminarz_id="1",
        cursor=cursor
    )

    assert data is None
    assert "Niepoprawny status meczu" in error


def test_validate_goal_form_rejects_invalid_minute():
    cursor = FakeCursor()

    data, error = liga_app.validate_goal_form(
        mecz_id="1",
        zawodnik_id="1",
        minuta="130",
        typ="normalny",
        cursor=cursor
    )

    assert data is None
    assert "nie może być większe" in error


def test_validate_goal_form_rejects_missing_match():
    cursor = FakeCursor(fetchone_results=[None])

    data, error = liga_app.validate_goal_form(
        mecz_id="1",
        zawodnik_id="1",
        minuta="10",
        typ="normalny",
        cursor=cursor
    )

    assert data is None
    assert "mecz nie istnieje" in error


def test_validate_goal_form_rejects_missing_player():
    cursor = FakeCursor(
        fetchone_results=[
            FakeRow(1, 10, 20, 2, 1),
            None
        ]
    )

    data, error = liga_app.validate_goal_form(
        mecz_id="1",
        zawodnik_id="999",
        minuta="10",
        typ="normalny",
        cursor=cursor
    )

    assert data is None
    assert "zawodnik nie istnieje" in error


def test_validate_goal_form_rejects_player_from_other_team():
    cursor = FakeCursor(
        fetchone_results=[
            FakeRow(1, 10, 20, 2, 1),
            FakeRow(99, 30)
        ]
    )

    data, error = liga_app.validate_goal_form(
        mecz_id="1",
        zawodnik_id="99",
        minuta="10",
        typ="normalny",
        cursor=cursor
    )

    assert data is None
    assert "nie należy" in error


def test_validate_goal_form_rejects_goal_without_match_score():
    cursor = FakeCursor(
        fetchone_results=[
            FakeRow(1, 10, 20, None, None),
            FakeRow(5, 10)
        ]
    )

    data, error = liga_app.validate_goal_form(
        mecz_id="1",
        zawodnik_id="5",
        minuta="10",
        typ="normalny",
        cursor=cursor
    )

    assert data is None
    assert "bez zapisanego wyniku" in error


def test_validate_goal_form_rejects_goal_exceeding_score():
    cursor = FakeCursor(
        fetchone_results=[
            FakeRow(1, 10, 20, 1, 0),
            FakeRow(5, 10),
            FakeRow(1)
        ]
    )

    data, error = liga_app.validate_goal_form(
        mecz_id="1",
        zawodnik_id="5",
        minuta="10",
        typ="normalny",
        cursor=cursor
    )

    assert data is None
    assert "przekroczyłaby wynik" in error


def test_validate_goal_form_accepts_valid_goal():
    cursor = FakeCursor(
        fetchone_results=[
            FakeRow(1, 10, 20, 2, 1),
            FakeRow(5, 10),
            FakeRow(1)
        ]
    )

    data, error = liga_app.validate_goal_form(
        mecz_id="1",
        zawodnik_id="5",
        minuta="70",
        typ="normalny",
        cursor=cursor
    )

    assert error is None
    assert data["mecz_id"] == 1
    assert data["zawodnik_id"] == 5
    assert data["druzyna_id"] == 10
    assert data["minuta"] == 70
    assert data["typ"] == "normalny"


def test_validate_goal_form_sets_default_goal_type():
    cursor = FakeCursor(
        fetchone_results=[
            FakeRow(1, 10, 20, 2, 1),
            FakeRow(5, 10),
            FakeRow(0)
        ]
    )

    data, error = liga_app.validate_goal_form(
        mecz_id="1",
        zawodnik_id="5",
        minuta="15",
        typ="",
        cursor=cursor
    )

    assert error is None
    assert data["typ"] == "normalny"
