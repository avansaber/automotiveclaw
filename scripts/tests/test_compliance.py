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
from decimal import Decimal

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


def _snapshot_report_state(conn):
    """Full dump of the deal/F&I rows plus the ledger entry count."""
    tables = ("automotiveclaw_deal", "automotiveclaw_deal_fi_product",
              "automotiveclaw_fi_product", "automotiveclaw_vehicle")
    snapshot = {}
    for table in tables:
        rows = conn.execute(
            f"SELECT * FROM {table} ORDER BY id").fetchall()
        snapshot[table] = [dict(row) for row in rows]
    snapshot["gl_entry_count"] = conn.execute(
        "SELECT COUNT(*) FROM gl_entry").fetchone()[0]
    return snapshot


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
        # Behavioural (was routability-only: asserted only that the keys
        # exist, on an empty database). Seeds two delivered deals (one with
        # F&I, one without) plus one pending deal carrying F&I, reads the
        # stored rows back independently, and proves the report aggregates
        # exactly those rows.
        # FINDING (not fixed per task rules): total_fi_income sums F&I profit
        # over ALL of the company's deals with no deal_status filter, while
        # total_delivered_deals/deals_with_fi count only delivered deals --
        # so the "1695.00" below deliberately includes the 500.00 sold on the
        # still-pending deal. See CHANGES.md.
        # NOTE: auto-fi-penetration is a read-only aggregate -- it never
        # reaches the ledger, so no debit/credit legs exist to assert here.
        product = call_action(
            ACTIONS["auto-add-fi-product"], conn,
            ns(company_id=env["company_id"], name="GAP Plus",
               product_type="gap", base_cost="800.00",
               retail_price="1995.00"),
        )
        assert is_ok(product), product

        deal_with_fi = seed_deal(
            conn, env["vehicle_id"], env["core_customer_id"],
            env["company_id"], selling_price="30000.00",
        )
        sale_a = call_action(
            ACTIONS["auto-add-deal-fi-product"], conn,
            ns(deal_id=deal_with_fi, fi_product_id=product["id"],
               company_id=env["company_id"], cost="800.00",
               selling_price="1995.00"),
        )
        assert is_ok(sale_a), sale_a
        assert is_ok(call_action(
            ACTIONS["auto-finalize-deal"], conn,
            ns(deal_id=deal_with_fi)),)

        bare_vehicle = seed_vehicle(conn, env["company_id"])
        deal_without_fi = seed_deal(
            conn, bare_vehicle, env["core_customer_id"],
            env["company_id"], selling_price="25000.00",
        )
        assert is_ok(call_action(
            ACTIONS["auto-finalize-deal"], conn,
            ns(deal_id=deal_without_fi)),)

        pending_vehicle = seed_vehicle(conn, env["company_id"])
        pending_deal = seed_deal(
            conn, pending_vehicle, env["core_customer_id"],
            env["company_id"], selling_price="20000.00",
        )
        sale_c = call_action(
            ACTIONS["auto-add-deal-fi-product"], conn,
            ns(deal_id=pending_deal, fi_product_id=product["id"],
               company_id=env["company_id"], cost="100.00",
               selling_price="600.00"),
        )
        assert is_ok(sale_c), sale_c

        stored_profits = {
            row["id"]: Decimal(str(row["profit"]))
            for row in conn.execute(
                "SELECT id, profit FROM automotiveclaw_deal_fi_product"
            ).fetchall()
        }
        assert stored_profits[sale_a["id"]] == Decimal("1195.00")
        assert stored_profits[sale_c["id"]] == Decimal("500.00")

        delivered = conn.execute(
            "SELECT id FROM automotiveclaw_deal "
            "WHERE company_id = ? AND deal_status = 'delivered'",
            (env["company_id"],),
        ).fetchall()
        assert {row["id"] for row in delivered} == {
            deal_with_fi, deal_without_fi}

        delivered_with_fi = conn.execute(
            "SELECT DISTINCT d.id FROM automotiveclaw_deal d "
            "JOIN automotiveclaw_deal_fi_product dfp ON d.id = dfp.deal_id "
            "WHERE d.company_id = ? AND d.deal_status = 'delivered'",
            (env["company_id"],),
        ).fetchall()
        assert [row["id"] for row in delivered_with_fi] == [deal_with_fi]

        stored_income = conn.execute(
            "SELECT COALESCE(SUM(CAST(dfp.profit AS NUMERIC)), 0) "
            "FROM automotiveclaw_deal_fi_product dfp "
            "JOIN automotiveclaw_deal d ON dfp.deal_id = d.id "
            "WHERE d.company_id = ?",
            (env["company_id"],),
        ).fetchone()[0]
        assert Decimal(str(stored_income)) == Decimal("1695.00")

        result = call_action(
            ACTIONS["auto-fi-penetration"], conn,
            ns(company_id=env["company_id"]),
        )
        assert is_ok(result), result
        assert result["total_delivered_deals"] == 2
        assert result["deals_with_fi"] == 1
        assert result["penetration_pct"] == 50.0
        assert result["total_fi_income"] == "1695.00"
        assert Decimal(str(result["total_fi_income"])) == Decimal(
            str(stored_income))

        # The report must not move any deal: delivered stay delivered, the
        # open deal stays open with its F&I row intact.
        statuses = {
            row["id"]: row["deal_status"]
            for row in conn.execute(
                "SELECT id, deal_status FROM automotiveclaw_deal "
                "WHERE company_id = ?", (env["company_id"],)).fetchall()
        }
        assert statuses[deal_with_fi] == "delivered"
        assert statuses[deal_without_fi] == "delivered"
        assert statuses[pending_deal] == "pending"
        assert conn.execute(
            "SELECT COUNT(*) FROM automotiveclaw_deal_fi_product "
            "WHERE deal_id = ?", (pending_deal,)).fetchone()[0] == 1

    def test_fi_penetration_is_read_only(self, conn, env):
        # A report must change nothing: snapshot the owned tables and the
        # ledger entry count, run the report, and require byte-identical state.
        product = call_action(
            ACTIONS["auto-add-fi-product"], conn,
            ns(company_id=env["company_id"], name="GAP Readonly",
               product_type="gap", base_cost="800.00",
               retail_price="1995.00"),
        )
        assert is_ok(product), product
        sale = call_action(
            ACTIONS["auto-add-deal-fi-product"], conn,
            ns(deal_id=seed_deal(conn, env["vehicle_id"],
                                 env["core_customer_id"], env["company_id"]),
               fi_product_id=product["id"], company_id=env["company_id"],
               cost="800.00", selling_price="1995.00"),
        )
        assert is_ok(sale), sale

        before = _snapshot_report_state(conn)
        result = call_action(
            ACTIONS["auto-fi-penetration"], conn,
            ns(company_id=env["company_id"]),
        )
        assert is_ok(result), result
        assert result["total_delivered_deals"] == 0
        assert result["deals_with_fi"] == 0
        assert result["penetration_pct"] == 0.0
        assert Decimal(str(result["total_fi_income"])) == Decimal("1195.00")
        assert _snapshot_report_state(conn) == before

    def test_fi_penetration_refuses_unknown_company_without_writing(
            self, conn, env):
        # Refusal case: an unknown company is refused with a truthful message
        # and the database is byte-identical afterwards. A refusal that
        # half-writes is worse than no refusal.
        product = call_action(
            ACTIONS["auto-add-fi-product"], conn,
            ns(company_id=env["company_id"], name="GAP Refusal",
               product_type="gap", base_cost="800.00",
               retail_price="1995.00"),
        )
        assert is_ok(product), product
        sale = call_action(
            ACTIONS["auto-add-deal-fi-product"], conn,
            ns(deal_id=seed_deal(conn, env["vehicle_id"],
                                 env["core_customer_id"], env["company_id"]),
               fi_product_id=product["id"], company_id=env["company_id"],
               cost="800.00", selling_price="1995.00"),
        )
        assert is_ok(sale), sale

        before = _snapshot_report_state(conn)
        result = call_action(
            ACTIONS["auto-fi-penetration"], conn,
            ns(company_id="no-such-company"),
        )
        assert is_error(result), result
        assert "Company no-such-company not found" in (
            result.get("message", "") + result.get("error", ""))
        assert _snapshot_report_state(conn) == before

        missing = call_action(
            ACTIONS["auto-fi-penetration"], conn,
            ns(company_id=None),
        )
        assert is_error(missing), missing
        assert "--company-id is required" in (
            missing.get("message", "") + missing.get("error", ""))
        assert _snapshot_report_state(conn) == before

    def test_status(self, conn, env):
        result = call_action(
            ACTIONS["status"], conn,
            ns(company_id=env["company_id"]),
        )
        assert is_ok(result), result
        assert result["skill"] == "automotiveclaw"
        assert result["total_tables"] == 14
        assert "record_counts" in result
