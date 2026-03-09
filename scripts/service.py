"""AutomotiveClaw -- service domain module

Actions for repair orders, service lines, warranty claims (3 tables, 10 actions).
Imported by db_query.py (unified router).
"""
import os
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

try:
    sys.path.insert(0, os.path.expanduser("~/.openclaw/erpclaw/lib"))
    from erpclaw_lib.naming import get_next_name, ENTITY_PREFIXES
    from erpclaw_lib.response import ok, err, row_to_dict
    from erpclaw_lib.audit import audit
    from erpclaw_lib.decimal_utils import to_decimal, round_currency

    ENTITY_PREFIXES.setdefault("automotiveclaw_repair_order", "RO-")
    ENTITY_PREFIXES.setdefault("automotiveclaw_warranty_claim", "WC-")
except ImportError:
    pass

SKILL = "automotiveclaw"

_now_iso = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

VALID_RO_TYPES = ("customer_pay", "warranty", "internal", "recall")
VALID_RO_STATUSES = ("open", "in_progress", "waiting_parts", "completed", "invoiced")
VALID_LINE_TYPES = ("labor", "parts", "sublet", "fee")
VALID_CLAIM_TYPES = ("factory", "extended", "goodwill")
VALID_CLAIM_STATUSES = ("submitted", "approved", "rejected", "paid")


def _validate_company(conn, company_id):
    if not company_id:
        err("--company-id is required")
    if not conn.execute("SELECT id FROM company WHERE id = ?", (company_id,)).fetchone():
        err(f"Company {company_id} not found")


def _to_money(val):
    if val is None:
        return None
    return str(round_currency(to_decimal(val)))


def _recalc_ro_totals(conn, ro_id):
    """Recalculate labor_total, parts_total, total from service lines."""
    labor = conn.execute(
        "SELECT COALESCE(SUM(CAST(amount AS REAL)), 0) FROM automotiveclaw_service_line WHERE repair_order_id = ? AND line_type = 'labor'",
        (ro_id,)
    ).fetchone()[0]
    parts = conn.execute(
        "SELECT COALESCE(SUM(CAST(amount AS REAL)), 0) FROM automotiveclaw_service_line WHERE repair_order_id = ? AND line_type IN ('parts', 'sublet', 'fee')",
        (ro_id,)
    ).fetchone()[0]
    total = labor + parts
    conn.execute(
        "UPDATE automotiveclaw_repair_order SET labor_total = ?, parts_total = ?, total = ?, updated_at = ? WHERE id = ?",
        (str(round_currency(to_decimal(str(labor)))),
         str(round_currency(to_decimal(str(parts)))),
         str(round_currency(to_decimal(str(total)))),
         _now_iso(), ro_id)
    )


# ===========================================================================
# 1. add-repair-order
# ===========================================================================
def add_repair_order(conn, args):
    _validate_company(conn, args.company_id)

    ro_type = getattr(args, "ro_type", None) or "customer_pay"
    if ro_type not in VALID_RO_TYPES:
        err(f"Invalid ro_type: {ro_type}. Must be one of: {', '.join(VALID_RO_TYPES)}")

    customer_id = getattr(args, "customer_id", None)
    if customer_id:
        if not conn.execute("SELECT id FROM customer WHERE id = ?", (customer_id,)).fetchone():
            err(f"Customer {customer_id} not found")

    ro_id = str(uuid.uuid4())
    now = _now_iso()
    conn.company_id = args.company_id
    naming = get_next_name(conn, "automotiveclaw_repair_order")

    conn.execute("""
        INSERT INTO automotiveclaw_repair_order (
            id, naming_series, vehicle_vin, customer_id, advisor, technician,
            ro_type, promised_date, ro_status, labor_total, parts_total, total,
            company_id, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        ro_id, naming,
        getattr(args, "vehicle_vin", None),
        customer_id,
        getattr(args, "advisor", None),
        getattr(args, "technician", None),
        ro_type,
        getattr(args, "promised_date", None),
        "open", "0.00", "0.00", "0.00",
        args.company_id, now, now,
    ))
    audit(conn, SKILL, "auto-add-repair-order", "automotiveclaw_repair_order", ro_id,
          new_values={"ro_type": ro_type, "vehicle_vin": getattr(args, "vehicle_vin", None)})
    conn.commit()
    ok({"id": ro_id, "naming_series": naming, "ro_type": ro_type, "ro_status": "open"})


# ===========================================================================
# 2. update-repair-order
# ===========================================================================
def update_repair_order(conn, args):
    ro_id = getattr(args, "repair_order_id", None)
    if not ro_id:
        err("--repair-order-id is required")
    if not conn.execute("SELECT id FROM automotiveclaw_repair_order WHERE id = ?", (ro_id,)).fetchone():
        err(f"Repair order {ro_id} not found")

    updates, params, changed = [], [], []
    for arg_name, col_name in {
        "advisor": "advisor",
        "technician": "technician",
        "promised_date": "promised_date",
    }.items():
        val = getattr(args, arg_name, None)
        if val is not None:
            updates.append(f"{col_name} = ?")
            params.append(val)
            changed.append(col_name)

    ro_status = getattr(args, "ro_status", None)
    if ro_status is not None:
        if ro_status not in VALID_RO_STATUSES:
            err(f"Invalid ro_status: {ro_status}. Must be one of: {', '.join(VALID_RO_STATUSES)}")
        updates.append("ro_status = ?")
        params.append(ro_status)
        changed.append("ro_status")

    if not updates:
        err("No fields to update")

    updates.append("updated_at = ?")
    params.append(_now_iso())
    params.append(ro_id)
    conn.execute(f"UPDATE automotiveclaw_repair_order SET {', '.join(updates)} WHERE id = ?", params)
    audit(conn, SKILL, "auto-update-repair-order", "automotiveclaw_repair_order", ro_id,
          new_values={"updated_fields": changed})
    conn.commit()
    ok({"id": ro_id, "updated_fields": changed})


# ===========================================================================
# 3. get-repair-order
# ===========================================================================
def get_repair_order(conn, args):
    ro_id = getattr(args, "repair_order_id", None)
    if not ro_id:
        err("--repair-order-id is required")
    row = conn.execute("SELECT * FROM automotiveclaw_repair_order WHERE id = ?", (ro_id,)).fetchone()
    if not row:
        err(f"Repair order {ro_id} not found")
    data = row_to_dict(row)

    lines = conn.execute(
        "SELECT * FROM automotiveclaw_service_line WHERE repair_order_id = ? ORDER BY created_at",
        (ro_id,)
    ).fetchall()
    data["service_lines"] = [row_to_dict(r) for r in lines]
    data["line_count"] = len(lines)
    ok(data)


# ===========================================================================
# 4. list-repair-orders
# ===========================================================================
def list_repair_orders(conn, args):
    where, params = ["1=1"], []
    if getattr(args, "company_id", None):
        where.append("company_id = ?")
        params.append(args.company_id)
    if getattr(args, "customer_id", None):
        where.append("customer_id = ?")
        params.append(args.customer_id)
    if getattr(args, "ro_status", None):
        where.append("ro_status = ?")
        params.append(args.ro_status)
    if getattr(args, "search", None):
        where.append("(vehicle_vin LIKE ? OR advisor LIKE ? OR technician LIKE ?)")
        params.extend([f"%{args.search}%"] * 3)

    where_sql = " AND ".join(where)
    total = conn.execute(
        f"SELECT COUNT(*) FROM automotiveclaw_repair_order WHERE {where_sql}", params
    ).fetchone()[0]
    params.extend([args.limit, args.offset])
    rows = conn.execute(
        f"SELECT * FROM automotiveclaw_repair_order WHERE {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        params
    ).fetchall()
    ok({
        "rows": [row_to_dict(r) for r in rows],
        "total_count": total, "limit": args.limit, "offset": args.offset,
        "has_more": (args.offset + args.limit) < total,
    })


# ===========================================================================
# 5. close-repair-order
# ===========================================================================
def close_repair_order(conn, args):
    ro_id = getattr(args, "repair_order_id", None)
    if not ro_id:
        err("--repair-order-id is required")
    row = conn.execute("SELECT * FROM automotiveclaw_repair_order WHERE id = ?", (ro_id,)).fetchone()
    if not row:
        err(f"Repair order {ro_id} not found")
    data = row_to_dict(row)
    if data["ro_status"] in ("completed", "invoiced"):
        err(f"Repair order is already {data['ro_status']}")

    _recalc_ro_totals(conn, ro_id)
    conn.execute(
        "UPDATE automotiveclaw_repair_order SET ro_status = 'completed', updated_at = ? WHERE id = ?",
        (_now_iso(), ro_id)
    )
    audit(conn, SKILL, "auto-close-repair-order", "automotiveclaw_repair_order", ro_id,
          new_values={"ro_status": "completed"})
    conn.commit()

    updated = conn.execute("SELECT * FROM automotiveclaw_repair_order WHERE id = ?", (ro_id,)).fetchone()
    ok({
        "id": ro_id, "ro_status": "completed",
        "labor_total": row_to_dict(updated)["labor_total"],
        "parts_total": row_to_dict(updated)["parts_total"],
        "total": row_to_dict(updated)["total"],
    })


# ===========================================================================
# 6. add-service-line
# ===========================================================================
def add_service_line(conn, args):
    ro_id = getattr(args, "repair_order_id", None)
    if not ro_id:
        err("--repair-order-id is required")
    if not conn.execute("SELECT id FROM automotiveclaw_repair_order WHERE id = ?", (ro_id,)).fetchone():
        err(f"Repair order {ro_id} not found")

    _validate_company(conn, args.company_id)

    line_type = getattr(args, "line_type", None) or "labor"
    if line_type not in VALID_LINE_TYPES:
        err(f"Invalid line_type: {line_type}. Must be one of: {', '.join(VALID_LINE_TYPES)}")

    qty = to_decimal(getattr(args, "quantity", None) or "1")
    rate = to_decimal(getattr(args, "rate", None) or "0")
    # Allow direct amount via --labor-amount or --parts-amount
    labor_amount = getattr(args, "labor_amount", None)
    parts_amount = getattr(args, "parts_amount", None)
    if labor_amount and line_type == "labor":
        amount = round_currency(to_decimal(labor_amount))
    elif parts_amount and line_type == "parts":
        amount = round_currency(to_decimal(parts_amount))
    else:
        amount = round_currency(qty * rate)

    line_id = str(uuid.uuid4())
    conn.execute("""
        INSERT INTO automotiveclaw_service_line (
            id, repair_order_id, line_type, description, quantity, rate, amount,
            technician, company_id, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (
        line_id, ro_id, line_type,
        getattr(args, "description", None),
        str(qty), str(rate), str(amount),
        getattr(args, "technician", None),
        args.company_id, _now_iso(),
    ))

    # Recalculate RO totals
    _recalc_ro_totals(conn, ro_id)
    conn.commit()
    ok({"id": line_id, "repair_order_id": ro_id, "line_type": line_type, "amount": str(amount)})


# ===========================================================================
# 7. list-service-lines
# ===========================================================================
def list_service_lines(conn, args):
    ro_id = getattr(args, "repair_order_id", None)
    if not ro_id:
        err("--repair-order-id is required")

    rows = conn.execute(
        "SELECT * FROM automotiveclaw_service_line WHERE repair_order_id = ? ORDER BY created_at LIMIT ? OFFSET ?",
        (ro_id, args.limit, args.offset)
    ).fetchall()
    ok({"repair_order_id": ro_id, "rows": [row_to_dict(r) for r in rows], "count": len(rows)})


# ===========================================================================
# 8. add-warranty-claim
# ===========================================================================
def add_warranty_claim(conn, args):
    ro_id = getattr(args, "repair_order_id", None)
    if not ro_id:
        err("--repair-order-id is required")
    if not conn.execute("SELECT id FROM automotiveclaw_repair_order WHERE id = ?", (ro_id,)).fetchone():
        err(f"Repair order {ro_id} not found")

    _validate_company(conn, args.company_id)

    claim_type = getattr(args, "claim_type", None) or "factory"
    if claim_type not in VALID_CLAIM_TYPES:
        err(f"Invalid claim_type: {claim_type}. Must be one of: {', '.join(VALID_CLAIM_TYPES)}")

    claim_id = str(uuid.uuid4())
    now = _now_iso()
    conn.company_id = args.company_id
    naming = get_next_name(conn, "automotiveclaw_warranty_claim")

    labor_amount = _to_money(getattr(args, "labor_amount", None))
    parts_amount = _to_money(getattr(args, "parts_amount", None))
    total = str(round_currency(
        to_decimal(labor_amount or "0") + to_decimal(parts_amount or "0")
    ))

    conn.execute("""
        INSERT INTO automotiveclaw_warranty_claim (
            id, naming_series, repair_order_id, claim_number, claim_type,
            labor_amount, parts_amount, total_amount, claim_status,
            company_id, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        claim_id, naming, ro_id,
        getattr(args, "claim_number", None),
        claim_type, labor_amount, parts_amount, total,
        "submitted", args.company_id, now, now,
    ))
    audit(conn, SKILL, "auto-add-warranty-claim", "automotiveclaw_warranty_claim", claim_id,
          new_values={"repair_order_id": ro_id, "claim_type": claim_type})
    conn.commit()
    ok({
        "id": claim_id, "naming_series": naming,
        "claim_type": claim_type, "claim_status": "submitted",
        "total_amount": total,
    })


# ===========================================================================
# 9. list-warranty-claims
# ===========================================================================
def list_warranty_claims(conn, args):
    where, params = ["1=1"], []
    if getattr(args, "company_id", None):
        where.append("company_id = ?")
        params.append(args.company_id)
    if getattr(args, "repair_order_id", None):
        where.append("repair_order_id = ?")
        params.append(args.repair_order_id)
    if getattr(args, "claim_status", None):
        where.append("claim_status = ?")
        params.append(args.claim_status)

    where_sql = " AND ".join(where)
    total = conn.execute(
        f"SELECT COUNT(*) FROM automotiveclaw_warranty_claim WHERE {where_sql}", params
    ).fetchone()[0]
    params.extend([args.limit, args.offset])
    rows = conn.execute(
        f"SELECT * FROM automotiveclaw_warranty_claim WHERE {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        params
    ).fetchall()
    ok({
        "rows": [row_to_dict(r) for r in rows],
        "total_count": total, "limit": args.limit, "offset": args.offset,
        "has_more": (args.offset + args.limit) < total,
    })


# ===========================================================================
# 10. service-efficiency-report
# ===========================================================================
def service_efficiency_report(conn, args):
    _validate_company(conn, args.company_id)

    total_ros = conn.execute(
        "SELECT COUNT(*) FROM automotiveclaw_repair_order WHERE company_id = ?",
        (args.company_id,)
    ).fetchone()[0]

    by_status = conn.execute(
        "SELECT ro_status, COUNT(*) as cnt FROM automotiveclaw_repair_order WHERE company_id = ? GROUP BY ro_status",
        (args.company_id,)
    ).fetchall()

    by_type = conn.execute(
        "SELECT ro_type, COUNT(*) as cnt FROM automotiveclaw_repair_order WHERE company_id = ? GROUP BY ro_type",
        (args.company_id,)
    ).fetchall()

    total_revenue = conn.execute(
        "SELECT COALESCE(SUM(CAST(total AS REAL)), 0) FROM automotiveclaw_repair_order WHERE company_id = ?",
        (args.company_id,)
    ).fetchone()[0]

    ok({
        "total_repair_orders": total_ros,
        "by_status": {r["ro_status"]: r["cnt"] for r in by_status},
        "by_type": {r["ro_type"]: r["cnt"] for r in by_type},
        "total_revenue": str(round_currency(to_decimal(str(total_revenue)))),
    })


# ---------------------------------------------------------------------------
# Action registry
# ---------------------------------------------------------------------------
ACTIONS = {
    "auto-add-repair-order": add_repair_order,
    "auto-update-repair-order": update_repair_order,
    "auto-get-repair-order": get_repair_order,
    "auto-list-repair-orders": list_repair_orders,
    "auto-close-repair-order": close_repair_order,
    "auto-add-service-line": add_service_line,
    "auto-list-service-lines": list_service_lines,
    "auto-add-warranty-claim": add_warranty_claim,
    "auto-list-warranty-claims": list_warranty_claims,
    "auto-service-efficiency-report": service_efficiency_report,
}
