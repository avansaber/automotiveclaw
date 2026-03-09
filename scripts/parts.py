"""AutomotiveClaw -- parts domain module

Actions for parts inventory and ordering (2 tables, 8 actions).
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

    ENTITY_PREFIXES.setdefault("automotiveclaw_parts_order", "PO-")
except ImportError:
    pass

SKILL = "automotiveclaw"

_now_iso = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

VALID_ORDER_STATUSES = ("ordered", "partial", "received", "cancelled")


def _validate_company(conn, company_id):
    if not company_id:
        err("--company-id is required")
    if not conn.execute("SELECT id FROM company WHERE id = ?", (company_id,)).fetchone():
        err(f"Company {company_id} not found")


def _to_money(val):
    if val is None:
        return None
    return str(round_currency(to_decimal(val)))


# ===========================================================================
# 1. add-part
# ===========================================================================
def add_part(conn, args):
    _validate_company(conn, args.company_id)
    part_number = getattr(args, "part_number", None)
    if not part_number:
        err("--part-number is required")

    part_id = str(uuid.uuid4())
    now = _now_iso()
    qty = int(args.quantity_on_hand) if getattr(args, "quantity_on_hand", None) else 0
    reorder = int(args.reorder_point) if getattr(args, "reorder_point", None) else 5

    conn.execute("""
        INSERT INTO automotiveclaw_part (
            id, part_number, description, oem_number, manufacturer,
            list_price, cost, quantity_on_hand, reorder_point, bin_location,
            is_active, company_id, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        part_id, part_number,
        getattr(args, "description", None),
        getattr(args, "oem_number", None),
        getattr(args, "manufacturer", None),
        _to_money(getattr(args, "list_price", None)),
        _to_money(getattr(args, "cost", None)),
        qty, reorder,
        getattr(args, "bin_location", None),
        1, args.company_id, now, now,
    ))
    audit(conn, SKILL, "auto-add-part", "automotiveclaw_part", part_id,
          new_values={"part_number": part_number})
    conn.commit()
    ok({"id": part_id, "part_number": part_number, "quantity_on_hand": qty})


# ===========================================================================
# 2. update-part
# ===========================================================================
def update_part(conn, args):
    part_id = getattr(args, "part_id", None)
    if not part_id:
        err("--part-id is required")
    if not conn.execute("SELECT id FROM automotiveclaw_part WHERE id = ?", (part_id,)).fetchone():
        err(f"Part {part_id} not found")

    updates, params, changed = [], [], []
    for arg_name, col_name in {
        "description": "description",
        "bin_location": "bin_location",
    }.items():
        val = getattr(args, arg_name, None)
        if val is not None:
            updates.append(f"{col_name} = ?")
            params.append(val)
            changed.append(col_name)

    for arg_name, col_name in {
        "list_price": "list_price",
        "cost": "cost",
    }.items():
        val = getattr(args, arg_name, None)
        if val is not None:
            updates.append(f"{col_name} = ?")
            params.append(_to_money(val))
            changed.append(col_name)

    for arg_name, col_name in {
        "quantity_on_hand": "quantity_on_hand",
        "reorder_point": "reorder_point",
    }.items():
        val = getattr(args, arg_name, None)
        if val is not None:
            updates.append(f"{col_name} = ?")
            params.append(int(val))
            changed.append(col_name)

    if not updates:
        err("No fields to update")

    updates.append("updated_at = ?")
    params.append(_now_iso())
    params.append(part_id)
    conn.execute(f"UPDATE automotiveclaw_part SET {', '.join(updates)} WHERE id = ?", params)
    audit(conn, SKILL, "auto-update-part", "automotiveclaw_part", part_id,
          new_values={"updated_fields": changed})
    conn.commit()
    ok({"id": part_id, "updated_fields": changed})


# ===========================================================================
# 3. get-part
# ===========================================================================
def get_part(conn, args):
    part_id = getattr(args, "part_id", None)
    if not part_id:
        err("--part-id is required")
    row = conn.execute("SELECT * FROM automotiveclaw_part WHERE id = ?", (part_id,)).fetchone()
    if not row:
        err(f"Part {part_id} not found")
    ok(row_to_dict(row))


# ===========================================================================
# 4. list-parts
# ===========================================================================
def list_parts(conn, args):
    where, params = ["1=1"], []
    if getattr(args, "company_id", None):
        where.append("company_id = ?")
        params.append(args.company_id)
    if getattr(args, "search", None):
        where.append("(part_number LIKE ? OR description LIKE ? OR oem_number LIKE ?)")
        params.extend([f"%{args.search}%"] * 3)

    where_sql = " AND ".join(where)
    total = conn.execute(
        f"SELECT COUNT(*) FROM automotiveclaw_part WHERE {where_sql}", params
    ).fetchone()[0]
    params.extend([args.limit, args.offset])
    rows = conn.execute(
        f"SELECT * FROM automotiveclaw_part WHERE {where_sql} ORDER BY part_number ASC LIMIT ? OFFSET ?",
        params
    ).fetchall()
    ok({
        "rows": [row_to_dict(r) for r in rows],
        "total_count": total, "limit": args.limit, "offset": args.offset,
        "has_more": (args.offset + args.limit) < total,
    })


# ===========================================================================
# 5. add-parts-order
# ===========================================================================
def add_parts_order(conn, args):
    _validate_company(conn, args.company_id)
    supplier_id = getattr(args, "supplier_id", None)
    if not supplier_id:
        err("--supplier-id is required")
    # Validate supplier FK against core supplier table
    sup_row = conn.execute("SELECT id, name FROM supplier WHERE id = ?", (supplier_id,)).fetchone()
    if not sup_row:
        err(f"Supplier {supplier_id} not found in core supplier table")

    po_id = str(uuid.uuid4())
    now = _now_iso()
    conn.company_id = args.company_id
    naming = get_next_name(conn, "automotiveclaw_parts_order")

    conn.execute("""
        INSERT INTO automotiveclaw_parts_order (
            id, naming_series, supplier_id, order_date, expected_date,
            order_status, total_amount, company_id, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (
        po_id, naming, supplier_id,
        getattr(args, "order_date", None) or now[:10],
        getattr(args, "expected_date", None),
        "ordered",
        _to_money(getattr(args, "total_amount", None)),
        args.company_id, now, now,
    ))
    audit(conn, SKILL, "auto-add-parts-order", "automotiveclaw_parts_order", po_id,
          new_values={"supplier_id": supplier_id})
    conn.commit()
    ok({"id": po_id, "naming_series": naming, "supplier_id": supplier_id, "supplier_name": sup_row[1], "order_status": "ordered"})


# ===========================================================================
# 6. receive-parts-order
# ===========================================================================
def receive_parts_order(conn, args):
    po_id = getattr(args, "parts_order_id", None)
    if not po_id:
        err("--parts-order-id is required")
    row = conn.execute("SELECT * FROM automotiveclaw_parts_order WHERE id = ?", (po_id,)).fetchone()
    if not row:
        err(f"Parts order {po_id} not found")
    data = row_to_dict(row)
    if data["order_status"] in ("received", "cancelled"):
        err(f"Parts order is already {data['order_status']}")

    conn.execute(
        "UPDATE automotiveclaw_parts_order SET order_status = 'received', updated_at = ? WHERE id = ?",
        (_now_iso(), po_id)
    )
    audit(conn, SKILL, "auto-receive-parts-order", "automotiveclaw_parts_order", po_id,
          new_values={"order_status": "received"})
    conn.commit()
    ok({"id": po_id, "order_status": "received"})


# ===========================================================================
# 7. parts-velocity-report
# ===========================================================================
def parts_velocity_report(conn, args):
    _validate_company(conn, args.company_id)
    rows = conn.execute("""
        SELECT id, part_number, description, quantity_on_hand, reorder_point,
               cost, list_price
        FROM automotiveclaw_part
        WHERE company_id = ? AND is_active = 1
        ORDER BY quantity_on_hand ASC
        LIMIT ? OFFSET ?
    """, (args.company_id, args.limit, args.offset)).fetchall()
    ok({"rows": [row_to_dict(r) for r in rows], "count": len(rows)})


# ===========================================================================
# 8. parts-inventory-value
# ===========================================================================
def parts_inventory_value(conn, args):
    _validate_company(conn, args.company_id)

    total_parts = conn.execute(
        "SELECT COUNT(*) FROM automotiveclaw_part WHERE company_id = ? AND is_active = 1",
        (args.company_id,)
    ).fetchone()[0]

    total_value = conn.execute(
        "SELECT COALESCE(SUM(CAST(cost AS REAL) * quantity_on_hand), 0) FROM automotiveclaw_part WHERE company_id = ? AND is_active = 1",
        (args.company_id,)
    ).fetchone()[0]

    below_reorder = conn.execute(
        "SELECT COUNT(*) FROM automotiveclaw_part WHERE company_id = ? AND is_active = 1 AND quantity_on_hand < reorder_point",
        (args.company_id,)
    ).fetchone()[0]

    ok({
        "total_active_parts": total_parts,
        "total_inventory_value": str(round_currency(to_decimal(str(total_value)))),
        "parts_below_reorder": below_reorder,
    })


# ---------------------------------------------------------------------------
# Action registry
# ---------------------------------------------------------------------------
ACTIONS = {
    "auto-add-part": add_part,
    "auto-update-part": update_part,
    "auto-get-part": get_part,
    "auto-list-parts": list_parts,
    "auto-add-parts-order": add_parts_order,
    "auto-receive-parts-order": receive_parts_order,
    "auto-parts-velocity-report": parts_velocity_report,
    "auto-parts-inventory-value": parts_inventory_value,
}
