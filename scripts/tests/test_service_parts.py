"""L1 tests for AutomotiveClaw service + parts domains.

Covers:
  - Repair orders: add, update, get, list, close
  - Service lines: add, list
  - Warranty claims: add, list
  - Service reports: efficiency
  - Parts: add, update, get, list
  - Parts orders: add, receive
  - Parts reports: velocity, inventory-value
"""
import pytest
import sys
import os

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

from auto_helpers import (
    call_action, ns, is_ok, is_error, load_db_query,
    seed_company, seed_customer, seed_naming_series,
    seed_vehicle, seed_repair_order, seed_supplier,
)

_mod = load_db_query()
ACTIONS = _mod.ACTIONS


# ── Repair Order Tests ───────────────────────────────────────────────────


class TestAddRepairOrder:
    """auto-add-repair-order"""

    def test_add_repair_order_minimal(self, conn, env):
        result = call_action(
            ACTIONS["auto-add-repair-order"], conn,
            ns(company_id=env["company_id"]),
        )
        assert is_ok(result), result
        assert result["ro_type"] == "customer_pay"
        assert result["ro_status"] == "open"

    def test_add_repair_order_full(self, conn, env):
        result = call_action(
            ACTIONS["auto-add-repair-order"], conn,
            ns(
                company_id=env["company_id"],
                customer_id=env["core_customer_id"],
                vehicle_vin="TESTVIN12345",
                advisor="Mike Advisor",
                technician="Jim Tech",
                ro_type="warranty",
                promised_date="2026-03-15",
            ),
        )
        assert is_ok(result), result
        assert result["ro_type"] == "warranty"

    def test_add_repair_order_invalid_type(self, conn, env):
        result = call_action(
            ACTIONS["auto-add-repair-order"], conn,
            ns(company_id=env["company_id"], ro_type="invalid_type"),
        )
        assert is_error(result)

    def test_add_repair_order_missing_company(self, conn, env):
        result = call_action(
            ACTIONS["auto-add-repair-order"], conn,
            ns(),
        )
        assert is_error(result)


class TestUpdateRepairOrder:
    """auto-update-repair-order"""

    def test_update_ro_status(self, conn, env):
        ro_id = seed_repair_order(conn, env["company_id"])
        result = call_action(
            ACTIONS["auto-update-repair-order"], conn,
            ns(repair_order_id=ro_id, ro_status="in_progress"),
        )
        assert is_ok(result), result
        assert "ro_status" in result["updated_fields"]

    def test_update_ro_technician(self, conn, env):
        ro_id = seed_repair_order(conn, env["company_id"])
        result = call_action(
            ACTIONS["auto-update-repair-order"], conn,
            ns(repair_order_id=ro_id, technician="New Tech"),
        )
        assert is_ok(result), result
        assert "technician" in result["updated_fields"]

    def test_update_ro_no_fields(self, conn, env):
        ro_id = seed_repair_order(conn, env["company_id"])
        result = call_action(
            ACTIONS["auto-update-repair-order"], conn,
            ns(repair_order_id=ro_id),
        )
        assert is_error(result)

    def test_update_ro_invalid_status(self, conn, env):
        ro_id = seed_repair_order(conn, env["company_id"])
        result = call_action(
            ACTIONS["auto-update-repair-order"], conn,
            ns(repair_order_id=ro_id, ro_status="garbage"),
        )
        assert is_error(result)

    def test_update_ro_not_found(self, conn, env):
        result = call_action(
            ACTIONS["auto-update-repair-order"], conn,
            ns(repair_order_id="nonexistent", ro_status="in_progress"),
        )
        assert is_error(result)


class TestGetRepairOrder:
    """auto-get-repair-order"""

    def test_get_repair_order_ok(self, conn, env):
        ro_id = seed_repair_order(conn, env["company_id"])
        result = call_action(
            ACTIONS["auto-get-repair-order"], conn,
            ns(repair_order_id=ro_id),
        )
        assert is_ok(result), result
        assert result["id"] == ro_id
        assert "service_lines" in result
        assert result["line_count"] == 0

    def test_get_repair_order_not_found(self, conn, env):
        result = call_action(
            ACTIONS["auto-get-repair-order"], conn,
            ns(repair_order_id="nonexistent"),
        )
        assert is_error(result)


class TestListRepairOrders:
    """auto-list-repair-orders"""

    def test_list_repair_orders_by_company(self, conn, env):
        seed_repair_order(conn, env["company_id"])
        result = call_action(
            ACTIONS["auto-list-repair-orders"], conn,
            ns(company_id=env["company_id"]),
        )
        assert is_ok(result), result
        assert result["total_count"] >= 1

    def test_list_repair_orders_by_status(self, conn, env):
        seed_repair_order(conn, env["company_id"])
        result = call_action(
            ACTIONS["auto-list-repair-orders"], conn,
            ns(company_id=env["company_id"], ro_status="open"),
        )
        assert is_ok(result), result
        for row in result["rows"]:
            assert row["ro_status"] == "open"


class TestCloseRepairOrder:
    """auto-close-repair-order"""

    def test_close_ro_ok(self, conn, env):
        ro_id = seed_repair_order(conn, env["company_id"])
        result = call_action(
            ACTIONS["auto-close-repair-order"], conn,
            ns(repair_order_id=ro_id),
        )
        assert is_ok(result), result
        assert result["ro_status"] == "completed"

    def test_close_ro_already_completed(self, conn, env):
        ro_id = seed_repair_order(conn, env["company_id"])
        call_action(
            ACTIONS["auto-close-repair-order"], conn,
            ns(repair_order_id=ro_id),
        )
        result = call_action(
            ACTIONS["auto-close-repair-order"], conn,
            ns(repair_order_id=ro_id),
        )
        assert is_error(result)


# ── Service Line Tests ───────────────────────────────────────────────────


class TestServiceLines:
    """auto-add-service-line + auto-list-service-lines"""

    def test_add_labor_line(self, conn, env):
        ro_id = seed_repair_order(conn, env["company_id"])
        result = call_action(
            ACTIONS["auto-add-service-line"], conn,
            ns(
                repair_order_id=ro_id,
                company_id=env["company_id"],
                line_type="labor",
                description="Oil change",
                quantity="1",
                rate="75.00",
            ),
        )
        assert is_ok(result), result
        assert result["line_type"] == "labor"
        assert result["amount"] == "75.00"

    def test_add_parts_line(self, conn, env):
        ro_id = seed_repair_order(conn, env["company_id"])
        result = call_action(
            ACTIONS["auto-add-service-line"], conn,
            ns(
                repair_order_id=ro_id,
                company_id=env["company_id"],
                line_type="parts",
                description="Oil filter",
                quantity="2",
                rate="15.00",
            ),
        )
        assert is_ok(result), result
        assert result["amount"] == "30.00"

    def test_add_line_invalid_type(self, conn, env):
        ro_id = seed_repair_order(conn, env["company_id"])
        result = call_action(
            ACTIONS["auto-add-service-line"], conn,
            ns(
                repair_order_id=ro_id,
                company_id=env["company_id"],
                line_type="invalid",
            ),
        )
        assert is_error(result)

    def test_add_line_recalculates_ro_totals(self, conn, env):
        ro_id = seed_repair_order(conn, env["company_id"])
        call_action(
            ACTIONS["auto-add-service-line"], conn,
            ns(
                repair_order_id=ro_id,
                company_id=env["company_id"],
                line_type="labor",
                description="Brake pad replacement",
                quantity="2",
                rate="100.00",
            ),
        )
        call_action(
            ACTIONS["auto-add-service-line"], conn,
            ns(
                repair_order_id=ro_id,
                company_id=env["company_id"],
                line_type="parts",
                description="Brake pads",
                quantity="1",
                rate="80.00",
            ),
        )
        ro = conn.execute(
            "SELECT labor_total, parts_total, total FROM automotiveclaw_repair_order WHERE id = ?",
            (ro_id,)
        ).fetchone()
        assert ro["labor_total"] == "200.00"
        assert ro["parts_total"] == "80.00"
        assert ro["total"] == "280.00"

    def test_list_service_lines(self, conn, env):
        ro_id = seed_repair_order(conn, env["company_id"])
        call_action(
            ACTIONS["auto-add-service-line"], conn,
            ns(
                repair_order_id=ro_id, company_id=env["company_id"],
                line_type="labor", description="Test", quantity="1", rate="50.00",
            ),
        )
        result = call_action(
            ACTIONS["auto-list-service-lines"], conn,
            ns(repair_order_id=ro_id),
        )
        assert is_ok(result), result
        assert result["count"] >= 1


# ── Warranty Claim Tests ─────────────────────────────────────────────────


class TestWarrantyClaims:
    """auto-add-warranty-claim + auto-list-warranty-claims"""

    def test_add_warranty_claim_ok(self, conn, env):
        ro_id = seed_repair_order(conn, env["company_id"])
        result = call_action(
            ACTIONS["auto-add-warranty-claim"], conn,
            ns(
                repair_order_id=ro_id,
                company_id=env["company_id"],
                claim_number="WC-001",
                claim_type="factory",
                labor_amount="200.00",
                parts_amount="150.00",
            ),
        )
        assert is_ok(result), result
        assert result["claim_type"] == "factory"
        assert result["claim_status"] == "submitted"
        assert result["total_amount"] == "350.00"

    def test_add_warranty_claim_invalid_type(self, conn, env):
        ro_id = seed_repair_order(conn, env["company_id"])
        result = call_action(
            ACTIONS["auto-add-warranty-claim"], conn,
            ns(
                repair_order_id=ro_id,
                company_id=env["company_id"],
                claim_type="invalid",
            ),
        )
        assert is_error(result)

    def test_list_warranty_claims(self, conn, env):
        ro_id = seed_repair_order(conn, env["company_id"])
        call_action(
            ACTIONS["auto-add-warranty-claim"], conn,
            ns(
                repair_order_id=ro_id,
                company_id=env["company_id"],
                claim_type="extended",
                labor_amount="100.00",
            ),
        )
        result = call_action(
            ACTIONS["auto-list-warranty-claims"], conn,
            ns(company_id=env["company_id"]),
        )
        assert is_ok(result), result
        assert result["total_count"] >= 1

    def test_list_warranty_claims_by_ro(self, conn, env):
        ro_id = seed_repair_order(conn, env["company_id"])
        call_action(
            ACTIONS["auto-add-warranty-claim"], conn,
            ns(
                repair_order_id=ro_id,
                company_id=env["company_id"],
                claim_type="goodwill",
            ),
        )
        result = call_action(
            ACTIONS["auto-list-warranty-claims"], conn,
            ns(repair_order_id=ro_id),
        )
        assert is_ok(result), result
        assert result["total_count"] >= 1


class TestServiceReports:
    """auto-service-efficiency-report"""

    def test_service_efficiency_report(self, conn, env):
        seed_repair_order(conn, env["company_id"])
        result = call_action(
            ACTIONS["auto-service-efficiency-report"], conn,
            ns(company_id=env["company_id"]),
        )
        assert is_ok(result), result
        assert result["total_repair_orders"] >= 1
        assert "by_status" in result
        assert "by_type" in result
        assert "total_revenue" in result


# ── Part Tests ───────────────────────────────────────────────────────────


class TestAddPart:
    """auto-add-part"""

    def test_add_part_ok(self, conn, env):
        result = call_action(
            ACTIONS["auto-add-part"], conn,
            ns(
                company_id=env["company_id"],
                part_number="BP-12345",
                description="Brake Pad Set",
                oem_number="OEM-BP-100",
                manufacturer="AcmeParts",
                list_price="45.00",
                cost="22.00",
                quantity_on_hand="100",
                reorder_point="10",
                bin_location="A1-R3-S5",
            ),
        )
        assert is_ok(result), result
        assert result["part_number"] == "BP-12345"
        assert result["quantity_on_hand"] == 100

    def test_add_part_minimal(self, conn, env):
        result = call_action(
            ACTIONS["auto-add-part"], conn,
            ns(company_id=env["company_id"], part_number="MIN-001"),
        )
        assert is_ok(result), result
        assert result["quantity_on_hand"] == 0

    def test_add_part_missing_number(self, conn, env):
        result = call_action(
            ACTIONS["auto-add-part"], conn,
            ns(company_id=env["company_id"]),
        )
        assert is_error(result)


class TestUpdatePart:
    """auto-update-part"""

    def test_update_part_price(self, conn, env):
        add = call_action(
            ACTIONS["auto-add-part"], conn,
            ns(company_id=env["company_id"], part_number="UPD-001",
               list_price="50.00"),
        )
        part_id = add["id"]
        result = call_action(
            ACTIONS["auto-update-part"], conn,
            ns(part_id=part_id, list_price="55.00"),
        )
        assert is_ok(result), result
        assert "list_price" in result["updated_fields"]

    def test_update_part_quantity(self, conn, env):
        add = call_action(
            ACTIONS["auto-add-part"], conn,
            ns(company_id=env["company_id"], part_number="UPD-002"),
        )
        part_id = add["id"]
        result = call_action(
            ACTIONS["auto-update-part"], conn,
            ns(part_id=part_id, quantity_on_hand="50"),
        )
        assert is_ok(result), result
        assert "quantity_on_hand" in result["updated_fields"]

    def test_update_part_no_fields(self, conn, env):
        add = call_action(
            ACTIONS["auto-add-part"], conn,
            ns(company_id=env["company_id"], part_number="UPD-003"),
        )
        part_id = add["id"]
        result = call_action(
            ACTIONS["auto-update-part"], conn,
            ns(part_id=part_id),
        )
        assert is_error(result)


class TestGetPart:
    """auto-get-part"""

    def test_get_part_ok(self, conn, env):
        add = call_action(
            ACTIONS["auto-add-part"], conn,
            ns(company_id=env["company_id"], part_number="GET-001"),
        )
        part_id = add["id"]
        result = call_action(
            ACTIONS["auto-get-part"], conn,
            ns(part_id=part_id),
        )
        assert is_ok(result), result
        assert result["part_number"] == "GET-001"

    def test_get_part_not_found(self, conn, env):
        result = call_action(
            ACTIONS["auto-get-part"], conn,
            ns(part_id="nonexistent"),
        )
        assert is_error(result)


class TestListParts:
    """auto-list-parts"""

    def test_list_parts(self, conn, env):
        call_action(
            ACTIONS["auto-add-part"], conn,
            ns(company_id=env["company_id"], part_number="LIST-001"),
        )
        result = call_action(
            ACTIONS["auto-list-parts"], conn,
            ns(company_id=env["company_id"]),
        )
        assert is_ok(result), result
        assert result["total_count"] >= 1

    def test_list_parts_search(self, conn, env):
        call_action(
            ACTIONS["auto-add-part"], conn,
            ns(company_id=env["company_id"], part_number="SEARCH-XYZ",
               description="Unique brake component"),
        )
        result = call_action(
            ACTIONS["auto-list-parts"], conn,
            ns(company_id=env["company_id"], search="SEARCH-XYZ"),
        )
        assert is_ok(result), result
        assert result["total_count"] >= 1


# ── Parts Order Tests ────────────────────────────────────────────────────


class TestPartsOrder:
    """auto-add-parts-order + auto-receive-parts-order"""

    def test_add_parts_order_ok(self, conn, env):
        result = call_action(
            ACTIONS["auto-add-parts-order"], conn,
            ns(
                company_id=env["company_id"],
                supplier_id=env["supplier_id"],
                order_date="2026-03-01",
                expected_date="2026-03-10",
                total_amount="1500.00",
            ),
        )
        assert is_ok(result), result
        assert result["order_status"] == "ordered"
        assert result["supplier_id"] == env["supplier_id"]

    def test_add_parts_order_missing_supplier(self, conn, env):
        result = call_action(
            ACTIONS["auto-add-parts-order"], conn,
            ns(company_id=env["company_id"]),
        )
        assert is_error(result)

    def test_add_parts_order_invalid_supplier(self, conn, env):
        result = call_action(
            ACTIONS["auto-add-parts-order"], conn,
            ns(company_id=env["company_id"], supplier_id="nonexistent"),
        )
        assert is_error(result)

    def test_receive_parts_order(self, conn, env):
        add = call_action(
            ACTIONS["auto-add-parts-order"], conn,
            ns(
                company_id=env["company_id"],
                supplier_id=env["supplier_id"],
                total_amount="500.00",
            ),
        )
        po_id = add["id"]
        result = call_action(
            ACTIONS["auto-receive-parts-order"], conn,
            ns(parts_order_id=po_id),
        )
        assert is_ok(result), result
        assert result["order_status"] == "received"

    def test_receive_parts_order_already_received(self, conn, env):
        add = call_action(
            ACTIONS["auto-add-parts-order"], conn,
            ns(
                company_id=env["company_id"],
                supplier_id=env["supplier_id"],
            ),
        )
        po_id = add["id"]
        call_action(
            ACTIONS["auto-receive-parts-order"], conn,
            ns(parts_order_id=po_id),
        )
        result = call_action(
            ACTIONS["auto-receive-parts-order"], conn,
            ns(parts_order_id=po_id),
        )
        assert is_error(result)


# ── Parts Reports ────────────────────────────────────────────────────────


class TestPartsReports:
    """auto-parts-velocity-report + auto-parts-inventory-value"""

    def test_parts_velocity_report(self, conn, env):
        call_action(
            ACTIONS["auto-add-part"], conn,
            ns(company_id=env["company_id"], part_number="VEL-001",
               cost="10.00", quantity_on_hand="50"),
        )
        result = call_action(
            ACTIONS["auto-parts-velocity-report"], conn,
            ns(company_id=env["company_id"]),
        )
        assert is_ok(result), result
        assert result["count"] >= 1

    def test_parts_inventory_value(self, conn, env):
        call_action(
            ACTIONS["auto-add-part"], conn,
            ns(company_id=env["company_id"], part_number="VAL-001",
               cost="25.00", quantity_on_hand="20"),
        )
        result = call_action(
            ACTIONS["auto-parts-inventory-value"], conn,
            ns(company_id=env["company_id"]),
        )
        assert is_ok(result), result
        assert result["total_active_parts"] >= 1
        assert float(result["total_inventory_value"]) > 0

    def test_parts_inventory_below_reorder(self, conn, env):
        call_action(
            ACTIONS["auto-add-part"], conn,
            ns(company_id=env["company_id"], part_number="LOW-001",
               cost="10.00", quantity_on_hand="2", reorder_point="10"),
        )
        result = call_action(
            ACTIONS["auto-parts-inventory-value"], conn,
            ns(company_id=env["company_id"]),
        )
        assert is_ok(result), result
        assert result["parts_below_reorder"] >= 1
