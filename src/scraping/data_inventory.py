"""
Data inventory — scans all collected raw data and produces a manifest.
Also validates content quality before RAG ingestion.
Run: python data_inventory.py
"""

import os
import json
from pathlib import Path
from collections import defaultdict
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()
BASE_DATA_DIR = Path(__file__).parent.parent.parent / "data" / "raw"


def scan_inventory():
    """Scan all collected JSON files and print summary."""
    stats = defaultdict(lambda: defaultdict(int))
    issues = []
    all_records = []

    for company_dir in sorted(BASE_DATA_DIR.iterdir()):
        if not company_dir.is_dir():
            continue
        company = company_dir.name.upper()

        for round_dir in sorted(company_dir.iterdir()):
            if not round_dir.is_dir():
                continue
            round_type = round_dir.name

            for json_file in round_dir.glob("*.json"):
                try:
                    with open(json_file) as f:
                        data = json.load(f)

                    # Handle both single records and batch results
                    records = data.get("results", [data]) if "results" in data else [data]

                    for rec in records:
                        content = rec.get("content", "")
                        char_count = len(content)
                        stats[company][round_type] += 1

                        if char_count < 300:
                            issues.append(f"⚠ Short ({char_count}c): {json_file.name}")
                        elif char_count > 100000:
                            issues.append(f"⚠ Very long ({char_count}c): {json_file.name}")

                        all_records.append({
                            "file": str(json_file.relative_to(BASE_DATA_DIR)),
                            "company": rec.get("company", company),
                            "round_type": rec.get("round_type", round_type),
                            "source_type": rec.get("source_type", "?"),
                            "char_count": char_count,
                            "url": rec.get("url", ""),
                            "scraped_at": rec.get("scraped_at", ""),
                        })

                except Exception as e:
                    issues.append(f"✗ Parse error {json_file.name}: {e}")

    # Print company/round breakdown table
    table = Table(title="Data Inventory by Company & Round", border_style="green")
    table.add_column("Company", style="bold cyan")
    table.add_column("Round Type", style="bold")
    table.add_column("Records", style="green", justify="right")

    totals = defaultdict(int)
    for company in sorted(stats.keys()):
        for round_type in sorted(stats[company].keys()):
            count = stats[company][round_type]
            table.add_row(company, round_type, str(count))
            totals[company] += count

    table.add_section()
    for company, total in sorted(totals.items()):
        table.add_row(f"[bold]{company} TOTAL[/]", "", f"[bold]{total}[/]")

    console.print(table)

    # Source type breakdown
    source_stats = defaultdict(int)
    for rec in all_records:
        source_stats[rec["source_type"]] += 1

    source_table = Table(title="By Source Type", border_style="blue")
    source_table.add_column("Source Type")
    source_table.add_column("Records", justify="right")
    for src, cnt in sorted(source_stats.items(), key=lambda x: -x[1]):
        source_table.add_row(src, str(cnt))
    console.print(source_table)

    # Issues
    if issues:
        console.print(Panel("\n".join(issues[:20]), title="[yellow]Issues[/]", border_style="yellow"))

    # Save manifest
    manifest_path = BASE_DATA_DIR / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump({
            "total_records": len(all_records),
            "records": all_records,
        }, f, indent=2)
    console.print(f"\n[bold green]Manifest saved:[/] {manifest_path}")
    console.print(f"[bold]Total records:[/] {len(all_records)}")

    return all_records


if __name__ == "__main__":
    scan_inventory()