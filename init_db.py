#!/usr/bin/env python3
"""AutomotiveClaw schema extension -- adds automotive dealership tables to the shared database.

14 tables across 7 domains: customers, inventory, deals, fi, service, parts,
compliance.

Prerequisite: ERPClaw init_db.py must have run first (creates foundation tables).
Run: python3 init_db.py [db_path]

ADR-0034 phase 2 bulk-39. Schema declared as metadata and provisioned through
`erpclaw_lib.seam`, which emits dialect-correct DDL, replacing a hand-written
``CREATE TABLE`` block opened with ``sqlite3.connect`` that could not run on
PostgreSQL at all. The docstring's table count said 18 across 8 domains
(including a "reports" domain); the file has only ever created 14 across 7, and
the count is corrected here rather than carried forward. Money stays TEXT
throughout -- selling prices, gross, payoffs and repair-order totals all remain
Decimal strings.
"""
import importlib.util
import os
import sys

# Bootstrap the shared lib only when it is not already reachable -- an
# unconditional insert at position 0 overrides a caller that deliberately bound a
# different tree (ADR-0034 phase 2 step 2d).
if importlib.util.find_spec("erpclaw_lib") is None:
    sys.path.insert(0, os.path.join(os.path.expanduser(
        os.environ.get("ERPCLAW_HOME", "~/.openclaw/erpclaw")), "lib"))

from erpclaw_lib.seam import (  # noqa: E402
    CheckConstraint, Column, ForeignKey, Index, Integer, MetaData, Table, Text,
    provision, reference_table, text,
)

DEFAULT_DB_PATH = os.path.join(os.path.expanduser(os.environ.get("ERPCLAW_HOME", "~/.openclaw/erpclaw")), "data.sqlite")
DISPLAY_NAME = "AutomotiveClaw"

REQUIRED_FOUNDATION = [
    "company", "customer", "naming_series", "audit_log",
]

METADATA = MetaData()

# Foundation tables this module points at but does not own -- declared for
# foreign-key resolution only and never created here.
reference_table("company", METADATA)
reference_table("customer", METADATA)
reference_table("supplier", METADATA)

# ==================================================================
# CUSTOMERS DOMAIN (extension table -- core fields live in customer)
# ==================================================================

# ---------------------------------------------------------------------------
# 1. automotiveclaw_customer_ext
# ---------------------------------------------------------------------------
CUSTOMER_EXT = Table(
    "automotiveclaw_customer_ext", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("naming_series", Text, server_default=text("'ACUST-'")),
    Column("customer_id", Text, ForeignKey("customer.id"), nullable=False),
    Column("drivers_license", Text),
    Column("customer_type", Text, server_default=text("'individual'")),
    Column("lead_source", Text, server_default=text("'walk_in'")),
    Column("company_id", Text, ForeignKey("company.id"), nullable=False),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint("customer_type IN ('individual','business','fleet')",
                    name="ck_automotiveclaw_customer_ext_customer_type"),
    CheckConstraint(
        "lead_source IN ('walk_in','internet','phone','referral','repeat','other')",
        name="ck_automotiveclaw_customer_ext_lead_source"),
)

Index("idx_ac_custext_company", CUSTOMER_EXT.c.company_id)
Index("idx_ac_custext_customer", CUSTOMER_EXT.c.customer_id)
Index("idx_ac_custext_type", CUSTOMER_EXT.c.customer_type)

# ==================================================================
# INVENTORY DOMAIN
# ==================================================================

# ---------------------------------------------------------------------------
# 2. automotiveclaw_vehicle
# ---------------------------------------------------------------------------
VEHICLE = Table(
    "automotiveclaw_vehicle", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("naming_series", Text),
    # Column-level UNIQUE as shipped: the VIN is the dedupe key for an inbound
    # unit, so losing it would let the same car be stocked in twice.
    Column("vin", Text, unique=True),
    Column("stock_number", Text),
    Column("year", Integer),
    Column("make", Text),
    Column("model", Text),
    Column("trim", Text),
    Column("color_exterior", Text),
    Column("color_interior", Text),
    Column("mileage", Text),
    Column("vehicle_condition", Text, server_default=text("'new'")),
    Column("body_style", Text),
    Column("engine", Text),
    Column("transmission", Text, server_default=text("'automatic'")),
    Column("drivetrain", Text, server_default=text("'fwd'")),
    Column("msrp", Text),
    Column("invoice_price", Text),
    Column("selling_price", Text),
    Column("internet_price", Text),
    Column("lot_location", Text),
    Column("days_in_stock", Integer, server_default=text("0")),
    Column("vehicle_status", Text, server_default=text("'available'")),
    Column("company_id", Text, ForeignKey("company.id"), nullable=False),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint("vehicle_condition IN ('new','used','cpo')",
                    name="ck_automotiveclaw_vehicle_vehicle_condition"),
    CheckConstraint("transmission IN ('automatic','manual','cvt')",
                    name="ck_automotiveclaw_vehicle_transmission"),
    CheckConstraint("drivetrain IN ('fwd','rwd','awd','4wd')",
                    name="ck_automotiveclaw_vehicle_drivetrain"),
    CheckConstraint(
        "vehicle_status IN ('available','hold','sold','traded','wholesale','transit')",
        name="ck_automotiveclaw_vehicle_vehicle_status"),
)

Index("idx_ac_veh_company", VEHICLE.c.company_id)
Index("idx_ac_veh_vin", VEHICLE.c.vin)
Index("idx_ac_veh_status", VEHICLE.c.vehicle_status)
Index("idx_ac_veh_make", VEHICLE.c.make)
Index("idx_ac_veh_condition", VEHICLE.c.vehicle_condition)

# ---------------------------------------------------------------------------
# 3. automotiveclaw_vehicle_photo
# ---------------------------------------------------------------------------
VEHICLE_PHOTO = Table(
    "automotiveclaw_vehicle_photo", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("vehicle_id", Text, ForeignKey("automotiveclaw_vehicle.id"),
           nullable=False),
    Column("photo_url", Text),
    Column("photo_order", Integer, server_default=text("0")),
    Column("caption", Text),
    Column("company_id", Text, ForeignKey("company.id"), nullable=False),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
)

Index("idx_ac_vphoto_vehicle", VEHICLE_PHOTO.c.vehicle_id)

# ---------------------------------------------------------------------------
# 4. automotiveclaw_trade_in
# ---------------------------------------------------------------------------
TRADE_IN = Table(
    "automotiveclaw_trade_in", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("naming_series", Text),
    # Nullable here, NOT NULL on the photo table: an appraisal can exist before
    # the trade is stocked in. Asymmetry preserved as shipped.
    Column("vehicle_id", Text, ForeignKey("automotiveclaw_vehicle.id")),
    Column("customer_id", Text, ForeignKey("customer.id")),
    Column("vin", Text),
    Column("year", Integer),
    Column("make", Text),
    Column("model", Text),
    Column("mileage", Text),
    Column("trade_condition", Text, server_default=text("'good'")),
    Column("offered_amount", Text),
    Column("acv", Text),
    Column("payoff_amount", Text),
    Column("trade_status", Text, server_default=text("'pending'")),
    Column("company_id", Text, ForeignKey("company.id"), nullable=False),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint("trade_condition IN ('excellent','good','fair','poor')",
                    name="ck_automotiveclaw_trade_in_trade_condition"),
    CheckConstraint("trade_status IN ('pending','accepted','rejected')",
                    name="ck_automotiveclaw_trade_in_trade_status"),
)

Index("idx_ac_trade_vehicle", TRADE_IN.c.vehicle_id)
Index("idx_ac_trade_customer", TRADE_IN.c.customer_id)
Index("idx_ac_trade_status", TRADE_IN.c.trade_status)

# ==================================================================
# DEALS DOMAIN
# ==================================================================

# ---------------------------------------------------------------------------
# 5. automotiveclaw_deal
# ---------------------------------------------------------------------------
DEAL = Table(
    "automotiveclaw_deal", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("naming_series", Text),
    Column("vehicle_id", Text, ForeignKey("automotiveclaw_vehicle.id")),
    Column("customer_id", Text, ForeignKey("customer.id")),
    Column("salesperson", Text),
    Column("deal_type", Text, server_default=text("'retail'")),
    Column("selling_price", Text),
    Column("trade_allowance", Text),
    Column("trade_payoff", Text),
    Column("down_payment", Text),
    Column("rebates", Text),
    Column("front_gross", Text),
    Column("back_gross", Text),
    Column("total_gross", Text),
    Column("deal_status", Text, server_default=text("'pending'")),
    Column("delivered_date", Text),
    Column("gl_entry_ids", Text),
    Column("company_id", Text, ForeignKey("company.id"), nullable=False),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint("deal_type IN ('retail','lease','wholesale','fleet')",
                    name="ck_automotiveclaw_deal_deal_type"),
    CheckConstraint(
        "deal_status IN ('pending','negotiating','submitted','approved','funded','delivered','unwound')",
        name="ck_automotiveclaw_deal_deal_status"),
)

Index("idx_ac_deal_vehicle", DEAL.c.vehicle_id)
Index("idx_ac_deal_customer", DEAL.c.customer_id)
Index("idx_ac_deal_status", DEAL.c.deal_status)
Index("idx_ac_deal_company", DEAL.c.company_id)

# ---------------------------------------------------------------------------
# 6. automotiveclaw_buyer_order
# ---------------------------------------------------------------------------
BUYER_ORDER = Table(
    "automotiveclaw_buyer_order", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    # One buyer order per deal, enforced by a column-level UNIQUE as shipped.
    Column("deal_id", Text, ForeignKey("automotiveclaw_deal.id"),
           nullable=False, unique=True),
    Column("vehicle_price", Text),
    Column("trade_value", Text),
    Column("accessories", Text),
    Column("fees", Text),
    Column("subtotal", Text),
    Column("tax_amount", Text),
    Column("total", Text),
    Column("company_id", Text, ForeignKey("company.id"), nullable=False),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
)

Index("idx_ac_bo_deal", BUYER_ORDER.c.deal_id)

# ==================================================================
# F&I DOMAIN
# ==================================================================

# ---------------------------------------------------------------------------
# 7. automotiveclaw_fi_product
# ---------------------------------------------------------------------------
FI_PRODUCT = Table(
    "automotiveclaw_fi_product", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("name", Text, nullable=False),
    Column("product_type", Text, server_default=text("'warranty'")),
    Column("provider", Text),
    Column("base_cost", Text),
    Column("retail_price", Text),
    Column("max_markup", Text),
    Column("term_months", Integer),
    Column("is_active", Integer, server_default=text("1")),
    Column("company_id", Text, ForeignKey("company.id"), nullable=False),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint(
        "product_type IN ('warranty','gap','maintenance','tire_wheel','paint','theft','other')",
        name="ck_automotiveclaw_fi_product_product_type"),
)

Index("idx_ac_fiprod_company", FI_PRODUCT.c.company_id)
Index("idx_ac_fiprod_type", FI_PRODUCT.c.product_type)

# ---------------------------------------------------------------------------
# 8. automotiveclaw_deal_fi_product
# ---------------------------------------------------------------------------
DEAL_FI_PRODUCT = Table(
    "automotiveclaw_deal_fi_product", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("deal_id", Text, ForeignKey("automotiveclaw_deal.id"), nullable=False),
    Column("fi_product_id", Text, ForeignKey("automotiveclaw_fi_product.id"),
           nullable=False),
    Column("cost", Text),
    Column("selling_price", Text),
    Column("profit", Text),
    Column("term_months", Integer),
    Column("company_id", Text, ForeignKey("company.id"), nullable=False),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
)

Index("idx_ac_dealfi_deal", DEAL_FI_PRODUCT.c.deal_id)
Index("idx_ac_dealfi_prod", DEAL_FI_PRODUCT.c.fi_product_id)

# ==================================================================
# SERVICE DOMAIN
# ==================================================================

# ---------------------------------------------------------------------------
# 9. automotiveclaw_repair_order
# ---------------------------------------------------------------------------
REPAIR_ORDER = Table(
    "automotiveclaw_repair_order", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("naming_series", Text),
    # The RO carries a bare VIN, not a vehicle_id: service writes ROs for cars
    # the dealership never stocked. No foreign key, as shipped.
    Column("vehicle_vin", Text),
    Column("customer_id", Text, ForeignKey("customer.id")),
    Column("advisor", Text),
    Column("technician", Text),
    Column("ro_type", Text, server_default=text("'customer_pay'")),
    Column("promised_date", Text),
    Column("ro_status", Text, server_default=text("'open'")),
    Column("labor_total", Text),
    Column("parts_total", Text),
    Column("total", Text),
    Column("company_id", Text, ForeignKey("company.id"), nullable=False),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint(
        "ro_type IN ('customer_pay','warranty','internal','recall')",
        name="ck_automotiveclaw_repair_order_ro_type"),
    CheckConstraint(
        "ro_status IN ('open','in_progress','waiting_parts','completed','invoiced')",
        name="ck_automotiveclaw_repair_order_ro_status"),
)

Index("idx_ac_ro_customer", REPAIR_ORDER.c.customer_id)
Index("idx_ac_ro_status", REPAIR_ORDER.c.ro_status)
Index("idx_ac_ro_company", REPAIR_ORDER.c.company_id)
Index("idx_ac_ro_vin", REPAIR_ORDER.c.vehicle_vin)

# ---------------------------------------------------------------------------
# 10. automotiveclaw_service_line
# ---------------------------------------------------------------------------
SERVICE_LINE = Table(
    "automotiveclaw_service_line", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("repair_order_id", Text,
           ForeignKey("automotiveclaw_repair_order.id"), nullable=False),
    Column("line_type", Text, server_default=text("'labor'")),
    Column("description", Text),
    Column("quantity", Text),
    Column("rate", Text),
    Column("amount", Text),
    Column("technician", Text),
    Column("company_id", Text, ForeignKey("company.id"), nullable=False),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint("line_type IN ('labor','parts','sublet','fee')",
                    name="ck_automotiveclaw_service_line_line_type"),
)

Index("idx_ac_svcline_ro", SERVICE_LINE.c.repair_order_id)

# ---------------------------------------------------------------------------
# 11. automotiveclaw_warranty_claim
# ---------------------------------------------------------------------------
WARRANTY_CLAIM = Table(
    "automotiveclaw_warranty_claim", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("naming_series", Text),
    Column("repair_order_id", Text,
           ForeignKey("automotiveclaw_repair_order.id"), nullable=False),
    Column("claim_number", Text),
    Column("claim_type", Text, server_default=text("'factory'")),
    Column("labor_amount", Text),
    Column("parts_amount", Text),
    Column("total_amount", Text),
    Column("claim_status", Text, server_default=text("'submitted'")),
    Column("company_id", Text, ForeignKey("company.id"), nullable=False),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint("claim_type IN ('factory','extended','goodwill')",
                    name="ck_automotiveclaw_warranty_claim_claim_type"),
    CheckConstraint(
        "claim_status IN ('submitted','approved','rejected','paid')",
        name="ck_automotiveclaw_warranty_claim_claim_status"),
)

Index("idx_ac_wc_ro", WARRANTY_CLAIM.c.repair_order_id)
Index("idx_ac_wc_status", WARRANTY_CLAIM.c.claim_status)

# ==================================================================
# PARTS DOMAIN
# ==================================================================

# ---------------------------------------------------------------------------
# 12. automotiveclaw_part
# ---------------------------------------------------------------------------
PART = Table(
    "automotiveclaw_part", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("part_number", Text, nullable=False),
    Column("description", Text),
    Column("oem_number", Text),
    Column("manufacturer", Text),
    Column("list_price", Text),
    Column("cost", Text),
    Column("quantity_on_hand", Integer, server_default=text("0")),
    Column("reorder_point", Integer, server_default=text("5")),
    Column("bin_location", Text),
    Column("is_active", Integer, server_default=text("1")),
    Column("company_id", Text, ForeignKey("company.id"), nullable=False),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
)

Index("idx_ac_part_company", PART.c.company_id)
Index("idx_ac_part_number", PART.c.part_number)

# ---------------------------------------------------------------------------
# 13. automotiveclaw_parts_order
# ---------------------------------------------------------------------------
PARTS_ORDER = Table(
    "automotiveclaw_parts_order", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("naming_series", Text),
    Column("supplier_id", Text, ForeignKey("supplier.id"), nullable=False),
    Column("order_date", Text),
    Column("expected_date", Text),
    Column("order_status", Text, server_default=text("'ordered'")),
    Column("total_amount", Text),
    Column("company_id", Text, ForeignKey("company.id"), nullable=False),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    Column("updated_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint(
        "order_status IN ('ordered','partial','received','cancelled')",
        name="ck_automotiveclaw_parts_order_order_status"),
)

Index("idx_ac_po_company", PARTS_ORDER.c.company_id)
Index("idx_ac_po_status", PARTS_ORDER.c.order_status)

# ==================================================================
# COMPLIANCE DOMAIN
# ==================================================================

# ---------------------------------------------------------------------------
# 14. automotiveclaw_compliance_check
# ---------------------------------------------------------------------------
COMPLIANCE_CHECK = Table(
    "automotiveclaw_compliance_check", METADATA,
    Column("id", Text, primary_key=True, nullable=True),
    Column("deal_id", Text, ForeignKey("automotiveclaw_deal.id")),
    # NOT NULL with no default, unlike every other CHECKed column here: an
    # OFAC/red-flag record has to say which check it is. Asymmetry preserved.
    Column("check_type", Text, nullable=False),
    Column("check_result", Text, server_default=text("'pending'")),
    Column("checked_by", Text),
    Column("check_date", Text),
    Column("notes", Text),
    Column("company_id", Text, ForeignKey("company.id"), nullable=False),
    Column("created_at", Text, nullable=False,
           server_default=text("CURRENT_TIMESTAMP")),
    CheckConstraint(
        "check_type IN ('ofac','red_flag','tila','odometer','buyers_guide')",
        name="ck_automotiveclaw_compliance_check_check_type"),
    CheckConstraint("check_result IN ('pass','fail','pending')",
                    name="ck_automotiveclaw_compliance_check_check_result"),
)

Index("idx_ac_comp_deal", COMPLIANCE_CHECK.c.deal_id)
Index("idx_ac_comp_type", COMPLIANCE_CHECK.c.check_type)


def _require_foundation(db_path):
    """The pre-conversion installer's foundation probe, asked through the seam.

    The original read ``sqlite_master`` directly, so the guard that exists to
    produce a friendly error was itself SQLite-only. ``seam.table_exists`` answers
    on both backends (ADR-0034 bulk-39).
    """
    from erpclaw_lib import seam

    missing = [t for t in REQUIRED_FOUNDATION if not seam.table_exists(t, db_path)]
    if missing:
        print(f"ERROR: Foundation tables missing: {', '.join(missing)}")
        print("Run erpclaw-setup first: clawhub install erpclaw-setup")
        sys.exit(1)


def create_automotiveclaw_tables(db_path=None):
    """Create AutomotiveClaw tables and indexes on whichever backend is configured.

    Same contract as before the ADR-0034 conversion: idempotent, and the returned
    counts are what was ACTUALLY created rather than what was declared.
    """
    db_path = db_path or os.environ.get("ERPCLAW_DB_PATH", DEFAULT_DB_PATH)
    _require_foundation(db_path)
    result = provision(METADATA, db_path)
    return {
        "database": db_path,
        "tables": result["tables"],
        "indexes": result["indexes"],
    }


if __name__ == "__main__":
    db = sys.argv[1] if len(sys.argv) > 1 else None
    result = create_automotiveclaw_tables(db)
    print(f"{DISPLAY_NAME} schema created in {result['database']}")
    print(f"  Tables: {result['tables']}")
    print(f"  Indexes: {result['indexes']}")
