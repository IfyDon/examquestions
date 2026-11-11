import psycopg
import pytest
import secrets

from conftest import ADMIN, FILLER, READER, TEST_APP_USER
from main import norm_options


def ids_by(client, **params):
    return client.get("/api/questions", params={"limit": 50, **params}).json()


def test_exams_and_subjects_only_count_approved(client):
    exams = {e["name"]: e["n"] for e in client.get("/api/exams").json()}
    assert exams == {"JAMB": 3 + 1 + FILLER, "WAEC": 2}  # pending and rejected excluded
    jamb = next(e["id"] for e in client.get("/api/exams").json() if e["name"] == "JAMB")
    subs = {s["name"]: s["n"] for s in client.get("/api/subjects", params={"exam_id": jamb}).json()}
    assert subs == {"English Language": 1, "Mathematics": 2 + 1 + FILLER}


def test_years_sorted_desc_and_skip_null(client):
    exams = {e["name"]: e["id"] for e in client.get("/api/exams").json()}
    ys = client.get("/api/years", params={"exam_id": exams["JAMB"]}).json()
    assert ys == sorted(ys, reverse=True) and None not in ys  # the NULL-year question adds no entry
    # WAEC has an approved 2012 and 2008, and a rejected 2013 that must not appear
    assert client.get("/api/years", params={"exam_id": exams["WAEC"]}).json() == [2012, 2008]


def test_filters_pagination_and_order(client):
    all_ = ids_by(client)
    assert all_["total"] == 3 + 1 + FILLER + 2
    page1 = client.get("/api/questions", params={"limit": 10, "offset": 0}).json()
    page2 = client.get("/api/questions", params={"limit": 10, "offset": 10}).json()
    assert len(page1["items"]) == 10 and not set(i["id"] for i in page1["items"]) & set(i["id"] for i in page2["items"])
    years = [i["year"] for i in ids_by(client)["items"] if i["year"] is not None]
    assert years == sorted(years, reverse=True)
    assert ids_by(client)["items"][-1]["year"] is None  # NULL years last
    assert ids_by(client, year=1999)["total"] == 1


def test_unapproved_content_never_leaks(client):
    blob = client.get("/api/questions", params={"limit": 50}).text
    assert "PENDING-SHOULD-NOT-APPEAR" not in blob and "REJECTED-QUESTION" not in blob
    with psycopg.connect(ADMIN) as c:
        pending_id = c.execute("SELECT id FROM jamb_questions WHERE review_status='pending'").fetchone()[0]
    r = client.get(f"/api/questions/{pending_id}/answer")
    assert r.status_code == 404 and "SECRET-PENDING" not in r.text


def test_list_hides_answers_until_requested(client):
    item = ids_by(client, year=1999)["items"][0]
    assert "answer" not in item and "explanation" not in item
    a = client.get(f"/api/questions/{item['id']}/answer").json()
    assert a["answer"] == "C" and "frac" in a["explanation"]


def test_search_and_hostile_input(client):
    assert ids_by(client, q="photosynthesis")["total"] == 1
    assert ids_by(client, q="benevolent")["items"][0]["subject"] == "English Language"
    for evil in ["'; DROP TABLE exams; --", '"unbalanced', "a & | ! ( )", "\x00".replace("\x00", "")]:
        assert client.get("/api/questions", params={"q": evil}).status_code == 200
    assert len(client.get("/api/exams").json()) == 2  # still there


@pytest.mark.parametrize("params", [{"limit": 1000}, {"limit": 0}, {"offset": -1}, {"exam_id": "x"}, {"q": "a" * 101}])
def test_bad_params_are_rejected(client, params):
    assert client.get("/api/questions", params=params).status_code == 422


def test_options_normalised_from_every_stored_shape(client):
    assert norm_options([{"key": "a", "text": "x"}]) == [{"key": "A", "text": "x"}]
    assert norm_options([{"label": "b", "option_text": "y"}]) == [{"key": "B", "text": "y"}]
    assert norm_options(["p", "q"]) == [{"key": "A", "text": "p"}, {"key": "B", "text": "q"}]
    assert norm_options({"B": "2", "A": "1"}) == [{"key": "A", "text": "1"}, {"key": "B", "text": "2"}]
    assert norm_options(None) == [] and norm_options([None]) == [{"key": "A", "text": ""}]
    q = ids_by(client, year=2005)["items"][0]
    assert [o["key"] for o in q["options"]] == ["A", "B", "C"]  # seeded with label/option_text keys


def test_database_role_is_read_only_and_minimal():
    with psycopg.connect(READER) as c:
        assert c.execute("SHOW default_transaction_read_only").fetchone()[0] == "on"
        for sql in [
            "INSERT INTO exams(name) VALUES ('x')",
            "UPDATE exams SET name='x'",
            "DELETE FROM exams",
            "SELECT * FROM jamb_questions",
            "SELECT * FROM crawl_runs",
            "SELECT * FROM question_revisions",
        ]:
            with pytest.raises(psycopg.Error):
                c.execute(sql)
            c.rollback()
        assert c.execute("SELECT count(*) FROM public_questions").fetchone()[0] > 0


def test_app_connection_cannot_write_even_as_superuser(monkeypatch):
    import main
    from fastapi.testclient import TestClient

    monkeypatch.setenv("DATABASE_URL", ADMIN)  # simulate a misconfigured, privileged login
    with TestClient(main.app):
        with main.pool.connection() as c:
            with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
                c.execute("INSERT INTO exams(name) VALUES ('nope')")


def test_optional_login(client, monkeypatch):
    password = secrets.token_urlsafe(24)
    monkeypatch.setenv("APP_PASSWORD", password)
    monkeypatch.setenv("APP_USER", "teacher")
    assert client.get("/api/exams").status_code == 401
    assert client.get("/api/exams", auth=("teacher", "wrong")).status_code == 401
    assert client.get("/api/exams", auth=(TEST_APP_USER, password)).status_code == 401
    assert client.get("/api/exams", auth=("teacher", password)).status_code == 200
    assert client.get("/", auth=("teacher", password)).status_code == 200


def test_home_page_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "Past Questions" in r.text
