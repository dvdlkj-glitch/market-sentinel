#!/usr/bin/env python
"""
Version: HORIZON Release LEO Supply Chain v1.3.6
Updated: 2026-04-23
Highlights:
- Added Taiwan Futures Lab with direction-aware break-even planning.
- Added feasibility ratio, recent range proxy, settlement-pressure warning, and fresher TWSE/TAIFEX market fetches.
- Kept the existing theme and dashboard analysis functions intact.
"""
from __future__ import annotations

import os
import contextlib
import io
import json
import ssl
from pathlib import Path
import re
import sqlite3
import textwrap
from datetime import datetime, timezone
from html import escape, unescape
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

try:
    import certifi
except Exception:
    certifi = None

try:
    import truststore
except Exception:
    truststore = None

# ---------------------------
# Configuration
# ---------------------------
DEFAULT_TICKERS = ["NVDA", "2330.TW", "2454.TW"]
DEFAULT_PERIOD = "1y"
DEFAULT_INTERVAL = "1d"
DEFAULT_WAVE_PERIOD = "6mo"
SUPPORTED_PERIODS = ["3mo", "6mo", "1y", "2y"]
SUPPORTED_INTERVALS = ["1d", "1wk"]

DASHBOARD_MODE_OPTIONS = ["General Market", "Active ETF Lab", "Supply Chain Lab", "Taiwan Futures Lab"]


def dashboard_mode_label(value: str) -> str:
    labels = {
        "General Market": t("dashboard_mode_main"),
        "Active ETF Lab": t("dashboard_mode_active_etf"),
        "Supply Chain Lab": t("dashboard_mode_supply_chain"),
        "Taiwan Futures Lab": t("dashboard_mode_taiwan_futures"),
    }
    return labels.get(str(value), str(value))


def theme_mode_label(value: str) -> str:
    labels = {
        "Dark Horizon": t("theme_dark"),
        "Light Horizon": t("theme_light"),
    }
    return labels.get(str(value), str(value))


def futures_position_side_label(value: str) -> str:
    labels = {
        "Call": t("taiwan_futures_side_long"),
        "Put": t("taiwan_futures_side_short"),
    }
    return labels.get(str(value), str(value))



DASHBOARD_LAYOUT_OPTIONS = ["Standard", "Advanced", "Expert"]
TX_FUTURES_POINT_VALUE = 50.0


def dashboard_layout_label(value: str) -> str:
    labels = {
        "Standard": t("layout_mode_standard"),
        "Advanced": t("layout_mode_advanced"),
        "Expert": t("layout_mode_expert"),
    }
    return labels.get(str(value), str(value))


def dashboard_layout_kicker() -> str:
    return "使用模式" if get_lang() == "繁體中文" else "Workspace mode"
