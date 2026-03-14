#!/usr/bin/env python3
"""AutomotiveClaw -- db_query.py (unified router)

AI-native automotive dealership management. Routes all 70 actions
across 8 domain modules: customers, inventory, deals, fi, service, parts,
compliance, reports.

Usage: python3 db_query.py --action <action-name> [--flags ...]
Output: JSON to stdout, exit 0 on success, exit 1 on error.
"""
import argparse
import json
import os
import sys

# Add shared lib to path
try:
    sys.path.insert(0, os.path.expanduser("~/.openclaw/erpclaw/lib"))
    from erpclaw_lib.db import get_connection, ensure_db_exists, DEFAULT_DB_PATH
    from erpclaw_lib.validation import check_input_lengths
    from erpclaw_lib.response import ok, err
    from erpclaw_lib.dependencies import check_required_tables
    from erpclaw_lib.args import SafeArgumentParser, check_unknown_args
except ImportError:
    import json as _json
    print(_json.dumps({
        "status": "error",
        "error": "ERPClaw foundation not installed. Install erpclaw-setup first: clawhub install erpclaw-setup",
        "suggestion": "clawhub install erpclaw-setup"
    }))
    sys.exit(1)

# Add this script's directory so domain modules can be imported
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from customers import ACTIONS as CUST_ACTIONS
from inventory import ACTIONS as INV_ACTIONS
from deals import ACTIONS as DEAL_ACTIONS
from fi import ACTIONS as FI_ACTIONS
from service import ACTIONS as SVC_ACTIONS
from parts import ACTIONS as PARTS_ACTIONS
from compliance import ACTIONS as COMP_ACTIONS
from reports import ACTIONS as RPT_ACTIONS

# ---------------------------------------------------------------------------
# Merge all domain actions into one router
# ---------------------------------------------------------------------------
SKILL = "automotiveclaw"
REQUIRED_TABLES = ["company", "customer", "automotiveclaw_customer_ext"]

ACTIONS = {}
ACTIONS.update(CUST_ACTIONS)
ACTIONS.update(INV_ACTIONS)
ACTIONS.update(DEAL_ACTIONS)
ACTIONS.update(FI_ACTIONS)
ACTIONS.update(SVC_ACTIONS)
ACTIONS.update(PARTS_ACTIONS)
ACTIONS.update(COMP_ACTIONS)
ACTIONS.update(RPT_ACTIONS)


def main():
    parser = SafeArgumentParser(description="automotiveclaw")
    parser.add_argument("--action", required=True, choices=sorted(ACTIONS.keys()))
    parser.add_argument("--db-path", default=None)

    # -- Shared IDs --
    parser.add_argument("--company-id")
    parser.add_argument("--customer-id")
    parser.add_argument("--vehicle-id")
    parser.add_argument("--deal-id")
    parser.add_argument("--trade-in-id")

    # -- Customer fields --
    parser.add_argument("--name")
    parser.add_argument("--email")
    parser.add_argument("--phone")
    parser.add_argument("--drivers-license")
    parser.add_argument("--customer-type")
    parser.add_argument("--lead-source")

    # -- Vehicle/Inventory fields --
    parser.add_argument("--vin")
    parser.add_argument("--stock-number")
    parser.add_argument("--year")
    parser.add_argument("--make")
    parser.add_argument("--model")
    parser.add_argument("--trim")
    parser.add_argument("--color-exterior")
    parser.add_argument("--color-interior")
    parser.add_argument("--mileage")
    parser.add_argument("--vehicle-condition")
    parser.add_argument("--body-style")
    parser.add_argument("--engine")
    parser.add_argument("--transmission")
    parser.add_argument("--drivetrain")
    parser.add_argument("--msrp")
    parser.add_argument("--invoice-price")
    parser.add_argument("--selling-price")
    parser.add_argument("--internet-price")
    parser.add_argument("--lot-location")
    parser.add_argument("--vehicle-status")
    parser.add_argument("--photo-url")
    parser.add_argument("--photo-order")
    parser.add_argument("--caption")

    # -- Trade-in fields --
    parser.add_argument("--trade-condition")
    parser.add_argument("--offered-amount")
    parser.add_argument("--acv")
    parser.add_argument("--payoff-amount")
    parser.add_argument("--trade-status")

    # -- Deal fields --
    parser.add_argument("--salesperson")
    parser.add_argument("--deal-type")
    parser.add_argument("--trade-allowance")
    parser.add_argument("--trade-payoff")
    parser.add_argument("--down-payment")
    parser.add_argument("--rebates")
    parser.add_argument("--deal-status")

    # -- GL posting fields (optional, for finalize-deal) --
    parser.add_argument("--revenue-account-id")
    parser.add_argument("--receivable-account-id")
    parser.add_argument("--cogs-account-id")
    parser.add_argument("--inventory-account-id")
    parser.add_argument("--cost-center-id")

    # -- Buyer order fields --
    parser.add_argument("--vehicle-price")
    parser.add_argument("--trade-value")
    parser.add_argument("--accessories")
    parser.add_argument("--fees")
    parser.add_argument("--subtotal")
    parser.add_argument("--tax-amount")
    parser.add_argument("--total")

    # -- F&I fields --
    parser.add_argument("--fi-product-id")
    parser.add_argument("--deal-fi-product-id")
    parser.add_argument("--product-type")
    parser.add_argument("--provider")
    parser.add_argument("--base-cost")
    parser.add_argument("--retail-price")
    parser.add_argument("--max-markup")
    parser.add_argument("--term-months")
    parser.add_argument("--cost")
    parser.add_argument("--interest-rate")

    # -- Service fields --
    parser.add_argument("--repair-order-id")
    parser.add_argument("--vehicle-vin")
    parser.add_argument("--advisor")
    parser.add_argument("--technician")
    parser.add_argument("--ro-type")
    parser.add_argument("--ro-status")
    parser.add_argument("--promised-date")
    parser.add_argument("--line-type")
    parser.add_argument("--description")
    parser.add_argument("--quantity")
    parser.add_argument("--rate")

    # -- Warranty claim fields --
    parser.add_argument("--claim-number")
    parser.add_argument("--claim-type")
    parser.add_argument("--labor-amount")
    parser.add_argument("--parts-amount")
    parser.add_argument("--claim-status")

    # -- Parts fields --
    parser.add_argument("--part-id")
    parser.add_argument("--part-number")
    parser.add_argument("--oem-number")
    parser.add_argument("--manufacturer")
    parser.add_argument("--list-price")
    parser.add_argument("--quantity-on-hand")
    parser.add_argument("--reorder-point")
    parser.add_argument("--bin-location")
    parser.add_argument("--parts-order-id")
    parser.add_argument("--supplier-id")
    parser.add_argument("--order-date")
    parser.add_argument("--expected-date")
    parser.add_argument("--total-amount")

    # -- Compliance fields --
    parser.add_argument("--check-type")
    parser.add_argument("--check-result")
    parser.add_argument("--checked-by")
    parser.add_argument("--check-date")

    # -- Shared --
    parser.add_argument("--notes")
    parser.add_argument("--search")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--offset", type=int, default=0)

    args, unknown = parser.parse_known_args()
    check_unknown_args(parser, unknown)
    check_input_lengths(args)

    db_path = args.db_path or DEFAULT_DB_PATH
    ensure_db_exists(db_path)
    conn = get_connection(db_path)

    _dep = check_required_tables(conn, REQUIRED_TABLES)
    if _dep:
        _dep["suggestion"] = "clawhub install erpclaw-setup && clawhub install automotiveclaw"
        print(json.dumps(_dep, indent=2))
        conn.close()
        sys.exit(1)

    try:
        ACTIONS[args.action](conn, args)
    except Exception as e:
        conn.rollback()
        sys.stderr.write(f"[{SKILL}] {e}\n")
        err(str(e))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
