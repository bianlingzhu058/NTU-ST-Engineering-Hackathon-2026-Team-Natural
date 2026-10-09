"""Review Sysmon process creation records without presuming parent lineage."""
import argparse
import csv
import logging
from pathlib import Path


def main() -> None:
    """List process creation events and their recorded parent images."""
    parser = argparse.ArgumentParser(); parser.add_argument("csv_path", type=Path); args = parser.parse_args()
    try:
        with args.csv_path.open(encoding="utf-8-sig", newline="") as file:
            for row in csv.DictReader(file):
                if row.get("EventID") == "1":
                    logging.info("Image=%s ParentImage=%s", row.get("Image", ""), row.get("ParentImage", ""))
    except OSError as exc: parser.error(str(exc))


if __name__ == "__main__": main()
