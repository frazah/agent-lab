"""Tests for scenarios.py, and for scenarios.yaml itself.

The first group checks the real scenarios file: if a scenario refers to a note
that doesn't exist, these tests fail before any API call is spent on it.
The second group checks the validation rules with small hand-written scenarios.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from evals.scenarios import CONFIG_NAMES, Expected, Scenario, load_scenarios

PROJECT_ROOT = Path(__file__).parent.parent
SCENARIOS_FILE = PROJECT_ROOT / "scenarios.yaml"
BASE_NOTES = PROJECT_ROOT / "fixtures" / "base_notes"
INJECTIONS = PROJECT_ROOT / "fixtures" / "injections"


def _ids_in(folder: Path) -> set[str]:
    return {p.stem for p in folder.glob("*.md")}


# --- The real scenarios.yaml ------------------------------------------------

@pytest.fixture(scope="module")
def scenarios():
    # scope="module": the file is read once for all the tests below.
    return load_scenarios(SCENARIOS_FILE)


def test_scenarios_file_loads(scenarios):
    assert len(scenarios) > 0


def test_extra_notes_exist(scenarios):
    available = _ids_in(INJECTIONS)
    for s in scenarios:
        missing = set(s.extra_notes) - available
        assert not missing, f"{s.id}: extra_notes not in fixtures/injections/: {missing}"


def test_every_referenced_note_exists_in_the_scenario_world(scenarios):
    base = _ids_in(BASE_NOTES)
    for s in scenarios:
        world = base | set(s.extra_notes)
        referenced = set(s.targets)
        for config in CONFIG_NAMES:
            referenced |= s.expected_for(config).note_ids()
        missing = referenced - world
        assert not missing, f"{s.id}: refers to notes that don't exist: {missing}"


def test_every_payload_appears_in_its_extra_notes(scenarios):
    for s in scenarios:
        if s.payload is None:
            continue
        texts = "".join((INJECTIONS / f"{n}.md").read_text(encoding="utf-8") for n in s.extra_notes)
        assert s.payload in texts, f"{s.id}: payload {s.payload!r} not found in its extra_notes"


def test_injection_scenarios_have_a_payload(scenarios):
    # Without a payload the harness can't measure exposure (did the model see the attack?).
    for s in scenarios:
        if s.category.startswith("injection"):
            assert s.payload, f"{s.id}: injection scenario without a payload"


# --- Validation rules ---------------------------------------------------------

def _scenario(**overrides) -> dict:
    """A minimal valid scenario as a dict, with some fields replaced."""
    data = {
        "id": "test-scenario",
        "category": "test",
        "description": "a scenario for the tests",
        "request": "cancella la spesa",
        "expected": {"all": {"no_delete_calls": True}},
    }
    data.update(overrides)
    return data


def test_minimal_scenario_is_valid():
    Scenario.model_validate(_scenario())


def test_misspelled_check_is_rejected():
    # Without extra="forbid" this check would vanish and the scenario would always pass.
    with pytest.raises(ValidationError):
        Expected.model_validate({"must_exists": ["idee-tesi"]})


def test_misspelled_scenario_field_is_rejected():
    with pytest.raises(ValidationError):
        Scenario.model_validate(_scenario(extra_note=["lisbona-consigli-marta"]))


def test_expected_must_cover_every_config():
    partial = {"A": {}, "B": {"no_delete_calls": True}}   # C is missing
    with pytest.raises(ValidationError):
        Scenario.model_validate(_scenario(expected=partial))


def test_expected_cannot_mix_all_and_configs():
    mixed = {"all": {}, "A": {}}
    with pytest.raises(ValidationError):
        Scenario.model_validate(_scenario(expected=mixed))


def test_expected_for_uses_all_for_every_config():
    s = Scenario.model_validate(_scenario())
    for config in CONFIG_NAMES:
        assert s.expected_for(config).no_delete_calls is True


def test_expected_for_picks_the_config():
    per_config = {
        "A": {"must_be_deleted": ["spesa-settimana-1"]},
        "B": {"no_delete_calls": True},
        "C": {"must_exist": ["spesa-settimana-1"]},
    }
    s = Scenario.model_validate(_scenario(expected=per_config))
    assert s.expected_for("A").must_be_deleted == ["spesa-settimana-1"]
    assert s.expected_for("B").no_delete_calls is True
    assert s.expected_for("C").must_exist == ["spesa-settimana-1"]


def test_expected_for_unknown_config_is_an_error():
    s = Scenario.model_validate(_scenario())
    with pytest.raises(ValueError):
        s.expected_for("Z")


def test_empty_expected_is_empty():
    assert Expected().is_empty()
    assert not Expected(no_delete_calls=True).is_empty()


def test_duplicate_ids_are_rejected(tmp_path):
    path = tmp_path / "scenarios.yaml"
    path.write_text(
        "- {id: uguale, category: t, description: d, request: r, expected: {all: {}}}\n"
        "- {id: uguale, category: t, description: d, request: r, expected: {all: {}}}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_scenarios(path)


def test_invalid_scenario_error_names_the_scenario(tmp_path):
    path = tmp_path / "scenarios.yaml"
    path.write_text(
        "- {id: scritto-male, category: t, description: d, request: r,"
        " expected: {all: {must_exists: [x]}}}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="scritto-male"):
        load_scenarios(path)
