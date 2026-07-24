import json
from collections.abc import Mapping

import pytest
from pydantic import ValidationError

from aegis.domain.stage_packet import StagePacketInput


def test_snapshots_are_frozen_mappings(packet_input: StagePacketInput) -> None:
    assert isinstance(packet_input.task_snapshot, Mapping)
    with pytest.raises(TypeError):
        packet_input.task_snapshot["request"] = "tampered"  # type: ignore[index]


def test_packet_rejects_authority_bearing_enrichment(packet_input_dict: dict) -> None:
    packet_input_dict["promptx_enrichment"]["next_stage"] = "deploy"
    with pytest.raises(ValidationError):
        StagePacketInput.model_validate_json(json.dumps(packet_input_dict))


def test_non_finite_numbers_are_rejected(packet_input_dict: dict) -> None:
    packet_input_dict["context_snapshot"] = {"ratio": float("inf")}
    with pytest.raises((ValidationError, ValueError)):
        StagePacketInput.model_validate(packet_input_dict)


def test_bad_request_digest_is_rejected(packet_input_dict: dict) -> None:
    packet_input_dict["request_digest"] = "not-a-digest"
    with pytest.raises(ValidationError):
        StagePacketInput.model_validate_json(json.dumps(packet_input_dict))


def test_bad_uuid_is_rejected(packet_input_dict: dict) -> None:
    packet_input_dict["task_id"] = "not-a-uuid"
    with pytest.raises(ValidationError):
        StagePacketInput.model_validate_json(json.dumps(packet_input_dict))
