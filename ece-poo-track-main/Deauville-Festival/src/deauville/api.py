from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from deauville.festival import (
    PERFORMANCE_CLASSES,
    ConflictError,
    FestivalError,
    InvalidValueError,
    NotFoundError,
    load_festival_instance,
)
from deauville.storage import Storage

BASE_DIR = Path(__file__).resolve().parent


def create_app(storage: Storage | None = None) -> FastAPI:
    """Usine d'application FastAPI configurée avec un stockage donné."""
    app = FastAPI(title="Deauville Festival API")
    fest = load_festival_instance(storage=storage)

    # --- GESTIONNAIRES D'ERREURS HTTP (API.md) ---

    @app.exception_handler(NotFoundError)
    async def handle_not_found(request: Request, exc: NotFoundError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ConflictError)
    async def handle_conflict(request: Request, exc: ConflictError):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(InvalidValueError)
    async def handle_invalid_value(request: Request, exc: InvalidValueError):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(FestivalError)
    async def handle_festival_error(request: Request, exc: FestivalError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    # --- ROUTES DE L'API ---

    @app.get("/api/festival")
    def get_festival_info():
        return {
            "name": fest.name,
            "first_day": fest.first_day.isoformat(),
            "last_day": fest.last_day.isoformat(),
            "venues_count": len(fest.venues),
            "artists_count": len(fest.artists),
            "performances_count": len(fest.performances),
        }

    @app.get("/api/venues")
    def get_venues():
        return [
            {
                "slug": v.slug,
                "name": v.name,
                "capacity": v.capacity,
                "address": v.address,
            }
            for v in fest.venues.values()
        ]

    @app.get("/api/artists")
    def get_artists():
        return [{"slug": a.slug, "name": a.name} for a in fest.artists.values()]

    @app.get("/api/performances")
    def get_performances(
        venue: str | None = Query(None),
        day: str | None = Query(None),
        kind: str | None = Query(None),
        artist: str | None = Query(None),
    ):
        perfs = fest.performances
        if venue:
            perfs = [p for p in perfs if p.venue_slug == venue]
        if day:
            perfs = [p for p in perfs if p.festival_day.isoformat() == day]
        if kind:
            perfs = [p for p in perfs if p.kind == kind]
        if artist:
            perfs = [p for p in perfs if p.involves(artist)]

        return [p.to_dict(fest.venues, fest.artists) for p in perfs]

    @app.get("/api/performances/{perf_id}")
    def get_performance(perf_id: str):
        for p in fest.performances:
            if p.id == perf_id:
                return p.to_dict(fest.venues, fest.artists)
        raise NotFoundError(f"Performance '{perf_id}' introuvable.")

    @app.post("/api/performances", status_code=201)
    def create_performance(data: dict):
        kind = data.get("kind")
        cls = PERFORMANCE_CLASSES.get(kind)
        if not cls:
            raise InvalidValueError(f"Kind de spectacle inconnu '{kind}'.")

        kwargs = {
            "title": data.get("title", ""),
            "venue_slug": data.get("venue", ""),
            "start_iso": data.get("start", ""),
            "duration_minutes": data.get("duration_minutes", 0),
            "description": data.get("description", ""),
        }
        if kind == "solo":
            kwargs["artist"] = data.get("artist", "")
            kwargs["min_age"] = data.get("min_age")
        elif kind == "lineup":
            kwargs["host"] = data.get("host", "")
            kwargs["acts"] = data.get("acts", [])
        elif kind == "workshop":
            kwargs["teacher"] = data.get("teacher", "")
            kwargs["max_participants"] = data.get("max_participants", 1)
            kwargs["participants"] = data.get("participants", [])

        perf = cls(**kwargs)
        fest.add_performance(perf)
        return perf.to_dict(fest.venues, fest.artists)

    @app.put("/api/performances/{perf_id}")
    def update_performance(perf_id: str, data: dict):
        new_venue = data.get("venue")
        new_start = data.get("start")
        fest.move_performance(
            perf_id, new_venue_slug=new_venue, new_start_iso=new_start
        )

        target_venue = new_venue or perf_id.split("-")[0]
        target_start = new_start or "-".join(perf_id.split("-")[1:])
        for p in fest.performances:
            if p.venue_slug == target_venue and p.start_iso == target_start:
                return p.to_dict(fest.venues, fest.artists)

        for p in fest.performances:
            if p.id == perf_id:
                return p.to_dict(fest.venues, fest.artists)

        raise NotFoundError(f"Performance '{perf_id}' introuvable.")

    @app.delete("/api/performances/{perf_id}")
    def delete_performance(perf_id: str):
        fest.cancel_performance(perf_id)
        return {"status": "deleted", "id": perf_id}

    @app.post("/api/performances/{perf_id}/register")
    def register_participant(perf_id: str, data: dict):
        name = data.get("name")
        if not name:
            raise InvalidValueError("Nom du participant requis.")
        fest.register_participant(perf_id, name)
        for p in fest.performances:
            if p.id == perf_id:
                return p.to_dict(fest.venues, fest.artists)
        raise NotFoundError(f"Performance '{perf_id}' introuvable.")

    # Recherche dynamique du dossier web/public pour servir le site web et l'admin
    web_public = None
    for candidate in [
        BASE_DIR / "web" / "public",
        BASE_DIR.parent / "web" / "public",
        BASE_DIR.parent.parent / "web" / "public",
        BASE_DIR.parent.parent.parent / "web" / "public",
    ]:
        if candidate.exists():
            web_public = candidate
            break

    if web_public:
        app.mount("/", StaticFiles(directory=web_public, html=True), name="static")

    return app


app = create_app()
