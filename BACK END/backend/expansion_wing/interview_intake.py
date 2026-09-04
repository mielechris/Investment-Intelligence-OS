from __future__ import annotations

import hashlib
from dataclasses import dataclass

FORMATS = {"AUDIO": {"wav", "mp3", "m4a"}, "VIDEO": {"mp4", "mov"}, "TEXT": {"txt", "md"}}


@dataclass(frozen=True)
class UploadPolicy:
    max_bytes: int = 25_000_000
    max_duration_seconds: int = 7_200


def stage_reviewed_upload(*, media_type: str, extension: str, payload: bytes, duration_seconds: float,
                          consent: bool, permitted_use: bool, confidential_exclusion: bool,
                          jesse_identity_confirmed: bool, jesse_approval_required: bool,
                          policy: UploadPolicy = UploadPolicy()) -> dict:
    reasons = []
    if media_type not in FORMATS or extension.casefold().lstrip(".") not in FORMATS.get(media_type, set()):
        reasons.append("FORMAT_REJECTED")
    if not payload or len(payload) > policy.max_bytes: reasons.append("PAYLOAD_LIMIT")
    if duration_seconds < 0 or duration_seconds > policy.max_duration_seconds: reasons.append("DURATION_LIMIT")
    if not consent: reasons.append("CONSENT_REQUIRED")
    if not permitted_use: reasons.append("PERMITTED_USE_REQUIRED")
    if not confidential_exclusion: reasons.append("CONFIDENTIAL_EXCLUSION_REQUIRED")
    if not jesse_identity_confirmed: reasons.append("JESSE_IDENTITY_REQUIRED")
    if not jesse_approval_required: reasons.append("FINAL_APPROVAL_GATE_REQUIRED")
    return {"status": "STAGED" if not reasons else "REJECTED", "reasons": reasons,
        "content_hash": hashlib.sha256(payload).hexdigest() if not reasons else None,
        "transcription_status": "NOT_ACTIVATED", "speaker_attribution_status": "PENDING",
        "correction_status": "PENDING", "professional_approval_status": "PENDING",
        "real_file_inspected": False, "provider_called": False}
