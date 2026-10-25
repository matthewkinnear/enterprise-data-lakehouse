
"""Generate reproducible synthetic ERP sales-order data."""

import csv
import logging
import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import TypedDict


LOGGER = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "raw" / "sales_orders.csv"


class SalesRecord(TypedDict):
    """A single ERP sales-order line."""

    order_id: int
    line_id: int
    order_date: str
    customer_id: str
    product_id: str
    quantity: int
    unit_price: str
    order_status: str


@dataclass(frozen=True, slots=True)
class GeneratorConfig:
    """Configuration for synthetic sales generation."""

    seed: int = 42
    target_lines: int = 10_000
    customer_count: int = 500
    product_count: int = 200
    max_lines_per_order: int = 5
    duplicate_count: int = 50
    start_order_id: int = 1001
    start_date: date = date(2026, 7, 1)
    date_range_days: int = 90

    def __post_init__(self) -> None:
        positive_fields = (
            "target_lines",
            "customer_count",
            "product_count",
            "max_lines_per_order",
            "date_range_days",
        )

        for field_name in positive_fields:
            if getattr(self, field_name) <= 0:
                raise ValueError(f"{field_name} must be positive")

        if self.duplicate_count < 0:
            raise ValueError("duplicate_count cannot be negative")


ORDER_FIELDS = tuple(SalesRecord.__annotations__)

ERROR_COUNTS = {
    "missing_customer": 30,
    "negative_quantity": 25,
    "zero_price": 20,
    "invalid_date": 15,
    "invalid_status": 10,
}

ORDER_STATUSES = ("Completed", "Pending", "Cancelled")
STATUS_WEIGHTS = (80, 15, 5)


def generate_ids(prefix: str, count: int) -> list[str]:
    """Generate sequential, zero-padded identifiers."""
    if count < 0:
        raise ValueError("count cannot be negative")

    return [
        f"{prefix}{number:04d}"
        for number in range(1, count + 1)
    ]


def generate_orders(
    rng: random.Random,
    config: GeneratorConfig,
) -> list[SalesRecord]:
    """Generate exactly the requested number of valid order lines."""

    customers = generate_ids("C", config.customer_count)
    products = generate_ids("P", config.product_count)

    records: list[SalesRecord] = []
    order_id = config.start_order_id

    while len(records) < config.target_lines:
        remaining = config.target_lines - len(records)

        line_count = min(
            rng.randint(1, config.max_lines_per_order),
            remaining,
        )

        # Shared attributes for the entire order.
        customer_id = rng.choice(customers)

        order_date = config.start_date + timedelta(
            days=rng.randrange(config.date_range_days)
        )

        order_status = rng.choices(
            ORDER_STATUSES,
            weights=STATUS_WEIGHTS,
            k=1,
        )[0]

        # Attributes specific to each order line.
        for line_id in range(1, line_count + 1):
            price_pence = rng.randint(100, 50_000)

            unit_price = Decimal(price_pence) / 100

            records.append(
                {
                    "order_id": order_id,
                    "line_id": line_id,
                    "order_date": order_date.isoformat(),
                    "customer_id": customer_id,
                    "product_id": rng.choice(products),
                    "quantity": rng.randint(1, 20),
                    "unit_price": f"{unit_price:.2f}",
                    "order_status": order_status,
                }
            )

        order_id += 1

    return records


def corrupt_record(
    record: SalesRecord,
    error_type: str,
) -> None:
    """Apply a specified data-quality defect to a record."""

    match error_type:
        case "missing_customer":
            record["customer_id"] = ""

        case "negative_quantity":
            record["quantity"] = -record["quantity"]

        case "zero_price":
            record["unit_price"] = "0.00"

        case "invalid_date":
            record["order_date"] = "invalid-date"

        case "invalid_status":
            record["order_status"] = "Unknown"

        case _:
            raise ValueError(f"Unknown error type: {error_type}")


def inject_errors(
    rng: random.Random,
    records: list[SalesRecord],
    duplicate_count: int,
) -> list[SalesRecord]:
    """Inject non-overlapping defects and duplicate valid rows."""

    total_errors = sum(ERROR_COUNTS.values())
    valid_candidates = len(records) - total_errors

    if total_errors > len(records):
        raise ValueError("Not enough records for error injection")

    if duplicate_count > valid_candidates:
        raise ValueError("Not enough valid records for duplicates")

    output = [record.copy() for record in records]

    # Sample once to ensure validation defects do not overlap.
    error_indices = rng.sample(
        range(len(output)),
        total_errors,
    )

    offset = 0

    for error_type, count in ERROR_COUNTS.items():
        selected = error_indices[offset : offset + count]

        for index in selected:
            corrupt_record(output[index], error_type)

        offset += count

    # Duplicates must come from records without injected defects.
    invalid_indices = set(error_indices)

    valid_indices = [
        index
        for index in range(len(output))
        if index not in invalid_indices
    ]

    for index in rng.sample(valid_indices, duplicate_count):
        output.append(output[index].copy())

    return output


def validate_counts(
    records: list[SalesRecord],
    config: GeneratorConfig,
) -> None:
    """Check the generated physical record count."""

    expected = config.target_lines + config.duplicate_count

    if len(records) != expected:
        raise ValueError(
            f"Expected {expected:,} records, "
            f"received {len(records):,}"
        )


def write_csv(
    records: list[SalesRecord],
    output_path: Path,
) -> None:
    """Write records to CSV with a consistent column order."""

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:
        writer = csv.DictWriter(file, fieldnames=ORDER_FIELDS)
        writer.writeheader()
        writer.writerows(records)


def main() -> None:
    """Run the synthetic sales-data generation pipeline."""

    config = GeneratorConfig()
    rng = random.Random(config.seed)

    records = generate_orders(rng, config)

    output = inject_errors(
        rng=rng,
        records=records,
        duplicate_count=config.duplicate_count,
    )

    validate_counts(output, config)
    write_csv(output, DEFAULT_OUTPUT)

    LOGGER.info("Generated %s original lines", config.target_lines)
    LOGGER.info("Injected %s validation errors", sum(ERROR_COUNTS.values()))
    LOGGER.info("Added %s duplicates", config.duplicate_count)
    LOGGER.info("Wrote %s records to %s", len(output), DEFAULT_OUTPUT)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s | %(message)s",
    )
    main()
