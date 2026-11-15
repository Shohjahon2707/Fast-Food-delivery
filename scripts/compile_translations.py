"""Build standard gettext catalogs without requiring system gettext tools."""

import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
translations = json.loads((ROOT / "locale/translations.json").read_text())
for language in ("en", "uz"):
    messages = {key: value[language] for key, value in translations.items()}
    messages[""] = (
        "Content-Type: text/plain; charset=UTF-8\nLanguage: "
        + language
        + "\nPlural-Forms: nplurals=2; plural=(n != 1);\n"
    )
    keys = sorted(messages)
    originals = [key.encode() for key in keys]
    values = [messages[key].encode() for key in keys]
    count = len(keys)
    offset = 28 + count * 16
    original_table, translation_table = [], []
    for item in originals:
        original_table.extend([len(item), offset])
        offset += len(item) + 1
    for item in values:
        translation_table.extend([len(item), offset])
        offset += len(item) + 1
    header = struct.pack("<7I", 0x950412DE, 0, count, 28, 28 + count * 8, 0, 0)
    tables = struct.pack("<" + "I" * count * 4, *original_table, *translation_table)
    directory = ROOT / "locale" / language / "LC_MESSAGES"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "django.mo").write_bytes(
        header + tables + b"\0".join(originals) + b"\0" + b"\0".join(values) + b"\0"
    )
    (directory / "django.po").write_text(
        "\n\n".join(
            "msgid "
            + json.dumps(key, ensure_ascii=False)
            + "\nmsgstr "
            + json.dumps(messages[key], ensure_ascii=False)
            for key in keys
        )
        + "\n"
    )
    print(f"{language}: {count - 1} translations compiled")
