"""Domain profiles: what is being evaluated, plugged into a core that does not know.

Importing this package registers every shipped profile, so a rubric naming one can be resolved
without the caller knowing which module defines it. Registration is a side effect of import and
nothing else -- no discovery, no entry points, no configuration-driven registry. There is one
shipped profile and one test double, and a seam earns machinery when it has consumers rather than
when it might have them.
"""

from __future__ import annotations

from hai_eval.profiles.cds import CDS_PROFILE

__all__ = ["CDS_PROFILE"]
