from __future__ import annotations

import sys
from pathlib import Path

from markitdown import MarkItDown


def transcribe_any_file(filepath: str):
    """Transcribe any supported file (PDF, PPTX, DOCX, XLSX, JPG, PNG, etc.) using MarkItDown."""
    path = Path(filepath)
    if not path.exists():
        print(f"❌ File not found: {path}")
        return

    print(f"📂 Processing: {path.name}")

    md = MarkItDown(enable_plugins=False)

    try:
        result = md.convert(str(path))
        output_md = path.with_suffix(".md")
        with open(output_md, "w", encoding="utf-8") as f:
            f.write(result.text_content)
        print(f"✅ Transcribed → {output_md}")
    except Exception as e:
        print(f"⚠️ Error processing {path.name}: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python markitdown_auto_detect.py <file1> [<file2> ...]")
        sys.exit(1)

    for file in sys.argv[1:]:
        transcribe_any_file(file)
