import pytest
from deauville.api import create_app
from deauville.storage import JsonStorage
from fastapi.testclient import TestClient


@pytest.fixture
def api_client(tmp_path):
    test_json = tmp_path / "test_api_festival.json"
    initial_data = {
        "name": "Deauville Test Festival",
        "first_day": "2027-06-10",
        "last_day": "2027-06-13",
        "venues": [
            {"name": "Le Kiosque", "capacity": 100, "address": "1 rue A"},
            {"name": "Grand Casino", "capacity": 650, "address": "2 rue B"},
        ],
        "artists": [
            {"name": "Max Pellerin"},
            {"name": "Elodie Marchal"},
            {"name": "Tom Vasseur"},
        ],
        "performances": [
            {
                "kind": "solo",
                "title": "Solo Show",
                "venue": "le-kiosque",
                "start": "2027-06-11T20:00",
                "duration_minutes": 60,
                "artist": "max-pellerin",
                "description": "Un solo de test",
            },
            {
                "kind": "workshop",
                "title": "Atelier Standup",
                "venue": "le-kiosque",
                "start": "2027-06-11T14:00",
                "duration_minutes": 60,
                "teacher": "elodie-marchal",
                "max_participants": 1,
                "participants": [],
            },
        ],
    }
    st = JsonStorage(test_json)
    st.save(initial_data)

    app = create_app(storage=st)
    return TestClient(app)


def test_get_festival(api_client):
    res = api_client.get("/api/festival")
    assert res.status_code == 200
    data = res.json()
    assert data["name"] == "Deauville Test Festival"
    assert data["venues_count"] == 2


def test_get_venues_and_artists(api_client):
    r_venues = api_client.get("/api/venues")
    assert r_venues.status_code == 200
    assert len(r_venues.json()) == 2

    r_artists = api_client.get("/api/artists")
    assert r_artists.status_code == 200
    assert len(r_artists.json()) == 3


def test_get_performances_with_filters(api_client):
    res = api_client.get("/api/performances?venue=le-kiosque&kind=solo")
    assert res.status_code == 200
    perfs = res.json()
    assert len(perfs) == 1
    assert perfs[0]["title"] == "Solo Show"


def test_get_performance_detail_and_404(api_client):
    res = api_client.get("/api/performances/le-kiosque-2027-06-11-2000")
    assert res.status_code == 200
    assert res.json()["title"] == "Solo Show"

    res_404 = api_client.get("/api/performances/unknown-id")
    assert res_404.status_code == 404


def test_create_performance_201_and_validation_422(api_client):
    new_perf = {
        "kind": "solo",
        "title": "Nouveau Solo",
        "venue": "grand-casino",
        "start": "2027-06-11T21:00",
        "duration_minutes": 60,
        "artist": "tom-vasseur",
    }
    res = api_client.post("/api/performances", json=new_perf)
    assert res.status_code == 201
    assert res.json()["title"] == "Nouveau Solo"

    # Validation d'erreur 422 (durée invalide)
    bad_perf = dict(new_perf, duration_minutes=0)
    res_bad = api_client.post("/api/performances", json=bad_perf)
    assert res_bad.status_code == 422


def test_update_performance_and_conflict_409(api_client):
    # Déplacement vers un créneau valide
    update_data = {"venue": "grand-casino", "start": "2027-06-11T22:00"}
    res = api_client.put(
        "/api/performances/le-kiosque-2027-06-11-2000", json=update_data
    )
    assert res.status_code == 200
    assert res.json()["venue"] == "grand-casino"

    # Tentative de déplacement sur un créneau occupé -> 409 Conflict
    conflict_data = {"venue": "le-kiosque", "start": "2027-06-11T14:00"}
    res_conflict = api_client.put(
        "/api/performances/grand-casino-2027-06-11-2200", json=conflict_data
    )
    assert res_conflict.status_code == 409


def test_delete_performance_twice_gives_404(api_client):
    perf_id = "le-kiosque-2027-06-11-2000"
    res1 = api_client.delete(f"/api/performances/{perf_id}")
    assert res1.status_code == 200

    res2 = api_client.delete(f"/api/performances/{perf_id}")
    assert res2.status_code == 404


def test_workshop_full_gives_409(api_client):
    perf_id = "le-kiosque-2027-06-11-1400"
    # Première inscription OK
    r1 = api_client.post(
        f"/api/performances/{perf_id}/register", json={"name": "Alice"}
    )
    assert r1.status_code == 200

    # Deuxième inscription alors que max_participants = 1 -> 409 Conflict
    r2 = api_client.post(f"/api/performances/{perf_id}/register", json={"name": "Bob"})
    assert r2.status_code == 409
