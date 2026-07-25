"""YAML loaders for the rubric and the synthetic vignette set.

Both loaders parse YAML, validate against the pydantic boundary models, and
raise a clear :class:`LoaderError` on a malformed file rather than letting a
schema error surface deep in the harness. Keeping I/O here means the rest of
the package works only with validated, typed objects.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import yaml
from loguru import logger
from pydantic import ValidationError

from hai_eval.evaluator import registered_probes
from hai_eval.models import Rubric, VignetteSet

if TYPE_CHECKING:
    from collections.abc import Mapping

# Package-relative locations of the shipped defaults.
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_RUBRIC_PATH = _PACKAGE_ROOT / "framework" / "rubric.yaml"
DEFAULT_VIGNETTES_PATH = _PACKAGE_ROOT / "data" / "vignettes.yaml"


class LoaderError(RuntimeError):
    """Raised when a rubric or vignette file is missing or malformed."""


def _read_yaml(path: Path) -> Mapping[str, object]:
    """Read a YAML file into a mapping, or raise :class:`LoaderError`."""
    if not path.exists():
        msg = f"file not found: {path}"
        raise LoaderError(msg)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        msg = f"could not parse YAML in {path}: {exc}"
        raise LoaderError(msg) from exc
    if not isinstance(data, dict):
        msg = f"expected a top-level mapping in {path}, got {type(data).__name__}"
        raise LoaderError(msg)
    return data


def load_rubric(path: Path | None = None) -> Rubric:
    """Load and validate a rubric, defaulting to the shipped ``framework/rubric.yaml``.

    Raises:
        LoaderError: if the file is missing, unparseable, or fails validation,
            or if any criterion references an axis the rubric does not declare.
    """
    target = path or DEFAULT_RUBRIC_PATH
    data = _read_yaml(target)
    try:
        rubric = Rubric.model_validate(data)
    except ValidationError as exc:
        msg = f"rubric failed validation ({target}): {exc}"
        raise LoaderError(msg) from exc
    axis_keys = {axis.key for axis in rubric.axes}
    dangling = sorted({c.axis for c in rubric.criteria} - axis_keys)
    if dangling:
        msg = f"rubric criteria reference undeclared axes {dangling} in {target}"
        raise LoaderError(msg)

    # A misspelled probe name used to be scored NOT_ASSESSED with a stderr warning nobody
    # reads. Because unassessed criteria drop out of the axis mean, a one-character typo on
    # the blocking criterion RAISED the score and removed the blocking finding: the failure
    # direction was toward "safe". A probe the harness cannot run is a broken rubric, not a
    # design decision -- except for the manual_ prefix, which declares human review on purpose.
    known = registered_probes()
    unknown = sorted(
        {
            c.probe
            for c in rubric.criteria
            if not c.probe.startswith("manual_") and c.probe not in known
        }
    )
    if unknown:
        msg = (
            f"rubric names probe(s) the harness cannot run: {unknown} in {target}. "
            f"Registered probes: {sorted(known)}. "
            f"Use a 'manual_' prefix for criteria that are reviewed by a human."
        )
        raise LoaderError(msg)

    # Blocking is opt-in per axis, so a rubric that marks nothing eligible can never produce a
    # blocking finding. That may be deliberate; it must not be accidental.
    if not any(axis.blocking_eligible for axis in rubric.axes):
        logger.warning(
            "rubric {} marks no axis blocking_eligible: no finding in this rubric can block "
            "adoption, however severe",
            target,
        )
    return rubric


def load_vignettes(path: Path | None = None) -> VignetteSet:
    """Load and validate a synthetic vignette set.

    Raises:
        LoaderError: if the file is missing, unparseable, or fails validation.
    """
    target = path or DEFAULT_VIGNETTES_PATH
    data = _read_yaml(target)
    try:
        return VignetteSet.model_validate(data)
    except ValidationError as exc:
        msg = f"vignette set failed validation ({target}): {exc}"
        raise LoaderError(msg) from exc
