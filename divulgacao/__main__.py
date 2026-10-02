"""Permite `python -m divulgacao ...` a partir da raiz do projeto."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
