"""AutomotiveClaw -- deals domain module

Actions for deal management, buyer orders, and deal reports (2 tables, 12 actions).
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

    ENTITY_PREFIXES.setdefault("automotiveclaw_deal", "DEAL-")
except ImportError:
    pass

try:
    from erpclaw_lib.gl_posting import insert_gl_entries, reverse_gl_entries
    HAS_GL = True
except ImportError:
    HAS_GL = False

SKILL = "automotiveclaw"

_now_iso = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

VALID_DEAL_TYPES = ("retail", "lease", "wholesale", "fleet")
VALID_DEAL_STATUSES = ("pending", "negotiating", "submitted", "approved", "funded", "delivered", "unwound")


def _validate_company(conn, company_id):
    if not company_id:
        err("--company-id is required")
    if not conn.execute("SELECT id FROM company WHERE id = ?", (company_id,)).fetchone():
        err(f"Company {company_id} not found")


def _to_money(val):
    if val is None:
        return None
    return str(round_currency(to_decimal(val)))


def _calc_gross(deal_data):
    """Recalculate front gross from deal fields."""
    selling = to_decimal(deal_data.get("selling_price") or "0")
    trade_allow = to_decimal(deal_data.get("trade_allowance") or "0")
    trade_payoff = to_decimal(deal_data.get("trade_payoff") or "0")
    down = to_decimal(deal_data.get("down_payment") or "0")
    rebates = to_decimal(deal_data.get("rebates") or "0")
    front_gross = selling - trade_allow + trade_payoff - rebates
    return str(round_currency(front_gross))


# ===========================================================================
# 1. add-deal
# ===========================================================================
def add_deal(conn, args):
    _validate_company(conn, args.company_id)

    vehicle_id = getattr(args, "vehicle_id", None)
    if not vehicle_id:
        err("--vehicle-id is required")
    if not conn.execute("SELECT id FROM automotiveclaw_vehicle WHERE id = ?", (vehicle_id,)).fetchone():
        err(f"Vehicle {vehicle_id} not found")

    customer_id = getattr(args, "customer_id", None)
    if not customer_id:
        err("--customer-id is required")
    if not conn.execute("SELECT id FROM customer WHERE id = ?", (customer_id,)).fetchone():
        err(f"Customer {customer_id} not found")

    selling_price = getattr(args, "selling_price", None)
    if not selling_price:
        err("--selling-price is required")

    deal_type = getattr(args, "deal_type", None) or "retail"
    if deal_type not in VALID_DEAL_TYPES:
        err(f"Invalid deal_type: {deal_type}. Must be one of: {', '.join(VALID_DEAL_TYPES)}")

    deal_id = str(uuid.uuid4())
    now = _now_iso()
    conn.company_id = args.company_id
    naming = get_next_name(conn, "automotiveclaw_deal")

    sp = _to_money(selling_price)
    ta = _to_money(getattr(args, "trade_allowance", None))
    tp = _to_money(getattr(args, "trade_payoff", None))
    dp = _to_money(getattr(args, "down_payment", None))
    rb = _to_money(getattr(args, "rebates", None))

    # Calculate front gross
    front_gross = str(round_currency(
        to_decimal(sp or "0") - to_decimal(ta or "0") + to_decimal(tp or "0") - to_decimal(rb or "0")
    ))

    conn.execute("""
        INSERT INTO automotiveclaw_deal (
            id, naming_series, vehicle_id, customer_id, salesperson,
            deal_type, selling_price, trade_allowance, trade_payoff,
            down_payment, rebates, front_gross, back_gross, total_gross,
            deal_status, company_id, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        deal_id, naming, vehicle_id, customer_id,
        getattr(args, "salesperson", None),
        deal_type, sp, ta, tp, dp, rb,
        front_gross, "0.00", front_gross,
        "pending", args.company_id, now, now,
    ))
    audit(conn, SKILL, "auto-add-deal", "automotiveclaw_deal", deal_id,
          new_values={"vehicle_id": vehicle_id, "customer_id": customer_id, "deal_type": deal_type})
    conn.commit()
    ok({
        "id": deal_id, "naming_series": naming, "deal_type": deal_type,
        "deal_status": "pending", "selling_price": sp, "front_gross": front_gross,
    })


# ===========================================================================
# 2. update-deal
# ===========================================================================
def update_deal(conn, args):
    deal_id = getattr(args, "deal_id", None)
    if not deal_id:
        err("--deal-id is required")
    if not conn.execute("SELECT id FROM automotiveclaw_deal WHERE id = ?", (deal_id,)).fetchone():
        err(f"Deal {deal_id} not found")

    updates, params, changed = [], [], []
    for arg_name, col_name in {
        "salesperson": "salesperson",
    }.items():
        val = getattr(args, arg_name, None)
        if val is not None:
            updates.append(f"{col_name} = ?")
            params.append(val)
            changed.append(col_name)

    deal_status = getattr(args, "deal_status", None)
    if deal_status is not None:
        if deal_status not in VALID_DEAL_STATUSES:
            err(f"Invalid deal_status: {deal_status}. Must be one of: {', '.join(VALID_DEAL_STATUSES)}")
        updates.append("deal_status = ?")
        params.append(deal_status)
        changed.append("deal_status")

    for arg_name, col_name in {
        "selling_price": "selling_price",
        "down_payment": "down_payment",
        "rebates": "rebates",
    }.items():
        val = getattr(args, arg_name, None)
        if val is not None:
            updates.append(f"{col_name} = ?")
            params.append(_to_money(val))
            changed.append(col_name)

    if not updates:
        err("No fields to update")

    updates.append("updated_at = ?")
    params.append(_now_iso())
    params.append(deal_id)
    conn.execute(f"UPDATE automotiveclaw_deal SET {', '.join(updates)} WHERE id = ?", params)
    audit(conn, SKILL, "auto-update-deal", "automotiveclaw_deal", deal_id,
          new_values={"updated_fields": changed})
    conn.commit()
    ok({"id": deal_id, "updated_fields": changed})


# ===========================================================================
# 3. get-deal
# ===========================================================================
def get_deal(conn, args):
    deal_id = getattr(args, "deal_id", None)
    if not deal_id:
        err("--deal-id is required")
    row = conn.execute("SELECT * FROM automotiveclaw_deal WHERE id = ?", (deal_id,)).fetchone()
    if not row:
        err(f"Deal {deal_id} not found")
    data = row_to_dict(row)

    # Include F&I products
    fi_rows = conn.execute(
        "SELECT * FROM automotiveclaw_deal_fi_product WHERE deal_id = ?", (deal_id,)
    ).fetchall()
    data["fi_products"] = [row_to_dict(r) for r in fi_rows]
    data["fi_product_count"] = len(fi_rows)

    # Include buyer order if exists
    bo = conn.execute(
        "SELECT * FROM automotiveclaw_buyer_order WHERE deal_id = ?", (deal_id,)
    ).fetchone()
    data["buyer_order"] = row_to_dict(bo) if bo else None

    ok(data)


# ===========================================================================
# 4. list-deals
# ===========================================================================
def list_deals(conn, args):
    where, params = ["1=1"], []
    if getattr(args, "company_id", None):
        where.append("company_id = ?")
        params.append(args.company_id)
    if getattr(args, "customer_id", None):
        where.append("customer_id = ?")
        params.append(args.customer_id)
    if getattr(args, "deal_status", None):
        where.append("deal_status = ?")
        params.append(args.deal_status)
    if getattr(args, "deal_type", None):
        where.append("deal_type = ?")
        params.append(args.deal_type)
    if getattr(args, "search", None):
        where.append("(salesperson LIKE ?)")
        params.append(f"%{args.search}%")

    where_sql = " AND ".join(where)
    total = conn.execute(
        f"SELECT COUNT(*) FROM automotiveclaw_deal WHERE {where_sql}", params
    ).fetchone()[0]
    params.extend([args.limit, args.offset])
    rows = conn.execute(
        f"SELECT * FROM automotiveclaw_deal WHERE {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        params
    ).fetchall()
    ok({
        "rows": [row_to_dict(r) for r in rows],
        "total_count": total, "limit": args.limit, "offset": args.offset,
        "has_more": (args.offset + args.limit) < total,
    })


# ===========================================================================
# 5. add-deal-trade
# ===========================================================================
def add_deal_trade(conn, args):
    deal_id = getattr(args, "deal_id", None)
    if not deal_id:
        err("--deal-id is required")
    deal_row = conn.execute("SELECT * FROM automotiveclaw_deal WHERE id = ?", (deal_id,)).fetchone()
    if not deal_row:
        err(f"Deal {deal_id} not found")

    trade_in_id = getattr(args, "trade_in_id", None)
    if not trade_in_id:
        err("--trade-in-id is required")
    trade_row = conn.execute("SELECT * FROM automotiveclaw_trade_in WHERE id = ?", (trade_in_id,)).fetchone()
    if not trade_row:
        err(f"Trade-in {trade_in_id} not found")

    trade_data = row_to_dict(trade_row)
    trade_allowance = getattr(args, "trade_allowance", None) or trade_data.get("offered_amount") or "0"

    conn.execute(
        "UPDATE automotiveclaw_deal SET trade_allowance = ?, trade_payoff = ?, updated_at = ? WHERE id = ?",
        (_to_money(trade_allowance), _to_money(trade_data.get("payoff_amount")), _now_iso(), deal_id)
    )
    conn.execute(
        "UPDATE automotiveclaw_trade_in SET trade_status = 'accepted', updated_at = ? WHERE id = ?",
        (_now_iso(), trade_in_id)
    )
    audit(conn, SKILL, "auto-add-deal-trade", "automotiveclaw_deal", deal_id,
          new_values={"trade_in_id": trade_in_id, "trade_allowance": trade_allowance})
    conn.commit()
    ok({"deal_id": deal_id, "trade_in_id": trade_in_id, "trade_allowance": _to_money(trade_allowance)})


# ===========================================================================
# 6. finalize-deal
# ===========================================================================
def finalize_deal(conn, args):
    deal_id = getattr(args, "deal_id", None)
    if not deal_id:
        err("--deal-id is required")
    row = conn.execute("SELECT * FROM automotiveclaw_deal WHERE id = ?", (deal_id,)).fetchone()
    if not row:
        err(f"Deal {deal_id} not found")
    data = row_to_dict(row)

    if data["deal_status"] in ("delivered", "unwound"):
        err(f"Cannot finalize deal in status '{data['deal_status']}'")

    # Calculate back gross from F&I products
    fi_profit = conn.execute(
        "SELECT COALESCE(SUM(CAST(profit AS REAL)), 0) FROM automotiveclaw_deal_fi_product WHERE deal_id = ?",
        (deal_id,)
    ).fetchone()[0]
    back_gross = str(round_currency(to_decimal(str(fi_profit))))

    front_gross = data.get("front_gross") or "0.00"
    total_gross = str(round_currency(to_decimal(front_gross) + to_decimal(back_gross)))

    now = _now_iso()
    conn.execute("""
        UPDATE automotiveclaw_deal SET deal_status = 'delivered', delivered_date = ?,
               back_gross = ?, total_gross = ?, updated_at = ?
        WHERE id = ?
    """, (now, back_gross, total_gross, now, deal_id))

    # Mark vehicle as sold
    if data.get("vehicle_id"):
        conn.execute(
            "UPDATE automotiveclaw_vehicle SET vehicle_status = 'sold', updated_at = ? WHERE id = ?",
            (now, data["vehicle_id"])
        )

    # --- GL Posting (optional — graceful degradation) ---
    gl_entry_ids = []
    gl_posted = False
    receivable_account_id = getattr(args, "receivable_account_id", None)
    revenue_account_id = getattr(args, "revenue_account_id", None)
    cogs_account_id = getattr(args, "cogs_account_id", None)
    inventory_account_id = getattr(args, "inventory_account_id", None)
    cost_center_id = getattr(args, "cost_center_id", None)

    if HAS_GL and receivable_account_id and revenue_account_id:
        selling_price = to_decimal(data.get("selling_price") or "0")
        trade_allowance = to_decimal(data.get("trade_allowance") or "0")

        # Revenue = selling_price (full amount owed by customer)
        # If there is a trade-in, the net cash receivable is selling_price - trade_allowance,
        # but the full selling_price is still revenue + trade-in credit
        total_receivable = str(round_currency(selling_price))

        # Revenue portion: selling_price - trade_allowance (net revenue from cash/financing)
        # Trade allowance is essentially a payment form, so full selling_price is receivable
        # and full selling_price is revenue. Trade-in is handled separately if needed.
        revenue_amount = str(round_currency(selling_price))

        entries = [
            {
                "account_id": receivable_account_id,
                "debit": total_receivable,
                "credit": "0",
                "party_type": "customer",
                "party_id": data["customer_id"],
            },
            {
                "account_id": revenue_account_id,
                "debit": "0",
                "credit": revenue_amount,
                "cost_center_id": cost_center_id,
            },
        ]

        posting_date = now[:10]  # YYYY-MM-DD from ISO timestamp

        try:
            gl_ids = insert_gl_entries(
                conn, entries,
                voucher_type="Vehicle Sale",
                voucher_id=deal_id,
                posting_date=posting_date,
                company_id=data["company_id"],
                remarks=f"Vehicle sale deal {data.get('naming_series') or deal_id}",
            )
            gl_entry_ids.extend(gl_ids)
            gl_posted = True
        except (ValueError, Exception):
            # GL posting failed — deal still closes, just without GL entries
            pass

        # Optional COGS entries (DR: COGS, CR: Inventory)
        # Uses the vehicle's invoice_price as cost basis
        if gl_posted and cogs_account_id and inventory_account_id and data.get("vehicle_id"):
            vehicle_row = conn.execute(
                "SELECT invoice_price FROM automotiveclaw_vehicle WHERE id = ?",
                (data["vehicle_id"],)
            ).fetchone()
            if vehicle_row and vehicle_row["invoice_price"]:
                cost_amount = str(round_currency(to_decimal(vehicle_row["invoice_price"])))
                if to_decimal(cost_amount) > Decimal("0"):
                    cogs_entries = [
                        {
                            "account_id": cogs_account_id,
                            "debit": cost_amount,
                            "credit": "0",
                            "cost_center_id": cost_center_id,
                        },
                        {
                            "account_id": inventory_account_id,
                            "debit": "0",
                            "credit": cost_amount,
                        },
                    ]
                    try:
                        cogs_ids = insert_gl_entries(
                            conn, cogs_entries,
                            voucher_type="Vehicle Sale",
                            voucher_id=deal_id,
                            posting_date=posting_date,
                            company_id=data["company_id"],
                            remarks=f"COGS for vehicle sale {data.get('naming_series') or deal_id}",
                            entry_set="cogs",
                        )
                        gl_entry_ids.extend(cogs_ids)
                    except (ValueError, Exception):
                        # COGS posting failed — revenue GL still stands
                        pass

    # Store GL entry IDs on the deal
    if gl_entry_ids:
        conn.execute(
            "UPDATE automotiveclaw_deal SET gl_entry_ids = ? WHERE id = ?",
            (",".join(gl_entry_ids), deal_id)
        )

    audit(conn, SKILL, "auto-finalize-deal", "automotiveclaw_deal", deal_id,
          new_values={"deal_status": "delivered", "total_gross": total_gross,
                      "gl_posted": gl_posted, "gl_entry_count": len(gl_entry_ids)})
    conn.commit()
    result = {
        "id": deal_id, "deal_status": "delivered",
        "front_gross": front_gross, "back_gross": back_gross, "total_gross": total_gross,
    }
    if gl_posted:
        result["gl_posted"] = True
        result["gl_entry_ids"] = gl_entry_ids
    ok(result)


# ===========================================================================
# 7. unwind-deal
# ===========================================================================
def unwind_deal(conn, args):
    deal_id = getattr(args, "deal_id", None)
    if not deal_id:
        err("--deal-id is required")
    row = conn.execute("SELECT * FROM automotiveclaw_deal WHERE id = ?", (deal_id,)).fetchone()
    if not row:
        err(f"Deal {deal_id} not found")
    data = row_to_dict(row)

    if data["deal_status"] == "unwound":
        err("Deal is already unwound")

    now = _now_iso()
    conn.execute(
        "UPDATE automotiveclaw_deal SET deal_status = 'unwound', updated_at = ? WHERE id = ?",
        (now, deal_id)
    )

    # Re-mark vehicle as available
    if data.get("vehicle_id"):
        conn.execute(
            "UPDATE automotiveclaw_vehicle SET vehicle_status = 'available', updated_at = ? WHERE id = ?",
            (now, data["vehicle_id"])
        )

    # Reverse GL entries if any were posted
    gl_reversed = False
    reversal_ids = []
    if HAS_GL and data.get("gl_entry_ids"):
        posting_date = now[:10]
        try:
            rev_ids = reverse_gl_entries(
                conn,
                voucher_type="Vehicle Sale",
                voucher_id=deal_id,
                posting_date=posting_date,
            )
            reversal_ids.extend(rev_ids)
            gl_reversed = True
        except (ValueError, Exception):
            # GL reversal failed — deal still unwinds
            pass

        # Clear GL entry IDs on the deal
        conn.execute(
            "UPDATE automotiveclaw_deal SET gl_entry_ids = NULL WHERE id = ?",
            (deal_id,)
        )

    audit(conn, SKILL, "auto-unwind-deal", "automotiveclaw_deal", deal_id,
          new_values={"deal_status": "unwound", "gl_reversed": gl_reversed})
    conn.commit()
    result = {"id": deal_id, "deal_status": "unwound"}
    if gl_reversed:
        result["gl_reversed"] = True
        result["reversal_entry_ids"] = reversal_ids
    ok(result)


# ===========================================================================
# 8. add-buyer-order
# ===========================================================================
def add_buyer_order(conn, args):
    deal_id = getattr(args, "deal_id", None)
    if not deal_id:
        err("--deal-id is required")
    if not conn.execute("SELECT id FROM automotiveclaw_deal WHERE id = ?", (deal_id,)).fetchone():
        err(f"Deal {deal_id} not found")

    # Check no existing buyer order
    if conn.execute("SELECT id FROM automotiveclaw_buyer_order WHERE deal_id = ?", (deal_id,)).fetchone():
        err(f"Buyer order already exists for deal {deal_id}")

    vehicle_price = getattr(args, "vehicle_price", None)
    if not vehicle_price:
        err("--vehicle-price is required")

    deal_row = conn.execute("SELECT company_id FROM automotiveclaw_deal WHERE id = ?", (deal_id,)).fetchone()
    company_id = deal_row[0]

    bo_id = str(uuid.uuid4())
    vp = _to_money(vehicle_price)
    tv = _to_money(getattr(args, "trade_value", None))
    acc = _to_money(getattr(args, "accessories", None))
    fees = _to_money(getattr(args, "fees", None))
    tax = _to_money(getattr(args, "tax_amount", None))

    subtotal_val = (
        to_decimal(vp or "0") - to_decimal(tv or "0")
        + to_decimal(acc or "0") + to_decimal(fees or "0")
    )
    subtotal = getattr(args, "subtotal", None)
    if subtotal:
        subtotal = _to_money(subtotal)
    else:
        subtotal = str(round_currency(subtotal_val))

    total = getattr(args, "total", None)
    if total:
        total = _to_money(total)
    else:
        total = str(round_currency(to_decimal(subtotal) + to_decimal(tax or "0")))

    conn.execute("""
        INSERT INTO automotiveclaw_buyer_order (
            id, deal_id, vehicle_price, trade_value, accessories, fees,
            subtotal, tax_amount, total, company_id, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (bo_id, deal_id, vp, tv, acc, fees, subtotal, tax, total, company_id, _now_iso()))
    conn.commit()
    ok({"id": bo_id, "deal_id": deal_id, "total": total})


# ===========================================================================
# 9. get-buyer-order
# ===========================================================================
def get_buyer_order(conn, args):
    deal_id = getattr(args, "deal_id", None)
    if not deal_id:
        err("--deal-id is required")
    row = conn.execute("SELECT * FROM automotiveclaw_buyer_order WHERE deal_id = ?", (deal_id,)).fetchone()
    if not row:
        err(f"No buyer order found for deal {deal_id}")
    ok(row_to_dict(row))


# ===========================================================================
# 10. deal-gross-report
# ===========================================================================
def deal_gross_report(conn, args):
    _validate_company(conn, args.company_id)
    rows = conn.execute("""
        SELECT d.id, d.naming_series, d.deal_type, d.selling_price,
               d.front_gross, d.back_gross, d.total_gross, d.deal_status,
               v.year, v.make, v.model
        FROM automotiveclaw_deal d
        LEFT JOIN automotiveclaw_vehicle v ON d.vehicle_id = v.id
        WHERE d.company_id = ? AND d.deal_status = 'delivered'
        ORDER BY d.delivered_date DESC
        LIMIT ? OFFSET ?
    """, (args.company_id, args.limit, args.offset)).fetchall()
    ok({"rows": [row_to_dict(r) for r in rows], "count": len(rows)})


# ===========================================================================
# 11. deal-summary
# ===========================================================================
def deal_summary(conn, args):
    _validate_company(conn, args.company_id)

    total = conn.execute(
        "SELECT COUNT(*) FROM automotiveclaw_deal WHERE company_id = ?", (args.company_id,)
    ).fetchone()[0]

    by_status = conn.execute(
        "SELECT deal_status, COUNT(*) as cnt FROM automotiveclaw_deal WHERE company_id = ? GROUP BY deal_status",
        (args.company_id,)
    ).fetchall()

    by_type = conn.execute(
        "SELECT deal_type, COUNT(*) as cnt FROM automotiveclaw_deal WHERE company_id = ? GROUP BY deal_type",
        (args.company_id,)
    ).fetchall()

    ok({
        "total_deals": total,
        "by_status": {r["deal_status"]: r["cnt"] for r in by_status},
        "by_type": {r["deal_type"]: r["cnt"] for r in by_type},
    })


# ===========================================================================
# 12. salesperson-performance-report
# ===========================================================================
def salesperson_performance_report(conn, args):
    _validate_company(conn, args.company_id)
    rows = conn.execute("""
        SELECT salesperson, COUNT(*) as deal_count,
               SUM(CAST(COALESCE(total_gross, '0') AS REAL)) as total_gross_sum
        FROM automotiveclaw_deal
        WHERE company_id = ? AND salesperson IS NOT NULL
        GROUP BY salesperson
        ORDER BY total_gross_sum DESC
        LIMIT ? OFFSET ?
    """, (args.company_id, args.limit, args.offset)).fetchall()
    ok({"rows": [row_to_dict(r) for r in rows], "count": len(rows)})


# ---------------------------------------------------------------------------
# Action registry
# ---------------------------------------------------------------------------
ACTIONS = {
    "auto-add-deal": add_deal,
    "auto-update-deal": update_deal,
    "auto-get-deal": get_deal,
    "auto-list-deals": list_deals,
    "auto-add-deal-trade": add_deal_trade,
    "auto-finalize-deal": finalize_deal,
    "auto-unwind-deal": unwind_deal,
    "auto-add-buyer-order": add_buyer_order,
    "auto-get-buyer-order": get_buyer_order,
    "auto-deal-gross-report": deal_gross_report,
    "auto-deal-summary": deal_summary,
    "auto-salesperson-performance-report": salesperson_performance_report,
}
