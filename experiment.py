"""Run the drift experiment and write its metrics as JSON."""

import argparse

from capturedrift import DATA_DIR
from capturedrift.run import main


def parse_args(argv=None):
    """The output path and the data directory to read."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="results/metrics.json", help="where to write the metrics JSON")
    parser.add_argument("--data", default=str(DATA_DIR), help="data directory holding MANIFEST.json")
    return parser.parse_args(argv)


if __name__ == "__main__":
    arguments = parse_args()
    main(arguments.data, arguments.out)
