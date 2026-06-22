"""Shared fixtures: the shipped rubric and vignette set, plus the mock tool."""

from __future__ import annotations

import pytest

from hai_eval.loader import load_rubric, load_vignettes
from hai_eval.models import Rubric, VignetteSet
from hai_eval.tool import DeterministicMockModel, MockDecisionSupportTool


@pytest.fixture
def rubric() -> Rubric:
    return load_rubric()


@pytest.fixture
def vignettes() -> VignetteSet:
    return load_vignettes()


@pytest.fixture
def mock_tool() -> MockDecisionSupportTool:
    return MockDecisionSupportTool(DeterministicMockModel())
