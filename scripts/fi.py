"""AutomotiveClaw -- F&I (Finance & Insurance) domain module

Actions for F&I product management and deal F&I tracking (2 tables, 10 actions).
Imported by db_query.py (unified router).
"""
import os
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

try:
    sys.path.insert(0, os.path.expanduser("~/.openclaw/erpclaw/lib"))
    from erpclaw_lib.response import ok, err, row_to_dict
    from erpclaw_lib.audit import audit
    from erpclaw_lib.decimal_utils import to_decimal, round_currency
except ImportError:
    pass

SKILL = "automotiveclaw"

_now_iso = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

VALID_PRODUCT_TYPES = ("warranty", "gap", "maintenance", "tire_wheel", "paint", "theft", "other")


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
# 1. add-fi-product
# ===========================================================================
def add_fi_product(conn, args):
    _validate_company(conn, args.company_id)
    name = getattr(args, "name", None)
    if not name:
        err("--name is required")

    product_type = getattr(args, "product_type", None) or "warranty"
    if product_type not in VALID_PRODUCT_TYPES:
        err(f"Invalid product_type: {product_type}. Must be one of: {', '.join(VALID_PRODUCT_TYPES)}")

    prod_id = str(uuid.uuid4())
    term_months = int(args.term_months) if getattr(args, "term_months", None) else None

    conn.execute("""
        INSERT INTO automotiveclaw_fi_product (
            id, name, product_type, provider, base_cost, retail_price,
            max_markup, term_months, is_active, company_id, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (
        prod_id, name, product_type,
        getattr(args, "provider", None),
        _to_money(getattr(args, "base_cost", None)),
        _to_money(getattr(args, "retail_price", None)),
        _to_money(getattr(args, "max_markup", None)),
        term_months, 1, args.company_id, _now_iso(),
    ))
    audit(conn, SKILL, "auto-add-fi-product", "automotiveclaw_fi_product", prod_id,
          new_values={"name": name, "product_type": product_type})
    conn.commit()
    ok({"id": prod_id, "name": name, "product_type": product_type, "is_active": 1})


# ===========================================================================
# 2. list-fi-products
# ===========================================================================
def list_fi_products(conn, args):
    where, params = ["1=1"], []
    if getattr(args, "company_id", None):
        where.append("company_id = ?")
        params.append(args.company_id)
    if getattr(args, "product_type", None):
        where.append("product_type = ?")
        params.append(args.product_type)
    if getattr(args, "search", None):
        where.append("(name LIKE ? OR provider LIKE ?)")
        params.extend([f"%{args.search}%"] * 2)

    where_sql = " AND ".join(where)
    total = conn.execute(
        f"SELECT COUNT(*) FROM automotiveclaw_fi_product WHERE {where_sql}", params
    ).fetchone()[0]
    params.extend([args.limit, args.offset])
    rows = conn.execute(
        f"SELECT * FROM automotiveclaw_fi_product WHERE {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        params
    ).fetchall()
    ok({
        "rows": [row_to_dict(r) for r in rows],
        "total_count": total, "limit": args.limit, "offset": args.offset,
        "has_more": (args.offset + args.limit) < total,
    })


# ===========================================================================
# 3. add-deal-fi-product
# ===========================================================================
def add_deal_fi_product(conn, args):
    deal_id = getattr(args, "deal_id", None)
    if not deal_id:
        err("--deal-id is required")
    if not conn.execute("SELECT id FROM automotiveclaw_deal WHERE id = ?", (deal_id,)).fetchone():
        err(f"Deal {deal_id} not found")

    fi_product_id = getattr(args, "fi_product_id", None)
    if not fi_product_id:
        err("--fi-product-id is required")
    fi_row = conn.execute("SELECT * FROM automotiveclaw_fi_product WHERE id = ?", (fi_product_id,)).fetchone()
    if not fi_row:
        err(f"F&I product {fi_product_id} not found")

    _validate_company(conn, args.company_id)

    fi_data = row_to_dict(fi_row)
    cost = getattr(args, "cost", None) or fi_data.get("base_cost")
    selling_price = getattr(args, "selling_price", None) or fi_data.get("retail_price")
    term_months = int(args.term_months) if getattr(args, "term_months", None) else fi_data.get("term_months")

    cost_d = to_decimal(cost or "0")
    sell_d = to_decimal(selling_price or "0")
    profit = str(round_currency(sell_d - cost_d))

    dfp_id = str(uuid.uuid4())
    conn.execute("""
        INSERT INTO automotiveclaw_deal_fi_product (
            id, deal_id, fi_product_id, cost, selling_price, profit,
            term_months, company_id, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?)
    """, (
        dfp_id, deal_id, fi_product_id,
        _to_money(cost), _to_money(selling_price), profit,
        term_months, args.company_id, _now_iso(),
    ))
    audit(conn, SKILL, "auto-add-deal-fi-product", "automotiveclaw_deal_fi_product", dfp_id,
          new_values={"deal_id": deal_id, "fi_product_id": fi_product_id})
    conn.commit()
    ok({"id": dfp_id, "deal_id": deal_id, "profit": profit})


# ===========================================================================
# 4. list-deal-fi-products
# ===========================================================================
def list_deal_fi_products(conn, args):
    deal_id = getattr(args, "deal_id", None)
    if not deal_id:
        err("--deal-id is required")

    rows = conn.execute(
        """SELECT dfp.*, fp.name as product_name, fp.product_type
           FROM automotiveclaw_deal_fi_product dfp
           LEFT JOIN automotiveclaw_fi_product fp ON dfp.fi_product_id = fp.id
           WHERE dfp.deal_id = ?
           ORDER BY dfp.created_at
           LIMIT ? OFFSET ?""",
        (deal_id, args.limit, args.offset)
    ).fetchall()
    ok({"deal_id": deal_id, "rows": [row_to_dict(r) for r in rows], "count": len(rows)})


# ===========================================================================
# 5. remove-deal-fi-product
# ===========================================================================
def remove_deal_fi_product(conn, args):
    dfp_id = getattr(args, "deal_fi_product_id", None)
    if not dfp_id:
        err("--deal-fi-product-id is required")
    if not conn.execute("SELECT id FROM automotiveclaw_deal_fi_product WHERE id = ?", (dfp_id,)).fetchone():
        err(f"Deal F&I product {dfp_id} not found")

    conn.execute("DELETE FROM automotiveclaw_deal_fi_product WHERE id = ?", (dfp_id,))
    audit(conn, SKILL, "auto-remove-deal-fi-product", "automotiveclaw_deal_fi_product", dfp_id)
    conn.commit()
    ok({"id": dfp_id, "deleted": True})


# ===========================================================================
# 6. calculate-payment
# ===========================================================================
def calculate_payment(conn, args):
    selling_price = getattr(args, "selling_price", None)
    if not selling_price:
        err("--selling-price is required")
    term_months_raw = getattr(args, "term_months", None)
    if not term_months_raw:
        err("--term-months is required")
    interest_rate_raw = getattr(args, "interest_rate", None)
    if not interest_rate_raw:
        err("--interest-rate is required")

    price = to_decimal(selling_price)
    term = int(term_months_raw)
    annual_rate = to_decimal(interest_rate_raw)

    down = to_decimal(getattr(args, "down_payment", None) or "0")
    trade = to_decimal(getattr(args, "trade_value", None) or "0")

    financed = price - down - trade
    if financed <= 0:
        ok({"monthly_payment": "0.00", "financed_amount": "0.00", "total_interest": "0.00"})
        return

    if annual_rate == 0:
        monthly = financed / Decimal(str(term))
        total_interest = Decimal("0")
    else:
        monthly_rate = annual_rate / Decimal("1200")
        factor = (monthly_rate * (1 + monthly_rate) ** term) / ((1 + monthly_rate) ** term - 1)
        monthly = financed * factor
        total_interest = (monthly * term) - financed

    ok({
        "monthly_payment": str(round_currency(monthly)),
        "financed_amount": str(round_currency(financed)),
        "total_interest": str(round_currency(total_interest)),
        "term_months": term,
        "annual_rate": str(annual_rate),
    })


# ===========================================================================
# 7. update-fi-markup
# ===========================================================================
def update_fi_markup(conn, args):
    prod_id = getattr(args, "fi_product_id", None)
    if not prod_id:
        err("--fi-product-id is required")
    if not conn.execute("SELECT id FROM automotiveclaw_fi_product WHERE id = ?", (prod_id,)).fetchone():
        err(f"F&I product {prod_id} not found")

    updates, params, changed = [], [], []
    for arg_name, col_name in {
        "retail_price": "retail_price",
        "max_markup": "max_markup",
    }.items():
        val = getattr(args, arg_name, None)
        if val is not None:
            updates.append(f"{col_name} = ?")
            params.append(_to_money(val))
            changed.append(col_name)

    if not updates:
        err("No fields to update. Provide --retail-price or --max-markup")

    params.append(prod_id)
    conn.execute(f"UPDATE automotiveclaw_fi_product SET {', '.join(updates)} WHERE id = ?", params)
    audit(conn, SKILL, "auto-update-fi-markup", "automotiveclaw_fi_product", prod_id,
          new_values={"updated_fields": changed})
    conn.commit()
    ok({"id": prod_id, "updated_fields": changed})


# ===========================================================================
# 8. fi-penetration-report
# ===========================================================================
def fi_penetration_report(conn, args):
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

    penetration = 0.0
    if total_deals > 0:
        penetration = round(deals_with_fi / total_deals * 100, 1)

    ok({
        "total_delivered_deals": total_deals,
        "deals_with_fi": deals_with_fi,
        "penetration_pct": penetration,
    })


# ===========================================================================
# 9. fi-income-report
# ===========================================================================
def fi_income_report(conn, args):
    _validate_company(conn, args.company_id)
    rows = conn.execute("""
        SELECT dfp.deal_id, fp.name as product_name, fp.product_type,
               dfp.cost, dfp.selling_price, dfp.profit
        FROM automotiveclaw_deal_fi_product dfp
        JOIN automotiveclaw_fi_product fp ON dfp.fi_product_id = fp.id
        JOIN automotiveclaw_deal d ON dfp.deal_id = d.id
        WHERE d.company_id = ?
        ORDER BY dfp.created_at DESC
        LIMIT ? OFFSET ?
    """, (args.company_id, args.limit, args.offset)).fetchall()
    ok({"rows": [row_to_dict(r) for r in rows], "count": len(rows)})


# ===========================================================================
# 10. fi-product-performance
# ===========================================================================
def fi_product_performance(conn, args):
    _validate_company(conn, args.company_id)
    rows = conn.execute("""
        SELECT fp.id, fp.name, fp.product_type,
               COUNT(dfp.id) as sold_count,
               COALESCE(SUM(CAST(dfp.profit AS REAL)), 0) as total_profit
        FROM automotiveclaw_fi_product fp
        LEFT JOIN automotiveclaw_deal_fi_product dfp ON fp.id = dfp.fi_product_id
        WHERE fp.company_id = ?
        GROUP BY fp.id, fp.name, fp.product_type
        ORDER BY total_profit DESC
        LIMIT ? OFFSET ?
    """, (args.company_id, args.limit, args.offset)).fetchall()
    ok({"rows": [row_to_dict(r) for r in rows], "count": len(rows)})


# ---------------------------------------------------------------------------
# Action registry
# ---------------------------------------------------------------------------
ACTIONS = {
    "auto-add-fi-product": add_fi_product,
    "auto-list-fi-products": list_fi_products,
    "auto-add-deal-fi-product": add_deal_fi_product,
    "auto-list-deal-fi-products": list_deal_fi_products,
    "auto-remove-deal-fi-product": remove_deal_fi_product,
    "auto-calculate-payment": calculate_payment,
    "auto-update-fi-markup": update_fi_markup,
    "auto-fi-penetration-report": fi_penetration_report,
    "auto-fi-income-report": fi_income_report,
    "auto-fi-product-performance": fi_product_performance,
}
