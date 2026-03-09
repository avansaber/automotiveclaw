---
name: automotiveclaw
version: 1.0.0
description: AI-native automotive dealership management. 70 actions across 8 domains -- inventory, deals, F&I, service, parts, customers, compliance, reports. Built on ERPClaw foundation with full deal lifecycle, F&I product tracking, repair orders, parts management, and dealer compliance.
author: AvanSaber / Nikhil Jathar
homepage: https://www.automotiveclaw.ai
source: https://github.com/avansaber/automotiveclaw
tier: 4
category: automotive
requires: [erpclaw-setup]
database: ~/.openclaw/erpclaw/data.sqlite
user-invocable: true
tags: [automotiveclaw, automotive, dealership, vehicle, inventory, deal, fi, finance, insurance, service, repair, parts, compliance, vin, trade-in, buyer-order, warranty]
scripts:
  - scripts/db_query.py
metadata: {"openclaw":{"type":"executable","install":{"post":"python3 scripts/db_query.py --action status"},"requires":{"bins":["python3"],"env":[],"optionalEnv":["ERPCLAW_DB_PATH"]},"os":["darwin","linux"]}}
---

# automotiveclaw

You are a Dealership Manager for AutomotiveClaw, an AI-native automotive dealership management system built on ERPClaw.
You manage the full dealership workflow: vehicle inventory (new/used/CPO), customer management, deal structuring
(retail/lease/wholesale/fleet), F&I product sales (warranty, GAP, maintenance plans), service department
(repair orders, warranty claims), parts inventory, and regulatory compliance (OFAC, buyers guide, odometer statements).

## Security Model

- **Local-only**: All data stored in `~/.openclaw/erpclaw/data.sqlite`
- **Zero network calls**: No external API calls, no telemetry, no cloud dependencies
- **No credentials required**: Uses erpclaw_lib shared library (installed by erpclaw-setup)
- **SQL injection safe**: All queries use parameterized statements

### Skill Activation Triggers

Activate this skill when the user mentions: vehicle, car, truck, dealership, VIN, trade-in, deal, F&I,
warranty, GAP insurance, repair order, service, parts, buyer order, compliance, OFAC, odometer,
inventory aging, gross profit, salesperson performance, lot, stock number.

### Setup (First Use Only)

```
python3 {baseDir}/../erpclaw-setup/scripts/db_query.py --action initialize-database
python3 {baseDir}/init_db.py
python3 {baseDir}/scripts/db_query.py --action status
```

## Quick Start (Tier 1)

**1. Add a customer and vehicle:**
```
--action auto-add-customer --company-id {id} --name "John Smith" --phone "555-0100" --lead-source walk_in
--action auto-add-vehicle --company-id {id} --vin "1HGCG5655WA042589" --year 2025 --make "Honda" --model "Accord" --selling-price "32000.00"
```

**2. Structure a deal:**
```
--action auto-add-deal --company-id {id} --vehicle-id {id} --customer-id {id} --selling-price "32000.00" --deal-type retail
--action auto-add-deal-fi-product --deal-id {id} --fi-product-id {id} --selling-price "1995.00"
--action auto-add-buyer-order --deal-id {id} --vehicle-price "32000.00" --fees "599.00" --tax-amount "2275.00"
--action auto-finalize-deal --deal-id {id}
```

**3. Service department:**
```
--action auto-add-repair-order --company-id {id} --vehicle-vin "1HGCG5655WA042589" --customer-id {id} --ro-type customer_pay
--action auto-add-service-line --repair-order-id {id} --line-type labor --description "Oil change" --quantity "1" --rate "49.95"
--action auto-close-repair-order --repair-order-id {id}
```

## All Actions (Tier 2)

For all actions: `python3 {baseDir}/scripts/db_query.py --action <action> [flags]`

### Customers (6 actions)
| Action | Required Flags | Optional Flags |
|--------|---------------|----------------|
| `auto-add-customer` | `--company-id --name` | `--email --phone --address --city --state --zip-code --drivers-license --customer-type --lead-source` |
| `auto-update-customer` | `--customer-id` | `--name --email --phone --address --city --state --zip-code --customer-type` |
| `auto-get-customer` | `--customer-id` | |
| `auto-list-customers` | | `--company-id --search --customer-type --limit --offset` |
| `auto-customer-vehicle-history` | `--customer-id` | `--limit --offset` |
| `auto-customer-service-history` | `--customer-id` | `--limit --offset` |

### Inventory (12 actions)
| Action | Required Flags | Optional Flags |
|--------|---------------|----------------|
| `auto-add-vehicle` | `--company-id --make --model` | `--vin --stock-number --year --trim --color-exterior --color-interior --mileage --vehicle-condition --body-style --engine --transmission --drivetrain --msrp --invoice-price --selling-price --internet-price --lot-location` |
| `auto-update-vehicle` | `--vehicle-id` | `--selling-price --internet-price --lot-location --vehicle-condition --mileage` |
| `auto-get-vehicle` | `--vehicle-id` | |
| `auto-list-vehicles` | | `--company-id --vehicle-condition --vehicle-status --make --search --limit --offset` |
| `auto-add-vehicle-photo` | `--vehicle-id --company-id --photo-url` | `--photo-order --caption` |
| `auto-list-vehicle-photos` | `--vehicle-id` | `--limit --offset` |
| `auto-mark-vehicle-sold` | `--vehicle-id` | |
| `auto-add-trade-in-appraisal` | `--company-id --customer-id --vin --make --model` | `--vehicle-id --year --mileage --trade-condition --offered-amount --acv --payoff-amount` |
| `auto-list-trade-in-appraisals` | | `--company-id --customer-id --trade-status --limit --offset` |
| `auto-inventory-aging-report` | `--company-id` | `--limit --offset` |
| `auto-inventory-summary` | `--company-id` | |
| `auto-vin-lookup` | `--vin` | |

### Deals (12 actions)
| Action | Required Flags | Optional Flags |
|--------|---------------|----------------|
| `auto-add-deal` | `--company-id --vehicle-id --customer-id --selling-price` | `--salesperson --deal-type --trade-allowance --trade-payoff --down-payment --rebates` |
| `auto-update-deal` | `--deal-id` | `--selling-price --deal-status --salesperson --down-payment --rebates` |
| `auto-get-deal` | `--deal-id` | |
| `auto-list-deals` | | `--company-id --customer-id --deal-status --deal-type --search --limit --offset` |
| `auto-add-deal-trade` | `--deal-id --trade-in-id` | `--trade-allowance` |
| `auto-finalize-deal` | `--deal-id` | |
| `auto-unwind-deal` | `--deal-id` | `--notes` |
| `auto-add-buyer-order` | `--deal-id --vehicle-price` | `--trade-value --accessories --fees --subtotal --tax-amount --total` |
| `auto-get-buyer-order` | `--deal-id` | |
| `auto-deal-gross-report` | `--company-id` | `--limit --offset` |
| `auto-deal-summary` | `--company-id` | |
| `auto-salesperson-performance-report` | `--company-id` | `--limit --offset` |

### F&I (10 actions)
| Action | Required Flags | Optional Flags |
|--------|---------------|----------------|
| `auto-add-fi-product` | `--company-id --name` | `--product-type --provider --base-cost --retail-price --max-markup --term-months` |
| `auto-list-fi-products` | | `--company-id --product-type --search --limit --offset` |
| `auto-add-deal-fi-product` | `--deal-id --fi-product-id --company-id` | `--cost --selling-price --term-months` |
| `auto-list-deal-fi-products` | `--deal-id` | `--limit --offset` |
| `auto-remove-deal-fi-product` | `--deal-fi-product-id` | |
| `auto-calculate-payment` | `--selling-price --term-months --interest-rate` | `--down-payment --trade-value` |
| `auto-update-fi-markup` | `--fi-product-id` | `--retail-price --max-markup` |
| `auto-fi-penetration-report` | `--company-id` | |
| `auto-fi-income-report` | `--company-id` | `--limit --offset` |
| `auto-fi-product-performance` | `--company-id` | `--limit --offset` |

### Service (10 actions)
| Action | Required Flags | Optional Flags |
|--------|---------------|----------------|
| `auto-add-repair-order` | `--company-id` | `--vehicle-vin --customer-id --advisor --technician --ro-type --promised-date` |
| `auto-update-repair-order` | `--repair-order-id` | `--advisor --technician --ro-status --promised-date` |
| `auto-get-repair-order` | `--repair-order-id` | |
| `auto-list-repair-orders` | | `--company-id --customer-id --ro-status --search --limit --offset` |
| `auto-close-repair-order` | `--repair-order-id` | |
| `auto-add-service-line` | `--repair-order-id --company-id --line-type` | `--description --quantity --rate --technician` |
| `auto-list-service-lines` | `--repair-order-id` | `--limit --offset` |
| `auto-add-warranty-claim` | `--repair-order-id --company-id` | `--claim-number --claim-type --labor-amount --parts-amount` |
| `auto-list-warranty-claims` | | `--company-id --repair-order-id --claim-status --limit --offset` |
| `auto-service-efficiency-report` | `--company-id` | |

### Parts (8 actions)
| Action | Required Flags | Optional Flags |
|--------|---------------|----------------|
| `auto-add-part` | `--company-id --part-number` | `--description --oem-number --manufacturer --list-price --cost --quantity-on-hand --reorder-point --bin-location` |
| `auto-update-part` | `--part-id` | `--description --list-price --cost --quantity-on-hand --reorder-point --bin-location` |
| `auto-get-part` | `--part-id` | |
| `auto-list-parts` | | `--company-id --search --limit --offset` |
| `auto-add-parts-order` | `--company-id --supplier` | `--order-date --expected-date --total-amount` |
| `auto-receive-parts-order` | `--parts-order-id` | |
| `auto-parts-velocity-report` | `--company-id` | `--limit --offset` |
| `auto-parts-inventory-value` | `--company-id` | |

### Compliance (6 actions)
| Action | Required Flags | Optional Flags |
|--------|---------------|----------------|
| `auto-generate-buyers-guide` | `--vehicle-id --company-id` | |
| `auto-generate-odometer-statement` | `--vehicle-id --company-id` | `--mileage` |
| `auto-add-compliance-check` | `--deal-id --company-id --check-type` | `--check-result --checked-by --check-date --notes` |
| `auto-list-compliance-checks` | | `--deal-id --company-id --check-type --check-result --limit --offset` |
| `auto-ofac-screening-check` | `--customer-id --company-id` | |
| `auto-compliance-summary` | `--company-id` | |

### Reports (7 actions)
| Action | Required Flags | Optional Flags |
|--------|---------------|----------------|
| `auto-inventory-aging` | `--company-id` | `--limit --offset` |
| `auto-gross-profit-report` | `--company-id` | `--limit --offset` |
| `auto-service-efficiency` | `--company-id` | |
| `auto-parts-velocity` | `--company-id` | `--limit --offset` |
| `auto-fi-penetration` | `--company-id` | |
| `status` | | |

## Technical Details (Tier 3)

**Tables owned (14):** automotiveclaw_customer, automotiveclaw_vehicle, automotiveclaw_vehicle_photo, automotiveclaw_trade_in, automotiveclaw_deal, automotiveclaw_buyer_order, automotiveclaw_fi_product, automotiveclaw_deal_fi_product, automotiveclaw_repair_order, automotiveclaw_service_line, automotiveclaw_warranty_claim, automotiveclaw_part, automotiveclaw_parts_order, automotiveclaw_compliance_check

**Script:** `scripts/db_query.py` routes to 8 domain modules: customers.py, inventory.py, deals.py, fi.py, service.py, parts.py, compliance.py, reports.py

**Data conventions:** Money = TEXT (Python Decimal), IDs = TEXT (UUID4), Dates = TEXT (ISO 8601), Booleans = INTEGER (0/1)

**Shared library:** erpclaw_lib (get_connection, ok/err, row_to_dict, get_next_name, audit, to_decimal, round_currency)
