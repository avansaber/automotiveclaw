#!/usr/bin/env python3
"""AutomotiveClaw schema extension -- adds automotive dealership tables to the shared database.

18 tables across 8 domains: inventory, deals, fi, service, parts, customers,
compliance, reports.

Prerequisite: ERPClaw init_db.py must have run first (creates foundation tables).
Run: python3 init_db.py [db_path]
"""
import os
import sqlite3
import sys

DEFAULT_DB_PATH = os.path.expanduser("~/.openclaw/erpclaw/data.sqlite")
DISPLAY_NAME = "AutomotiveClaw"

REQUIRED_FOUNDATION = [
    "company", "naming_series", "audit_log",
]


def create_automotiveclaw_tables(db_path=None):
    db_path = db_path or os.environ.get("ERPCLAW_DB_PATH", DEFAULT_DB_PATH)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")

    # -- Verify ERPClaw foundation --
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    missing = [t for t in REQUIRED_FOUNDATION if t not in tables]
    if missing:
        print(f"ERROR: Foundation tables missing: {', '.join(missing)}")
        print("Run erpclaw-setup first: clawhub install erpclaw-setup")
        conn.close()
        sys.exit(1)

    tables_created = 0
    indexes_created = 0

    # ==================================================================
    # CUSTOMERS DOMAIN
    # ==================================================================

    # 1. automotiveclaw_customer
    conn.execute("""
        CREATE TABLE IF NOT EXISTS automotiveclaw_customer (
            id              TEXT PRIMARY KEY,
            naming_series   TEXT,
            name            TEXT NOT NULL,
            email           TEXT,
            phone           TEXT,
            address         TEXT,
            city            TEXT,
            state           TEXT,
            zip_code        TEXT,
            drivers_license TEXT,
            customer_type   TEXT DEFAULT 'individual'
                            CHECK(customer_type IN ('individual','business','fleet')),
            lead_source     TEXT DEFAULT 'walk_in'
                            CHECK(lead_source IN ('walk_in','internet','phone','referral','repeat','other')),
            company_id      TEXT NOT NULL REFERENCES company(id),
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    tables_created += 1
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ac_cust_company ON automotiveclaw_customer(company_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ac_cust_name ON automotiveclaw_customer(name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ac_cust_type ON automotiveclaw_customer(customer_type)")
    indexes_created += 3

    # ==================================================================
    # INVENTORY DOMAIN
    # ==================================================================

    # 2. automotiveclaw_vehicle
    conn.execute("""
        CREATE TABLE IF NOT EXISTS automotiveclaw_vehicle (
            id              TEXT PRIMARY KEY,
            naming_series   TEXT,
            vin             TEXT UNIQUE,
            stock_number    TEXT,
            year            INTEGER,
            make            TEXT,
            model           TEXT,
            trim            TEXT,
            color_exterior  TEXT,
            color_interior  TEXT,
            mileage         TEXT,
            vehicle_condition TEXT DEFAULT 'new'
                            CHECK(vehicle_condition IN ('new','used','cpo')),
            body_style      TEXT,
            engine          TEXT,
            transmission    TEXT DEFAULT 'automatic'
                            CHECK(transmission IN ('automatic','manual','cvt')),
            drivetrain      TEXT DEFAULT 'fwd'
                            CHECK(drivetrain IN ('fwd','rwd','awd','4wd')),
            msrp            TEXT,
            invoice_price   TEXT,
            selling_price   TEXT,
            internet_price  TEXT,
            lot_location    TEXT,
            days_in_stock   INTEGER DEFAULT 0,
            vehicle_status  TEXT DEFAULT 'available'
                            CHECK(vehicle_status IN ('available','hold','sold','traded','wholesale','transit')),
            company_id      TEXT NOT NULL REFERENCES company(id),
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    tables_created += 1
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ac_veh_company ON automotiveclaw_vehicle(company_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ac_veh_vin ON automotiveclaw_vehicle(vin)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ac_veh_status ON automotiveclaw_vehicle(vehicle_status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ac_veh_make ON automotiveclaw_vehicle(make)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ac_veh_condition ON automotiveclaw_vehicle(vehicle_condition)")
    indexes_created += 5

    # 3. automotiveclaw_vehicle_photo
    conn.execute("""
        CREATE TABLE IF NOT EXISTS automotiveclaw_vehicle_photo (
            id              TEXT PRIMARY KEY,
            vehicle_id      TEXT NOT NULL REFERENCES automotiveclaw_vehicle(id),
            photo_url       TEXT,
            photo_order     INTEGER DEFAULT 0,
            caption         TEXT,
            company_id      TEXT NOT NULL REFERENCES company(id),
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    tables_created += 1
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ac_vphoto_vehicle ON automotiveclaw_vehicle_photo(vehicle_id)")
    indexes_created += 1

    # 4. automotiveclaw_trade_in
    conn.execute("""
        CREATE TABLE IF NOT EXISTS automotiveclaw_trade_in (
            id              TEXT PRIMARY KEY,
            naming_series   TEXT,
            vehicle_id      TEXT REFERENCES automotiveclaw_vehicle(id),
            customer_id     TEXT REFERENCES automotiveclaw_customer(id),
            vin             TEXT,
            year            INTEGER,
            make            TEXT,
            model           TEXT,
            mileage         TEXT,
            trade_condition TEXT DEFAULT 'good'
                            CHECK(trade_condition IN ('excellent','good','fair','poor')),
            offered_amount  TEXT,
            acv             TEXT,
            payoff_amount   TEXT,
            trade_status    TEXT DEFAULT 'pending'
                            CHECK(trade_status IN ('pending','accepted','rejected')),
            company_id      TEXT NOT NULL REFERENCES company(id),
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    tables_created += 1
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ac_trade_vehicle ON automotiveclaw_trade_in(vehicle_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ac_trade_customer ON automotiveclaw_trade_in(customer_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ac_trade_status ON automotiveclaw_trade_in(trade_status)")
    indexes_created += 3

    # ==================================================================
    # DEALS DOMAIN
    # ==================================================================

    # 5. automotiveclaw_deal
    conn.execute("""
        CREATE TABLE IF NOT EXISTS automotiveclaw_deal (
            id              TEXT PRIMARY KEY,
            naming_series   TEXT,
            vehicle_id      TEXT REFERENCES automotiveclaw_vehicle(id),
            customer_id     TEXT REFERENCES automotiveclaw_customer(id),
            salesperson     TEXT,
            deal_type       TEXT DEFAULT 'retail'
                            CHECK(deal_type IN ('retail','lease','wholesale','fleet')),
            selling_price   TEXT,
            trade_allowance TEXT,
            trade_payoff    TEXT,
            down_payment    TEXT,
            rebates         TEXT,
            front_gross     TEXT,
            back_gross      TEXT,
            total_gross     TEXT,
            deal_status     TEXT DEFAULT 'pending'
                            CHECK(deal_status IN ('pending','negotiating','submitted','approved','funded','delivered','unwound')),
            delivered_date  TEXT,
            company_id      TEXT NOT NULL REFERENCES company(id),
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    tables_created += 1
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ac_deal_vehicle ON automotiveclaw_deal(vehicle_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ac_deal_customer ON automotiveclaw_deal(customer_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ac_deal_status ON automotiveclaw_deal(deal_status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ac_deal_company ON automotiveclaw_deal(company_id)")
    indexes_created += 4

    # 6. automotiveclaw_buyer_order
    conn.execute("""
        CREATE TABLE IF NOT EXISTS automotiveclaw_buyer_order (
            id              TEXT PRIMARY KEY,
            deal_id         TEXT NOT NULL UNIQUE REFERENCES automotiveclaw_deal(id),
            vehicle_price   TEXT,
            trade_value     TEXT,
            accessories     TEXT,
            fees            TEXT,
            subtotal        TEXT,
            tax_amount      TEXT,
            total           TEXT,
            company_id      TEXT NOT NULL REFERENCES company(id),
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    tables_created += 1
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ac_bo_deal ON automotiveclaw_buyer_order(deal_id)")
    indexes_created += 1

    # ==================================================================
    # F&I DOMAIN
    # ==================================================================

    # 7. automotiveclaw_fi_product
    conn.execute("""
        CREATE TABLE IF NOT EXISTS automotiveclaw_fi_product (
            id              TEXT PRIMARY KEY,
            name            TEXT NOT NULL,
            product_type    TEXT DEFAULT 'warranty'
                            CHECK(product_type IN ('warranty','gap','maintenance','tire_wheel','paint','theft','other')),
            provider        TEXT,
            base_cost       TEXT,
            retail_price    TEXT,
            max_markup      TEXT,
            term_months     INTEGER,
            is_active       INTEGER DEFAULT 1,
            company_id      TEXT NOT NULL REFERENCES company(id),
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    tables_created += 1
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ac_fiprod_company ON automotiveclaw_fi_product(company_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ac_fiprod_type ON automotiveclaw_fi_product(product_type)")
    indexes_created += 2

    # 8. automotiveclaw_deal_fi_product
    conn.execute("""
        CREATE TABLE IF NOT EXISTS automotiveclaw_deal_fi_product (
            id              TEXT PRIMARY KEY,
            deal_id         TEXT NOT NULL REFERENCES automotiveclaw_deal(id),
            fi_product_id   TEXT NOT NULL REFERENCES automotiveclaw_fi_product(id),
            cost            TEXT,
            selling_price   TEXT,
            profit          TEXT,
            term_months     INTEGER,
            company_id      TEXT NOT NULL REFERENCES company(id),
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    tables_created += 1
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ac_dealfi_deal ON automotiveclaw_deal_fi_product(deal_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ac_dealfi_prod ON automotiveclaw_deal_fi_product(fi_product_id)")
    indexes_created += 2

    # ==================================================================
    # SERVICE DOMAIN
    # ==================================================================

    # 9. automotiveclaw_repair_order
    conn.execute("""
        CREATE TABLE IF NOT EXISTS automotiveclaw_repair_order (
            id              TEXT PRIMARY KEY,
            naming_series   TEXT,
            vehicle_vin     TEXT,
            customer_id     TEXT REFERENCES automotiveclaw_customer(id),
            advisor         TEXT,
            technician      TEXT,
            ro_type         TEXT DEFAULT 'customer_pay'
                            CHECK(ro_type IN ('customer_pay','warranty','internal','recall')),
            promised_date   TEXT,
            ro_status       TEXT DEFAULT 'open'
                            CHECK(ro_status IN ('open','in_progress','waiting_parts','completed','invoiced')),
            labor_total     TEXT,
            parts_total     TEXT,
            total           TEXT,
            company_id      TEXT NOT NULL REFERENCES company(id),
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    tables_created += 1
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ac_ro_customer ON automotiveclaw_repair_order(customer_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ac_ro_status ON automotiveclaw_repair_order(ro_status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ac_ro_company ON automotiveclaw_repair_order(company_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ac_ro_vin ON automotiveclaw_repair_order(vehicle_vin)")
    indexes_created += 4

    # 10. automotiveclaw_service_line
    conn.execute("""
        CREATE TABLE IF NOT EXISTS automotiveclaw_service_line (
            id              TEXT PRIMARY KEY,
            repair_order_id TEXT NOT NULL REFERENCES automotiveclaw_repair_order(id),
            line_type       TEXT DEFAULT 'labor'
                            CHECK(line_type IN ('labor','parts','sublet','fee')),
            description     TEXT,
            quantity        TEXT,
            rate            TEXT,
            amount          TEXT,
            technician      TEXT,
            company_id      TEXT NOT NULL REFERENCES company(id),
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    tables_created += 1
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ac_svcline_ro ON automotiveclaw_service_line(repair_order_id)")
    indexes_created += 1

    # 11. automotiveclaw_warranty_claim
    conn.execute("""
        CREATE TABLE IF NOT EXISTS automotiveclaw_warranty_claim (
            id              TEXT PRIMARY KEY,
            naming_series   TEXT,
            repair_order_id TEXT NOT NULL REFERENCES automotiveclaw_repair_order(id),
            claim_number    TEXT,
            claim_type      TEXT DEFAULT 'factory'
                            CHECK(claim_type IN ('factory','extended','goodwill')),
            labor_amount    TEXT,
            parts_amount    TEXT,
            total_amount    TEXT,
            claim_status    TEXT DEFAULT 'submitted'
                            CHECK(claim_status IN ('submitted','approved','rejected','paid')),
            company_id      TEXT NOT NULL REFERENCES company(id),
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    tables_created += 1
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ac_wc_ro ON automotiveclaw_warranty_claim(repair_order_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ac_wc_status ON automotiveclaw_warranty_claim(claim_status)")
    indexes_created += 2

    # ==================================================================
    # PARTS DOMAIN
    # ==================================================================

    # 12. automotiveclaw_part
    conn.execute("""
        CREATE TABLE IF NOT EXISTS automotiveclaw_part (
            id              TEXT PRIMARY KEY,
            part_number     TEXT NOT NULL,
            description     TEXT,
            oem_number      TEXT,
            manufacturer    TEXT,
            list_price      TEXT,
            cost            TEXT,
            quantity_on_hand INTEGER DEFAULT 0,
            reorder_point   INTEGER DEFAULT 5,
            bin_location    TEXT,
            is_active       INTEGER DEFAULT 1,
            company_id      TEXT NOT NULL REFERENCES company(id),
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    tables_created += 1
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ac_part_company ON automotiveclaw_part(company_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ac_part_number ON automotiveclaw_part(part_number)")
    indexes_created += 2

    # 13. automotiveclaw_parts_order
    conn.execute("""
        CREATE TABLE IF NOT EXISTS automotiveclaw_parts_order (
            id              TEXT PRIMARY KEY,
            naming_series   TEXT,
            supplier        TEXT,
            order_date      TEXT,
            expected_date   TEXT,
            order_status    TEXT DEFAULT 'ordered'
                            CHECK(order_status IN ('ordered','partial','received','cancelled')),
            total_amount    TEXT,
            company_id      TEXT NOT NULL REFERENCES company(id),
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    tables_created += 1
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ac_po_company ON automotiveclaw_parts_order(company_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ac_po_status ON automotiveclaw_parts_order(order_status)")
    indexes_created += 2

    # ==================================================================
    # COMPLIANCE DOMAIN
    # ==================================================================

    # 14. automotiveclaw_compliance_check
    conn.execute("""
        CREATE TABLE IF NOT EXISTS automotiveclaw_compliance_check (
            id              TEXT PRIMARY KEY,
            deal_id         TEXT REFERENCES automotiveclaw_deal(id),
            check_type      TEXT NOT NULL
                            CHECK(check_type IN ('ofac','red_flag','tila','odometer','buyers_guide')),
            check_result    TEXT DEFAULT 'pending'
                            CHECK(check_result IN ('pass','fail','pending')),
            checked_by      TEXT,
            check_date      TEXT,
            notes           TEXT,
            company_id      TEXT NOT NULL REFERENCES company(id),
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    tables_created += 1
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ac_comp_deal ON automotiveclaw_compliance_check(deal_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ac_comp_type ON automotiveclaw_compliance_check(check_type)")
    indexes_created += 2

    conn.commit()
    conn.close()

    return {
        "database": db_path,
        "tables": tables_created,
        "indexes": indexes_created,
    }


if __name__ == "__main__":
    db = sys.argv[1] if len(sys.argv) > 1 else None
    result = create_automotiveclaw_tables(db)
    print(f"{DISPLAY_NAME} schema created in {result['database']}")
    print(f"  Tables: {result['tables']}")
    print(f"  Indexes: {result['indexes']}")
