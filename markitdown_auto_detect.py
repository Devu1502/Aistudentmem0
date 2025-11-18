# Quick utility to convert PDFs into plaintext snippets.
from __future__ import annotations

import sys
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError


def extract_pdf(filepath: str):
    """Extract plain text from a PDF file using PyPDF."""
    path = Path(filepath)
    if not path.exists():
        print(f"File not found: {path}")
        return

    print(f"Processing: {path.name}")

    try:
        reader = PdfReader(str(path))
        output_txt = path.with_suffix(".txt")
        with open(output_txt, "w", encoding="utf-8") as f:
            for page in reader.pages:
                text = page.extract_text() or ""
                f.write(text)
        print(f"Extracted -> {output_txt}")
    except PdfReadError as err:
        print(f"Unable to read {path.name}: {err}")
    except Exception as err:
        print(f"Error processing {path.name}: {err}")


if __name__ == "__main__":
    # Allow running `python markitdown_auto_detect.py file.pdf`.
    if len(sys.argv) < 2:
        print("Usage: python markitdown_auto_detect.py <pdf1> [<pdf2> ...]")
        sys.exit(1)

    for file in sys.argv[1:]:
        extract_pdf(file)
