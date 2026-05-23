#!/usr/bin/env python3
"""
assemble_project_files.py

Recursively collects Python source files and YAML configuration files
from one or more directories and combines them into a single master file.

Included file types:
- .yaml
- .yml
- .py

YAML files are always placed BEFORE Python files.

Features:
- Recursive directory scanning
- Skips common junk folders (__pycache__, .git, venv, etc.)
- Preserves file paths as section headers
- Optional exclusion patterns
- Deterministic ordering

Usage:
    python3 assemble_python_project.py output.txt src1 src2 src3

Example:
    (alpaca) zhaohuiwang@WangFamily:~/dev/finance-project$ python3 assemble_python_project.py master_project.txt ./alpaca

Optional:
    python3 assemble_python_project.py master.txt . --exclude tests migrations
"""

from pathlib import Path
import argparse
import sys


DEFAULT_EXCLUDES = {
    "__pycache__",
    ".git",
    ".idea",
    ".vscode",
    "venv",
    ".venv",
    "env",
    "node_modules",
    "dist",
    "build",
    ".mypy_cache",
    ".pytest_cache",
}


YAML_EXTENSIONS = {".yaml", ".yml"}
PYTHON_EXTENSIONS = {".py"}

SUPPORTED_EXTENSIONS = YAML_EXTENSIONS.union(PYTHON_EXTENSIONS)


def should_skip(path: Path, exclude_names: set[str]) -> bool:
    return any(part in exclude_names for part in path.parts)


def collect_files(paths, exclude_names):
    collected_files = []

    for base in paths:
        base_path = Path(base).resolve()

        if not base_path.exists():
            print(f"[WARNING] Path does not exist: {base}")
            continue

        # Single file input
        if base_path.is_file():
            if base_path.suffix.lower() in SUPPORTED_EXTENSIONS:
                collected_files.append(base_path)
            continue

        # Directory scan
        for file in base_path.rglob("*"):
            if should_skip(file, exclude_names):
                continue

            if file.is_file() and file.suffix.lower() in SUPPORTED_EXTENSIONS:
                collected_files.append(file)

    # Remove duplicates
    collected_files = list(set(collected_files))

    # YAML first, then Python
    yaml_files = sorted(
        [f for f in collected_files if f.suffix.lower() in YAML_EXTENSIONS]
    )

    python_files = sorted(
        [f for f in collected_files if f.suffix.lower() in PYTHON_EXTENSIONS]
    )

    return yaml_files + python_files


def assemble_files(files, output_file):
    with open(output_file, "w", encoding="utf-8") as out:
        out.write("# AUTO-GENERATED MASTER PROJECT FILE\n")
        out.write("# ----------------------------------\n\n")

        for file_path in files:
            separator = "=" * 80

            out.write(f"\n# {separator}\n")
            out.write(f"# FILE: {file_path}\n")
            out.write(f"# {separator}\n\n")

            try:
                content = file_path.read_text(encoding="utf-8")

                out.write(content)

                if not content.endswith("\n"):
                    out.write("\n")

            except Exception as e:
                out.write(f"# ERROR READING FILE: {e}\n")

            out.write("\n")

    print(f"[DONE] Combined {len(files)} files into: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Assemble Python and YAML project files into one master file."
    )

    parser.add_argument(
        "output",
        help="Output master file path"
    )

    parser.add_argument(
        "sources",
        nargs="+",
        help="Directories or files to scan"
    )

    parser.add_argument(
        "--exclude",
        nargs="*",
        default=[],
        help="Additional directory/file names to exclude"
    )

    args = parser.parse_args()

    exclude_names = DEFAULT_EXCLUDES.union(set(args.exclude))

    files = collect_files(args.sources, exclude_names)

    if not files:
        print("[ERROR] No matching files found.")
        sys.exit(1)

    assemble_files(files, args.output)


if __name__ == "__main__":
    main()