"""Shared helper functions for AutomotiveClaw L1 unit tests.

Provides:
  - DB bootstrap via init_schema.init_db() + create_automotiveclaw_tables()
  - load_db_query() for explicit module loading (avoids sys.path collisions)
  - call_action() / ns() / is_error() / is_ok()
  - Seed functions for company, customers, suppliers, naming_series
  - build_env() for a complete automotive test environment
"""
import argparse
import importlib.util
import io
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.dirname(TESTS_DIR)          # automotiveclaw/scripts/
MODULE_DIR = os.path.dirname(SCRIPTS_DIR)          # automotiveclaw/
INIT_DB_PATH = os.path.join(MODULE_DIR, "init_db.py")

# Foundation init_schema.py (erpclaw-setup)
SRC_DIR = os.path.dirname(MODULE_DIR)              # src/
ERPCLAW_DIR = os.path.join(SRC_DIR, "erpclaw", "scripts", "erpclaw-setup")
INIT_SCHEMA_PATH = os.path.join(ERPCLAW_DIR, "init_schema.py")

# Make erpclaw_lib importable
ERPCLAW_LIB = os.path.expanduser("~/.openclaw/erpclaw/lib")
if ERPCLAW_LIB not in sys.path:
    sys.path.insert(0, ERPCLAW_LIB)

# Make scripts dir importable so domain modules (customers, inventory, ...) resolve
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)


def load_db_query():
    """Load automotiveclaw db_query.py explicitly to avoid sys.path collisions."""
    db_query_path = os.path.join(SCRIPTS_DIR, "db_query.py")
    spec = importlib.util.spec_from_file_location("db_query_auto", db_query_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def init_all_tables(db_path: str):
    """Create foundation tables + automotiveclaw extension tables.

    1. Runs erpclaw-setup init_schema.init_db()  (core tables)
    2. Extends customer table with columns automotiveclaw code expects
    3. Runs automotiveclaw init_db.create_automotiveclaw_tables()
    """
    # Step 1: Foundation schema
    spec = importlib.util.spec_from_file_location("init_schema", INIT_SCHEMA_PATH)
    schema_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(schema_mod)
    schema_mod.init_db(db_path)

    # Step 2: The automotiveclaw code references c.name, c.email,
    # c.phone on the customer table. email/phone/modified may not be in
    # the core schema — add them if missing so JOIN queries work in tests.
    conn = sqlite3.connect(db_path)
    for col_def in [
        "ALTER TABLE customer ADD COLUMN email TEXT",
        "ALTER TABLE customer ADD COLUMN phone TEXT",
        "ALTER TABLE customer ADD COLUMN modified TEXT",
    ]:
        try:
            conn.execute(col_def)
        except sqlite3.OperationalError:
            pass  # Column already exists
    conn.commit()
    conn.close()

    # Step 3: Automotiveclaw extension tables
    spec2 = importlib.util.spec_from_file_location("auto_init_db", INIT_DB_PATH)
    auto_mod = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(auto_mod)
    auto_mod.create_automotiveclaw_tables(db_path)


class _ConnWrapper:
    """Thin wrapper so conn.company_id works (some actions set it)."""
    def __init__(self, real_conn):
        self._conn = real_conn
        self.company_id = None

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def execute(self, *a, **kw):
        return self._conn.execute(*a, **kw)

    def executemany(self, *a, **kw):
        return self._conn.executemany(*a, **kw)

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return self._conn.close()

    @property
    def row_factory(self):
        return self._conn.row_factory

    @row_factory.setter
    def row_factory(self, value):
        self._conn.row_factory = value


class _DecimalSum:
    """Custom SQLite aggregate: SUM using Python Decimal for precision."""
    def __init__(self):
        self.total = Decimal("0")

    def step(self, value):
        if value is not None:
            self.total += Decimal(str(value))

    def finalize(self):
        return str(self.total)


def get_conn(db_path: str):
    """Return a wrapped sqlite3.Connection with FK enabled and Row factory."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.create_aggregate("decimal_sum", 1, _DecimalSum)
    return _ConnWrapper(conn)


# ---------------------------------------------------------------------------
# Action invocation helpers
# ---------------------------------------------------------------------------

def call_action(fn, conn, args) -> dict:
    """Invoke a domain function, capture stdout JSON, return parsed dict."""
    buf = io.StringIO()

    def _fake_exit(code=0):
        raise SystemExit(code)

    try:
        with patch("sys.stdout", buf), patch("sys.exit", side_effect=_fake_exit):
            fn(conn, args)
    except SystemExit:
        pass

    output = buf.getvalue().strip()
    if not output:
        return {"status": "error", "message": "no output captured"}
    return json.loads(output)


def ns(**kwargs) -> argparse.Namespace:
    """Build an argparse.Namespace from keyword args (mimics CLI flags)."""
    defaults = {
        "limit": 50,
        "offset": 0,
        "company_id": None,
        "customer_id": None,
        "vehicle_id": None,
        "deal_id": None,
        "trade_in_id": None,
        "name": None,
        "email": None,
        "phone": None,
        "drivers_license": None,
        "customer_type": None,
        "lead_source": None,
        "vin": None,
        "stock_number": None,
        "year": None,
        "make": None,
        "model": None,
        "trim": None,
        "color_exterior": None,
        "color_interior": None,
        "mileage": None,
        "vehicle_condition": None,
        "body_style": None,
        "engine": None,
        "transmission": None,
        "drivetrain": None,
        "msrp": None,
        "invoice_price": None,
        "selling_price": None,
        "internet_price": None,
        "lot_location": None,
        "vehicle_status": None,
        "photo_url": None,
        "photo_order": None,
        "caption": None,
        "trade_condition": None,
        "offered_amount": None,
        "acv": None,
        "payoff_amount": None,
        "trade_status": None,
        "salesperson": None,
        "deal_type": None,
        "trade_allowance": None,
        "trade_payoff": None,
        "down_payment": None,
        "rebates": None,
        "deal_status": None,
        "revenue_account_id": None,
        "receivable_account_id": None,
        "cogs_account_id": None,
        "inventory_account_id": None,
        "cost_center_id": None,
        "vehicle_price": None,
        "trade_value": None,
        "accessories": None,
        "fees": None,
        "subtotal": None,
        "tax_amount": None,
        "total": None,
        "fi_product_id": None,
        "deal_fi_product_id": None,
        "product_type": None,
        "provider": None,
        "base_cost": None,
        "retail_price": None,
        "max_markup": None,
        "term_months": None,
        "cost": None,
        "interest_rate": None,
        "repair_order_id": None,
        "vehicle_vin": None,
        "advisor": None,
        "technician": None,
        "ro_type": None,
        "ro_status": None,
        "promised_date": None,
        "line_type": None,
        "description": None,
        "quantity": None,
        "rate": None,
        "claim_number": None,
        "claim_type": None,
        "labor_amount": None,
        "parts_amount": None,
        "claim_status": None,
        "part_id": None,
        "part_number": None,
        "oem_number": None,
        "manufacturer": None,
        "list_price": None,
        "quantity_on_hand": None,
        "reorder_point": None,
        "bin_location": None,
        "parts_order_id": None,
        "supplier_id": None,
        "order_date": None,
        "expected_date": None,
        "total_amount": None,
        "check_type": None,
        "check_result": None,
        "checked_by": None,
        "check_date": None,
        "notes": None,
        "search": None,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def is_error(result: dict) -> bool:
    return result.get("status") == "error"


def is_ok(result: dict) -> bool:
    return result.get("status") == "ok"


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

def seed_company(conn, name="Auto Dealer Co", abbr="AD") -> str:
    """Insert a test company and return its ID."""
    cid = _uuid()
    conn.execute(
        """INSERT INTO company (id, name, abbr, default_currency, country,
           fiscal_year_start_month)
           VALUES (?, ?, ?, 'USD', 'United States', 1)""",
        (cid, f"{name} {cid[:6]}", f"{abbr}{cid[:4]}")
    )
    conn.commit()
    return cid


def seed_customer(conn, company_id: str, name="John Doe",
                  email=None, phone=None) -> str:
    """Insert a core customer and return its ID."""
    cid = _uuid()
    conn.execute(
        """INSERT INTO customer (id, name, email, phone,
           company_id, customer_type, status)
           VALUES (?, ?, ?, ?, ?, 'individual', 'active')""",
        (cid, name, email, phone, company_id)
    )
    conn.commit()
    return cid


def seed_customer_ext(conn, customer_id: str, company_id: str,
                      customer_type="individual", lead_source="walk_in",
                      drivers_license=None) -> str:
    """Insert an automotiveclaw customer extension row and return its ID."""
    ext_id = _uuid()
    now = _now()
    conn.execute(
        """INSERT INTO automotiveclaw_customer_ext (
               id, naming_series, customer_id, drivers_license,
               customer_type, lead_source, company_id, created_at, updated_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (ext_id, f"ACUST-{ext_id[:6]}", customer_id, drivers_license,
         customer_type, lead_source, company_id, now, now)
    )
    conn.commit()
    return ext_id


def seed_supplier(conn, company_id: str, name="Auto Parts Inc") -> str:
    """Insert a supplier and return its ID."""
    sid = _uuid()
    conn.execute(
        """INSERT INTO supplier (id, name, company_id)
           VALUES (?, ?, ?)""",
        (sid, name, company_id)
    )
    conn.commit()
    return sid


def seed_naming_series(conn, company_id: str):
    """Seed naming series for automotiveclaw entity types."""
    series = [
        ("automotiveclaw_customer_ext", "ACUST-", 0),
        ("automotiveclaw_vehicle", "VEH-", 0),
        ("automotiveclaw_trade_in", "TRADE-", 0),
        ("automotiveclaw_deal", "DEAL-", 0),
        ("automotiveclaw_repair_order", "RO-", 0),
        ("automotiveclaw_warranty_claim", "WC-", 0),
        ("automotiveclaw_parts_order", "PO-", 0),
    ]
    for entity_type, prefix, current in series:
        conn.execute(
            """INSERT OR IGNORE INTO naming_series
               (id, entity_type, prefix, current_value, company_id)
               VALUES (?, ?, ?, ?, ?)""",
            (_uuid(), entity_type, prefix, current, company_id)
        )
    conn.commit()


def seed_account(conn, company_id: str, name="Test Account",
                 root_type="asset", account_type=None,
                 account_number=None) -> str:
    """Insert a GL account and return its ID."""
    aid = _uuid()
    direction = "debit_normal" if root_type in ("asset", "expense") else "credit_normal"
    conn.execute(
        """INSERT INTO account (id, name, account_number, root_type, account_type,
           balance_direction, company_id, depth)
           VALUES (?, ?, ?, ?, ?, ?, ?, 0)""",
        (aid, name, account_number or f"ACC-{aid[:6]}", root_type,
         account_type, direction, company_id)
    )
    conn.commit()
    return aid


def seed_fiscal_year(conn, company_id: str,
                     start="2026-01-01", end="2026-12-31") -> str:
    """Insert a fiscal year and return its ID."""
    fid = _uuid()
    conn.execute(
        """INSERT INTO fiscal_year (id, name, start_date, end_date, company_id)
           VALUES (?, ?, ?, ?, ?)""",
        (fid, f"FY-{fid[:6]}", start, end, company_id)
    )
    conn.commit()
    return fid


def seed_cost_center(conn, company_id: str, name="Main CC") -> str:
    """Insert a cost center and return its ID."""
    ccid = _uuid()
    conn.execute(
        """INSERT INTO cost_center (id, name, company_id, is_group)
           VALUES (?, ?, ?, 0)""",
        (ccid, name, company_id)
    )
    conn.commit()
    return ccid


def seed_vehicle(conn, company_id: str, make="Toyota", model="Camry",
                 year=2025, vin=None, selling_price="30000.00",
                 vehicle_condition="new") -> str:
    """Insert a vehicle and return its ID."""
    veh_id = _uuid()
    now = _now()
    vin = vin or f"VIN{_uuid()[:13].upper()}"
    conn.execute(
        """INSERT INTO automotiveclaw_vehicle (
               id, naming_series, vin, stock_number, year, make, model,
               vehicle_condition, transmission, drivetrain,
               msrp, selling_price, vehicle_status,
               company_id, created_at, updated_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (veh_id, f"VEH-{veh_id[:6]}", vin, f"STK-{veh_id[:6]}",
         year, make, model, vehicle_condition, "automatic", "fwd",
         selling_price, selling_price, "available",
         company_id, now, now)
    )
    conn.commit()
    return veh_id


def seed_deal(conn, vehicle_id: str, customer_id: str, company_id: str,
              selling_price="30000.00", deal_type="retail") -> str:
    """Insert a deal and return its ID."""
    deal_id = _uuid()
    now = _now()
    conn.execute(
        """INSERT INTO automotiveclaw_deal (
               id, naming_series, vehicle_id, customer_id, salesperson,
               deal_type, selling_price, front_gross, back_gross, total_gross,
               deal_status, company_id, created_at, updated_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (deal_id, f"DEAL-{deal_id[:6]}", vehicle_id, customer_id, "Sales Rep",
         deal_type, selling_price, selling_price, "0.00", selling_price,
         "pending", company_id, now, now)
    )
    conn.commit()
    return deal_id


def seed_repair_order(conn, company_id: str, customer_id=None,
                      vehicle_vin=None, ro_type="customer_pay") -> str:
    """Insert a repair order and return its ID."""
    ro_id = _uuid()
    now = _now()
    conn.execute(
        """INSERT INTO automotiveclaw_repair_order (
               id, naming_series, vehicle_vin, customer_id, ro_type,
               ro_status, labor_total, parts_total, total,
               company_id, created_at, updated_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (ro_id, f"RO-{ro_id[:6]}", vehicle_vin, customer_id, ro_type,
         "open", "0.00", "0.00", "0.00", company_id, now, now)
    )
    conn.commit()
    return ro_id


def build_env(conn) -> dict:
    """Create a complete automotive test environment.

    Returns dict with all IDs needed for tests.
    """
    cid = seed_company(conn)
    seed_naming_series(conn, cid)
    fyid = seed_fiscal_year(conn, cid)
    ccid = seed_cost_center(conn, cid)

    # GL accounts
    ar = seed_account(conn, cid, "Accounts Receivable", "asset", "receivable", "1100")
    revenue = seed_account(conn, cid, "Sales Revenue", "income", "revenue", "4000")
    cogs = seed_account(conn, cid, "COGS", "expense", "cost_of_goods_sold", "5000")
    inventory_acct = seed_account(conn, cid, "Vehicle Inventory", "asset", "stock", "1200")

    # Customer (core + extension)
    core_cust = seed_customer(conn, cid, "John Doe", "john@test.com", "555-0100")
    ext_cust = seed_customer_ext(conn, core_cust, cid)

    # Supplier
    supplier = seed_supplier(conn, cid, "Auto Parts Inc")

    # Vehicle
    vehicle = seed_vehicle(conn, cid, "Toyota", "Camry", 2025,
                           selling_price="30000.00")

    return {
        "company_id": cid,
        "fiscal_year_id": fyid,
        "cost_center_id": ccid,
        "ar": ar,
        "revenue": revenue,
        "cogs": cogs,
        "inventory_acct": inventory_acct,
        "core_customer_id": core_cust,
        "customer_ext_id": ext_cust,
        "supplier_id": supplier,
        "vehicle_id": vehicle,
    }
