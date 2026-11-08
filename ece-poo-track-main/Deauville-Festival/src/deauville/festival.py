import re
import unicodedata
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from deauville.storage import JsonStorage, Storage

BASE_DIR = Path(__file__).resolve().parent


# --- EXCEPTIONS SUR MESURE (Étape 10) ---


class FestivalError(Exception):
    """Classe de base pour toutes les erreurs du festival."""

    pass


class NotFoundError(FestivalError):
    """Ressource introuvable (mappé en HTTP 404)."""

    pass


class ConflictError(FestivalError):
    """Conflit d'emploi du temps ou doublon (mappé en HTTP 409)."""

    pass


class InvalidValueError(FestivalError):
    """Règle métier non respectée ou valeur invalide (mappé en HTTP 422)."""

    pass


# --- UTILITAIRES ---


def get_data_filepath(filepath: str | Path | None = None) -> Path:
    """Retourne le chemin d'accès au fichier JSON de données du festival."""
    if filepath:
        return Path(filepath)
    if (BASE_DIR / "data" / "festival.json").exists():
        return BASE_DIR / "data" / "festival.json"
    if (BASE_DIR.parent / "data" / "festival.json").exists():
        return BASE_DIR.parent / "data" / "festival.json"
    if (BASE_DIR.parent.parent / "data" / "festival.json").exists():
        return BASE_DIR.parent.parent / "data" / "festival.json"
    return BASE_DIR / "data" / "festival.json"


def slugify(text: str) -> str:
    """Convertit un texte brut en slug normalisé (minuscules, sans accents)."""
    normalized = unicodedata.normalize("NFKD", str(text))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    clean = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower())
    return clean.strip("-")


# --- CLASSES DU DOMAINE ---


@dataclass
class Venue:
    """Représente une salle de spectacle du festival."""

    slug: str
    name: str
    capacity: int
    address: str


@dataclass
class Artist:
    """Représente un artiste ou intervenant."""

    slug: str
    name: str

    def __eq__(self, other) -> bool:
        if isinstance(other, Artist):
            return self.slug == other.slug
        if isinstance(other, str):
            return self.slug == slugify(other)
        return False


@dataclass
class Performance(ABC):
    """Classe abstraite de base pour tous les types de spectacles."""

    title: str
    venue_slug: str
    start_iso: str
    duration_minutes: int
    description: str = ""
    kind: str = ""

    @property
    def start(self) -> datetime:
        return datetime.fromisoformat(self.start_iso)

    @property
    def end(self) -> datetime:
        return self.start + timedelta(minutes=self.duration_minutes)

    @property
    def festival_day(self) -> date:
        return (self.start - timedelta(hours=6)).date()

    @property
    def id(self) -> str:
        return f"{self.venue_slug}-{self.start.strftime('%Y-%m-%d-%H%M')}"

    def __lt__(self, other) -> bool:
        if not isinstance(other, Performance):
            return NotImplemented
        return (self.start, self.venue_slug) < (other.start, other.venue_slug)

    def __str__(self) -> str:
        s_fmt = self.start.strftime("%H:%M")
        e_fmt = self.end.strftime("%H:%M")
        return (
            f"{s_fmt}-{e_fmt} | {self.venue_slug} | "
            f"{self.title} ({self.kind})"
        )

    def overlaps_with(self, start_dt: datetime, end_dt: datetime) -> bool:
        return max(self.start, start_dt) < min(self.end, end_dt)

    @abstractmethod
    def involves(self, artist_slug: str) -> bool:
        pass

    @abstractmethod
    def summary(self, artists_map: dict[str, Artist]) -> str:
        pass

    @abstractmethod
    def to_dict(
        self, venues_map: dict[str, Venue], artists_map: dict[str, Artist]
    ) -> dict:
        pass

    @abstractmethod
    def to_raw_dict(self) -> dict:
        pass

    def _base_dict(
        self, venues_map: dict[str, Venue], artists_map: dict[str, Artist]
    ) -> dict:
        venue_obj = venues_map.get(self.venue_slug)
        v_name = venue_obj.name if venue_obj else self.venue_slug
        cap = venue_obj.capacity if venue_obj else 0

        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "venue": self.venue_slug,
            "venue_name": v_name,
            "start": self.start_iso,
            "end": self.end.isoformat(),
            "duration_minutes": self.duration_minutes,
            "festival_day": self.festival_day.isoformat(),
            "description": self.description,
            "summary": self.summary(artists_map),
            "capacity": cap,
        }


@dataclass
class SoloShow(Performance):
    """Représentation d'un spectacle solo."""

    artist: str = ""
    min_age: int | None = None
    kind: str = "solo"

    def __post_init__(self):
        if self.min_age is not None and not (0 <= self.min_age <= 18):
            raise InvalidValueError("min_age must be between 0 and 18.")

    def involves(self, artist_slug: str) -> bool:
        return slugify(artist_slug) == slugify(self.artist)

    def summary(self, artists_map: dict[str, Artist]) -> str:
        a_obj = artists_map.get(slugify(self.artist))
        return a_obj.name if a_obj else self.artist

    def to_dict(
        self, venues_map: dict[str, Venue], artists_map: dict[str, Artist]
    ) -> dict:
        res = self._base_dict(venues_map, artists_map)
        s = slugify(self.artist)
        a_obj = artists_map.get(s)
        a_name = a_obj.name if a_obj else self.artist
        res["artist"] = s
        res["artists"] = [{"slug": s, "name": a_name}]
        if self.min_age is not None:
            res["min_age"] = self.min_age
        return res

    def to_raw_dict(self) -> dict:
        d = {
            "kind": "solo",
            "title": self.title,
            "venue": self.venue_slug,
            "start": self.start_iso,
            "duration_minutes": self.duration_minutes,
            "artist": slugify(self.artist),
            "description": self.description,
        }
        if self.min_age is not None:
            d["min_age"] = self.min_age
        return d


@dataclass
class Lineup(Performance):
    """Représentation d'un plateau d'humoristes avec hôte."""

    host: str = ""
    acts: list[str] = field(default_factory=list)
    kind: str = "lineup"

    def __post_init__(self):
        if len(self.acts) < 2:
            raise InvalidValueError("Lineup must have at least 2 acts.")
        host_slug = slugify(self.host)
        act_slugs = [slugify(a) for a in self.acts]
        if host_slug in act_slugs:
            raise InvalidValueError("Host cannot be one of the acts.")
        min_duration = 10 * len(self.acts) + 3 * (len(self.acts) - 1)
        if self.duration_minutes < min_duration:
            raise InvalidValueError(
                f"Lineup duration must be at least {min_duration} minutes."
            )

    def involves(self, artist_slug: str) -> bool:
        target = slugify(artist_slug)
        return target == slugify(self.host) or target in [
            slugify(a) for a in self.acts
        ]

    def summary(self, artists_map: dict[str, Artist]) -> str:
        h_obj = artists_map.get(slugify(self.host))
        h_name = h_obj.name if h_obj else self.host
        act_names = []
        for act in self.acts:
            a_obj = artists_map.get(slugify(act))
            act_names.append(a_obj.name if a_obj else act)
        return f"hosted by {h_name}, with {', '.join(act_names)}"

    def to_dict(
        self, venues_map: dict[str, Venue], artists_map: dict[str, Artist]
    ) -> dict:
        res = self._base_dict(venues_map, artists_map)
        res["host"] = slugify(self.host)
        res["acts"] = [slugify(a) for a in self.acts]

        art_list = []
        for raw_a in [self.host] + self.acts:
            s = slugify(raw_a)
            a_obj = artists_map.get(s)
            name = a_obj.name if a_obj else raw_a
            if not any(x["slug"] == s for x in art_list):
                art_list.append({"slug": s, "name": name})
        res["artists"] = art_list
        return res

    def to_raw_dict(self) -> dict:
        return {
            "kind": "lineup",
            "title": self.title,
            "venue": self.venue_slug,
            "start": self.start_iso,
            "duration_minutes": self.duration_minutes,
            "host": slugify(self.host),
            "acts": [slugify(a) for a in self.acts],
            "description": self.description,
        }


@dataclass
class Workshop(Performance):
    """Représentation d'un atelier participatif."""

    teacher: str = ""
    max_participants: int = 1
    participants: list[str] = field(default_factory=list)
    kind: str = "workshop"

    def __post_init__(self):
        if self.max_participants < 1:
            raise InvalidValueError("Workshop must have at least 1 place.")

    @property
    def places_left(self) -> int:
        return self.max_participants - len(self.participants)

    def involves(self, artist_slug: str) -> bool:
        return slugify(artist_slug) == slugify(self.teacher)

    def summary(self, artists_map: dict[str, Artist]) -> str:
        t_obj = artists_map.get(slugify(self.teacher))
        t_name = t_obj.name if t_obj else self.teacher
        taken = len(self.participants)
        return f"with {t_name}, {taken}/{self.max_participants} places taken"

    def to_dict(
        self, venues_map: dict[str, Venue], artists_map: dict[str, Artist]
    ) -> dict:
        res = self._base_dict(venues_map, artists_map)
        venue_obj = venues_map.get(self.venue_slug)
        if venue_obj:
            res["capacity"] = min(self.max_participants, venue_obj.capacity)

        t_slug = slugify(self.teacher)
        t_obj = artists_map.get(t_slug)
        t_name = t_obj.name if t_obj else self.teacher

        res["teacher"] = t_slug
        res["max_participants"] = self.max_participants
        res["participants"] = self.participants
        res["places_left"] = self.places_left
        res["artists"] = [{"slug": t_slug, "name": t_name}]
        return res

    def to_raw_dict(self) -> dict:
        return {
            "kind": "workshop",
            "title": self.title,
            "venue": self.venue_slug,
            "start": self.start_iso,
            "duration_minutes": self.duration_minutes,
            "teacher": slugify(self.teacher),
            "max_participants": self.max_participants,
            "participants": self.participants,
            "description": self.description,
        }


PERFORMANCE_CLASSES = {
    "solo": SoloShow,
    "lineup": Lineup,
    "workshop": Workshop,
}


# --- CLASSE FESTIVAL (LOGIQUE MÉTIER ET ENCAPSULATION) ---


class Festival:
    """Modèle domaine central du festival."""

    def __init__(
        self,
        name: str,
        first_day: str,
        last_day: str,
        storage: Storage | None = None,
    ):
        self.name = name
        self.first_day = datetime.strptime(first_day, "%Y-%m-%d").date()
        self.last_day = datetime.strptime(last_day, "%Y-%m-%d").date()
        self.storage = storage
        self._venues: dict[str, Venue] = {}
        self._artists: dict[str, Artist] = {}
        self._performances: list[Performance] = []

    @property
    def days(self) -> list[str]:
        cur = self.first_day
        res = []
        while cur <= self.last_day:
            res.append(cur.isoformat())
            cur += timedelta(days=1)
        return res

    @property
    def venues(self) -> dict[str, Venue]:
        return dict(self._venues)

    @property
    def artists(self) -> dict[str, Artist]:
        return dict(self._artists)

    @property
    def performances(self) -> list[Performance]:
        return list(self._performances)

    def save(self):
        if not self.storage:
            return
        data = {
            "name": self.name,
            "first_day": self.first_day.isoformat(),
            "last_day": self.last_day.isoformat(),
            "venues": [
                {"name": v.name, "capacity": v.capacity, "address": v.address}
                for v in self._venues.values()
            ],
            "artists": [{"name": a.name} for a in self._artists.values()],
            "performances": [p.to_raw_dict() for p in self._performances],
        }
        self.storage.save(data)

    def add_venue(self, venue: Venue):
        self._venues[venue.slug] = venue

    def add_artist(self, artist: Artist):
        if artist.slug in self._artists:
            raise ConflictError(f"Artist '{artist.name}' already exists.")
        self._artists[artist.slug] = artist
        self.save()

    def add_performance(self, perf: Performance):
        if perf.duration_minutes <= 0 or perf.duration_minutes > 360:
            raise InvalidValueError(
                f"Invalid duration {perf.duration_minutes}. "
                "Must be between 1 and 360 minutes."
            )

        if perf.venue_slug not in self._venues:
            raise NotFoundError(f"No venue '{perf.venue_slug}'.")

        if not (self.first_day <= perf.festival_day <= self.last_day):
            raise InvalidValueError(
                f"Date {perf.festival_day} is outside festival bounds "
                f"({self.first_day} to {self.last_day})."
            )

        involved_slugs = []
        if isinstance(perf, SoloShow):
            involved_slugs.append(slugify(perf.artist))
        elif isinstance(perf, Lineup):
            involved_slugs.append(slugify(perf.host))
            involved_slugs.extend([slugify(a) for a in perf.acts])
        elif isinstance(perf, Workshop):
            involved_slugs.append(slugify(perf.teacher))

        for slug in involved_slugs:
            if slug not in self._artists:
                raise NotFoundError(f"No artist '{slug}'.")

        for existing in self._performances:
            if existing.venue_slug == perf.venue_slug and existing.overlaps_with(
                perf.start, perf.end
            ):
                raise ConflictError(
                    f"Venue '{perf.venue_slug}' is already occupied during this time."
                )

        for slug in involved_slugs:
            for existing in self._performances:
                if existing.involves(slug) and existing.overlaps_with(
                    perf.start, perf.end
                ):
                    raise ConflictError(
                        f"Artist '{slug}' is already busy during this time."
                    )

        self._performances.append(perf)
        self._performances.sort()
        self.save()

    def move_performance(
        self,
        perf_id: str,
        new_venue_slug: str | None = None,
        new_start_iso: str | None = None,
    ):
        perf = None
        for p in self._performances:
            if p.id == perf_id:
                perf = p
                break

        if not perf:
            raise NotFoundError(f"Unknown performance '{perf_id}'.")

        target_venue = new_venue_slug or perf.venue_slug
        target_start_iso = new_start_iso or perf.start_iso

        if target_venue not in self._venues:
            raise NotFoundError(f"No venue '{target_venue}'.")

        target_start = datetime.fromisoformat(target_start_iso)
        target_end = target_start + timedelta(minutes=perf.duration_minutes)
        target_day = (target_start - timedelta(hours=6)).date()

        if not (self.first_day <= target_day <= self.last_day):
            raise InvalidValueError(
                f"Date {target_day} is outside festival bounds."
            )

        for existing in self._performances:
            if existing.id == perf_id:
                continue
            if existing.venue_slug == target_venue and existing.overlaps_with(
                target_start, target_end
            ):
                raise ConflictError(
                    f"Venue '{target_venue}' is already occupied."
                )

            involved_slugs = []
            if isinstance(perf, SoloShow):
                involved_slugs.append(slugify(perf.artist))
            elif isinstance(perf, Lineup):
                involved_slugs.append(slugify(perf.host))
                involved_slugs.extend([slugify(a) for a in perf.acts])
            elif isinstance(perf, Workshop):
                involved_slugs.append(slugify(perf.teacher))

            for slug in involved_slugs:
                if existing.involves(slug) and existing.overlaps_with(
                    target_start, target_end
                ):
                    raise ConflictError(
                        f"Artist '{slug}' is already busy during this time."
                    )

        perf.venue_slug = target_venue
        perf.start_iso = target_start_iso
        self._performances.sort()
        self.save()

    def cancel_performance(self, perf_id: str):
        initial_len = len(self._performances)
        self._performances = [p for p in self._performances if p.id != perf_id]
        if len(self._performances) == initial_len:
            raise NotFoundError(f"Unknown performance '{perf_id}'.")
        self.save()

    def register_participant(self, perf_id: str, participant_name: str):
        perf = None
        for p in self._performances:
            if p.id == perf_id:
                perf = p
                break

        if not perf:
            raise NotFoundError(f"Unknown performance '{perf_id}'.")

        if not isinstance(perf, Workshop):
            raise InvalidValueError(
                "Only workshops accept participant registrations."
            )

        if participant_name in perf.participants:
            raise ConflictError(
                f"Participant '{participant_name}' is already registered."
            )

        if perf.places_left <= 0:
            raise ConflictError("Workshop is already full.")

        perf.participants.append(participant_name)
        self.save()

    def programme_for_day(self, day: date | str) -> list[Performance]:
        if isinstance(day, str):
            day = datetime.strptime(day, "%Y-%m-%d").date()
        return [p for p in self._performances if p.festival_day == day]

    def artist_performances(self, artist_slug: str) -> list[Performance]:
        s = slugify(artist_slug)
        return [p for p in self._performances if p.involves(s)]

    def now(
        self, at_dt: datetime
    ) -> tuple[list[Performance], list[Performance]]:
        now_playing = [
            p for p in self._performances if p.start <= at_dt < p.end
        ]
        upcoming = [p for p in self._performances if p.start > at_dt]
        upcoming.sort()
        return now_playing, upcoming[:3]


# --- CHARGEMENT VIA STORAGE ---


def load_festival_instance(
    storage: Storage | None = None,
    filepath: str | Path | None = None,
) -> Festival:
    """Charge le festival en utilisant l'abstraction Storage."""
    if storage is None:
        target_path = get_data_filepath(filepath)
        storage = JsonStorage(target_path)

    data = storage.load()

    fest = Festival(
        name=data["name"],
        first_day=data["first_day"],
        last_day=data["last_day"],
        storage=storage,
    )

    for v in data["venues"]:
        s = slugify(v["name"])
        fest.add_venue(
            Venue(
                slug=s,
                name=v["name"],
                capacity=v["capacity"],
                address=v["address"],
            )
        )

    for a in data["artists"]:
        name = a["name"] if isinstance(a, dict) else a
        s = slugify(name)
        fest._artists[s] = Artist(slug=s, name=name)

    for p in data["performances"]:
        k = p["kind"]
        cls = PERFORMANCE_CLASSES.get(k)
        if not cls:
            raise InvalidValueError(f"Unknown performance kind '{k}'.")

        kwargs = {
            "title": p["title"],
            "venue_slug": p["venue"],
            "start_iso": p["start"],
            "duration_minutes": p["duration_minutes"],
            "description": p.get("description", ""),
        }

        if k == "solo":
            kwargs["artist"] = p.get("artist", "")
            kwargs["min_age"] = p.get("min_age")
        elif k == "lineup":
            kwargs["host"] = p.get("host", "")
            kwargs["acts"] = p.get("acts", [])
        elif k == "workshop":
            kwargs["teacher"] = p.get("teacher", "")
            kwargs["max_participants"] = p.get("max_participants", 1)
            kwargs["participants"] = p.get("participants", [])

        perf = cls(**kwargs)
        fest._performances.append(perf)

    fest._performances.sort()
    return fest
