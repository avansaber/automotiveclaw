"""AutomotiveClaw -- customers domain module

Actions for customer management (extension table + core customer via cross_skill).
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
    from erpclaw_lib.cross_skill import create_customer, CrossSkillError
    from erpclaw_lib.query import Q, P, Table, Field, fn, Order, insert_row, update_row

    ENTITY_PREFIXES.setdefault("automotiveclaw_customer_ext", "ACUST-")
except ImportError:
    pass

SKILL = "automotiveclaw"

_now_iso = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

VALID_CUSTOMER_TYPES = ("individual", "business", "fleet")
VALID_LEAD_SOURCES = ("walk_in", "internet", "phone", "referral", "repeat", "other")

# Map automotiveclaw customer_type to core customer_type
_CORE_CUSTOMER_TYPE = {
    "individual": "individual",
    "business": "company",
    "fleet": "company",
}


def _validate_company(conn, company_id):
    if not company_id:
        err("--company-id is required")
    if not conn.execute(Q.from_(Table("company")).select(Field("id")).where(Field("id") == P()).get_sql(), (company_id,)).fetchone():
        err(f"Company {company_id} not found")


def _get_ext_by_id(conn, ext_id):
    """Get extension row by its own id."""
    return conn.execute(Q.from_(Table("automotiveclaw_customer_ext")).select(Table("automotiveclaw_customer_ext").star).where(Field("id") == P()).get_sql(), (ext_id,)).fetchone()


def _get_ext_with_core(conn, ext_id):
    """Get extension + core customer data via JOIN."""
    return conn.execute("""
        SELECT ace.id, ace.naming_series, ace.customer_id, ace.drivers_license,
               ace.customer_type, ace.lead_source, ace.company_id,
               ace.created_at, ace.updated_at,
               c.name as name, c.email, c.phone
        FROM automotiveclaw_customer_ext ace
        JOIN customer c ON ace.customer_id = c.id
        WHERE ace.id = ?
    """, (ext_id,)).fetchone()


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

    email = getattr(args, "email", None)
    phone = getattr(args, "phone", None)

    # Step 1: Create core customer via cross_skill
    core_customer_type = _CORE_CUSTOMER_TYPE.get(customer_type, "individual")
    try:
        result = create_customer(
            customer_name=name,
            company_id=args.company_id,
            customer_type=core_customer_type,
            email=email,
            phone=phone,
        )
    except CrossSkillError as e:
        err(f"Failed to create core customer: {e}")

    core_customer_id = result.get("customer_id") or result.get("id")
    if not core_customer_id:
        err("Failed to create core customer: no ID returned")

    # Step 2: Create extension row
    ext_id = str(uuid.uuid4())
    now = _now_iso()
    conn.company_id = args.company_id
    naming = get_next_name(conn, "automotiveclaw_customer_ext")

    sql, _ = insert_row("automotiveclaw_customer_ext", {"id": P(), "naming_series": P(), "customer_id": P(), "drivers_license": P(), "customer_type": P(), "lead_source": P(), "company_id": P(), "created_at": P(), "updated_at": P()})
    conn.execute(sql, (
        ext_id, naming, core_customer_id,
        getattr(args, "drivers_license", None),
        customer_type, lead_source,
        args.company_id, now, now,
    ))
    audit(conn, SKILL, "auto-add-customer", "automotiveclaw_customer_ext", ext_id,
          new_values={"name": name, "customer_type": customer_type, "core_customer_id": core_customer_id})
    conn.commit()
    ok({"id": ext_id, "customer_id": core_customer_id, "naming_series": naming,
        "name": name, "customer_type": customer_type})


# ===========================================================================
# 2. update-customer
# ===========================================================================
def update_customer(conn, args):
    cust_id = getattr(args, "customer_id", None)
    if not cust_id:
        err("--customer-id is required")
    ext_row = _get_ext_by_id(conn, cust_id)
    if not ext_row:
        err(f"Customer {cust_id} not found")
    ext_data = row_to_dict(ext_row)
    core_customer_id = ext_data["customer_id"]

    # Fields that live in core customer table
    core_updates, core_params, changed = [], [], []
    for arg_name, col_name in {
        "name": "name", "email": "email", "phone": "phone",
    }.items():
        val = getattr(args, arg_name, None)
        if val is not None:
            core_updates.append(f"{col_name} = ?")
            core_params.append(val)
            changed.append(arg_name)

    if core_updates:
        core_updates.append("modified = ?")
        core_params.append(_now_iso())
        core_params.append(core_customer_id)
        conn.execute(f"UPDATE customer SET {', '.join(core_updates)} WHERE id = ?", core_params)

    # Fields that live in extension table
    ext_updates, ext_params = [], []
    for arg_name, col_name in {
        "customer_type": "customer_type",
        "drivers_license": "drivers_license",
        "lead_source": "lead_source",
    }.items():
        val = getattr(args, arg_name, None)
        if val is not None:
            ext_updates.append(f"{col_name} = ?")
            ext_params.append(val)
            changed.append(arg_name)

    if ext_updates:
        ext_updates.append("updated_at = ?")
        ext_params.append(_now_iso())
        ext_params.append(cust_id)
        conn.execute(f"UPDATE automotiveclaw_customer_ext SET {', '.join(ext_updates)} WHERE id = ?", ext_params)

    if not changed:
        err("No fields to update")

    audit(conn, SKILL, "auto-update-customer", "automotiveclaw_customer_ext", cust_id,
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
    row = _get_ext_with_core(conn, cust_id)
    if not row:
        err(f"Customer {cust_id} not found")
    ok(row_to_dict(row))


# ===========================================================================
# 4. list-customers
# ===========================================================================
def list_customers(conn, args):
    where, params = ["1=1"], []
    if getattr(args, "company_id", None):
        where.append("ace.company_id = ?")
        params.append(args.company_id)
    if getattr(args, "customer_type", None):
        where.append("ace.customer_type = ?")
        params.append(args.customer_type)
    if getattr(args, "search", None):
        where.append("(c.name LIKE ? OR c.email LIKE ? OR c.phone LIKE ?)")
        params.extend([f"%{args.search}%"] * 3)

    where_sql = " AND ".join(where)
    total = conn.execute(
        f"""SELECT COUNT(*) FROM automotiveclaw_customer_ext ace
            JOIN customer c ON ace.customer_id = c.id
            WHERE {where_sql}""", params
    ).fetchone()[0]
    params.extend([args.limit, args.offset])
    rows = conn.execute(
        f"""SELECT ace.id, ace.naming_series, ace.customer_id, ace.drivers_license,
                   ace.customer_type, ace.lead_source, ace.company_id,
                   ace.created_at, ace.updated_at,
                   c.name as name, c.email, c.phone
            FROM automotiveclaw_customer_ext ace
            JOIN customer c ON ace.customer_id = c.id
            WHERE {where_sql} ORDER BY ace.created_at DESC LIMIT ? OFFSET ?""",
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
    ext_row = _get_ext_by_id(conn, cust_id)
    if not ext_row:
        err(f"Customer {cust_id} not found")
    core_customer_id = row_to_dict(ext_row)["customer_id"]

    rows = conn.execute("""
        SELECT d.id as deal_id, d.deal_type, d.deal_status, d.selling_price,
               d.delivered_date, v.vin, v.year, v.make, v.model
        FROM automotiveclaw_deal d
        LEFT JOIN automotiveclaw_vehicle v ON d.vehicle_id = v.id
        WHERE d.customer_id = ?
        ORDER BY d.created_at DESC
        LIMIT ? OFFSET ?
    """, (core_customer_id, args.limit, args.offset)).fetchall()
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
    ext_row = _get_ext_by_id(conn, cust_id)
    if not ext_row:
        err(f"Customer {cust_id} not found")
    core_customer_id = row_to_dict(ext_row)["customer_id"]

    rows = conn.execute("""
        SELECT id, naming_series, vehicle_vin, ro_type, ro_status,
               labor_total, parts_total, total, created_at
        FROM automotiveclaw_repair_order
        WHERE customer_id = ?
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    """, (core_customer_id, args.limit, args.offset)).fetchall()
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
