from unittest.mock import patch

import factory_room_api as room


def test_validation_failure_does_not_hide_governed_cases():
    case = {
        "case_id": "case_promoted",
        "ticker": "AMD",
        "topic": "AMD opportunity review",
        "stage": "EVIDENCE",
    }
    activity = {
        "case_latest": {},
        "by_room": {},
        "recent_events": [],
    }

    with (
        patch.object(room, "opportunity_queue", return_value=[]),
        patch.object(
            room,
            "_candidate_case_ids",
            return_value=["case_promoted"],
        ),
        patch.object(room, "_live_activity", return_value=activity),
        patch.object(room, "_case_row", return_value=case),
        patch.object(
            room,
            "build_validation_scorecard",
            side_effect=RuntimeError("validation unavailable"),
        ),
    ):
        status = room.factory_room_status()

    assert status["cases"] == [
        {
            **case,
            "active_room": None,
            "latest_event": None,
            "latest_event_at": None,
        }
    ]
    assert status["validation"]["availability"] == "OFFLINE"
    assert status["validation"]["error_type"] == "RuntimeError"
    assert status["validation"]["case_projection_available"] is True
    assert status["live_execution"] is False
