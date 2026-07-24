import json

from aegis.domain.stage_packet import StagePacketInput
from aegis.engine.stage_packets import StagePacketCompiler


def test_packet_hash_is_stable_and_captures_exact_companions(
    packet_input: StagePacketInput,
) -> None:
    compiler = StagePacketCompiler()
    first = compiler.compile(packet_input)
    second = compiler.compile(packet_input)
    assert first.canonical_hash == second.canonical_hash
    assert len(first.canonical_hash) == 64
    assert first.promptx.source_commit == packet_input.promptx.source_commit
    assert first.subagents.catalog_sha256 == packet_input.subagents.catalog_sha256


def test_hash_covers_content(packet_input_dict: dict) -> None:
    compiler = StagePacketCompiler()
    base = compiler.compile(
        StagePacketInput.model_validate_json(json.dumps(packet_input_dict))
    )
    changed = dict(packet_input_dict, attempt_ordinal=1)
    other = compiler.compile(
        StagePacketInput.model_validate_json(json.dumps(changed))
    )
    assert base.canonical_hash != other.canonical_hash


def test_hash_is_independent_of_input_key_order(packet_input_dict: dict) -> None:
    compiler = StagePacketCompiler()
    forward = compiler.compile(
        StagePacketInput.model_validate_json(json.dumps(packet_input_dict))
    )
    reordered = dict(reversed(list(packet_input_dict.items())))
    backward = compiler.compile(
        StagePacketInput.model_validate_json(json.dumps(reordered))
    )
    assert forward.canonical_hash == backward.canonical_hash
