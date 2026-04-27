"""L1 tests for AutomotiveClaw deals + F&I domains.

Covers:
  - Deals: add, update, get, list, add-deal-trade, finalize, unwind
  - Buyer orders: add, get
  - Deal reports: gross, summary, salesperson-performance
  - F&I products: add, list, update-markup
  - Deal F&I: add, list, remove
  - F&I reports: penetration, income, product-performance
  - Payment calculator
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
    seed_vehicle, seed_deal, seed_account, seed_fiscal_year,
    seed_cost_center,
)

_mod = load_db_query()
ACTIONS = _mod.ACTIONS


# ── Deal Tests ───────────────────────────────────────────────────────────


class TestAddDeal:
    """auto-add-deal"""

    def test_add_deal_ok(self, conn, env):
        result = call_action(
            ACTIONS["auto-add-deal"], conn,
            ns(
                company_id=env["company_id"],
                vehicle_id=env["vehicle_id"],
                customer_id=env["core_customer_id"],
                selling_price="30000.00",
                salesperson="Bob Smith",
                deal_type="retail",
            ),
        )
        assert is_ok(result), result
        assert result["deal_status"] == "pending"
        assert result["deal_type"] == "retail"
        assert result["selling_price"] == "30000.00"

    def test_add_deal_with_trade(self, conn, env):
        result = call_action(
            ACTIONS["auto-add-deal"], conn,
            ns(
                company_id=env["company_id"],
                vehicle_id=env["vehicle_id"],
                customer_id=env["core_customer_id"],
                selling_price="35000.00",
                trade_allowance="10000.00",
                trade_payoff="5000.00",
                down_payment="3000.00",
                rebates="500.00",
            ),
        )
        assert is_ok(result), result
        # front_gross = selling_price - trade_allowance + trade_payoff - rebates
        # = 35000 - 10000 + 5000 - 500 = 29500
        assert result["front_gross"] == "29500.00"

    def test_add_deal_missing_vehicle(self, conn, env):
        result = call_action(
            ACTIONS["auto-add-deal"], conn,
            ns(
                company_id=env["company_id"],
                customer_id=env["core_customer_id"],
                selling_price="30000.00",
            ),
        )
        assert is_error(result)

    def test_add_deal_missing_customer(self, conn, env):
        result = call_action(
            ACTIONS["auto-add-deal"], conn,
            ns(
                company_id=env["company_id"],
                vehicle_id=env["vehicle_id"],
                selling_price="30000.00",
            ),
        )
        assert is_error(result)

    def test_add_deal_missing_price(self, conn, env):
        result = call_action(
            ACTIONS["auto-add-deal"], conn,
            ns(
                company_id=env["company_id"],
                vehicle_id=env["vehicle_id"],
                customer_id=env["core_customer_id"],
            ),
        )
        assert is_error(result)

    def test_add_deal_invalid_type(self, conn, env):
        result = call_action(
            ACTIONS["auto-add-deal"], conn,
            ns(
                company_id=env["company_id"],
                vehicle_id=env["vehicle_id"],
                customer_id=env["core_customer_id"],
                selling_price="30000.00",
                deal_type="invalid_type",
            ),
        )
        assert is_error(result)


class TestUpdateDeal:
    """auto-update-deal"""

    def test_update_deal_status(self, conn, env):
        deal_id = seed_deal(
            conn, env["vehicle_id"], env["core_customer_id"],
            env["company_id"],
        )
        result = call_action(
            ACTIONS["auto-update-deal"], conn,
            ns(deal_id=deal_id, deal_status="negotiating"),
        )
        assert is_ok(result), result
        assert "deal_status" in result["updated_fields"]

    def test_update_deal_salesperson(self, conn, env):
        deal_id = seed_deal(
            conn, env["vehicle_id"], env["core_customer_id"],
            env["company_id"],
        )
        result = call_action(
            ACTIONS["auto-update-deal"], conn,
            ns(deal_id=deal_id, salesperson="Alice Jones"),
        )
        assert is_ok(result), result
        assert "salesperson" in result["updated_fields"]

    def test_update_deal_no_fields(self, conn, env):
        deal_id = seed_deal(
            conn, env["vehicle_id"], env["core_customer_id"],
            env["company_id"],
        )
        result = call_action(
            ACTIONS["auto-update-deal"], conn,
            ns(deal_id=deal_id),
        )
        assert is_error(result)

    def test_update_deal_invalid_status(self, conn, env):
        deal_id = seed_deal(
            conn, env["vehicle_id"], env["core_customer_id"],
            env["company_id"],
        )
        result = call_action(
            ACTIONS["auto-update-deal"], conn,
            ns(deal_id=deal_id, deal_status="garbage"),
        )
        assert is_error(result)


class TestGetDeal:
    """auto-get-deal"""

    def test_get_deal_ok(self, conn, env):
        deal_id = seed_deal(
            conn, env["vehicle_id"], env["core_customer_id"],
            env["company_id"],
        )
        result = call_action(
            ACTIONS["auto-get-deal"], conn,
            ns(deal_id=deal_id),
        )
        assert is_ok(result), result
        assert result["id"] == deal_id
        assert "fi_products" in result
        assert result["buyer_order"] is None

    def test_get_deal_not_found(self, conn, env):
        result = call_action(
            ACTIONS["auto-get-deal"], conn,
            ns(deal_id="nonexistent"),
        )
        assert is_error(result)


class TestListDeals:
    """auto-list-deals"""

    def test_list_deals_by_company(self, conn, env):
        seed_deal(
            conn, env["vehicle_id"], env["core_customer_id"],
            env["company_id"],
        )
        result = call_action(
            ACTIONS["auto-list-deals"], conn,
            ns(company_id=env["company_id"]),
        )
        assert is_ok(result), result
        assert result["total_count"] >= 1

    def test_list_deals_by_status(self, conn, env):
        seed_deal(
            conn, env["vehicle_id"], env["core_customer_id"],
            env["company_id"],
        )
        result = call_action(
            ACTIONS["auto-list-deals"], conn,
            ns(company_id=env["company_id"], deal_status="pending"),
        )
        assert is_ok(result), result
        for row in result["rows"]:
            assert row["deal_status"] == "pending"


class TestDealTrade:
    """auto-add-deal-trade"""

    def test_add_deal_trade_ok(self, conn, env):
        deal_id = seed_deal(
            conn, env["vehicle_id"], env["core_customer_id"],
            env["company_id"],
        )
        trade_result = call_action(
            ACTIONS["auto-add-trade-in-appraisal"], conn,
            ns(
                company_id=env["company_id"],
                customer_id=env["core_customer_id"],
                vin="TRADE_DEAL_VIN_1",
                make="Ford", model="Escape", year="2019",
                offered_amount="12000.00",
                payoff_amount="3000.00",
            ),
        )
        assert is_ok(trade_result), trade_result
        trade_id = trade_result["id"]

        result = call_action(
            ACTIONS["auto-add-deal-trade"], conn,
            ns(deal_id=deal_id, trade_in_id=trade_id),
        )
        assert is_ok(result), result
        assert result["deal_id"] == deal_id
        assert result["trade_in_id"] == trade_id

    def test_add_deal_trade_missing_deal(self, conn, env):
        result = call_action(
            ACTIONS["auto-add-deal-trade"], conn,
            ns(trade_in_id="some-trade-id"),
        )
        assert is_error(result)


class TestFinalizeDeal:
    """auto-finalize-deal"""

    def test_finalize_deal_no_gl(self, conn, env):
        deal_id = seed_deal(
            conn, env["vehicle_id"], env["core_customer_id"],
            env["company_id"],
        )
        result = call_action(
            ACTIONS["auto-finalize-deal"], conn,
            ns(deal_id=deal_id),
        )
        assert is_ok(result), result
        assert result["deal_status"] == "delivered"
        assert result["id"] == deal_id

        # Verify vehicle is now sold
        veh = conn.execute(
            "SELECT vehicle_status FROM automotiveclaw_vehicle WHERE id = ?",
            (env["vehicle_id"],)
        ).fetchone()
        assert veh["vehicle_status"] == "sold"

    def test_finalize_deal_already_delivered(self, conn, env):
        deal_id = seed_deal(
            conn, env["vehicle_id"], env["core_customer_id"],
            env["company_id"],
        )
        call_action(ACTIONS["auto-finalize-deal"], conn, ns(deal_id=deal_id))
        result = call_action(
            ACTIONS["auto-finalize-deal"], conn,
            ns(deal_id=deal_id),
        )
        assert is_error(result)


class TestUnwindDeal:
    """auto-unwind-deal"""

    def test_unwind_deal_ok(self, conn, env):
        deal_id = seed_deal(
            conn, env["vehicle_id"], env["core_customer_id"],
            env["company_id"],
        )
        call_action(ACTIONS["auto-finalize-deal"], conn, ns(deal_id=deal_id))
        result = call_action(
            ACTIONS["auto-unwind-deal"], conn,
            ns(deal_id=deal_id),
        )
        assert is_ok(result), result
        assert result["deal_status"] == "unwound"

        # Verify vehicle is back to available
        veh = conn.execute(
            "SELECT vehicle_status FROM automotiveclaw_vehicle WHERE id = ?",
            (env["vehicle_id"],)
        ).fetchone()
        assert veh["vehicle_status"] == "available"

    def test_unwind_deal_already_unwound(self, conn, env):
        deal_id = seed_deal(
            conn, env["vehicle_id"], env["core_customer_id"],
            env["company_id"],
        )
        call_action(ACTIONS["auto-finalize-deal"], conn, ns(deal_id=deal_id))
        call_action(ACTIONS["auto-unwind-deal"], conn, ns(deal_id=deal_id))
        result = call_action(
            ACTIONS["auto-unwind-deal"], conn,
            ns(deal_id=deal_id),
        )
        assert is_error(result)


# ── Buyer Order Tests ────────────────────────────────────────────────────


class TestBuyerOrder:
    """auto-add-buyer-order + auto-get-buyer-order"""

    def test_add_buyer_order_ok(self, conn, env):
        deal_id = seed_deal(
            conn, env["vehicle_id"], env["core_customer_id"],
            env["company_id"],
        )
        result = call_action(
            ACTIONS["auto-add-buyer-order"], conn,
            ns(
                deal_id=deal_id,
                vehicle_price="30000.00",
                trade_value="5000.00",
                accessories="1500.00",
                fees="500.00",
                tax_amount="1950.00",
            ),
        )
        assert is_ok(result), result
        # subtotal = 30000 - 5000 + 1500 + 500 = 27000
        # total = 27000 + 1950 = 28950
        assert result["total"] == "28950.00"

    def test_add_buyer_order_duplicate(self, conn, env):
        deal_id = seed_deal(
            conn, env["vehicle_id"], env["core_customer_id"],
            env["company_id"],
        )
        call_action(
            ACTIONS["auto-add-buyer-order"], conn,
            ns(deal_id=deal_id, vehicle_price="30000.00"),
        )
        result = call_action(
            ACTIONS["auto-add-buyer-order"], conn,
            ns(deal_id=deal_id, vehicle_price="30000.00"),
        )
        assert is_error(result)

    def test_get_buyer_order_ok(self, conn, env):
        deal_id = seed_deal(
            conn, env["vehicle_id"], env["core_customer_id"],
            env["company_id"],
        )
        call_action(
            ACTIONS["auto-add-buyer-order"], conn,
            ns(deal_id=deal_id, vehicle_price="30000.00"),
        )
        result = call_action(
            ACTIONS["auto-get-buyer-order"], conn,
            ns(deal_id=deal_id),
        )
        assert is_ok(result), result
        assert result["deal_id"] == deal_id

    def test_get_buyer_order_not_found(self, conn, env):
        deal_id = seed_deal(
            conn, env["vehicle_id"], env["core_customer_id"],
            env["company_id"],
        )
        result = call_action(
            ACTIONS["auto-get-buyer-order"], conn,
            ns(deal_id=deal_id),
        )
        assert is_error(result)


# ── Deal Reports ─────────────────────────────────────────────────────────


class TestDealReports:
    """auto-deal-gross-report + auto-deal-summary + auto-salesperson-performance-report"""

    def test_deal_gross_report(self, conn, env):
        deal_id = seed_deal(
            conn, env["vehicle_id"], env["core_customer_id"],
            env["company_id"],
        )
        call_action(ACTIONS["auto-finalize-deal"], conn, ns(deal_id=deal_id))
        result = call_action(
            ACTIONS["auto-deal-gross-report"], conn,
            ns(company_id=env["company_id"]),
        )
        assert is_ok(result), result
        assert result["count"] >= 1

    def test_deal_summary(self, conn, env):
        seed_deal(
            conn, env["vehicle_id"], env["core_customer_id"],
            env["company_id"],
        )
        result = call_action(
            ACTIONS["auto-deal-summary"], conn,
            ns(company_id=env["company_id"]),
        )
        assert is_ok(result), result
        assert result["total_deals"] >= 1

    def test_salesperson_performance(self, conn, env):
        seed_deal(
            conn, env["vehicle_id"], env["core_customer_id"],
            env["company_id"],
        )
        result = call_action(
            ACTIONS["auto-salesperson-performance-report"], conn,
            ns(company_id=env["company_id"]),
        )
        assert is_ok(result), result
        assert result["count"] >= 1


# ── F&I Product Tests ────────────────────────────────────────────────────


class TestFIProducts:
    """auto-add-fi-product + auto-list-fi-products + auto-update-fi-markup"""

    def test_add_fi_product_ok(self, conn, env):
        result = call_action(
            ACTIONS["auto-add-fi-product"], conn,
            ns(
                company_id=env["company_id"],
                name="Extended Warranty",
                product_type="warranty",
                provider="WarrantyCo",
                base_cost="500.00",
                retail_price="1200.00",
                max_markup="700.00",
                term_months="36",
            ),
        )
        assert is_ok(result), result
        assert result["product_type"] == "warranty"
        assert result["is_active"] == 1

    def test_add_fi_product_missing_name(self, conn, env):
        result = call_action(
            ACTIONS["auto-add-fi-product"], conn,
            ns(company_id=env["company_id"]),
        )
        assert is_error(result)

    def test_add_fi_product_invalid_type(self, conn, env):
        result = call_action(
            ACTIONS["auto-add-fi-product"], conn,
            ns(
                company_id=env["company_id"],
                name="Bad Product",
                product_type="invalid",
            ),
        )
        assert is_error(result)

    def test_list_fi_products(self, conn, env):
        call_action(
            ACTIONS["auto-add-fi-product"], conn,
            ns(company_id=env["company_id"], name="GAP Insurance",
               product_type="gap"),
        )
        result = call_action(
            ACTIONS["auto-list-fi-products"], conn,
            ns(company_id=env["company_id"]),
        )
        assert is_ok(result), result
        assert result["total_count"] >= 1

    def test_update_fi_markup(self, conn, env):
        add_result = call_action(
            ACTIONS["auto-add-fi-product"], conn,
            ns(
                company_id=env["company_id"],
                name="Paint Protection",
                product_type="paint",
                retail_price="800.00",
            ),
        )
        assert is_ok(add_result), add_result
        prod_id = add_result["id"]

        result = call_action(
            ACTIONS["auto-update-fi-markup"], conn,
            ns(fi_product_id=prod_id, retail_price="900.00"),
        )
        assert is_ok(result), result
        assert "retail_price" in result["updated_fields"]

    def test_update_fi_markup_no_fields(self, conn, env):
        add_result = call_action(
            ACTIONS["auto-add-fi-product"], conn,
            ns(company_id=env["company_id"], name="Tire & Wheel",
               product_type="tire_wheel"),
        )
        prod_id = add_result["id"]
        result = call_action(
            ACTIONS["auto-update-fi-markup"], conn,
            ns(fi_product_id=prod_id),
        )
        assert is_error(result)


class TestDealFIProducts:
    """auto-add-deal-fi-product + auto-list-deal-fi-products + auto-remove-deal-fi-product"""

    def _create_fi_product(self, conn, env, name="Test Warranty"):
        r = call_action(
            ACTIONS["auto-add-fi-product"], conn,
            ns(
                company_id=env["company_id"],
                name=name, product_type="warranty",
                base_cost="400.00", retail_price="1000.00",
                term_months="24",
            ),
        )
        assert is_ok(r), r
        return r["id"]

    def test_add_deal_fi_product_ok(self, conn, env):
        deal_id = seed_deal(
            conn, env["vehicle_id"], env["core_customer_id"],
            env["company_id"],
        )
        prod_id = self._create_fi_product(conn, env)
        result = call_action(
            ACTIONS["auto-add-deal-fi-product"], conn,
            ns(
                deal_id=deal_id,
                fi_product_id=prod_id,
                company_id=env["company_id"],
            ),
        )
        assert is_ok(result), result
        # profit = retail_price - base_cost = 1000 - 400 = 600
        assert result["profit"] == "600.00"

    def test_add_deal_fi_product_custom_prices(self, conn, env):
        deal_id = seed_deal(
            conn, env["vehicle_id"], env["core_customer_id"],
            env["company_id"],
        )
        prod_id = self._create_fi_product(conn, env, "Custom Warranty")
        result = call_action(
            ACTIONS["auto-add-deal-fi-product"], conn,
            ns(
                deal_id=deal_id,
                fi_product_id=prod_id,
                company_id=env["company_id"],
                cost="350.00",
                selling_price="950.00",
            ),
        )
        assert is_ok(result), result
        assert result["profit"] == "600.00"

    def test_list_deal_fi_products(self, conn, env):
        deal_id = seed_deal(
            conn, env["vehicle_id"], env["core_customer_id"],
            env["company_id"],
        )
        prod_id = self._create_fi_product(conn, env, "List Test")
        call_action(
            ACTIONS["auto-add-deal-fi-product"], conn,
            ns(deal_id=deal_id, fi_product_id=prod_id,
               company_id=env["company_id"]),
        )
        result = call_action(
            ACTIONS["auto-list-deal-fi-products"], conn,
            ns(deal_id=deal_id),
        )
        assert is_ok(result), result
        assert result["count"] >= 1

    def test_remove_deal_fi_product(self, conn, env):
        deal_id = seed_deal(
            conn, env["vehicle_id"], env["core_customer_id"],
            env["company_id"],
        )
        prod_id = self._create_fi_product(conn, env, "Remove Test")
        add_result = call_action(
            ACTIONS["auto-add-deal-fi-product"], conn,
            ns(deal_id=deal_id, fi_product_id=prod_id,
               company_id=env["company_id"]),
        )
        dfp_id = add_result["id"]
        result = call_action(
            ACTIONS["auto-remove-deal-fi-product"], conn,
            ns(deal_fi_product_id=dfp_id),
        )
        assert is_ok(result), result
        assert result["deleted"] is True


class TestCalculatePayment:
    """auto-calculate-payment"""

    def test_calculate_payment_ok(self, conn, env):
        result = call_action(
            ACTIONS["auto-calculate-payment"], conn,
            ns(
                selling_price="30000.00",
                term_months="60",
                interest_rate="5.9",
                down_payment="3000.00",
                trade_value="5000.00",
            ),
        )
        assert is_ok(result), result
        assert result["financed_amount"] == "22000.00"
        assert result["term_months"] == 60
        assert float(result["monthly_payment"]) > 0

    def test_calculate_payment_zero_rate(self, conn, env):
        result = call_action(
            ACTIONS["auto-calculate-payment"], conn,
            ns(
                selling_price="20000.00",
                term_months="48",
                interest_rate="0",
            ),
        )
        assert is_ok(result), result
        assert result["total_interest"] == "0.00"
        # 20000 / 48 = 416.67
        assert float(result["monthly_payment"]) == pytest.approx(416.67, abs=0.01)

    def test_calculate_payment_fully_covered(self, conn, env):
        result = call_action(
            ACTIONS["auto-calculate-payment"], conn,
            ns(
                selling_price="20000.00",
                term_months="48",
                interest_rate="5.0",
                down_payment="10000.00",
                trade_value="10000.00",
            ),
        )
        assert is_ok(result), result
        assert result["monthly_payment"] == "0.00"

    def test_calculate_payment_missing_price(self, conn, env):
        result = call_action(
            ACTIONS["auto-calculate-payment"], conn,
            ns(term_months="60", interest_rate="5.0"),
        )
        assert is_error(result)

    def test_calculate_payment_missing_term(self, conn, env):
        result = call_action(
            ACTIONS["auto-calculate-payment"], conn,
            ns(selling_price="30000.00", interest_rate="5.0"),
        )
        assert is_error(result)


# ── F&I Reports ──────────────────────────────────────────────────────────


class TestFIReports:
    """auto-fi-penetration-report + auto-fi-income-report + auto-fi-product-performance"""

    def test_fi_penetration_report_empty(self, conn, env):
        result = call_action(
            ACTIONS["auto-fi-penetration-report"], conn,
            ns(company_id=env["company_id"]),
        )
        assert is_ok(result), result
        assert result["total_delivered_deals"] == 0
        assert result["penetration_pct"] == 0.0

    def test_fi_income_report(self, conn, env):
        result = call_action(
            ACTIONS["auto-fi-income-report"], conn,
            ns(company_id=env["company_id"]),
        )
        assert is_ok(result), result
        assert "rows" in result

    def test_fi_product_performance(self, conn, env):
        call_action(
            ACTIONS["auto-add-fi-product"], conn,
            ns(company_id=env["company_id"], name="Performance Test",
               product_type="gap"),
        )
        result = call_action(
            ACTIONS["auto-fi-product-performance"], conn,
            ns(company_id=env["company_id"]),
        )
        assert is_ok(result), result
        assert result["count"] >= 1
