import json
from pathlib import Path

from die_firma.i18n import (
    DEFAULT_LANG,
    LOCALES_DIR,
    available_languages,
    load_translator,
)


def test_english_is_default_and_formats():
    tr = load_translator("en")
    assert tr.t("cli.approved", id="abc") == "approved abc"


def test_german_catalogue_translates():
    tr = load_translator("de")
    msg = tr.t("cli.approved", id="abc")
    assert msg == "freigegeben abc"


def test_missing_key_falls_back_to_key():
    tr = load_translator("en")
    assert tr.t("does.not.exist") == "does.not.exist"


def test_unknown_language_falls_back_to_english(tmp_path: Path):
    (tmp_path / "en.json").write_text(json.dumps({"k": "english {x}"}), encoding="utf-8")
    tr = load_translator("xx", locales_dir=tmp_path)
    assert tr.t("k", x=1) == "english 1"


def test_partial_translation_uses_english_for_missing(tmp_path: Path):
    (tmp_path / "en.json").write_text(json.dumps({"a": "A", "b": "B"}), encoding="utf-8")
    (tmp_path / "de.json").write_text(json.dumps({"a": "Ä"}), encoding="utf-8")
    tr = load_translator("de", locales_dir=tmp_path)
    assert tr.t("a") == "Ä"  # translated
    assert tr.t("b") == "B"  # falls back to english


def test_available_languages_lists_shipped_catalogues():
    langs = available_languages()
    assert DEFAULT_LANG in langs
    assert "de" in langs


def test_shipped_catalogues_have_matching_keys():
    # de must cover exactly the english keys (no drift).
    en = json.loads((LOCALES_DIR / "en.json").read_text(encoding="utf-8"))
    de = json.loads((LOCALES_DIR / "de.json").read_text(encoding="utf-8"))
    assert set(en) == set(de)
