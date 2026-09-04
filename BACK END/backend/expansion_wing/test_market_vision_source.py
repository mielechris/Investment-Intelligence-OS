from __future__ import annotations

import unittest

from expansion_wing.investor_intelligence import SOURCE_TYPES
from expansion_wing.market_vision_source import (
    IIOS_ROUTES,
    ForecastObservation,
    PaidSourceDiscoveryRegistry,
    bounded_paid_source_note,
    market_vision_registration,
    publication_identity,
)
from expansion_wing.professional_library import initial_library


def forecast(**changes) -> ForecastObservation:
    values = {
        "observation_id": "synthetic-forecast-1",
        "publication_timestamp": "2026-08-01T12:00:00-04:00",
        "publication_family": "UNKNOWN_PUBLICATION_VARIANT",
        "commodity": "SYNTHETIC_CORN_FIXTURE",
        "forecast_horizon": "30_DAYS",
        "directional_expectation": "UP",
        "catalysts": ("SYNTHETIC_WEATHER_CATALYST",),
        "invalidation_conditions": ("SYNTHETIC_SUPPLY_RECOVERY",),
        "supporting_primary_sources": ("https://example.gov/synthetic-primary-fixture",),
    }
    values.update(changes)
    return ForecastObservation(**values)


class MarketVisionRegistrationTests(unittest.TestCase):
    def test_exact_governed_identity_rights_and_false_authority(self):
        value = market_vision_registration()
        self.assertEqual((value["publisher"], value["analyst"], value["domain"]),
            ("Market Vision Inc.", "John T. Barone", "mktvsn.com"))
        self.assertEqual(value["source_type"], "PAID_SUBSCRIPTION_COMMODITY_RESEARCH")
        self.assertEqual(value["trust_class"], "SECONDARY_DOMAIN_EXPERT")
        self.assertEqual((value["lifecycle"], value["rights_state"], value["claim_state"]),
            ("DISCOVERED", "RIGHTS_REVIEW_REQUIRED", "REPORTED"))
        self.assertFalse(value["automatic_promotion"])
        self.assertTrue(all(authority is False for authority in value["authority"].values()))
        self.assertEqual(value["primary_system"], "IIOS")
        self.assertEqual(value["possible_downstream_consumers"], ("DULCE",))
        self.assertIn("PAID_SUBSCRIPTION_COMMODITY_RESEARCH", SOURCE_TYPES)

    def test_publication_identity_stays_unknown_until_exactly_verified(self):
        self.assertEqual(publication_identity(None, None), "UNKNOWN_PUBLICATION_VARIANT")
        self.assertEqual(publication_identity("Email report", None), "UNKNOWN_PUBLICATION_VARIANT")
        self.assertEqual(publication_identity("The Weekly Summary", "Other"), "UNKNOWN_PUBLICATION_VARIANT")
        self.assertEqual(publication_identity("The Commodity Update", "The Commodity Update"),
            "UNKNOWN_PUBLICATION_VARIANT")
        self.assertEqual(publication_identity("The Commodity Update", "The Commodity Update", human_verified=True),
            "The Commodity Update")

    def test_paid_full_text_and_unsupported_quotation_are_rejected(self):
        with self.assertRaises(PermissionError):
            bounded_paid_source_note(note="synthetic", complete_newsletter=True,
                rights_state="RIGHTS_REVIEW_REQUIRED")
        with self.assertRaises(PermissionError):
            bounded_paid_source_note(note="synthetic", quotation="unsupported",
                rights_state="RIGHTS_REVIEW_REQUIRED")
        value = bounded_paid_source_note(note="bounded synthetic reviewer note",
            rights_state="RIGHTS_REVIEW_REQUIRED")
        self.assertEqual(value["rights_state"], "RIGHTS_REVIEW_REQUIRED")
        self.assertFalse(value["complete_newsletter_retained"])

    def test_content_hash_controls_duplicates(self):
        left = bounded_paid_source_note(note="same synthetic note", rights_state="RIGHTS_REVIEW_REQUIRED")
        right = bounded_paid_source_note(note=" same   synthetic note ", rights_state="RIGHTS_REVIEW_REQUIRED")
        self.assertEqual(left["content_hash"], right["content_hash"])
        registry = PaidSourceDiscoveryRegistry()
        self.assertEqual(registry.register(left), "DISCOVERED_RIGHTS_REVIEW_REQUIRED")
        self.assertEqual(registry.register(right), "DUPLICATE")

    def test_professional_library_closes_commodity_practitioner_gap(self):
        entry = next(item for item in initial_library()
            if item["profile"]["professional_id"] == "john_t_barone")
        self.assertEqual(entry["plan"]["hypothesis_status"], "SOURCE_REVIEW_REQUIRED")
        self.assertEqual(entry["plan"]["acquisition_status"], "NOT_ACTIVATED")
        self.assertFalse(entry["plan"]["external_requests_allowed"])
        self.assertIn("COMMODITY", entry["plan"]["specialties"])


class ForecastObservationTests(unittest.TestCase):
    def test_attribution_primary_verification_and_no_authority(self):
        blocked = forecast().review_projection()
        self.assertEqual(blocked["routes"], ())
        self.assertEqual(blocked["routing_status"], "BLOCKED_HUMAN_RIGHTS_REVIEW")
        projection = forecast().review_projection(rights_approved=True, human_approved=True)
        self.assertEqual((projection["analyst"], projection["publisher"], projection["claim_state"]),
            ("John T. Barone", "Market Vision Inc.", "REPORTED"))
        self.assertEqual(projection["routes"], IIOS_ROUTES)
        for key in ("automatic_promotion", "investment_recommendation", "paper_trade_authority"):
            self.assertFalse(projection[key])
        with self.assertRaises(PermissionError):
            forecast(supporting_primary_sources=()).validate()
        with self.assertRaises(ValueError):
            forecast(analyst="Unknown").validate()

    def test_incorrect_forecast_is_failure_museum_eligible(self):
        blocked = forecast(subsequent_outcome="SYNTHETIC_DECLINE",
            accuracy_classification="INCORRECT").review_projection()
        self.assertFalse(blocked["failure_museum_eligible"])
        projection = forecast(subsequent_outcome="SYNTHETIC_DECLINE",
            accuracy_classification="INCORRECT").review_projection(rights_approved=True, human_approved=True)
        self.assertTrue(projection["failure_museum_eligible"])
        self.assertIn("Failure Museum", projection["routes"])
        self.assertFalse(projection["automatic_promotion"])


if __name__ == "__main__":
    unittest.main()
