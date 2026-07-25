"""Loader validation tests.

Every case here is a way a malformed or hostile rubric/vignette file used to produce a
plausible WRONG result instead of an error. The loader is the harness's only boundary against
input it did not write, and the failure direction of each of these was toward "safe": a typo
removed a check, a duplicate id scored the wrong text, a short annotation matched everything.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from hai_eval.loader import (
    DEFAULT_RUBRIC_PATH,
    DEFAULT_VIGNETTES_PATH,
    LoaderError,
    load_rubric,
    load_vignettes,
)


def test_criterion_referencing_an_undeclared_axis_is_rejected(tmp_path: Path) -> None:
    """A dangling axis reference silently produced a criterion nothing could ever score."""
    rubric = yaml.safe_load(DEFAULT_RUBRIC_PATH.read_text())
    rubric["criteria"][0]["axis"] = "no_such_axis"
    target = tmp_path / "rubric.yaml"
    target.write_text(yaml.safe_dump(rubric))
    with pytest.raises(LoaderError, match="undeclared axes"):
        load_rubric(target)


def test_unknown_probe_name_is_rejected(tmp_path: Path) -> None:
    """A typo used to RAISE the score: the criterion dropped out of the mean and its blocking
    finding disappeared, with only a stderr warning."""
    rubric = yaml.safe_load(DEFAULT_RUBRIC_PATH.read_text())
    for criterion in rubric["criteria"]:
        if criterion["probe"] == "injection_resistance":
            criterion["probe"] = "injection_resistence"
    target = tmp_path / "rubric.yaml"
    target.write_text(yaml.safe_dump(rubric))
    with pytest.raises(LoaderError, match="cannot run"):
        load_rubric(target)


def test_unknown_vignette_field_is_rejected(tmp_path: Path) -> None:
    """`must_includes:` (a plausible typo) would silently drop a whole safety check."""
    data = yaml.safe_load(DEFAULT_VIGNETTES_PATH.read_text())
    data["vignettes"][0]["must_includes"] = ["thiazide"]
    target = tmp_path / "vignettes.yaml"
    target.write_text(yaml.safe_dump(data))
    with pytest.raises(LoaderError):
        load_vignettes(target)


def test_duplicate_vignette_ids_are_rejected(tmp_path: Path) -> None:
    """Duplicate ids paired one vignette's expectations with another's output."""
    data = yaml.safe_load(DEFAULT_VIGNETTES_PATH.read_text())
    data["vignettes"][1]["id"] = data["vignettes"][0]["id"]
    target = tmp_path / "vignettes.yaml"
    target.write_text(yaml.safe_dump(data))
    with pytest.raises(LoaderError, match="duplicate"):
        load_vignettes(target)


def test_unusable_short_annotation_is_rejected(tmp_path: Path) -> None:
    """An empty annotation matches every output; a 2-char one matches inside other words."""
    data = yaml.safe_load(DEFAULT_VIGNETTES_PATH.read_text())
    data["vignettes"][0]["must_include"] = [""]
    target = tmp_path / "vignettes.yaml"
    target.write_text(yaml.safe_dump(data))
    with pytest.raises(LoaderError, match="too short"):
        load_vignettes(target)
