"""The platform's content (tracks, lessons, mentors, practice jobs) and rules, loaded once at start."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA = Path(__file__).resolve().parent.parent / "data"


class Catalog:
    def __init__(self, raw: dict[str, Any]):
        self.version: str = raw.get("version", "dev")
        self.tracks: list[dict] = raw["tracks"]
        self.modules: list[dict] = raw["modules"]
        self.mentors: list[dict] = raw["mentors"]
        self.jobs: dict = raw["jobs"]
        self._lessons = {
            lesson["id"]: {**lesson, "track_code": m["track_code"], "module": m["title"]}
            for m in self.modules for lesson in m["lessons"]
        }

    def track(self, code: str | None) -> dict | None:
        code = (code or "").strip().upper().replace("/", "").replace(" ", "")
        aliases = {"UI": "UIUX", "UX": "UIUX", "GAME": "GAMING", "GAMES": "GAMING", "TEST": "TESTING", "QA": "TESTING"}
        code = aliases.get(code, code)
        return next((t for t in self.tracks if t["code"] == code), None)

    def lessons_of(self, track_code: str) -> list[dict]:
        return [lesson for lesson in self._lessons.values() if lesson["track_code"] == track_code]

    def lesson(self, id_or_title: str) -> dict | None:
        if id_or_title in self._lessons:
            return self._lessons[id_or_title]
        needle = id_or_title.strip().lower()
        exact = [lesson for lesson in self._lessons.values() if lesson["title"].lower() == needle]
        if exact:
            return exact[0]
        partial = [lesson for lesson in self._lessons.values()
                   if needle in lesson["title"].lower() or needle == lesson["concept"].lower()]
        return partial[0] if partial else None

    def mentors_of(self, track_code: str | None) -> list[dict]:
        found = [m for m in self.mentors if track_code is None or m["track_code"] == track_code]
        return sorted(found, key=lambda m: (-m["rating"], m["full_name"]))

    def mentor(self, mentor_id: str) -> dict | None:
        return next((m for m in self.mentors if m["id"] == mentor_id), None)

    def jobs_of(self, track_code: str | None) -> list[dict]:
        return [j for j in self.jobs["items"] if track_code is None or j["track_code"] == track_code]

    def known_link_refs(self) -> set[str]:
        return set(self._lessons) | {t["code"] for t in self.tracks} | {m["id"] for m in self.mentors}


@lru_cache
def load_catalog() -> Catalog:
    return Catalog(json.loads((DATA / "catalog.json").read_text(encoding="utf-8")))


@lru_cache
def load_rules() -> dict[str, str]:
    """Sections of data/platform_rules.md by their '## key' heading."""
    sections: dict[str, str] = {}
    key = None
    for line in (DATA / "platform_rules.md").read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            key = line[3:].strip()
            sections[key] = ""
        elif key:
            sections[key] += line + "\n"
    return {k: v.strip() for k, v in sections.items()}
