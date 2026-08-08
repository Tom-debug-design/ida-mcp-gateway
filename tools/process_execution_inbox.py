from __future__ import annotations

import json

from execution_worker import process_next_execution


def main() -> None:
    print(json.dumps(process_next_execution(), indent=2, default=str))


if __name__ == "__main__":
    main()
