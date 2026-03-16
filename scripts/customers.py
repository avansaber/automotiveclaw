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
    from erpclaw_lib.query import (
        Q, P, Table, Field, fn, Order, LiteralValue,
        insert_row, update_row, dynamic_update,
    )

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

# ── Table aliases ──
_ace = Table("automotiveclaw_customer_ext")
_c = Table("customer")
_d = Table("automotiveclaw_deal")
_v = Table("automotiveclaw_vehicle")
_ro = Table("automotiveclaw_repair_order")
_company = Table("company")


def _validate_company(conn, company_id):
    if not company_id:
        err("--company-id is required")
    q = Q.from_(_company).select(_company.id).where(_company.id == P())
    if not conn.execute(q.get_sql(), (company_id,)).fetchone():
        err(f"Company {company_id} not found")


def _get_ext_by_id(conn, ext_id):
    """Get extension row by its own id."""
    q = Q.from_(_ace).select(_ace.star).where(_ace.id == P())
    return conn.execute(q.get_sql(), (ext_id,)).fetchone()


def _get_ext_with_core(conn, ext_id):
    """Get extension + core customer data via JOIN."""
    q = (
        Q.from_(_ace)
        .join(_c).on(_ace.customer_id == _c.id)
        .select(
            _ace.id, _ace.naming_series, _ace.customer_id, _ace.drivers_license,
            _ace.customer_type, _ace.lead_source, _ace.company_id,
            _ace.created_at, _ace.updated_at,
            _c.name.as_("name"), _c.email, _c.phone,
        )
        .where(_ace.id == P())
    )
    return conn.execute(q.get_sql(), (ext_id,)).fetchone()


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
    core_data = {}
    changed = []
    for arg_name, col_name in {
        "name": "name", "email": "email", "phone": "phone",
    }.items():
        val = getattr(args, arg_name, None)
        if val is not None:
            core_data[col_name] = val
            changed.append(arg_name)

    if core_data:
        core_data["modified"] = _now_iso()
        sql, params = dynamic_update("customer", core_data, where={"id": core_customer_id})
        conn.execute(sql, params)

    # Fields that live in extension table
    ext_data_upd = {}
    for arg_name, col_name in {
        "customer_type": "customer_type",
        "drivers_license": "drivers_license",
        "lead_source": "lead_source",
    }.items():
        val = getattr(args, arg_name, None)
        if val is not None:
            ext_data_upd[col_name] = val
            changed.append(arg_name)

    if ext_data_upd:
        ext_data_upd["updated_at"] = _now_iso()
        sql, params = dynamic_update("automotiveclaw_customer_ext", ext_data_upd, where={"id": cust_id})
        conn.execute(sql, params)

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
    # Build base query with JOIN
    base = Q.from_(_ace).join(_c).on(_ace.customer_id == _c.id)

    # Build WHERE conditions
    conditions = []
    params = []
    if getattr(args, "company_id", None):
        conditions.append(_ace.company_id == P())
        params.append(args.company_id)
    if getattr(args, "customer_type", None):
        conditions.append(_ace.customer_type == P())
        params.append(args.customer_type)
    if getattr(args, "search", None):
        # LIKE requires LiteralValue for the pattern in PyPika; use raw criterion
        conditions.append(
            (_c.name.like(P()) | _c.email.like(P()) | _c.phone.like(P()))
        )
        params.extend([f"%{args.search}%"] * 3)

    # Count query
    count_q = base.select(fn.Count("*"))
    for cond in conditions:
        count_q = count_q.where(cond)
    total = conn.execute(count_q.get_sql(), params).fetchone()[0]

    # Data query
    data_q = base.select(
        _ace.id, _ace.naming_series, _ace.customer_id, _ace.drivers_license,
        _ace.customer_type, _ace.lead_source, _ace.company_id,
        _ace.created_at, _ace.updated_at,
        _c.name.as_("name"), _c.email, _c.phone,
    )
    for cond in conditions:
        data_q = data_q.where(cond)
    data_q = data_q.orderby(_ace.created_at, order=Order.desc).limit(P()).offset(P())

    rows = conn.execute(data_q.get_sql(), params + [args.limit, args.offset]).fetchall()
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

    q = (
        Q.from_(_d)
        .left_join(_v).on(_d.vehicle_id == _v.id)
        .select(
            _d.id.as_("deal_id"), _d.deal_type, _d.deal_status, _d.selling_price,
            _d.delivered_date, _v.vin, _v.year, _v.make, _v.model,
        )
        .where(_d.customer_id == P())
        .orderby(_d.created_at, order=Order.desc)
        .limit(P()).offset(P())
    )
    rows = conn.execute(q.get_sql(), (core_customer_id, args.limit, args.offset)).fetchall()
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

    q = (
        Q.from_(_ro)
        .select(
            _ro.id, _ro.naming_series, _ro.vehicle_vin, _ro.ro_type, _ro.ro_status,
            _ro.labor_total, _ro.parts_total, _ro.total, _ro.created_at,
        )
        .where(_ro.customer_id == P())
        .orderby(_ro.created_at, order=Order.desc)
        .limit(P()).offset(P())
    )
    rows = conn.execute(q.get_sql(), (core_customer_id, args.limit, args.offset)).fetchall()
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
