"""A finalized vehicle sale posts its ledger, or the finalize is refused.

finalize-deal posted under a voucher type the GL registry does not hold and
swallowed the resulting error, so every deal with accounts supplied closed as
delivered with no ledger entries at all. It now posts under the registered
journal_entry type, and a posting failure rolls the whole finalize back and
says why. unwind-deal reverses under the same type.
"""
import os
import sys
from datetime import date
from decimal import Decimal

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

from auto_helpers import (call_action, is_error, is_ok, load_db_query, ns,  # noqa: E402
                          seed_deal, seed_fiscal_year)

ACTIONS = load_db_query().ACTIONS


def _fiscal_year_for_today(conn, env):
    year = date.today().year
    if year != 2026:
        seed_fiscal_year(conn, env["company_id"], start=f"{year}-01-01",
                         end=f"{year}-12-31")


def _gl(conn, deal_id):
    return conn.execute(
        "SELECT account_id, debit, credit, is_cancelled FROM gl_entry "
        "WHERE voucher_type = 'journal_entry' AND voucher_id = ?",
        (deal_id,)).fetchall()


def _finalize(conn, env, deal_id, **accounts):
    return call_action(ACTIONS["auto-finalize-deal"], conn, ns(
        deal_id=deal_id, cost_center_id=env["cost_center_id"], **accounts))


def test_finalize_with_accounts_posts_a_balanced_sale(conn, env):
    _fiscal_year_for_today(conn, env)
    deal_id = seed_deal(conn, env["vehicle_id"], env["core_customer_id"],
                        env["company_id"], selling_price="30000.00")
    r = _finalize(conn, env, deal_id, receivable_account_id=env["ar"],
                  revenue_account_id=env["revenue"])
    assert is_ok(r), r
    assert r.get("gl_posted") is True
    rows = _gl(conn, deal_id)
    debit = sum((Decimal(x["debit"]) for x in rows), Decimal("0"))
    credit = sum((Decimal(x["credit"]) for x in rows), Decimal("0"))
    assert debit == credit == Decimal("30000.00")
    by_account = {x["account_id"]: (x["debit"], x["credit"]) for x in rows}
    assert Decimal(by_account[env["ar"]][0]) == Decimal("30000.00")
    assert Decimal(by_account[env["revenue"]][1]) == Decimal("30000.00")


def test_a_posting_failure_refuses_the_finalize_and_leaves_the_deal_open(conn, env):
    _fiscal_year_for_today(conn, env)
    deal_id = seed_deal(conn, env["vehicle_id"], env["core_customer_id"],
                        env["company_id"], selling_price="30000.00")
    r = _finalize(conn, env, deal_id, receivable_account_id=env["ar"],
                  revenue_account_id="no-such-account")
    assert is_error(r), r
    assert "GL posting failed" in (r.get("message", "") + r.get("error", ""))
    deal = conn.execute("SELECT deal_status FROM automotiveclaw_deal WHERE id = ?",
                        (deal_id,)).fetchone()
    assert deal["deal_status"] == "pending"
    veh = conn.execute("SELECT vehicle_status FROM automotiveclaw_vehicle WHERE id = ?",
                       (env["vehicle_id"],)).fetchone()
    assert veh["vehicle_status"] == "available"
    assert _gl(conn, deal_id) == []


def test_unwind_reverses_the_sale_ledger(conn, env):
    _fiscal_year_for_today(conn, env)
    deal_id = seed_deal(conn, env["vehicle_id"], env["core_customer_id"],
                        env["company_id"], selling_price="30000.00")
    assert is_ok(_finalize(conn, env, deal_id, receivable_account_id=env["ar"],
                           revenue_account_id=env["revenue"]))
    r = call_action(ACTIONS["auto-unwind-deal"], conn, ns(deal_id=deal_id))
    assert is_ok(r), r
    rows = _gl(conn, deal_id)
    net = {}
    for x in rows:
        d, c = net.get(x["account_id"], (Decimal("0"), Decimal("0")))
        net[x["account_id"]] = (d + Decimal(x["debit"]), c + Decimal(x["credit"]))
    assert len(rows) == 4
    assert all(d == c for d, c in net.values())
