"""Domain-neutral evaluation core.

No subject-matter vocabulary may appear in this package -- not in code, not in comments, not in
docstrings -- and ``tests/test_core_boundary.py`` enforces that rather than trusting it. (The first
thing it caught was this file, which had been explaining the rule by listing the very words it
forbids.)

What is being evaluated is a *profile's* business. The core knows only about scenarios, responses,
criteria, trust, coverage and reporting.
"""
