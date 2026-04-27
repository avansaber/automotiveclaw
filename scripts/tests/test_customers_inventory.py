"""L1 tests for AutomotiveClaw customers + inventory domains.

Covers:
  - Customer extension: get, update, list, vehicle-history, service-history
  - Vehicles: add, update, get, list, mark-sold, vin-lookup
  - Vehicle photos: add, list
  - Trade-in appraisals: add, list
  - Inventory reports: aging, summary

Note: auto-add-customer is NOT tested here because it calls cross_skill
(subprocess). Customer extension rows are seeded directly.
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

# Load ACTIONS dict from db_query.py
_mod = load_db_query()
ACTIONS = _mod.ACTIONS


# ── Customer Extension Tests ─────────────────────────────────────────────


class TestGetCustomer:
    """auto-get-customer"""

    def test_get_customer_ok(self, conn, env):
        result = call_action(
            ACTIONS["auto-get-customer"], conn,
            ns(customer_id=env["customer_ext_id"]),
        )
        assert is_ok(result), result
        assert result["id"] == env["customer_ext_id"]
        assert result["customer_type"] == "individual"
        assert result["name"] == "John Doe"

    def test_get_customer_missing_id(self, conn, env):
        result = call_action(
            ACTIONS["auto-get-customer"], conn,
            ns(customer_id=None),
        )
        assert is_error(result)

    def test_get_customer_not_found(self, conn, env):
        result = call_action(
            ACTIONS["auto-get-customer"], conn,
            ns(customer_id="nonexistent-id"),
        )
        assert is_error(result)


class TestUpdateCustomer:
    """auto-update-customer"""

    def test_update_customer_type(self, conn, env):
        result = call_action(
            ACTIONS["auto-update-customer"], conn,
            ns(customer_id=env["customer_ext_id"], customer_type="fleet"),
        )
        assert is_ok(result), result
        assert "customer_type" in result["updated_fields"]

    def test_update_customer_drivers_license(self, conn, env):
        result = call_action(
            ACTIONS["auto-update-customer"], conn,
            ns(customer_id=env["customer_ext_id"], drivers_license="DL12345"),
        )
        assert is_ok(result), result
        assert "drivers_license" in result["updated_fields"]

    def test_update_customer_name_via_core(self, conn, env):
        result = call_action(
            ACTIONS["auto-update-customer"], conn,
            ns(customer_id=env["customer_ext_id"], name="Jane Doe"),
        )
        assert is_ok(result), result
        assert "name" in result["updated_fields"]

    def test_update_customer_no_fields(self, conn, env):
        result = call_action(
            ACTIONS["auto-update-customer"], conn,
            ns(customer_id=env["customer_ext_id"]),
        )
        assert is_error(result)

    def test_update_customer_not_found(self, conn, env):
        result = call_action(
            ACTIONS["auto-update-customer"], conn,
            ns(customer_id="nonexistent-id", name="Nobody"),
        )
        assert is_error(result)


class TestListCustomers:
    """auto-list-customers"""

    def test_list_customers_by_company(self, conn, env):
        result = call_action(
            ACTIONS["auto-list-customers"], conn,
            ns(company_id=env["company_id"]),
        )
        assert is_ok(result), result
        assert result["total_count"] >= 1

    def test_list_customers_by_type(self, conn, env):
        result = call_action(
            ACTIONS["auto-list-customers"], conn,
            ns(company_id=env["company_id"], customer_type="individual"),
        )
        assert is_ok(result), result
        for row in result["rows"]:
            assert row["customer_type"] == "individual"

    def test_list_customers_empty(self, conn, env):
        cid2 = seed_company(conn, "Empty Co", "EC")
        result = call_action(
            ACTIONS["auto-list-customers"], conn,
            ns(company_id=cid2),
        )
        assert is_ok(result), result
        assert result["total_count"] == 0


class TestCustomerHistory:
    """auto-customer-vehicle-history + auto-customer-service-history"""

    def test_vehicle_history_empty(self, conn, env):
        result = call_action(
            ACTIONS["auto-customer-vehicle-history"], conn,
            ns(customer_id=env["customer_ext_id"]),
        )
        assert is_ok(result), result
        assert result["count"] == 0

    def test_vehicle_history_with_deal(self, conn, env):
        seed_deal(
            conn, env["vehicle_id"], env["core_customer_id"],
            env["company_id"], "30000.00",
        )
        result = call_action(
            ACTIONS["auto-customer-vehicle-history"], conn,
            ns(customer_id=env["customer_ext_id"]),
        )
        assert is_ok(result), result
        assert result["count"] >= 1

    def test_service_history_empty(self, conn, env):
        result = call_action(
            ACTIONS["auto-customer-service-history"], conn,
            ns(customer_id=env["customer_ext_id"]),
        )
        assert is_ok(result), result
        assert result["count"] == 0

    def test_service_history_with_ro(self, conn, env):
        seed_repair_order(
            conn, env["company_id"],
            customer_id=env["core_customer_id"],
            vehicle_vin="TESTVIN123",
        )
        result = call_action(
            ACTIONS["auto-customer-service-history"], conn,
            ns(customer_id=env["customer_ext_id"]),
        )
        assert is_ok(result), result
        assert result["count"] >= 1

    def test_vehicle_history_missing_id(self, conn, env):
        result = call_action(
            ACTIONS["auto-customer-vehicle-history"], conn,
            ns(customer_id=None),
        )
        assert is_error(result)


# ── Vehicle Tests ────────────────────────────────────────────────────────


class TestAddVehicle:
    """auto-add-vehicle"""

    def test_add_vehicle_minimal(self, conn, env):
        result = call_action(
            ACTIONS["auto-add-vehicle"], conn,
            ns(company_id=env["company_id"], make="Honda", model="Civic"),
        )
        assert is_ok(result), result
        assert result["make"] == "Honda"
        assert result["model"] == "Civic"
        assert result["vehicle_status"] == "available"
        assert result["id"]

    def test_add_vehicle_full(self, conn, env):
        result = call_action(
            ACTIONS["auto-add-vehicle"], conn,
            ns(
                company_id=env["company_id"],
                make="BMW", model="X5", year="2025", vin="WBAPH5C55BA123456",
                trim="xDrive40i", color_exterior="Black",
                color_interior="Tan", mileage="15000",
                vehicle_condition="used", body_style="SUV",
                engine="3.0L I6", transmission="automatic",
                drivetrain="awd", msrp="65000.00",
                invoice_price="58000.00", selling_price="62000.00",
                internet_price="61000.00", lot_location="Lot A",
            ),
        )
        assert is_ok(result), result
        assert result["vin"] == "WBAPH5C55BA123456"

    def test_add_vehicle_missing_make(self, conn, env):
        result = call_action(
            ACTIONS["auto-add-vehicle"], conn,
            ns(company_id=env["company_id"], model="Civic"),
        )
        assert is_error(result)

    def test_add_vehicle_missing_model(self, conn, env):
        result = call_action(
            ACTIONS["auto-add-vehicle"], conn,
            ns(company_id=env["company_id"], make="Honda"),
        )
        assert is_error(result)

    def test_add_vehicle_missing_company(self, conn, env):
        result = call_action(
            ACTIONS["auto-add-vehicle"], conn,
            ns(make="Honda", model="Civic"),
        )
        assert is_error(result)

    def test_add_vehicle_duplicate_vin(self, conn, env):
        vin = "UNIQUE_VIN_123456789"
        call_action(
            ACTIONS["auto-add-vehicle"], conn,
            ns(company_id=env["company_id"], make="Toyota", model="Corolla", vin=vin),
        )
        result = call_action(
            ACTIONS["auto-add-vehicle"], conn,
            ns(company_id=env["company_id"], make="Toyota", model="Camry", vin=vin),
        )
        assert is_error(result)

    def test_add_vehicle_invalid_condition(self, conn, env):
        result = call_action(
            ACTIONS["auto-add-vehicle"], conn,
            ns(company_id=env["company_id"], make="Honda", model="Civic",
               vehicle_condition="garbage"),
        )
        assert is_error(result)


class TestGetVehicle:
    """auto-get-vehicle"""

    def test_get_vehicle_ok(self, conn, env):
        result = call_action(
            ACTIONS["auto-get-vehicle"], conn,
            ns(vehicle_id=env["vehicle_id"]),
        )
        assert is_ok(result), result
        assert result["make"] == "Toyota"

    def test_get_vehicle_not_found(self, conn, env):
        result = call_action(
            ACTIONS["auto-get-vehicle"], conn,
            ns(vehicle_id="nonexistent"),
        )
        assert is_error(result)


class TestUpdateVehicle:
    """auto-update-vehicle"""

    def test_update_vehicle_price(self, conn, env):
        result = call_action(
            ACTIONS["auto-update-vehicle"], conn,
            ns(vehicle_id=env["vehicle_id"], selling_price="28000.00"),
        )
        assert is_ok(result), result
        assert "selling_price" in result["updated_fields"]

    def test_update_vehicle_location(self, conn, env):
        result = call_action(
            ACTIONS["auto-update-vehicle"], conn,
            ns(vehicle_id=env["vehicle_id"], lot_location="Lot B"),
        )
        assert is_ok(result), result
        assert "lot_location" in result["updated_fields"]

    def test_update_vehicle_no_fields(self, conn, env):
        result = call_action(
            ACTIONS["auto-update-vehicle"], conn,
            ns(vehicle_id=env["vehicle_id"]),
        )
        assert is_error(result)


class TestListVehicles:
    """auto-list-vehicles"""

    def test_list_vehicles_by_company(self, conn, env):
        result = call_action(
            ACTIONS["auto-list-vehicles"], conn,
            ns(company_id=env["company_id"]),
        )
        assert is_ok(result), result
        assert result["total_count"] >= 1

    def test_list_vehicles_by_make(self, conn, env):
        result = call_action(
            ACTIONS["auto-list-vehicles"], conn,
            ns(company_id=env["company_id"], make="Toyota"),
        )
        assert is_ok(result), result
        for row in result["rows"]:
            assert row["make"] == "Toyota"

    def test_list_vehicles_by_status(self, conn, env):
        result = call_action(
            ACTIONS["auto-list-vehicles"], conn,
            ns(company_id=env["company_id"], vehicle_status="available"),
        )
        assert is_ok(result), result
        for row in result["rows"]:
            assert row["vehicle_status"] == "available"


class TestMarkVehicleSold:
    """auto-mark-vehicle-sold"""

    def test_mark_sold_ok(self, conn, env):
        result = call_action(
            ACTIONS["auto-mark-vehicle-sold"], conn,
            ns(vehicle_id=env["vehicle_id"]),
        )
        assert is_ok(result), result
        assert result["vehicle_status"] == "sold"

    def test_mark_sold_already_sold(self, conn, env):
        call_action(
            ACTIONS["auto-mark-vehicle-sold"], conn,
            ns(vehicle_id=env["vehicle_id"]),
        )
        result = call_action(
            ACTIONS["auto-mark-vehicle-sold"], conn,
            ns(vehicle_id=env["vehicle_id"]),
        )
        assert is_error(result)


class TestVinLookup:
    """auto-vin-lookup"""

    def test_vin_lookup_found(self, conn, env):
        row = conn.execute(
            "SELECT vin FROM automotiveclaw_vehicle WHERE id = ?",
            (env["vehicle_id"],)
        ).fetchone()
        vin = row["vin"]

        result = call_action(
            ACTIONS["auto-vin-lookup"], conn,
            ns(vin=vin),
        )
        assert is_ok(result), result
        assert result["id"] == env["vehicle_id"]

    def test_vin_lookup_not_found(self, conn, env):
        result = call_action(
            ACTIONS["auto-vin-lookup"], conn,
            ns(vin="DOES_NOT_EXIST_12345"),
        )
        assert is_error(result)

    def test_vin_lookup_missing(self, conn, env):
        result = call_action(
            ACTIONS["auto-vin-lookup"], conn,
            ns(vin=None),
        )
        assert is_error(result)


# ── Vehicle Photo Tests ──────────────────────────────────────────────────


class TestVehiclePhotos:
    """auto-add-vehicle-photo + auto-list-vehicle-photos"""

    def test_add_photo_ok(self, conn, env):
        result = call_action(
            ACTIONS["auto-add-vehicle-photo"], conn,
            ns(
                vehicle_id=env["vehicle_id"],
                company_id=env["company_id"],
                photo_url="https://example.com/photo1.jpg",
                photo_order="1",
                caption="Front view",
            ),
        )
        assert is_ok(result), result
        assert result["photo_url"] == "https://example.com/photo1.jpg"

    def test_add_photo_missing_url(self, conn, env):
        result = call_action(
            ACTIONS["auto-add-vehicle-photo"], conn,
            ns(vehicle_id=env["vehicle_id"], company_id=env["company_id"]),
        )
        assert is_error(result)

    def test_list_photos(self, conn, env):
        for i in range(2):
            call_action(
                ACTIONS["auto-add-vehicle-photo"], conn,
                ns(
                    vehicle_id=env["vehicle_id"],
                    company_id=env["company_id"],
                    photo_url=f"https://example.com/photo{i}.jpg",
                    photo_order=str(i),
                ),
            )
        result = call_action(
            ACTIONS["auto-list-vehicle-photos"], conn,
            ns(vehicle_id=env["vehicle_id"]),
        )
        assert is_ok(result), result
        assert result["count"] == 2


# ── Trade-In Tests ───────────────────────────────────────────────────────


class TestTradeInAppraisals:
    """auto-add-trade-in-appraisal + auto-list-trade-in-appraisals"""

    def test_add_trade_in_ok(self, conn, env):
        result = call_action(
            ACTIONS["auto-add-trade-in-appraisal"], conn,
            ns(
                company_id=env["company_id"],
                customer_id=env["core_customer_id"],
                vin="TRADE_VIN_123456789",
                make="Ford",
                model="F-150",
                year="2020",
                mileage="45000",
                trade_condition="good",
                offered_amount="18000.00",
                acv="17000.00",
                payoff_amount="5000.00",
            ),
        )
        assert is_ok(result), result
        assert result["trade_status"] == "pending"
        assert result["trade_condition"] == "good"

    def test_add_trade_in_missing_vin(self, conn, env):
        result = call_action(
            ACTIONS["auto-add-trade-in-appraisal"], conn,
            ns(
                company_id=env["company_id"],
                customer_id=env["core_customer_id"],
                make="Ford", model="F-150",
            ),
        )
        assert is_error(result)

    def test_add_trade_in_missing_customer(self, conn, env):
        result = call_action(
            ACTIONS["auto-add-trade-in-appraisal"], conn,
            ns(
                company_id=env["company_id"],
                vin="TRADE_VIN_2", make="Ford", model="F-150",
            ),
        )
        assert is_error(result)

    def test_list_trade_ins(self, conn, env):
        call_action(
            ACTIONS["auto-add-trade-in-appraisal"], conn,
            ns(
                company_id=env["company_id"],
                customer_id=env["core_customer_id"],
                vin="TRADE_VIN_LIST_1",
                make="Chevrolet", model="Silverado", year="2019",
            ),
        )
        result = call_action(
            ACTIONS["auto-list-trade-in-appraisals"], conn,
            ns(company_id=env["company_id"]),
        )
        assert is_ok(result), result
        assert result["total_count"] >= 1


# ── Inventory Report Tests ───────────────────────────────────────────────


class TestInventoryReports:
    """auto-inventory-aging-report + auto-inventory-summary"""

    def test_inventory_aging_report(self, conn, env):
        result = call_action(
            ACTIONS["auto-inventory-aging-report"], conn,
            ns(company_id=env["company_id"]),
        )
        assert is_ok(result), result
        assert result["count"] >= 1

    def test_inventory_summary(self, conn, env):
        result = call_action(
            ACTIONS["auto-inventory-summary"], conn,
            ns(company_id=env["company_id"]),
        )
        assert is_ok(result), result
        assert result["total_vehicles"] >= 1
        assert "by_status" in result
        assert "by_condition" in result
