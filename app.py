# ============================================================
# Gujarat Survey Map Maker  —  version 2 (October 2026)
#
# Publication-ready district / taluka maps of Gujarat with survey
# points, plus a zoomable interactive map.
#
# What changed from version 1
#   * The map is drawn only when you press "Make map". Changing a
#     setting no longer re-draws a 300-dpi map on every click.
#   * Legend, locator map, compass and scale bar are laid out
#     automatically and no longer cover the map.
#   * District and taluka maps share one set of controls.
#   * CSV (any encoding, comma/semicolon/tab) and Excel files are read
#     robustly; degree-minute-second coordinates and swapped
#     lat/long columns are handled.
#   * Duplicate taluka names (Mandvi, Kalol, Mahuva, Mangrol) are kept
#     apart; broken boundary shapes are repaired on loading.
#   * Downloads: PNG and TIFF (300 or 600 dpi) and vector PDF.
# ============================================================
from __future__ import annotations

import html
import inspect
import io
import json
import re
import textwrap
import threading
from pathlib import Path

import geopandas as gpd
import matplotlib as mpl
import matplotlib.patheffects as pe
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import shapely
import streamlit as st
from matplotlib import font_manager
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.collections import PatchCollection
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.offsetbox import AnchoredOffsetbox, AuxTransformBox
from matplotlib.patches import Circle, Patch, PathPatch, Rectangle
from matplotlib.patches import Polygon as MplPolygon
from matplotlib.path import Path as MplPath
from matplotlib.text import Text
from matplotlib.transforms import Bbox
from PIL import Image

st.set_page_config(
    page_title="Gujarat Survey Map Maker",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded",
)

mpl.rcParams.update({"pdf.fonttype": 42, "svg.fonttype": "none", "axes.unicode_minus": False})

# Serif look for the app's text. Only text elements are targeted so that
# Streamlit's own icons (expander arrows, upload icon) keep their icon font.
st.markdown(
    """
<style>
.stApp p, .stApp li, .stApp label, .stApp h1, .stApp h2, .stApp h3,
.stApp input, .stApp textarea {
    font-family: "Times New Roman", Times, "Liberation Serif", serif;
}
</style>
""",
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────
APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DISTRICT_FILE = DATA_DIR / "gujarat.geojson"
TALUKA_FILE = DATA_DIR / "gujarat_talukas.geojson"

DISTRICT_COLS = ["district_name", "dtname", "NAME_2", "district", "Dist_Name", "REGNAME"]
TALUKA_COLS = ["sdtname", "NAME_3", "taluka", "Taluka_Name", "taluka_name", "TALUKA",
               "Sub_Distri", "subdistrict", "tehsil_name", "Tehsil"]
TALUKA_DISTRICT_COLS = ["dtname", "district", "District", "DISTRICT", "district_name", "NAME_2"]

STATIC_TOL = 0.0003   # ~30 m: invisible on an A4 map, halves drawing time
WEB_TOL = 0.0015      # ~150 m: keeps the interactive map light in the browser
MAX_TILES = 64

# Spelling variants of district names → one key
_DIST_ALIASES = {
    "ahmedabad": "ahmadabad", "dahod": "dohad", "aravalli": "aravali",
    "chotaudaipur": "chhotaudaipur", "chhotaudepur": "chhotaudaipur",
    "chotaudepur": "chhotaudaipur", "panchmahal": "panchmahals",
    "mehsana": "mahesana", "kutch": "kachchh", "kachh": "kachchh",
    "dang": "thedangs", "dangs": "thedangs", "devbhoomidwarka": "devbhumidwarka",
}

PRESETS = {
    "Middle Gujarat (AAU area)": ["ahmedabad", "anand", "vadodara", "kheda", "panchmahal",
                                  "dahod", "mahisagar", "chhotaudepur", "botad"],
    "South Gujarat (NAU area)": ["navsari", "valsad", "surat", "tapi", "dang",
                                 "bharuch", "narmada"],
    "All districts": "ALL",
    "Clear selection": [],
}
DEFAULT_DISTRICTS = PRESETS["Middle Gujarat (AAU area)"]

BASEMAPS = {
    "Plain white": None,
    "Light grey (Esri)": "Esri.WorldGrayCanvas",
    "Street map (OpenStreetMap)": "OpenStreetMap.Mapnik",
    "Topographic (Esri)": "Esri.WorldTopoMap",
    "Satellite (Esri)": "Esri.WorldImagery",
}
TILE_HEADERS = {"User-Agent": "GujaratSurveyMapMaker/2.0 (+https://github.com/vkcvaibhav-eng/map-maker-)"}

FILL_EACH, FILL_ONE, FILL_NONE = "Different colour for each", "One colour for all", "No fill (outline only)"
PALETTES = {
    "Pastel": ("qual", "Pastel1"), "Soft": ("qual", "Set3"), "Bright": ("qual", "Set2"),
    "Greens": ("seq", "Greens"), "Blues": ("seq", "Blues"), "Oranges": ("seq", "Oranges"),
    "Greys (B&W print)": ("seq", "Greys"),
}

SHAPES = ["Circle", "Map pin", "Triangle", "Square", "Diamond", "Star"]
SIZES = ["Small", "Medium", "Large"]
SCATTER_SIZE = {"Circle": (18, 36, 70), "Map pin": (260, 420, 700), "Triangle": (22, 42, 80),
                "Square": (16, 32, 60), "Diamond": (16, 30, 56), "Star": (45, 85, 150)}
LEGEND_MS = {"Circle": 8, "Map pin": 14, "Triangle": 8.5, "Square": 7.5, "Diamond": 7, "Star": 12}
WEB_RADIUS = {"Small": 4, "Medium": 6, "Large": 8}
LABEL_MODES = ["No labels", "Names", "Short names (full names in legend)", "Numbers (names in legend)"]
KEY_MODES = LABEL_MODES[2:]
POINT_COLOURS = ["#e41a1c", "#377eb8", "#4daf4a", "#984ea3", "#ff7f00", "#a65628", "#f781bf",
                 "#1b9e77", "#d95f02", "#7570b3", "#e7298a", "#66a61e", "#e6ab02", "#666666"]
LAYER_DEFAULTS = [("Survey points", "Circle", "#E41A1C"), ("Important locations", "Map pin", "#FFD700"),
                  ("Point layer 3", "Triangle", "#377EB8"), ("Point layer 4", "Square", "#4DAF4A"),
                  ("Point layer 5", "Diamond", "#984EA3"), ("Point layer 6", "Star", "#FF7F00")]

PANEL_OPTS = ["Side panel", "Inside map – top left", "Inside map – top right",
              "Inside map – bottom left", "Inside map – bottom right", "Don't show"]
CORNER_OPTS = ["Top right", "Top left", "Bottom right", "Bottom left", "Don't show"]
LOC_CODE = {"top right": 1, "top left": 2, "bottom left": 3, "bottom right": 4}

SAMPLE_CSV = (
    "Latitude,Longitude,Name,Short Name,Group\n"
    "20.92405,72.91038,Navsari Agricultural University,NAU,University\n"
    "21.13399,73.10306,Bardoli Sugar Factory,BSF,Industry\n"
    "21.17024,72.80125,Main Cotton Research Station,MCRS,Research station\n"
    "21.10017,73.39466,Polytechnic in Agriculture Vyara,PAV,College\n"
)


def district_key(name) -> str:
    k = re.sub(r"[^a-z]", "", str(name).lower())
    return _DIST_ALIASES.get(k, k)


# ─────────────────────────────────────────────────────────────
# MARKERS
# ─────────────────────────────────────────────────────────────
def _pin_path(centered: bool) -> MplPath:
    """Map-pin teardrop. Tip at the origin (so the tip marks the spot),
    or centred for the legend."""
    D, R = 2.5, 1.0
    th = np.arcsin(R / D)
    a = np.linspace(np.pi + th, -th, 60)
    outer = np.column_stack([np.r_[R * np.cos(a), 0.0], np.r_[R * np.sin(a) + D, 0.0]])
    outer = np.vstack([outer, outer[:1]])
    ai = np.linspace(0, 2 * np.pi, 40)
    inner = np.column_stack([0.4 * np.cos(ai), 0.4 * np.sin(ai) + D])
    verts = np.vstack([outer, inner])
    if centered:
        verts = verts - [0.0, (D + R) / 2]
    codes = np.full(len(verts), MplPath.LINETO, dtype=np.uint8)
    codes[0] = MplPath.MOVETO
    codes[len(outer)] = MplPath.MOVETO
    return MplPath(verts, codes)


_PIN, _PIN_LEGEND = _pin_path(False), _pin_path(True)
MARKER = {"Circle": "o", "Map pin": _PIN, "Triangle": "^", "Square": "s", "Diamond": "D", "Star": "*"}
LEGEND_MARKER = {**MARKER, "Map pin": _PIN_LEGEND}


# ─────────────────────────────────────────────────────────────
# SHARED RESOURCES (one per server process)
# ─────────────────────────────────────────────────────────────
@st.cache_resource
def _render_lock() -> threading.Lock:
    # One map at a time: keeps memory low on Streamlit Cloud and keeps
    # matplotlib's font settings from mixing between users.
    return threading.Lock()


@st.cache_resource
def font_names() -> dict:
    have = {f.name for f in font_manager.fontManager.ttflist}

    def first(cands):
        return next((c for c in cands if c in have), cands[-1])

    return {
        "Times New Roman": first(["Times New Roman", "Times", "Liberation Serif", "Nimbus Roman",
                                  "TeX Gyre Termes", "STIXGeneral", "DejaVu Serif"]),
        "Arial": first(["Arial", "Liberation Sans", "Helvetica", "Nimbus Sans",
                        "TeX Gyre Heros", "DejaVu Sans"]),
    }


# ─────────────────────────────────────────────────────────────
# GEOMETRY HELPERS
# ─────────────────────────────────────────────────────────────
def _find_col(columns, candidates):
    lower = {str(c).lower(): c for c in columns}
    for cand in candidates:
        if cand.lower() in lower:
            return lower[cand.lower()]
    return None


def _orient(geom):
    if hasattr(shapely, "orient_polygons"):
        return shapely.orient_polygons(geom)
    from shapely.geometry.polygon import orient
    parts = [orient(p, 1.0) for p in shapely.get_parts(geom)]
    return parts[0] if len(parts) == 1 else shapely.MultiPolygon(parts)


def _polygonal(geom):
    """Valid (Multi)Polygon from any geometry; drops stray lines and points."""
    if geom is None or geom.is_empty:
        return None
    if not geom.is_valid:
        geom = shapely.make_valid(geom)
    parts = [p for p in shapely.get_parts(geom) if p.geom_type in ("Polygon", "MultiPolygon")]
    if not parts:
        return None
    g = shapely.union_all(parts) if len(parts) > 1 else parts[0]
    return _orient(g)


def _simplify(geoms, tol):
    geoms = np.asarray(geoms, dtype=object)
    try:   # keeps shared borders identical, so no slivers appear
        out = shapely.coverage_simplify(geoms, tol)
    except Exception:
        out = shapely.simplify(geoms, tol, preserve_topology=True)
    return [_polygonal(g) or o for g, o in zip(out, geoms)]


def _drop_small_holes(geom, min_area=1e-4):
    polys = []
    for p in shapely.get_parts(geom):
        if p.geom_type != "Polygon":
            continue
        holes = [r for r in p.interiors if shapely.Polygon(r).area >= min_area]
        polys.append(shapely.Polygon(p.exterior, holes))
    if not polys:
        return geom
    return _polygonal(polys[0] if len(polys) == 1 else shapely.MultiPolygon(polys))


def _geom_path(geom) -> MplPath:
    verts, codes = [], []
    for poly in shapely.get_parts(geom):
        if poly.geom_type != "Polygon" or poly.is_empty:
            continue
        for ring in (poly.exterior, *poly.interiors):
            xy = np.asarray(ring.coords)[:, :2]
            if len(xy) < 4:
                continue
            c = np.full(len(xy), MplPath.LINETO, dtype=np.uint8)
            c[0], c[-1] = MplPath.MOVETO, MplPath.CLOSEPOLY
            verts.append(xy)
            codes.append(c)
    if not verts:
        return MplPath(np.zeros((1, 2)))
    return MplPath(np.concatenate(verts), np.concatenate(codes))


def _label_point(geom):
    big = max(shapely.get_parts(geom), key=lambda p: p.area)
    try:
        from shapely.ops import polylabel
        pt = polylabel(big, tolerance=0.002)
    except Exception:
        pt = big.representative_point()
    return pt.x, pt.y


def _finish_level(units: gpd.GeoDataFrame, outlines: gpd.GeoDataFrame) -> dict:
    units = units.reset_index(drop=True)
    units["path"] = [_geom_path(g) for g in units.geometry]
    pts = [_label_point(g) for g in units.geometry]
    units["lx"], units["ly"] = [p[0] for p in pts], [p[1] for p in pts]
    _ = units.sindex

    outlines = outlines.reset_index(drop=True)
    outlines["geometry"] = [_drop_small_holes(g) for g in outlines.geometry]
    state = _drop_small_holes(shapely.union_all(units.geometry.values))

    web = units[["label", "name", "district", "geometry"]].copy()
    web_geoms = _simplify(web.geometry.values, WEB_TOL)
    web["geometry"] = shapely.transform(np.array(web_geoms, dtype=object), lambda c: np.round(c, 4))
    return {
        "units": units,
        "outline_paths": [_geom_path(g) for g in outlines.geometry],
        "state_path": _geom_path(state),
        "bounds": tuple(float(v) for v in units.total_bounds),
        "web": json.loads(web.to_json(drop_id=True)),
    }


@st.cache_resource(show_spinner="Loading Gujarat boundaries (first time only)…")
def load_boundaries() -> dict:
    # ── districts
    raw = gpd.read_file(DISTRICT_FILE)
    raw = raw.set_crs(4326) if raw.crs is None else raw.to_crs(4326)
    col = _find_col(raw.columns, DISTRICT_COLS)
    if col is None:
        raise ValueError(f"No district-name column in {DISTRICT_FILE.name}. Expected one of {DISTRICT_COLS}.")
    names = raw[col].astype(str).str.strip()
    geoms = [_polygonal(g) for g in raw.geometry.values]
    keep = [bool(n) and n.lower() != "nan" and g is not None for n, g in zip(names, geoms)]
    d = gpd.GeoDataFrame({"label": names[keep].values},
                         geometry=[g for g, k in zip(geoms, keep) if k], crs=4326)
    d = d.dissolve(by="label", as_index=False)
    d["geometry"] = _simplify(d.geometry.values, STATIC_TOL)
    d["name"] = d["label"]
    d["district"] = d["label"]
    d["selectable"] = True
    d = d.sort_values("label").reset_index(drop=True)
    district_display = {district_key(n): n for n in d["label"]}
    out = {"district": _finish_level(d, d[["district", "geometry"]].copy())}

    # ── talukas
    raw = gpd.read_file(TALUKA_FILE)
    raw = raw.set_crs(4326) if raw.crs is None else raw.to_crs(4326)
    tcol = _find_col(raw.columns, TALUKA_COLS)
    dcol = _find_col(raw.columns, TALUKA_DISTRICT_COLS)
    if tcol is None:
        raise ValueError(f"No taluka-name column in {TALUKA_FILE.name}. Expected one of {TALUKA_COLS}.")
    tnames = raw[tcol].fillna("").astype(str).str.strip().replace({"nan": ""})
    if dcol is not None:
        draw = raw[dcol].fillna("").astype(str).str.strip()
        dnames = [district_display.get(district_key(x), x.title()) for x in draw]
    else:
        dnames = [""] * len(raw)
    geoms = [_polygonal(g) for g in raw.geometry.values]
    t = gpd.GeoDataFrame({"name": tnames.values, "district": dnames}, geometry=geoms, crs=4326)
    t = t[t.geometry.notna()].reset_index(drop=True)
    t["geometry"] = _simplify(t.geometry.values, STATIC_TOL)
    t["selectable"] = t["name"] != ""
    dup = t["name"].duplicated(keep=False) & t["selectable"]
    labels = []
    for nm, dn, sel, dp in zip(t["name"], t["district"], t["selectable"], dup):
        if not sel:
            labels.append("Rann of Kachchh" if district_key(dn) == "kachchh" else f"Unnamed area ({dn})")
        elif dp and dn:
            labels.append(f"{nm} ({dn})")
        else:
            labels.append(nm)
    t["label"] = labels
    outlines = t.dissolve(by="district", as_index=False)[["district", "geometry"]]
    out["taluka"] = _finish_level(t, outlines)
    out["district_names"] = list(d["label"])
    return out


# ─────────────────────────────────────────────────────────────
# COLOURS
# ─────────────────────────────────────────────────────────────
def palette_colours(name: str) -> list[str]:
    kind, cmap_name = PALETTES.get(name, PALETTES["Pastel"])
    cmap = mpl.colormaps[cmap_name]
    if kind == "qual":
        cols = [mpl.colors.to_hex(c) for c in cmap.colors]
        cols = [c for c in cols if c.lower() not in ("#f2f2f2", "#d9d9d9")]
    else:
        cols = [mpl.colors.to_hex(cmap(x)) for x in np.linspace(0.2, 0.62, 5)]
    return cols


@st.cache_data(show_spinner=False, max_entries=64)
def area_colours(level: str, labels: tuple, palette: str) -> dict:
    """Colour each highlighted area so that neighbours never share a colour."""
    units = load_boundaries()[level]["units"]
    sub = units[units["label"].isin(labels)].reset_index(drop=True)
    cols = palette_colours(palette)
    if sub.empty:
        return {}
    a, b = sub.sindex.query(sub.geometry.values, predicate="intersects")
    nbrs = {i: set() for i in range(len(sub))}
    for i, j in zip(a, b):
        if i != j:
            nbrs[i].add(j)
            nbrs[j].add(i)
    order = sorted(range(len(sub)), key=lambda i: (-len(nbrs[i]), sub.at[i, "label"]))
    use = [0] * len(cols)
    pick = {}
    for i in order:
        taken = {pick[j] for j in nbrs[i] if j in pick}
        free = [c for c in range(len(cols)) if c not in taken] or list(range(len(cols)))
        c = min(free, key=lambda k: (use[k], k))
        pick[i] = c
        use[c] += 1
    return {sub.at[i, "label"]: cols[pick[i]] for i in range(len(sub))}


def sorted_groups(values) -> list[str]:
    def key(v):
        try:
            return (0, float(v), "")
        except ValueError:
            return (1, 0.0, v.lower())
    return sorted({str(v) for v in values}, key=key)


def group_colours(groups) -> dict:
    return {g: POINT_COLOURS[i % len(POINT_COLOURS)] for i, g in enumerate(groups)}


# ─────────────────────────────────────────────────────────────
# READING POINT FILES
# ─────────────────────────────────────────────────────────────
_NUM = re.compile(r"[-+]?\d+(?:[.,]\d+)?")


def parse_coord(v) -> float:
    """Decimal degrees, '21.17 N', or degrees-minutes-seconds (21°10'12"N)."""
    if v is None:
        return np.nan
    if isinstance(v, (int, float, np.number)):
        return float(v)
    s = str(v).strip()
    if not s or s.lower() in ("nan", "none", "na", "-"):
        return np.nan
    try:
        return float(s)
    except ValueError:
        pass
    nums = [float(x.replace(",", ".")) for x in _NUM.findall(s)]
    if not nums:
        return np.nan
    val = abs(nums[0]) + (nums[1] / 60 if len(nums) > 1 else 0) + (nums[2] / 3600 if len(nums) > 2 else 0)
    neg = nums[0] < 0 or bool(re.search(r"[SW]\s*$", s.upper())) or s.upper().startswith(("S", "W"))
    return -val if neg else val


def _norm(c) -> str:
    return re.sub(r"[^a-z]", "", str(c).lower())


def _coord_columns(cols):
    lat = lon = None
    for c in cols:
        n = _norm(c)
        if lat is None and (n.startswith("lat") or n.endswith(("latitude", "lat")) or n in ("y", "northing")):
            lat = c
        elif lon is None and (n.startswith(("lon", "lng", "long"))
                              or n.endswith(("longitude", "lon", "lng", "long")) or n in ("x", "easting")):
            lon = c
    return lat, lon


def guess_name_col(cols):
    norm = {c: _norm(c) for c in cols}
    for c, n in norm.items():
        if n == "name":
            return c
    for c, n in norm.items():
        if "name" in n and "short" not in n:
            return c
    for word in ("location", "place", "village", "site", "locality", "station", "centre", "center",
                 "farm", "taluka", "district", "label", "lable"):
        for c, n in norm.items():
            if word in n:
                return c
    return None


def guess_short_col(cols):
    for c in cols:
        n = _norm(c)
        if n in ("shortname", "short", "abbr", "abbreviation", "code", "shortcode", "acronym") \
                or "short" in n or "abbr" in n:
            return c
    return None


def _read_table(data: bytes, fname: str) -> pd.DataFrame:
    if fname.lower().endswith((".xlsx", ".xlsm")):
        return pd.read_excel(io.BytesIO(data), dtype=object)
    text = None
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        raise ValueError("The file is empty.")
    sep = max([",", ";", "\t", "|"], key=lines[0].count)
    return pd.read_csv(io.StringIO(text), sep=sep, dtype=str, skipinitialspace=True)


def _cell_str(v) -> str:
    """Text for a table cell; Excel's 2023.0 becomes 2023."""
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    s = str(v).strip()
    return "" if s.lower() == "nan" else s


def _rows(idx) -> str:
    rows = [str(i + 2) for i in idx]   # +2 = header row + 1-based numbering
    return ", ".join(rows[:8]) + (" …" if len(rows) > 8 else "")


@st.cache_data(show_spinner=False, max_entries=60)
def read_points(data: bytes, fname: str):
    """Returns (DataFrame with _lat/_lon columns, notes, error)."""
    notes = []
    try:
        df = _read_table(data, fname)
    except Exception as exc:
        return None, [], f"Could not read this file ({exc}). Save it as CSV or .xlsx and try again."
    df.columns = [re.sub(r"\s+", " ", str(c).replace("﻿", "")).strip() for c in df.columns]
    df = df.loc[:, [not (c.startswith("Unnamed") and df[c].isna().all()) for c in df.columns]]
    df = df.dropna(how="all").reset_index(drop=True)
    if df.empty:
        return None, [], "The file has no data rows."

    lat_c, lon_c = _coord_columns(df.columns)
    if lat_c is None or lon_c is None:
        # fall back to columns whose numbers look like Gujarat coordinates
        num = {c: pd.to_numeric(df[c], errors="coerce") for c in df.columns}
        lat_c = lat_c or next((c for c, v in num.items() if v.notna().mean() > 0.8 and v.between(19, 26).mean() > 0.8), None)
        lon_c = lon_c or next((c for c, v in num.items() if v.notna().mean() > 0.8 and v.between(67, 76).mean() > 0.8), None)
        if lat_c is None or lon_c is None:
            return None, [], ("Could not find the Latitude and Longitude columns. Columns found: "
                              + ", ".join(map(str, df.columns)) + ". Name them 'Latitude' and 'Longitude'.")
        notes.append(f"Using '{lat_c}' as latitude and '{lon_c}' as longitude.")

    lat = df[lat_c].map(parse_coord).astype(float)
    lon = df[lon_c].map(parse_coord).astype(float)
    if lat.notna().any() and lat.median() > 60 and lon.median() < 40:
        lat, lon = lon, lat
        notes.append("Latitude and longitude looked swapped, so they were switched.")
    missing = lat.isna() | lon.isna()
    if missing.any():
        notes.append(f"{int(missing.sum())} row(s) skipped: coordinates missing or unreadable (row {_rows(np.where(missing)[0])}).")
    far = ~missing & ~(lat.between(10, 35) & lon.between(60, 85))
    if far.any():
        notes.append(f"{int(far.sum())} row(s) skipped: coordinates far outside Gujarat (row {_rows(np.where(far)[0])}).")
    outside = ~missing & ~far & ~(lat.between(19.8, 24.9) & lon.between(67.9, 74.8))
    if outside.any():
        notes.append(f"{int(outside.sum())} point(s) lie outside Gujarat (row {_rows(np.where(outside)[0])}); they are still shown.")
    ok = ~missing & ~far
    df = df.loc[ok].copy()
    df["_lat"], df["_lon"] = lat[ok].round(6), lon[ok].round(6)
    df = df.drop(columns=[lat_c, lon_c]).reset_index(drop=True)
    for c in df.columns:
        if not c.startswith("_"):
            df[c] = df[c].map(_cell_str)
    if df.empty:
        return None, notes, "No usable points were found in this file."
    return df, notes, None


# ─────────────────────────────────────────────────────────────
# MAP EXTENT
# ─────────────────────────────────────────────────────────────
def compute_extent(B, level, hi_labels, focus_districts, layers):
    units = B[level]["units"]
    boxes = []
    hi = units[units["label"].isin(hi_labels)]
    if not hi.empty:
        boxes.append(hi.total_bounds)
    elif focus_districts:
        f = units[units["district"].isin(focus_districts)]
        if not f.empty:
            boxes.append(f.total_bounds)
    lats = [v for lay in layers for v in lay["lat"]]
    lons = [v for lay in layers for v in lay["lon"]]
    if lats:
        boxes.append([min(lons), min(lats), max(lons), max(lats)])
    if not boxes:
        return B[level]["bounds"]
    b = np.array(boxes, dtype=float)
    return float(b[:, 0].min()), float(b[:, 1].min()), float(b[:, 2].max()), float(b[:, 3].max())


# ─────────────────────────────────────────────────────────────
# BACKGROUND TILES
# ─────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False, max_entries=4, ttl=6 * 3600)
def fetch_basemap(provider_name: str, w: float, s: float, e: float, n: float, width_px: int):
    import contextily as cx

    prov = cx.providers.query_name(provider_name)
    max_z = int(prov.get("max_zoom", 18))
    z = int(np.ceil(np.log2(width_px * 360.0 / (256.0 * max(e - w, 1e-6)))))
    z = max(3, min(z, max_z))
    while z > 3 and cx.howmany(w, s, e, n, z, verbose=False, ll=True) > MAX_TILES:
        z -= 1
    params = inspect.signature(cx.bounds2img).parameters
    kw = {"zoom": z, "source": prov, "ll": True}
    if "headers" in params:
        kw["headers"] = TILE_HEADERS
    if "n_connections" in params:
        kw.update(n_connections=4, use_cache=False)
    if "timeout" in params:
        kw["timeout"] = 20
    img, ext = cx.bounds2img(w, s, e, n, **kw)
    img, ext = cx.warp_tiles(img, ext, t_crs="EPSG:4326")
    return img, tuple(ext), str(prov.get("attribution", ""))


# ─────────────────────────────────────────────────────────────
# STATIC MAP DRAWING
# ─────────────────────────────────────────────────────────────
def _halo(colour, lw=2.4):
    return [pe.withStroke(linewidth=lw, foreground=colour)]


def _corner(option: str) -> str | None:
    o = option.lower().replace("inside map – ", "")
    return o if o in LOC_CODE else None


def _add_paths(ax, paths, face, edge, lw, z):
    paths = list(paths)
    if not paths:
        return
    pc = PatchCollection([PathPatch(p) for p in paths], facecolors=face, edgecolors=edge,
                         linewidths=lw, zorder=z)
    ax.add_collection(pc, autolim=False)


def _deg_formatter(pos_h, neg_h):
    def fmt(v, _pos=None):
        h = pos_h if v >= 0 else neg_h
        a = abs(v)
        d = int(np.floor(a + 1e-9))
        m = (a - d) * 60
        if abs(m - round(m)) < 0.02:
            m = int(round(m))
            if m == 60:
                d, m = d + 1, 0
            return f"{d}°{h}" if m == 0 else f"{d}°{m:02d}'{h}"
        return f"{a:.2f}°{h}"
    return mticker.FuncFormatter(fmt)


def _fit_limits(fig, ax, w, s, e, n, pad):
    """Map limits that contain (w, s, e, n) plus padding and exactly fill the
    frame at the true north-south / east-west scale. Only ever widens."""
    dx, dy = max(e - w, 0.05), max(n - s, 0.05)
    cx, cy = (w + e) / 2, (s + n) / 2
    dx, dy = max(dx * (1 + 2 * pad), 0.15), max(dy * (1 + 2 * pad), 0.15)
    aspect = 1 / np.cos(np.radians(cy))          # 1° of latitude is longer than 1° of longitude
    pos = ax.get_position()
    W, H = fig.get_size_inches()
    box = (pos.height * H) / (pos.width * W)     # frame height / width
    if dy * aspect / dx < box:
        dy = dx * box / aspect
    else:
        dx = dy * aspect / box
    xlim, ylim = (cx - dx / 2, cx + dx / 2), (cy - dy / 2, cy + dy / 2)
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.set_aspect("auto")
    return xlim, ylim


def _nice_number(x: float) -> float:
    if x <= 0:
        return 1.0
    k = 10 ** np.floor(np.log10(x))
    best = k
    for m in (1, 2, 4, 5, 10):
        if m * k <= x:
            best = m * k
    return float(best)


def _layout(fig, landscape, side_leg, side_loc, top):
    loc_spec = leg_spec = None
    panel = side_leg or side_loc
    if landscape:
        if panel:
            gs = fig.add_gridspec(1, 2, width_ratios=[3.05, 1], left=0.045, right=0.985,
                                  bottom=0.06, top=top, wspace=0.045)
            ax = fig.add_subplot(gs[0, 0])
            sub = gs[0, 1].subgridspec(2, 1, height_ratios=[1, 1.45], hspace=0.07)
            if side_loc:
                loc_spec = sub[0]
            if side_leg:
                leg_spec = sub[1] if side_loc else gs[0, 1]
        else:
            ax = fig.add_subplot(fig.add_gridspec(1, 1, left=0.045, right=0.985, bottom=0.06, top=top)[0, 0])
    else:
        if panel:
            gs = fig.add_gridspec(2, 1, height_ratios=[3.2, 1], left=0.07, right=0.975,
                                  bottom=0.035, top=top, hspace=0.05)
            ax = fig.add_subplot(gs[0, 0])
            sub = gs[1, 0].subgridspec(1, 2, width_ratios=[1, 1.5], wspace=0.05)
            if side_loc:
                loc_spec = sub[0]
            if side_leg:
                leg_spec = sub[1] if side_loc else gs[1, 0]
        else:
            ax = fig.add_subplot(fig.add_gridspec(1, 1, left=0.07, right=0.975, bottom=0.035, top=top)[0, 0])
    return ax, loc_spec, leg_spec


def _legend_items(spec, n_hi):
    """List of (handle, label, is_header)."""
    items = []
    if n_hi and spec["fill"] != FILL_EACH:
        face = spec["fill_color"] if spec["fill"] == FILL_ONE else "white"
        items.append((Patch(facecolor=face, edgecolor="black", linewidth=0.8),
                      spec["area_text"].strip() or "Study area", False))
    for lay in spec["layers"]:
        shape = lay["shape"]

        def handle(colour, shape=shape):
            return Line2D([], [], linestyle="none", marker=LEGEND_MARKER[shape], markersize=LEGEND_MS[shape],
                          markerfacecolor=colour, markeredgecolor="black", markeredgewidth=0.7)

        groups = sorted_groups(lay["cat"]) if lay["by"] else []
        gcol = group_colours(groups)
        if lay["by"]:
            items.append((Line2D([], [], linestyle="none"), lay["name"], True))
            items += [(handle(gcol[g]), g, False) for g in groups]
        elif lay["labels"] not in KEY_MODES:
            items.append((handle(lay["color"]), lay["name"], False))
        if lay["labels"] in KEY_MODES:
            if not lay["by"]:
                items.append((Line2D([], [], linestyle="none"), lay["name"], True))
            for i, (full, short) in enumerate(zip(lay["txt"], lay["short"])):
                key = str(i + 1) if lay["labels"] == KEY_MODES[1] or not short else short
                colour = gcol[lay["cat"][i]] if lay["by"] else lay["color"]
                items.append((handle(colour), f"{key} – {full}" if full else key, False))
    if spec["legend_lines"]:
        items.append((Line2D([], [], color="black", linewidth=1.1), "State boundary", False))
        if spec["level"] == "taluka":
            if spec["district_lines"]:
                items.append((Line2D([], [], color="#333333", linewidth=0.9), "District boundary", False))
            items.append((Line2D([], [], color="#8a8a8a", linewidth=0.45), "Taluka boundary", False))
        else:
            items.append((Line2D([], [], color="#8a8a8a", linewidth=0.6), "District boundary", False))
    return items


_LEGEND_STYLE = dict(frameon=True, fancybox=False, edgecolor="black", borderpad=0.8,
                     labelspacing=0.65, handletextpad=0.6, handlelength=1.6, borderaxespad=0.3,
                     title="Legend", alignment="left")


def _make_legend(target, items, fs, ncol, wrap, **kw):
    labels = [textwrap.fill(lbl, wrap) for _, lbl, _ in items]
    leg = target.legend([h for h, _, _ in items], labels, ncol=ncol, fontsize=fs,
                        title_fontproperties={"weight": "bold", "size": fs + 1.5},
                        **_LEGEND_STYLE, **kw)
    for txt, (_, _, is_header) in zip(leg.get_texts(), items):
        if is_header:
            txt.set_fontweight("bold")
    return leg


def _side_legend(fig, canvas, leg_spec, items, fs0):
    lax = fig.add_subplot(leg_spec)
    lax.axis("off")
    renderer = canvas.get_renderer()
    box = lax.get_window_extent(renderer)
    leg = None
    for ncol in (1, 2):
        fs = fs0
        while fs >= 5.5:
            width_pt = box.width * 72 / fig.dpi / ncol
            wrap = max(14, int((width_pt - 48) / (0.48 * fs)))
            leg = _make_legend(lax, items, fs, ncol, wrap, loc="upper left", bbox_to_anchor=(0, 1))
            bb = leg.get_window_extent(renderer)
            if bb.height <= box.height and bb.width <= box.width * 1.02:
                return leg
            leg.remove()
            fs -= 0.5
    return _make_legend(lax, items, 5.5, 2, 24, loc="upper left", bbox_to_anchor=(0, 1))


def _scale_bar(ax, corner, fs=7.5):
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    km_per_deg = 111.32 * np.cos(np.radians((y0 + y1) / 2))
    nice = _nice_number((x1 - x0) * km_per_deg * 0.2)
    length = nice / km_per_deg
    h = (y1 - y0) * 0.0075
    box = AuxTransformBox(ax.transData)
    for i in range(4):
        box.add_artist(Rectangle((i * length / 4, 0), length / 4, h, linewidth=0.6, edgecolor="black",
                                 facecolor="black" if i % 2 == 0 else "white"))
    for v, xpos in ((0, 0), (nice / 2, length / 2), (nice, length)):
        box.add_artist(Text(xpos, h * 1.9, f"{v:g}", ha="center", va="bottom", fontsize=fs))
    box.add_artist(Text(length * 1.04, h * 0.5, "km", ha="left", va="center", fontsize=fs))
    ab = AnchoredOffsetbox(loc=LOC_CODE[corner], child=box, pad=0.45, borderpad=0.8, frameon=True)
    ab.patch.set(facecolor="white", alpha=0.88, edgecolor="#9a9a9a", linewidth=0.5)
    ab.set_zorder(26)
    ax.add_artist(ab)


def _inset(fig, ax, corner, w_in, h_in, margin_in=0.14):
    pos = ax.get_position()
    W, H = fig.get_size_inches()
    aw, ah = pos.width * W, pos.height * H
    w, h = w_in / aw, h_in / ah
    mx, my = margin_in / aw, margin_in / ah
    x = mx if "left" in corner else 1 - mx - w
    y = my if "bottom" in corner else 1 - my - h
    return ax.inset_axes([x, y, w, h])


def _compass(fig, ax, corner, style, on_basemap):
    rose = style == "Compass rose"
    cax = _inset(fig, ax, corner, 0.80 if rose else 0.46, 0.80 if rose else 0.72)
    cax.set_zorder(27)
    cax.axis("off")
    halo = _halo("white", 2.5)
    if rose:
        cax.set_xlim(-1.6, 1.6)
        cax.set_ylim(-1.6, 1.6)
        if on_basemap:
            cax.add_patch(Circle((0, 0), 1.55, facecolor="white", alpha=0.75, edgecolor="none"))
        w = 0.15
        tri = [([0, 1], w, 0, "black"), ([0, 1], -w, 0, "white"), ([0, -1], w, 0, "white"),
               ([0, -1], -w, 0, "black"), ([1, 0], 0, w, "black"), ([1, 0], 0, -w, "white"),
               ([-1, 0], 0, w, "white"), ([-1, 0], 0, -w, "black")]
        for tip, sx, sy, col in tri:
            cax.add_patch(MplPolygon([[0, 0], tip, [sx, sy]], closed=True, facecolor=col,
                                     edgecolor="black", linewidth=0.5))
        cax.text(0, 1.3, "N", ha="center", va="center", fontsize=13, fontweight="bold", path_effects=halo)
        for t, (x, y) in (("S", (0, -1.3)), ("E", (1.3, 0)), ("W", (-1.3, 0))):
            cax.text(x, y, t, ha="center", va="center", fontsize=9, fontweight="bold", path_effects=halo)
    else:
        cax.set_xlim(-0.8, 0.8)
        cax.set_ylim(-1.15, 1.75)
        if on_basemap:
            cax.add_patch(Rectangle((-0.78, -1.13), 1.56, 2.86, facecolor="white", alpha=0.75, edgecolor="none"))
        cax.add_patch(MplPolygon([[0, 0.95], [-0.5, -0.95], [0, -0.5]], closed=True,
                                 facecolor="black", edgecolor="black", linewidth=0.8))
        cax.add_patch(MplPolygon([[0, 0.95], [0, -0.5], [0.5, -0.95]], closed=True,
                                 facecolor="white", edgecolor="black", linewidth=0.8))
        cax.text(0, 1.3, "N", ha="center", va="center", fontsize=14, fontweight="bold", path_effects=halo)


def _draw_locator(lax, L, hi, extent, inside):
    lax.set_facecolor("white")
    # explicit white card (axes backgrounds are made transparent for PNG/TIFF export)
    lax.add_patch(Rectangle((0, 0), 1, 1, transform=lax.transAxes, facecolor="white",
                            edgecolor="none", zorder=0))
    lax.add_collection(PatchCollection([PathPatch(L["state_path"])], facecolor="white",
                                       edgecolor="#333333", linewidths=0.7, zorder=1))
    lax.add_collection(PatchCollection([PathPatch(p) for p in L["outline_paths"]], facecolor="none",
                                       edgecolor="#a8a8a8", linewidths=0.25, zorder=2))
    if not hi.empty:
        lax.add_collection(PatchCollection([PathPatch(p) for p in hi["path"]], facecolor="#e34a33",
                                           edgecolor="#7f0000", linewidths=0.3, zorder=3))
    bx0, by0, bx1, by1 = L["bounds"]
    px, py = (bx1 - bx0) * 0.04, (by1 - by0) * 0.04
    lax.set_xlim(bx0 - px, bx1 + px)
    lax.set_ylim(by0 - py, by1 + py)
    lax.set_aspect(1 / np.cos(np.radians((by0 + by1) / 2)), adjustable="box")
    x0, x1, y0, y1 = extent
    if (x1 - x0) < 0.75 * (bx1 - bx0) or (y1 - y0) < 0.75 * (by1 - by0):
        lax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, edgecolor="#1f4e9c",
                                linewidth=1.1, zorder=4))
    lax.set_xticks([])
    lax.set_yticks([])
    for sp in lax.spines.values():
        sp.set_linewidth(0.8)
    if inside:
        lax.text(0.04, 0.96, "Gujarat", transform=lax.transAxes, ha="left", va="top",
                 fontsize=8, fontweight="bold")
    else:
        lax.set_title("Location in Gujarat", fontsize=9, fontweight="bold", pad=3)


def _draw_map(spec: dict):
    B = load_boundaries()
    level = spec["level"]
    L = B[level]
    units = L["units"]
    notes = []
    hi_set = set(spec["hi"])
    hi = units[units["label"].isin(hi_set)]

    landscape = spec["orient"] == "Landscape"
    W, H = (11.69, 8.27) if landscape else (8.27, 11.69)
    fig = Figure(figsize=(W, H), dpi=100, facecolor="white")
    canvas = FigureCanvasAgg(fig)

    items = _legend_items(spec, len(hi))
    side_leg = spec["legend"] == "Side panel" and bool(items)
    side_loc = spec["locator"] == "Side panel"
    title = spec["title"].strip()
    ax, loc_spec, leg_spec = _layout(fig, landscape, side_leg, side_loc, 0.925 if title else 0.975)

    # ── extent (selected areas + all points), widened to fill the frame
    w, s, e, n = compute_extent(B, level, spec["hi"], spec["focus"], spec["layers"])
    xlim, ylim = _fit_limits(fig, ax, w, s, e, n, spec["zoom_out"])

    # ── background tiles
    on_basemap, attribution, tile_fail, basemap = False, "", False, None
    provider = BASEMAPS.get(spec["bg"])
    if provider:
        try:
            width_px = int(ax.get_position().width * W * 300)
            img, ext, attribution = fetch_basemap(provider, round(xlim[0], 5), round(ylim[0], 5),
                                                  round(xlim[1], 5), round(ylim[1], 5), width_px)
            # Shown in the PDF only; PNG/TIFF get the tiles pasted in by _export_raster,
            # which needs far less memory than matplotlib's own image resampling.
            im = ax.imshow(img, extent=ext, interpolation="bilinear", zorder=0, aspect="auto")
            ax.set_xlim(*xlim)
            ax.set_ylim(*ylim)
            on_basemap = True
            basemap = {"im": im, "img": img, "ext": ext, "ax": ax, "xlim": xlim, "ylim": ylim}
        except Exception as exc:
            notes.append(f"The background map could not be downloaded just now ({type(exc).__name__}); "
                         "the map was drawn on a plain white background. Press Update map to try again, "
                         "or pick another background.")
            tile_fail = True

    dark = on_basemap and spec["bg"] == "Satellite (Esri)"
    txt_c, halo_c = ("white", "black") if dark else ("black", "white")

    # ── boundaries
    unit_lw = 0.45 if level == "district" else 0.3
    if on_basemap:
        _add_paths(ax, units["path"], "none", "#eeeeee" if dark else "#555555", unit_lw, 1)
    else:
        _add_paths(ax, units["path"], "white", "#8a8a8a", unit_lw, 1)

    if not hi.empty:
        if spec["fill"] == FILL_EACH:
            cmap = area_colours(level, tuple(sorted(hi["label"])), spec["palette"])
            faces = [cmap.get(lbl, "#cccccc") for lbl in hi["label"]]
        elif spec["fill"] == FILL_ONE:
            faces = [spec["fill_color"]] * len(hi)
        else:
            faces = ["white"] * len(hi)
        if on_basemap:
            faces = ["none"] * len(hi) if spec["fill"] == FILL_NONE else [mpl.colors.to_rgba(f, 0.5) for f in faces]
        edge = "#ffff66" if dark else "black"
        lw = (1.4 if spec["fill"] == FILL_NONE else 0.9) if level == "district" else 0.8
        _add_paths(ax, hi["path"], faces, edge, lw, 2)

    if level == "taluka" and spec["district_lines"]:
        _add_paths(ax, L["outline_paths"], "none", "#f2f2f2" if dark else "#333333", 0.9, 3)
    _add_paths(ax, [L["state_path"]], "none", "white" if dark else "black", 1.1, 3.2)

    # ── area names
    if spec["rlabels"] != "None":
        fs = spec["rlabel_size"]
        targets = hi if spec["rlabels"] == "Selected areas" else units
        for row in targets.itertuples():
            if not row.name or not (xlim[0] < row.lx < xlim[1] and ylim[0] < row.ly < ylim[1]):
                continue
            main = row.label in hi_set or spec["rlabels"] == "Selected areas"
            ax.text(row.lx, row.ly, row.name, ha="center", va="center", zorder=4, clip_on=True,
                    fontsize=fs if main else fs * 0.82, fontweight="bold" if main else "normal",
                    fontstyle="normal" if main else "italic",
                    color=txt_c if main else ("#dddddd" if dark else "#555555"),
                    path_effects=_halo(halo_c, 2.4 if main else 1.8))

    # ── points
    for li, lay in enumerate(spec["layers"]):
        lat, lon = np.asarray(lay["lat"], float), np.asarray(lay["lon"], float)
        shape = lay["shape"]
        size = SCATTER_SIZE[shape][SIZES.index(lay["size"])]
        if lay["by"]:
            gcol = group_colours(sorted_groups(lay["cat"]))
            colours = [gcol[c] for c in lay["cat"]]
        else:
            colours = [lay["color"]] * len(lat)
        ax.scatter(lon, lat, s=size, marker=MARKER[shape], c=colours, edgecolors="black",
                   linewidths=0.8 if shape == "Map pin" else 0.6, zorder=5 + li * 0.01)
        if lay["labels"] != "No labels":
            if lay["labels"] == "Names":
                texts = lay["txt"]
            elif lay["labels"] == KEY_MODES[0]:
                texts = [sh or str(i + 1) for i, sh in enumerate(lay["short"])]
            else:
                texts = [str(i + 1) for i in range(len(lat))]
            r = 0.5 * np.sqrt(size)
            if shape == "Map pin":
                off, ha, va = (0, r + 1.5), "center", "bottom"
            else:
                off, ha, va = (r + 2.5, 0), "left", "center"
            for x, y, t in zip(lon, lat, texts):
                if t:
                    ax.annotate(t, (x, y), xytext=off, textcoords="offset points", ha=ha, va=va,
                                fontsize=spec["plabel_size"], fontweight="bold", color=txt_c,
                                path_effects=_halo(halo_c, 2.2), zorder=7, annotation_clip=True)

    # ── frame and grid
    if spec["grid"]:
        for axis, hemi in ((ax.xaxis, ("E", "W")), (ax.yaxis, ("N", "S"))):
            axis.set_major_locator(mticker.MaxNLocator(nbins=5, steps=[1, 1.5, 2, 2.5, 3, 5, 10]))
            axis.set_major_formatter(_deg_formatter(*hemi))
        ax.tick_params(labelsize=7.5, direction="in", length=3, width=0.6, top=True, right=True)
        ax.grid(True, linestyle=(0, (4, 3)), linewidth=0.35, color="#6f6f6f", alpha=0.6)
        ax.set_axisbelow(False)
    else:
        ax.set_xticks([])
        ax.set_yticks([])
    ax.set_xlabel("")
    ax.set_ylabel("")
    for sp in ax.spines.values():
        sp.set_linewidth(1.1)
        sp.set_zorder(30)

    # ── map furniture
    corners = {}

    def claim(corner, what):
        if corner in corners:
            notes.append(f"The {what} and the {corners[corner]} are both in the {corner} corner. "
                         "Move one of them under 'Page & layout'.")
        corners.setdefault(corner, what)

    if spec["scalebar"] != "Don't show":
        c = spec["scalebar"].lower()
        claim(c, "scale bar")
        _scale_bar(ax, c)
    if spec["compass"] != "Don't show":
        c = spec["compass"].lower()
        claim(c, "north arrow")
        _compass(fig, ax, c, spec["compass_style"], on_basemap)

    extent = (*xlim, *ylim)
    if side_loc:
        lax = fig.add_subplot(loc_spec)
        lax.set_anchor("N" if landscape else "W")
        _draw_locator(lax, L, hi, extent, inside=False)
    elif _corner(spec["locator"]):
        c = _corner(spec["locator"])
        claim(c, "locator map")
        pos = ax.get_position()
        size = min(2.3, 0.3 * pos.width * W, 0.42 * pos.height * H)
        lax = _inset(fig, ax, c, size, size)
        lax.set_zorder(28)
        lax.set_anchor({"top left": "NW", "top right": "NE", "bottom left": "SW", "bottom right": "SE"}[c])
        _draw_locator(lax, L, hi, extent, inside=True)

    if items and spec["legend"] != "Don't show":
        if side_leg:
            _side_legend(fig, canvas, leg_spec, items, spec["legend_size"])
        else:
            c = _corner(spec["legend"])
            claim(c, "legend")
            leg = _make_legend(ax, items, spec["legend_size"], 1, 38, loc=LOC_CODE[c], framealpha=0.92)
            leg.set_zorder(29)

    if title:
        fig.suptitle(title, fontsize=15, fontweight="bold", y=0.985)
    if on_basemap and attribution:
        pos = ax.get_position()
        fig.text(pos.x0, pos.y0 - (0.032 if spec["grid"] else 0.008), "Background map: " + attribution,
                 fontsize=5.5, color="#555555", ha="left", va="top")
    return fig, notes, tile_fail, basemap


def _export_raster(fig, dpi, basemap) -> Image.Image:
    """Page image at `dpi`, cropped to its content.
    The figure is rendered with a transparent background and laid over a
    white page; background tiles (if any) are pasted under the map frame
    with Pillow at exactly the print size."""
    W, H = fig.get_size_inches()
    m = 0.3                                    # spare margin around the A4 page, inches
    raw = io.BytesIO()
    if basemap:
        basemap["im"].set_visible(False)
    fig.savefig(raw, format="raw", dpi=dpi, transparent=True,
                bbox_inches=Bbox([[-m, -m], [W + m, H + m]]))
    if basemap:
        basemap["im"].set_visible(True)
    data = raw.getvalue()
    del raw
    w = int(round((W + 2 * m) * dpi))
    for cand in (w, w - 1, w + 1):
        if len(data) % (4 * cand) == 0:
            w = cand
            break
    h = len(data) // (4 * w)
    over = Image.frombuffer("RGBA", (w, h), data, "raw", "RGBA", 0, 1)
    page = Image.new("RGB", (w, h), "white")

    box = over.getbbox() or (0, 0, w, h)
    if basemap:
        bb = basemap["ax"].get_window_extent()          # display pixels at fig.dpi
        to_px = lambda x_in, y_in: ((x_in + m) * dpi, (H + m - y_in) * dpi)
        x0, y0 = to_px(bb.x0 / fig.dpi, bb.y1 / fig.dpi)
        x1, y1 = to_px(bb.x1 / fig.dpi, bb.y0 / fig.dpi)
        x0, y0, x1, y1 = (int(round(v)) for v in (x0, y0, x1, y1))
        src = Image.fromarray(np.asarray(basemap["img"])[..., :3])
        ex0, ex1, ey0, ey1 = basemap["ext"]
        (vx0, vx1), (vy0, vy1) = basemap["xlim"], basemap["ylim"]
        sw, sh = src.size
        sbox = ((vx0 - ex0) / (ex1 - ex0) * sw, (ey1 - vy1) / (ey1 - ey0) * sh,
                (vx1 - ex0) / (ex1 - ex0) * sw, (ey1 - vy0) / (ey1 - ey0) * sh)
        sbox = (max(0.0, sbox[0]), max(0.0, sbox[1]), min(float(sw), sbox[2]), min(float(sh), sbox[3]))
        page.paste(src.resize((x1 - x0, y1 - y0), Image.BILINEAR, box=sbox), (x0, y0))
        box = (min(box[0], x0), min(box[1], y0), max(box[2], x1), max(box[3], y1))

    page.paste(over, (0, 0), over)
    del over, data
    pad = int(0.15 * dpi)
    crop = (max(0, box[0] - pad), max(0, box[1] - pad), min(w, box[2] + pad), min(h, box[3] + pad))
    return page.crop(crop)


@st.cache_data(show_spinner=False, max_entries=3, ttl=3600)
def render_print_map(spec_json: str, attempt: int = 0) -> dict:
    """Draw the map and export it. `attempt` only forces a fresh try after
    the background tiles failed to download."""
    spec = json.loads(spec_json)
    font = font_names()[spec["font"]]
    dpi = int(spec["dpi"])
    with _render_lock(), mpl.rc_context({"font.family": font, "font.size": 10}):
        fig, notes, tile_fail, basemap = _draw_map(spec)
        if basemap:   # embed the tiles in the PDF as they are (no memory-hungry resampling)
            basemap["im"].set_interpolation("none")
        pdf = io.BytesIO()
        fig.savefig(pdf, format="pdf", dpi=min(dpi, 300), bbox_inches="tight", pad_inches=0.15,
                    facecolor="white")
        page = _export_raster(fig, dpi, basemap)
        fig.clear()
    png, tif, pbuf = io.BytesIO(), io.BytesIO(), io.BytesIO()
    page.save(png, format="PNG", dpi=(dpi, dpi))
    page.save(tif, format="TIFF", compression="tiff_lzw", dpi=(dpi, dpi))
    size = page.size
    page.thumbnail((1800, 1800))
    page.save(pbuf, format="JPEG", quality=92)
    return {"preview": pbuf.getvalue(), "png": png.getvalue(), "tiff": tif.getvalue(),
            "pdf": pdf.getvalue(), "notes": notes, "px": size, "tile_fail": tile_fail}


# ─────────────────────────────────────────────────────────────
# INTERACTIVE MAP
# ─────────────────────────────────────────────────────────────
def build_web_map(B, spec, layer_frames):
    import folium
    from branca.element import MacroElement
    from jinja2 import Template

    level = spec["level"]
    L = B[level]
    hi_set = set(spec["hi"])
    if spec["fill"] == FILL_EACH and hi_set:
        cmap = area_colours(level, tuple(sorted(hi_set)), spec["palette"])
    else:
        cmap = {}
    fill_one = spec["fill_color"] if spec["fill"] == FILL_ONE else "#ffffff"

    m = folium.Map(location=[22.3, 71.6], zoom_start=7, tiles=None, control_scale=True)
    folium.TileLayer("OpenStreetMap", name="Street map").add_to(m)
    esri = "https://server.arcgisonline.com/ArcGIS/rest/services/{}/MapServer/tile/{{z}}/{{y}}/{{x}}"
    folium.TileLayer(esri.format("World_Imagery"), attr="Tiles © Esri", name="Satellite").add_to(m)
    folium.TileLayer(esri.format("World_Topo_Map"), attr="Tiles © Esri", name="Topographic").add_to(m)
    folium.TileLayer(esri.format("Canvas/World_Light_Gray_Base"), attr="Tiles © Esri",
                     name="Light grey").add_to(m)

    def style(feature):
        lbl = feature["properties"]["label"]
        if lbl in hi_set:
            return {"fillColor": cmap.get(lbl, fill_one), "color": "#111111", "weight": 1.8,
                    "fillOpacity": 0.6 if spec["fill"] != FILL_NONE else 0.0}
        return {"fillColor": "#ffffff", "color": "#555555", "weight": 0.7, "fillOpacity": 0.05}

    fields = ["label", "district"] if level == "taluka" else ["label"]
    aliases = ["Taluka:", "District:"] if level == "taluka" else ["District:"]
    folium.GeoJson(L["web"], name="Talukas" if level == "taluka" else "Districts", style_function=style,
                   highlight_function=lambda f: {"weight": 3, "color": "#000000"},
                   tooltip=folium.GeoJsonTooltip(fields=fields, aliases=aliases)).add_to(m)

    legend_rows = []
    for lay, df in zip(spec["layers"], layer_frames):
        cols = [c for c in df.columns if not c.startswith("_")]
        name_col = lay["name_col"]
        groups = sorted_groups(lay["cat"]) if lay["by"] else [None]
        gcol = group_colours(groups) if lay["by"] else {None: lay["color"]}
        fgs = {}
        for g in groups:
            fgs[g] = folium.FeatureGroup(name=f"{lay['name']}: {g}" if g is not None else lay["name"])
            legend_rows.append((gcol[g], f"{lay['name']}: {g}" if g is not None else lay["name"]))
        for i, row in df.iterrows():
            g = lay["cat"][i] if lay["by"] else None
            title = row[name_col] if name_col else f"Point {i + 1}"
            table = "".join(f"<tr><th style='text-align:left;padding-right:8px'>{html.escape(str(c))}</th>"
                            f"<td>{html.escape(str(row[c]))}</td></tr>" for c in cols)
            table += f"<tr><th style='text-align:left'>Lat, Long</th><td>{row['_lat']:.5f}, {row['_lon']:.5f}</td></tr>"
            folium.CircleMarker(
                location=[row["_lat"], row["_lon"]], radius=WEB_RADIUS[lay["size"]],
                color="#222222", weight=1, fill=True, fill_color=gcol[g], fill_opacity=0.9,
                tooltip=html.escape(str(title) or f"Point {i + 1}"),
                popup=folium.Popup(f"<table style='font-size:12px'>{table}</table>", max_width=320),
            ).add_to(fgs[g])
        for fg in fgs.values():
            fg.add_to(m)

    if legend_rows:
        rows = "".join(f"<div><span style='display:inline-block;width:11px;height:11px;border-radius:50%;"
                       f"background:{c};border:1px solid #222;margin-right:6px'></span>{html.escape(t)}</div>"
                       for c, t in legend_rows[:25])

        class _Legend(MacroElement):
            _template = Template("""
            {% macro script(this, kwargs) %}
            var legend = L.control({position: 'bottomleft'});
            legend.onAdd = function (map) {
                var div = L.DomUtil.create('div');
                div.style.cssText = 'background:white;padding:6px 10px;border:1px solid #888;border-radius:6px;font:12px "Times New Roman",serif;max-height:220px;overflow:auto';
                div.innerHTML = {{ this.html|tojson }};
                return div;
            };
            legend.addTo({{ this._parent.get_name() }});
            {% endmacro %}
            """)

            def __init__(self, content):
                super().__init__()
                self._name = "Legend"
                self.html = content

        _Legend(rows).add_to(m)

    w, s, e, n = compute_extent(B, level, spec["hi"], spec["focus"], spec["layers"])
    m.fit_bounds([[s, w], [n, e]], padding=(20, 20))
    folium.LayerControl(collapsed=True).add_to(m)
    return m


# ─────────────────────────────────────────────────────────────
# SIDEBAR CONTROLS
# ─────────────────────────────────────────────────────────────
def _default(key, value):
    """Set a widget's starting value. If the widget was hidden for a while
    (Streamlit then forgets its value), bring back the last value instead."""
    if key not in st.session_state:
        st.session_state[key] = st.session_state.get(f"_keep_{key}", value)


def _keep(*keys):
    """Remember widget values so they survive being hidden (see _default)."""
    for key in keys:
        if key in st.session_state:
            st.session_state[f"_keep_{key}"] = st.session_state[key]


def _valid_choice(key, options, fallback):
    if st.session_state.get(key) not in options:
        st.session_state[key] = fallback


def _apply_preset(target_key, all_names):
    choice = st.session_state.get("preset")
    if not choice:
        return
    rule = PRESETS[choice]
    if rule == "ALL":
        st.session_state[target_key] = list(all_names)
    else:
        keys = {district_key(x) for x in rule}
        st.session_state[target_key] = [nm for nm in all_names if district_key(nm) in keys]
    st.session_state["preset"] = None


def _add_layer():
    st.session_state.layer_ids.append(st.session_state.next_layer_id)
    st.session_state.next_layer_id += 1


def _remove_layer(lid):
    if lid in st.session_state.layer_ids:
        st.session_state.layer_ids.remove(lid)
    for k in [k for k in st.session_state.keys() if str(k).startswith(f"L{lid}_")]:
        del st.session_state[k]
    if not st.session_state.layer_ids:
        _add_layer()


def area_controls(B):
    st.markdown("### 1 · Area to highlight")
    level_ui = st.radio("Boundary level", ["Districts", "Talukas"], key="level", horizontal=True)
    level = "district" if level_ui == "Districts" else "taluka"
    dnames = B["district_names"]
    target = "sel_districts" if level == "district" else "tal_districts"
    st.selectbox("Quick pick", list(PRESETS), index=None, key="preset",
                 placeholder="Choose a group of districts…",
                 on_change=_apply_preset, args=(target, dnames))
    focus = []
    if level == "district":
        _default("sel_districts", [nm for nm in dnames if district_key(nm) in {district_key(x) for x in DEFAULT_DISTRICTS}])
        st.session_state["sel_districts"] = [x for x in st.session_state["sel_districts"] if x in dnames]
        hi = st.multiselect("Districts to highlight", dnames, key="sel_districts")
        _keep("sel_districts")
        return level, sorted(hi), focus

    units = B["taluka"]["units"]
    t_dists = sorted(d for d in units["district"].unique() if d)
    _default("tal_districts", [])
    st.session_state["tal_districts"] = [x for x in st.session_state["tal_districts"] if x in t_dists]
    focus = st.multiselect("Districts", t_dists, key="tal_districts",
                           help="Pick the districts first; their talukas appear below.")
    pool = units[units["selectable"] & (units["district"].isin(focus) if focus else True)]
    options = sorted(pool["label"])
    _default("tal_all", False)
    every = st.checkbox("Highlight every taluka of these districts", key="tal_all", disabled=not focus)
    _default("sel_talukas", [])
    _keep("tal_districts", "tal_all")
    if every and focus:
        return level, sorted(options), sorted(focus)
    st.session_state["sel_talukas"] = [x for x in st.session_state["sel_talukas"] if x in options]
    hi = st.multiselect(f"Talukas to highlight ({len(options)} available)", options, key="sel_talukas")
    _keep("sel_talukas")
    return level, sorted(hi), sorted(focus)


def layer_controls(lid: int, idx: int):
    """One point layer. Returns (spec dict, DataFrame) or None."""
    k = lambda s: f"L{lid}_{s}"
    dname, dshape, dcolour = LAYER_DEFAULTS[(lid - 1) % len(LAYER_DEFAULTS)]
    _default(k("name"), dname)
    _default(k("shape"), dshape)
    _default(k("color"), dcolour)
    _default(k("size"), "Medium")
    with st.expander(f"📍 Point layer {idx + 1}", expanded=True):
        up = st.file_uploader("CSV or Excel file (Latitude, Longitude, Name…)",
                              type=["csv", "txt", "xlsx"], key=k("file"))
        df = None
        if up is not None:
            df, notes, err = read_points(up.getvalue(), up.name)
            if err:
                st.error(err)
            for note in notes:
                st.caption("⚠️ " + note)
            if df is not None:
                st.caption(f"✅ {len(df)} point(s) read from **{up.name}**")
        st.text_input("Name in legend", key=k("name"))
        c1, c2 = st.columns([3, 2])
        c1.selectbox("Shape", SHAPES, key=k("shape"))
        st.select_slider("Size", SIZES, key=k("size"))
        by_col = None
        if df is not None:
            cols = [c for c in df.columns if not c.startswith("_")]
            _valid_choice(k("by"), ["(none)"] + cols, "(none)")
            by_choice = st.selectbox("Colour by group (optional)", ["(none)"] + cols, key=k("by"),
                                     help="e.g. a 'Crop' or 'Year' column: each group gets its own colour and legend entry.")
            by_col = None if by_choice == "(none)" else by_choice
            name_guess = guess_name_col(cols)
            _valid_choice(k("labels"), LABEL_MODES,
                          "Names" if name_guess and (len(df) <= 12 or dshape == "Map pin") else "No labels")
            label_mode = st.selectbox("Labels on map", LABEL_MODES, key=k("labels"))
            name_col = short_col = None
            if cols:
                _valid_choice(k("namecol"), cols, name_guess or cols[0])
                name_col = st.selectbox("Column with the names", cols, key=k("namecol"))
            if label_mode == KEY_MODES[0] and cols:
                _valid_choice(k("shortcol"), cols, guess_short_col(cols) or cols[0])
                short_col = st.selectbox("Column with the short names", cols, key=k("shortcol"))
            if label_mode in KEY_MODES and len(df) > 30:
                st.caption("⚠️ Many points: the legend key will be long.")
            if by_col and df[by_col].nunique() > len(POINT_COLOURS):
                st.caption(f"⚠️ {df[by_col].nunique()} groups — colours will repeat. A column with fewer groups works better.")
        c2.color_picker("Colour", key=k("color"), disabled=by_col is not None)
        st.button("🗑️ Remove layer", key=k("del"), on_click=_remove_layer, args=(lid,))

    if df is None:
        return None
    lay = {
        "name": st.session_state[k("name")].strip() or dname,
        "shape": st.session_state[k("shape")],
        "size": st.session_state[k("size")],
        "color": st.session_state[k("color")],
        "labels": label_mode,
        "by": by_col is not None,
        "name_col": name_col,
        "lat": df["_lat"].tolist(),
        "lon": df["_lon"].tolist(),
        "txt": df[name_col].tolist() if name_col else [""] * len(df),
        "short": df[short_col].tolist() if short_col else [""] * len(df),
        "cat": [v if v else "(blank)" for v in df[by_col]] if by_col else [],
    }
    return lay, df


def look_controls(level):
    with st.expander("3 · Map look", expanded=False):
        _default("bg", "Plain white")
        st.selectbox("Background", list(BASEMAPS), key="bg",
                     help="Background maps are downloaded when you press Make map; this needs internet and takes a few seconds.")
        _default("fill", FILL_EACH)
        fill = st.radio("Highlighted areas", [FILL_EACH, FILL_ONE, FILL_NONE], key="fill")
        if fill == FILL_EACH:
            _default("palette", "Pastel")
            st.selectbox("Colour set", list(PALETTES), key="palette")
        else:
            if fill == FILL_ONE:
                _default("fill_color", "#a6d96a")
                st.color_picker("Fill colour", key="fill_color")
            _default("area_text", "Study area")
            st.text_input("Legend text for the highlighted area", key="area_text")
        _default("rlabels", "Selected areas")
        st.selectbox("Area names on the map", ["Selected areas", "All areas in view", "None"], key="rlabels")
        _default(f"rlsize_{level}", 9 if level == "district" else 7)
        st.slider("Area name size", 5, 24, key=f"rlsize_{level}")
        _keep(f"rlsize_{level}")
        _default("plabel_size", 8)
        st.slider("Point label size", 5, 16, key="plabel_size")
        _default("title", "")
        st.text_input("Map title (optional)", key="title")
        _default("font", "Times New Roman")
        st.radio("Font", ["Times New Roman", "Arial"], key="font", horizontal=True)
        _default("grid", False)
        st.checkbox("Latitude / longitude grid", key="grid")


def layout_controls(level):
    with st.expander("4 · Page & layout", expanded=False):
        _default("orient", "Landscape")
        st.radio("Page (A4)", ["Landscape", "Portrait"], key="orient", horizontal=True)
        _default("legend", "Side panel")
        st.selectbox("Legend", PANEL_OPTS, key="legend")
        _default("legend_size", 9.0)
        st.slider("Legend text size", 6.0, 14.0, step=0.5, key="legend_size",
                  help="Shrinks automatically if the legend would not fit.")
        _default("locator", "Side panel")
        st.selectbox("Small 'Location in Gujarat' map", PANEL_OPTS, key="locator")
        c1, c2 = st.columns(2)
        _default("compass", "Top right")
        c1.selectbox("North arrow", CORNER_OPTS, key="compass")
        _default("compass_style", "Compass rose")
        c2.selectbox("Style", ["Compass rose", "North arrow"], key="compass_style")
        _default("scalebar", "Bottom right")
        st.selectbox("Scale bar", CORNER_OPTS, key="scalebar")
        _default("zoom_out", 0.12)
        st.slider("Space around the selected areas", 0.0, 1.0, step=0.02, key="zoom_out")
        _default("legend_lines", True)
        st.checkbox("Show boundary lines in the legend", key="legend_lines")
        if level == "taluka":
            _default("district_lines", True)
            st.checkbox("Draw district boundaries over talukas", key="district_lines")
            _keep("district_lines")
        _default("dpi", 300)
        st.radio("Resolution of PNG/TIFF", [300, 600], key="dpi", horizontal=True,
                 format_func=lambda v: f"{v} dpi" + (" (slower)" if v == 600 else ""))


# ─────────────────────────────────────────────────────────────
# APP
# ─────────────────────────────────────────────────────────────
try:
    B = load_boundaries()
except Exception as exc:
    st.error(f"Could not load the boundary files in the `data` folder: {exc}")
    st.stop()

_default("layer_ids", [1])
_default("next_layer_id", 2)

with st.sidebar:
    st.markdown("## 🗺️ Map settings")
    level, hi_labels, focus = area_controls(B)

    st.markdown("### 2 · Survey points (optional)")
    st.download_button("⬇️ Sample CSV file", SAMPLE_CSV, file_name="sample_points.csv",
                       mime="text/csv", on_click="ignore")
    layers, frames = [], []
    for idx, lid in enumerate(list(st.session_state.layer_ids)):
        res = layer_controls(lid, idx)
        if res:
            layers.append(res[0])
            frames.append(res[1])
    st.button("➕ Add another point layer", on_click=_add_layer)

    look_controls(level)
    layout_controls(level)

ss = st.session_state
spec = {
    "level": level, "hi": hi_labels, "focus": focus,
    "bg": ss["bg"], "fill": ss["fill"], "palette": ss.get("palette", "Pastel"),
    "fill_color": ss.get("fill_color", "#a6d96a"), "area_text": ss.get("area_text", "Study area"),
    "rlabels": ss["rlabels"], "rlabel_size": ss[f"rlsize_{level}"], "plabel_size": ss["plabel_size"],
    "title": ss["title"], "font": ss["font"], "grid": ss["grid"], "orient": ss["orient"],
    "legend": ss["legend"], "legend_size": ss["legend_size"], "locator": ss["locator"],
    "compass": ss["compass"], "compass_style": ss["compass_style"], "scalebar": ss["scalebar"],
    "zoom_out": ss["zoom_out"], "legend_lines": ss["legend_lines"],
    "district_lines": ss.get("district_lines", ss.get("_keep_district_lines", True)), "dpi": ss["dpi"],
    "layers": layers,
}
spec_json = json.dumps(spec, sort_keys=True, separators=(",", ":"))

st.title("Gujarat Survey Map Maker")
st.caption("Thesis-quality district and taluka maps of Gujarat with your survey points. "
           "Choose settings in the left panel, then press **Make map**.")
view = st.radio("View", ["🖨️ Map for thesis / paper", "🌐 Interactive map"], horizontal=True,
                key="view", label_visibility="collapsed")

n_pts = sum(len(lay["lat"]) for lay in layers)
what = (f"{len(hi_labels)} {'district' if level == 'district' else 'taluka'}(s) highlighted · "
        f"{n_pts} point(s) in {len(layers)} layer(s)")

if view.startswith("🖨️"):
    made = ss.get("made_spec")
    c1, c2 = st.columns([1, 3], vertical_alignment="center")
    if c1.button("🔄 Update map" if made else "🗺️ Make map", type="primary", key="make_btn", width="stretch"):
        if made == spec_json and ss.get("tile_fail"):
            ss["attempt"] = ss.get("attempt", 0) + 1   # retry the background download
        ss["made_spec"] = made = spec_json
    if made is None:
        c2.caption(what)
    elif made == spec_json:
        c2.caption("✅ The map below matches your settings · " + what)
    else:
        c2.markdown("⚠️ **You changed some settings.** Press **Update map** to see them on the map.")

    if made is None:
        st.info(
            "**How to use**\n\n"
            "1. **Area** – pick districts (or talukas) to highlight. *Quick pick* fills common groups.\n"
            "2. **Survey points** – upload a CSV or Excel file with `Latitude` and `Longitude` columns "
            "(a `Name` column gives labels; a `Group` column can colour points). Use **Add another point layer** "
            "for a second file, e.g. important locations as map pins.\n"
            "3. **Map look / Page & layout** – optional; the defaults already give a clean A4 map.\n"
            "4. Press **Make map**, check the preview, then download PNG, TIFF or PDF."
        )
    else:
        try:
            with st.spinner("Drawing the map… (a background map adds 5–20 seconds)"):
                result = render_print_map(made, ss.get("attempt", 0))
            ss["tile_fail"] = result["tile_fail"]
        except Exception as exc:
            st.error(f"Sorry, the map could not be drawn: {exc}")
            with st.expander("Technical details"):
                st.exception(exc)
        else:
            for note in result["notes"]:
                st.warning(note)
            st.image(result["preview"], width="stretch")
            made_spec = json.loads(made)
            base = re.sub(r"[^A-Za-z0-9]+", "_", made_spec["title"]).strip("_") or f"gujarat_{made_spec['level']}_map"
            d1, d2, d3 = st.columns(3)
            dpi = made_spec["dpi"]
            d1.download_button(f"⬇️ PNG ({dpi} dpi) – Word / PowerPoint", result["png"], f"{base}.png",
                               "image/png", width="stretch", on_click="ignore")
            d2.download_button(f"⬇️ TIFF ({dpi} dpi) – journals", result["tiff"], f"{base}.tif",
                               "image/tiff", width="stretch", on_click="ignore")
            d3.download_button("⬇️ PDF (vector) – printing", result["pdf"], f"{base}.pdf",
                               "application/pdf", width="stretch", on_click="ignore")
            st.caption(f"Image size: {result['px'][0]} × {result['px'][1]} pixels.")
else:
    from streamlit_folium import st_folium

    st.caption(what + " · Click a point for its details; use the layer button (top right) to switch "
               "background or hide groups.")
    web = build_web_map(B, spec, frames)
    st_folium(web, key="web_map", height=620, use_container_width=True, returned_objects=[])
    st.download_button("⬇️ Download this interactive map (HTML)", web.get_root().render(),
                       file_name="gujarat_interactive_map.html", mime="text/html", on_click="ignore")
