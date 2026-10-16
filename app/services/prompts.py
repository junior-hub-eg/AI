"""Versioned prompt files: prompts/<name>@<version>.md"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    template: str

    @property
    def label(self) -> str:
        return f"{self.name}@{self.version}"

    def render(self, **values: str) -> str:
        def substitute(match: re.Match[str]) -> str:
            key = match.group(1)
            if key not in values:
                raise KeyError(f"prompt {self.label} needs a value for {{{{{key}}}}}")
            return values[key]

        return _PLACEHOLDER.sub(substitute, self.template)


class PromptStore:
    def __init__(self, directory: Path, versions: dict[str, str]) -> None:
        self._prompts: dict[str, Prompt] = {}
        for name, version in versions.items():
            path = directory / f"{name}@{version}.md"
            if not path.is_file():
                raise FileNotFoundError(f"Prompt file not found: {path}")
            self._prompts[name] = Prompt(name, version, path.read_text(encoding="utf-8"))

    def get(self, name: str) -> Prompt:
        return self._prompts[name]
