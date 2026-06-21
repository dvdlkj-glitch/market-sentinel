# -*- coding: utf-8 -*-
"""
🌸 今天煮什麼？— 亞庇家庭買菜煮飯小幫手（YouTube 反向版）
首頁：官方市場行情月度報告 ｜ YouTube 找菜 ｜ 一週餐表 ｜ 採買清單 ｜ 花費總覽
- 找菜：YouTube 搜尋 → 卡片式結果 → Dashboard 內嵌播放（可全螢幕）→ 排入餐表
- 一週餐表：Supabase meal_plan，粉色日曆卡，🪄 一鍵生成
- 採買清單：YouTube 抽取食材自動加總 + 估價 + WhatsApp 分享
- 估價：以市場行情／海鮮價格做本機推估（標「估」）
"""
import os
import base64
import functools
import urllib.parse
import urllib.request
import tempfile
import datetime
import random
import time
from collections import defaultdict
from datetime import date, timedelta

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from anthropic import Anthropic
from supabase import create_client

from recipes_data import (
    RECIPES, SEAFOOD_PRICES, MARKET_TIPS, ELDERLY_TIPS,
)
import recipe_to_ingredients as R
import meal_plan as MP
import market_compare as MC

st.set_page_config(page_title="今天煮什麼？亞庇買菜煮飯小幫手",
                   page_icon="🌸", layout="wide")

DAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
DAY_EMOJIS = ["🌷", "🌼", "🌺", "🌻", "🌹", "🌸", "💐"]
IMG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")


# ---------------------------------------------------------------- 連線
@st.cache_resource
def _get_clients():
    claude = Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])
    sb = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    return claude, sb

try:
    claude, supabase = _get_clients()
    YT_KEY = st.secrets["YOUTUBE_API_KEY"]
    CLIENTS_OK = True
except Exception:
    claude = supabase = YT_KEY = None
    CLIENTS_OK = False


def _bump_visits(supabase):
    """每個 session 記一筆造訪，回傳 (累計, 今日)。"""
    if supabase is None:
        return None, None
    try:
        if not st.session_state.get("_visit_logged"):
            import uuid
            supabase.table("visits").insert(
                {"session_id": str(uuid.uuid4())[:12]}).execute()
            st.session_state["_visit_logged"] = True
        now = time.monotonic()
        cached = st.session_state.get("_visit_counts")
        if cached and now - cached.get("ts", 0) < 120:
            return cached.get("total"), cached.get("today")
        total = supabase.table("visits").select(
            "id", count="exact").limit(1).execute().count
        import datetime as _dt
        t0 = _dt.datetime.now(_dt.timezone.utc).date().isoformat()
        today = supabase.table("visits").select(
            "id", count="exact").gte("ts", t0).limit(1).execute().count
        st.session_state["_visit_counts"] = {"total": total, "today": today, "ts": now}
        return total, today
    except Exception:
        cached = st.session_state.get("_visit_counts")
        if cached:
            return cached.get("total"), cached.get("today")
        return None, None


# ---------------------------------------------------------------- 主題 CSS（暖米色 × 赤陶 編輯風）
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Serif+TC:wght@500;700;900&family=Noto+Sans+TC:wght@400;500;700&display=swap');

:root{
  --ink:#2b211a; --terra:#c0492b; --terra-soft:#d9633f; --gold:#e7b04a;
  --muted:#9b8b76; --muted2:#b39a6e; --muted3:#a2917b;
  --bg-1:#f6efe4; --bg-2:#ece3d4;
  --card:#fffdf8; --line:#ebe0cd; --line2:#e7dccb; --panel:#fbf5ea;
  --green:#5c7a4a;
  --shadow:0 4px 18px rgba(120,90,50,.07);
}
*{ -webkit-tap-highlight-color:transparent; }
html, body, [class*="css"]{ font-family:'Noto Sans TC',system-ui,sans-serif; color:var(--ink); }
.serif{ font-family:'Noto Serif TC',serif; }
.stApp{
  background:#f6efe4;
  background-image:
    radial-gradient(circle at 12% -5%, #f4e7d2 0%, transparent 40%),
    radial-gradient(circle at 90% 0%, #f0e3cf 0%, transparent 35%);
  background-attachment:fixed;
}
/* 內容主欄＝霧面米色面板：影片在兩側留白與面板後方透出，所有文字始終落在可讀表面上 */
.block-container{
  max-width:1180px; padding:1.6rem 1.8rem 4rem; margin-top:1rem; margin-bottom:2rem;
  background:rgba(248,242,232,.86);
  backdrop-filter:blur(10px) saturate(1.05); -webkit-backdrop-filter:blur(10px) saturate(1.05);
  border:1px solid rgba(255,255,255,.55); border-radius:26px;
  box-shadow:0 24px 60px rgba(70,52,34,.22);
}
[data-testid="stHeader"]{ background:transparent !important; }
[data-testid="stToolbar"]{ right:8px; }

@keyframes floatUp{ from{opacity:0; transform:translateY(10px)} to{opacity:1; transform:none} }

/* ---------- 頂部品牌列 ---------- */
.appbar{ display:flex; align-items:center; gap:14px; padding:6px 2px 16px;
  border-bottom:1px solid var(--line2); margin-bottom:18px; }
.appbar .logo{ width:38px; height:38px; border-radius:11px; background:var(--terra);
  color:#fff; display:grid; place-items:center; font-family:'Noto Serif TC',serif;
  font-weight:900; font-size:21px; }
.appbar .brand{ line-height:1.05; }
.appbar .brand .t{ font-family:'Noto Serif TC',serif; font-weight:900; font-size:22px;
  letter-spacing:.5px; color:var(--ink); }
.appbar .brand .s{ font-size:11px; color:var(--muted); letter-spacing:2px; margin-top:3px;
  text-transform:uppercase; }

/* ---------- HERO ---------- */
.hero{ position:relative; border-radius:22px; overflow:hidden; border:1px solid var(--line2);
  min-height:230px; display:flex; align-items:flex-end;
  background:#2b211a; }
.hero img, .hero video{ position:absolute; inset:0; width:100%; height:100%; object-fit:cover; }
.hero .scrim{ position:absolute; inset:0;
  background:linear-gradient(100deg,rgba(43,33,26,.90) 0%,rgba(43,33,26,.58) 48%,rgba(43,33,26,.12) 100%); }
.hero .inner{ position:relative; padding:34px 32px; max-width:600px; }
.hero .tag{ display:inline-flex; align-items:center; gap:7px; background:rgba(255,255,255,.16);
  border:1px solid rgba(255,255,255,.28); color:#fff; font-size:11px; letter-spacing:1.5px;
  text-transform:uppercase; padding:5px 12px; border-radius:999px; margin-bottom:14px; }
.hero h1{ font-family:'Noto Serif TC',serif; font-weight:900; font-size:2rem; line-height:1.2;
  color:#fff; margin:0 0 10px; }
.hero p{ color:rgba(255,255,255,.84); font-size:.92rem; line-height:1.65; margin:0 0 18px;
  max-width:460px; }
.hero .steps{ display:flex; gap:18px; flex-wrap:wrap; }
.hero .step{ display:flex; align-items:center; gap:9px; color:#fff; font-size:.8rem; font-weight:500; }
.hero .step .n{ width:28px; height:28px; border-radius:50%; background:#fff; color:var(--terra);
  display:grid; place-items:center; font-weight:900; font-size:13px; font-family:'Noto Serif TC',serif; }
.hero .gold{ color:var(--gold); font-weight:700; }

/* ---------- 卡片 ---------- */
.card,.day-card,.pkg-card,.stat,
div[data-testid="stVerticalBlockBorderWrapper"]{
  background:var(--card); border:1px solid var(--line)!important; border-radius:18px;
  box-shadow:var(--shadow);
}
.card{ padding:18px 20px; margin-bottom:14px; line-height:1.7; }
.pkg-card{ padding:10px 10px 8px; text-align:center; transition:transform .18s ease, box-shadow .18s ease; }
.pkg-card:hover{ transform:translateY(-3px); box-shadow:0 12px 28px rgba(120,90,50,.14); }
.day-card{ padding:12px; margin-bottom:8px; }

.section-title{ font-family:'Noto Serif TC',serif; font-size:1.5rem; font-weight:900; color:var(--ink);
  margin:6px 0 14px; display:flex; align-items:center; gap:10px; }
.section-title::before{ content:''; width:5px; height:24px; border-radius:6px;
  background:var(--terra); display:inline-block; }
div[data-testid="stCaptionContainer"], div[data-testid="stCaptionContainer"] *{
  color:var(--muted) !important; }

.meal-name,.dish-mini{ font-family:'Noto Serif TC',serif; color:var(--ink); font-weight:700; line-height:1.3; }
.dish-mini{ font-size:.9rem; min-height:2.3em; margin-top:4px; }
.pkg-title{ font-weight:700; color:var(--ink); margin-top:8px; font-size:.92rem;
  line-height:1.35; min-height:2.4em; }
.pkg-desc{ font-size:.74rem; color:var(--muted3); margin-top:2px; }
.yt-thumb{ width:100%; height:128px; object-fit:cover; border-radius:12px; display:block; }

.cost-badge{ display:inline-block; background:transparent;
  color:var(--terra); font-weight:700; font-size:.86rem; padding:2px 0; margin-top:7px; }
.day-head{ display:flex; justify-content:space-between; align-items:center;
  font-family:'Noto Serif TC',serif; font-weight:700; color:var(--ink); font-size:1.05rem; margin-bottom:8px; }
.day-cost{ background:var(--panel); color:var(--muted); font-size:.74rem; font-weight:700;
  border-radius:999px; padding:3px 11px; border:1px solid var(--line); }
.slot-label{ font-size:.7rem; font-weight:700; color:var(--muted2); margin:10px 0 2px;
  letter-spacing:1px; text-transform:uppercase; }
.warn-flag{ color:var(--terra); font-size:.72rem; }
.day-divider{ border-top:1.5px dashed var(--line); margin:10px 0 8px; }
.meal-tag{ display:inline-block; font-size:.72rem; font-weight:700; padding:2px 10px;
  border-radius:999px; margin-bottom:6px; }
.tag-lunch{ background:#f7eede; color:#a6731f; } .tag-dinner{ background:#efe7d6; color:#7a5a3f; }
.chip{ display:inline-block; background:var(--panel); color:#7a5a3f; border-radius:999px;
  font-size:.72rem; padding:2px 9px; margin:2px; border:1px solid var(--line); }
.note{ font-size:.82rem; color:#5f5141; background:var(--panel); border-left:3px solid var(--terra);
  border-radius:8px; padding:8px 12px; margin-top:8px; line-height:1.6; }
.emoji-hero{ font-size:2.4rem; text-align:center; background:#f1e7d6; border-radius:12px;
  padding:10px 0; margin-bottom:8px; }

.stats-row{ display:flex; flex-wrap:wrap; gap:10px; margin:6px 0 14px; }
.stat{ flex:1 1 140px; text-align:center; padding:16px 8px; }
.stat .v{ font-family:'Noto Serif TC',serif; font-size:1.4rem; font-weight:900; color:var(--terra); }
.stat .l{ font-size:.78rem; color:var(--muted); margin-top:3px; }

.stButton > button{ border-radius:999px; border:1px solid var(--line);
  color:#7a5a3f; background:var(--card); font-weight:700; min-height:2.7rem;
  transition:transform .12s ease, box-shadow .18s ease, background .2s, border-color .2s; }
.stButton > button:hover{ border-color:var(--terra); color:var(--terra);
  box-shadow:0 6px 16px rgba(120,90,50,.12); }
.stButton > button:active{ transform:scale(.97); }
div[data-testid="stButton"] > button[kind="primary"]{
  background:var(--terra); color:#fff; border:none;
  font-size:1rem; font-weight:700; box-shadow:0 4px 14px rgba(192,73,43,.28); }
div[data-testid="stButton"] > button[kind="primary"]:hover{ background:#a93d22; color:#fff; }
div[data-testid="stButton"] > button[kind="primary"]:active{ transform:scale(.97); }
.stLinkButton > a{ border-radius:999px!important; min-height:2.7rem; font-weight:700!important;
  background:var(--card)!important; border:1px solid var(--line)!important; color:#7a5a3f!important; }
.stButton > button p, .stLinkButton > a p{ white-space:nowrap; }
.stDownloadButton > button{ border-radius:999px; }

.stTabs [data-baseweb="tab-list"]{ gap:6px; overflow-x:auto; flex-wrap:nowrap;
  scrollbar-width:none; -webkit-overflow-scrolling:touch; padding:4px 0 14px;
  border-bottom:1px solid var(--line2); }
.stTabs [data-baseweb="tab-list"]::-webkit-scrollbar{ display:none; }
.stTabs [data-baseweb="tab"]{ background:transparent;
  border-radius:13px; padding:9px 16px; border:none;
  color:#6f5f4c; font-weight:700; white-space:nowrap; flex-shrink:0; }
.stTabs [data-baseweb="tab"]:hover{ background:#f1e7d6; }
.stTabs [aria-selected="true"]{ background:var(--ink)!important;
  color:#fff!important; border:none!important; }
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"]{ background:transparent!important; }

[data-testid="stDataFrame"]{ border-radius:16px; overflow:hidden; box-shadow:var(--shadow);
  border:1px solid var(--line); }

/* ---------- 響應式（手機優先） ---------- */
@media (max-width:1024px){
  [data-testid="stHorizontalBlock"]{ flex-wrap:wrap!important; gap:.7rem!important; }
  [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]{
    flex:1 1 48%!important; min-width:48%!important; width:auto!important; }
}
@media (max-width:768px){
  .block-container{ padding:.8rem .7rem 3rem!important; }
  .hero h1{ font-size:1.6rem; } .hero p{ font-size:.85rem; }
  .appbar .brand .t{ font-size:19px; }
  .yt-thumb{ height:150px; }
}
@media (max-width:560px){
  [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]{
    flex:1 1 100%!important; min-width:100%!important; }
  .hero .inner{ padding:24px 22px; }
  .hero h1{ font-size:1.4rem; }
  .section-title{ font-size:1.25rem; }
  .stButton > button{ min-height:3rem; font-size:1rem; }
  .stat .v{ font-size:1.2rem; }
  .yt-thumb{ height:185px; }
}
@media (max-width:380px){
  .hero h1{ font-size:1.25rem; } .hero p{ font-size:.8rem; }
  .block-container{ padding:.6rem .5rem 3rem!important; }
}
footer{ visibility:hidden; }

.yt-wrap{ position:relative; border-radius:12px; overflow:hidden; height:140px; background:#f1e7d6; }
.yt-wrap .yt-thumb{ height:100%; border-radius:0; }
.yt-play{ position:absolute; inset:0; display:flex; align-items:center; justify-content:center;
  font-size:30px; color:#fff; background:rgba(43,33,26,.14); opacity:0; transition:opacity .2s; }
.yt-wrap:hover .yt-play{ opacity:1; background:rgba(43,33,26,.34); }
.yt-card-title{ font-family:'Noto Serif TC',serif; font-weight:700; color:var(--ink); font-size:.95rem; line-height:1.3;
  margin-top:9px; height:2.5em; display:-webkit-box; -webkit-line-clamp:2;
  -webkit-box-orient:vertical; overflow:hidden; }
.yt-card-chan{ font-size:.74rem; color:var(--muted3); margin:5px 0 2px; white-space:nowrap;
  overflow:hidden; text-overflow:ellipsis; }
@media (max-width:560px){ .yt-wrap{ height:190px; } }

.dish-mini{ height:2.3em; min-height:2.3em; display:-webkit-box; -webkit-line-clamp:2;
  -webkit-box-orient:vertical; overflow:hidden; }
.day-card .yt-thumb{ height:84px; }

.rec-emoji{ font-size:30px; text-align:center; }
.rec-name{ font-family:'Noto Serif TC',serif; font-weight:700; color:var(--ink); font-size:1rem; text-align:center;
  line-height:1.25; height:2.5em; display:-webkit-box; -webkit-line-clamp:2;
  -webkit-box-orient:vertical; overflow:hidden; margin:4px 0 6px; }
.rec-name + .cost-badge{ display:block; text-align:center; }

.cost-badge{ white-space:nowrap; }
.day-card .cost-badge{ font-size:.78rem; }
.day-card .dish-mini{ height:2.4em; }

.rec-cat{ font-family:'Noto Serif TC',serif; font-weight:700; color:var(--ink); margin:14px 2px 6px; font-size:1.15rem; }
.pan-have{ font-size:.86rem; color:#5f5141; background:var(--panel); border-radius:10px;
  padding:8px 12px; margin:2px 0 6px; border:1px solid var(--line); }
.pan-cat{ font-weight:700; color:#7a5a3f; font-size:.84rem; margin:8px 2px 2px; }
.pan-ok{ display:inline-block; font-size:.82rem; font-weight:700; color:var(--green); margin:2px 0; }
.pan-miss{ font-size:.8rem; color:var(--terra); margin:2px 0 4px; }
.pan-miss-ok{ color:var(--green); font-weight:700; }
.pan-guide{ font-size:.85rem; line-height:1.7; color:#5f5141; background:var(--panel);
  border:1px dashed var(--muted2); border-radius:12px; padding:10px 14px; margin:4px 0 10px; }

/* 人數 − / + 步進器 */
.stepper-label{ font-weight:700; color:var(--ink); font-size:.92rem; margin-bottom:4px; }
.people-count{ text-align:center; font-family:'Noto Serif TC',serif; font-weight:900;
  font-size:1.35rem; color:var(--ink); line-height:2.7rem; }</style>
""", unsafe_allow_html=True)


# 烹飪背景影片（由 Streamlit 靜態服務 app/static/ 提供）；現只用於 Hero 區塊內當動態背景。
_BG_VIDEO_URL = "app/static/cooking_background.mp4"


# ---------------------------------------------------------------- 估價（本機推估）
# 以「每道菜該食材的常見份量價」粗估，避開調味料；標示「估」。
PRICE_PORTIONS = [
    (("蝦", "明蝦", "白蝦", "草蝦"), 14),
    (("蟹", "螃蟹"), 18),
    (("牛",), 16),
    (("鴨",), 13),
    (("豬", "排骨", "五花"), 11),
    (("魚", "馬鮫", "甘望", "石斑", "紅鰽", "鱸", "鯧", "鯛"), 12),
    (("雞",), 9),
    (("香菇", "蘑菇", "金針菇", "杏鮑菇", "草菇", "菇"), 4),
    (("豆腐", "豆干", "豆包", "豆皮"), 3),
    (("蛋",), 2),
    (("番茄", "西紅柿"), 2),
    (("洋蔥",), 2),
    (("馬鈴薯", "土豆", "薯", "蘿蔔"), 2),
    (("青菜", "菜心", "白菜", "芥蘭", "空心菜", "菠菜", "花椰", "西蘭花",
      "高麗", "包菜", "生菜", "莧菜", "油菜", "青江", "豆芽", "長豆"), 3),
    (("麵", "河粉", "米粉", "烏冬", "粄條", "板麵"), 3),
    (("米", "飯", "糯米"), 2),
    (("咖哩", "椰漿", "椰奶"), 3),
    (("辣椒", "紅椒", "青椒", "彩椒", "甜椒"), 2),
    (("蒜", "薑", "蔥", "香菜", "九層塔", "羅勒"), 1),
]
SEASONING_FREE = ("鹽", "糖", "油", "醬油", "胡椒", "醋", "味精", "料酒", "米酒",
                  "水", "太白粉", "澱粉", "蠔油", "魚露", "醬", "酒", "粉")


def estimate_dish_cost(ingredients):
    """回傳 (low, high, matched, counted) 或 None。"""
    total, matched, counted = 0.0, 0, 0
    for ing in ingredients or []:
        name = (ing.get("name_norm") or ing.get("name") or "")
        if any(s in name for s in SEASONING_FREE):
            continue
        counted += 1
        for kws, rm in PRICE_PORTIONS:
            if any(k in name for k in kws):
                total += rm
                matched += 1
                break
    if matched == 0:
        return None
    return int(round(total * 0.9)), int(round(total * 1.1)), matched, counted


def cost_badge(ingredients):
    est = estimate_dish_cost(ingredients)
    if not est:
        return "<span class='cost-badge'>💰 RM —</span>"
    lo, hi, _m, _c = est
    return f"<span class='cost-badge'>💰 估 RM {lo}–{hi}</span>"


def dish_mid_cost(ingredients):
    est = estimate_dish_cost(ingredients)
    if not est:
        return 0
    lo, hi, _m, _c = est
    return (lo + hi) / 2


# ---------------------------------------------------------------- 樂齡用：份量縮放
def people_factor(n):
    return {2: 0.8, 3: 1.0, 4: 1.15, 5: 1.35, 6: 1.5}.get(n, 1.0)

def scaled_cost(recipe, n):
    f = people_factor(n)
    return int(round(recipe["cost"][0] * f)), int(round(recipe["cost"][1] * f))


def people_stepper(value, key_prefix, lo=2, hi=6, label="👨‍👩‍👧 用餐人數"):
    """以 − / + 按鈕調整人數（取代滑桿），回傳調整後的人數。"""
    st.markdown(f"<div class='stepper-label'>{label}</div>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 1.5, 1])
    v = value
    with c1:
        if st.button("−", key=f"{key_prefix}_minus", use_container_width=True):
            v = max(lo, value - 1)
    with c3:
        if st.button("＋", key=f"{key_prefix}_plus", use_container_width=True):
            v = min(hi, value + 1)
    with c2:
        st.markdown(f"<div class='people-count'>{v} 人</div>", unsafe_allow_html=True)
    return v


@functools.lru_cache(maxsize=64)
def _img_b64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


# ---------------------------------------------------------------- 官方物價 PriceCatcher
PC_BASE = "https://storage.data.gov.my/pricecatcher"

OFFICIAL_ITEMS = [
    ("🐟 甘望魚 Ikan Kembung", ["IKAN KEMBUNG"]),
    ("🐠 馬鮫魚 Ikan Tenggiri", ["IKAN TENGGIRI"]),
    ("🦐 蝦 Udang", ["UDANG"]),
    ("🐡 紅鰽魚 / 石斑", ["IKAN MERAH", "KERAPU"]),
    ("🍗 雞肉 Ayam", ["AYAM STANDARD", "AYAM SUPER", "AYAM BERSIH"]),
    ("🥚 雞蛋 Telur", ["TELUR AYAM"]),
    ("🍅 番茄 Tomato", ["TOMATO"]),
    ("🧅 洋蔥 Bawang", ["BAWANG BESAR"]),
    ("🥬 菜心 / 小白菜 Sawi", ["SAWI"]),
    ("🌶️ 辣椒 Cili", ["CILI"]),
]

def _read_parquet_url(url):
    fn = os.path.join(tempfile.gettempdir(), os.path.basename(url))
    if not os.path.exists(fn):
        urllib.request.urlretrieve(url, fn)
    return pd.read_parquet(fn)

@st.cache_data(ttl=60 * 60 * 24, show_spinner=False)
def fetch_official_mom():
    premise = _read_parquet_url(f"{PC_BASE}/lookup_premise.parquet")
    items = _read_parquet_url(f"{PC_BASE}/lookup_item.parquet")
    kk = set(premise.loc[
        premise["district"].astype(str).str.contains("Kota Kinabalu", case=False, na=False),
        "premise_code"])

    def prep(m):
        df = _read_parquet_url(f"{PC_BASE}/pricecatcher_{m}.parquet")
        df = df[df["premise_code"].isin(kk)]
        df = df[df["price"] > 0]
        df = df.merge(items[["item_code", "item", "unit"]], on="item_code", how="left")
        df["item"] = df["item"].astype(str).str.upper()
        return df

    today = datetime.date.today()
    first = today.replace(day=1)
    m_now = today.strftime("%Y-%m")
    m_prev = (first - datetime.timedelta(days=1)).strftime("%Y-%m")
    m_prev2 = ((first - datetime.timedelta(days=1)).replace(day=1)
               - datetime.timedelta(days=1)).strftime("%Y-%m")
    pair = None
    for cm, pm in ((m_now, m_prev), (m_prev, m_prev2)):
        try:
            pair = (cm, prep(cm), pm, prep(pm))
            break
        except Exception:
            continue
    if pair is None:
        raise RuntimeError("PriceCatcher 下載失敗")
    cm, cur, pm, prev = pair
    rows = []
    for label, kws in OFFICIAL_ITEMS:
        pat = "|".join(kws)
        c = cur[cur["item"].str.contains(pat, na=False)]
        p = prev[prev["item"].str.contains(pat, na=False)]
        if len(c) < 3 or len(p) < 3:
            continue
        mc, mp = float(c["price"].median()), float(p["price"].median())
        pct = (mc - mp) / mp * 100 if mp else 0.0
        arrow = "🔺" if pct > 0.5 else ("🔻" if pct < -0.5 else "➖")
        unit = c["unit"].mode().iloc[0] if len(c["unit"].mode()) else "-"
        rows.append({"品項": label,
                     f"上月 ({pm})": round(mp, 2),
                     f"本月 ({cm})": round(mc, 2),
                     "變化": f"{arrow} {pct:+.1f}%",
                     "單位": unit})
    return pd.DataFrame(rows), {"cur": cm, "prev": pm, "premises": int(len(kk))}


# ---------------------------------------------------------------- 找菜池（一鍵生成用）
LUNCH_NAMES = [r["name"] for r in RECIPES if "lunch" in r["meal"]]
DINNER_NAMES = [r["name"] for r in RECIPES if "dinner" in r["meal"]]

CUISINES = ["全部", "中式", "台式", "西式", "泰式", "馬來西亞", "印尼"]
CUISINE_KW = {"全部": "", "中式": "中式", "台式": "台式", "西式": "西式",
              "泰式": "泰式", "馬來西亞": "馬來西亞", "印尼": "印尼"}
CUISINE_DISHES = {
    "中式": [("麻婆豆腐", 8, 12), ("番茄炒蛋", 5, 8), ("宮保雞丁", 12, 18), ("糖醋排骨", 14, 20),
            ("清蒸魚", 16, 24), ("蒜蓉青菜", 5, 8), ("紅燒豆腐", 7, 11), ("蔥爆牛肉", 18, 26)],
    "台式": [("滷肉飯", 8, 12), ("三杯雞", 14, 20), ("菜脯蛋", 6, 9), ("客家小炒", 14, 20),
            ("台式炒米粉", 8, 13), ("麻油雞", 18, 26), ("塔香茄子", 8, 12), ("鹹蛋苦瓜", 9, 14)],
    "西式": [("奶油義大利麵", 12, 18), ("香煎雞排", 12, 18), ("烤時蔬", 8, 13), ("蘑菇濃湯", 8, 12),
            ("焗烤馬鈴薯", 9, 14), ("凱薩沙拉", 10, 15), ("番茄肉醬麵", 12, 18), ("煎鮭魚", 20, 30)],
    "泰式": [("打拋豬", 12, 18), ("泰式綠咖哩", 14, 20), ("泰式炒河粉", 10, 16), ("椒麻雞", 13, 19),
            ("泰式青木瓜沙拉", 8, 13), ("泰式炒空心菜", 7, 11), ("泰式酸辣湯", 12, 18), ("鳳梨炒飯", 10, 15)],
    "馬來西亞": [("椰漿飯", 7, 11), ("咖哩雞", 14, 20), ("炒粿條", 8, 13), ("海南雞飯", 10, 15),
              ("叻沙", 10, 16), ("馬來風光", 9, 14), ("黃薑飯", 7, 11), ("參巴江魚仔", 8, 12)],
    "印尼": [("印尼炒飯", 8, 13), ("仁當牛肉", 20, 30), ("沙嗲雞", 12, 18), ("巴東牛肉", 20, 30),
            ("印尼炒麵", 8, 13), ("加多加多", 9, 14), ("薑黃飯", 7, 11), ("參巴空心菜", 7, 11)],
}
CUISINE_DISHES["全部"] = [d for _c in ["中式", "台式", "西式", "泰式", "馬來西亞", "印尼"]
                        for d in CUISINE_DISHES[_c]]
CUISINE_POOLS = {c: [n for (n, _lo, _hi) in lst] for c, lst in CUISINE_DISHES.items()}
DISH_PRICE = {n: (lo, hi) for lst in CUISINE_DISHES.values() for (n, lo, hi) in lst}

SKIN_TRIGGERS = ["蝦", "蟹", "貝", "蛤", "蚌", "魷", "茄子", "筍", "辣", "花生", "芒果"]
SKIN_NOTE = ("💧 皮膚敏感模式：含蝦、蟹、貝、魷、茄子、竹筍、辣等常見發物的菜會標 ⚠。"
             "此為飲食參考，若有確診過敏請以醫生囑咐為準。")

def name_has_trigger(name):
    return any(t in (name or "") for t in SKIN_TRIGGERS)

def ingredients_have_trigger(ingredients):
    for ing in ingredients or []:
        nm = (ing.get("name_norm") or ing.get("name") or "")
        if any(t in nm for t in SKIN_TRIGGERS):
            return True
    return False

def scaled_cost_badge(ingredients, people):
    est = estimate_dish_cost(ingredients)
    if not est:
        return "<span class='cost-badge'>💰 RM —</span>"
    lo, hi, _m, _c = est
    f = people_factor(people)
    return f"<span class='cost-badge'>💰 估 RM {int(round(lo * f))}–{int(round(hi * f))}</span>"



# ---------------------------------------------------------------- 頁首：品牌列 + Hero
# 品牌列（沿用設計稿的 logo「煮」＋中英標題）
st.markdown("""
<div class="appbar">
  <div class="logo">煮</div>
  <div class="brand">
    <div class="t">今天煮什麼？</div>
    <div class="s">What to cook today · 亞庇 Kota Kinabalu</div>
  </div>
</div>
""", unsafe_allow_html=True)

# Hero 動態背景：把烹飪影片放在 Hero 區塊內當「較小尺寸」的動態背景（取代滿版背景）。
# weekend_feast.jpg 當 poster（載入前先顯示一張靜態圖，避免空白）。
_hero_img = os.path.join(IMG_DIR, "weekend_feast.jpg")
_hero_poster = (f"data:image/jpeg;base64,{_img_b64(_hero_img)}"
                if os.path.exists(_hero_img) else "")

_vt, _vd = _bump_visits(supabase)
if _vt:
    _td = f" · 今日 {_vd}" if _vd is not None else ""
    _visits_html = f"👀 累計造訪 {_vt:,} 次{_td}"
else:
    _visits_html = "👀 為亞庇家庭設計的買菜煮飯小幫手"

st.markdown(f"""
<div class="hero">
  <video autoplay loop muted playsinline preload="auto"
         poster="{_hero_poster}" src="{_BG_VIDEO_URL}"></video>
  <div class="scrim"></div>
  <div class="inner">
    <div class="tag">反向流程 · 選菜就好</div>
    <h1>先選想吃的菜，<br>採買清單自動生成</h1>
    <p>選菜 → YouTube 抽食材 → 一週餐表與花費。專為亞庇家庭晚餐而設，
       對比 <span class="gold">麗都 &amp; 生源市場</span> 行情、貼心避開敏感食材。</p>
    <div class="steps">
      <div class="step"><span class="n">1</span>選菜</div>
      <div class="step"><span class="n">2</span>抽食材</div>
      <div class="step"><span class="n">3</span>採買 + 花費</div>
    </div>
    <div style="margin-top:18px;font-size:12px;color:rgba(255,255,255,.62);">{_visits_html}</div>
  </div>
</div>
""", unsafe_allow_html=True)
st.write("")

if not CLIENTS_OK:
    st.error("⚠️ 找不到 API 金鑰（ANTHROPIC / SUPABASE / YOUTUBE）。"
             "市場行情與樂齡專區仍可使用，但「找菜／餐表／採買清單」需要設定 Secrets。")

# 導覽：只渲染目前選到的 Dashboard 區塊，避免 st.tabs 每次互動都重建所有內容。
DASHBOARD_SECTIONS = [
    ("find", "🍳 探索找菜"),
    ("week", "📅 一週餐表"),
    ("shop", "🛒 採買清單"),
    ("budget", "💰 花費總覽"),
    ("market", "📊 市場行情"),
    ("elderly", "👵 樂齡專區"),
    ("tips", "💡 小貼士"),
]
_dashboard_labels = [label for _, label in DASHBOARD_SECTIONS]
_dashboard_default = st.session_state.get("_dashboard_active_label", _dashboard_labels[0])
if _dashboard_default not in _dashboard_labels:
    _dashboard_default = _dashboard_labels[0]
try:
    _dashboard_label = st.pills(
        "Dashboard",
        _dashboard_labels,
        default=_dashboard_default,
        key="dashboard_nav",
        label_visibility="collapsed",
    )
except Exception:
    _dashboard_label = st.radio(
        "Dashboard",
        _dashboard_labels,
        index=_dashboard_labels.index(_dashboard_default),
        horizontal=True,
        key="dashboard_nav_radio",
        label_visibility="collapsed",
    )
_dashboard_label = _dashboard_label or _dashboard_default
st.session_state["_dashboard_active_label"] = _dashboard_label
_active_section = dict((label, section) for section, label in DASHBOARD_SECTIONS)[_dashboard_label]


# ================ 📊 市場行情 ================
if _active_section == "market":
    st.markdown("<div class='section-title'>📊 亞庇官方物價月報（上月 vs 本月）</div>",
                unsafe_allow_html=True)
    try:
        with st.spinner("正在載入官方數據（首次約 20–60 秒，之後全站共用快取）…"):
            otable, ometa = fetch_official_mom()
        if len(otable):
            ups = int(otable["變化"].str.startswith("🔺").sum())
            downs = int(otable["變化"].str.startswith("🔻").sum())
            flat = len(otable) - ups - downs
            st.markdown(f"""
            <div class='stats-row'>
              <div class='stat'><div class='v'>🔺 {ups} 項</div><div class='l'>本月變貴</div></div>
              <div class='stat'><div class='v'>🔻 {downs} 項</div><div class='l'>本月變便宜</div></div>
              <div class='stat'><div class='v'>➖ {flat} 項</div><div class='l'>大致持平</div></div>
              <div class='stat'><div class='v'>{ometa['premises']} 家</div><div class='l'>KK 採價店家</div></div>
            </div>""", unsafe_allow_html=True)
            st.dataframe(otable, use_container_width=True, hide_index=True)
            st.caption(
                f"資料來源：PriceCatcher（馬來西亞 KPDN + DOSM，data.gov.my，CC BY 4.0）｜"
                f"比較月份 {ometa['prev']} → {ometa['cur']}，取 Kota Kinabalu 店家當月中位價。"
                f"官方採價以超市與零售店為主，濕市場價格可能略有差異，僅供參考。")
        else:
            st.info("官方數據已下載，但本期抓不到亞庇的相關品項，請過幾天再看。")
    except Exception:
        st.warning("📡 官方月度數據暫時無法載入（來源網站忙碌），請稍後重新整理頁面。"
                   "下方為麗都市場參考行情。")

    st.markdown("<div class='section-title'>🌏 三地市場對比：亞庇 · 吉隆坡 · 台北</div>",
                unsafe_allow_html=True)
    try:
        with st.spinner("正在載入三地對比（首次稍久）…"):
            cdf, cmeta = MC.fetch_compare()
        st.dataframe(cdf, use_container_width=True, hide_index=True)
        st.caption(
            f"亞庇／吉隆坡：PriceCatcher 官方零售價（{cmeta['month']}；KK {cmeta['kk_n']} 家、KL {cmeta['kl_n']} 家中位價）。"
            f"台北：台灣農業部農產品批發行情，以即時匯率 1 TWD≈{cmeta['rate']:.3f} RM 換算"
            "（批發價通常低於零售，僅供跨國參考）。雞肉／雞蛋／海鮮在台灣屬畜漁產、不在此農產批發資料，故台北欄留空。")
    except Exception as _ce:
        st.info(f"三地對比資料暫時無法取得（{_ce}）。")

    st.markdown("<div class='section-title'>🐟 麗都市場海鮮參考行情（RM / 公斤）</div>",
                unsafe_allow_html=True)
    _mkt = [("market_tenggiri.jpg", "馬鮫魚 Ikan Tenggiri"),
            ("market_kembung.jpg", "甘望魚 Ikan Kembung"),
            ("market_udang.jpg", "本地白蝦 Udang"),
            ("market_merah.jpg", "紅鰽魚 / 石斑")]
    if any(os.path.exists(os.path.join(IMG_DIR, f)) for f, _ in _mkt):
        mcols = st.columns(4)
        for col, (fn, cap) in zip(mcols, _mkt):
            p = os.path.join(IMG_DIR, fn)
            if os.path.exists(p):
                col.image(p, caption=cap, use_container_width=True)
    sf = pd.DataFrame([{"海鮮": f"{e} {zh}", "馬來名稱": my,
                        "價格 (RM/kg)": f"RM {a} – {b}", "特點 / 料理方式": note}
                       for zh, my, e, a, b, note in SEAFOOD_PRICES])
    st.dataframe(sf, use_container_width=True, hide_index=True)
    st.markdown("<div class='card'><b style='color:#2b211a'>🧺 買海鮮小貼士</b><br>" +
                "<br>".join(MARKET_TIPS[:5]) + "</div>", unsafe_allow_html=True)


# ================ 🔍 找菜（YouTube 搜尋 → 卡片 → 內嵌播放 → 排入餐表） ================
if _active_section == "find":
    st.markdown("<div class='section-title'>🔍 想煮什麼？YouTube 上找，找到就排進餐表</div>",
                unsafe_allow_html=True)

    if not CLIENTS_OK:
        st.info("此功能需要 ANTHROPIC / SUPABASE / YOUTUBE 三把金鑰，請先到 Secrets 設定。")
    else:
        ss = st.session_state
        ss.setdefault("find_cards", [])
        ss.setdefault("play_vid", None)
        ss.setdefault("play_title", "")
        ss.setdefault("people", 4)
        ss.setdefault("skin", False)
        ss.setdefault("cuisine", "全部")

        with st.container(border=True):
            st.markdown("<b style='color:#2b211a'>⚙️ 用餐設定</b>", unsafe_allow_html=True)
            sc1, sc2 = st.columns([1.4, 1])
            with sc1:
                ss.people = people_stepper(ss.people, "people")
            with sc2:
                ss.skin = st.toggle("💧 皮膚敏感（標示發物）", value=ss.skin, key="skin_toggle")
            try:
                _cz = st.pills("🍽️ 料理大類", CUISINES, default=ss.cuisine, key="cuisine_pills")
                ss.cuisine = _cz or "全部"
            except Exception:
                ss.cuisine = st.radio("🍽️ 料理大類", CUISINES,
                                      index=CUISINES.index(ss.cuisine), horizontal=True,
                                      key="cuisine_radio")
            if ss.skin:
                st.caption(SKIN_NOTE)

        _f = people_factor(ss.get("people", 4))
        _emojis = ["🍲", "🍛", "🥘", "🍜", "🥗", "🍳", "🐟", "🍗"]
        _cz = ss.cuisine

        # ── 🧊 我的食材庫（管理）──────────────────────────────
        PANTRY_CATS = {
            "🥬 蔬菜": ["番茄", "洋蔥", "高麗菜", "青菜", "紅蘿蔔", "馬鈴薯",
                       "苦瓜", "茄子", "玉米", "青椒", "菇類", "小黃瓜"],
            "🍖 肉‧海鮮": ["雞肉", "豬肉", "牛肉", "蝦", "魚", "花枝"],
            "🥚 蛋‧豆製": ["雞蛋", "豆腐", "豆乾", "油豆腐"],
            "🌶 辛香料": ["辣椒", "九層塔", "香菜"],
            "🍚 主食": ["白飯", "麵條", "米粉", "河粉"],
        }
        _ALL_PRESET = [it for items in PANTRY_CATS.values() for it in items]

        # 食材庫只在進頁時載入一次 → 之後點選純記憶體、不再每次連線（快很多）
        if "pan_items" not in ss:
            ss["pan_items"] = [r["item"] for r in MP.get_pantry(supabase)]

        with st.container(border=True):
            st.markdown("<div class='section-title' style='margin-top:0'>🧊 我的食材庫</div>",
                        unsafe_allow_html=True)
            st.markdown(
                "<div class='pan-guide'>🌸 <b>怎麼用</b>：① 點下面標籤勾出家裡有的食材"
                "（可一次點多個）→ ② 下方切到 <b>🧊 用現有食材煮</b>"
                " → ③ 挑一道按 <b>➕ 排入</b> → ④ 到最上面 <b>📅 一週餐表</b> 分頁就能看到囉！</div>",
                unsafe_allow_html=True)

            _picked = []
            for _ci, (_cat, _items) in enumerate(PANTRY_CATS.items()):
                _cur = set(ss["pan_items"])
                _sel = st.pills(_cat, _items, selection_mode="multi",
                                default=[it for it in _items if it in _cur],
                                key=f"pan_pills_{_ci}")
                _picked.extend(_sel or [])

            _ac1, _ac2 = st.columns([3, 1])
            with _ac1:
                _new = st.text_input("自己加", key="pan_new",
                                     placeholder="例：芹菜、鯧魚、年糕…",
                                     label_visibility="collapsed")
            with _ac2:
                _add = st.button("➕ 加入", key="pan_add_btn", use_container_width=True)
            _clear = bool(ss["pan_items"]) and st.button("🧹 清空食材庫", key="pan_clear")

            if _clear:
                for _ci in range(len(PANTRY_CATS)):
                    ss.pop(f"pan_pills_{_ci}", None)
                ss.pop("pan_new", None)
                MP.clear_pantry(supabase)
                ss["pan_items"] = []
                st.toast("食材庫已清空", icon="🧹")
                st.rerun()

            _custom = [it for it in ss["pan_items"] if it not in _ALL_PRESET]
            _target = list(dict.fromkeys(_picked + _custom))
            _did_add = False
            if _add and _new.strip() and _new.strip() not in _target:
                _target.append(_new.strip())
                _did_add = True

            _old, _newset = set(ss["pan_items"]), set(_target)
            if _old != _newset:
                for _it in (_newset - _old):
                    _cat0 = next((c for c, its in PANTRY_CATS.items() if _it in its), "自訂")
                    MP.add_pantry(supabase, _it, _cat0)
                for _it in (_old - _newset):
                    MP.remove_pantry(supabase, _it)
                ss["pan_items"] = _target
            if _did_add:
                ss.pop("pan_new", None)
                st.toast(f"已加入 {_new.strip()}", icon="🧺")
                st.rerun()

            _pan = ss["pan_items"]
            if _pan:
                st.markdown("<div class='pan-have'>🧺 目前有 " + str(len(_pan)) + " 樣："
                            + "、".join(_pan) + "</div>", unsafe_allow_html=True)
            else:
                st.caption("還沒勾食材，先點幾個吧 🌸")
            st.caption("💡 鹽油醬蒜薑蔥等常備調味料一律當作已有，不列入「還缺」。")

        # ── 推薦模式切換 ─────────────────────────────────────
        _mode = st.radio("推薦方式", ["🎲 隨機精選", "🧊 用現有食材煮"],
                         horizontal=True, key="rec_mode", label_visibility="collapsed")
        st.caption("🎲 隨機精選＝每類給 5 道靈感　·　🧊 用現有食材煮＝依你勾的食材排出最能煮的菜")

        def _render_rec_row(cz, dishes):
            _cols = st.columns(5)
            for _i, (_name, _lo, _hi) in enumerate(dishes):
                with _cols[_i % 5]:
                    with st.container(border=True):
                        _fl = " ⚠" if (ss.get("skin") and name_has_trigger(_name)) else ""
                        st.markdown(
                            f"<div class='rec-emoji'>{_emojis[_i % len(_emojis)]}</div>"
                            f"<div class='rec-name'>{_name}{_fl}</div>"
                            f"<span class='cost-badge'>💰 估 RM {int(round(_lo * _f))}–{int(round(_hi * _f))}</span>",
                            unsafe_allow_html=True)
                        # 看做法：到 YouTube 搜尋這道菜的做法（新分頁開啟，像設計稿一樣）
                        _wq = (CUISINE_KW.get(cz, "") + " " + _name + " 做法 食譜").strip()
                        _yt = ("https://www.youtube.com/results?search_query="
                               + urllib.parse.quote(_wq))
                        st.link_button("▶ 看做法", _yt, use_container_width=True)
                        _pop = st.popover("➕ 排入", use_container_width=True)
                        with _pop:
                            _d = st.date_input("排到哪一天", value=date.today(), key=f"rd_{cz}_{_i}")
                            _sl = st.radio("時段", MP.SLOTS, horizontal=True, key=f"rs_{cz}_{_i}")
                            if st.button("✅ 確認排入", key=f"rcf_{cz}_{_i}", use_container_width=True):
                                with st.spinner(f"從 YouTube 找「{_name}」並抽食材…"):
                                    try:
                                        _rec = R.get_or_build_by_name(
                                            _name, yt_api_key=YT_KEY, anthropic_client=claude,
                                            supabase=supabase, search_prefix=CUISINE_KW.get(cz, ""))
                                        if _rec:
                                            MP.add_to_plan(supabase, _d, _sl, _rec["video_id"])
                                            st.success(f"已排入 {_d} {_sl}：{_rec['title'][:16]}　👉 到「📅 一週餐表」看")
                                            st.toast("已排入！", icon="✅")
                                        else:
                                            st.error("找不到對應影片，換一道試試。")
                                    except Exception as _e:
                                        st.error(f"排入失敗：{_e}")

        if _mode.startswith("🧊"):
            if not _pan:
                st.info("先在上面「🧊 我的食材庫」加一些食材，這裡就會推薦你能煮的菜 🌸")
            else:
                _only = st.checkbox("只看缺 ≤ 1 樣", key="pan_only_close")
                if "pan_index" not in ss:
                    ss["pan_index"] = R.load_pantry_index(
                        supabase, [n for (n, _l, _h) in CUISINE_DISHES["全部"]])
                _recs = R.score_by_pantry(ss["pan_index"], _pan, max_results=24)
                if _only:
                    _recs = [r for r in _recs if (r["total"] - r["have"]) <= 1]
                st.markdown(
                    f"<div class='section-title'>🍳 用現有食材能煮（{len(_recs)} 道 · 吻合度排序）</div>",
                    unsafe_allow_html=True)
                if not _recs:
                    st.warning("目前快取裡沒有吻合的菜。多加幾樣常見食材，或先用「🎲 隨機精選」把菜建進快取。")
                _pcols = st.columns(4)
                for _i, _r in enumerate(_recs):
                    _nm = _r["name"]
                    _lo, _hi = DISH_PRICE.get(_nm, (0, 0))
                    _miss = _r["missing"]
                    _full = (_r["have"] == _r["total"])
                    with _pcols[_i % 4]:
                        with st.container(border=True):
                            _fl = " ⚠" if (ss.get("skin") and name_has_trigger(_nm)) else ""
                            _badge = ("<span class='pan-ok'>✅ 有 %d/%d 食材%s</span>"
                                      % (_r["have"], _r["total"], " 🎉" if _full else ""))
                            if _miss:
                                _need = ("<div class='pan-miss'>🛒 還缺："
                                         + "、".join(_miss[:4])
                                         + ("…" if len(_miss) > 4 else "") + "</div>")
                            else:
                                _need = "<div class='pan-miss pan-miss-ok'>全部都有！</div>"
                            st.markdown(
                                f"<div class='rec-name'>{_nm}{_fl}</div>"
                                f"{_badge}{_need}"
                                f"<span class='cost-badge'>💰 估 RM {int(round(_lo * _f))}–{int(round(_hi * _f))}</span>",
                                unsafe_allow_html=True)
                            with st.popover("➕ 排入", use_container_width=True):
                                _d = st.date_input("排到哪一天", value=date.today(), key=f"pd_{_i}")
                                _sl = st.radio("時段", MP.SLOTS, horizontal=True, key=f"ps_{_i}")
                                if st.button("✅ 確認排入", key=f"pcf_{_i}", use_container_width=True):
                                    with st.spinner(f"排入「{_nm}」…"):
                                        try:
                                            _rec = R.get_or_build_by_name(
                                                _nm, yt_api_key=YT_KEY, anthropic_client=claude,
                                                supabase=supabase)
                                            if _rec:
                                                MP.add_to_plan(supabase, _d, _sl, _rec["video_id"])
                                                st.success(f"已排入 {_d} {_sl}：{_nm}　👉 到上面「📅 一週餐表」分頁看")
                                                st.toast(f"{_nm} 已排入！", icon="✅")
                                            else:
                                                st.error("找不到影片，換一道試試。")
                                        except Exception as _e:
                                            st.error(f"排入失敗：{_e}")
        else:
            rc1, rc2 = st.columns([3, 1])
            with rc1:
                _hdr = ("🍴 為你精選（每大類各 5 道，可直接排入）"
                        if _cz == "全部" else f"🍴 為你精選 5 道【{_cz}】")
                st.markdown(f"<div class='section-title'>{_hdr}</div>", unsafe_allow_html=True)
            with rc2:
                _regen = st.button("🔄 換一批", key="regen_recs", use_container_width=True)
            if _cz == "全部":
                for _bcz in ["中式", "台式", "西式", "泰式", "馬來西亞", "印尼"]:
                    _rk = f"recs_{_bcz}"
                    if _regen or _rk not in ss:
                        ss[_rk] = random.sample(CUISINE_DISHES[_bcz], 5)
                    st.markdown(f"<div class='rec-cat'>🍽️ {_bcz}</div>", unsafe_allow_html=True)
                    _render_rec_row(_bcz, ss[_rk])
            else:
                _rk = f"recs_{_cz}"
                _pool = CUISINE_DISHES.get(_cz) or CUISINE_DISHES["全部"]
                if _regen or _rk not in ss:
                    ss[_rk] = random.sample(_pool, min(5, len(_pool)))
                _render_rec_row(_cz, ss[_rk])


        st.markdown("<div class='section-title'>🔎 或自己搜尋</div>", unsafe_allow_html=True)
        query = st.text_input("輸入菜名", placeholder="例：麻婆豆腐、咖哩雞、番茄炒蛋")
        if st.button("🔍 搜尋", key="find_search", type="primary"):
            if query.strip():
                kw = CUISINE_KW.get(ss.cuisine, "")
                full_q = (kw + " " + query.strip()).strip()
                with st.spinner("搜尋中…"):
                    try:
                        ss.find_cards = R.search_dishes(full_q, YT_KEY)
                        ss.play_vid = None
                    except Exception as e:
                        st.error(f"搜尋失敗：{e}")
                        ss.find_cards = []
            else:
                st.warning("先輸入菜名再搜尋喔 🌸")

        if ss.find_cards:
            cols = st.columns(3)
            for i, card in enumerate(ss.find_cards):
                with cols[i % 3]:
                    with st.container(border=True):
                        thumb = card.get("thumbnail_url")
                        if thumb:
                            visual = (f"<div class='yt-wrap'><img class='yt-thumb' src='{thumb}'/>"
                                      f"<span class='yt-play'>▶</span></div>")
                        else:
                            visual = "<div class='emoji-hero'>🍳</div>"
                        skin_flag = ""
                        if ss.skin and name_has_trigger(card["title"]):
                            skin_flag = "<span class='warn-flag'> ⚠發物</span>"
                        st.markdown(
                            f"{visual}"
                            f"<div class='yt-card-title'>{card['title']}{skin_flag}</div>"
                            f"<div class='yt-card-chan'>📺 {card['channel']}</div>",
                            unsafe_allow_html=True)
                        if st.button("▶️ 播放", key=f"play_{card['video_id']}",
                                     use_container_width=True):
                            ss.play_vid = card["video_id"]
                            ss.play_title = card["title"]
                        with st.popover("➕ 排入餐表", use_container_width=True):
                            d = st.date_input("排到哪一天", value=date.today(),
                                              key=f"d_{card['video_id']}")
                            sl = st.radio("時段", MP.SLOTS, horizontal=True,
                                          key=f"sl_{card['video_id']}")
                            if st.button("✅ 確認排入", key=f"cf_{card['video_id']}",
                                         use_container_width=True):
                                with st.spinner("抽取食材中…"):
                                    try:
                                        rec = R.get_or_build_recipe(
                                            card, yt_api_key=YT_KEY,
                                            anthropic_client=claude, supabase=supabase)
                                        MP.add_to_plan(supabase, d, sl, card["video_id"])
                                        warn = ""
                                        if ss.skin and ingredients_have_trigger(rec.get("ingredients")):
                                            warn = "（⚠ 含發物）"
                                        st.success(f"已排入 {d} {sl}：{rec['title'][:16]}{warn}")
                                    except Exception as e:
                                        st.error(f"排入失敗：{e}")

        st.markdown("<div id='find-player'></div>", unsafe_allow_html=True)
        if ss.play_vid:
            pc1, pc2 = st.columns([3, 1])
            with pc1:
                st.markdown(f"<div class='section-title'>▶️ 正在播放：{ss.play_title[:44]}</div>",
                            unsafe_allow_html=True)
            with pc2:
                if st.button("✕ 關閉影片", key="close_find_player", use_container_width=True):
                    ss.play_vid = None
                    st.rerun()
            st.video(f"https://www.youtube.com/watch?v={ss.play_vid}")
            st.caption("點播放器右下角可全螢幕。")

if _active_section == "week":
    st.markdown("<div class='section-title'>📅 一週餐表</div>", unsafe_allow_html=True)

    if not CLIENTS_OK:
        st.info("此功能需要 Secrets 設定。")
    else:
        ss = st.session_state
        ss.setdefault("week_anchor", date.today())
        ss.setdefault("play_vid_week", None)
        ss.setdefault("play_title_week", "")
        ss.setdefault("scroll_to_player", False)
        ss.setdefault("people", 4)
        ss.setdefault("skin", False)
        ss.setdefault("cuisine", "全部")

        def render_dish(dish, day, slot):
            vid = dish["video_id"]
            thumb = dish.get("thumbnail_url")
            visual = (f"<img class='yt-thumb' src='{thumb}'/>" if thumb else "")
            flag = " <span class='warn-flag'>⚠</span>" if dish.get("inferred") else ""
            if ss.get("skin") and ingredients_have_trigger(dish.get("ingredients")):
                flag += " <span class='warn-flag'>⚠發物</span>"
            st.markdown(
                f"<div class='day-card'>{visual}"
                f"<div class='dish-mini'>{dish['title'][:40]}{flag}</div>"
                f"{scaled_cost_badge(dish.get('ingredients'), ss.get('people', 4))}</div>",
                unsafe_allow_html=True)
            if st.button("▶️ 播放", key=f"playw_{day}_{slot}_{vid}", use_container_width=True):
                ss.play_vid_week = vid
                ss.play_title_week = dish["title"]
                ss.scroll_to_player = True
                st.toast("▶️ 影片已在下方開始播放")
            with st.expander("🥬 食材"):
                if dish.get("inferred"):
                    st.caption("⚠ 由菜名推測，非影片實際食材，請核對")
                _ings = dish.get("ingredients") or []
                if _ings:
                    for _ing in _ings:
                        _q = _ing.get("qty")
                        _u = _ing.get("unit") or ""
                        _amt = "適量" if (_ing.get("is_fuzzy") or _q is None) else f"{_q:g} {_u}".strip()
                        st.markdown(f"- {_ing.get('name', '')} {_amt}")
                else:
                    st.caption("這支影片的描述沒有附食材清單。")
            if st.button("✕ 移除", key=f"rm_{day}_{slot}_{vid}", use_container_width=True):
                MP.remove_from_plan(supabase, day, slot, vid)
                st.rerun()

        with st.container(border=True):
            st.markdown("<b style='color:#2b211a'>🪄 一鍵生成：依你選的料理大類搜 YouTube 填滿餐表</b>",
                        unsafe_allow_html=True)
            gcz1, gcz2 = st.columns([1.6, 1])
            with gcz1:
                try:
                    gen_cuisine = st.pills("🍽️ 料理大類", CUISINES,
                                           default=ss.get("cuisine", "全部"), key="gen_cuisine") or "全部"
                except Exception:
                    gen_cuisine = st.selectbox("🍽️ 料理大類", CUISINES,
                                               index=CUISINES.index(ss.get("cuisine", "全部")),
                                               key="gen_cuisine_sb")
            with gcz2:
                gen_skin = st.toggle("💧 皮膚敏感（避開發物）", value=ss.get("skin", False), key="gen_skin")
            if gen_skin:
                st.caption(SKIN_NOTE)
            g1, g2 = st.columns([1, 1])
            with g1:
                gen_days = st.slider("要排幾天", 1, 7, 3, key="gen_days")
            with g2:
                gen_slots = st.multiselect("時段", MP.SLOTS, default=MP.SLOTS, key="gen_slots")
            st.caption(f"預估耗用 YouTube 額度約 {gen_days * max(1, len(gen_slots)) * 100} units"
                       f"（每道菜 100u，已抽取過的會走快取）。")
            gb1, gb2 = st.columns([1.4, 1])
            with gb1:
                go = st.button("🪄 一鍵生成本週餐表", key="gen_week", type="primary",
                               use_container_width=True)
            with gb2:
                if st.button("🗑️ 清空本週", key="clear_week", use_container_width=True):
                    ss._confirm_clear = True
            if go:
                if not gen_slots:
                    st.warning("至少選一個時段。")
                else:
                    pool = CUISINE_POOLS.get(gen_cuisine, CUISINE_POOLS["全部"])
                    mon = MP.week_start(ss.week_anchor)
                    # 候選菜名：先濾發物，洗牌後「不重複」依序取用
                    cand = [n for n in pool if not (gen_skin and name_has_trigger(n))]
                    if not cand:
                        cand = list(pool) or ["家常菜"]
                    random.shuffle(cand)
                    jobs = [(d, s2) for d in range(gen_days) for s2 in gen_slots]
                    if len(cand) < len(jobs):
                        st.info(f"「{gen_cuisine}」可用菜色約 {len(cand)} 道，少於要排的 {len(jobs)} 格；"
                                f"為避免重複，部分格子可能留空。可改選「全部」或減少天數／時段。")
                    # 本週已排的影片一併避開，避免和現有的重複
                    try:
                        _ex = MP.get_plan(supabase, mon, mon + timedelta(days=6))
                        used_vids = {r["video_id"] for r in _ex}
                    except Exception:
                        used_vids = set()
                    used_names = set()
                    ci = 0
                    prog = st.progress(0.0, text="開始生成…")
                    done = 0
                    fails = []
                    added = 0
                    for d, slot in jobs:
                        day = mon + timedelta(days=d)
                        # 依序取下一個沒用過的菜名；候選用完就重新洗牌循環
                        name = None
                        while ci < len(cand):
                            c = cand[ci]
                            ci += 1
                            if c not in used_names:
                                name = c
                                break
                        if name is None:
                            random.shuffle(cand)
                            ci = 0
                            name = cand[0] if cand else "家常菜"
                            ci = 1
                        used_names.add(name)
                        prog.progress(done / len(jobs), text=f"搜尋：{name}")
                        try:
                            rec = R.get_or_build_by_name(
                                name, yt_api_key=YT_KEY, anthropic_client=claude,
                                supabase=supabase, throttle=1.2)
                            if not rec:
                                fails.append(f"{name}：找不到對應影片")
                            else:
                                vid = rec["video_id"]
                                if vid in used_vids:
                                    fails.append(f"{name}：與已排重複，略過")
                                elif gen_skin and ingredients_have_trigger(rec.get("ingredients")):
                                    fails.append(f"{name}：含發物已略過")
                                else:
                                    MP.add_to_plan(supabase, day, slot, vid)
                                    used_vids.add(vid)
                                    added += 1
                        except Exception as e:
                            fails.append(f"{name}：{e}")
                        done += 1
                    prog.progress(1.0, text="完成！")
                    if added:
                        st.success(f"已加入 {added} 道，往下看餐表 👇")
                        st.balloons()
                    if fails:
                        st.warning("有 {} 道沒加成功（顯示前 5 個）：\n\n{}".format(len(fails), "\n".join(fails[:5])))

        with st.expander("🔧 進階：預建菜色快取（一次性，解 429）"):
            st.caption("把所有內建菜色的搜尋結果一次存進快取；跑完後一鍵生成就走快取、"
                       "不再打 YouTube、也不會再 429。約 50 道、需 1–2 分鐘，已在快取的會自動跳過。")
            if st.button("開始預建快取", key="warm_cache"):
                alln = sorted({n for lst in CUISINE_DISHES.values() for (n, _l, _h) in lst})
                todo = [n for n in alln if not R.get_cached_video_id(supabase, n)]
                if not todo:
                    st.success("全部菜色都已在快取中，無需預建 🎉")
                else:
                    pw = st.progress(0.0, text="預建中…")
                    ok = 0
                    bad = []
                    for wi, wn in enumerate(todo):
                        pw.progress(wi / len(todo), text=f"預建：{wn}（{wi + 1}/{len(todo)}）")
                        try:
                            wr = R.get_or_build_by_name(wn, yt_api_key=YT_KEY,
                                                        anthropic_client=claude,
                                                        supabase=supabase, throttle=1.5)
                            if wr:
                                ok += 1
                            else:
                                bad.append(wn)
                        except Exception as we:
                            bad.append(f"{wn}：{str(we)[:40]}")
                    pw.progress(1.0, text="完成")
                    st.success(f"已預建 {ok} 道進快取。")
                    if bad:
                        st.warning("有 {} 道仍失敗（多半是 429，稍等片刻再按一次即可，"
                                   "已成功的會跳過）：\n\n{}".format(len(bad), "\n".join(str(b) for b in bad[:10])))

        if ss.get("_confirm_clear"):
            st.warning("確定要清空本週所有已排的菜嗎？此動作無法復原。")
            cc1, cc2 = st.columns(2)
            if cc1.button("✅ 確定清空", key="clear_yes", type="primary", use_container_width=True):
                MP.clear_week(supabase, ss.week_anchor)
                ss._confirm_clear = False
                ss.play_vid_week = None
                st.rerun()
            if cc2.button("取消", key="clear_no", use_container_width=True):
                ss._confirm_clear = False
                st.rerun()

        nav1, nav2, nav3 = st.columns([1, 2, 1])
        with nav1:
            if st.button("← 上一週", use_container_width=True):
                ss.week_anchor -= timedelta(days=7)
        with nav3:
            if st.button("下一週 →", use_container_width=True):
                ss.week_anchor += timedelta(days=7)
        mon = MP.week_start(ss.week_anchor)
        with nav2:
            st.markdown(f"<div style='text-align:center;font-weight:900;color:#2b211a'>"
                        f"{mon} ～ {mon + timedelta(days=6)}</div>", unsafe_allow_html=True)

        week_names = ["一", "二", "三", "四", "五", "六", "日"]
        view = st.radio("檢視方式", ["📆 單日", "🗓️ 整週"], horizontal=True, key="week_view")

        grid = {}
        try:
            grid = MP.get_week_plan(supabase, ss.week_anchor)
            if view == "📆 單日":
                day_labels = [f"週{week_names[i]}" for i in range(7)]
                default_i = (date.today() - mon).days
                default_i = default_i if 0 <= default_i <= 6 else 0
                sel = st.radio("選一天", day_labels, index=default_i, horizontal=True,
                               key="day_sel", label_visibility="collapsed")
                di = day_labels.index(sel)
                day = mon + timedelta(days=di)
                st.markdown(f"<div class='day-head'><span>{DAY_EMOJIS[di]} 週{week_names[di]}</span>"
                            f"<span class='day-cost'>{day.month}/{day.day}</span></div>",
                            unsafe_allow_html=True)
                for slot in MP.SLOTS:
                    st.markdown(f"<div class='slot-label'>{'🍱 午餐' if slot == '午' else '🌙 晚餐'}</div>",
                                unsafe_allow_html=True)
                    dishes = grid.get((str(day), slot), [])
                    if not dishes:
                        st.markdown("<div class='dish-mini' style='color:#b39a6e'>· 未排</div>",
                                    unsafe_allow_html=True)
                    for dish in dishes:
                        render_dish(dish, day, slot)
            else:
                day_cols = st.columns(7)
                for d in range(7):
                    day = mon + timedelta(days=d)
                    with day_cols[d]:
                        st.markdown(f"<div class='day-head'><span>{DAY_EMOJIS[d]} 週{week_names[d]}</span>"
                                    f"<span class='day-cost'>{day.month}/{day.day}</span></div>",
                                    unsafe_allow_html=True)
                        for slot in MP.SLOTS:
                            st.markdown(f"<div class='slot-label'>{'🍱 午餐' if slot == '午' else '🌙 晚餐'}</div>",
                                        unsafe_allow_html=True)
                            dishes = grid.get((str(day), slot), [])
                            if not dishes:
                                st.markdown("<div class='dish-mini' style='color:#b39a6e'>· 未排</div>",
                                            unsafe_allow_html=True)
                            for dish in dishes:
                                render_dish(dish, day, slot)
        except Exception as e:
            st.error(f"餐表載入錯誤：{e}")
        st.session_state["_grid_cache"] = grid

        st.markdown("<div id='player-anchor'></div>", unsafe_allow_html=True)
        if ss.get("play_vid_week"):
            pc1, pc2 = st.columns([3, 1])
            with pc1:
                st.markdown(f"<div class='section-title'>▶️ 正在播放：{ss.play_title_week[:44]}</div>",
                            unsafe_allow_html=True)
            with pc2:
                if st.button("✕ 關閉影片", key="close_week_player", use_container_width=True):
                    ss.play_vid_week = None
                    ss.scroll_to_player = False
                    st.rerun()
            st.video(f"https://www.youtube.com/watch?v={ss.play_vid_week}")
            st.caption("點播放器右下角可全螢幕。")
            if ss.get("scroll_to_player"):
                components.html(
                    "<script>try{var d=window.parent.document;"
                    "var t=d.getElementById('player-anchor');"
                    "if(t){t.scrollIntoView({behavior:'smooth',block:'center'});}}catch(e){}</script>",
                    height=0)
                ss.scroll_to_player = False

if _active_section == "shop":
    st.markdown("<div class='section-title'>🛒 本週採買清單（YouTube 食材自動加總）</div>",
                unsafe_allow_html=True)
    if not CLIENTS_OK:
        st.info("此功能需要 Secrets 設定。")
    else:
        grid = st.session_state.get("_grid_cache")
        if grid is None:
            try:
                grid = MP.get_week_plan(supabase, st.session_state.get("week_anchor", date.today()))
            except Exception:
                grid = {}
        recipes = MP.collect_week_recipes(grid)
        if not recipes:
            st.info("本週還沒排菜，先去「📅 一週餐表」排幾道吧 🌸")
        else:
            try:
                shopping = R.build_shopping_list(recipes)
                total_lo = sum(estimate_dish_cost(r.get("ingredients"))[0]
                               for r in recipes if estimate_dish_cost(r.get("ingredients")))
                total_hi = sum(estimate_dish_cost(r.get("ingredients"))[1]
                               for r in recipes if estimate_dish_cost(r.get("ingredients")))
                _mid = (total_lo + total_hi) / 2
                _per = _mid / len(recipes) if recipes else 0
                st.markdown(
                    f"<div style='background:#2b211a;color:#fff;border-radius:20px;"
                    f"padding:22px 26px;margin-bottom:18px;display:flex;flex-wrap:wrap;"
                    f"align-items:center;gap:8px 36px;'>"
                    f"<div><div style='font-size:12px;letter-spacing:2px;text-transform:uppercase;"
                    f"color:rgba(255,255,255,.55);'>預估總花費 ESTIMATED TOTAL</div>"
                    f"<div class='serif' style='font-weight:900;font-size:2.4rem;margin-top:4px;'>"
                    f"RM {total_lo} – {total_hi}</div></div>"
                    f"<div style='margin-left:auto;text-align:right;font-size:13px;"
                    f"color:rgba(255,255,255,.78);line-height:1.9;'>"
                    f"🍽️ 本週 {len(recipes)} 餐<br>"
                    f"每餐平均約 <b style='color:#e7b04a'>RM {_per:.0f}</b></div>"
                    f"<div style='flex-basis:100%;font-size:12px;color:rgba(255,255,255,.5);'>"
                    f"依市場行情粗估，未含米油鹽等常備品</div>"
                    f"</div>",
                    unsafe_allow_html=True)
                cat_emojis = {"蔬菜": "🥬", "肉類": "🍗", "海鮮": "🐟", "蛋豆製品": "🥚",
                              "調味料": "🧄", "乾貨雜貨": "🛍️", "其他": "🧺"}
                cols = st.columns(3)
                lines = ["🌸 本週採買清單", f"估計買菜費：RM {total_lo} – {total_hi}", ""]
                idx = 0
                for cat, items in shopping.items():
                    with cols[idx % 3]:
                        items_html = "".join(
                            f"<div style='padding:4px 0;border-bottom:1px dashed #f4ecdd;"
                            f"display:flex;justify-content:space-between'>"
                            f"<span>☐ {it['name']}</span>"
                            f"<b style='color:#c0492b'>{it['amount']}</b></div>"
                            for it in items)
                        st.markdown(f"<div class='card'><b style='color:#2b211a'>"
                                    f"{cat_emojis.get(cat, '🛍️')} {cat}</b><br>{items_html}</div>",
                                    unsafe_allow_html=True)
                    lines.append(f"【{cat}】")
                    lines += [f"  □ {it['name']}  {it['amount']}" for it in items]
                    lines.append("")
                    idx += 1
                lines += ["—" * 18] + MARKET_TIPS[:5]
                text = "\n".join(lines)
                dl1, dl2 = st.columns(2)
                with dl1:
                    st.download_button("⬇️ 下載採買清單（帶去市場）", text,
                                       file_name="本週採買清單.txt", use_container_width=True)
                with dl2:
                    _wa = text if len(text) <= 1500 else text[:1500] + "\n…"
                    st.link_button("💬 用 WhatsApp 分享清單",
                                   "https://wa.me/?text=" + urllib.parse.quote(_wa),
                                   use_container_width=True)
            except Exception as e:
                st.error(f"採買清單錯誤：{e}")


# ================ 💰 花費總覽 ================
if _active_section == "budget":
    st.markdown("<div class='section-title'>💰 本週每日餐費估算（依市場行情粗估）</div>",
                unsafe_allow_html=True)
    if not CLIENTS_OK:
        st.info("此功能需要 Secrets 設定。")
    else:
        grid = st.session_state.get("_grid_cache")
        if grid is None:
            try:
                grid = MP.get_week_plan(supabase, st.session_state.get("week_anchor", date.today()))
            except Exception:
                grid = {}
        if not grid:
            st.info("本週還沒排菜。")
        else:
            mon = MP.week_start(st.session_state.get("week_anchor", date.today()))
            week_names = ["一", "二", "三", "四", "五", "六", "日"]
            rows = []
            for d in range(7):
                day = mon + timedelta(days=d)
                lunch = grid.get((str(day), "午"), [])
                dinner = grid.get((str(day), "晚"), [])
                lc = sum(dish_mid_cost(x.get("ingredients")) for x in lunch)
                dc = sum(dish_mid_cost(x.get("ingredients")) for x in dinner)
                rows.append({"星期": f"週{week_names[d]}",
                             "午餐": "、".join(x["title"][:10] for x in lunch) or "—",
                             "晚餐": "、".join(x["title"][:10] for x in dinner) or "—",
                             "當日估費": round(lc + dc)})
            df = pd.DataFrame(rows)
            b1, b2 = st.columns([1.3, 1])
            with b1:
                st.dataframe(df[["星期", "午餐", "晚餐", "當日估費"]],
                             use_container_width=True, hide_index=True)
            with b2:
                chart_df = df.set_index("星期")[["當日估費"]].rename(columns={"當日估費": "RM"})
                st.bar_chart(chart_df, color="#c0492b")
                wk = int(df["當日估費"].sum())
                avg = df["當日估費"].mean()
                st.markdown(f"<div class='card'>📌 本週估計合計約 <b style='color:#c0492b'>RM {wk}</b>，"
                            f"平均每天約 <b style='color:#c0492b'>RM {avg:.0f}</b>"
                            f"（粗估，未含米油鹽等常備品）</div>", unsafe_allow_html=True)


# ================ 👵 樂齡專區 ================
if _active_section == "elderly":
    st.markdown("<div class='section-title'>👵 適合家有年長者的食譜</div>",
                unsafe_allow_html=True)
    st.session_state.setdefault("people_eld", 4)
    _es1, _es2 = st.columns([1, 1.6])
    with _es1:
        st.session_state.people_eld = people_stepper(st.session_state.people_eld, "elder")
    n_eld = st.session_state.people_eld
    elder_recipes = [r for r in RECIPES if r.get("elderly_ok")]
    cols = st.columns(3)
    for idx, r in enumerate(elder_recipes):
        lo2, hi2 = scaled_cost(r, n_eld)
        with cols[idx % 3]:
            st.markdown(f"<div class='day-card'><div class='emoji-hero'>{r['emoji']}</div>"
                        f"<div class='meal-name'>{r['name']}</div>"
                        f"<span class='cost-badge'>💰 RM {lo2} – {hi2}</span>"
                        f"<div class='note'>👵 {r.get('elderly_note', '')}</div></div>",
                        unsafe_allow_html=True)
    st.markdown("<div class='card'><b style='color:#2b211a'>🤍 為長輩備餐的小提醒</b><br>" +
                "<br>".join(ELDERLY_TIPS) + "</div>", unsafe_allow_html=True)


# ================ 💡 小貼士 ================
if _active_section == "tips":
    t1, t2 = st.columns(2)
    with t1:
        st.markdown("<div class='card'><b style='color:#2b211a'>🧺 市場採買小貼士</b><br>" +
                    "<br>".join(MARKET_TIPS) + "</div>", unsafe_allow_html=True)
    with t2:
        st.markdown("""<div class='card'><b style='color:#2b211a'>🌸 使用小撇步</b><br>
        ① 「📊 市場行情」先看這個月什麼變便宜<br>
        ② 「🔍 找菜」輸入想煮的菜 → 卡片結果可直接播放、排進餐表<br>
        ③ 「📅 一週餐表」可手動排，或按 🪄 一鍵生成填滿一週<br>
        ④ 「🛒 採買清單」自動加總食材＋估價，可下載或 WhatsApp 分享<br>
        ⑤ 「💰 花費總覽」看本週每天大概要花多少
        </div>""", unsafe_allow_html=True)
        st.markdown("""<div class='card'><b style='color:#2b211a'>📍 之後可以擴充</b><br>
        ・更精準的估價（接 LLM 依亞庇市價估每道菜）<br>
        ・收藏「我家最愛」常用菜單<br>
        ・節慶菜單（農曆新年、中秋圍爐）
        </div>""", unsafe_allow_html=True)

st.markdown("<p style='text-align:center;color:#b39a6e;font-size:0.8rem;margin-top:18px'>"
            "🌸 今天煮什麼？ · 為亞庇的妳設計 · 估價為市場常見推算，實際以當日市價為準</p>",
            unsafe_allow_html=True)
