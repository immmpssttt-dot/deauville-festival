
import pytest
from deauville import festival as fest
from deauville import storage


@pytest.fixture
def fresh_festival(tmp_path):
    test_json = tmp_path / "test_festival.json"
    # Utilisation du JsonStorage au lieu de filepath
    st = storage.JsonStorage(test_json)
    f = fest.Festival("Test Fest", "2027-06-10", "2027-06-13", storage=st)
    f.add_venue(fest.Venue("kiosque", "Le Kiosque", 100, "1 rue A"))
    f.add_venue(fest.Venue("casino", "Grand Casino", 650, "2 rue B"))
    f.add_venue(fest.Venue("cabane", "La Cabane", 12, "3 rue C"))
    f.add_artist(fest.Artist("max", "Max Pellerin"))
    f.add_artist(fest.Artist("elodie", "Elodie Marchal"))
    f.add_artist(fest.Artist("tom", "Tom Vasseur"))
    f.add_artist(fest.Artist("hugo", "Hugo Lemaire"))
    f.add_artist(fest.Artist("maya", "Maya Choukri"))
    f.add_artist(fest.Artist("ines", "Inès Moreau"))
    f.add_artist(fest.Artist("lea", "Léa Fontaine"))
    f.add_artist(fest.Artist("zoe", "Zoé Tanguy"))
    return f


# --- TESTS ÉTAPE 08 ---


def test_add_valid_performance(fresh_festival):
    p = fest.SoloShow(
        title="Show 1",
        venue_slug="kiosque",
        start_iso="2027-06-11T20:00",
        duration_minutes=60,
        artist="max",
    )
    fresh_festival.add_performance(p)
    assert len(fresh_festival.performances) == 1


def test_rule_invalid_duration(fresh_festival):
    p = fest.SoloShow(
        title="Bad Duration",
        venue_slug="kiosque",
        start_iso="2027-06-11T20:00",
        duration_minutes=0,
        artist="max",
    )
    with pytest.raises(fest.InvalidValueError, match="Invalid duration"):
        fresh_festival.add_performance(p)


def test_rule_unknown_venue(fresh_festival):
    p = fest.SoloShow(
        title="Unknown Venue",
        venue_slug="nowhere",
        start_iso="2027-06-11T20:00",
        duration_minutes=60,
        artist="max",
    )
    with pytest.raises(fest.NotFoundError, match="No venue"):
        fresh_festival.add_performance(p)


def test_rule_venue_occupied(fresh_festival):
    p1 = fest.SoloShow(
        title="Show 1",
        venue_slug="kiosque",
        start_iso="2027-06-11T20:00",
        duration_minutes=60,
        artist="max",
    )
    p2 = fest.SoloShow(
        title="Show 2",
        venue_slug="kiosque",
        start_iso="2027-06-11T20:30",
        duration_minutes=60,
        artist="elodie",
    )
    fresh_festival.add_performance(p1)
    with pytest.raises(fest.ConflictError, match="occupied"):
        fresh_festival.add_performance(p2)


def test_rule_artist_busy_in_other_venue(fresh_festival):
    p1 = fest.SoloShow(
        title="Show 1",
        venue_slug="kiosque",
        start_iso="2027-06-11T20:00",
        duration_minutes=60,
        artist="max",
    )
    p2 = fest.SoloShow(
        title="Show 2",
        venue_slug="casino",
        start_iso="2027-06-11T20:30",
        duration_minutes=60,
        artist="max",
    )
    fresh_festival.add_performance(p1)
    with pytest.raises(fest.ConflictError, match="busy"):
        fresh_festival.add_performance(p2)


def test_rule_date_outside_festival(fresh_festival):
    p = fest.SoloShow(
        title="Outside",
        venue_slug="kiosque",
        start_iso="2027-05-01T20:00",
        duration_minutes=60,
        artist="max",
    )
    with pytest.raises(fest.InvalidValueError, match="outside festival bounds"):
        fresh_festival.add_performance(p)


def test_show_at_0100_belongs_to_previous_day(fresh_festival):
    p = fest.SoloShow(
        title="Late Show",
        venue_slug="kiosque",
        start_iso="2027-06-12T01:00",
        duration_minutes=60,
        artist="max",
    )
    assert p.festival_day.isoformat() == "2027-06-11"


# --- TESTS ÉTAPE 09 ---


def test_abstract_performance_instantiation_raises_typeerror():
    with pytest.raises(TypeError):
        fest.Performance("Title", "kiosque", "2027-06-11T20:00", 60)


def test_solo_summary(fresh_festival):
    p = fest.SoloShow(
        title="Solo",
        venue_slug="casino",
        start_iso="2027-06-11T20:30",
        duration_minutes=60,
        artist="lea",
    )
    fresh_festival.add_performance(p)
    assert p.summary(fresh_festival.artists) == "Léa Fontaine"


def test_lineup_summary_and_duration_rule(fresh_festival):
    with pytest.raises(fest.InvalidValueError, match="at least 36 minutes"):
        fest.Lineup(
            title="Lineup",
            venue_slug="kiosque",
            start_iso="2027-06-12T01:00",
            duration_minutes=35,
            host="tom",
            acts=["hugo", "maya", "elodie"],
        )

    p = fest.Lineup(
        title="After Hours",
        venue_slug="kiosque",
        start_iso="2027-06-12T01:00",
        duration_minutes=36,
        host="tom",
        acts=["hugo", "maya", "elodie"],
    )
    fresh_festival.add_performance(p)
    assert (
        p.summary(fresh_festival.artists)
        == "hosted by Tom Vasseur, with Hugo Lemaire, Maya Choukri, Elodie Marchal"
    )


def test_workshop_summary_and_capacity_cap(fresh_festival):
    p = fest.Workshop(
        title="Atelier",
        venue_slug="casino",
        start_iso="2027-06-11T10:30",
        duration_minutes=90,
        teacher="ines",
        max_participants=999,
        participants=["p1", "p2", "p3"],
    )
    fresh_festival.add_performance(p)
    d = p.to_dict(fresh_festival.venues, fresh_festival.artists)
    assert d["capacity"] == 650
    assert p.summary(fresh_festival.artists) == "with Inès Moreau, 3/999 places taken"


# --- TESTS ÉTAPE 10 ---


def test_custom_exception_hierarchy(fresh_festival):
    p = fest.SoloShow(
        title="Show Bad",
        venue_slug="nowhere",
        start_iso="2027-06-11T20:00",
        duration_minutes=60,
        artist="max",
    )
    with pytest.raises(fest.NotFoundError):
        fresh_festival.add_performance(p)


def test_failed_move_leaves_schedule_unchanged(fresh_festival):
    p1 = fest.SoloShow(
        title="Show 1",
        venue_slug="kiosque",
        start_iso="2027-06-11T20:00",
        duration_minutes=60,
        artist="max",
    )
    p2 = fest.SoloShow(
        title="Show 2",
        venue_slug="casino",
        start_iso="2027-06-11T20:00",
        duration_minutes=60,
        artist="elodie",
    )
    fresh_festival.add_performance(p1)
    fresh_festival.add_performance(p2)

    with pytest.raises(fest.ConflictError):
        fresh_festival.move_performance(
            p2.id, new_venue_slug="kiosque", new_start_iso="2027-06-11T20:00"
        )

    p2_after = next(p for p in fresh_festival.performances if p.id == p2.id)
    assert p2_after.venue_slug == "casino"


def test_duplicate_artist_raises_conflict(fresh_festival):
    with pytest.raises(fest.ConflictError, match="already exists"):
        fresh_festival.add_artist(fest.Artist("zoe", "Zoé Tanguy"))


def test_participant_registration_and_duplicate_refusal(fresh_festival):
    p = fest.Workshop(
        title="Stand-up Lab",
        venue_slug="kiosque",
        start_iso="2027-06-11T14:00",
        duration_minutes=60,
        teacher="ines",
        max_participants=2,
    )
    fresh_festival.add_performance(p)
    fresh_festival.register_participant(p.id, "Alice")

    with pytest.raises(fest.ConflictError, match="already registered"):
        fresh_festival.register_participant(p.id, "Alice")


def test_encapsulation_prevents_direct_mutation(fresh_festival):
    perfs = fresh_festival.performances
    perfs.clear()
    assert len(fresh_festival.performances) == len(fresh_festival._performances)
