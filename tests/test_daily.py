"""Tests del resumen diario por WhatsApp: banderas, formato, filtro y carga de teléfonos."""
import json
from datetime import date

from app.services import whatsapp
from app.services.daily import format_daily_message, todays_matches
from app.services.flags import emoji_flag


def test_emoji_flag_regular_country():
    assert emoji_flag("MEX") == "\U0001F1F2\U0001F1FD"  # 🇲🇽
    assert emoji_flag("mex") == "\U0001F1F2\U0001F1FD"  # case-insensitive


def test_emoji_flag_subdivisions_and_unknown():
    eng = emoji_flag("ENG")
    assert eng.startswith("\U0001F3F4") and eng.endswith("\U000E007F")  # bandera de Inglaterra
    assert emoji_flag("SCO") and emoji_flag("WAL")
    assert emoji_flag("XYZ") == ""  # código desconocido
    assert emoji_flag(None) == ""


def test_format_daily_message_layout():
    matches = [
        {"time": "23:00", "home_es": "Corea del Sur", "away_es": "Chequia",
         "home_code": "KOR", "away_code": "CZE"},
        {"time": "16:00", "home_es": "México", "away_es": "Sudáfrica",
         "home_code": "MEX", "away_code": "RSA"},
    ]
    msg = format_daily_message(matches, date(2026, 6, 11))
    assert "Partidos de hoy" in msg
    # Formato pedido: "HH:MM hs   🏠bandera Local vs Visitante bandera🏁"
    assert "16:00 hs   \U0001F1F2\U0001F1FD México vs Sudáfrica \U0001F1FF\U0001F1E6" in msg
    # La bandera del local va antes del nombre; la del visitante, después.
    assert msg.index("\U0001F1F2\U0001F1FD") < msg.index("México")


def test_format_daily_message_empty():
    msg = format_daily_message([], date(2026, 6, 11))
    assert "no hay partidos" in msg.lower()


def test_todays_matches_filters_and_sorts():
    # El fixture tiene partidos el día inaugural (11-jun-2026).
    matches = todays_matches(date(2026, 6, 11))
    assert matches, "Debería haber partidos el 2026-06-11"
    assert all(m["date"] == "2026-06-11" for m in matches)
    times = [m.get("time") or "99:99" for m in matches]
    assert times == sorted(times)  # ordenados por hora


def test_notifier_dry_run_builds_without_sending():
    import asyncio

    from app.services import notifier

    notifier.JOBS["_t_msg"] = lambda: "hola mundo"
    try:
        res = asyncio.run(notifier.run_job("_t_msg", dry_run=True))
    finally:
        del notifier.JOBS["_t_msg"]
    assert res["status"] == "dry_run" and res["message"] == "hola mundo"


def test_notifier_skips_empty_message():
    import asyncio

    from app.services import notifier

    notifier.JOBS["_t_empty"] = lambda: ""  # job sin contenido (ej. día sin partidos)
    try:
        res = asyncio.run(notifier.run_job("_t_empty"))
    finally:
        del notifier.JOBS["_t_empty"]
    assert res["status"] == "skipped"  # no intenta enviar


def test_notifier_unknown_job():
    import asyncio

    from app.services import notifier

    res = asyncio.run(notifier.run_job("no_existe"))
    assert res["status"] == "error"


def test_load_phones_sanitizes_and_skips_comment(tmp_path, monkeypatch):
    f = tmp_path / "phones.json"
    f.write_text(json.dumps({
        "_comment": "ignorar 99999",
        "Pablo": "+54 9 11 1234-5678",
        "Vacío": "",
    }), encoding="utf-8")
    monkeypatch.setattr(whatsapp, "phones_path", lambda: f)
    phones = whatsapp.load_phones()
    assert phones == {"Pablo": "5491112345678"}  # solo dígitos, sin _comment ni vacíos
