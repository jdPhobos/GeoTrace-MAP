import csv
import datetime
import ipaddress
import json
import math
import os
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from tkinter import filedialog, messagebox, ttk

import requests

CONFIG = {
    "map_file": os.path.join(os.path.expanduser("~"), "desktop_trace_map.html"),
    "data_js_file": os.path.join(os.path.expanduser("~"), "desktop_trace_data.js"),
    "settings_file": os.path.join(os.path.expanduser("~"), "geotrace_settings.json"),
    "learn_file": os.path.join(os.path.expanduser("~"), "geotrace_learned.json"),
    "peeringdb_file": os.path.join(os.path.expanduser("~"), "geotrace_peeringdb.json"),
    "timeout": 3,
}

# Global socket timeout so blocking calls with no explicit timeout (e.g. PTR lookups via
# socket.gethostbyaddr in ptr_city_code) can't hang a worker thread indefinitely on a slow
# or unresponsive DNS server. requests/session calls are unaffected — they always pass an
# explicit timeout=. Set once at import time to avoid races from concurrent PTR workers
# flipping this global back and forth.
socket.setdefaulttimeout(CONFIG["timeout"])

THEMES = {
    "light": {"bg": "#f2f4f8", "panel": "#e1e4ea", "fg": "#1f2937",
              "entry_bg": "#ffffff", "entry_fg": "#111827",
              "log_bg": "#1e1e1e", "log_fg": "#ffffff",
              "btn_bg": "#e1e1e1", "btn_fg": "#000000",
              "accent": "#0288d1", "hover": "#d3d9e3",
              "danger_hover": "#b71c1c", "outline": "#c2c8d4"},
    "dark": {"bg": "#1e1e2e", "panel": "#2b2b3d", "fg": "#e5e7eb",
             "entry_bg": "#28283a", "entry_fg": "#e5e7eb",
             "log_bg": "#14141f", "log_fg": "#d7d7e2",
             "btn_bg": "#3a3a4e", "btn_fg": "#e5e7eb",
             "accent": "#4fc3f7", "hover": "#3d3d55",
             "danger_hover": "#c62828", "outline": "#4a4a68"},
}

MAP_THEMES = {
    "light": {"body": "#fcfaf2", "land": "#fcfaf2", "ocean": "#e0f2f1",
              "country": "#90a4ae", "title": "#37474f", "annot": "#78909c",
              "label": "#37474f"},
    "dark": {"body": "#0e1526", "land": "#16203a", "ocean": "#0a101f",
             "country": "#3b4a63", "title": "#e2e8f0", "annot": "#8fa3bf",
             "label": "#e2e8f0"},
}

CITY_DB = {
    "msk": ("Москва", "Moscow", 55.7558, 37.6173, "Россия", "Russia"),
    "spb": ("Санкт-Петербург", "Saint Petersburg", 59.9343, 30.3351, "Россия", "Russia"),
    "led": ("Санкт-Петербург", "Saint Petersburg", 59.9343, 30.3351, "Россия", "Russia"),
    "svx": ("Екатеринбург", "Yekaterinburg", 56.8389, 60.6057, "Россия", "Russia"),
    "ovb": ("Новосибирск", "Novosibirsk", 55.0084, 82.9357, "Россия", "Russia"),
    "kja": ("Красноярск", "Krasnoyarsk", 56.0153, 92.8932, "Россия", "Russia"),
    "khv": ("Хабаровск", "Khabarovsk", 48.4827, 135.0838, "Россия", "Russia"),
    "vvo": ("Владивосток", "Vladivostok", 43.1056, 131.8735, "Россия", "Russia"),
    "kzn": ("Казань", "Kazan", 55.7963, 49.1088, "Россия", "Russia"),
    "goj": ("Нижний Новгород", "Nizhny Novgorod", 56.2965, 43.9361, "Россия", "Russia"),
    "nnov": ("Нижний Новгород", "Nizhny Novgorod", 56.2965, 43.9361, "Россия", "Russia"),
    "kuf": ("Самара", "Samara", 53.1959, 50.1008, "Россия", "Russia"),
    "ufa": ("Уфа", "Ufa", 54.7388, 55.9721, "Россия", "Russia"),
    "rov": ("Ростов-на-Дону", "Rostov-on-Don", 47.2357, 39.7015, "Россия", "Russia"),
    "krr": ("Краснодар", "Krasnodar", 45.0355, 38.9753, "Россия", "Russia"),
    "aar": ("Сочи", "Sochi", 43.6028, 39.7342, "Россия", "Russia"),
    "cek": ("Челябинск", "Chelyabinsk", 55.1644, 61.4368, "Россия", "Russia"),
    "chel": ("Челябинск", "Chelyabinsk", 55.1644, 61.4368, "Россия", "Russia"),
    "pee": ("Пермь", "Perm", 58.0105, 56.2502, "Россия", "Russia"),
    "voz": ("Воронеж", "Voronezh", 51.6720, 39.1843, "Россия", "Russia"),
    "vog": ("Волгоград", "Volgograd", 48.7080, 44.5133, "Россия", "Russia"),
    "mmk": ("Мурманск", "Murmansk", 68.9585, 33.0827, "Россия", "Russia"),
    "kgd": ("Калининград", "Kaliningrad", 54.7104, 20.4522, "Россия", "Russia"),
    "ikt": ("Иркутск", "Irkutsk", 52.2870, 104.3050, "Россия", "Russia"),
    "hta": ("Чита", "Chita", 52.0340, 113.4994, "Россия", "Russia"),
    "yks": ("Якутск", "Yakutsk", 62.0355, 129.6755, "Россия", "Russia"),
    "gdx": ("Магадан", "Magadan", 59.5550, 150.8050, "Россия", "Russia"),
    "pks": ("Петропавловск-Камчатский", "Petropavlovsk-Kamchatsky", 53.0167, 158.6500, "Россия", "Russia"),
    "fra": ("Франкфурт", "Frankfurt", 50.1109, 8.6821, "Германия", "Germany"),
    "ber": ("Берлин", "Berlin", 52.5200, 13.4050, "Германия", "Germany"),
    "ams": ("Амстердам", "Amsterdam", 52.3676, 4.9041, "Нидерланды", "Netherlands"),
    "lhr": ("Лондон", "London", 51.5074, -0.1278, "Великобритания", "UK"),
    "cdg": ("Париж", "Paris", 48.8566, 2.3522, "Франция", "France"),
    "hel": ("Хельсинки", "Helsinki", 60.1699, 24.9384, "Финляндия", "Finland"),
    "arn": ("Стокгольм", "Stockholm", 59.3293, 18.0686, "Швеция", "Sweden"),
    "cph": ("Копенгаген", "Copenhagen", 55.6761, 12.5683, "Дания", "Denmark"),
    "waw": ("Варшава", "Warsaw", 52.2297, 21.0122, "Польша", "Poland"),
    "prg": ("Прага", "Prague", 50.0755, 14.4378, "Чехия", "Czechia"),
    "vie": ("Вена", "Vienna", 48.2082, 16.3738, "Австрия", "Austria"),
    "bud": ("Будапешт", "Budapest", 47.4979, 19.0402, "Венгрия", "Hungary"),
    "sof": ("София", "Sofia", 42.6977, 23.3219, "Болгария", "Bulgaria"),
    "ist": ("Стамбул", "Istanbul", 41.0082, 28.9784, "Турция", "Turkey"),
    "dxb": ("Дубай", "Dubai", 25.2048, 55.2708, "ОАЭ", "UAE"),
    "hkg": ("Гонконг", "Hong Kong", 22.3193, 114.1694, "Гонконг", "Hong Kong"),
    "sgp": ("Сингапур", "Singapore", 1.3521, 103.8198, "Сингапур", "Singapore"),
    "nrt": ("Токио", "Tokyo", 35.6762, 139.6503, "Япония", "Japan"),
    "icn": ("Сеул", "Seoul", 37.5665, 126.9780, "Корея", "South Korea"),
    "pek": ("Пекин", "Beijing", 39.9042, 116.4074, "Китай", "China"),
    "lax": ("Лос-Анджелес", "Los Angeles", 34.0522, -118.2437, "США", "USA"),
    "jfk": ("Нью-Йорк", "New York", 40.7128, -74.0060, "США", "USA"),
    "iad": ("Вашингтон", "Washington", 38.9072, -77.0369, "США", "USA"),
    "ord": ("Чикаго", "Chicago", 41.8781, -87.6298, "США", "USA"),
    "sea": ("Сиэтл", "Seattle", 47.6062, -122.3321, "США", "USA"),
    "anc": ("Анкоридж", "Anchorage", 61.2181, -149.9003, "США", "USA"),
}

# Переводы городов/стран для fallback (когда GeoIP вернул английское название)
CITY_TRANSLATIONS = {
    "Moscow": ("Москва", "Россия"),
    "Saint Petersburg": ("Санкт-Петербург", "Россия"),
    "Yekaterinburg": ("Екатеринбург", "Россия"),
    "Novosibirsk": ("Новосибирск", "Россия"),
    "Krasnoyarsk": ("Красноярск", "Россия"),
    "Khabarovsk": ("Хабаровск", "Россия"),
    "Vladivostok": ("Владивосток", "Россия"),
    "Kazan": ("Казань", "Россия"),
    "Nizhny Novgorod": ("Нижний Новгород", "Россия"),
    "Samara": ("Самара", "Россия"),
    "Ufa": ("Уфа", "Россия"),
    "Rostov-on-Don": ("Ростов-на-Дону", "Россия"),
    "Krasnodar": ("Краснодар", "Россия"),
    "Sochi": ("Сочи", "Россия"),
    "Chelyabinsk": ("Челябинск", "Россия"),
    "Perm": ("Пермь", "Россия"),
    "Voronezh": ("Воронеж", "Россия"),
    "Volgograd": ("Волгоград", "Россия"),
    "Murmansk": ("Мурманск", "Россия"),
    "Kaliningrad": ("Калининград", "Россия"),
    "Irkutsk": ("Иркутск", "Россия"),
    "Chita": ("Чита", "Россия"),
    "Yakutsk": ("Якутск", "Россия"),
    "Magadan": ("Магадан", "Россия"),
    "Petropavlovsk-Kamchatsky": ("Петропавловск-Камчатский", "Россия"),
    "Frankfurt": ("Франкфурт", "Германия"),
    "Berlin": ("Берлин", "Германия"),
    "Amsterdam": ("Амстердам", "Нидерланды"),
    "London": ("Лондон", "Великобритания"),
    "Paris": ("Париж", "Франция"),
    "Helsinki": ("Хельсинки", "Финляндия"),
    "Stockholm": ("Стокгольм", "Швеция"),
    "Copenhagen": ("Копенгаген", "Дания"),
    "Warsaw": ("Варшава", "Польша"),
    "Prague": ("Прага", "Чехия"),
    "Vienna": ("Вена", "Австрия"),
    "Budapest": ("Будапешт", "Венгрия"),
    "Sofia": ("София", "Болгария"),
    "Istanbul": ("Стамбул", "Турция"),
    "Dubai": ("Дубай", "ОАЭ"),
    "Hong Kong": ("Гонконг", "Гонконг"),
    "Singapore": ("Сингапур", "Сингапур"),
    "Tokyo": ("Токио", "Япония"),
    "Seoul": ("Сеул", "Южная Корея"),
    "Beijing": ("Пекин", "Китай"),
    "Shanghai": ("Шанхай", "Китай"),
    "Los Angeles": ("Лос-Анджелес", "США"),
    "New York": ("Нью-Йорк", "США"),
    "Washington": ("Вашингтон", "США"),
    "Chicago": ("Чикаго", "США"),
    "Seattle": ("Сиэтл", "США"),
    "Anchorage": ("Анкоридж", "США"),
    "San Francisco": ("Сан-Франциско", "США"),
    "Miami": ("Майами", "США"),
    "Dallas": ("Даллас", "США"),
    "Denver": ("Денвер", "США"),
    "Atlanta": ("Атланта", "США"),
    "Boston": ("Бостон", "США"),
    "Toronto": ("Торонто", "Канада"),
    "Vancouver": ("Ванкувер", "Канада"),
    "Montreal": ("Монреаль", "Канада"),
    "Sydney": ("Сидней", "Австралия"),
    "Melbourne": ("Мельбурн", "Австралия"),
    "Mumbai": ("Мумбаи", "Индия"),
    "Delhi": ("Дели", "Индия"),
    "Bangalore": ("Бангалор", "Индия"),
    "Bangkok": ("Бангкок", "Таиланд"),
    "Kuala Lumpur": ("Куала-Лумпур", "Малайзия"),
    "Jakarta": ("Джакарта", "Индонезия"),
    "Manila": ("Манила", "Филиппины"),
    "Taipei": ("Тайбэй", "Тайвань"),
}

COUNTRY_TRANSLATIONS = {
    "Russia": "Россия", "Russian Federation": "Россия",
    "Germany": "Германия", "Netherlands": "Нидерланды",
    "United Kingdom": "Великобритания", "UK": "Великобритания",
    "France": "Франция", "Finland": "Финляндия",
    "Sweden": "Швеция", "Denmark": "Дания",
    "Poland": "Польша", "Czechia": "Чехия", "Czech Republic": "Чехия",
    "Austria": "Австрия", "Hungary": "Венгрия",
    "Bulgaria": "Болгария", "Turkey": "Турция",
    "United Arab Emirates": "ОАЭ", "UAE": "ОАЭ",
    "Hong Kong": "Гонконг", "Singapore": "Сингапур",
    "Japan": "Япония", "South Korea": "Южная Корея", "Korea": "Южная Корея",
    "China": "Китай", "United States": "США", "USA": "США",
    "Canada": "Канада", "Australia": "Австралия",
    "India": "Индия", "Thailand": "Таиланд",
    "Malaysia": "Малайзия", "Indonesia": "Индонезия",
    "Philippines": "Филиппины", "Taiwan": "Тайвань",
    "Brazil": "Бразилия", "Argentina": "Аргентина",
    "Mexico": "Мексика", "Chile": "Чили",
    "South Africa": "ЮАР", "Egypt": "Египет",
    "Israel": "Израиль", "Saudi Arabia": "Саудовская Аравия",
}


def translate_city(city: str, country: str, lang: str) -> tuple:
    """Перевод города/страны для fallback-случая (GeoIP вернул английское)."""
    if lang != "ru":
        return city, country
    if city in CITY_TRANSLATIONS:
        return CITY_TRANSLATIONS[city]
    city_lower = city.lower()
    for eng_city, pair in CITY_TRANSLATIONS.items():
        if city_lower in eng_city.lower() or eng_city.lower() in city_lower:
            return pair
    return city, COUNTRY_TRANSLATIONS.get(country, country)


def strip_as_prefix(asn) -> str:
    """Strip a leading 'AS'/'as' prefix from an ASN string. Unlike str.lstrip(), this
    removes only the literal two-character prefix, not any leading run of 'A'/'S' chars."""
    s = str(asn or "").strip().upper()
    return re.sub(r'^AS', '', s)


def haversine(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------------------
# Physical feasibility bounds, used by anycast/suspicious-hop detection and by the
# geolocation-learning confidence math (GeoTraceApp._speed_bound / _min_rtt_for_distance).
# Real fibre round-trip speed is ~100 km per ms of RTT, but real routes are appreciably
# longer than the great-circle distance between two points (submarine cables hug
# coastlines, terrestrial links follow rights-of-way, traffic backhauls through a distant
# exchange, etc). A detour factor from the geolocation literature (see e.g. Gueye et al.,
# "Constraint-Based Geolocation of Internet Hosts") is applied so a legitimately long,
# winding route isn't treated as physically impossible just because it isn't a straight
# line. GeoTraceApp._speed_bound() calibrates this further per-trace.
# ---------------------------------------------------------------------------------------
SPEED_KM_PER_MS = 100.0
DETOUR_FACTOR = 1.4

# Confidence weights for GeoTraceApp._eff()'s weighted-consensus city resolution — signals
# that agree with each other on a location have their weights summed, so two independently
# weaker signals that agree can outrank a single stronger one that disagrees with everything
# else, instead of a strict first-match priority chain.
SRC_WEIGHT = {
    "ixp": 5.0,
    "facility": 4.5,
    "host": 4.0,
    "learned": 3.2,
    "whois": 2.0,
    "near": 1.6,
    "rtt_override": 10.0,  # <--- Добавили (перебивает любые другие источники)
    "geo_agree": 2.4,
    "geo": 1.0,
    "peeringdb": 3.5,
}

# Ceiling used to normalize _eff()'s confidence score — deliberately NOT "however much
# weight happened to be present for this hop". Normalizing against only the present
# candidates means a hop with a single weak, uncorroborated signal (e.g. raw GeoIP alone,
# weight 1.0) trivially "wins" 100% of a 1.0-wide pool and displays as fully confident,
# which is backwards: no competing evidence isn't the same as strong evidence. Normalizing
# against a fixed ceiling — the weight of two strong independent signals agreeing — means a
# lone weak signal correctly reads as low confidence instead.
CONFIDENCE_CEILING = SRC_WEIGHT["ixp"] + SRC_WEIGHT["facility"]

# Router-hostname naming conventions typically place a location code directly next to an
# interface/role identifier (digits, or a short keyword like core/edge/gw/...), e.g.
# "ae1-0.FRA-tr1.example.net" or "xe-0-0-0.core2.LED.example.com". Preferring a code found
# in that position over one found in an arbitrary label cuts down on coincidental matches of
# ordinary words against short (often 3-letter) airport-style city codes.
ROUTER_ROLE_WORDS = ("core", "edge", "gw", "rtr", "router", "ix", "peer", "px", "bb",
                     "backbone", "transit", "agg")


def ptr_city_code(ip: str) -> tuple | None:
    try:
        host = socket.gethostbyaddr(ip)[0]
    except Exception:
        return None
    if not host:
        return None
    labels = re.split(r'[.\-]', host)
    hits = []
    for i, raw in enumerate(labels):
        tok = re.sub(r'[^a-zA-Z]', '', raw).lower()
        if len(tok) >= 3 and tok in CITY_DB:
            neighbours = " ".join(labels[max(0, i - 1):i + 2]).lower()
            has_digit = any(ch.isdigit() for ch in raw) or any(
                any(ch.isdigit() for ch in labels[j]) for j in (i - 1, i + 1) if 0 <= j < len(labels))
            has_role_word = any(w in neighbours for w in ROUTER_ROLE_WORDS)
            hits.append((tok, has_digit or has_role_word))
    if not hits:
        return None
    # prefer a hit sitting in a router-naming position; if nothing sits in that position,
    # only accept a lone, unambiguous match rather than guessing between several
    for tok, contextual in hits:
        if contextual:
            return tok, host
    if len(hits) == 1:
        return hits[0][0], host
    return None


def ripestat_city_code(ip: str) -> tuple | None:
    try:
        resp = session.get(f"https://stat.ripe.net/data/whois/data?resource={ip}",
                           timeout=CONFIG["timeout"]).json()
    except Exception:
        return None
    texts = []
    try:
        for rec in resp.get("data", {}).get("records", []):
            for field in rec:
                if (field.get("key") or "").lower() in ("netname", "descr", "remarks"):
                    texts.append(field.get("value") or "")
    except Exception:
        return None
    blob = " ".join(texts)
    for tok in re.split(r'[^a-zA-Z]+', blob):
        tok = tok.lower().rstrip('0123456789')
        if len(tok) >= 3 and tok in CITY_DB:
            return tok, blob
    low = blob.lower()
    for code, (ru, en, *_r) in CITY_DB.items():
        if ru.lower() in low or en.lower() in low:
            return code, blob
    return None


ANYCAST_NETS = {
    "13335": "cloudflare", "cloudflare": "cloudflare",
    "20940": "akamai", "akamai": "akamai",
    "54113": "fastly", "fastly": "fastly",
    "16509": "amazon", "amazon": "amazon", "cloudfront": "amazon",
    "15169": "google", "google": "google",
    "8075": "microsoft", "microsoft": "microsoft", "azure": "microsoft",
    "15133": "edgecast", "edgecast": "edgecast",
    "22822": "limelight", "limelight": "limelight",
}


def is_anycast(asn: str, org: str) -> bool:
    asn_clean = strip_as_prefix(asn)
    org_lower = str(org or "").lower()
    for key in ANYCAST_NETS:
        if key.isdigit() and asn_clean == key:
            return True
        if not key.isdigit() and key in org_lower:
            return True
    return False


LANGS = {
    "ru": {
        "title": "GeoTrace MAP", "addr": "Адрес сайта:",
        "start": "Запустить", "stop": "Стоп", "ready": "Готово",
        "tracing": "Трассировка...", "tracing_hops": "Трассировка... прыжков: {}",
        "aborted": "Прервано", "export": "Экспорт ▾",
        "cut": "Вырезать", "copy": "Копировать", "paste": "Вставить",
        "select_all": "Выделить всё",
        "exp_report": "📋 Копировать отчёт", "exp_csv": "Сохранить CSV…",
        "exp_json": "Сохранить JSON…", "exp_html": "Сохранить HTML (автономный)…",
        "done_title": "Готово", "done_msg": "Трассировка завершена!",
        "err_title": "Ошибка", "util_fail": "Не удалось запустить утилиту: {}",
        "log_geo": "[+] Определение вашей геопозиции (Прыжок 0)...",
        "log_noip": "[!] Не удалось определить внешний IP.",
        "you_here": "Вы здесь ({})", "ping_no": "нет ответа",
        "ping_tcp": "📡 ICMP блокирован · TCP {ms} мс · транзит живой",
        "ping_ok": "{mn}/{avg}/{mx} мс, потери {loss}%",
        "ready_ping": "Готово · пинг: {}",
        "report_title": "🌍 Маршрут до: {}", "report_ping": "📶 Пинг: {}",
        "report_copied": "Отчёт скопирован в буфер обмена",
        "html_saved": "Автономный HTML сохранён", "ms": "мс",
        "m_recovered": "🔧 узел восстановлен TCP-пробой (ICMP был заблокирован)",
        "m_target": "🎯 цель: нет ответа на traceroute (ICMP фильтруется)",
        "m_pin": "Закрепить — тултип можно таскать за шапку",
        "m_unpin": "Открепить и закрыть",
        "m_annot": "➜ направление движения: от вас к цели",
        "m_footer": "📡 клик по строке — непрерывный пинг",
        "m_seam": "⚡ стык сетей", "m_copied": "✔ Скопировано!",
        "m_starting": "запуск…", "m_waiting": "ожидание…",
        "m_nolink": "нет связи с приложением", "m_stop": "Стоп",
        "m_again": "Пинговать снова", "m_copyout": "Копировать вывод",
        "m_close": "Закрыть", "m_title": "Маршрут до: {}",
        "m_zilla_on": "🦖 ГОДЗИЛЛА ПРОБУДИЛСЯ!", "m_zilla_off": "🦖 Годзилла ушёл спать",
        "m_zilla_live": "Пинг доступен только в live-режиме",
        "m_waitreplies": "ожидание ответов…",
        "m_stats": "ответов: {n} · мин/ср/макс: {mn}/{avg}/{mx} мс · потери {loss}%",
        "m_stats0": "ответов: 0 · потери {loss}%",
        "m_src_geo": "🛰 GeoIP", "m_src_host": "📇 hostname",
        "m_src_learned": "🧠 обучено", "m_src_whois": "📜 whois",
        "m_src_near": "📍 рядом",
        "m_src_ixp": "⚡ IXP", "m_role_transit": "🛣️ транзит", "m_role_edge": "🏠 край сети",
        "m_src_facility": "🏢 дата-центр",
        "m_src_peeringdb": "🏢 HQ провайдера",
        "m_src_rtt": "🧲 рядом по RTT",
        "m_sus": "⚠ геолокация противоречит задержке",
        "m_anycast": "🌐 anycast CDN: вы на ближайшем edge-узле, GeoIP не отражает реальную точку",
        "conf_intro": "Уверенность: сколько независимых источников подтверждают эту локацию.",
        "conf_you": "Это ваш узел — локация известна, а не выведена.",
        "conf_capped": "Снижено: задержка противоречит этой геолокации.",
        "conf_boosted": "Только GeoIP, но задержка не противоречит соседним узлам.",
        "conf_strong": "Подтверждено именем хоста или данными реестра, не только GeoIP.",
        "conf_weak": "Только GeoIP, других подтверждений нет.",
        "learn_title": "🧠 Обучение геолокации",
        "learn_desc": "Программа запоминает города узлов, подтверждённые по hostname (PTR), и в дальнейшем использует их вместо GeoIP. База локальна; устаревшие и конфликтные записи отбрасываются; anycast не обучается.",
        "learn_off": "Выключено",
        "learn_semi": "Полуавто — предлагать сохранение (рекомендуется)",
        "learn_auto": "Авто — сохранять само (после 2+ наблюдений в разные дни)",
        "learn_stat": "записей: {} · доверенных: {}",
        "learn_ptr": "PTR-запросов: {} · совпадений с кодами городов: {}",
        "learn_clear": "Очистить базу",
        "learn_head": "📇 {} → {}",
        "learn_question": "Сохранить как подтверждённый город узла?",
        "learn_save": "Сохранить", "learn_skip": "Пропустить",
        "learn_ev_ptr": "PTR: {}", "learn_ev_hop": "Прыжок {} · {}",
        "learn_ev_geo": "GeoIP: {}", "learn_ev_agree": "✓ GeoIP согласен с hostname",
        "learn_ev_diff": "GeoIP говорит {} — для роутеров это часто «адрес по документам»",
        "learn_ev_ok": "✓ задержка согласуется с расстоянием до {} (≈{} км)",
        "learn_ev_bad": "⚠ задержка {} мс слишком мала для {} км до {} — вероятно, ошибка",
        "hist_empty": "история пуста",
        "report_skipped": "⊘ {} узел(ов) пропущено (приватные/таймауты)",
        "about_title": "О программе",
        "about_coding": "shitty vibe-coding with \n«Qwen 3.8-Max»\n «Claude»",
    },
    "en": {
        "title": "GeoTrace MAP", "addr": "Target address:",
        "start": "Start", "stop": "Stop", "ready": "Ready",
        "tracing": "Tracing...", "tracing_hops": "Tracing... hops: {}",
        "aborted": "Aborted", "export": "Export ▾",
        "cut": "Cut", "copy": "Copy", "paste": "Paste", "select_all": "Select all",
        "exp_report": "📋 Copy report", "exp_csv": "Save CSV…",
        "exp_json": "Save JSON…", "exp_html": "Save standalone HTML…",
        "done_title": "Done", "done_msg": "Trace complete!",
        "err_title": "Error", "util_fail": "Failed to start utility: {}",
        "log_geo": "[+] Detecting your location (Hop 0)...",
        "log_noip": "[!] Could not determine external IP.",
        "you_here": "You are here ({})", "ping_no": "no response",
        "ping_tcp": "📡 ICMP blocked · TCP {ms} ms · transit alive",
        "ping_ok": "{mn}/{avg}/{mx} ms, {loss}% loss", "ready_ping": "Ready · ping: {}",
        "report_title": "🌍 Route to: {}", "report_ping": "📶 Ping: {}",
        "report_copied": "Report copied to clipboard",
        "html_saved": "Standalone HTML saved", "ms": "ms",
        "m_recovered": "🔧 hop recovered via TCP probe (ICMP was blocked)",
        "m_target": "🎯 target: no traceroute response (ICMP filtered)",
        "m_pin": "Pin — tooltip becomes draggable by its header",
        "m_unpin": "Unpin and close",
        "m_annot": "➜ direction of travel: from you to the target",
        "m_footer": "📡 click a row to run a continuous ping",
        "m_seam": "⚡ peering point", "m_copied": "✔ Copied!",
        "m_starting": "starting…", "m_waiting": "waiting…",
        "m_nolink": "no connection to the app", "m_stop": "Stop",
        "m_again": "Ping again", "m_copyout": "Copy output", "m_close": "Close",
        "m_title": "Route to: {}",
        "m_zilla_on": "🦖 GODZILLA AWAKENED!", "m_zilla_off": "🦖 Godzilla went to sleep",
        "m_zilla_live": "Ping is available in live mode only",
        "m_waitreplies": "waiting for replies…",
        "m_stats": "replies: {n} · min/avg/max: {mn}/{avg}/{mx} ms · loss {loss}%",
        "m_stats0": "replies: 0 · loss {loss}%",
        "m_src_geo": "🛰 GeoIP", "m_src_host": "📇 hostname",
        "m_src_learned": "🧠 learned", "m_src_whois": "📜 whois",
        "m_src_near": "📍 nearby",
        "m_src_ixp": "⚡ IXP", "m_role_transit": "🛣️ transit", "m_role_edge": "🏠 edge",
        "m_src_facility": "🏢 datacenter",
        "m_src_peeringdb": "🏢 provider HQ",
        "m_src_rtt": "🧲 nearby by RTT",
        "m_sus": "⚠ geolocation contradicts latency",
        "m_anycast": "🌐 anycast CDN: you're on the nearest edge node, GeoIP doesn't reflect the actual location",
        "conf_intro": "Confidence: how much independent evidence backs this location.",
        "conf_you": "This is your own node — known, not inferred.",
        "conf_capped": "Lowered: latency contradicts this geolocation.",
        "conf_boosted": "GeoIP only, but latency doesn't contradict nearby hops.",
        "conf_strong": "Confirmed by hostname or registry data, not just GeoIP.",
        "conf_weak": "GeoIP only — nothing else confirms it.",
        "learn_title": "🧠 Geolocation learning",
        "learn_desc": "The app remembers node cities confirmed via hostname (PTR) and uses them instead of GeoIP. Local DB; stale/conflicting entries discarded; anycast never learned.",
        "learn_off": "Off", "learn_semi": "Semi-auto — ask before saving (recommended)",
        "learn_auto": "Auto — save by itself (after 2+ observations on different days)",
        "learn_stat": "entries: {} · trusted: {}",
        "learn_ptr": "PTR lookups: {} · city-code matches: {}",
        "learn_clear": "Clear database",
        "learn_head": "📇 {} → {}",
        "learn_question": "Save as the confirmed node city?",
        "learn_save": "Save", "learn_skip": "Skip",
        "learn_ev_ptr": "PTR: {}", "learn_ev_hop": "Hop {} · {}",
        "learn_ev_geo": "GeoIP: {}", "learn_ev_agree": "✓ GeoIP agrees with the hostname",
        "learn_ev_diff": "GeoIP says {} — for routers that's often the paper address",
        "learn_ev_ok": "✓ latency is consistent with the distance to {} (≈{} km)",
        "learn_ev_bad": "⚠ latency {} ms is too small for {} km to {} — likely wrong",
        "hist_empty": "history is empty",
        "report_skipped": "⊘ {} node(s) skipped (private/timeouts)",
        "about_title": "About",
        "about_coding": "shitty vibe-coding with \n«Qwen3.8-Max»\n «Claude»",
    },
}

def load_settings() -> dict:
    try:
        with open(CONFIG["settings_file"], "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(data: dict) -> None:
    try:
        with open(CONFIG["settings_file"], "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass


session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"})


@dataclass
class GeoPoint:
    hop: int
    ip: str
    city: str
    country: str
    lat: float
    lon: float
    ms: float | None = None
    ms_min: float | None = None
    ms_bound: bool = False   # True if the traceroute reading was an upper bound ("<1 ms"),
                              # not a tight measurement — see rtt_pattern parsing below
    asn: str = ""
    org: str = ""
    src: str = "geo"
    hcode: str = ""
    wcode: str = ""
    anycast: bool = False
    ixp: dict | None = None
    role: str = ""
    geo_agree: bool = False  # True if both independent GeoIP providers agreed
    recovered: bool = False   # ← добавить: хоп восстановлен TCP-пробой
    target: bool = False      # ← добавить: синтетический хоп цели
    hostname: str = ""


class GeoLearner:
    TRUST_THRESHOLD = 3.0  # accumulated confidence needed before a code is trusted

    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        self.data = {}
        self.load()

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            self.data = raw if isinstance(raw, dict) else {}
        except Exception:
            self.data = {}
        self._prune()

    def _prune(self):
        today = datetime.date.today()
        cut_c = today - datetime.timedelta(days=30)
        cut_t = today - datetime.timedelta(days=180)
        for ip in list(self.data):
            codes = self.data[ip].get("codes", {})
            for code in list(codes):
                st = codes[code]
                try:
                    last = datetime.date.fromisoformat(st["last"])
                except Exception:
                    del codes[code]
                    continue
                if last < (cut_t if st.get("trusted") else cut_c):
                    del codes[code]
                    continue
                # gently decay confidence on stale, not-yet-trusted candidates so an old,
                # never-corroborated guess doesn't linger indefinitely just under the bar
                if not st.get("trusted") and st.get("conf", 0.0) > 0:
                    idle = (today - last).days
                    if idle > 14:
                        st["conf"] = round(st.get("conf", 0.0) * (0.9 ** (idle // 14)), 3)
            if not codes:
                del self.data[ip]
        if len(self.data) > 2000:
            def key(i):
                e = self.data[i]
                return (any(s.get("trusted") for s in e["codes"].values()),
                        max(s["last"] for s in e["codes"].values()))
            for i in sorted(self.data, key=key)[:len(self.data) - 2000]:
                del self.data[i]

    def save(self):
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False)
            os.replace(tmp, self.path)
        except Exception:
            pass

    def trusted_code(self, ip):
        with self.lock:
            e = self.data.get(ip)
            if not e:
                return None
            best = None
            for code, st in e.get("codes", {}).items():
                if st.get("trusted"):
                    k = (st.get("n", 0), len(st.get("days", [])))
                    if best is None or k > best[1]:
                        best = (code, k)
            return best[0] if best else None

    def observe(self, ip, code, host, feasible=True, corroborated=False):
        """Record a PTR-derived city-code observation for `ip`.

        feasible: whether the RTT that produced this observation was physically consistent
            with `code`'s location (see GeoTraceApp._learn_evidence / _min_rtt_for_distance).
            Infeasible observations are discarded outright — they never accrue confidence,
            so a coincidental hostname-token match with an impossible RTT can't get trusted
            just by repeating a few times.
        corroborated: whether an independent signal (GeoIP provider agreement) already
            points at roughly the same place — corroborated observations count for more.
        """
        if not feasible:
            return False
        today = datetime.date.today().isoformat()
        with self.lock:
            e = self.data.setdefault(ip, {"codes": {}})
            st = e["codes"].setdefault(code, {"n": 0, "days": [], "last": today, "host": host, "conf": 0.0})
            st["n"] += 1
            st["last"] = today
            st["host"] = host
            if today not in st["days"]:
                st["days"].append(today)
                st["conf"] = st.get("conf", 0.0) + (1.5 if corroborated else 1.0)
            if not st.get("trusted") and st["conf"] >= self.TRUST_THRESHOLD and len(st["days"]) >= 2:
                conflict = any(c != code and s.get("conf", 0.0) >= self.TRUST_THRESHOLD * 0.6
                               for c, s in e["codes"].items())
                if not conflict:
                    st["trusted"] = True
            self.save()
            return bool(st.get("trusted"))

    def confirm(self, ip, code, host):
        today = datetime.date.today().isoformat()
        with self.lock:
            e = self.data.setdefault(ip, {"codes": {}})
            st = e["codes"].setdefault(code, {"n": 0, "days": [], "last": today, "host": host, "conf": 0.0})
            st["n"] = max(st.get("n", 0), 1)
            st["last"] = today
            st["host"] = host
            if today not in st["days"]:
                st["days"].append(today)
            st["conf"] = max(st.get("conf", 0.0), self.TRUST_THRESHOLD)  # explicit human confirmation is authoritative
            st["trusted"] = True
            self.save()

    def demote(self, ip):
        with self.lock:
            e = self.data.get(ip)
            if not e:
                return
            for st in e.get("codes", {}).values():
                st.pop("trusted", None)
            self.save()

    def clear(self):
        with self.lock:
            self.data = {}
            self.save()

    def counts(self):
        with self.lock:
            total = len(self.data)
            trusted = sum(1 for e in self.data.values()
                          if any(s.get("trusted") for s in e.get("codes", {}).values()))
            return total, trusted


class BgpInfo:
    """IXP-детект (PeeringDB) и роль AS (RIPEstat). Официальные API, кэш, без блокировок UI."""
    
    # PeeringDB WAF блокирует браузерные User-Agent. 
    # Указываем имя приложения и email, чтобы пройти WAF.
    PDB_HEADERS = {"User-Agent": "GeoTrace/1.0 (geotracemap@protonmail.com)"}

    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        self.nets = []
        self.roles = {}
        self.ready = False
        self._load_cache()
        self.asn_geo = {}  
        self.fac_db = {}        
        self.asn_fac_cache = {}

    def fetch_asn_geo(self, asn):
        asn_clean = strip_as_prefix(asn)
        if not asn_clean.isdigit():
            return None
        if asn_clean in self.asn_geo:            # работает и для отрицательного кэша: неудачи хранятся как None
            return self.asn_geo[asn_clean]

        with self.lock:
        # Double-check
            if asn_clean in self.asn_geo:
                return self.asn_geo[asn_clean]
        try:
            net_resp = session.get(f"https://www.peeringdb.com/api/net?asn={asn_clean}",
                                   timeout=CONFIG["timeout"], headers=self.PDB_HEADERS).json()
            if not net_resp.get("data"):
                self.asn_geo[asn_clean] = None   # ASN нет в PeeringDB — повторять бессмысленно
                return None
            net = net_resp["data"][0]
            result = {
                "name": (net.get("name") or "").lower(),
                "aka": (net.get("aka") or "").lower(),
                "hq": None
            }
            if net.get("org_id"):
                org_resp = session.get(f"https://www.peeringdb.com/api/org?id={net['org_id']}",
                                       timeout=CONFIG["timeout"], headers=self.PDB_HEADERS).json()
                if org_resp.get("data"):
                    org = org_resp["data"][0]
                    if org.get("latitude") and org.get("longitude"):
                        result["hq"] = {
                            "city": org.get("city", "Unknown"),
                            "country": org.get("country", "Unknown"),
                            "lat": float(org["latitude"]),
                            "lon": float(org["longitude"])
                    }
            self.asn_geo[asn_clean] = result
            return result
        except Exception:
            self.asn_geo[asn_clean] = None
            return None

    def _load_cache(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if time.time() - raw.get("ts", 0) < 86400:
                self._build(raw.get("entries", []))
                # Загружаем сохранённые дата-центры (если их нет в старом кэше, берём пустой словарь)
                self.fac_db = raw.get("fac_db", {})
                self.ready = True
        except Exception:
            pass

    def _build(self, entries):
        nets = []
        for e in entries:
            try:
                net = ipaddress.ip_network(e["net"], strict=False)
                if net.version == 4:
                    nets.append((net, e))
            except Exception:
                continue
        nets.sort(key=lambda x: x[0].prefixlen, reverse=True)  # longest-prefix match
        self.nets = nets

    def _ensure_fac_db(self):
        """Подгружает базу дата-центров (/api/fac), если она ещё пуста.
        В файловый кэш её не пишем сознательно — ответ слишком большой."""
        if self.fac_db:
            return
        with self.lock:
            if self.fac_db:
                return
        try:
            fac_resp = session.get("https://www.peeringdb.com/api/fac",
                                   timeout=20, headers=self.PDB_HEADERS).json()
            self.fac_db = {f["id"]: f for f in fac_resp.get("data", [])}
        except Exception:
            pass

    def refresh(self):
        """Фоновое обновление базы IXP (раз в сутки). Ошибка = фича выключена."""
        if self.ready:
            self._ensure_fac_db()   # сети взяты из кэша, но базы ДЦ там нет — подтягиваем
            return
        try:
            ix = session.get("https://www.peeringdb.com/api/ix", timeout=10, headers=self.PDB_HEADERS).json()["data"]
            meta = {i["id"]: i for i in ix}
            pfx = session.get("https://www.peeringdb.com/api/ixpfx", timeout=10, headers=self.PDB_HEADERS).json()["data"]
            entries = []
            for p in pfx:
                m = meta.get(p["ix_id"])
                if not m or p.get("protocol") != 4:
                    continue
                lat, lon = m.get("latitude"), m.get("longitude")
                if lat in (None, "") or lon in (None, ""):
                    continue
                entries.append({"net": p["prefix"], "name": m.get("name", ""),
                                "city": m.get("city", ""), "country": m.get("country", ""),
                                "lat": float(lat), "lon": float(lon)})
            self._ensure_fac_db()   # заменяет старый инлайн-блок fac_resp = session.get(...api/fac...)
            with self.lock:
                self._build(entries)
                self.ready = True
            try:
                with open(self.path, "w", encoding="utf-8") as f:
                    json.dump({"ts": time.time(), "entries": entries}, f)
            except Exception:
                pass
        except Exception:
            pass

    def fetch_facilities(self, asn):
        """Возвращает список дата-центров, в которых присутствует данный ASN."""
        asn_clean = strip_as_prefix(asn)
        if not asn_clean.isdigit():
            return []
        if asn_clean in self.asn_fac_cache:
            return self.asn_fac_cache[asn_clean]
        if not self.fac_db:
            return []   # база ДЦ ещё не загрузилась — не кэшируем пустоту, повторим позже
        try:
            net_resp = session.get(f"https://www.peeringdb.com/api/net?asn={asn_clean}", timeout=CONFIG["timeout"], headers=self.PDB_HEADERS).json()
            if not net_resp.get("data"):
                self.asn_fac_cache[asn_clean] = []
                return []
            net_id = net_resp["data"][0]["id"]
            netfac_resp = session.get(f"https://www.peeringdb.com/api/netfac?net_id={net_id}", timeout=CONFIG["timeout"], headers=self.PDB_HEADERS).json()
            fac_ids = [f["fac_id"] for f in netfac_resp.get("data", [])]
            facilities = []
            for fid in fac_ids:
                fac = self.fac_db.get(fid)
                if fac and fac.get("latitude") and fac.get("longitude"):
                    facilities.append({
                        "name": fac.get("name", ""),
                        "city": fac.get("city", "Unknown"),
                        "country": fac.get("country", "Unknown"),
                        "lat": float(fac["latitude"]),
                        "lon": float(fac["longitude"])
                    })
            self.asn_fac_cache[asn_clean] = facilities
            return facilities
        except Exception:
            self.asn_fac_cache[asn_clean] = []
            return []

    def lookup_ip(self, ip):
        if not self.ready:
            return None
        try:
            a = ipaddress.ip_address(ip)
        except Exception:
            return None
        if a.version != 4:
            return None
        with self.lock:
            for net, e in self.nets:
                if a in net:
                    return e
        return None

    def fetch_role(self, asn):
        asn_clean = strip_as_prefix(asn)
        if not asn_clean.isdigit() or asn_clean in self.roles:
            return
        try:
            resp = session.get(
                f"https://stat.ripe.net/data/asn-neighbours/data?resource=AS{asn_clean}",
                timeout=CONFIG["timeout"]).json()
            counts = resp.get("data", {}).get("neighbour_counts", {})
            down = int(counts.get("downstream", 0) or 0)
            self.roles[asn_clean] = "transit" if down >= 100 else "edge"
        except Exception:
            self.roles[asn_clean] = ""

    def role_of(self, asn):
        return self.roles.get(strip_as_prefix(asn), "")


def clean_target(url_input: str) -> str:
    try:
        url = str(url_input).strip()
        url = re.sub(r'^https?://', '', url, flags=re.IGNORECASE)
        url = re.sub(r'^.*?@', '', url)
        url = re.split(r'[:/?#]', url)[0]
        return url.translate(str.maketrans('', '', "[]'\""))
    except Exception:
        return "google.com"


def get_public_ip() -> str | None:
    services = [
        ("https://api.ipify.org?format=json", lambda r: r.json().get("ip")),
        ("https://ifconfig.me/ip", lambda r: r.text.strip())]
    for url, parser in services:
        try:
            return parser(session.get(url, timeout=CONFIG["timeout"]))
        except Exception:
            continue
    return None


def _geo_ipwhois(ip):
    try:
        resp = session.get(f"https://ipwho.is/{ip}", timeout=CONFIG["timeout"]).json()
    except Exception:
        return None
    if not (resp.get("success") and resp.get("latitude") is not None and resp.get("longitude") is not None):
        return None
    conn = resp.get("connection") or {}
    return {"city": resp.get("city", "Unknown"), "country": resp.get("country", "Unknown"),
            "lat": float(resp["latitude"]), "lon": float(resp["longitude"]),
            "asn": conn.get("asn", "") or "", "org": conn.get("org") or conn.get("isp") or ""}


def _geo_ipapi(ip):
    try:
        resp = session.get(f"http://ip-api.com/json/{ip}", timeout=CONFIG["timeout"]).json()
    except Exception:
        return None
    if resp.get("status") != "success":
        return None
    asn, _, org = resp.get("as", "").partition(" ")
    return {"city": resp.get("city", "Unknown"), "country": resp.get("country", "Unknown"),
            "lat": float(resp.get("lat", 0.0)), "lon": float(resp.get("lon", 0.0)),
            "asn": asn, "org": resp.get("org") or org}


geo_cache = {}
ptr_cache = {}
whois_cache = {}
cache_lock = threading.Lock()   # guards the check-then-act pattern on the caches above,
                                  # which are hit concurrently from several worker pools
_GEO_FAILED = object()          # sentinel: "already tried, both providers failed"


def _geo_dual(ip):
    """Query both independent GeoIP providers (instead of treating the second as a mere
    fallback) so agreement between them can be used as a confidence signal downstream — see
    SRC_WEIGHT["geo_agree"] in GeoTraceApp._eff and GeoLearner's "corroborated" observations.
    This costs one extra HTTP request per not-yet-cached hop versus the old fallback-only
    behaviour; ip-api.com's free tier is rate-limited, so very large/rapid traces could hit
    that limit slightly sooner than before."""
    a = _geo_ipwhois(ip)
    b = _geo_ipapi(ip)
    primary = a or b
    agree = False
    if a and b:
        if a["city"].strip().lower() == b["city"].strip().lower() and a["city"] not in ("", "Unknown"):
            agree = True
        else:
            try:
                agree = haversine(a["lat"], a["lon"], b["lat"], b["lon"]) < 50
            except Exception:
                agree = False
    return primary, agree


def get_ip_geo(ip):
    with cache_lock:
        cached = geo_cache.get(ip, "missing")
    if cached == "missing":
        data, agree = _geo_dual(ip)
        if data is None:
            with cache_lock:
                geo_cache[ip] = _GEO_FAILED   # remember the failure — don't hit both
            return None                        # providers again for every re-reference
        cached = dict(data, agree=agree)
        with cache_lock:
            geo_cache[ip] = cached
    elif cached is _GEO_FAILED:
        return None
    return GeoPoint(hop=0, ip=ip, city=cached["city"], country=cached["country"],
                    lat=cached["lat"], lon=cached["lon"], asn=cached["asn"], org=cached["org"],
                    geo_agree=cached.get("agree", False))


class PingManager:
    def __init__(self, lang="ru"):
        self.pings = {}
        self.lock = threading.Lock()
        self.lang = lang

    @staticmethod
    def _hidden_kwargs():
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        return {"startupinfo": si,
                "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}

    def start(self, ip):
        with self.lock:
            old = self.pings.get(ip)
            if old and old["running"]:
                return
        cmd = ["ping", "-t", ip]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, encoding='cp866',
                                    errors='ignore', **self._hidden_kwargs())
        except Exception:
            return
        entry = {"proc": proc, "lines": [], "running": True, "lock": threading.Lock()}
        with self.lock:
            self.pings[ip] = entry
        threading.Thread(target=self._reader, args=(ip,), daemon=True).start()

    def _reader(self, ip):
        e = self.pings.get(ip)
        if not e:
            return
        for line in iter(e["proc"].stdout.readline, ""):
            t = line.strip()
            if not t:
                continue
            with e["lock"]:
                e["lines"].append(t)
                if len(e["lines"]) > 300:
                    del e["lines"][:100]
        e["running"] = False

    def stop(self, ip):
        with self.lock:
            e = self.pings.get(ip)
        if e and e["running"]:
            e["running"] = False
            try:
                e["proc"].kill()
                e["proc"].wait(timeout=2)
            except Exception:
                pass

    def stop_all(self):
        with self.lock:
            ips = list(self.pings.keys())
        for ip in ips:
            self.stop(ip)

    def _stats(self, e):
        L = LANGS[self.lang]
        with e["lock"]:
            lines = list(e["lines"])
        rtts, lost = [], 0
        for ln in lines:
            m = re.search(r'(?:time|время)\s*[<=]\s*(\d+(?:[.,]\d+)?)', ln, re.IGNORECASE)
            if m:
                rtts.append(float(m.group(1).replace(",", ".")))
            elif any(x in ln.lower() for x in ("timed out", "превышен", "unreachable", "недоступен")):
                lost += 1
        if not rtts and not lost:
            return L["m_waitreplies"]
        req = len(rtts) + lost
        loss = round(lost / req * 100) if req else 0
        if rtts:
            return L["m_stats"].format(n=len(rtts), mn=int(round(min(rtts))),
                                       avg=int(round(sum(rtts) / len(rtts))),
                                       mx=int(round(max(rtts))), loss=loss)
        return L["m_stats0"].format(loss=loss)

    def snapshot(self):
        out = {}
        with self.lock:
            items = list(self.pings.items())
        for ip, e in items:
            with e["lock"]:
                lines = list(e["lines"][-100:])
            out[ip] = {"lines": lines, "running": e["running"], "stats": self._stats(e)}
        return out

    def live_min_rtts(self):
        """Minimum RTT (ms) observed so far for every IP with an active/recent continuous-
        ping history. A running ping session accumulates dozens of samples and its min is a
        much tighter, more reliable floor on true propagation delay than any single
        traceroute probe — GeoTraceApp._rtt() folds this in wherever the user has actually
        pinged a node, feeding real measured data back into the feasibility/audit math
        instead of relying solely on the original trace's one-shot reading."""
        out = {}
        with self.lock:
            items = list(self.pings.items())
        for ip, e in items:
            with e["lock"]:
                lines = list(e["lines"])
            best = None
            for ln in lines:
                m = re.search(r'(?:time|время)\s*[<=]\s*(\d+(?:[.,]\d+)?)', ln, re.IGNORECASE)
                if m:
                    v = float(m.group(1).replace(",", "."))
                    if best is None or v < best:
                        best = v
            if best is not None:
                out[ip] = best
        return out


def _start_api_server(manager, token):
    # Local control API for the map page (start/stop live pings). Two layers of defense
    # against other software/webpages on the same machine driving it without the user's
    # map page being involved:
    #   1. CORS is scoped to the "null" origin that browsers send for file:// pages (the
    #      map is opened as a local .html file) instead of "*". A page loaded from an
    #      http(s) origin gets no Access-Control-Allow-Origin match, so its preflight for
    #      state-changing POSTs fails and the browser blocks the request from being sent,
    #      and any GET response it did receive can't be read cross-origin either.
    #   2. State-changing POST actions (start/stop) must include the per-run secret token
    #      that's embedded only in the rendered map HTML, so even a same-origin-looking
    #      blind request can't drive the API without having read that file.
    def _allowed_origin(origin):
        # file:// pages send Origin: null; some browsers omit Origin for local files.
        return origin is None or origin == "null"

    class Handler(BaseHTTPRequestHandler):
        def _cors(self, code=200):
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            if _allowed_origin(self.headers.get("Origin")):
                self.send_header("Access-Control-Allow-Origin", "null")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()

        def do_GET(self):
            self._cors()
            if self.path.startswith("/api"):
                self.wfile.write(json.dumps({"pings": manager.snapshot()}).encode("utf-8"))
            else:
                self.wfile.write(b'{"ok":true}')

        def do_POST(self):
            if self.path.startswith("/api") and _allowed_origin(self.headers.get("Origin")):
                length = int(self.headers.get("Content-Length") or 0)
                try:
                    req = json.loads(self.rfile.read(length) or b"{}")
                except Exception:
                    req = {}
                if req.get("token") == token:
                    action = req.get("action")
                    ip = str(req.get("ip", ""))
                    if action == "start" and re.fullmatch(r"[\w.\-:]+", ip):
                        manager.start(ip)
                    elif action == "stop":
                        manager.stop(ip)
            self._cors()
            self.wfile.write(b'{"ok":true}')

        def do_OPTIONS(self):
            self.send_response(204)
            if _allowed_origin(self.headers.get("Origin")):
                self.send_header("Access-Control-Allow-Origin", "null")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "*")
            self.end_headers()

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return port, server


def trace_worker(target, callback, stop_event, app):
    L = LANGS[app.lang]
    callback("log", L["log_geo"])
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE

    def _spawn(cmd):
        return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding='cp866',
                                startupinfo=startupinfo, errors='ignore')

    cmd = ["tracert", "-d", "-h", "30", target]
    try:
        process = _spawn(cmd)
        # Marshal onto the UI thread like every other cross-thread update in this
        # module — app.process must never be written directly from a worker thread.
        callback("process", process)
    except Exception as e:
        callback("error", L["util_fail"].format(e))
        return
    try:
        target_ip = socket.gethostbyname(target)
    except Exception:
        target_ip = None
    seen_target = False


    # собственный IP определяем, пока процесс уже «греется»
    if my_ip := get_public_ip():
        if geo := get_ip_geo(my_ip):
            geo.hop = 0
            geo.city = L["you_here"].format(geo.city)
            callback("hop", geo)
    else:
        callback("log", L["log_noip"])

    ip_pattern = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')
    rtt_pattern = re.compile(r'(<)?\s*(\d+(?:[.,]\d+)?)\s*(?:ms|мс)', re.IGNORECASE)
    executor = ThreadPoolExecutor(max_workers=4)
    ptr_executor = ThreadPoolExecutor(max_workers=6)
    whois_executor = ThreadPoolExecutor(max_workers=3)
    bgp_executor = ThreadPoolExecutor(max_workers=2)
    # Hand references to the UI thread so _on_close can shut them down (with
    # cancel_futures) instead of leaving pending network calls to block process exit.
    callback("executors", (executor, ptr_executor, whois_executor, bgp_executor))

    def submit_bgp(ip, asn):
        try:
            fut = bgp_executor.submit(_bgp_probe, ip, asn)
        except RuntimeError:
            return

        def on_done(f):
            if stop_event.is_set():
                return
            try:
                res = f.result()
            except Exception:
                res = None
            if res:
                callback("bgp", {"ip": ip, **res})
        fut.add_done_callback(on_done)

    def _bgp_probe(ip, asn):
        out = {}
        e = app.bgp.lookup_ip(ip)
        if e:
            out["ixp"] = e
        if asn:
            if not app.bgp.role_of(asn):
                app.bgp.fetch_role(asn)
            role = app.bgp.role_of(asn)
            if role:
                out["role"] = role
                app.bgp.fetch_asn_geo(asn)
                app.bgp.fetch_facilities(asn)
        return out

    def submit_geo(ip, hop, ms, ms_min, ms_bound=False, recovered=False):
        try:
            fut = executor.submit(get_ip_geo, ip)
        except RuntimeError:
            return

        def on_done(f):
            if stop_event.is_set():
                return
            try:
                g = f.result()
            except Exception:
                return
            if g:
                g.hop = hop
                g.ms = ms
                g.ms_min = ms_min
                g.ms_bound = ms_bound
                g.recovered = recovered
                g.anycast = is_anycast(g.asn, g.org)
                submit_bgp(ip, g.asn)
                callback("hop", g)
        fut.add_done_callback(on_done)

    def submit_whois(ip):
        with cache_lock:
            if ip in whois_cache:
                res = whois_cache[ip]
            else:
                whois_cache[ip] = None   # placeholder claims this IP so a concurrent
                res = "pending"           # hop for the same IP won't also submit it
        if res != "pending":
            if res:
                callback("whois", {"ip": ip, "code": res[0]})
            return
        try:
            fut = whois_executor.submit(ripestat_city_code, ip)
        except RuntimeError:
            return

        def on_done(f):
            if stop_event.is_set():
                return
            try:
                res = f.result()
            except Exception:
                res = None
            with cache_lock:
                whois_cache[ip] = res
            if res:
                callback("whois", {"ip": ip, "code": res[0]})
        fut.add_done_callback(on_done)

    def submit_ptr(ip):
        with cache_lock:
            if ip in ptr_cache:
                res = ptr_cache[ip]
            else:
                ptr_cache[ip] = None
                res = "pending"
        if res != "pending":
            _ptr_done(ip, res)
            return
        try:
            fut = ptr_executor.submit(ptr_city_code, ip)
        except RuntimeError:
            return

        def on_done(f):
            if stop_event.is_set():
                return
            try:
                res = f.result()
            except Exception:
                res = None
            with cache_lock:
                ptr_cache[ip] = res
            _ptr_done(ip, res)
        fut.add_done_callback(on_done)

    def _ptr_done(ip, res):
        callback("ptr_stat", 1 if res else 0)
        if res:
            code, host = res
            callback("fix", {"ip": ip, "code": code, "host": host})
        elif app.learner.trusted_code(ip) is None:
            submit_whois(ip)   # WHOIS — только если PTR молчит и нет доверия

    hop_index = 1
    total_lines = 0       # всего строк с hop'ами (глобальные + приватные + таймауты)
    timeout_lines = 0     # сколько из них — таймауты
    try:
        for line in iter(process.stdout.readline, ""):
            if stop_event.is_set():
                break
            cleaned = line.strip()
            if not cleaned:
                continue
            callback("log", cleaned)
            if any(x in cleaned.lower() for x in ("трассировка маршрута", "трассировка завершена",
                                                   "tracing route", "trace complete", "over")):
                continue
            # считаем «пропуски» (приватные + таймауты)
            has_timeout = any(x in cleaned for x in ("*", "Превышен", "timed out"))
            ips = ip_pattern.findall(cleaned)
            is_global = False
            if ips:
                ip = ips[-1].strip()
                try:
                    is_global = ipaddress.ip_address(ip).is_global
                except ValueError:
                    pass
                # 🎯 трассировка дошла до самой цели — синтетический хоп не понадобится
                if target_ip and ip == target_ip:
                    seen_target = True
            # hop-строка — если есть IP или таймаут
            if ips or has_timeout:
                total_lines += 1
                if has_timeout and not is_global:
                    timeout_lines += 1
            if ips:
                if not is_global:
                    continue
                rtts = []
                any_bound = False
                for m in rtt_pattern.finditer(cleaned):
                    v = float(m.group(2).replace(",", "."))
                    if m.group(1):
                        any_bound = True
                    rtts.append(v)
                avg_ms = round(sum(rtts) / len(rtts), 1) if rtts else None
                min_ms = round(min(rtts), 1) if rtts else None
                submit_geo(ip, hop_index, avg_ms, min_ms, any_bound)
                submit_ptr(ip)
                hop_index += 1
    except Exception:
        pass
    finally:
        if process.stdout:
            process.stdout.close()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()


    executor.shutdown(wait=True)
    ptr_executor.shutdown(wait=False)
    whois_executor.shutdown(wait=False)
    bgp_executor.shutdown(wait=False)
    # 🎯 Синтетический target-хоп: ICMP отфильтрован, tracert не дошёл до цели,
    # но её IP известен — показываем на карте как конец маршрута
    if target_ip and not seen_target and not stop_event.is_set():
        g = get_ip_geo(target_ip)
        if g:
            g.hop = hop_index
            g.target = True
            g.anycast = is_anycast(g.asn, g.org)
            pres = ptr_cache.get(target_ip) or ptr_city_code(target_ip)
            if pres:
                g.hcode = pres[0]
                ptr_cache[target_ip] = pres
            ixp = app.bgp.lookup_ip(target_ip)
            if ixp:
                g.ixp = ixp
            role = app.bgp.role_of(g.asn)
            if role:
                g.role = role
            callback("hop", g)
    callback("aborted" if stop_event.is_set() else "done",
             {"target": target, "global": hop_index - 1,
              "total": total_lines, "timeout": timeout_lines})

class GeoTraceApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("GeoTrace MAP")
        self.geometry("560x646")

        self.hops: list[GeoPoint] = []
        self._live_rtt = {}   # ip -> min RTT (ms) from an active continuous-ping session,
                                # refreshed each _audit_sus() pass — see PingManager.live_min_rtts
        self._eff_conf = {}   # (hop, ip) -> consensus confidence (0-1) from the last _eff() call,
                                # populated as a side effect so callers can display it
        self.map_opened = False
        self.process: subprocess.Popen | None = None
        self.stop_event = threading.Event()
        self.ping_summary = ""
        self.map_rev = 0
        self.data_rev = 0
        self.trace_stats = None
        self.hist_win = None
        self._hist_h = 0
        self._bg_executors = []   # ThreadPoolExecutors handed over by the current
                                    # trace_worker run, so _on_close can shut them down
        self.api_server = None

        prefs = load_settings()
        self.theme = prefs.get("theme", "light")
        if self.theme not in THEMES:
            self.theme = "light"
        self.lang = prefs.get("lang", "ru")
        if self.lang not in LANGS:
            self.lang = "ru"
        self.learn_mode = prefs.get("learn", "off")
        if self.learn_mode not in ("off", "semi", "auto"):
            self.learn_mode = "off"
        self.history = prefs.get("history", [])
        if not isinstance(self.history, list):
            self.history = []
        self.tracing = False
        self.ptr_attempts = 0
        self.ptr_matches = 0

        self.learner = GeoLearner(CONFIG["learn_file"])
        self.suggest_queue = []
        self.suggest_open = False

        self.bgp = BgpInfo(CONFIG["peeringdb_file"])
        threading.Thread(target=self.bgp.refresh, daemon=True).start()

        self.ping_manager = PingManager(lang=self.lang)
        self.api_port = 0
        self.api_token = secrets.token_urlsafe(24)
        try:
            self.api_port, self.api_server = _start_api_server(self.ping_manager, self.api_token)
        except Exception:
            pass

        self._setup_ui()
        self._apply_theme(self.theme, save=False)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------- i18n
    def tr(self, key, *args, **kw):
        s = LANGS[self.lang][key]
        return s.format(*args, **kw) if (args or kw) else s

    def _save_prefs(self):
        save_settings({"theme": self.theme, "lang": self.lang,
                       "learn": self.learn_mode, "history": self.history})

    def _apply_lang(self):
        self.title(self.tr("title"))
        self.addr_label.config(text=self.tr("addr"))
        self.lang_btn.config(text="EN" if self.lang == "ru" else "RU")
        self.btn.config(text=self.tr("stop") if self.tracing else self.tr("start"))
        self.export_btn.config(text=self.tr("export"))
        self.status.config(text=self.tr("tracing") if self.tracing else self.tr("ready"))
        self.entry_menu.entryconfig(0, label=self.tr("cut"))
        self.entry_menu.entryconfig(1, label=self.tr("copy"))
        self.entry_menu.entryconfig(2, label=self.tr("paste"))
        self.entry_menu.entryconfig(4, label=self.tr("select_all"))
        self.menu.entryconfig(0, label=self.tr("copy"))
        self.export_menu.entryconfig(0, label=self.tr("exp_report"))
        self.export_menu.entryconfig(2, label=self.tr("exp_csv"))
        self.export_menu.entryconfig(3, label=self.tr("exp_json"))
        self.export_menu.entryconfig(4, label=self.tr("exp_html"))

    def _toggle_lang(self):
        self.lang = "en" if self.lang == "ru" else "ru"
        self.ping_manager.lang = self.lang
        self._apply_lang()
        self._save_prefs()
        if self.map_opened:
            self.map_rev += 1
            with open(CONFIG["map_file"], "w", encoding="utf-8") as f:
                f.write(self._render_map_html(self.entry.get().strip()))
            if self.hops:
                self._update_map(final=self.process is None)

    # ------------------------------------------------------------- geo
    def _rtt(self, h):
        live = self._live_rtt.get(h.ip)
        base = h.ms_min if h.ms_min is not None else h.ms
        if live is None:
            return base
        return live if base is None else min(live, base)

    def _speed_bound(self):
        """Km of great-circle distance considered feasible per ms of RTT, calibrated for
        this trace. Starts from the fibre-speed default deflated by the assumed detour
        factor (a real route is longer than a straight line), then loosens to whatever this
        specific trace has already demonstrated between two confidently-located hops — so a
        network that happens to run unusually direct routes doesn't get false "sus"/anycast
        flags from an overly conservative global constant. Never exceeds the physical
        ceiling (undeflated fibre speed)."""
        best = SPEED_KM_PER_MS / DETOUR_FACTOR
        confident_srcs = ("host", "learned", "ixp")
        pts = []
        for h in self._sorted_hops():
            if h.ms_bound:
                continue  # an upper-bound reading ("<1 ms") isn't tight enough to calibrate from
            _, _, lat, lon, src = self._eff(h)
            r = self._rtt(h)
            if src in confident_srcs and r is not None:
                pts.append((lat, lon, r))
        for i in range(len(pts)):
            for j in range(i + 1, len(pts)):
                lat1, lon1, r1 = pts[i]
                lat2, lon2, r2 = pts[j]
                dr = abs(r1 - r2)
                if dr > 1:
                    dist = haversine(lat1, lon1, lat2, lon2)
                    if dist > 200:
                        best = max(best, dist / dr)
        return min(best, SPEED_KM_PER_MS)

    def _min_rtt_for_distance(self, dist_km, speed=None):
        speed = speed or self._speed_bound()
        return dist_km / speed if speed > 0 else float("inf")

    def _learn_evidence(self, hop, code):
        """Physical/GeoIP feasibility evidence for treating `code` as `hop`'s confirmed
        city. Returns (feasible, corroborated, dist_km): feasible is False when the observed
        RTT could not physically reach that far given the calibrated per-trace speed bound;
        corroborated is True when GeoIP (dual-provider agreement, or the raw fallback city/
        country) already points at roughly the same place."""
        user = next((h for h in self.hops if h.hop == 0), None)
        e = CITY_DB[code]
        lat, lon = e[2], e[3]
        dist = haversine(user.lat, user.lon, lat, lon) if user else None
        r = self._rtt(hop)
        feasible = True
        if dist is not None and r is not None:
            feasible = r >= self._min_rtt_for_distance(dist) * 0.5
        geo_city_l = (hop.city or "").strip().lower()
        corroborated = bool(hop.geo_agree) or geo_city_l in (e[0].lower(), e[1].lower())
        return feasible, corroborated, (dist or 0.0)

    def _eff(self, h):
        ru = self.lang == "ru"

        def city_of(code):
            e = CITY_DB[code]
            return (e[0] if ru else e[1]), (e[4] if ru else e[5]), e[2], e[3]

        candidates = []  # (weight, group_key, city, country, lat, lon, src)

        if h.hcode and h.hcode in CITY_DB:
            c, ct, la, lo = city_of(h.hcode)
            candidates.append((SRC_WEIGHT["host"], ("code", h.hcode), c, ct, la, lo, "host"))

        code = self.learner.trusted_code(h.ip)
        if code and code in CITY_DB:
            c, ct, la, lo = city_of(code)
            candidates.append((SRC_WEIGHT["learned"], ("code", code), c, ct, la, lo, "learned"))

        if h.ixp:
            candidates.append((SRC_WEIGHT["ixp"], ("ixp", h.ixp.get("name")),
                               h.ixp["city"], h.ixp["country"], h.ixp["lat"], h.ixp["lon"], "ixp"))

        if h.wcode and h.wcode in CITY_DB:
            c, ct, la, lo = city_of(h.wcode)
            candidates.append((SRC_WEIGHT["whois"], ("code", h.wcode), c, ct, la, lo, "whois"))

        hr = self._rtt(h)
        if hr is not None:
            prev = next((o for o in self.hops if o.hop == h.hop - 1), None)
            pr = self._rtt(prev) if prev is not None else None
            if prev is not None and pr is not None:
                pc, pct, pla, plo, psrc = self._eff(prev)
                delta = abs(hr - pr)
                # старое правило: наследуем только от "уверенных" узлов при почти равном RTT
                if delta <= 2 and (psrc in ("host", "learned", "whois", "near") or prev.hop == 0):
                    candidates.append((SRC_WEIGHT["near"], ("pt", round(pla, 2), round(plo, 2)),
                                       pc, pct, pla, plo, "near"))
                # RTT-Override: разница <= 4 мс => физически в одном месте,
                # вес 10.0 перебивает любой GeoIP (даже geo_agree)
                elif delta <= 4:
                    candidates.append((SRC_WEIGHT["rtt_override"], ("rtt_override", round(pla, 2), round(plo, 2)),
                                       pc, pct, pla, plo, "rtt_override"))

        c, ct = translate_city(h.city, h.country, self.lang)
        geo_weight = SRC_WEIGHT["geo_agree"] if h.geo_agree else SRC_WEIGHT["geo"]
        candidates.append((geo_weight, ("pt", round(h.lat, 2), round(h.lon, 2)), c, ct, h.lat, h.lon, h.src))

        # PeeringDB: штаб-квартира ASN
        pdb = self.bgp.fetch_asn_geo(h.asn)
        if pdb and pdb.get("hq") and not h.anycast:  # Игнорируем CDN/Anycast (AS13335 и т.д.)
            host_lower = (h.hostname or "").lower()
            name_match = bool(pdb["name"]) and pdb["name"] in host_lower
            # AKA в PeeringDB часто перечисляется через запятую
            aka_match = bool(pdb["aka"]) and any(part.strip() in host_lower for part in pdb["aka"].split(','))
            # Если провайдер совпадает с hostname ИЛИ у нас вообще нет других зацепок (hcode пуст)
            if name_match or aka_match or not h.hcode:
                c, ct, la, lo = pdb["hq"]["city"], pdb["hq"]["country"], pdb["hq"]["lat"], pdb["hq"]["lon"]
                candidates.append((
                    SRC_WEIGHT["peeringdb"],
                    ("pt", round(la, 2), round(lo, 2)),
                    c, ct, la, lo, "peeringdb"
                ))

        # <--- Boss Level: Facilities (Точки присутствия / Дата-центры)
        if h.asn and not h.anycast:
            facs = self.bgp.fetch_facilities(h.asn)
            if facs:
                geo_city_l = (h.city or "").strip().lower()
                ptr_city_l = ""
                if h.hcode and h.hcode in CITY_DB:
                    ptr_city_l = CITY_DB[h.hcode][1].lower()  # Английское название

                best_fac = None
                for fac in facs:
                    fac_city_l = (fac["city"] or "").strip().lower()
                    city_match = False
                    # Проверка 1: Совпадение названий городов
                    if fac_city_l and (fac_city_l in geo_city_l or geo_city_l in fac_city_l or
                                       fac_city_l in ptr_city_l or ptr_city_l in fac_city_l):
                        city_match = True
                    # Проверка 2: Дата-центр в пригороде (расстояние < 50 км от GeoIP)
                    elif h.lat and h.lon:
                        dist = haversine(h.lat, h.lon, fac["lat"], fac["lon"])
                        if dist < 50:
                            city_match = True

                    if city_match:
                        best_fac = fac
                        break

                if best_fac:
                    boosted = False
                    # Ищем существующего кандидата, чтобы усилить его и снэпнуть к зданию
                    for i, (w, key, cc, cct, cla, clo, csrc) in enumerate(candidates):
                        if csrc in ("host", "geo", "geo_agree", "learned", "peeringdb", "whois"):
                            if (cc.lower() == best_fac["city"].lower() or
                                    cc.lower() in best_fac["city"].lower() or
                                    best_fac["city"].lower() in cc.lower() or
                                    cc.lower() in ("unknown", "")):
                                # БОСС-СНЭП: усиливаем вес И заменяем координаты на точные координаты ДЦ
                                candidates[i] = (w + SRC_WEIGHT["facility"], key, cc, cct,
                                                 best_fac["lat"], best_fac["lon"], csrc)
                                boosted = True
                                break

                    # Если бустить некого, добавляем как самостоятельного мощного кандидата
                    if not boosted:
                        candidates.append((SRC_WEIGHT["facility"], ("facility", best_fac["name"]),
                                           best_fac["city"], best_fac["country"],
                                           best_fac["lat"], best_fac["lon"], "facility"))

        groups = {}
        for w, key, cc, cct, cla, clo, csrc in candidates:
            groups.setdefault(key, []).append((w, cc, cct, cla, clo, csrc))

        best_key, best_total = None, -1.0
        for key, members in groups.items():
            total = sum(m[0] for m in members)
            if total > best_total:
                best_total, best_key = total, key
        runner_up = max((sum(m[0] for m in mem) for key, mem in groups.items() if key != best_key),
                        default=0.0)
        margin = max(0.0, best_total - runner_up)
        # keyed by (hop, ip), not just ip — a routing loop can revisit the same IP at
        # a different hop, and each occurrence should keep its own confidence score
        self._eff_conf[(h.hop, h.ip)] = round(min(1.0, margin / CONFIDENCE_CEILING), 3)
        top = max(groups[best_key], key=lambda m: m[0])
        return top[1], top[2], top[3], top[4], top[5]

    def _conf(self, h, sus, consistent=frozenset()):
        """Display-ready consensus confidence for a hop: the raw weighted-consensus score
        from _eff() (how much corroborating signal backs the winning location), adjusted by
        what _audit_sus() independently found when cross-checking RTT physics — capped low
        when it found the location physically inconsistent, nudged up when it found the
        location consistent with every distant landmark checked (real, if modest,
        corroboration for a hop whose location otherwise rests on GeoIP alone). Computed
        here rather than mutated inside _audit_sus() itself, because _eff() is called again
        by every caller after _audit_sus() runs and would silently recompute (and overwrite)
        an adjusted value otherwise — a hop must never display as both "suspicious" and
        "confident" at once.

        Hop 0 ("you") is exempt: it's the trace's own anchor point, not an inference about a
        downstream router, so it isn't subject to the same signal-corroboration uncertainty
        as the rest of the route — showing an inference-confidence badge next to "you are
        here" is confusing regardless of how the underlying signals happen to score."""
        if h.hop == 0:
            return 1.0
        c = self._eff_conf.get((h.hop, h.ip), 1.0)
        if h.ip in sus:
            return min(c, 0.3)
        if h.ip in consistent:
            return min(1.0, c + 0.15)
        return c

    def _conf_note(self, h, sus, consistent, src):
        """Short, plain-language explanation for the confidence badge's hover tooltip.
        Priority matters here: a strong signal (host/learned/whois/ixp) explains the score
        even when the hop is also RTT-consistent, since _conf()'s "consistent" boost is a
        flat +0.15 nudge that's really only the *story* when GeoIP was the only source to
        begin with — checking `consistent` before `src` would (and did) mislabel a
        hostname-confirmed hop as "GeoIP only". Two short lines (not one long one) so the
        native tooltip wraps compactly instead of stretching to the screen edge."""
        L = LANGS[self.lang]
        intro = L["conf_intro"]
        if h.hop == 0:
            reason = L["conf_you"]
        elif h.ip in sus:
            reason = L["conf_capped"]
        elif src in ("host", "learned", "whois", "ixp"):
            reason = L["conf_strong"]
        elif h.ip in consistent:
            reason = L["conf_boosted"]
        else:
            reason = L["conf_weak"]
        return f"{intro}\n{reason}"

    def _audit_sus(self):
        """Cross-checks each non-anycast hop's claimed position against every previously
        confirmed hop already walked in this trace (not just the immediately preceding one),
        using a per-trace-calibrated, detour-adjusted speed-of-light bound (_speed_bound). A
        hop that could not physically be as far away as GeoIP/PTR/whois claims, given how
        little extra RTT it took to reach from multiple earlier reference points, either gets
        folded into anycast detection (when its AS role looks like edge/CDN infrastructure)
        or flagged suspicious otherwise (probably stale/wrong location data).

        Also returns the complementary positive case: hops fully consistent with every
        distant landmark checked so far. That's real, if modest, corroboration for a hop
        whose location otherwise rests on GeoIP alone — see _conf(), which uses it to
        separate "GeoIP said X and nothing contradicts it" from "GeoIP said X and we have
        no way to check it", instead of both reading as the same flat, uninformative
        number."""
        self._live_rtt = self.ping_manager.live_min_rtts()
        sus = set()
        consistent = set()
        speed = self._speed_bound()
        landmarks = []  # (rtt, lat, lon) of hops already trusted as position references
        for h in self._sorted_hops():
            r = self._rtt(h)
            if h.anycast:
                continue
            _, _, lat, lon, src = self._eff(h)
            if r is not None and landmarks:
                checked = violations = 0
                for p_r, p_lat, p_lon in landmarks:
                    dist = haversine(p_lat, p_lon, lat, lon)
                    if dist <= 400:
                        continue
                    checked += 1
                    delta = max(0.0, r - p_r)
                    if delta < self._min_rtt_for_distance(dist, speed) * 0.5:
                        violations += 1
                if checked:
                    ratio = violations / checked
                    if ratio >= 0.6:
                        # too close (in time) to too many already-confirmed hops to really
                        # be where GeoIP/PTR/whois claims — if this AS looks like edge/CDN
                        # infrastructure treat it as anycast, otherwise flag it as suspect
                        if h.role == "edge":
                            h.anycast = True
                        else:
                            sus.add(h.ip)
                            if src == "learned":
                                self.learner.demote(h.ip)
                    elif ratio == 0:
                        consistent.add(h.ip)
            if r is not None and not h.anycast and not h.ms_bound:
                landmarks.append((r, lat, lon))
        return sus, consistent

    # ------------------------------------------------------------- UI
    def _setup_ui(self):
        # рамки-обводки 1 px: цвет задаётся в _apply_theme
        self.borders = []

        def make_border(parent):
            fr = tk.Frame(parent, padx=1, pady=1)
            self.borders.append(fr)
            return fr

        top = ttk.Frame(self, padding=12)
        top.pack(side=tk.TOP, fill=tk.X)

        self.addr_label = ttk.Label(top, font=("Arial", 10, "bold"))
        self.addr_label.pack(anchor=tk.W)

        entry_frame = ttk.Frame(top)
        entry_frame.pack(fill=tk.X, pady=4)

        self.entry = ttk.Entry(entry_frame, font=("Arial", 10))
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        self.entry.insert(0, self.history[0] if self.history else "example.com")

        self.entry.bind("<FocusIn>", self._on_entry_focus)
        self.entry.bind("<Return>", lambda e: self._toggle_trace())
        for seq in ("<Control-c>", "<Control-C>", "<Control-Cyrillic_es>"):
            self.entry.bind(seq, self._entry_copy)
        for seq in ("<Control-v>", "<Control-V>", "<Control-Cyrillic_em>"):
            self.entry.bind(seq, self._entry_paste)
        for seq in ("<Control-a>", "<Control-A>", "<Control-Cyrillic_ef>"):
            self.entry.bind(seq, self._entry_select_all_kbd)
        for seq in ("<Control-x>", "<Control-X>", "<Control-Cyrillic_che>"):
            self.entry.bind(seq, self._entry_cut)
        if sys.platform == "win32":
            self.entry.bind("<Control-KeyPress>", self._entry_ctrl_keycode)

        self.entry_menu = tk.Menu(self, tearoff=0)
        self.entry_menu.add_command(label="Вырезать", command=self._entry_cut)
        self.entry_menu.add_command(label="Копировать", command=self._entry_copy)
        self.entry_menu.add_command(label="Вставить", command=self._entry_paste)
        self.entry_menu.add_separator()
        self.entry_menu.add_command(label="Выделить всё", command=self._entry_select_all_kbd)
        self.entry.bind("<Button-3>", lambda e: self.entry_menu.tk_popup(e.x_root, e.y_root))

        right_col = ttk.Frame(entry_frame)
        right_col.pack(side=tk.RIGHT)

        # квадрат 2×2: язык | тема | обучение | ?
        grid = ttk.Frame(right_col)
        grid.pack()
        icon_kw = {"width": 3, "relief": "flat", "borderwidth": 0, "takefocus": 0}

        b = make_border(grid); b.grid(row=0, column=0, padx=3, pady=3)
        self.lang_btn = tk.Button(b, text="EN", command=self._toggle_lang, **icon_kw)
        self.lang_btn.pack()

        b = make_border(grid); b.grid(row=0, column=1, padx=3, pady=3)
        self.theme_btn = tk.Button(b, text="🌙", command=self._toggle_theme, **icon_kw)
        self.theme_btn.pack()

        b = make_border(grid); b.grid(row=1, column=0, padx=3, pady=3)
        self.brain_btn = tk.Button(b, text="🧠", command=self._show_learn_dialog, **icon_kw)
        self.brain_btn.pack()

        b = make_border(grid); b.grid(row=1, column=1, padx=3, pady=3)
        self.about_btn = tk.Button(b, text="?", command=self._show_about, **icon_kw)
        self.about_btn.pack()

        hb = make_border(entry_frame)
        hb.pack(side=tk.RIGHT, padx=(0, 2))
        self.hist_btn = tk.Button(hb, text="▾", width=2, command=self._show_history,
                                  relief="flat", borderwidth=0, takefocus=0)
        self.hist_btn.pack()

        bb = make_border(top)
        bb.pack(pady=(2, 0))
        self.btn = tk.Button(bb, text="Запустить", command=self._toggle_trace,
                             width=21, relief="flat", borderwidth=0, takefocus=0)
        self.btn.pack()

        log_frame = ttk.Frame(self, padding=12)
        log_frame.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(log_frame)
        header.pack(fill=tk.X)
        self.status = ttk.Label(header, font=("Arial", 9, "italic"))
        self.status.pack(side=tk.LEFT)

        cb = make_border(header)
        cb.pack(side=tk.RIGHT)
        self.copy_btn = tk.Button(cb, text="📋", width=3, command=self._copy_log,
                                  relief="flat", borderwidth=0, takefocus=0)
        self.copy_btn.pack()

        eb = make_border(header)
        eb.pack(side=tk.RIGHT, padx=(0, 6))
        self.export_btn = tk.Button(eb, text="Экспорт ▾", command=self._show_export_menu,
                                    relief="flat", borderwidth=0, takefocus=0)
        self.export_btn.pack()

        self.log = tk.Text(log_frame, wrap=tk.WORD, font=("Courier New", 9), bg="#1e1e1e", fg="#fff")
        self.log.pack(fill=tk.BOTH, expand=True)

        for seq in ("<Control-c>", "<Control-C>", "<Control-Cyrillic_es>"):
            self.log.bind(seq, self._log_copy)
        for seq in ("<Control-a>", "<Control-A>", "<Control-Cyrillic_ef>"):
            self.log.bind(seq, self._log_select_all)
        if sys.platform == "win32":
            self.log.bind("<Control-KeyPress>", self._log_ctrl_keycode)

        self.menu = tk.Menu(self, tearoff=0)
        self.menu.add_command(label="Копировать", command=self._copy_selection)
        self.log.bind("<Button-3>", lambda e: self.menu.tk_popup(e.x_root, e.y_root))

        self.export_menu = tk.Menu(self, tearoff=0)
        self.export_menu.add_command(label="📋 Копировать отчёт", command=self._copy_report)
        self.export_menu.add_separator()
        self.export_menu.add_command(label="Сохранить CSV…", command=self._save_csv)
        self.export_menu.add_command(label="Сохранить JSON…", command=self._save_json)
        self.export_menu.add_command(label="Сохранить HTML (автономный)…", command=self._save_html)

        for w in (self.btn, self.copy_btn, self.theme_btn, self.brain_btn,
                  self.about_btn, self.lang_btn, self.hist_btn, self.export_btn):
            self._bind_hover(w)

        self._apply_lang()

    # ------------------------------------------------------------- history
    def _show_history(self):
        if self.hist_win is not None:
            self._close_history()
            return
        win = tk.Toplevel(self)
        self.hist_win = win
        win.wm_overrideredirect(True)
        x = self.entry.winfo_rootx()
        y = self.entry.winfo_rooty() + self.entry.winfo_height() + 2
        w = max(240, self.entry.winfo_width())
        rows = max(1, len(self.history))
        self._hist_h = 30 + rows * 26
        win.geometry(f"{w}x{self._hist_h}+{x}+{y}")
        t = THEMES[self.theme]
        win.config(bg=t["outline"])
        if not self.history:
            ttk.Label(win, text=self.tr("hist_empty")).pack(padx=8, pady=8)
        else:
            for a in self.history:
                row = tk.Frame(win, bg=t["panel"])
                row.pack(fill=tk.X, padx=1, pady=1)
                lb = tk.Label(
                    row, text=a, anchor="w", bg=t["panel"], fg=t["fg"],
                    font=("Arial", 9), padx=6, pady=3, cursor="hand2"
                )
                lb.pack(side=tk.LEFT, fill=tk.X, expand=True)
                lb.bind("<Button-1>", lambda e, addr=a: self._pick_history(addr))
                xb = tk.Button(
                    row, text="✕", width=2, relief="flat", bd=0,
                    bg=t["panel"], fg=t["fg"],
                    activebackground=t["danger_hover"],
                    command=lambda addr=a: self._drop_history(addr)
                )
                xb.pack(side=tk.RIGHT)
        win.update_idletasks()
        win.lift()
        self.bind("<Configure>", self._reposition_history)

    def _reposition_history(self, event=None):
        """Держит список истории у поля ввода при перемещении/ресайзе окна."""
        if self.hist_win is None:
            return
        # <Configure> пропагирует и от дочерних виджетов — реагируем только
        # на перемещение/ресайз самого главного окна
        if event is not None and event.widget is not self:
            return
        x = self.entry.winfo_rootx()
        y = self.entry.winfo_rooty() + self.entry.winfo_height() + 2
        w = max(240, self.entry.winfo_width())
        self.hist_win.geometry(f"{w}x{self._hist_h}+{x}+{y}")

    def _pick_history(self, addr):
        self.entry.delete(0, tk.END)
        self.entry.insert(0, addr)
        self._close_history()

    def _drop_history(self, addr):
        if addr in self.history:
            self.history.remove(addr)
            self._save_prefs()
        self._close_history()
        if self.history:
            self._show_history()

    def _close_history(self):
        if self.hist_win is not None:
            try:
                self.hist_win.destroy()
            except Exception:
                pass
            self.hist_win = None
        try:
            self.unbind("<Configure>")
        except Exception:
            pass

    # ------------------------------------------------------------- hover
    def _bind_hover(self, widget):
        def on_enter(e):
            t = THEMES[self.theme]
            if widget is self.btn and self.tracing:
                widget.config(bg=t["danger_hover"])
            else:
                widget.config(bg=t["hover"])

        def on_leave(e):
            widget.config(bg=self._base_bg_for(widget))

        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)

    def _base_bg_for(self, widget):
        t = THEMES[self.theme]
        if widget is self.btn and self.tracing:
            return "#d32f2f"
        if widget is self.btn:
            return t["btn_bg"]
        return t["panel"]

    # ------------------------------------------------------------- themes
    def _toggle_theme(self):
        self._apply_theme("dark" if self.theme == "light" else "light")
        if self.hops:
            self._update_map(final=self.process is None)

    def _apply_theme(self, name, save=True):
        self.theme = name
        t = THEMES[name]
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=t["bg"], foreground=t["fg"])
        s.configure("TFrame", background=t["bg"])
        s.configure("TLabel", background=t["bg"], foreground=t["fg"])
        s.configure("TEntry", fieldbackground=t["entry_bg"],
                    foreground=t["entry_fg"], insertcolor=t["entry_fg"])
        s.configure("TButton", background=t["panel"], foreground=t["fg"])
        s.map("TButton", background=[("active", t["accent"])],
              foreground=[("active", "#ffffff")])
        s.configure("TRadiobutton", background=t["bg"], foreground=t["fg"])
        s.map("TRadiobutton",
              background=[("active", t["hover"])],
              foreground=[("active", t["fg"])])

        self.configure(bg=t["bg"])
        self.log.config(bg=t["log_bg"], fg=t["log_fg"],
                        insertbackground=t["log_fg"],
                        selectbackground=t["accent"], selectforeground="#ffffff")

        flat = {"relief": "flat", "borderwidth": 0,
                "activebackground": t["accent"], "activeforeground": "#ffffff"}
        self.btn.config(bg=self._base_bg_for(self.btn), fg=t["btn_fg"], pady=2, **flat)
        self.copy_btn.config(bg=t["panel"], fg=t["fg"], **flat)
        self.export_btn.config(bg=t["panel"], fg=t["fg"], padx=8, pady=2, **flat)
        self.theme_btn.config(text="🌙" if name == "light" else "☀️",
                              bg=t["panel"], fg=t["fg"], **flat)
        self.lang_btn.config(bg=t["panel"], fg=t["fg"], **flat)
        self.hist_btn.config(bg=t["panel"], fg=t["fg"], **flat)
        self.about_btn.config(bg=t["panel"], fg=t["fg"], **flat)

        # обводка 1 px: чёрная в светлой теме, белая в тёмной
        border = "#000000" if name == "light" else "#ffffff"
        for fr in self.borders:
            fr.config(bg=border)

        for m in (self.menu, self.entry_menu, self.export_menu):
            m.config(bg=t["panel"], fg=t["fg"],
                     activebackground=t["accent"], activeforeground="#ffffff")

        self._brain_appearance()
        if save:
            self._save_prefs()

    def _brain_appearance(self):
        t = THEMES[self.theme]
        self.brain_btn.config(bg=t["panel"],
                              fg=t["accent"] if self.learn_mode != "off" else t["fg"])

    # ------------------------------------------------------------- learning
    def _show_learn_dialog(self):
        t = THEMES[self.theme]
        win = tk.Toplevel(self)
        win.title(self.tr("learn_title"))
        win.geometry("470x340")
        win.attributes("-topmost", True)
        win.config(bg=t["bg"])
        ttk.Label(win, text=self.tr("learn_desc"), wraplength=440,
                  justify="left").pack(padx=12, pady=(12, 6))
        var = tk.StringVar(value=self.learn_mode)
        for mode, key in (("off", "learn_off"), ("semi", "learn_semi"), ("auto", "learn_auto")):
            ttk.Radiobutton(win, text=self.tr(key), variable=var,
                            value=mode).pack(anchor="w", padx=18, pady=2)

        def on_change(*_):
            self.learn_mode = var.get()
            self._save_prefs()
            self._brain_appearance()
        var.trace_add("write", on_change)

        ttk.Label(win, text=self.tr("learn_ptr", self.ptr_attempts, self.ptr_matches),
                  font=("Arial", 9)).pack(pady=(6, 0))

        bf = ttk.Frame(win)
        bf.pack(pady=10)
        total, trusted = self.learner.counts()
        stat = ttk.Label(bf, text=self.tr("learn_stat", total, trusted))
        stat.pack(side=tk.LEFT, padx=8)

        def clear():
            self.learner.clear()
            stat.config(text=self.tr("learn_stat", 0, 0))
        ttk.Button(bf, text=self.tr("learn_clear"), command=clear).pack(side=tk.LEFT)

    def _queue_suggestion(self, ev):
        self.suggest_queue.append(ev)
        self._next_suggestion()

    def _next_suggestion(self):
        if self.suggest_open or not self.suggest_queue:
            return
        ev = self.suggest_queue.pop(0)
        e = CITY_DB[ev["code"]]
        ru = self.lang == "ru"
        city = e[0] if ru else e[1]
        self.suggest_open = True

        lines = [self.tr("learn_head", ev["ip"], city),
                 self.tr("learn_ev_ptr", ev["host"])]
        if ev["org"]:
            lines.append(f"{ev['org']} ({ev['asn']})")
        ms_txt = f"{ev['ms']:.0f} {self.tr('ms')}" if ev["ms"] is not None else "—"
        lines.append(self.tr("learn_ev_hop", ev["hop"], ms_txt))
        lines.append(self.tr("learn_ev_geo", ev["geo_city"]))
        if ev["geo_city"].strip().lower() in (e[0].lower(), e[1].lower()):
            lines.append(self.tr("learn_ev_agree"))
        else:
            lines.append(self.tr("learn_ev_diff", ev["geo_city"]))
        user = next((h for h in self.hops if h.hop == 0), None)
        if user is not None and ev["ms"] is not None:
            dist = haversine(user.lat, user.lon, e[2], e[3])
            if ev["ms"] >= self._min_rtt_for_distance(dist) * 0.5:
                lines.append(self.tr("learn_ev_ok", city, int(dist)))
            else:
                lines.append(self.tr("learn_ev_bad", int(ev["ms"]), int(dist), city))

        win = tk.Toplevel(self)
        win.title("🧠")
        win.geometry(f"470x{128 + (len(lines) + 1) * 16}")
        win.attributes("-topmost", True)
        ttk.Label(win, text="\n".join(lines), justify="left",
                  font=("Arial", 9)).pack(padx=12, pady=(10, 0))
        ttk.Label(win, text=self.tr("learn_question"), justify="center",
                  anchor="center", font=("Arial", 9)).pack(fill=tk.X, padx=12, pady=(8, 0))
        ttk.Label(win, text="").pack()
        bf = ttk.Frame(win)
        bf.pack(pady=(0, 10))

        def close():
            self.suggest_open = False
            win.destroy()
            self.after(100, self._next_suggestion)

        def yes():
            self.learner.confirm(ev["ip"], ev["code"], ev["host"])
            self._update_map(final=self.process is None)
            close()

        ttk.Button(bf, text=self.tr("learn_save"), command=yes).pack(side=tk.LEFT, padx=5)
        ttk.Button(bf, text=self.tr("learn_skip"), command=close).pack(side=tk.LEFT, padx=5)

    # ------------------------------------------------------------- about
    def _show_about(self):
        t = THEMES[self.theme]
        win = tk.Toplevel(self)
        win.title(self.tr("about_title"))
        win.geometry("320x160")
        win.attributes("-topmost", True)
        win.config(bg=t["bg"])

        content = tk.Frame(win, bg=t["bg"])
        content.pack(expand=True)

        tk.Label(content, text="jdPhobos", bg=t["bg"], fg=t["fg"],
                 font=("Arial", 14, "bold")).pack(pady=(0, 10))

        email_var = tk.StringVar(value="jdphobos@gmail.com")
        email_entry = tk.Entry(content, textvariable=email_var, width=24,
                               justify="center", state="readonly",
                               bg=t["bg"], fg=t["accent"],
                               readonlybackground=t["bg"],
                               font=("Consolas", 10), relief="flat",
                               borderwidth=0, cursor="hand2")
        email_entry.pack(pady=(0, 8))

        def select_all(e=None):
            email_entry.focus_set()
            email_entry.select_range(0, tk.END)
            return "break"
        email_entry.bind("<Button-1>", select_all)

        def copy_mail(e=None):
            self.clipboard_clear()
            self.clipboard_append("jdphobos@gmail.com")
            return "break"
        for seq in ("<Control-c>", "<Control-C>", "<Control-Cyrillic_es>"):
            email_entry.bind(seq, copy_mail)
        if sys.platform == "win32":
            email_entry.bind("<Control-KeyPress>",
                             lambda e: copy_mail() if e.keycode == 67 else None)

        def open_mail(e=None):
            import webbrowser
            webbrowser.open("mailto:jdphobos@gmail.com")
        email_entry.bind("<Double-Button-1>", open_mail)

        tk.Label(content, text=self.tr("about_coding"), bg=t["bg"],
                 fg=t["fg"], font=("Arial", 8, "italic")).pack()

    # ── Кликабельный логотип GitHub в правом нижнем углу ──
        def open_github(e=None):
            import webbrowser
            webbrowser.open("https://github.com/jdPhobos/GeoTrace-MAP")
        
    # Эмодзи осьминога 🐙 как отсылка к Octocat, цвет адаптируется к теме
        gh_label = tk.Label(
            win, text="🐙 GitHub", bg=t["bg"], fg=t["accent"],
            font=("Arial", 12, "underline"), cursor="hand2"
    )
        gh_label.pack(side=tk.BOTTOM, anchor=tk.CENTER, padx=12, pady=8)
        gh_label.bind("<Button-1>", open_github)

    # ------------------------------------------- clipboard / hotkeys (entry)
    def _on_entry_focus(self, event=None):
        self.entry.select_range(0, tk.END)
        self.entry.icursor(tk.END)

    def _entry_copy(self, event=None):
        try:
            sel = self.entry.selection_get()
        except tk.TclError:
            sel = ""
        if sel:
            self.clipboard_clear()
            self.clipboard_append(sel)
        return "break"

    def _entry_cut(self, event=None):
        self._entry_copy()
        try:
            self.entry.delete(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            pass
        return "break"

    def _entry_paste(self, event=None):
        try:
            text = self.clipboard_get()
        except tk.TclError:
            return "break"
        text = text.strip()
        if text:
            text = text.splitlines()[0].strip()
        try:
            self.entry.delete(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            pass
        self.entry.insert(tk.INSERT, text)
        return "break"

    def _entry_select_all_kbd(self, event=None):
        self.entry.select_range(0, tk.END)
        self.entry.icursor(tk.END)
        return "break"

    def _entry_ctrl_keycode(self, event):
        return {65: self._entry_select_all_kbd, 67: self._entry_copy,
                86: self._entry_paste, 88: self._entry_cut}.get(event.keycode, lambda: None)()

    def _log_copy(self, event=None):
        try:
            sel = self.log.get(tk.SEL_FIRST, tk.SEL_LAST)
        except tk.TclError:
            return "break"
        if sel:
            self.clipboard_clear()
            self.clipboard_append(sel)
        return "break"

    def _log_select_all(self, event=None):
        self.log.tag_add(tk.SEL, "1.0", tk.END)
        self.log.mark_set(tk.INSERT, tk.END)
        return "break"

    def _log_ctrl_keycode(self, event):
        return {65: self._log_select_all, 67: self._log_copy}.get(event.keycode, lambda: None)()

    # ------------------------------------------------------------- trace
    def _toggle_trace(self):
        # self.tracing is set synchronously (on the UI thread) inside _start()/_stop(),
        # unlike self.process which is only populated once the background trace_worker
        # thread actually spawns tracert — checking self.process here left a race window
        # where a second click before that assignment landed would call _start() again.
        if self.tracing:
            self._stop()
        else:
            self._start()

    def _start(self):
        target = clean_target(self.entry.get())
        if len(target) < 3:
            return
        self._close_history()

        if target in self.history:
            self.history.remove(target)
        self.history.insert(0, target)
        self.history = self.history[:10]
        self._save_prefs()

        self.stop_event = threading.Event()
        self.tracing = True
        self.process = None
        self._bg_executors = []
        self.ptr_attempts = 0
        self.ptr_matches = 0
        self.hops.clear()
        self.ping_summary = ""
        self.log.delete("1.0", tk.END)
        self.map_opened = False

        self.entry.delete(0, tk.END)
        self.entry.insert(0, target)
        self.btn.config(text=self.tr("stop"), bg="#d32f2f", fg="white")
        self.status.config(text=self.tr("tracing"))

        for f in (CONFIG["map_file"], CONFIG["data_js_file"]):
            try:
                os.remove(f)
            except OSError:
                pass

        threading.Thread(target=trace_worker,
                         args=(target, self._callback, self.stop_event, self), daemon=True).start()

    def _stop(self):
        self.stop_event.set()
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.process.kill()
            except Exception:
                pass
            self.process = None
        self.tracing = False
        t = THEMES[self.theme]
        self.btn.config(text=self.tr("start"), bg=t["btn_bg"], fg=t["btn_fg"])
        self.status.config(text=self.tr("aborted"))

    def _callback(self, action, data):
        self.after(0, self._process, action, data)

    def _process(self, action, data):
        if action == "log":
            self.log.insert(tk.END, f"{data}\n")
            self.log.see(tk.END)

        elif action == "process":
            self.process = data

        elif action == "executors":
            self._bg_executors.extend(data)

        elif action == "hop":
            self.hops.append(data)
        # ── FIX: применить уже пришедшие PTR/WHOIS (гонка колбэков) ──
        # ptr_cache/whois_cache заполняются в trace_worker *до* отправки "hop",
        # поэтому в момент прихода хопа кэш может уже содержать данные для этого IP.
            ip = data.ip
            if ip in ptr_cache and ptr_cache[ip] and not data.hcode:
                code, host = ptr_cache[ip]
                data.hcode = code
                data.hostname = host
            # НЕ трогаем data.src: он описывает источник GEO-кандидата (geo/geo_agree),
            # а PTR-информация живёт отдельно в hcode. Подмена src ломает _eff и тултип.
            if ip in whois_cache and whois_cache[ip] and not data.wcode:
                wcode, _ = whois_cache[ip]
                data.wcode = wcode
        # ── END FIX ──
            if self.tracing:
                self.status.config(text=self.tr("tracing_hops", len(self.hops)))
            self._update_map()

        elif action == "ptr_stat":
            self.ptr_attempts += 1
            self.ptr_matches += data

        elif action == "fix":
            ip = data.get("ip", "")
            code = data.get("code", "")
            host = data.get("host", "")
            if ip and code:
                hop = None
                for h in self.hops:
                    if h.ip == ip and (not h.hcode or h.hcode != code):
                        h.hcode = code
                        h.hostname = host
                    # убрал `h.src = "host"` — см. комментарий выше и §3.4 предыдущего ревью
                        hop = h
                        break
            # если хоп ещё не добавлен — ничего не делаем: _process("hop") применит
            # данные из ptr_cache позже; кэш в trace_worker уже заполнен
                if hop is not None and self.hops:
                    self._update_map(final=self.process is None)
                # обучение — только для реального хопа, найденного в self.hops
                    if code in CITY_DB and not hop.anycast:
                        if self.learn_mode == "auto":
                            feasible, corroborated, _dist = self._learn_evidence(hop, code)
                            self.learner.observe(ip, code, host,
                                                 feasible=feasible, corroborated=corroborated)
                        elif self.learn_mode == "semi":
                            if not self.learner.trusted_code(ip):
                                self._queue_suggestion({
                                    "ip": ip, "code": code, "host": host,
                                    "geo_city": hop.city, "ms": hop.ms,
                                    "asn": hop.asn, "org": hop.org, "hop": hop.hop})

        elif action == "whois":
            ip = data.get("ip", "")
            code = data.get("code", "")
            if ip and code:
                changed = False
                for h in self.hops:
                    if h.ip == ip and not h.wcode:
                        h.wcode = code
                        changed = True
                        break
                if changed and self.hops:
                    self._update_map(final=self.process is None)
        elif action == "bgp":
            ip = data.get("ip", "")
            for h in self.hops:
                if h.ip == ip:
                    if data.get("ixp"):
                        h.ixp = data["ixp"]
                    if data.get("role"):
                        h.role = data["role"]
            if self.hops:
                self._update_map(final=self.process is None)
        elif action == "ping":
            self.ping_summary = data
            self.status.config(text=self.tr("ready_ping", data))
        elif action in ("done", "aborted"):
            self.process = None
            self.tracing = False
            t = THEMES[self.theme]
            self.btn.config(text=self.tr("start"), bg=t["btn_bg"], fg=t["btn_fg"])
            if action == "done" and isinstance(data, dict):
                self.trace_stats = data
                g = data["global"]
                skip = data["total"] - g
                if skip > 0:
                    self.status.config(text=f"{self.tr('ready')} · {g}/{data['total']} ({skip} ⊘)")
                else:
                    self.status.config(text=self.tr("ready"))
            else:
                self.status.config(text=self.tr("aborted"))
            self._update_map(final=True)
            if action == "done" and isinstance(data, dict):
                threading.Thread(target=self._ping_worker,
                                 args=(data["target"],), daemon=True).start()
                messagebox.showinfo(self.tr("done_title"), self.tr("done_msg"))
        elif action == "error":
            self.process = None
            self.tracing = False
            t = THEMES[self.theme]
            self.btn.config(text=self.tr("start"), bg=t["btn_bg"], fg=t["btn_fg"])
            messagebox.showerror(self.tr("err_title"), data)

    # ------------------------------------------------------------- ping
    def _ping_worker(self, target):
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        kwargs = {"startupinfo": si,
                  "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}
        rtts = []
        icmp_ok = False
        try:
            r = subprocess.run(["ping", "-n", "4", "-w", "1500", target],
                               capture_output=True, text=True, timeout=20,
                               encoding='cp866', errors='ignore', **kwargs)
            out = r.stdout or ""
            rtts = [float(v.replace(",", ".")) for v in
                    re.findall(r'(?:time|время)\s*[<=]\s*(\d+(?:[.,]\d+)?)', out, re.IGNORECASE)]
            icmp_ok = len(rtts) > 0
        except Exception:
            pass

        if icmp_ok:
            rtts_sorted = sorted(rtts)
            n = len(rtts_sorted)
            median = rtts_sorted[n // 2] if n % 2 else (rtts_sorted[n // 2 - 1] + rtts_sorted[n // 2]) / 2
            loss = int(round((4 - len(rtts)) / 4 * 100))
            summary = self.tr("ping_ok", mn=int(round(min(rtts))),
                              avg=int(round(median)),
                              mx=int(round(max(rtts))), loss=loss)
        else:
            tcp_ms = self._tcp_ping(target)
            if tcp_ms is not None:
                summary = self.tr("ping_tcp", ms=tcp_ms)
            else:
                summary = self.tr("ping_no")

        self._callback("ping", summary)

    def _tcp_ping(self, target):
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        kwargs = {"startupinfo": si,
                  "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}
        try:
            r = subprocess.run(["curl", "-o", "NUL", "-s", "-w", "%{time_connect}",
                                f"https://{target}/"],
                               capture_output=True, text=True, timeout=5, **kwargs)
            if r.returncode == 0 and r.stdout.strip():
                t = float(r.stdout.strip())
                return int(round(t * 1000))
        except Exception:
            pass
        return None

    # ------------------------------------------------------------- export
    def _show_export_menu(self):
        if not self.hops:
            return
        self.export_menu.tk_popup(self.export_btn.winfo_rootx(),
                                  self.export_btn.winfo_rooty() + self.export_btn.winfo_height())

    def _sorted_hops(self):
        return sorted(self.hops, key=lambda h: h.hop)

    def _copy_report(self):
        if not self.hops:
            return
        unit = self.tr("ms")
        sus, consistent = self._audit_sus()
        lines = [self.tr("report_title", self.entry.get().strip())]
        for h in self._sorted_hops():
            c, ct, _, _, src = self._eff(h)
            ms = f" · {'<' if h.ms_bound else ''}{h.ms:.0f} {unit}" if h.ms is not None else ""
            org = f" · {h.org}" if h.org else ""
            tgt = " · 🎯" if h.target else ""
            asn = f" ({h.asn})" if h.asn else ""
            src_sym = {"ixp": "⚡", "facility": "🏢", "host": "📇", "learned": "🧠", "whois": "📜", "near": "📍", "rtt_override": "🧲", "peeringdb": "🏢"}.get(src, "🛰")
            ac = " · 🌐" if h.anycast else ""
            warn = " · ⚠" if h.ip in sus else ""
            role = " · 🛣️" if h.role == "transit" else (" · 🏠" if h.role == "edge" else "")
            conf = self._conf(h, sus, consistent)
            low_conf = f" · {conf:.0%}" if conf < 0.6 else ""
            lines.append(f"{h.hop} · {c}, {ct} · {h.ip}{ms}{org}{asn}{role} · {src_sym}{low_conf}{tgt}{ac}{warn}")
        if self.trace_stats:
            skip = self.trace_stats["total"] - self.trace_stats["global"]
            if skip > 0:
                lines.append(self.tr("report_skipped", skip))
        if self.ping_summary:
            lines.append(self.tr("report_ping", self.ping_summary))
        self.clipboard_clear()
        self.clipboard_append("\n".join(lines))
        self.status.config(text=self.tr("report_copied"))

    def _save_csv(self):
        if not self.hops:
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")],
                                            initialfile=f"trace_{clean_target(self.entry.get())}.csv")
        if not path:
            return
        sus, consistent = self._audit_sus()
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["hop", "ip", "city", "country", "lat", "lon", "avg_ms", "ms_bound", "asn", "org",
                        "geo_src", "confidence", "anycast", "suspect", "target"])
            for h in self._sorted_hops():
                c, ct, la, lo, src = self._eff(h)
                w.writerow([h.hop, h.ip, c, ct, la, lo, h.ms if h.ms is not None else "",
                            1 if h.ms_bound else 0, h.asn, h.org, src, self._conf(h, sus, consistent), 1 if h.anycast else 0, 1 if h.ip in sus else 0, 1 if h.target else 0])

    def _save_json(self):
        if not self.hops:
            return
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")],
                                            initialfile=f"trace_{clean_target(self.entry.get())}.json")
        if not path:
            return
        sus, consistent = self._audit_sus()
        hops = []
        for h in self._sorted_hops():
            d = asdict(h)  # copy, not a reference to h.__dict__ — must not mutate the live hop
            c, ct, la, lo, src = self._eff(h)
            d.update({"eff_city": c, "eff_country": ct, "eff_lat": la, "eff_lon": lo,
                      "geo_src": src, "confidence": self._conf(h, sus, consistent), "suspect": h.ip in sus})
            hops.append(d)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"target": self.entry.get().strip(), "ping": self.ping_summary,
                       "hops": hops}, f, ensure_ascii=False, indent=2)

    def _save_html(self):
        if not self.hops:
            return
        path = filedialog.asksaveasfilename(defaultextension=".html", filetypes=[("HTML", "*.html")],
                                            initialfile=f"trace_{clean_target(self.entry.get())}.html")
        if not path:
            return
        payload = self._build_payload(final=True)
        html = self._render_map_html(self.entry.get().strip(),
                                     inline_payload=json.dumps(payload, ensure_ascii=False), api_port=0)
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        self.status.config(text=self.tr("html_saved"))

    # ------------------------------------------------------------- map
    def _render_map_html(self, title, inline_payload=None, api_port=None):
        port = self.api_port if api_port is None else api_port
        token = self.api_token if port else ""
        L = LANGS[self.lang]
        lstr = {
            "lang": self.lang,
            "annot": L["m_annot"], "footer": L["m_footer"],
            "seam": L["m_seam"], "copied": L["m_copied"],
            "starting": L["m_starting"], "waiting": L["m_waiting"],
            "nolink": L["m_nolink"], "stop": L["m_stop"],
            "again": L["m_again"], "copyout": L["m_copyout"],
            "close": L["m_close"], "ms": L["ms"],
            "zilla_on": L["m_zilla_on"], "zilla_off": L["m_zilla_off"],
            "zilla_live": L["m_zilla_live"],
            "src_geo": L["m_src_geo"], "src_host": L["m_src_host"],
            "src_learned": L["m_src_learned"], "src_whois": L["m_src_whois"],
            "src_near": L["m_src_near"], "src_ixp": L["m_src_ixp"],
            "src_facility": L["m_src_facility"],
            "src_peeringdb": L["m_src_peeringdb"],
            "src_rtt": L["m_src_rtt"],
            "role_transit": L["m_role_transit"], "role_edge": L["m_role_edge"],
            "sus": L["m_sus"], "anycast": L["m_anycast"],
            "target": L["m_target"], "recovered": L["m_recovered"],
            "pin": L["m_pin"], "unpin": L["m_unpin"],
        }
        html = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="utf-8">
    <title>GeoTrace MAP</title>
    <script src="https://cdn.plot.ly/plotly-2.24.1.min.js"></script>
    <style>
        body { margin: 0; padding: 0; overflow: hidden; background: #fcfaf2; transition: background .3s ease; }
        #graph { width: 100vw; height: 100vh; }
        #toast { position: fixed; top: 20px; left: 50%; transform: translateX(-50%); background: rgba(46,125,50,.9); color: #fff; padding: 10px 20px; border-radius: 20px; display: none; z-index: 10000; font-family: "Segoe UI", system-ui, Arial, sans-serif; }
        #tooltip { position: fixed; left: -9999px; top: -9999px; min-width: 250px; max-width: 340px; max-height: calc(100vh - 24px); overflow-y: auto; overflow-x: hidden; background: rgba(17, 24, 39, .94); backdrop-filter: blur(6px); border: 1px solid rgba(255,255,255,.08); border-radius: 12px; box-shadow: 0 10px 30px rgba(0,0,0,.35); padding: 8px; font-family: "Segoe UI", system-ui, Arial, sans-serif; color: #f9fafb; pointer-events: auto; visibility: hidden; opacity: 0; transform: translateY(4px); transition: opacity .15s ease, transform .15s ease, visibility .15s; z-index: 9999; }
        #tooltip.show { opacity: 1; transform: translateY(0); visibility: visible; }
        #tooltip::-webkit-scrollbar { width: 8px; }
        #tooltip::-webkit-scrollbar-thumb { background: rgba(255,255,255,.18); border-radius: 4px; }
        #tooltip::-webkit-scrollbar-track { background: transparent; }
        .tt-header { display: flex; justify-content: space-between; align-items: center; gap: 10px; padding: 4px 6px 8px 6px; border-bottom: 1px solid rgba(255,255,255,.08); margin-bottom: 6px; position: sticky; top: -8px; background: rgba(17, 24, 39, .97); margin-top: -8px; padding-top: 8px; border-radius: 12px 12px 0 0; z-index: 2; }
        .pinned-tip { position: fixed; min-width: 250px; max-width: 340px; max-height: calc(100vh - 24px); overflow-y: auto; overflow-x: hidden; background: rgba(17, 24, 39, .96); backdrop-filter: blur(6px); border: 1px solid rgba(255,255,255,.08); border-radius: 12px; box-shadow: 0 12px 32px rgba(0,0,0,.4); padding: 8px; font-family: "Segoe UI", system-ui, Arial, sans-serif; color: #f9fafb; }
        .pinned-tip .tt-header { cursor: move; user-select: none; }
        .tt-target { margin: 2px 0 0 30px; font-size: 10.5px; color: #ef5350; }
        .tt-city { font-weight: 600; font-size: 13px; }
        .tt-count { font-size: 11px; color: #9ca3af; background: rgba(255,255,255,.08); padding: 2px 8px; border-radius: 10px; white-space: nowrap; }
        .tt-pin { margin-left: auto; background: rgba(255,255,255,.08); border: none; color: #e5e7eb; width: 24px; height: 24px; border-radius: 6px; cursor: pointer; font-size: 12px; line-height: 1; flex: 0 0 auto; filter: grayscale(70%); opacity: .75; }
        .tt-pin:hover { background: rgba(79,195,247,.35); filter: none; opacity: 1; }
        .tt-pin.on { background: rgba(79,195,247,.45); filter: none; opacity: 1; }
        .tt-row { padding: 5px 6px; border-radius: 7px; }
        .tt-row.tt-alt { background: rgba(255,255,255,.07); }
        .tt-row.tt-ping { cursor: pointer; }
        .tt-row.tt-ping:hover { outline: 1px solid rgba(79,195,247,.45); }
        .tt-main { flex: 1; min-width: 0; }
        .tt-line1 { display: flex; align-items: center; gap: 8px; }
        .tt-hop { min-width: 22px; height: 22px; border-radius: 50%; background: #0288d1; color: #fff; display: inline-flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 700; flex: 0 0 auto; }
        .tt-ip { font-family: Consolas, "Courier New", monospace; font-size: 12.5px; color: #e5e7eb; }
        .tt-ms { margin-left: auto; font-family: Consolas, monospace; font-size: 11px; color: #9ca3af; white-space: nowrap; }
        .tt-org { margin: 2px 0 0 30px; font-size: 11px; color: #8b93a7; white-space: normal; overflow-wrap: break-word; }
        .tt-sus { margin: 2px 0 0 30px; font-size: 10.5px; color: #fbbf24; }
        .tt-anycast { margin: 2px 0 0 30px; font-size: 10.5px; color: #a78bfa; }
        .tt-conf { font-family: Consolas, monospace; font-size: 10px; opacity: .85; cursor: help; }
        .tt-seam { display: flex; align-items: center; gap: 6px; margin: 4px 2px; font-size: 10.5px; color: #fbbf24; }
        .tt-seam::before, .tt-seam::after { content: ""; flex: 1; border-top: 1px dashed rgba(251,191,36,.4); }
        .tt-footer { margin-top: 6px; padding-top: 6px; border-top: 1px solid rgba(255,255,255,.08); font-size: 10.5px; color: #8b93a7; }
        .ping-panel { position: fixed; width: 380px; max-width: 92vw; background: rgba(17, 24, 39, .96); backdrop-filter: blur(6px); border: 1px solid rgba(255,255,255,.08); border-radius: 12px; box-shadow: 0 12px 32px rgba(0,0,0,.4); color: #f9fafb; font-family: "Segoe UI", system-ui, Arial, sans-serif; z-index: 10001; display: flex; flex-direction: column; }
        .pp-header { display: flex; align-items: center; gap: 8px; padding: 8px 10px; cursor: move; user-select: none; border-bottom: 1px solid rgba(255,255,255,.08); border-radius: 12px 12px 0 0; background: rgba(255,255,255,.04); }
        .pp-title { font-weight: 600; font-size: 12.5px; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .pp-btn { background: rgba(255,255,255,.08); border: none; color: #e5e7eb; width: 24px; height: 24px; border-radius: 6px; cursor: pointer; font-size: 12px; line-height: 1; flex: 0 0 auto; }
        .pp-btn:hover { background: rgba(79,195,247,.35); }
        .pp-btn.stop:hover { background: rgba(198,40,40,.55); }
        .pp-stats { padding: 6px 10px; font-size: 11px; color: #9ca3af; border-bottom: 1px dashed rgba(255,255,255,.08); }
        .pp-body { padding: 6px 8px; height: 220px; overflow-y: auto; font-family: Consolas, "Courier New", monospace; font-size: 11.5px; color: #d1d5db; }
        .pp-body::-webkit-scrollbar { width: 8px; }
        .pp-body::-webkit-scrollbar-thumb { background: rgba(255,255,255,.18); border-radius: 4px; }
        .pp-line { padding: 1px 4px; border-radius: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .pp-line:nth-child(even) { background: rgba(255,255,255,.05); }
        #zillaBtn { position: fixed; right: 10px; bottom: 10px; background: transparent; border: none; cursor: pointer; font-size: 20px; opacity: .22; z-index: 9500; transition: opacity .2s ease, transform .2s ease; filter: grayscale(70%); }
        #zillaBtn:hover { opacity: .95; transform: scale(1.15); filter: none; }
        #zillaBtn.active { opacity: .9; filter: none; }
        #zilla { position: fixed; left: -100px; top: -100px; font-size: 30px; z-index: 9400; pointer-events: none; transform: translate(-50%, -100%); filter: drop-shadow(0 4px 6px rgba(0,0,0,.35)); }
        #zilla .zflip { display: block; position: relative; transform-origin: 50% 100%; }
        #zilla .flame { position: absolute; left: -24px; top: 4px; font-size: 20px; opacity: 0; transform: scale(.3); transform-origin: right center; }
        #zilla.breathe .flame { animation: flameJet .55s ease-out; }
        @keyframes flameJet { 0% {opacity:0; transform:scale(.3);} 25% {opacity:1; transform:scale(1.25);} 100% {opacity:0; transform:scale(1.6);} }
        #zilla .roar { position: absolute; left: 50%; top: -26px; transform: translateX(-50%); font: 700 12px "Segoe UI", sans-serif; color: #fbbf24; text-shadow: 0 1px 2px #000; opacity: 0; white-space: nowrap; }
        #zilla.roaring .roar { animation: roarPop 1s ease-out; }
        @keyframes roarPop { 0% {opacity:0; transform:translateX(-50%) scale(.5);} 20% {opacity:1; transform:translateX(-50%) scale(1.1);} 80% {opacity:1;} 100% {opacity:0; transform:translateX(-50%) scale(1);} }
        .fire-spot { position: fixed; font-size: 18px; z-index: 9300; pointer-events: none; transform: translate(-50%, -80%); animation: fireFlicker 1s ease-in-out infinite; filter: drop-shadow(0 0 6px rgba(255,120,0,.8)); }
        @keyframes fireFlicker { 0%,100% {transform:translate(-50%,-80%) scale(1) rotate(-2deg); opacity:.95;} 50% {transform:translate(-50%,-86%) scale(1.15) rotate(2deg); opacity:.8;} }
        body.quake #graph { animation: quakeShake .3s linear; }
        @keyframes quakeShake { 0%,100% {transform:translate(0,0);} 25% {transform:translate(1px,.5px);} 50% {transform:translate(-1px,-.5px);} 75% {transform:translate(.5px,-.5px);} }
        .fx-hole { position: fixed; width: 74px; height: 18px; z-index: 9390; transform: translate(-50%, -50%); background: radial-gradient(ellipse at center, rgba(0,0,0,.6) 0%, rgba(0,0,0,.35) 45%, transparent 72%); border-radius: 50%; animation: holeOpen 1.4s ease-out forwards; pointer-events: none; }
        @keyframes holeOpen { 0% {transform:translate(-50%,-50%) scaleX(.1); opacity:0;} 30% {opacity:1;} 100% {transform:translate(-50%,-50%) scaleX(1); opacity:.9;} }
        .fx-dust { position: fixed; font-size: 16px; z-index: 9391; pointer-events: none; transform: translate(-50%, -50%); animation: dustPuff .8s ease-out forwards; }
        @keyframes dustPuff { 0% {opacity:.9; transform:translate(-50%,-50%) scale(.4);} 100% {opacity:0; transform:translate(calc(-50% + var(--dx)), calc(-50% + var(--dy))) scale(1.4);} }
        .fx-spark { position: fixed; font-size: 14px; z-index: 9391; pointer-events: none; transform: translate(-50%, -50%); animation: sparkPop .9s ease-out forwards; }
        @keyframes sparkPop { 0% {opacity:0; transform:translate(-50%,-50%) scale(.2) rotate(0deg);} 40% {opacity:1;} 100% {opacity:0; transform:translate(calc(-50% + var(--dx)), calc(-50% + var(--dy))) scale(1.2) rotate(160deg);} }
        #zilla.spawn-ground .zflip { animation: riseUp .9s cubic-bezier(.2,.9,.3,1.1); }
        @keyframes riseUp { 0% {transform:translateY(46px) scale(.85); opacity:0;} 40% {opacity:1;} 100% {transform:translateY(0) scale(1); opacity:1;} }
        #zilla.spawn-magic .zflip { animation: magicIn .9s ease-out; }
        @keyframes magicIn { 0% {transform:scale(0) rotate(-540deg); opacity:0; filter:drop-shadow(0 0 18px #a78bfa);} 60% {opacity:1; filter:drop-shadow(0 0 14px #a78bfa);} 100% {transform:scale(1) rotate(0deg); opacity:1; filter:none;} }
        #zilla.spawn-fall .zflip { animation: fallIn .7s cubic-bezier(.3,1.6,.5,1); }
        @keyframes fallIn { 0% {transform:translateY(-160px) rotate(360deg); opacity:0;} 30% {opacity:1;} 100% {transform:translateY(0) rotate(0deg); opacity:1;} }
    </style>
</head>
<body>
    <div id="graph"></div>
    <div id="toast"></div>
    <div id="tooltip"></div>
    <button id="zillaBtn" title="...">🦖</button>
    __DATA_SOURCE__
    <script>
        var gd = document.getElementById('graph');
        var tst = document.getElementById('toast');
        var tip = document.getElementById('tooltip');
        var currentData = null;
        var lastDataRev = null;
        var lastRev = null;
        var labelColor = "#37474f";
        var mx = 0, my = 0;
        var tipVisible = false, tipHovered = false, follow = false;
        var pinnedCards = {};        // key -> DOM-элемент закреплённой карточки
        var currentTipMarker = null; // маркер, который сейчас показан в ховер-тултипе
        var hideTimer = null;
        var API_PORT = __API_PORT__;
        var API_TOKEN = __API_TOKEN__;
        var panels = {};
        var panelSeq = 0;
        var zTop = 10001;
        var LSTR = __LSTR__;
        var mapThemes = __MAP_THEMES__;

        var layout = {
            title: __TITLE__,
            margin: {l: 0, r: 0, t: 45, b: 0},
            showlegend: false,
            hovermode: 'closest',
            annotations: [{ xref: 'paper', yref: 'paper', x: 0.01, y: 0.02,
                showarrow: false, xanchor: 'left', yanchor: 'bottom',
                text: LSTR.annot, font: {size: 11, color: '#78909c'} }],
            geo: { showland: true, landcolor: "#fcfaf2", showcountries: true,
                   countrycolor: "#90a4ae", showocean: true, oceancolor: "#e0f2f1" }
        };
        Plotly.newPlot(gd, [], layout);

        function showToast(msg) { tst.textContent = msg; tst.style.display = 'block'; setTimeout(function () { tst.style.display = 'none'; }, 1500); }
        function apiGet() { return fetch('http://127.0.0.1:' + API_PORT + '/api').then(function (r) { return r.json(); }); }
        function apiPost(obj) { obj.token = API_TOKEN; return fetch('http://127.0.0.1:' + API_PORT + '/api', { method: 'POST', body: JSON.stringify(obj) }).catch(function () {}); }
        function applyTheme(name) {
            var th = mapThemes[name] || mapThemes.light;
            document.body.style.background = th.body;
            layout.geo.bgcolor = th.body; layout.geo.landcolor = th.land;
            layout.geo.oceancolor = th.ocean; layout.geo.countrycolor = th.country;
            layout.font = {color: th.title, family: '"Segoe UI", system-ui, Arial, sans-serif'};
            if (layout.annotations && layout.annotations.length) layout.annotations[0].font.color = th.annot;
            labelColor = th.label;
        }
        function esc(s) { return String(s).replace(/[&<>"']/g, function (c) { return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
        function pluralNodes(n) {
            if (LSTR.lang === 'ru') {
                var m10 = n % 10, m100 = n % 100;
                if (m10 === 1 && m100 !== 11) return n + ' узел';
                if (m10 >= 2 && m10 <= 4 && (m100 < 10 || m100 >= 20)) return n + ' узла';
                return n + ' узлов';
            }
            return n + (n === 1 ? ' node' : ' nodes');
        }
        function latColor(ms) { if (ms == null) return '#0288d1'; if (ms < 50) return '#2e7d32'; if (ms < 150) return '#f57f17'; return '#c62828'; }
        function fmtMs(ms, bound) { return (bound ? '<' : '') + Math.round(ms) + ' ' + LSTR.ms; }
        function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
        function srcLabel(it) {
            var map = {
                'host': LSTR.src_host,
                'learned': LSTR.src_learned,
                'whois': LSTR.src_whois,
                'near': LSTR.src_near,
                'ixp': LSTR.src_ixp,
                'facility': LSTR.src_facility,
                'peeringdb': LSTR.src_peeringdb,
                'rtt_override': LSTR.src_rtt
    };
            return map[it.src] || LSTR.src_geo;
}
        function confBadge(it) {
            // consensus confidence from GeoTraceApp._eff()'s weighted-vote city resolution —
            // how much of the total signal weight (PTR/whois/IXP/GeoIP/near-inherit) backs
            // the winning answer, not just which signal happened to win
            if (it.conf == null) return '';
            var pct = Math.round(it.conf * 100);
            var color = it.conf >= 0.8 ? '#66bb6a' : (it.conf >= 0.6 ? '#fbbf24' : '#ef5350');
            var note = it.conf_note ? ' title="' + esc(it.conf_note) + '"' : '';
            return ' · <span class="tt-conf" style="color:' + color + '"' + note + '>' + pct + '%</span>';
        }
        function buildTooltip(m) {
            var first = m.items[0];
            var head = esc(first.city);
            if (!first.user && first.country && first.country !== 'Unknown') head += ', ' + esc(first.country);
            var multiCity = m.items.some(function (x) { return x.city !== first.city; });
            var html = '<div class="tt-header"><span class="tt-city">' + head + '</span>';
            if (m.items.length > 1) html += '<span class="tt-count">' + pluralNodes(m.items.length) + '</span>';
            html += '<button class="tt-pin" title="' + LSTR.pin + '">📌</button>';
            html += '</div>';
            m.items.forEach(function (it, i) {
                var prev = i > 0 ? m.items[i - 1] : null;
                if (prev && it.asn && prev.asn && it.asn !== prev.asn) html += '<div class="tt-seam">' + LSTR.seam + '</div>';
                var badge = it.user ? '#2e7d32' : (it.target ? '#d32f2f' : (it.sus ? '#78909c' : (it.anycast ? '#a78bfa' : latColor(it.ms))));
                html += '<div class="tt-row tt-ping' + (i % 2 ? ' tt-alt' : '') +
                        '" data-ip="' + esc(it.ip) + '" data-city="' + esc(it.city) +
                        '" title="' + LSTR.footer + '"><div class="tt-main">' +
                        '<div class="tt-line1">' +
                        '<span class="tt-hop" style="background:' + badge + '">' + (it.target ? '🎯' : it.hop) + '</span>' +
                        '<span class="tt-ip">' + esc(it.ip) + '</span>' +
                        (it.ms != null ? '<span class="tt-ms">' + fmtMs(it.ms, it.ms_bound) + '</span>' : '') +
                        '</div>' +
                        '<div class="tt-org">' +
                        (multiCity ? esc(it.city) + ' · ' : '') +
                        (it.org ? esc(it.org) + (it.asn ? ' · ' + esc(it.asn) : '') + ' · ' : '') +
                        srcLabel(it) + confBadge(it) +
                        (it.role === 'transit' ? ' · ' + LSTR.role_transit :
                         (it.role === 'edge' ? ' · ' + LSTR.role_edge : '')) + '</div>' +
                        (it.anycast ? '<div class="tt-anycast">' + LSTR.anycast + '</div>' :
                         (it.sus ? '<div class="tt-sus">' + LSTR.sus + '</div>' : '')) +
                        (it.target ? '<div class="tt-target">' + LSTR.target + '</div>' : '') +
                     '</div></div>';
            });
            if (API_PORT) html += '<div class="tt-footer">' + LSTR.footer + '</div>';
            return html;
        }
        function positionTip() {
            var pad = 14, margin = 8;
            var r = tip.getBoundingClientRect();
            var x = mx + pad, y = my + pad;
            if (x + r.width > window.innerWidth - margin) x = mx - r.width - pad;
            if (x < margin) x = margin;
            if (y + r.height > window.innerHeight - margin) y = my - r.height - pad;
            if (y < margin) y = margin;
            tip.style.left = x + 'px'; tip.style.top = y + 'px';
        }
        function scheduleHide() { clearTimeout(hideTimer); hideTimer = setTimeout(function () { if (!tipHovered) { tip.classList.remove('show'); tipVisible = false; } }, 200); }

        // пакеты на отдельном canvas: оптимизированный режим (routeDirty + пауза при pan/zoom)
var fxCanvas = document.createElement('canvas');
fxCanvas.style.cssText = 'position:absolute;left:0;top:0;pointer-events:none;z-index:5;will-change:transform;';
gd.style.position = 'relative';
gd.appendChild(fxCanvas);
var fxCtx = fxCanvas.getContext('2d');

var routePath = null, routeLen = 0, routePts = [], routeBreaks = [], fxOffset = 0;
var fxRunning = false, fxLast = 0;
var fxInteracting = false;
var fxInteractTimer = null;
var routeDirty = true;
var FX_FPS = 20, FX_SPEED = 70;
var routeStep = 6;

function sizeFx() {
    var dpr = Math.min(1.25, window.devicePixelRatio || 1);
    var r = gd.getBoundingClientRect();
    var w = Math.round(r.width * dpr), h = Math.round(r.height * dpr);

    if (fxCanvas.width !== w || fxCanvas.height !== h) {
        fxCanvas.width = w;
        fxCanvas.height = h;
        fxCanvas.style.width = r.width + 'px';
        fxCanvas.style.height = r.height + 'px';
    }

    fxCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function markRouteDirty() {
    routeDirty = true;
}

function findRoute() {
    var lines = Array.prototype.slice.call(gd.querySelectorAll('.js-line'));
    routePath = null;

    for (var i = lines.length - 1; i >= 0; i--) {
        var stroke = (lines[i].getAttribute('stroke') || lines[i].style.stroke || '').toLowerCase();
        if (stroke.indexOf('#d32f2f') !== -1 || stroke.indexOf('rgb(211') !== -1) {
            routePath = lines[i];
            break;
        }
    }

    if (!routePath) {
        routePath = lines[lines.length - 1] || null;
    }

    routeLen = 0;
    routePts = [];
    routeBreaks = [];

    if (!routePath) return;

    try {
        routeLen = routePath.getTotalLength();
    } catch (e) {
        routeLen = 0;
    }

    if (!routeLen || routeLen < 40) {
        routePath = null;
        routeLen = 0;
        return;
    }

    routeStep = Math.max(8, routeLen / 80);
    var n = Math.max(2, Math.floor(routeLen / routeStep));

    var px = null, py = null;

    for (var j = 0; j <= n; j++) {
        var p = routePath.getPointAtLength(Math.min(routeLen, j * routeStep));
        var k = routePts.length / 2;

        if (px !== null && Math.hypot(p.x - px, p.y - py) > routeStep * 4) {
            routeBreaks[k] = true;
        }

        routePts.push(p.x, p.y);
        px = p.x;
        py = p.y;
    }
}

function pointAt(d) {
    if (!routePts.length || !routeStep) return { x: 0, y: 0 };

    var idx = d / routeStep;
    var i0 = Math.floor(idx);
    var i1 = Math.min(routePts.length / 2 - 1, i0 + 1);

    if (routeBreaks[i1]) {
        return { x: routePts[i1 * 2], y: routePts[i1 * 2 + 1] };
    }

    var t = idx - i0;

    return {
        x: routePts[i0 * 2] + (routePts[i1 * 2] - routePts[i0 * 2]) * t,
        y: routePts[i0 * 2 + 1] + (routePts[i1 * 2 + 1] - routePts[i0 * 2 + 1]) * t
    };
}

function fxInteractionStart() {
    fxInteracting = true;

    if (fxCtx) {
        fxCtx.clearRect(0, 0, fxCanvas.width, fxCanvas.height);
    }

    clearTimeout(fxInteractTimer);

    fxInteractTimer = setTimeout(function () {
        fxInteracting = false;
        markRouteDirty();
    }, 200);
}

function fxInteractionEnd() {
    clearTimeout(fxInteractTimer);

    fxInteractTimer = setTimeout(function () {
        fxInteracting = false;
        markRouteDirty();

        if (!fxRunning && !document.hidden && !document.body.classList.contains('idle')) {
            fxStart();
        }
    }, 120);
}

function fxStart() {
    if (fxRunning || document.hidden || fxInteracting) return;
    if (document.body.classList.contains('idle')) return;

    sizeFx();

    if (routeDirty || !routePath || !routePath.isConnected) {
        findRoute();
        routeDirty = false;
    }

    if (!routePath) return;

    fxRunning = true;
    fxLast = 0;
    requestAnimationFrame(fxTick);
}

function fxStop() {
    fxRunning = false;

    if (fxCtx) {
        fxCtx.clearRect(0, 0, fxCanvas.width, fxCanvas.height);
    }
}

function fxTick(ts) {
    if (!fxRunning) return;
    requestAnimationFrame(fxTick);

    if (fxInteracting) return;

    if (ts - fxLast < 1000 / FX_FPS) return;

    var dt = fxLast ? Math.min(0.1, (ts - fxLast) / 1000) : 0;
    fxLast = ts;

    if (routePath && !routePath.isConnected) {
        routeDirty = true;
    }

    if (routeDirty) {
        findRoute();
        routeDirty = false;

        if (!routePath || !routeLen) {
            if (fxCtx) fxCtx.clearRect(0, 0, fxCanvas.width, fxCanvas.height);
            return;
        }
    }

    if (!routePath || !routeLen) {
        if (fxCtx) fxCtx.clearRect(0, 0, fxCanvas.width, fxCanvas.height);
        return;
    }

    if (fxCtx) fxCtx.clearRect(0, 0, fxCanvas.width, fxCanvas.height);

    var m = routePath.getScreenCTM();
    if (!m) return;

    var rect = gd.getBoundingClientRect();

    fxOffset = (fxOffset + dt * FX_SPEED) % routeLen;

    for (var i = 0; i < 5; i++) {
        var p = pointAt((fxOffset + routeLen / 5 * i) % routeLen);

        var sx = m.a * p.x + m.c * p.y + m.e - rect.left;
        var sy = m.b * p.x + m.d * p.y + m.f - rect.top;

        fxCtx.beginPath();
        fxCtx.arc(sx, sy, 4.5, 0, 6.2832);
        fxCtx.fillStyle = '#d32f2f';
        fxCtx.fill();
        fxCtx.lineWidth = 1;
        fxCtx.strokeStyle = '#ffffff';
        fxCtx.stroke();
    }
}

var rsT = null;

function relayoutFx() {
    clearTimeout(rsT);

    rsT = setTimeout(function () {
        sizeFx();
        markRouteDirty();
    }, 250);
}

window.addEventListener('resize', relayoutFx);

gd.on('plotly_relayout', function () {
    relayoutFx();
    fxInteractionEnd();
});

gd.on('plotly_relayouting', function () {
    fxInteractionStart();
    markRouteDirty();
});

gd.addEventListener('mousedown', fxInteractionStart);
gd.addEventListener('wheel', fxInteractionStart, { passive: true });
gd.addEventListener('touchstart', fxInteractionStart, { passive: true });



        function makeDraggable(el, handle) {
            handle.addEventListener('mousedown', function (e) {
                if (e.target.closest('.pp-btn')) return;
                e.preventDefault();
                var r = el.getBoundingClientRect();
                var dx = e.clientX - r.left, dy = e.clientY - r.top;
                function mv(ev) {
                    var x = ev.clientX - dx, y = ev.clientY - dy;
                    x = Math.max(4, Math.min(x, window.innerWidth - 80));
                    y = Math.max(4, Math.min(y, window.innerHeight - 40));
                    el.style.left = x + 'px'; el.style.top = y + 'px';
                }
                function up() { document.removeEventListener('mousemove', mv); document.removeEventListener('mouseup', up); }
                document.addEventListener('mousemove', mv); document.addEventListener('mouseup', up);
            });
        }
        function openPing(ip, city) {
            if (!API_PORT) { showToast(LSTR.zilla_live); return; }
            if (panels[ip]) { panels[ip].el.style.zIndex = ++zTop; return; }
            apiPost({action: 'start', ip: ip});
            var el = document.createElement('div');
            el.className = 'ping-panel';
            var off = (panelSeq++ % 6);
            el.style.left = (90 + off * 46) + 'px'; el.style.top = (70 + off * 36) + 'px';
            el.style.zIndex = ++zTop;
            el.innerHTML =
                '<div class="pp-header">' +
                '<span class="pp-title">📡 ' + esc(ip) + (city ? ' · ' + esc(city) : '') + '</span>' +
                '<button class="pp-btn stop" data-act="stop" title="' + LSTR.stop + '">⏹</button>' +
                '<button class="pp-btn" data-act="copy" title="' + LSTR.copyout + '">⧉</button>' +
                '<button class="pp-btn" data-act="close" title="' + LSTR.close + '">✕</button>' +
                '</div>' +
                '<div class="pp-stats">' + LSTR.starting + '</div>' +
                '<div class="pp-body"><div class="pp-line">' + LSTR.waiting + '</div></div>';
            document.body.appendChild(el);
            var p = { ip: ip, el: el, body: el.querySelector('.pp-body'), stats: el.querySelector('.pp-stats'),
                      stopBtn: el.querySelector('[data-act="stop"]'), running: true, lastLines: [] };
            panels[ip] = p;
            el.addEventListener('mousedown', function () { el.style.zIndex = ++zTop; });
            makeDraggable(el, el.querySelector('.pp-header'));
            p.stopBtn.onclick = function () { apiPost({action: p.running ? 'stop' : 'start', ip: ip}); };
            el.querySelector('[data-act="copy"]').onclick = function () { navigator.clipboard.writeText(p.lastLines.join('\\n')); showToast(LSTR.copied); };
            el.querySelector('[data-act="close"]').onclick = function () { apiPost({action: 'stop', ip: ip}); el.remove(); delete panels[ip]; };
        }
        function updatePanels(pings) {
            Object.keys(panels).forEach(function (ip) {
                var p = panels[ip]; var d = pings[ip];
                if (!d) { p.stats.textContent = LSTR.nolink; return; }
                p.running = d.running; p.lastLines = d.lines;
                p.stats.textContent = (d.running ? '● ' : '○ ') + d.stats;
                p.stopBtn.textContent = d.running ? '⏹' : '▶';
                p.stopBtn.title = d.running ? LSTR.stop : LSTR.again;
                var nearBottom = p.body.scrollTop + p.body.clientHeight >= p.body.scrollHeight - 24;
                p.body.innerHTML = d.lines.length
                    ? d.lines.map(function (ln) { return '<div class="pp-line">' + esc(ln) + '</div>'; }).join('')
                    : '<div class="pp-line">' + LSTR.waiting + '</div>';
                if (nearBottom) p.body.scrollTop = p.body.scrollHeight;
            });
        }
        setInterval(function () { if (!API_PORT || !Object.keys(panels).length) return; apiGet().then(function (d) { updatePanels(d.pings || {}); }).catch(function () {}); }, 800);

        var zBtn = document.getElementById('zillaBtn');
        var Z = null;
        function markerScreenPoints() {
            var out = [];
            var nodes = gd.querySelectorAll('.points .point, g.points path.point, path.point, .point');
            for (var i = 0; i < nodes.length; i++) {
                var r = nodes[i].getBoundingClientRect();
                if (r.width === 0 && r.height === 0) continue;
                out.push({x: r.left + r.width / 2, y: r.top + r.height / 2, el: nodes[i]});
            }
            return out;
        }
        function randomViewportPoints() {
            var out = [];
            for (var i = 0; i < 6; i++) out.push({x: 60 + Math.random() * (window.innerWidth - 120), y: 90 + Math.random() * (window.innerHeight - 170), el: null});
            return out;
        }
        function stopZilla() { if (!Z) return; Z.active = false; if (Z.el) Z.el.remove(); Z.fires.forEach(function (f) { f.remove(); }); Z.chars.forEach(function (c) { c.el.setAttribute('fill', c.fill); }); Z = null; zBtn.classList.remove('active'); }
        function spawnFx(x, y, mode) {
            function puff(cls, emoji, dx, dy, delay) {
                var d = document.createElement('div');
                d.className = cls; d.textContent = emoji;
                d.style.left = x + 'px'; d.style.top = y + 'px';
                d.style.setProperty('--dx', dx + 'px'); d.style.setProperty('--dy', dy + 'px');
                if (delay) d.style.animationDelay = delay + 'ms';
                document.body.appendChild(d);
                setTimeout(function () { d.remove(); }, 1700);
            }
            if (mode === 'ground') {
                var h = document.createElement('div'); h.className = 'fx-hole';
                h.style.left = x + 'px'; h.style.top = (y + 4) + 'px';
                document.body.appendChild(h); setTimeout(function () { h.remove(); }, 2500);
                puff('fx-dust', '💨', -34, -6, 150); puff('fx-dust', '💨', 34, -6, 250);
            } else if (mode === 'magic') {
                for (var i = 0; i < 7; i++) { var a = (Math.PI * 2 / 7) * i; puff('fx-spark', '✨', Math.cos(a) * 46, Math.sin(a) * 40, i * 60); }
            } else { puff('fx-dust', '💨', -30, 2, 550); puff('fx-dust', '💨', 30, 2, 600); }
        }
        function startZilla() {
            if (Z) return;
            var modes = ['ground', 'magic', 'fall'];
            var mode = modes[Math.floor(Math.random() * modes.length)];
            var sx = window.innerWidth / 2 + (Math.random() * 200 - 100);
            var sy = window.innerHeight / 2 + (Math.random() * 140 - 70);
            var el = document.createElement('div');
            el.id = 'zilla'; el.className = 'spawn-' + mode;
            el.style.left = sx + 'px'; el.style.top = sy + 'px';
            el.innerHTML = '<div class="zflip"><span class="flame">🔥</span><span class="zbody">🦖</span></div><span class="roar">RAWR!</span>';
            document.body.appendChild(el);
            Z = {active: true, el: el, flip: el.querySelector('.zflip'), fires: [], chars: [], lastFace: 1, x: sx, y: sy};
            zBtn.classList.add('active');
            spawnFx(sx, sy, mode);
            zillaLoop();
        }
        function roar() { if (!Z) return; Z.el.classList.remove('roaring'); void Z.el.offsetWidth; Z.el.classList.add('roaring'); setTimeout(function () { if (Z) Z.el.classList.remove('roaring'); }, 1000); }
        function smallHop(from, to) {
            return new Promise(function (res) {
                var face = (to.x < from.x) ? 1 : -1;
                Z.lastFace = face;
                var dist = Math.hypot(to.x - from.x, to.y - from.y);
                var dur = Math.max(180, Math.min(320, dist * 3));
                var t0 = performance.now();
                function frame(t) {
                    if (!Z || !Z.active) return res();
                    var k = Math.min(1, (t - t0) / dur);
                    var x = from.x + (to.x - from.x) * k;
                    var y = from.y + (to.y - from.y) * k - Math.sin(Math.PI * k) * 24;
                    Z.el.style.left = x + 'px'; Z.el.style.top = y + 'px';
                    Z.flip.style.transform = 'scaleX(' + face + ') rotate(' + (face * Math.sin(Math.PI * k) * 8) + 'deg)';
                    if (k < 1) requestAnimationFrame(frame);
                    else { Z.flip.style.transform = 'scaleX(' + face + ')'; Z.x = to.x; Z.y = to.y; res(); }
                }
                requestAnimationFrame(frame);
            });
        }
        async function hopAlong(from, to) {
            var dist = Math.hypot(to.x - from.x, to.y - from.y);
            var n = Math.max(1, Math.round(dist / 85));
            var prev = from;
            for (var i = 1; i <= n && Z && Z.active; i++) {
                var pt = {x: from.x + (to.x - from.x) * i / n, y: from.y + (to.y - from.y) * i / n};
                await smallHop(prev, pt); prev = pt;
            }
        }
        function breatheAndIgnite(pt) {
            return new Promise(function (res) {
                if (!Z || !Z.active) return res();
                Z.flip.style.transform = 'scaleX(' + Z.lastFace + ') rotate(' + (Z.lastFace * -12) + 'deg)';
                Z.el.classList.add('breathe');
                setTimeout(function () {
                    if (!Z || !Z.active) return res();
                    Z.el.classList.remove('breathe');
                    var f = document.createElement('div');
                    f.className = 'fire-spot'; f.textContent = '🔥';
                    f.style.left = pt.x + 'px'; f.style.top = pt.y + 'px';
                    document.body.appendChild(f); Z.fires.push(f);
                    if (pt.el && !pt.el.__charred) { pt.el.__charred = true; Z.chars.push({el: pt.el, fill: pt.el.getAttribute('fill')}); pt.el.setAttribute('fill', '#4a4a4a'); }
                    document.body.classList.add('quake');
                    setTimeout(function () { document.body.classList.remove('quake'); }, 350);
                    setTimeout(res, 250);
                }, 550);
            });
        }
        async function zillaLoop() {
            try {
                await sleep(950);
                while (Z && Z.active) {
                    var pts = markerScreenPoints();
                    if (!pts.length) { console.warn('[zilla] markers not found, random mode'); pts = randomViewportPoints(); }
                    var cur = {x: Z.x, y: Z.y};
                    roar();
                    var order = pts.slice().sort(function () { return Math.random() - .5; });
                    for (var i = 0; i < order.length && Z && Z.active; i++) {
                        await hopAlong(cur, order[i]);
                        if (!Z || !Z.active) return;
                        await breatheAndIgnite(order[i]);
                        if (!Z || !Z.active) return;
                        cur = {x: Z.x, y: Z.y};
                    }
                    if (Z && Z.active) roar();
                }
            } catch (e) { console.error('[zilla]', e); showToast('🦖 error: ' + e.message); }
        }
        zBtn.addEventListener('click', function () {
            try { if (Z) { stopZilla(); showToast(LSTR.zilla_off); } else { startZilla(); showToast(LSTR.zilla_on); } }
            catch (e) { console.error('[zilla]', e); showToast('🦖 error: ' + e.message); }
        });

        var lastWakeTime = 0;
        document.addEventListener('mousemove', function (e) {
            mx = e.clientX; my = e.clientY;
            if (tipVisible && follow && !tipHovered) positionTip();
            var now = Date.now();
            if (now - lastWakeTime > 200) { lastWakeTime = now; wake(); }
        });
        tip.addEventListener('mouseenter', function () { tipHovered = true; clearTimeout(hideTimer); });
        tip.addEventListener('mouseleave', function () { tipHovered = false; scheduleHide(); });
// ---------- множественные закрепляемые карточки узлов ----------
        function tipKey(m) {
    return m.items.map(function (it) { return it.ip; }).join(',');
}

        function spawnPinnedCard(m) {
        var key = tipKey(m);
                if (pinnedCards[key]) {                 // уже закреплён — просто на передний план
        pinnedCards[key].style.zIndex = ++zTop;
        return pinnedCards[key];
    }
        var r = tip.getBoundingClientRect();
        var el = document.createElement('div');
            el.className = 'pinned-tip';
            el.setAttribute('data-key', key);
            el.innerHTML = buildTooltip(m);
        var pin = el.querySelector('.tt-pin');
                if (pin) { pin.classList.add('on'); pin.title = LSTR.unpin; }
            el.style.left = Math.max(4, Math.min(r.left, window.innerWidth - r.width - 4)) + 'px';
            el.style.top = Math.max(4, Math.min(r.top, window.innerHeight - r.height - 4)) + 'px';
            el.style.zIndex = ++zTop;
    document.body.appendChild(el);
    pinnedCards[key] = el;
    makeTipDraggable(el);
    return el;
}

        function makeTipDraggable(el) {
    el.addEventListener('mousedown', function () { el.style.zIndex = ++zTop; });
        var handle = el.querySelector('.tt-header');
                if (!handle) return;
    handle.addEventListener('mousedown', function (e) {
                if (e.target.closest('.tt-pin')) return;
        e.preventDefault();
        var r = el.getBoundingClientRect();
        var dx = e.clientX - r.left, dy = e.clientY - r.top;
        function mv(ev) {
            var x = Math.max(4, Math.min(ev.clientX - dx, window.innerWidth - 80));
            var y = Math.max(4, Math.min(ev.clientY - dy, window.innerHeight - 40));
            el.style.left = x + 'px'; el.style.top = y + 'px';
        }
        function up() { document.removeEventListener('mousemove', mv); document.removeEventListener('mouseup', up); }
        document.addEventListener('mousemove', mv);
        document.addEventListener('mouseup', up);
    });
}

// единый делегированный обработчик: 📌 и строки пинга во ВСЕХ карточках и в ховер-тултипе
document.addEventListener('click', function (e) {
        var pin = e.target.closest('.tt-pin');
                if (pin) {
        var card = pin.closest('.pinned-tip');
                if (card) {                                   // 📌 на закреплённой карточке = закрыть её
            delete pinnedCards[card.getAttribute('data-key')];
            card.remove();
        } else if (pin.closest('#tooltip') && currentTipMarker) {
            spawnPinnedCard(currentTipMarker);        // закрепить текущий узел
        }
        return;
    }
        var row = e.target.closest('.tt-row');
                if (!row) return;
        var ip = row.getAttribute('data-ip');
                if (ip) openPing(ip, row.getAttribute('data-city') || '');
});
        gd.on('plotly_hover', function (data) {
                var pt = data.points && data.points[0];
    if (!pt || pt.pointNumber == null || !currentData) return;
                var m = currentData.markers[pt.pointNumber];
    if (!m) return;
    currentTipMarker = m;   // запоминаем маркер — нужно кнопке 📌
    clearTimeout(hideTimer);
    tip.innerHTML = buildTooltip(m);
    tip.classList.add('show'); tipVisible = true; follow = true;
    positionTip();
});
        gd.on('plotly_unhover', function () { follow = false; scheduleHide(); });

        async function update() {
            try {
                var base = document.getElementById('data-script');
                if (base) {
                    base.remove();
                    var newScript = document.createElement('script');
                    newScript.id = 'data-script';
                    newScript.src = 'desktop_trace_data.js?t=' + new Date().getTime();
                    await new Promise(function (resolve, reject) { newScript.onload = resolve; newScript.onerror = reject; document.body.appendChild(newScript); });
                }
                var d = window.traceData;
                if (!d) return;
                if (lastRev !== null && d.map_rev !== lastRev) { window.location.reload(); return; }
                lastRev = d.map_rev;
                if (lastDataRev !== null && d.data_rev === lastDataRev) return;
                lastDataRev = d.data_rev; currentData = d;
                if (!!d.final !== traceFinal) { traceFinal = !!d.final; if (traceFinal) scheduleIdle(); else document.body.classList.remove('idle'); }
                pollDelay = traceFinal ? 5000 : 1500;
                applyTheme(d.theme || 'light');
                var traces = [];
                if (d.line_lon.length > 1) {
                    traces.push({type: 'scattergeo', mode: 'lines', lon: d.line_lon, lat: d.line_lat, line: {width: 4, color: 'rgba(255,10,10,0.35)'}, hoverinfo: 'skip'});
                }
                if (d.markers.length > 0) {
                    traces.push({
                        type: 'scattergeo', mode: 'markers+text',
                        lon: d.markers.map(function(m){return m.lon;}),
                        lat: d.markers.map(function(m){return m.lat;}),
                        text: d.markers.map(function(m){return m.tgt ? '🎯' : m.hop;}),
                        textposition: d.markers.map(function(m){return m.tp || 'top center';}),
                        textfont: {color: labelColor, size: 10},
                        marker: { size: d.markers.map(function(m){return m.size;}), color: d.markers.map(function(m){return m.color;}), line: {width: 1.5, color: 'white'} },
                        hoverinfo: 'none',
                        customdata: d.markers.map(function(m){return m.copy;})
                    });
                }
                Plotly.react(gd, traces, layout).then(function () { markRouteDirty(); fxStart(); });
            } catch (e) { console.error("Map update error:", e); }
        }
        gd.on('plotly_click', function (data) {
            if (data.points && data.points[0] && data.points[0].customdata)
                navigator.clipboard.writeText(data.points[0].customdata).then(function () { showToast(LSTR.copied); });
        });

        var autopoll = __AUTOPOLL__ === 1;
        var pollDelay = 1500;
        var traceFinal = false;
        var idleTimer = null;
        function scheduleIdle() {
            clearTimeout(idleTimer);
            idleTimer = setTimeout(function () {
                document.body.classList.add('idle');
                fxStop();
            }, 2500);
        }
        function wake() {
            if (!traceFinal) return;
            if (!document.body.classList.contains('idle')) {
                clearTimeout(idleTimer);
                scheduleIdle();
                return;
            }
            document.body.classList.remove('idle');
            fxStart();
            scheduleIdle();
        }
        document.addEventListener('keydown', wake);
        document.addEventListener('visibilitychange', function () {
            if (document.hidden) fxStop();
            else if (!document.body.classList.contains('idle')) fxStart();
        });
        function loop() { if (!autopoll) return; setTimeout(function () { update().then(loop, loop); }, pollDelay); }
        update().then(loop, loop);
    </script>
</body>
</html>"""
        if inline_payload is not None:
            data_source = f"<script>window.traceData = {inline_payload};</script>"
            autopoll = "0"
        else:
            data_source = '<script id="data-script" src="desktop_trace_data.js"></script>'
            autopoll = "1"
        html = html.replace("__DATA_SOURCE__", data_source)
        html = html.replace("__AUTOPOLL__", autopoll)
        html = html.replace("__API_PORT__", str(port))
        html = html.replace("__API_TOKEN__", json.dumps(token))
        html = html.replace("__LSTR__", json.dumps(lstr, ensure_ascii=False))
        html = html.replace("__TITLE__", json.dumps(L["m_title"].format(title), ensure_ascii=False))
        html = html.replace("__MAP_THEMES__", json.dumps(MAP_THEMES, ensure_ascii=False))
        return html

    def _build_payload(self, final: bool) -> dict:
        sorted_hops = self._sorted_hops()
        sus, consistent = self._audit_sus()
        eff = {h.ip: self._eff(h) for h in sorted_hops}

        line_lon = [eff[h.ip][3] for h in sorted_hops]
        line_lat = [eff[h.ip][2] for h in sorted_hops]

        groups = {}
        for h in sorted_hops:
            c, ct, la, lo, src = eff[h.ip]
            groups.setdefault((h.hop == 0, c.strip().lower()), []).append([h, c, ct, la, lo, src])

        clusters = []
        for (is_user, _city), members in groups.items():
            lat_c = sum(m[3] for m in members) / len(members)
            lon_c = sum(m[4] for m in members) / len(members)
            if not is_user:
                for cl in clusters:
                    if not cl["user"] and haversine(lat_c, lon_c, cl["lat"], cl["lon"]) < 40:
                        cl["members"].extend(members)
                        n = len(cl["members"])
                        cl["lat"] = sum(m[3] for m in cl["members"]) / n
                        cl["lon"] = sum(m[4] for m in cl["members"]) / n
                        break
                else:
                    clusters.append({"user": is_user, "members": members, "lat": lat_c, "lon": lon_c})
            else:
                clusters.append({"user": True, "members": members, "lat": lat_c, "lon": lon_c})

        clusters.sort(key=lambda cl: min(m[0].hop for m in cl["members"]))

        for i, cl in enumerate(clusters):
            cl["tp"] = "top center"
            for j in range(i):
                if haversine(cl["lat"], cl["lon"], clusters[j]["lat"], clusters[j]["lon"]) < 40:
                    cl["tp"] = "bottom center" if clusters[j]["tp"] == "top center" else "top center"

        markers = []
        for cl in clusters:
            hops = sorted((m[0] for m in cl["members"]), key=lambda h: h.hop)
            is_user = cl["user"]
            count = len(hops)
            unit = self.tr("ms")
            copy_lines = []
            for h in hops:
                c, ct, _, _, src = eff[h.ip]
                line = f"{h.hop} · {c}, {ct} · {h.ip}"
                if h.ms is not None:
                    line += f" · {'<' if h.ms_bound else ''}{h.ms:.0f} {unit}"
                if h.org:
                    line += f" · {h.org} ({h.asn})"
                src_sym = {"ixp": "⚡", "facility": "🏢", "host": "📇", "learned": "🧠", "whois": "📜", "near": "📍", "rtt_override": "🧲", "peeringdb": "🏢"}.get(src, "🛰")
                if h.target:
                    line += " · 🎯"
                    line += f" · {src_sym}"
                conf = self._conf(h, sus, consistent)
                if conf < 0.6:
                    line += f" · {conf:.0%}"
                if h.anycast:
                    line += " · 🌐"
                if h.ip in sus:
                    line += " · ⚠"
                copy_lines.append(line)

            markers.append({
                "lon": cl["lon"], "lat": cl["lat"],
                "tgt": all(h.target for h in hops),
                "color": (
                         "#78909c" if any(h.ip in sus for h in hops) else
                         "#a78bfa" if all(h.anycast for h in hops) else
                         "#d32f2f" if all(h.target for h in hops) else
                         "#2e7d32" if is_user else "#0288d1"
    ),
                "hop": ",".join(str(h.hop) for h in hops),
                "tp": cl["tp"],
                "size": (14 if is_user else 12) + min(count - 1, 4) * 2,
                "items": [
                    {"hop": h.hop, "ip": h.ip, "city": eff[h.ip][0], "country": eff[h.ip][1],
                     "user": h.hop == 0, "ms": h.ms, "ms_bound": h.ms_bound, "asn": h.asn, "org": h.org,
                     "src": eff[h.ip][4], "conf": self._conf(h, sus, consistent),
                     "conf_note": self._conf_note(h, sus, consistent, eff[h.ip][4]), "role": h.role,
                     "sus": h.ip in sus, "anycast": h.anycast, "recovered": h.recovered, "target": h.target}
                    for h in hops
                ],
                "copy": "\n────────────\n".join(copy_lines),
            })

        return {"line_lon": line_lon, "line_lat": line_lat, "markers": markers,
                "final": final, "theme": self.theme, "map_rev": self.map_rev}

    def _update_map(self, final: bool = False) -> None:
        if not self.hops:
            return
        payload = self._build_payload(final)
        self.data_rev += 1
        payload["data_rev"] = self.data_rev
        js_file = CONFIG["data_js_file"]
        with open(js_file, "w", encoding="utf-8") as f:
            f.write(f"window.traceData = {json.dumps(payload, ensure_ascii=False)};")
        if not self.map_opened:
            with open(CONFIG["map_file"], "w", encoding="utf-8") as f:
                f.write(self._render_map_html(self.entry.get().strip()))
            self.map_opened = True
            os.startfile(CONFIG["map_file"])

    # ------------------------------------------------------------- misc
    def _copy_log(self) -> None:
        text = self.log.get("1.0", tk.END).strip()
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
            self.copy_btn.config(text="✔", fg="green")
            self.after(1200, lambda: self.copy_btn.config(text="📋", fg=THEMES[self.theme]["fg"]))

    def _copy_selection(self) -> None:
        try:
            sel = self.log.get(tk.SEL_FIRST, tk.SEL_LAST)
            if sel:
                self.clipboard_clear()
                self.clipboard_append(sel)
        except tk.TclError:
            pass

    def _on_close(self) -> None:
        self.stop_event.set()
        if self.process:
            try:
                self.process.kill()
            except Exception:
                pass
        self.ping_manager.stop_all()
        for ex in self._bg_executors:
            try:
                ex.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass
        if self.api_server is not None:
            try:
                self.api_server.shutdown()
                self.api_server.server_close()
            except Exception:
                pass
        self.destroy()


if __name__ == "__main__":
    GeoTraceApp().mainloop()
