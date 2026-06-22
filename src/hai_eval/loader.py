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
from pydantic import ValidationError

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
