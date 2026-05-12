from __future__ import annotations

from sim.testing import assert_protocol_conformance
from sim_plugin_blender import BlenderDriver


def test_protocol_conformance() -> None:
    assert_protocol_conformance(BlenderDriver)
