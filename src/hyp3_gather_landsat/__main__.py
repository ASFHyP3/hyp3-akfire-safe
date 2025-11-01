"""gather-landsat processing for HyP3."""

import argparse
import logging
import sys
from argparse import ArgumentParser
from importlib.metadata import entry_points


def main() -> None:
    """HyP3 entrypoint for hyp3_gather_landsat."""
    parser = ArgumentParser(prefix_chars='+', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '++process',
        choices=[
            'gather_landsat',
            'pull_perimeter',
            'feds',
        ],
        default='gather_landsat',
        help='Select the HyP3 entrypoint to use',  # HyP3 entrypoints are specified in `pyproject.toml`
    )

    args, unknowns = parser.parse_known_args()

    logging.basicConfig(
        format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p', level=logging.INFO
    )

    process_entry_point = list(entry_points(group='hyp3', name=args.process))[0]

    sys.argv = [args.process, *unknowns]
    sys.exit(process_entry_point.load()())


if __name__ == '__main__':
    main()
