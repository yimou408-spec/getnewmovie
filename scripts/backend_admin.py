"""Local database checks, safe backup and independently verified source mappings."""
import argparse
import json
import os
from pathlib import Path

from app.services.storage import Repository
from scripts.s0_contracts import ExternalMovieIdentity

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=Path(os.getenv("MOVIE_DB_PATH") or ROOT / "artifacts/state/movie.sqlite3"))
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("check")
    backup = sub.add_parser("backup")
    backup.add_argument("--output", type=Path, required=True)
    mapping = sub.add_parser("map")
    mapping.add_argument("--movie-id", required=True)
    mapping.add_argument("--provider", choices=["douban", "tmdb"], required=True)
    mapping.add_argument("--external-id", required=True)
    mapping.add_argument("--basis", choices=["human_verified", "provider_mapping"], required=True)
    mapping.add_argument("--confirmed", action="store_true")
    args = parser.parse_args()
    if args.action == "backup" and not args.database.is_file():
        parser.error("source database does not exist")
    repo = Repository(args.database)
    try:
        if args.action == "check":
            integrity = repo.connection.execute("PRAGMA integrity_check").fetchone()[0]
            version = repo.connection.execute("PRAGMA user_version").fetchone()[0]
            print(json.dumps({"integrity": integrity, "schema_version": version}))
            return 0 if integrity == "ok" else 1
        if args.action == "backup":
            repo.backup(args.output)
            print("Backup created; contains private records, keep local.")
        elif args.action == "map":
            if not args.confirmed:
                parser.error("--confirmed requires independent identity verification")
            url = f"https://movie.douban.com/subject/{args.external_id}/" if args.provider == "douban" else f"https://www.themoviedb.org/movie/{args.external_id}"
            repo.register_mapping(args.movie_id, ExternalMovieIdentity(provider=args.provider,
                external_id=args.external_id, status="confirmed", basis=args.basis, url=url))
            print("Verified mapping registered; this does not establish evidence access or usage permission.")
        return 0
    finally:
        repo.close()


if __name__ == "__main__":
    raise SystemExit(main())
