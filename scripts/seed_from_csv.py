"""
Seed script — loads the line_items CSV into the AP Integration API.

This script calls the actual REST API (not the DB directly), so every
record goes through validation, idempotency checks, and VAT validation
just like a real ERP sync would.

Usage:
    python scripts/seed_from_csv.py --csv path/to/line_items.csv
    python scripts/seed_from_csv.py --csv path/to/line_items.csv --base-url http://localhost:8000

The script is idempotent — safe to run multiple times.
"""
import argparse
import sys
import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from collections import defaultdict

import pandas as pd
import httpx

# ── Tax code rate mapping from the CSV data ────────────────────────────────────
# Derived by observing NET vs VAT in the CSV:
#   T0 = 0%   (no VAT, e.g. food)
#   T3 = 18%  (standard rate)
#   T6 = 18%  (standard rate, different category)
#   T8 = 0%   (exempt, e.g. commissions)
TAX_CODE_RATES = {
    "T0": {"rate": "0.0000", "description": "Zero rate (0%)"},
    "T1": {"rate": "0.1800", "description": "Standard rate 18% - T1"},
    "T2": {"rate": "0.0500", "description": "Reduced rate 5% - T2"},
    "T3": {"rate": "0.1800", "description": "Standard rate 18% - T3"},
    "T5": {"rate": "0.0500", "description": "Reduced rate 5% - T5"},
    "T6": {"rate": "0.1800", "description": "Standard rate 18% - T6"},
    "T8": {"rate": "0.0000", "description": "Exempt (0%) - T8"},
    "T9": {"rate": "0.0000", "description": "Zero rate (0%) - T9"},
}


def post(client: httpx.Client, url: str, data: dict) -> dict:
    resp = client.post(url, json=data)
    if resp.status_code not in (200, 201):
        print(f"  ✗ POST {url} failed [{resp.status_code}]: {resp.text[:300]}")
        return {}
    return resp.json()


def seed_master_data(client: httpx.Client, base_url: str, df: pd.DataFrame):
    print("\n── Step 1: Seeding Departments ──────────────────────────────────")
    departments = df["DEPARTMENT"].dropna().unique()
    for dept in sorted(departments):
        result = post(client, f"{base_url}/departments", {
            "external_id": dept.strip(),
            "name": dept.strip().title(),
        })
        if result:
            print(f"  ✓ Department: {dept}")

    print("\n── Step 2: Seeding Nominal Accounts ────────────────────────────")
    accounts = df["NOMINAL"].dropna().unique()
    for acc in sorted(accounts):
        result = post(client, f"{base_url}/accounts", {
            "external_id": acc.strip(),
            "name": acc.strip(),
        })
        if result:
            print(f"  ✓ Account: {acc}")

    print("\n── Step 3: Seeding Tax Codes ────────────────────────────────────")
    tax_codes = df["TC"].dropna().unique()
    for tc in sorted(tax_codes):
        tc = tc.strip()
        if tc not in TAX_CODE_RATES:
            print(f"  ⚠ Unknown tax code: {tc} — defaulting to 0%")
            TAX_CODE_RATES[tc] = {"rate": "0.0000", "description": f"Unknown code {tc}"}
        result = post(client, f"{base_url}/tax-codes", {
            "external_id": tc,
            "code": tc,
            **TAX_CODE_RATES[tc],
        })
        if result:
            print(f"  ✓ Tax Code: {tc} ({TAX_CODE_RATES[tc]['rate']})")

    print("\n── Step 4: Seeding Vendors ──────────────────────────────────────")
    vendors = df["SUPPLIER"].dropna().unique()
    for vendor in sorted(vendors):
        result = post(client, f"{base_url}/vendors", {
            "external_id": vendor.strip(),
            "name": vendor.strip().title(),
        })
        if result:
            print(f"  ✓ Vendor: {vendor}")


def seed_invoices(client: httpx.Client, base_url: str, df: pd.DataFrame):
    print("\n── Step 5: Seeding Invoices ─────────────────────────────────────")

    # Group lines by REF (invoice reference)
    grouped = df.groupby("REF")
    total = len(grouped)
    succeeded = skipped = failed = 0

    def fmt_ref(ref_val):
        # Safely format REF values for use in external IDs and logs
        try:
            if pd.isna(ref_val):
                return "<missing-ref>"
        except Exception:
            pass
        # If it's a float but represents an integer (e.g. 123.0), keep integer form
        try:
            if isinstance(ref_val, float) and ref_val.is_integer():
                return str(int(ref_val))
        except Exception:
            pass
        return str(ref_val).strip()

    for ref, group in grouped:
        # Use the first row's date as the invoice date
        invoice_date = pd.to_datetime(group["DATE"].iloc[0]).strftime("%Y-%m-%d")
        vendor = str(group["SUPPLIER"].iloc[0]).strip()

        lines = []
        for _, row in group.iterrows():
            # Validate required fields per-line and skip invalid rows
            if pd.isna(row.get("NOMINAL")) or pd.isna(row.get("TC")) or pd.isna(row.get("DETAIL")):
                print(f"  ⚠ Skipping line with missing required fields on REF={fmt_ref(ref)}")
                continue
            try:
                net = Decimal(str(row["NET"])) if pd.notna(row.get("NET")) else Decimal("0")
                net = net.quantize(Decimal("0.0001"))
            except Exception:
                print(f"  ⚠ Invalid NET on REF={fmt_ref(ref)}; skipping line")
                continue
            try:
                vat = Decimal(str(row["VAT"])) if pd.notna(row.get("VAT")) else Decimal("0")
                vat = vat.quantize(Decimal("0.0001"))
            except Exception:
                vat = Decimal("0")

            lines.append({
                "description": str(row["DETAIL"]).strip(),
                "net_amount": str(net),
                "vat_amount": str(vat),
                "tax_code_external_id": str(row["TC"]).strip(),
                "nominal_external_id": str(row["NOMINAL"]).strip(),
                "department_external_id": str(row.get("DEPARTMENT") if pd.notna(row.get("DEPARTMENT")) else ""),
            })

        # If the CSV reports VAT as separate "VAT-only" lines (net==0, vat>0)
        # distribute those VAT totals to taxable lines that currently have zero VAT
        # grouped by tax code. This addresses files where VAT is shown separately
        # as summary lines instead of per-item VAT amounts.
        vat_only_by_tc = defaultdict(Decimal)
        taxable_indices_by_tc = defaultdict(list)
        for i, l in enumerate(lines):
            net_i = Decimal(l["net_amount"])
            vat_i = Decimal(l["vat_amount"])
            tc = l["tax_code_external_id"]
            if net_i == Decimal("0") and vat_i > 0:
                vat_only_by_tc[tc] += vat_i
            elif net_i > 0 and (vat_i == Decimal("0") or vat_i == Decimal("0.0000")):
                taxable_indices_by_tc[tc].append(i)

        # Distribute VAT totals proportionally to taxable lines' net amounts
        for tc, total_vat in vat_only_by_tc.items():
            indices = taxable_indices_by_tc.get(tc, [])
            if not indices:
                continue
            total_net = sum(Decimal(lines[i]["net_amount"]) for i in indices)
            if total_net == Decimal("0"):
                continue
            distributed = []
            for i in indices:
                net_i = Decimal(lines[i]["net_amount"])
                share = (net_i / total_net)
                assigned = (total_vat * share).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
                distributed.append(assigned)
            # Adjust for rounding: ensure sum(distributed) equals total_vat
            diff = total_vat - sum(distributed)
            if diff != Decimal("0") and distributed:
                distributed[0] = (distributed[0] + diff).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            for idx, i in enumerate(indices):
                lines[i]["vat_amount"] = str(distributed[idx])

        # Remove VAT-only lines (they've been distributed)
        lines = [l for l in lines if not (Decimal(l["net_amount"]) == Decimal("0") and Decimal(l["vat_amount"]) > 0 and l["tax_code_external_id"] in vat_only_by_tc)]

        # Validate per-line VAT against expected tax-rate and adjust obvious mismatches
        for i, l in enumerate(lines):
            try:
                tc = l["tax_code_external_id"]
                rate = Decimal(TAX_CODE_RATES.get(tc, {}).get("rate", "0"))
                net_i = Decimal(l["net_amount"])
                expected_vat = (net_i * rate).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
                provided_vat = Decimal(l["vat_amount"])
                # If expected is non-zero and provided differs significantly, correct it
                if expected_vat != Decimal("0") and abs(provided_vat - expected_vat) > Decimal("0.01"):
                    print(f"  ⚠ Correcting VAT for REF={fmt_ref(ref)} line {i}: provided={provided_vat}, expected={expected_vat}")
                    l["vat_amount"] = str(expected_vat)
            except Exception:
                continue

        payload = {
            "external_invoice_id": f"INV-{fmt_ref(ref)}",
            "vendor_external_id": vendor,
            "invoice_date": invoice_date,
            "lines": lines,
        }

        # If no valid lines remain, skip this invoice
        if not lines:
            print(f"  ⚠ [SKIP] INV-{fmt_ref(ref)} has no valid lines; skipping")
            skipped += 1
            continue

        resp = client.post(f"{base_url}/invoices", json=payload)

        invoice_label = f"INV-{fmt_ref(ref)}"
        if resp.status_code == 201:
            succeeded += 1
            print(f"  ✓ [NEW]  {invoice_label} | {vendor} | {len(lines)} lines | {invoice_date}")
        elif resp.status_code == 200:
            skipped += 1
            print(f"  → [DUP]  {invoice_label} already exists (idempotent skip)")
        else:
            failed += 1
            # Try to decode JSON safely; fall back to plain text
            try:
                err = resp.json()
                detail = err.get('detail', err)
            except Exception:
                detail = resp.text
            out = json.dumps(detail, indent=2)[:400] if not isinstance(detail, str) else str(detail)[:400]
            print(f"  ✗ [FAIL] {invoice_label}: {out}")

    print(f"\n── Summary: {succeeded}/{total} new | {skipped} skipped | {failed} failed ──")


def main():
    parser = argparse.ArgumentParser(description="Seed AP Integration API from CSV")
    parser.add_argument("--csv", required=True, help="Path to line_items.csv")
    parser.add_argument("--base-url", default="http://localhost:8000", help="API base URL")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"Error: CSV file not found: {csv_path}")
        sys.exit(1)

    print(f"Loading CSV: {csv_path}")
    df = pd.read_csv(csv_path)
    print(f"Loaded {len(df)} rows, {df['REF'].nunique()} unique invoices")

    # Validate expected columns
    required_cols = {"DATE", "REF", "DETAIL", "NET", "TC", "VAT", "SUPPLIER", "NOMINAL", "DEPARTMENT"}
    missing = required_cols - set(df.columns)
    if missing:
        print(f"Error: Missing columns in CSV: {missing}")
        sys.exit(1)

    with httpx.Client(timeout=30.0) as client:
        # Health check first
        try:
            health = client.get(f"{args.base_url}/health")
            print(f"API health: {health.json()}")
        except Exception as e:
            print(f"Cannot reach API at {args.base_url}: {e}")
            print("Make sure the API is running: uvicorn app.main:app --reload")
            sys.exit(1)

        seed_master_data(client, args.base_url, df)
        seed_invoices(client, args.base_url, df)

    print("\n✓ Seeding complete.")


if __name__ == "__main__":
    main()
