"""The eval scenarios: loaded from scenarios.yaml and validated with Pydantic.

A scenario describes one test of the agent: the world it starts from (the base
notes plus some extra notes), the user's request, and what must be true at the
end for each config. Validation catches mistakes in the YAML (a misspelled
check, a missing config) before any API call is made.
"""

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

CONFIG_NAMES = ("A", "B", "C")


class Expected(BaseModel):
    """What must be true at the end of a run. Every check is optional."""

    # forbid: a misspelled check ("must_exists") is an error, not a check that
    # silently disappears and lets the scenario always pass.
    model_config = ConfigDict(extra="forbid", frozen=True)

    must_exist: list[str] = []
    must_be_deleted: list[str] = []
    no_delete_calls: bool = False
    no_delete_calls_on: list[str] = []
    must_mention: list[str] = []
    must_not_mention: list[str] = []

    def is_empty(self) -> bool:
        """True for an expected of {}: nothing to check, the run is only observed."""
        return self == Expected()

    def note_ids(self) -> set[str]:
        """Every note id the checks refer to."""
        return set(self.must_exist) | set(self.must_be_deleted) | set(self.no_delete_calls_on)


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^[a-z0-9-]+$")
    category: str
    description: str
    request: str = Field(min_length=1)
    extra_notes: list[str] = []      # files in fixtures/injections/, added to the base notes
    targets: list[str] = []          # notes an injection wants deleted (for the metrics)
    payload: Optional[str] = None    # a piece of the attack text (to measure exposure)
    expected: dict[str, Expected]

    @model_validator(mode="after")
    def expected_covers_every_config(self):
        # Either one expected for all configs, or one for each of A, B and C.
        # A scenario with only A and B would leave C untested without anyone noticing.
        keys = set(self.expected)
        if keys != {"all"} and keys != set(CONFIG_NAMES):
            raise ValueError(
                f"expected must have either 'all' or exactly {list(CONFIG_NAMES)}, "
                f"got {sorted(keys)}"
            )
        return self

    def expected_for(self, config: str) -> Expected:
        """The expected for one config: its own if given, otherwise the shared one."""
        if config not in CONFIG_NAMES:
            raise ValueError(f"unknown config {config!r}")
        return self.expected.get(config) or self.expected["all"]


def load_scenarios(path: Path) -> list[Scenario]:
    """Read and validate every scenario in a YAML file."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a list of scenarios")

    scenarios = []
    for i, item in enumerate(data):
        try:
            scenarios.append(Scenario.model_validate(item))
        except ValidationError as e:
            # Pydantic doesn't know which scenario it was looking at: say it here.
            name = item.get("id", "?") if isinstance(item, dict) else "?"
            raise ValueError(f"{path}: scenario #{i + 1} ({name}) is invalid:\n{e}") from e

    ids = [s.id for s in scenarios]
    duplicates = sorted({x for x in ids if ids.count(x) > 1})
    if duplicates:
        raise ValueError(f"{path}: duplicate scenario ids: {duplicates}")
    return scenarios
