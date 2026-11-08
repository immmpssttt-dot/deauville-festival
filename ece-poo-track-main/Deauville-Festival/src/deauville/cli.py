import sys
from datetime import datetime
from pathlib import Path

from deauville import festival as fest
from deauville.storage import JsonStorage


def print_summary(f: fest.Festival):
    print(f.name)
    print()
    print(f"From {f.first_day} to {f.last_day}")
    print()
    print(
        f"{len(f.venues)} venues, "
        f"{len(f.artists)} artists, "
        f"{len(f.performances)} performances"
    )


def print_venues(f: fest.Festival):
    total_seats = 0
    for venue in f.venues.values():
        print(f"{venue.slug}: {venue.name}, {venue.capacity} seats")
        total_seats += venue.capacity

    print()
    print(f"Total: {total_seats} seats")


def print_programme(f: fest.Festival, day_str: str):
    performances = f.programme_for_day(day_str)
    target_day = datetime.strptime(day_str, "%Y-%m-%d").date()

    print(f"Programme for {target_day:%A %d %B}:")
    for p in performances:
        venue_name = f.venues[p.venue_slug].name
        print(f"{p.start:%H:%M}-{p.end:%H:%M} | {venue_name} | {p.title} ({p.kind})")


def print_artist(f: fest.Festival, artist_slug: str):
    if artist_slug not in f.artists:
        print(f"No artist '{artist_slug}'.")
        return

    art = f.artists[artist_slug]
    print(art.name)
    for p in f.artist_performances(artist_slug):
        venue = f.venues[p.venue_slug]
        print(f"{p.start:%a %d %H:%M}-{p.end:%H:%M} | {venue.name} | {p.title}")


def print_now(f: fest.Festival, moment_text: str):
    at = datetime.fromisoformat(moment_text)
    now_playing, upcoming = f.now(at)

    print(f"On stage at {at:%Y-%m-%d %H:%M}:")
    for p in now_playing:
        venue_name = f.venues[p.venue_slug].name
        print(f"- {p.title} at {venue_name}, until {p.end:%H:%M}")

    print("Up next:")
    for p in upcoming:
        venue_name = f.venues[p.venue_slug].name
        print(f"- {p.start:%H:%M}-{p.end:%H:%M} | {venue_name} | {p.title} ({p.kind})")


def main():
    args = sys.argv[1:]
    data_path = None

    # Gestion de l'option optionnelle --data
    if "--data" in args:
        idx = args.index("--data")
        if idx + 1 < len(args):
            data_path = Path(args[idx + 1])
            del args[idx : idx + 2]

    storage = JsonStorage(data_path) if data_path else None
    f = fest.load_festival_instance(storage=storage)

    if not args:
        print_summary(f)
        return

    cmd = args[0]

    if cmd == "serve":
        import uvicorn

        from deauville.api import create_app

        app_instance = create_app(storage=storage)
        uvicorn.run(app_instance, host="127.0.0.1", port=8000)
    elif cmd == "venues":
        print_venues(f)
    elif cmd == "programme" and len(args) > 1:
        print_programme(f, args[1])
    elif cmd == "artist" and len(args) > 1:
        print_artist(f, args[1])
    elif cmd == "now" and len(args) > 1:
        print_now(f, args[1])
    elif cmd == "summary":
        print_summary(f)
    else:
        print(
            "Usage: deauville [--data file.json] "
            "[serve|venues|programme YYYY-MM-DD|artist slug|now ISO]"
        )


if __name__ == "__main__":
    main()
