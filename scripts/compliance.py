"""AutomotiveClaw -- compliance domain module

Actions for dealer compliance checks (1 table, 6 actions).
Imported by db_query.py (unified router).
"""
import os
import sys
import uuid
from datetime import datetime, timezone

try:
    sys.path.insert(0, os.path.expanduser("~/.openclaw/erpclaw/lib"))
    from erpclaw_lib.response import ok, err, row_to_dict
    from erpclaw_lib.audit import audit
    from erpclaw_lib.query import (
        Q, P, Table, Field, fn, Order,
        insert_row, update_row,
    )
except ImportError:
    pass

SKILL = "automotiveclaw"

_now_iso = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

VALID_CHECK_TYPES = ("ofac", "red_flag", "tila", "odometer", "buyers_guide")
VALID_CHECK_RESULTS = ("pass", "fail", "pending")

# ── Table aliases ──
_company = Table("company")
_vehicle = Table("automotiveclaw_vehicle")
_deal = Table("automotiveclaw_deal")
_cc = Table("automotiveclaw_compliance_check")
_ace = Table("automotiveclaw_customer_ext")
_c = Table("customer")


def _validate_company(conn, company_id):
    if not company_id:
        err("--company-id is required")
    q = Q.from_(_company).select(_company.id).where(_company.id == P())
    if not conn.execute(q.get_sql(), (company_id,)).fetchone():
        err(f"Company {company_id} not found")


# ===========================================================================
# 1. generate-buyers-guide
# ===========================================================================
def generate_buyers_guide(conn, args):
    vehicle_id = getattr(args, "vehicle_id", None)
    if not vehicle_id:
        err("--vehicle-id is required")
    _validate_company(conn, args.company_id)

    q = Q.from_(_vehicle).select(_vehicle.star).where(_vehicle.id == P())
    row = conn.execute(q.get_sql(), (vehicle_id,)).fetchone()
    if not row:
        err(f"Vehicle {vehicle_id} not found")
    data = row_to_dict(row)

    guide = {
        "vin": data.get("vin"),
        "year": data.get("year"),
        "make": data.get("make"),
        "model": data.get("model"),
        "vehicle_condition": data.get("vehicle_condition"),
        "warranty_type": "as_is" if data.get("vehicle_condition") == "used" else "manufacturer",
        "document_type": "buyers_guide",
        "generated_at": _now_iso(),
    }
    ok(guide)


# ===========================================================================
# 2. generate-odometer-statement
# ===========================================================================
def generate_odometer_statement(conn, args):
    vehicle_id = getattr(args, "vehicle_id", None)
    if not vehicle_id:
        err("--vehicle-id is required")
    _validate_company(conn, args.company_id)

    q = Q.from_(_vehicle).select(_vehicle.star).where(_vehicle.id == P())
    row = conn.execute(q.get_sql(), (vehicle_id,)).fetchone()
    if not row:
        err(f"Vehicle {vehicle_id} not found")
    data = row_to_dict(row)

    mileage = getattr(args, "mileage", None) or data.get("mileage")

    statement = {
        "vin": data.get("vin"),
        "year": data.get("year"),
        "make": data.get("make"),
        "model": data.get("model"),
        "odometer_reading": mileage,
        "document_type": "odometer_statement",
        "generated_at": _now_iso(),
    }
    ok(statement)


# ===========================================================================
# 3. add-compliance-check
# ===========================================================================
def add_compliance_check(conn, args):
    deal_id = getattr(args, "deal_id", None)
    if not deal_id:
        err("--deal-id is required")
    q = Q.from_(_deal).select(_deal.id).where(_deal.id == P())
    if not conn.execute(q.get_sql(), (deal_id,)).fetchone():
        err(f"Deal {deal_id} not found")

    _validate_company(conn, args.company_id)

    check_type = getattr(args, "check_type", None)
    if not check_type:
        err("--check-type is required")
    if check_type not in VALID_CHECK_TYPES:
        err(f"Invalid check_type: {check_type}. Must be one of: {', '.join(VALID_CHECK_TYPES)}")

    check_result = getattr(args, "check_result", None) or "pending"
    if check_result not in VALID_CHECK_RESULTS:
        err(f"Invalid check_result: {check_result}. Must be one of: {', '.join(VALID_CHECK_RESULTS)}")

    check_id = str(uuid.uuid4())
    sql, _ = insert_row("automotiveclaw_compliance_check", {"id": P(), "deal_id": P(), "check_type": P(), "check_result": P(), "checked_by": P(), "check_date": P(), "notes": P(), "company_id": P(), "created_at": P()})
    conn.execute(sql, (
        check_id, deal_id, check_type, check_result,
        getattr(args, "checked_by", None),
        getattr(args, "check_date", None) or _now_iso()[:10],
        getattr(args, "notes", None),
        args.company_id, _now_iso(),
    ))
    audit(conn, SKILL, "auto-add-compliance-check", "automotiveclaw_compliance_check", check_id,
          new_values={"deal_id": deal_id, "check_type": check_type})
    conn.commit()
    ok({"id": check_id, "deal_id": deal_id, "check_type": check_type, "check_result": check_result})


# ===========================================================================
# 4. list-compliance-checks
# ===========================================================================
def list_compliance_checks(conn, args):
    # Build WHERE conditions dynamically
    conditions = []
    params = []
    if getattr(args, "deal_id", None):
        conditions.append(_cc.deal_id == P())
        params.append(args.deal_id)
    if getattr(args, "company_id", None):
        conditions.append(_cc.company_id == P())
        params.append(args.company_id)
    if getattr(args, "check_type", None):
        conditions.append(_cc.check_type == P())
        params.append(args.check_type)
    if getattr(args, "check_result", None):
        conditions.append(_cc.check_result == P())
        params.append(args.check_result)

    # Count query
    count_q = Q.from_(_cc).select(fn.Count("*"))
    for cond in conditions:
        count_q = count_q.where(cond)
    total = conn.execute(count_q.get_sql(), params).fetchone()[0]

    # Data query
    data_q = Q.from_(_cc).select(_cc.star)
    for cond in conditions:
        data_q = data_q.where(cond)
    data_q = data_q.orderby(_cc.created_at, order=Order.desc).limit(P()).offset(P())

    rows = conn.execute(data_q.get_sql(), params + [args.limit, args.offset]).fetchall()
    ok({
        "rows": [row_to_dict(r) for r in rows],
        "total_count": total, "limit": args.limit, "offset": args.offset,
        "has_more": (args.offset + args.limit) < total,
    })


# ===========================================================================
# 5. ofac-screening-check
# ===========================================================================
def ofac_screening_check(conn, args):
    customer_id = getattr(args, "customer_id", None)
    if not customer_id:
        err("--customer-id is required")
    _validate_company(conn, args.company_id)

    q = (
        Q.from_(_ace)
        .join(_c).on(_ace.customer_id == _c.id)
        .select(_ace.id, _c.name.as_("name"))
        .where(_ace.id == P())
    )
    row = conn.execute(q.get_sql(), (customer_id,)).fetchone()
    if not row:
        err(f"Customer {customer_id} not found")
    data = row_to_dict(row)

    # Local-only screening (no network calls) -- always passes
    ok({
        "customer_id": customer_id,
        "customer_name": data.get("name"),
        "screening_result": "pass",
        "screening_type": "ofac",
        "note": "Local-only screening. No network calls. Manual OFAC verification recommended for production.",
        "screened_at": _now_iso(),
    })


# ===========================================================================
# 6. compliance-summary
# ===========================================================================
def compliance_summary(conn, args):
    _validate_company(conn, args.company_id)

    q = Q.from_(_cc).select(fn.Count("*")).where(_cc.company_id == P())
    total = conn.execute(q.get_sql(), (args.company_id,)).fetchone()[0]

    by_type_q = (
        Q.from_(_cc)
        .select(_cc.check_type, fn.Count("*").as_("cnt"))
        .where(_cc.company_id == P())
        .groupby(_cc.check_type)
    )
    by_type = conn.execute(by_type_q.get_sql(), (args.company_id,)).fetchall()

    by_result_q = (
        Q.from_(_cc)
        .select(_cc.check_result, fn.Count("*").as_("cnt"))
        .where(_cc.company_id == P())
        .groupby(_cc.check_result)
    )
    by_result = conn.execute(by_result_q.get_sql(), (args.company_id,)).fetchall()

    ok({
        "total_checks": total,
        "by_type": {r["check_type"]: r["cnt"] for r in by_type},
        "by_result": {r["check_result"]: r["cnt"] for r in by_result},
    })


# ---------------------------------------------------------------------------
# Action registry
# ---------------------------------------------------------------------------
ACTIONS = {
    "auto-generate-buyers-guide": generate_buyers_guide,
    "auto-generate-odometer-statement": generate_odometer_statement,
    "auto-add-compliance-check": add_compliance_check,
    "auto-list-compliance-checks": list_compliance_checks,
    "auto-ofac-screening-check": ofac_screening_check,
    "auto-compliance-summary": compliance_summary,
}
