"""AutomotiveClaw -- reports domain module

Consolidated reporting actions + status (6 actions).
These are top-level report entry points that aggregate across domains.
Imported by db_query.py (unified router).
"""
import os
import sys

try:
    sys.path.insert(0, os.path.expanduser("~/.openclaw/erpclaw/lib"))
    from erpclaw_lib.response import ok, err, row_to_dict
    from erpclaw_lib.decimal_utils import to_decimal, round_currency
except ImportError:
    pass

SKILL = "automotiveclaw"


def _validate_company(conn, company_id):
    if not company_id:
        err("--company-id is required")
    if not conn.execute("SELECT id FROM company WHERE id = ?", (company_id,)).fetchone():
        err(f"Company {company_id} not found")


# ===========================================================================
# 1. inventory-aging (cross-domain report)
# ===========================================================================
def inventory_aging(conn, args):
    _validate_company(conn, args.company_id)
    rows = conn.execute("""
        SELECT id, naming_series, vin, year, make, model, selling_price,
               days_in_stock, vehicle_status, vehicle_condition, lot_location
        FROM automotiveclaw_vehicle
        WHERE company_id = ? AND vehicle_status = 'available'
        ORDER BY days_in_stock DESC
        LIMIT ? OFFSET ?
    """, (args.company_id, args.limit, args.offset)).fetchall()

    total_available = conn.execute(
        "SELECT COUNT(*) FROM automotiveclaw_vehicle WHERE company_id = ? AND vehicle_status = 'available'",
        (args.company_id,)
    ).fetchone()[0]

    ok({
        "rows": [row_to_dict(r) for r in rows],
        "total_available": total_available,
        "count": len(rows),
    })


# ===========================================================================
# 2. gross-profit-report
# ===========================================================================
def gross_profit_report(conn, args):
    _validate_company(conn, args.company_id)
    rows = conn.execute("""
        SELECT d.id, d.naming_series, d.deal_type, d.selling_price,
               d.front_gross, d.back_gross, d.total_gross,
               v.year, v.make, v.model, v.vin
        FROM automotiveclaw_deal d
        LEFT JOIN automotiveclaw_vehicle v ON d.vehicle_id = v.id
        WHERE d.company_id = ? AND d.deal_status = 'delivered'
        ORDER BY CAST(d.total_gross AS REAL) DESC
        LIMIT ? OFFSET ?
    """, (args.company_id, args.limit, args.offset)).fetchall()

    total_gross = conn.execute(
        "SELECT COALESCE(SUM(CAST(total_gross AS REAL)), 0) FROM automotiveclaw_deal WHERE company_id = ? AND deal_status = 'delivered'",
        (args.company_id,)
    ).fetchone()[0]

    ok({
        "rows": [row_to_dict(r) for r in rows],
        "total_gross_profit": str(round_currency(to_decimal(str(total_gross)))),
        "count": len(rows),
    })


# ===========================================================================
# 3. service-efficiency (cross-domain)
# ===========================================================================
def service_efficiency(conn, args):
    _validate_company(conn, args.company_id)

    total_ros = conn.execute(
        "SELECT COUNT(*) FROM automotiveclaw_repair_order WHERE company_id = ?",
        (args.company_id,)
    ).fetchone()[0]

    completed = conn.execute(
        "SELECT COUNT(*) FROM automotiveclaw_repair_order WHERE company_id = ? AND ro_status IN ('completed','invoiced')",
        (args.company_id,)
    ).fetchone()[0]

    total_revenue = conn.execute(
        "SELECT COALESCE(SUM(CAST(total AS REAL)), 0) FROM automotiveclaw_repair_order WHERE company_id = ? AND ro_status IN ('completed','invoiced')",
        (args.company_id,)
    ).fetchone()[0]

    completion_rate = round(completed / total_ros * 100, 1) if total_ros > 0 else 0.0

    ok({
        "total_repair_orders": total_ros,
        "completed_orders": completed,
        "completion_rate_pct": completion_rate,
        "total_service_revenue": str(round_currency(to_decimal(str(total_revenue)))),
    })


# ===========================================================================
# 4. parts-velocity (cross-domain)
# ===========================================================================
def parts_velocity(conn, args):
    _validate_company(conn, args.company_id)
    rows = conn.execute("""
        SELECT id, part_number, description, quantity_on_hand, reorder_point,
               cost, list_price,
               CASE WHEN quantity_on_hand < reorder_point THEN 1 ELSE 0 END as needs_reorder
        FROM automotiveclaw_part
        WHERE company_id = ? AND is_active = 1
        ORDER BY quantity_on_hand ASC
        LIMIT ? OFFSET ?
    """, (args.company_id, args.limit, args.offset)).fetchall()
    ok({"rows": [row_to_dict(r) for r in rows], "count": len(rows)})


# ===========================================================================
# 5. fi-penetration (cross-domain)
# ===========================================================================
def fi_penetration(conn, args):
    _validate_company(conn, args.company_id)

    total_deals = conn.execute(
        "SELECT COUNT(*) FROM automotiveclaw_deal WHERE company_id = ? AND deal_status = 'delivered'",
        (args.company_id,)
    ).fetchone()[0]

    deals_with_fi = conn.execute("""
        SELECT COUNT(DISTINCT d.id)
        FROM automotiveclaw_deal d
        JOIN automotiveclaw_deal_fi_product dfp ON d.id = dfp.deal_id
        WHERE d.company_id = ? AND d.deal_status = 'delivered'
    """, (args.company_id,)).fetchone()[0]

    total_fi_income = conn.execute("""
        SELECT COALESCE(SUM(CAST(dfp.profit AS REAL)), 0)
        FROM automotiveclaw_deal_fi_product dfp
        JOIN automotiveclaw_deal d ON dfp.deal_id = d.id
        WHERE d.company_id = ?
    """, (args.company_id,)).fetchone()[0]

    penetration = round(deals_with_fi / total_deals * 100, 1) if total_deals > 0 else 0.0

    ok({
        "total_delivered_deals": total_deals,
        "deals_with_fi": deals_with_fi,
        "penetration_pct": penetration,
        "total_fi_income": str(round_currency(to_decimal(str(total_fi_income)))),
    })


# ===========================================================================
# 6. status
# ===========================================================================
def status_action(conn, args):
    tables = [
        "automotiveclaw_customer", "automotiveclaw_vehicle", "automotiveclaw_vehicle_photo",
        "automotiveclaw_trade_in", "automotiveclaw_deal", "automotiveclaw_buyer_order",
        "automotiveclaw_fi_product", "automotiveclaw_deal_fi_product",
        "automotiveclaw_repair_order", "automotiveclaw_service_line", "automotiveclaw_warranty_claim",
        "automotiveclaw_part", "automotiveclaw_parts_order", "automotiveclaw_compliance_check",
    ]
    counts = {}
    for tbl in tables:
        try:
            counts[tbl] = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        except Exception:
            counts[tbl] = -1
    ok({
        "skill": "automotiveclaw",
        "version": "1.0.0",
        "total_tables": len(tables),
        "record_counts": counts,
        "domains": ["customers", "inventory", "deals", "fi", "service", "parts", "compliance", "reports"],
    })


# ---------------------------------------------------------------------------
# Action registry
# ---------------------------------------------------------------------------
ACTIONS = {
    "auto-inventory-aging": inventory_aging,
    "auto-gross-profit-report": gross_profit_report,
    "auto-service-efficiency": service_efficiency,
    "auto-parts-velocity": parts_velocity,
    "auto-fi-penetration": fi_penetration,
    "status": status_action,
}
