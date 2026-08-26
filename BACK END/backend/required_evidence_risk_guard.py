from __future__ import annotations

from typing import Any

from ledger import get_object, record_event, record_object
from required_evidence_reconciler import reconcile_committee


def reconcile_for_risk(
    decision: dict[str, Any],
    live_floor: dict[str, Any],
    packet_items: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    reconciliation = reconcile_committee(
        decision,
        live_floor,
        packet_items,
    )

    raw_required = [
        str(item).strip()
        for item in decision.get("required_evidence") or []
        if str(item).strip()
    ]

    if (
        raw_required
        and reconciliation["risk_can_ignore_raw_required_evidence"]
    ):
        effective_decision = {
            **decision,
            "required_evidence": [],
        }
    else:
        effective_decision = decision

    return effective_decision, reconciliation


def install_required_evidence_risk_guard(primary_module: Any) -> None:
    import main

    prior_evaluate = main.evaluate_decision

    def governed_evaluate_decision(
        decision: dict[str, Any]
    ) -> dict[str, Any]:
        case_id = str(decision.get("case_id") or "")
        packet_id = str(decision.get("evidence_packet_id") or "")

        live_floor = primary_module.primary_evidence_status(case_id)
        packet = get_object(packet_id) or {}

        # Risk must see both the original Committee packet
        # and governed evidence captured after Committee review.
        packet_items = list(packet.get("items") or [])

        governed_primary = (
            primary_module.primary_evidence_evidence(case_id)
        )

        packet_items.extend(governed_primary)

        effective_decision, reconciliation = reconcile_for_risk(
            decision,
            live_floor,
            packet_items,
        )

        authorization = prior_evaluate(effective_decision)

        raw_required = [
            str(item).strip()
            for item in decision.get("required_evidence") or []
            if str(item).strip()
        ]

        watch_obligations = []
        seen_watch_targets = set()

        for row in reconciliation.get("requirements") or []:
            for target in row.get("targets") or []:
                if target.get("state") != "WATCHING":
                    continue

                key = (
                    str(target.get("lane") or ""),
                    str(target.get("fact_key") or ""),
                )

                # A governed watch target counts once even if several
                # Committee requirements reference the same underlying fact.
                if key in seen_watch_targets:
                    continue

                seen_watch_targets.add(key)

                watch_obligations.append(
                    {
                        "requirement": row.get("requirement"),
                        "lane": target.get("lane"),
                        "fact_key": target.get("fact_key"),
                        "state": "WATCHING",
                    }
                )

        reconciled_nonblocking = (
            bool(raw_required)
            and reconciliation["risk_can_ignore_raw_required_evidence"]
        )

        enriched = {
            **authorization,
            "raw_required_evidence": raw_required,
            "required_evidence_reconciliation": reconciliation,
            "watch_obligations": watch_obligations,
            "risk_required_evidence_mode": (
                "RECONCILED_NONBLOCKING"
                if reconciled_nonblocking
                else "BLOCKING_OR_RAW"
            ),
        }

        authorization_id = str(
            enriched.get("risk_authorization_id") or ""
        )

        if authorization_id:
            record_object(
                authorization_id,
                "risk_authorization",
                case_id,
                enriched,
                parent_id=decision.get("decision_id"),
                topic=decision.get("topic"),
            )

            record_event(
                case_id,
                "RISK_REQUIRED_EVIDENCE_RECONCILED",
                entity_id=authorization_id,
                payload={
                    "blocking_count": reconciliation["blocking_count"],
                    "watching_count": reconciliation["watching_count"],
                    "ungoverned_new_scope_count": reconciliation[
                        "ungoverned_new_scope_count"
                    ],
                    "raw_required_evidence_ignored": (
                        reconciled_nonblocking
                    ),
                    "watch_obligations": len(watch_obligations),
                },
            )

        return enriched

    main.evaluate_decision = governed_evaluate_decision
