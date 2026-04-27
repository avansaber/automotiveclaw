"""L1 tests for AutomotiveClaw compliance + reports domains.

Covers:
  - Compliance: add-check, list-checks, generate-buyers-guide,
    generate-odometer-statement, ofac-screening, compliance-summary
  - Reports: inventory-aging, gross-profit, service-efficiency,
    parts-velocity, fi-penetration, status
"""
import pytest
import sys
import os

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

from auto_helpers import (
    call_action, ns, is_ok, is_error, load_db_query,
    seed_company, seed_customer, seed_customer_ext, seed_naming_series,
    seed_vehicle, seed_deal, seed_repair_order,
)

_mod = load_db_query()
ACTIONS = _mod.ACTIONS


# ── Compliance Check Tests ───────────────────────────────────────────────


class TestAddComplianceCheck:
    """auto-add-compliance-check"""

    def test_add_compliance_check_ok(self, conn, env):
        deal_id = seed_deal(
            conn, env["vehicle_id"], env["core_customer_id"],
            env["company_id"],
        )
        result = call_action(
            ACTIONS["auto-add-compliance-check"], conn,
            ns(
                deal_id=deal_id,
                company_id=env["company_id"],
                check_type="ofac",
                check_result="pass",
                checked_by="Compliance Officer",
                notes="All clear",
            ),
        )
        assert is_ok(result), result
        assert result["check_type"] == "ofac"
        assert result["check_result"] == "pass"
        assert result["deal_id"] == deal_id

    def test_add_compliance_check_all_types(self, conn, env):
        deal_id = seed_deal(
            conn, env["vehicle_id"], env["core_customer_id"],
            env["company_id"],
        )
        for check_type in ("ofac", "red_flag", "tila", "odometer", "buyers_guide"):
            result = call_action(
                ACTIONS["auto-add-compliance-check"], conn,
                ns(
                    deal_id=deal_id,
                    company_id=env["company_id"],
                    check_type=check_type,
                    check_result="pass",
                ),
            )
            assert is_ok(result), f"Failed for check_type={check_type}: {result}"
            assert result["check_type"] == check_type

    def test_add_compliance_check_pending(self, conn, env):
        deal_id = seed_deal(
            conn, env["vehicle_id"], env["core_customer_id"],
            env["company_id"],
        )
        result = call_action(
            ACTIONS["auto-add-compliance-check"], conn,
            ns(
                deal_id=deal_id,
                company_id=env["company_id"],
                check_type="tila",
            ),
        )
        assert is_ok(result), result
        assert result["check_result"] == "pending"

    def test_add_compliance_check_missing_type(self, conn, env):
        deal_id = seed_deal(
            conn, env["vehicle_id"], env["core_customer_id"],
            env["company_id"],
        )
        result = call_action(
            ACTIONS["auto-add-compliance-check"], conn,
            ns(deal_id=deal_id, company_id=env["company_id"]),
        )
        assert is_error(result)

    def test_add_compliance_check_invalid_type(self, conn, env):
        deal_id = seed_deal(
            conn, env["vehicle_id"], env["core_customer_id"],
            env["company_id"],
        )
        result = call_action(
            ACTIONS["auto-add-compliance-check"], conn,
            ns(
                deal_id=deal_id,
                company_id=env["company_id"],
                check_type="invalid",
            ),
        )
        assert is_error(result)

    def test_add_compliance_check_missing_deal(self, conn, env):
        result = call_action(
            ACTIONS["auto-add-compliance-check"], conn,
            ns(company_id=env["company_id"], check_type="ofac"),
        )
        assert is_error(result)

    def test_add_compliance_check_invalid_result(self, conn, env):
        deal_id = seed_deal(
            conn, env["vehicle_id"], env["core_customer_id"],
            env["company_id"],
        )
        result = call_action(
            ACTIONS["auto-add-compliance-check"], conn,
            ns(
                deal_id=deal_id,
                company_id=env["company_id"],
                check_type="ofac",
                check_result="maybe",
            ),
        )
        assert is_error(result)


class TestListComplianceChecks:
    """auto-list-compliance-checks"""

    def test_list_compliance_checks_by_deal(self, conn, env):
        deal_id = seed_deal(
            conn, env["vehicle_id"], env["core_customer_id"],
            env["company_id"],
        )
        call_action(
            ACTIONS["auto-add-compliance-check"], conn,
            ns(
                deal_id=deal_id,
                company_id=env["company_id"],
                check_type="ofac",
                check_result="pass",
            ),
        )
        result = call_action(
            ACTIONS["auto-list-compliance-checks"], conn,
            ns(deal_id=deal_id),
        )
        assert is_ok(result), result
        assert result["total_count"] >= 1

    def test_list_compliance_checks_by_type(self, conn, env):
        deal_id = seed_deal(
            conn, env["vehicle_id"], env["core_customer_id"],
            env["company_id"],
        )
        call_action(
            ACTIONS["auto-add-compliance-check"], conn,
            ns(
                deal_id=deal_id,
                company_id=env["company_id"],
                check_type="red_flag",
                check_result="pass",
            ),
        )
        result = call_action(
            ACTIONS["auto-list-compliance-checks"], conn,
            ns(company_id=env["company_id"], check_type="red_flag"),
        )
        assert is_ok(result), result
        for row in result["rows"]:
            assert row["check_type"] == "red_flag"

    def test_list_compliance_checks_by_result(self, conn, env):
        deal_id = seed_deal(
            conn, env["vehicle_id"], env["core_customer_id"],
            env["company_id"],
        )
        call_action(
            ACTIONS["auto-add-compliance-check"], conn,
            ns(
                deal_id=deal_id,
                company_id=env["company_id"],
                check_type="tila",
                check_result="fail",
            ),
        )
        result = call_action(
            ACTIONS["auto-list-compliance-checks"], conn,
            ns(company_id=env["company_id"], check_result="fail"),
        )
        assert is_ok(result), result
        assert result["total_count"] >= 1
        for row in result["rows"]:
            assert row["check_result"] == "fail"


# ── Buyers Guide + Odometer Statement ────────────────────────────────────


class TestBuyersGuide:
    """auto-generate-buyers-guide"""

    def test_generate_buyers_guide_new(self, conn, env):
        result = call_action(
            ACTIONS["auto-generate-buyers-guide"], conn,
            ns(vehicle_id=env["vehicle_id"], company_id=env["company_id"]),
        )
        assert is_ok(result), result
        assert result["document_type"] == "buyers_guide"
        assert result["make"] == "Toyota"
        assert result["model"] == "Camry"
        assert result["warranty_type"] == "manufacturer"

    def test_generate_buyers_guide_used(self, conn, env):
        veh_id = seed_vehicle(
            conn, env["company_id"], "Ford", "Mustang",
            year=2020, vehicle_condition="used",
        )
        result = call_action(
            ACTIONS["auto-generate-buyers-guide"], conn,
            ns(vehicle_id=veh_id, company_id=env["company_id"]),
        )
        assert is_ok(result), result
        assert result["warranty_type"] == "as_is"

    def test_generate_buyers_guide_not_found(self, conn, env):
        result = call_action(
            ACTIONS["auto-generate-buyers-guide"], conn,
            ns(vehicle_id="nonexistent", company_id=env["company_id"]),
        )
        assert is_error(result)

    def test_generate_buyers_guide_missing_vehicle(self, conn, env):
        result = call_action(
            ACTIONS["auto-generate-buyers-guide"], conn,
            ns(company_id=env["company_id"]),
        )
        assert is_error(result)


class TestOdometerStatement:
    """auto-generate-odometer-statement"""

    def test_generate_odometer_statement(self, conn, env):
        result = call_action(
            ACTIONS["auto-generate-odometer-statement"], conn,
            ns(vehicle_id=env["vehicle_id"], company_id=env["company_id"]),
        )
        assert is_ok(result), result
        assert result["document_type"] == "odometer_statement"
        assert result["make"] == "Toyota"

    def test_generate_odometer_with_mileage_override(self, conn, env):
        result = call_action(
            ACTIONS["auto-generate-odometer-statement"], conn,
            ns(
                vehicle_id=env["vehicle_id"],
                company_id=env["company_id"],
                mileage="99999",
            ),
        )
        assert is_ok(result), result
        assert result["odometer_reading"] == "99999"


# ── OFAC Screening ───────────────────────────────────────────────────────


class TestOFACScreening:
    """auto-ofac-screening-check"""

    def test_ofac_screening_ok(self, conn, env):
        result = call_action(
            ACTIONS["auto-ofac-screening-check"], conn,
            ns(
                customer_id=env["customer_ext_id"],
                company_id=env["company_id"],
            ),
        )
        assert is_ok(result), result
        assert result["screening_result"] == "pass"
        assert result["screening_type"] == "ofac"
        assert result["customer_name"] == "John Doe"

    def test_ofac_screening_missing_customer(self, conn, env):
        result = call_action(
            ACTIONS["auto-ofac-screening-check"], conn,
            ns(company_id=env["company_id"]),
        )
        assert is_error(result)

    def test_ofac_screening_customer_not_found(self, conn, env):
        result = call_action(
            ACTIONS["auto-ofac-screening-check"], conn,
            ns(customer_id="nonexistent", company_id=env["company_id"]),
        )
        assert is_error(result)


# ── Compliance Summary ───────────────────────────────────────────────────


class TestComplianceSummary:
    """auto-compliance-summary"""

    def test_compliance_summary_empty(self, conn, env):
        result = call_action(
            ACTIONS["auto-compliance-summary"], conn,
            ns(company_id=env["company_id"]),
        )
        assert is_ok(result), result
        assert result["total_checks"] == 0

    def test_compliance_summary_with_data(self, conn, env):
        deal_id = seed_deal(
            conn, env["vehicle_id"], env["core_customer_id"],
            env["company_id"],
        )
        for ct in ("ofac", "red_flag", "tila"):
            call_action(
                ACTIONS["auto-add-compliance-check"], conn,
                ns(
                    deal_id=deal_id,
                    company_id=env["company_id"],
                    check_type=ct,
                    check_result="pass",
                ),
            )
        result = call_action(
            ACTIONS["auto-compliance-summary"], conn,
            ns(company_id=env["company_id"]),
        )
        assert is_ok(result), result
        assert result["total_checks"] == 3
        assert result["by_result"]["pass"] == 3


# ── Cross-Domain Reports ────────────────────────────────────────────────


class TestCrossDomainReports:
    """auto-inventory-aging, auto-gross-profit-report, auto-service-efficiency,
    auto-parts-velocity, auto-fi-penetration, status"""

    def test_inventory_aging(self, conn, env):
        result = call_action(
            ACTIONS["auto-inventory-aging"], conn,
            ns(company_id=env["company_id"]),
        )
        assert is_ok(result), result
        assert result["total_available"] >= 1

    def test_gross_profit_report_empty(self, conn, env):
        result = call_action(
            ACTIONS["auto-gross-profit-report"], conn,
            ns(company_id=env["company_id"]),
        )
        assert is_ok(result), result
        assert result["count"] == 0

    def test_gross_profit_report_with_deal(self, conn, env):
        deal_id = seed_deal(
            conn, env["vehicle_id"], env["core_customer_id"],
            env["company_id"],
        )
        call_action(ACTIONS["auto-finalize-deal"], conn, ns(deal_id=deal_id))
        result = call_action(
            ACTIONS["auto-gross-profit-report"], conn,
            ns(company_id=env["company_id"]),
        )
        assert is_ok(result), result
        assert result["count"] >= 1
        assert float(result["total_gross_profit"]) > 0

    def test_service_efficiency(self, conn, env):
        seed_repair_order(conn, env["company_id"])
        result = call_action(
            ACTIONS["auto-service-efficiency"], conn,
            ns(company_id=env["company_id"]),
        )
        assert is_ok(result), result
        assert result["total_repair_orders"] >= 1

    def test_parts_velocity(self, conn, env):
        call_action(
            ACTIONS["auto-add-part"], conn,
            ns(company_id=env["company_id"], part_number="RPT-VEL-001",
               cost="10.00", quantity_on_hand="3", reorder_point="10"),
        )
        result = call_action(
            ACTIONS["auto-parts-velocity"], conn,
            ns(company_id=env["company_id"]),
        )
        assert is_ok(result), result
        assert result["count"] >= 1

    def test_fi_penetration(self, conn, env):
        result = call_action(
            ACTIONS["auto-fi-penetration"], conn,
            ns(company_id=env["company_id"]),
        )
        assert is_ok(result), result
        assert "total_delivered_deals" in result
        assert "penetration_pct" in result
        assert "total_fi_income" in result

    def test_status(self, conn, env):
        result = call_action(
            ACTIONS["status"], conn,
            ns(company_id=env["company_id"]),
        )
        assert is_ok(result), result
        assert result["skill"] == "automotiveclaw"
        assert result["total_tables"] == 14
        assert "record_counts" in result
