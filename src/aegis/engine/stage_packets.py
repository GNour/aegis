"""The only path that turns a validated ``StagePacketInput`` into a hashed packet.

Pure: no I/O, no clock, no global configuration. The canonical hash (see
``canonical_packet_hash``) is computed over the compact, sorted JSON of the packet with
the hash field blanked, so it is stable across processes and independent of key ordering.
Round-tripping goes through JSON (not Python dicts) so the strict domain models accept
arrays as tuples.
"""

from __future__ import annotations

import json

from aegis.domain.stage_packet import (
    StageExecutionPacket,
    StagePacketInput,
    canonical_packet_hash,
)

_ZERO_HASH = "0" * 64


class StagePacketCompiler:
    def compile(self, source: StagePacketInput) -> StageExecutionPacket:
        values = source.packet_values()
        unsigned = StageExecutionPacket.model_validate_json(
            json.dumps({**values, "canonical_hash": _ZERO_HASH})
        )
        digest = canonical_packet_hash(unsigned)
        return StageExecutionPacket.model_validate_json(
            json.dumps({**unsigned.model_dump(mode="json"), "canonical_hash": digest})
        )
