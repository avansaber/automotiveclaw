"""AutomotiveClaw -- inventory domain module

Actions for vehicle inventory, photos, trade-ins (3 tables, 12 actions).
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
    from erpclaw_lib.query import Q, P, Table, Field, fn, Order, insert_row, update_row

    ENTITY_PREFIXES.setdefault("automotiveclaw_vehicle", "VEH-")
    ENTITY_PREFIXES.setdefault("automotiveclaw_trade_in", "TRADE-")
except ImportError:
    pass

SKILL = "automotiveclaw"

_now_iso = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

VALID_CONDITIONS = ("new", "used", "cpo")
VALID_TRANSMISSIONS = ("automatic", "manual", "cvt")
VALID_DRIVETRAINS = ("fwd", "rwd", "awd", "4wd")
VALID_VEHICLE_STATUSES = ("available", "hold", "sold", "traded", "wholesale", "transit")
VALID_TRADE_CONDITIONS = ("excellent", "good", "fair", "poor")
VALID_TRADE_STATUSES = ("pending", "accepted", "rejected")


def _validate_company(conn, company_id):
    if not company_id:
        err("--company-id is required")
    if not conn.execute(Q.from_(Table("company")).select(Field("id")).where(Field("id") == P()).get_sql(), (company_id,)).fetchone():
        err(f"Company {company_id} not found")


# ===========================================================================
# 1. add-vehicle
# ===========================================================================
def add_vehicle(conn, args):
    _validate_company(conn, args.company_id)
    make = getattr(args, "make", None)
    model = getattr(args, "model", None)
    if not make:
        err("--make is required")
    if not model:
        err("--model is required")

    vin = getattr(args, "vin", None)
    if vin:
        existing = conn.execute(Q.from_(Table("automotiveclaw_vehicle")).select(Field("id")).where(Field("vin") == P()).get_sql(), (vin,)).fetchone()
        if existing:
            err(f"Vehicle with VIN {vin} already exists")

    vehicle_condition = getattr(args, "vehicle_condition", None) or "new"
    if vehicle_condition not in VALID_CONDITIONS:
        err(f"Invalid vehicle_condition: {vehicle_condition}. Must be one of: {', '.join(VALID_CONDITIONS)}")

    transmission = getattr(args, "transmission", None) or "automatic"
    if transmission not in VALID_TRANSMISSIONS:
        err(f"Invalid transmission: {transmission}. Must be one of: {', '.join(VALID_TRANSMISSIONS)}")

    drivetrain = getattr(args, "drivetrain", None) or "fwd"
    if drivetrain not in VALID_DRIVETRAINS:
        err(f"Invalid drivetrain: {drivetrain}. Must be one of: {', '.join(VALID_DRIVETRAINS)}")

    veh_id = str(uuid.uuid4())
    now = _now_iso()
    conn.company_id = args.company_id
    naming = get_next_name(conn, "automotiveclaw_vehicle")

    year_val = int(args.year) if getattr(args, "year", None) else None
    msrp = str(round_currency(to_decimal(args.msrp))) if getattr(args, "msrp", None) else None
    invoice_price = str(round_currency(to_decimal(args.invoice_price))) if getattr(args, "invoice_price", None) else None
    selling_price = str(round_currency(to_decimal(args.selling_price))) if getattr(args, "selling_price", None) else None
    internet_price = str(round_currency(to_decimal(args.internet_price))) if getattr(args, "internet_price", None) else None

    sql, _ = insert_row("automotiveclaw_vehicle", {"id": P(), "naming_series": P(), "vin": P(), "stock_number": P(), "year": P(), "make": P(), "model": P(), "trim": P(), "color_exterior": P(), "color_interior": P(), "mileage": P(), "vehicle_condition": P(), "body_style": P(), "engine": P(), "transmission": P(), "drivetrain": P(), "msrp": P(), "invoice_price": P(), "selling_price": P(), "internet_price": P(), "lot_location": P(), "days_in_stock": P(), "vehicle_status": P(), "company_id": P(), "created_at": P(), "updated_at": P()})
    conn.execute(sql, (
        veh_id, naming, vin,
        getattr(args, "stock_number", None),
        year_val, make, model,
        getattr(args, "trim", None),
        getattr(args, "color_exterior", None),
        getattr(args, "color_interior", None),
        getattr(args, "mileage", None),
        vehicle_condition,
        getattr(args, "body_style", None),
        getattr(args, "engine", None),
        transmission, drivetrain,
        msrp, invoice_price, selling_price, internet_price,
        getattr(args, "lot_location", None),
        0, "available",
        args.company_id, now, now,
    ))
    audit(conn, SKILL, "auto-add-vehicle", "automotiveclaw_vehicle", veh_id,
          new_values={"vin": vin, "make": make, "model": model})
    conn.commit()
    ok({
        "id": veh_id, "naming_series": naming, "vin": vin,
        "make": make, "model": model, "vehicle_status": "available",
    })


# ===========================================================================
# 2. update-vehicle
# ===========================================================================
def update_vehicle(conn, args):
    veh_id = getattr(args, "vehicle_id", None)
    if not veh_id:
        err("--vehicle-id is required")
    if not conn.execute(Q.from_(Table("automotiveclaw_vehicle")).select(Field("id")).where(Field("id") == P()).get_sql(), (veh_id,)).fetchone():
        err(f"Vehicle {veh_id} not found")

    updates, params, changed = [], [], []
    for arg_name, col_name in {
        "lot_location": "lot_location",
        "vehicle_condition": "vehicle_condition",
        "mileage": "mileage",
    }.items():
        val = getattr(args, arg_name, None)
        if val is not None:
            updates.append(f"{col_name} = ?")
            params.append(val)
            changed.append(col_name)

    for arg_name, col_name in {
        "selling_price": "selling_price",
        "internet_price": "internet_price",
    }.items():
        val = getattr(args, arg_name, None)
        if val is not None:
            updates.append(f"{col_name} = ?")
            params.append(str(round_currency(to_decimal(val))))
            changed.append(col_name)

    if not updates:
        err("No fields to update")

    updates.append("updated_at = ?")
    params.append(_now_iso())
    params.append(veh_id)
    conn.execute(f"UPDATE automotiveclaw_vehicle SET {', '.join(updates)} WHERE id = ?", params)
    audit(conn, SKILL, "auto-update-vehicle", "automotiveclaw_vehicle", veh_id,
          new_values={"updated_fields": changed})
    conn.commit()
    ok({"id": veh_id, "updated_fields": changed})


# ===========================================================================
# 3. get-vehicle
# ===========================================================================
def get_vehicle(conn, args):
    veh_id = getattr(args, "vehicle_id", None)
    if not veh_id:
        err("--vehicle-id is required")
    row = conn.execute(Q.from_(Table("automotiveclaw_vehicle")).select(Table("automotiveclaw_vehicle").star).where(Field("id") == P()).get_sql(), (veh_id,)).fetchone()
    if not row:
        err(f"Vehicle {veh_id} not found")
    ok(row_to_dict(row))


# ===========================================================================
# 4. list-vehicles
# ===========================================================================
def list_vehicles(conn, args):
    where, params = ["1=1"], []
    if getattr(args, "company_id", None):
        where.append("company_id = ?")
        params.append(args.company_id)
    if getattr(args, "vehicle_condition", None):
        where.append("vehicle_condition = ?")
        params.append(args.vehicle_condition)
    if getattr(args, "vehicle_status", None):
        where.append("vehicle_status = ?")
        params.append(args.vehicle_status)
    if getattr(args, "make", None):
        where.append("make = ?")
        params.append(args.make)
    if getattr(args, "search", None):
        where.append("(make LIKE ? OR model LIKE ? OR vin LIKE ? OR stock_number LIKE ?)")
        params.extend([f"%{args.search}%"] * 4)

    where_sql = " AND ".join(where)
    total = conn.execute(
        f"SELECT COUNT(*) FROM automotiveclaw_vehicle WHERE {where_sql}", params
    ).fetchone()[0]
    params.extend([args.limit, args.offset])
    rows = conn.execute(
        f"SELECT * FROM automotiveclaw_vehicle WHERE {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        params
    ).fetchall()
    ok({
        "rows": [row_to_dict(r) for r in rows],
        "total_count": total, "limit": args.limit, "offset": args.offset,
        "has_more": (args.offset + args.limit) < total,
    })


# ===========================================================================
# 5. add-vehicle-photo
# ===========================================================================
def add_vehicle_photo(conn, args):
    veh_id = getattr(args, "vehicle_id", None)
    if not veh_id:
        err("--vehicle-id is required")
    _validate_company(conn, args.company_id)
    if not conn.execute(Q.from_(Table("automotiveclaw_vehicle")).select(Field("id")).where(Field("id") == P()).get_sql(), (veh_id,)).fetchone():
        err(f"Vehicle {veh_id} not found")

    photo_url = getattr(args, "photo_url", None)
    if not photo_url:
        err("--photo-url is required")

    photo_id = str(uuid.uuid4())
    photo_order = int(getattr(args, "photo_order", None) or 0)

    sql, _ = insert_row("automotiveclaw_vehicle_photo", {"id": P(), "vehicle_id": P(), "photo_url": P(), "photo_order": P(), "caption": P(), "company_id": P(), "created_at": P()})
    conn.execute(sql, (
        photo_id, veh_id, photo_url, photo_order,
        getattr(args, "caption", None),
        args.company_id, _now_iso(),
    ))
    conn.commit()
    ok({"id": photo_id, "vehicle_id": veh_id, "photo_url": photo_url})


# ===========================================================================
# 6. list-vehicle-photos
# ===========================================================================
def list_vehicle_photos(conn, args):
    veh_id = getattr(args, "vehicle_id", None)
    if not veh_id:
        err("--vehicle-id is required")

    rows = conn.execute(
        "SELECT * FROM automotiveclaw_vehicle_photo WHERE vehicle_id = ? ORDER BY photo_order LIMIT ? OFFSET ?",
        (veh_id, args.limit, args.offset)
    ).fetchall()
    ok({"vehicle_id": veh_id, "rows": [row_to_dict(r) for r in rows], "count": len(rows)})


# ===========================================================================
# 7. mark-vehicle-sold
# ===========================================================================
def mark_vehicle_sold(conn, args):
    veh_id = getattr(args, "vehicle_id", None)
    if not veh_id:
        err("--vehicle-id is required")
    row = conn.execute(Q.from_(Table("automotiveclaw_vehicle")).select(Table("automotiveclaw_vehicle").star).where(Field("id") == P()).get_sql(), (veh_id,)).fetchone()
    if not row:
        err(f"Vehicle {veh_id} not found")
    data = row_to_dict(row)
    if data["vehicle_status"] == "sold":
        err("Vehicle is already marked as sold")

    conn.execute(
        "UPDATE automotiveclaw_vehicle SET vehicle_status = 'sold', updated_at = ? WHERE id = ?",
        (_now_iso(), veh_id)
    )
    audit(conn, SKILL, "auto-mark-vehicle-sold", "automotiveclaw_vehicle", veh_id,
          new_values={"vehicle_status": "sold"})
    conn.commit()
    ok({"id": veh_id, "vehicle_status": "sold"})


# ===========================================================================
# 8. add-trade-in-appraisal
# ===========================================================================
def add_trade_in_appraisal(conn, args):
    _validate_company(conn, args.company_id)

    customer_id = getattr(args, "customer_id", None)
    if not customer_id:
        err("--customer-id is required")
    if not conn.execute(Q.from_(Table("customer")).select(Field("id")).where(Field("id") == P()).get_sql(), (customer_id,)).fetchone():
        err(f"Customer {customer_id} not found")

    vin = getattr(args, "vin", None)
    if not vin:
        err("--vin is required")
    make = getattr(args, "make", None)
    if not make:
        err("--make is required")
    model_val = getattr(args, "model", None)
    if not model_val:
        err("--model is required")

    trade_id = str(uuid.uuid4())
    now = _now_iso()
    conn.company_id = args.company_id
    naming = get_next_name(conn, "automotiveclaw_trade_in")

    trade_condition = getattr(args, "trade_condition", None) or "good"
    if trade_condition not in VALID_TRADE_CONDITIONS:
        err(f"Invalid trade_condition: {trade_condition}. Must be one of: {', '.join(VALID_TRADE_CONDITIONS)}")

    offered = str(round_currency(to_decimal(args.offered_amount))) if getattr(args, "offered_amount", None) else None
    acv = str(round_currency(to_decimal(args.acv))) if getattr(args, "acv", None) else None
    payoff = str(round_currency(to_decimal(args.payoff_amount))) if getattr(args, "payoff_amount", None) else None
    year_val = int(args.year) if getattr(args, "year", None) else None

    sql, _ = insert_row("automotiveclaw_trade_in", {"id": P(), "naming_series": P(), "vehicle_id": P(), "customer_id": P(), "vin": P(), "year": P(), "make": P(), "model": P(), "mileage": P(), "trade_condition": P(), "offered_amount": P(), "acv": P(), "payoff_amount": P(), "trade_status": P(), "company_id": P(), "created_at": P(), "updated_at": P()})
    conn.execute(sql, (
        trade_id, naming,
        getattr(args, "vehicle_id", None),
        customer_id, vin, year_val, make, model_val,
        getattr(args, "mileage", None),
        trade_condition, offered, acv, payoff,
        "pending", args.company_id, now, now,
    ))
    audit(conn, SKILL, "auto-add-trade-in-appraisal", "automotiveclaw_trade_in", trade_id,
          new_values={"vin": vin, "make": make, "model": model_val})
    conn.commit()
    ok({
        "id": trade_id, "naming_series": naming, "vin": vin,
        "trade_status": "pending", "trade_condition": trade_condition,
    })


# ===========================================================================
# 9. list-trade-in-appraisals
# ===========================================================================
def list_trade_in_appraisals(conn, args):
    where, params = ["1=1"], []
    if getattr(args, "company_id", None):
        where.append("company_id = ?")
        params.append(args.company_id)
    if getattr(args, "customer_id", None):
        where.append("customer_id = ?")
        params.append(args.customer_id)
    if getattr(args, "trade_status", None):
        where.append("trade_status = ?")
        params.append(args.trade_status)

    where_sql = " AND ".join(where)
    total = conn.execute(
        f"SELECT COUNT(*) FROM automotiveclaw_trade_in WHERE {where_sql}", params
    ).fetchone()[0]
    params.extend([args.limit, args.offset])
    rows = conn.execute(
        f"SELECT * FROM automotiveclaw_trade_in WHERE {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        params
    ).fetchall()
    ok({
        "rows": [row_to_dict(r) for r in rows],
        "total_count": total, "limit": args.limit, "offset": args.offset,
        "has_more": (args.offset + args.limit) < total,
    })


# ===========================================================================
# 10. inventory-aging-report
# ===========================================================================
def inventory_aging_report(conn, args):
    _validate_company(conn, args.company_id)
    rows = conn.execute("""
        SELECT id, naming_series, vin, year, make, model, selling_price,
               days_in_stock, vehicle_status, vehicle_condition
        FROM automotiveclaw_vehicle
        WHERE company_id = ? AND vehicle_status = 'available'
        ORDER BY days_in_stock DESC
        LIMIT ? OFFSET ?
    """, (args.company_id, args.limit, args.offset)).fetchall()
    ok({
        "rows": [row_to_dict(r) for r in rows],
        "count": len(rows),
    })


# ===========================================================================
# 11. inventory-summary
# ===========================================================================
def inventory_summary(conn, args):
    _validate_company(conn, args.company_id)

    total = conn.execute(Q.from_(Table("automotiveclaw_vehicle")).select(fn.Count("*")).where(Field("company_id") == P()).get_sql(), (args.company_id,)).fetchone()[0]

    by_status = conn.execute(
        "SELECT vehicle_status, COUNT(*) as cnt FROM automotiveclaw_vehicle WHERE company_id = ? GROUP BY vehicle_status",
        (args.company_id,)
    ).fetchall()

    by_condition = conn.execute(
        "SELECT vehicle_condition, COUNT(*) as cnt FROM automotiveclaw_vehicle WHERE company_id = ? GROUP BY vehicle_condition",
        (args.company_id,)
    ).fetchall()

    ok({
        "total_vehicles": total,
        "by_status": {r["vehicle_status"]: r["cnt"] for r in by_status},
        "by_condition": {r["vehicle_condition"]: r["cnt"] for r in by_condition},
    })


# ===========================================================================
# 12. vin-lookup
# ===========================================================================
def vin_lookup(conn, args):
    vin = getattr(args, "vin", None)
    if not vin:
        err("--vin is required")
    row = conn.execute(Q.from_(Table("automotiveclaw_vehicle")).select(Table("automotiveclaw_vehicle").star).where(Field("vin") == P()).get_sql(), (vin,)).fetchone()
    if not row:
        err(f"No vehicle found with VIN {vin}")
    ok(row_to_dict(row))


# ---------------------------------------------------------------------------
# Action registry
# ---------------------------------------------------------------------------
ACTIONS = {
    "auto-add-vehicle": add_vehicle,
    "auto-update-vehicle": update_vehicle,
    "auto-get-vehicle": get_vehicle,
    "auto-list-vehicles": list_vehicles,
    "auto-add-vehicle-photo": add_vehicle_photo,
    "auto-list-vehicle-photos": list_vehicle_photos,
    "auto-mark-vehicle-sold": mark_vehicle_sold,
    "auto-add-trade-in-appraisal": add_trade_in_appraisal,
    "auto-list-trade-in-appraisals": list_trade_in_appraisals,
    "auto-inventory-aging-report": inventory_aging_report,
    "auto-inventory-summary": inventory_summary,
    "auto-vin-lookup": vin_lookup,
}
