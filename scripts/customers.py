"""AutomotiveClaw -- customers domain module

Actions for customer management (1 table, 6 actions).
Imported by db_query.py (unified router).
"""
import os
import sys
import uuid
from datetime import datetime, timezone

try:
    sys.path.insert(0, os.path.expanduser("~/.openclaw/erpclaw/lib"))
    from erpclaw_lib.naming import get_next_name, ENTITY_PREFIXES
    from erpclaw_lib.response import ok, err, row_to_dict
    from erpclaw_lib.audit import audit

    ENTITY_PREFIXES.setdefault("automotiveclaw_customer", "ACUST-")
except ImportError:
    pass

SKILL = "automotiveclaw"

_now_iso = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

VALID_CUSTOMER_TYPES = ("individual", "business", "fleet")
VALID_LEAD_SOURCES = ("walk_in", "internet", "phone", "referral", "repeat", "other")


def _validate_company(conn, company_id):
    if not company_id:
        err("--company-id is required")
    if not conn.execute("SELECT id FROM company WHERE id = ?", (company_id,)).fetchone():
        err(f"Company {company_id} not found")


# ===========================================================================
# 1. add-customer
# ===========================================================================
def add_customer(conn, args):
    _validate_company(conn, args.company_id)
    name = getattr(args, "name", None)
    if not name:
        err("--name is required")

    customer_type = getattr(args, "customer_type", None) or "individual"
    if customer_type not in VALID_CUSTOMER_TYPES:
        err(f"Invalid customer_type: {customer_type}. Must be one of: {', '.join(VALID_CUSTOMER_TYPES)}")

    lead_source = getattr(args, "lead_source", None) or "walk_in"
    if lead_source not in VALID_LEAD_SOURCES:
        err(f"Invalid lead_source: {lead_source}. Must be one of: {', '.join(VALID_LEAD_SOURCES)}")

    cust_id = str(uuid.uuid4())
    now = _now_iso()
    conn.company_id = args.company_id
    naming = get_next_name(conn, "automotiveclaw_customer")

    conn.execute("""
        INSERT INTO automotiveclaw_customer (
            id, naming_series, name, email, phone, address, city, state,
            zip_code, drivers_license, customer_type, lead_source,
            company_id, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        cust_id, naming, name,
        getattr(args, "email", None),
        getattr(args, "phone", None),
        getattr(args, "address", None),
        getattr(args, "city", None),
        getattr(args, "state", None),
        getattr(args, "zip_code", None),
        getattr(args, "drivers_license", None),
        customer_type, lead_source,
        args.company_id, now, now,
    ))
    audit(conn, SKILL, "auto-add-customer", "automotiveclaw_customer", cust_id,
          new_values={"name": name, "customer_type": customer_type})
    conn.commit()
    ok({"id": cust_id, "naming_series": naming, "name": name, "customer_type": customer_type})


# ===========================================================================
# 2. update-customer
# ===========================================================================
def update_customer(conn, args):
    cust_id = getattr(args, "customer_id", None)
    if not cust_id:
        err("--customer-id is required")
    if not conn.execute("SELECT id FROM automotiveclaw_customer WHERE id = ?", (cust_id,)).fetchone():
        err(f"Customer {cust_id} not found")

    updates, params, changed = [], [], []
    for arg_name, col_name in {
        "name": "name", "email": "email", "phone": "phone",
        "address": "address", "city": "city", "state": "state",
        "zip_code": "zip_code", "customer_type": "customer_type",
    }.items():
        val = getattr(args, arg_name, None)
        if val is not None:
            updates.append(f"{col_name} = ?")
            params.append(val)
            changed.append(col_name)

    if not updates:
        err("No fields to update")

    updates.append("updated_at = ?")
    params.append(_now_iso())
    params.append(cust_id)
    conn.execute(f"UPDATE automotiveclaw_customer SET {', '.join(updates)} WHERE id = ?", params)
    audit(conn, SKILL, "auto-update-customer", "automotiveclaw_customer", cust_id,
          new_values={"updated_fields": changed})
    conn.commit()
    ok({"id": cust_id, "updated_fields": changed})


# ===========================================================================
# 3. get-customer
# ===========================================================================
def get_customer(conn, args):
    cust_id = getattr(args, "customer_id", None)
    if not cust_id:
        err("--customer-id is required")
    row = conn.execute("SELECT * FROM automotiveclaw_customer WHERE id = ?", (cust_id,)).fetchone()
    if not row:
        err(f"Customer {cust_id} not found")
    ok(row_to_dict(row))


# ===========================================================================
# 4. list-customers
# ===========================================================================
def list_customers(conn, args):
    where, params = ["1=1"], []
    if getattr(args, "company_id", None):
        where.append("company_id = ?")
        params.append(args.company_id)
    if getattr(args, "customer_type", None):
        where.append("customer_type = ?")
        params.append(args.customer_type)
    if getattr(args, "search", None):
        where.append("(name LIKE ? OR email LIKE ? OR phone LIKE ?)")
        params.extend([f"%{args.search}%"] * 3)

    where_sql = " AND ".join(where)
    total = conn.execute(
        f"SELECT COUNT(*) FROM automotiveclaw_customer WHERE {where_sql}", params
    ).fetchone()[0]
    params.extend([args.limit, args.offset])
    rows = conn.execute(
        f"SELECT * FROM automotiveclaw_customer WHERE {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        params
    ).fetchall()
    ok({
        "rows": [row_to_dict(r) for r in rows],
        "total_count": total, "limit": args.limit, "offset": args.offset,
        "has_more": (args.offset + args.limit) < total,
    })


# ===========================================================================
# 5. customer-vehicle-history
# ===========================================================================
def customer_vehicle_history(conn, args):
    cust_id = getattr(args, "customer_id", None)
    if not cust_id:
        err("--customer-id is required")
    if not conn.execute("SELECT id FROM automotiveclaw_customer WHERE id = ?", (cust_id,)).fetchone():
        err(f"Customer {cust_id} not found")

    rows = conn.execute("""
        SELECT d.id as deal_id, d.deal_type, d.deal_status, d.selling_price,
               d.delivered_date, v.vin, v.year, v.make, v.model
        FROM automotiveclaw_deal d
        LEFT JOIN automotiveclaw_vehicle v ON d.vehicle_id = v.id
        WHERE d.customer_id = ?
        ORDER BY d.created_at DESC
        LIMIT ? OFFSET ?
    """, (cust_id, args.limit, args.offset)).fetchall()
    ok({
        "customer_id": cust_id,
        "rows": [row_to_dict(r) for r in rows],
        "count": len(rows),
    })


# ===========================================================================
# 6. customer-service-history
# ===========================================================================
def customer_service_history(conn, args):
    cust_id = getattr(args, "customer_id", None)
    if not cust_id:
        err("--customer-id is required")
    if not conn.execute("SELECT id FROM automotiveclaw_customer WHERE id = ?", (cust_id,)).fetchone():
        err(f"Customer {cust_id} not found")

    rows = conn.execute("""
        SELECT id, naming_series, vehicle_vin, ro_type, ro_status,
               labor_total, parts_total, total, created_at
        FROM automotiveclaw_repair_order
        WHERE customer_id = ?
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    """, (cust_id, args.limit, args.offset)).fetchall()
    ok({
        "customer_id": cust_id,
        "rows": [row_to_dict(r) for r in rows],
        "count": len(rows),
    })


# ---------------------------------------------------------------------------
# Action registry
# ---------------------------------------------------------------------------
ACTIONS = {
    "auto-add-customer": add_customer,
    "auto-update-customer": update_customer,
    "auto-get-customer": get_customer,
    "auto-list-customers": list_customers,
    "auto-customer-vehicle-history": customer_vehicle_history,
    "auto-customer-service-history": customer_service_history,
}
