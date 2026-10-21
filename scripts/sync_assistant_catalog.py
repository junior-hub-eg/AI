"""Build data/catalog.json from the backend seed content, without any quiz questions or answers.

Usage:
    python scripts/sync_catalog.py [path/to/Seeding/Content]

The default path is the backend repo's content folder next to this service. Ids are the same name-based UUIDs the
backend seed gives its rows (SeedIds.For in the backend), so a lesson id in the context matches a lesson id here.
"""

from __future__ import annotations

import hashlib
import json
import sys
import uuid
from pathlib import Path

# Must match SeedIds.Namespace in src/JuniorHub.Infrastructure/Seeding/SeedIds.cs.
SEED_NAMESPACE = uuid.UUID("6f1c3c9e-2b1a-4f7e-9a51-4a1d2c7b9e10")

ROOT = Path(__file__).resolve().parent.parent
# Default: the service sits inside the backend repo. Pass the path when it lives in its own repo.
DEFAULT_CONTENT = ROOT.parent / "src" / "JuniorHub.Infrastructure" / "Seeding" / "Content"
OUTPUT = ROOT / "data" / "catalog.json"


def seed_id(kind: str, key: str) -> str:
    """Same as SeedIds.For(kind, key): a version 5 UUID of "kind:key" in lower case."""
    return str(uuid.uuid5(SEED_NAMESPACE, f"{kind}:{key}".lower()))


def build(content: Path) -> dict:
    tracks = json.loads((content / "tracks.json").read_text(encoding="utf-8"))["tracks"]
    learning = json.loads((content / "learning.json").read_text(encoding="utf-8"))["modules"]
    mentors = json.loads((content / "mentors.json").read_text(encoding="utf-8"))["mentors"]
    jobs = json.loads((content / "jobs.json").read_text(encoding="utf-8"))

    catalog = {
        "tracks": [
            {
                "code": t["code"],
                "name": t["name"],
                "short_description": t["shortDescription"],
                "profile": t["discoveryProfile"],
                "has_lessons": t["hasLessons"],
                "videos": [{"title": v["title"], "duration_seconds": v["durationSeconds"]} for v in t["videos"]],
                # The questions themselves stay out: the assistant must not help answer them.
                "quiz_question_count": len(t["quiz"]),
            }
            for t in tracks
        ],
        "modules": [
            {
                "track_code": m["trackCode"],
                "title": m["title"],
                "lessons": [
                    {
                        "id": seed_id("lesson", lesson["key"]),
                        "title": lesson["title"],
                        "concept": lesson["concept"],
                        "level": lesson["level"],
                        "duration_seconds": lesson["durationSeconds"],
                        "try_it_starter_code": lesson["tryItStarterCode"],
                        "try_it_expected_output": lesson["tryItExpectedOutput"],
                        "quiz_question_count": len(lesson["questions"]),
                        "school_link": _school_link(lesson.get("link")),
                    }
                    for lesson in m["lessons"]
                ],
            }
            for m in learning
        ],
        "mentors": [
            {
                "id": seed_id("mentor", m["key"]),
                "full_name": m["fullName"],
                "title": m["title"],
                "track_code": m["trackCode"],
                "years_of_experience": m["yearsOfExperience"],
                "rating": m["rating"],
                "languages": m["languages"],
                "availability": m["availability"],
                "skills": m["skills"],
                "bio": m["bio"],
            }
            for m in mentors
        ],
        "jobs": {
            "disclaimer": jobs["disclaimer"],
            "items": [
                {
                    "company_name": j["companyName"],
                    "role": j["role"],
                    "track_code": j["trackCode"],
                    "level": j["level"],
                    "skills": j["skills"],
                    "description": j["description"],
                    "question_count": len(j["questions"]),
                }
                for j in jobs["jobs"]
            ],
        },
    }
    body = json.dumps(catalog, ensure_ascii=False, sort_keys=True)
    catalog["version"] = hashlib.sha256(body.encode("utf-8")).hexdigest()[:12]
    return catalog


def _school_link(link: dict | None) -> dict | None:
    if not link:
        return None
    return {
        "subject": link["subject"],
        "grade": link["grade"],
        "unit": link["unit"],
        "title": link["title"],
        "school_example": link["schoolExample"],
        "bridge_text": link["bridgeText"],
        "badge": {"code": link["badge"]["code"], "name": link["badge"]["name"]},
    }


def main() -> None:
    content = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CONTENT
    catalog = build(content)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lessons = sum(len(m["lessons"]) for m in catalog["modules"])
    print(f"Wrote {OUTPUT} (version {catalog['version']}): {len(catalog['tracks'])} tracks, {lessons} lessons, "
          f"{len(catalog['mentors'])} mentors, {len(catalog['jobs']['items'])} jobs")


if __name__ == "__main__":
    main()
