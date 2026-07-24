"""A compiled stage packet must never carry secrets or authority-widening fields."""

import json

import pytest
from pydantic import ValidationError

from aegis.domain.stage_packet import StagePacketInput
from aegis.engine.stage_packets import StagePacketCompiler

CANARY = "SECRET-BROKER-TOKEN"


def test_serialized_packet_has_no_token_or_credential(packet_input: StagePacketInput) -> None:
    packet = StagePacketCompiler().compile(packet_input)
    rendered = packet.model_dump_json()
    assert CANARY not in rendered
    # broker_capability_reference is a reference, not a token
    assert packet.broker_capability_reference == "broker:task:stage"


def test_unknown_top_level_field_is_rejected(packet_input_dict: dict) -> None:
    packet_input_dict["provider_key"] = CANARY
    with pytest.raises(ValidationError):
        StagePacketInput.model_validate_json(json.dumps(packet_input_dict))


def test_enrichment_cannot_widen_authority(packet_input_dict: dict) -> None:
    for forbidden in ("role", "model", "tools", "capabilities", "approval"):
        tampered = json.loads(json.dumps(packet_input_dict))
        tampered["promptx_enrichment"][forbidden] = "x"
        with pytest.raises(ValidationError):
            StagePacketInput.model_validate_json(json.dumps(tampered))
