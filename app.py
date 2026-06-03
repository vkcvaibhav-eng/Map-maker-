# ============================================================
# Gujarat Survey Map Generator — Refactored app.py
# Improvements: cached GeoJSON loading, shared helper functions,
# generate-on-demand button, scale bar, map title, PDF export,
# coordinate grid, better UX, and no duplicate code.
# ============================================================

import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import matplotlib.path as mpath
import matplotlib.lines as mlines
import matplotlib.patheffects as pe
import matplotlib.ticker as mticker
import numpy as np
import io
import os
import contextily as cx

# ─────────────────────────────────────────────
# PAGE CONFIG & GLOBAL STYLES
# ─────────────────────────────────────────────
st.set_page_config(page_title="Ph.D. Survey Map Generator", layout="wide")

st.markdown("""
<style>
html, body, [class*="css"], [class*="st-"] {
    font-family: "Times New Roman", Times, serif !important;
}
</style>
""", unsafe_allow_html=True)

plt.rcParams['font.family'] = 'serif'
plt.rcParams['font.serif'] = ['Times New Roman'] + plt.rcParams['font.serif']
plt.rcParams['axes.titlesize'] = 14
plt.rcParams['axes.labelsize'] = 12

# ─────────────────────────────────────────────
# CONSTANTS & MARKER DEFINITIONS
# ─────────────────────────────────────────────
DATA_PATHS = {
    "Gujarat State": "data/gujarat_state.geojson",
    "Districts":     "data/gujarat.geojson",
    "Talukas":       "data/gujarat_talukas.geojson",
}

DISTRICT_COL_CANDIDATES = ['dtname', 'NAME_2', 'district', 'Dist_Name', 'district_name', 'REGNAME']
TALUKA_COL_CANDIDATES   = ['NAME_3', 'taluka', 'Taluka_Name', 'taluka_name', 'TALUKA',
                            'Sub_Distri', 'subdistrict', 'sdtname', 'tehsil_name', 'Tehsil', 'NAME_2']
NAME_COL_CANDIDATES     = ['name', 'location', 'label', 'site']
SHORT_COL_CANDIDATES    = ['short name', 'short', 'abbr', 'abbreviation']

COLOR_PALETTES = ["None (White)", "Set2", "Dark2", "Paired", "tab10",
                  "Greens", "Blues", "YlGnBu", "OrRd", "viridis",
                  "cividis", "plasma", "Pastel1", "Set3", "Accent"]

LEGEND_MAPPING = {
    "Outside Top Right":    {"loc": "upper left",  "bbox": (1.02, 1)},
    "Outside Center Right": {"loc": "center left", "bbox": (1.02, 0.5)},
    "Outside Bottom Right": {"loc": "lower left",  "bbox": (1.02, 0)},
    "Inside Top Right":     {"loc": "upper right", "bbox": None},
    "Inside Top Left":      {"loc": "upper left",  "bbox": None},
    "Inside Bottom Right":  {"loc": "lower right", "bbox": None},
    "Inside Bottom Left":   {"loc": "lower left",  "bbox": None},
}

FOLIUM_COLORS = ['red', 'blue', 'green', 'purple', 'orange',
                 'darkred', 'cadetblue', 'darkgreen', 'darkpurple', 'pink']

IDEAL_DISTRICTS = {"ahmedabad", "anand", "vadodara", "kheda", "panchmahal",
                   "panch mahal", "dahod", "mahisagar", "chhotaudepur", "botad"}


def _build_pin_path(include_dummy: bool):
    """Return a matplotlib Path shaped like a map pin teardrop."""
    D, R = 2.5, 1.0
    theta = np.arcsin(R / D)
    angles = np.linspace(np.pi + theta, -theta, 100)
    xo = R * np.cos(angles)
    yo = R * np.sin(angles) + 2.5
    xo = np.concatenate([xo, [0.0], [xo[0]]])
    yo = np.concatenate([yo, [0.0], [yo[0]]])

    r_inner = 0.4
    ai = np.linspace(0, 2 * np.pi, 100)
    xi = r_inner * np.cos(ai)
    yi = r_inner * np.sin(ai) + 2.5

    outer = np.column_stack((xo, yo))
    inner = np.column_stack((xi, yi))

    if include_dummy:
        dummy = np.array([[0.0, -3.5]])
        verts = np.vstack((outer, inner, dummy))
        codes = np.full(len(verts), mpath.Path.LINETO)
        codes[0] = mpath.Path.MOVETO
        codes[len(outer)] = mpath.Path.MOVETO
        codes[-1] = mpath.Path.MOVETO
    else:
        verts = np.vstack((outer, inner))
        codes = np.full(len(verts), mpath.Path.LINETO)
        codes[0] = mpath.Path.MOVETO
        codes[len(outer)] = mpath.Path.MOVETO

    return mpath.Path(verts, codes)


_PIN_PLOT   = _build_pin_path(include_dummy=True)
_PIN_LEGEND = _build_pin_path(include_dummy=False)

MARKER_MAP        = {"Map Pin": _PIN_PLOT,   "Circle": "o", "Square": "s", "Triangle": "^", "Diamond": "D", "Star": "*"}
LEGEND_MARKER_MAP = {"Map Pin": _PIN_LEGEND, "Circle": "o", "Square": "s", "Triangle": "^", "Diamond": "D", "Star": "*"}

# ─────────────────────────────────────────────
# CACHED DATA LOADERS
# ─────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_geodata(path: str) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(path)
    if gdf.crs is None:
        gdf.set_crs(epsg=4326, inplace=True)
    return gdf


@st.cache_data(show_spinner=False)
def load_sample_csv(path: str) -> bytes:
    if os.path.exists(path):
        with open(path, "rb") as f:
            return f.read()
    return b"Latitude,Longitude,Name,Short Name\n20.9467,72.9520,Navsari Agricultural University,NAU\n"

# ─────────────────────────────────────────────
# UTILITY FUNCTIONS
# ─────────────────────────────────────────────
def process_uploaded_csv(uploaded_file) -> pd.DataFrame | None:
    df = pd.read_csv(uploaded_file)
    df.columns = df.columns.str.strip()
    df = df.loc[:, ~df.columns.duplicated()]
    if 'Latitude' in df.columns and 'Longitude' in df.columns:
        df['Latitude']  = pd.to_numeric(df['Latitude'],  errors='coerce')
        df['Longitude'] = pd.to_numeric(df['Longitude'], errors='coerce')
        return df.dropna(subset=['Latitude', 'Longitude'])
    return None


def find_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    return next((c for c in df.columns if c.lower() in candidates), None)


def find_region_col(gdf: gpd.GeoDataFrame, candidates: list[str]) -> str | None:
    return next((c for c in candidates if c in gdf.columns), None)


def text_colors(basemap: str) -> tuple[str, str]:
    """Return (text_color, outline_color) suited to the chosen basemap."""
    if basemap == "Esri World Imagery (Satellite)":
        return 'white', 'black'
    return 'black', 'white'


def annotate_with_outline(ax, text, xy, offset_pts, fontsize, txt_color, out_color, zorder=7):
    ax.annotate(
        text, xy,
        xytext=(0, offset_pts), textcoords='offset points',
        ha='center', va='bottom', fontsize=fontsize, fontweight='bold',
        color=txt_color,
        path_effects=[pe.withStroke(linewidth=2.5, foreground=out_color)],
        zorder=zorder,
    )


def add_scale_bar(ax, length_deg=0.5, label="~50 km"):
    """Draw a simple scale bar in the lower-right corner of ax."""
    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    x0 = xlim[1] - (xlim[1] - xlim[0]) * 0.05 - length_deg
    y0 = ylim[0] + (ylim[1] - ylim[0]) * 0.04
    ax.plot([x0, x0 + length_deg], [y0, y0], color='black', linewidth=2.5, zorder=10)
    ax.plot([x0, x0], [y0, y0 + (ylim[1]-ylim[0])*0.008], color='black', linewidth=2, zorder=10)
    ax.plot([x0+length_deg, x0+length_deg], [y0, y0 + (ylim[1]-ylim[0])*0.008], color='black', linewidth=2, zorder=10)
    ax.text(x0 + length_deg/2, y0 + (ylim[1]-ylim[0])*0.015, label,
            ha='center', va='bottom', fontsize=8, fontweight='bold', zorder=10)


def add_compass(fig, cx, cy, size=0.1):
    """Draw a compass rose at figure coordinates (cx, cy)."""
    ax_c = fig.add_axes([cx, cy, size, size])
    ax_c.set_axis_off()
    ax_c.set_aspect('equal')
    w = 0.15
    polys = [
        [[0,0],[0,1],[w,0],'black'],   [[0,0],[0,1],[-w,0],'white'],
        [[0,0],[0,-1],[w,0],'white'],  [[0,0],[0,-1],[-w,0],'black'],
        [[0,0],[1,0],[0,w],'black'],   [[0,0],[1,0],[0,-w],'white'],
        [[0,0],[-1,0],[0,w],'white'],  [[0,0],[-1,0],[0,-w],'black'],
    ]
    for p in polys:
        ax_c.add_patch(patches.Polygon(p[:3], facecolor=p[3], edgecolor='black', lw=0.5))
    ax_c.text(0,  1.25, 'N', ha='center', va='center', fontweight='bold', fontsize=14)
    for txt, pos in [('S',(0,-1.25)),('E',(1.25,0)),('W',(-1.25,0))]:
        ax_c.text(*pos, txt, ha='center', va='center', fontsize=10, fontweight='bold')
    ax_c.set(xlim=(-1.5,1.5), ylim=(-1.5,1.5))
    return ax_c


def add_inset(fig, ix, iy, state_gdf, highlighted_gdf, color_choice, size=0.25):
    """Draw a small Gujarat-state inset locator map."""
    ax_i = fig.add_axes([ix, iy, size, size])
    state_gdf.plot(ax=ax_i, color='white', edgecolor='gray', linewidth=0.5)
    highlight_color = '#d3d3d3' if color_choice == "None (White)" else '#ff66b2'
    highlighted_gdf.plot(ax=ax_i, color=highlight_color, edgecolor='black', linewidth=0.8)
    ax_i.set_xticks([])
    ax_i.set_yticks([])
    ax_i.set_title("Gujarat State", fontsize=11, fontweight='bold', pad=4)
    for spine in ax_i.spines.values():
        spine.set_edgecolor('black')
    return ax_i


def plot_legend(ax, handles, legend_pos, font_size):
    if not handles:
        return
    cfg = LEGEND_MAPPING[legend_pos]
    kwargs = dict(
        loc=cfg["loc"], title="Legend",
        fontsize=font_size, title_fontsize=font_size + 2,
        frameon=True, facecolor='white', framealpha=0.9, edgecolor='black',
        shadow=True, borderpad=1.2, labelspacing=1.0, handletextpad=0.8,
    )
    if cfg["bbox"] is not None:
        kwargs["bbox_to_anchor"] = cfg["bbox"]
    ax.legend(handles=handles, **kwargs)


def make_legend_handle(style, color, label):
    return mlines.Line2D(
        [], [], color='none',
        marker=LEGEND_MARKER_MAP[style],
        markerfacecolor=color, markeredgecolor='black',
        markersize=12, label=label,
    )

# ─────────────────────────────────────────────
# SHARED MAP RENDERER (used by both District & Taluka tabs)
# ─────────────────────────────────────────────
def render_static_map(
    *,
    gdf: gpd.GeoDataFrame,
    state_gdf: gpd.GeoDataFrame,
    region_col: str,
    selected_regions: list[str],
    # Styling
    basemap_choice: str,
    color_map_choice: str,
    font_size: int,
    orientation: str,
    margin_multiplier: float,
    map_title: str,
    show_grid: bool,
    # Legend / elements
    legend_pos: str,
    legend_font_size: int,
    inset_x: float, inset_y: float,
    compass_x: float, compass_y: float,
    # Data layers
    survey_data: list[dict],
    loc_data: list[dict],
    show_loc_labels: bool,
    # Export
    tab_key: str,
):
    figsize = (11.69, 8.27) if orientation == "Landscape (A4)" else (8.27, 11.69)
    fig, ax = plt.subplots(figsize=figsize, dpi=300)

    right_margin = 0.70 if "Outside" in legend_pos else 0.95
    plt.subplots_adjust(top=0.90, bottom=0.05, left=0.05, right=right_margin)

    poly_alpha      = 1.0 if basemap_choice == "None (White Background)" else 0.55
    base_poly_alpha = 1.0 if basemap_choice == "None (White Background)" else 0.15

    bg_color = 'white' if basemap_choice == "None (White Background)" else 'none'
    gdf.plot(ax=ax, color=bg_color, edgecolor='black', linewidth=0.3,
             alpha=base_poly_alpha, zorder=1)

    legend_handles = []

    if not selected_regions:
        ax.text(0.5, 0.5, "Select regions to render map.",
                ha='center', va='center', transform=ax.transAxes,
                fontsize=14, color='gray')
        ax.set_xticks([]); ax.set_yticks([]); ax.set_frame_on(False)
        st.pyplot(fig)
        return

    highlighted = gdf[gdf[region_col].isin(selected_regions)]

    if color_map_choice == "None (White)":
        highlighted.plot(ax=ax, color='white', edgecolor='black',
                         linewidth=1.5, alpha=poly_alpha, zorder=2)
    else:
        highlighted.plot(ax=ax, column=region_col, cmap=color_map_choice,
                         edgecolor='black', linewidth=1.5, alpha=poly_alpha, zorder=2)

    # Zoom to highlighted area
    minx, miny, maxx, maxy = highlighted.total_bounds
    mx = max((maxx - minx) * margin_multiplier, 0.05)
    my = max((maxy - miny) * margin_multiplier, 0.05)
    ax.set_xlim(minx - mx, maxx + mx)
    ax.set_ylim(miny - my, maxy + my)

    # Region labels
    txt_col, out_col = text_colors(basemap_choice)
    for _, row in highlighted.iterrows():
        centroid = row.geometry.centroid
        ax.annotate(
            text=row[region_col], xy=(centroid.x, centroid.y),
            ha='center', va='center', fontsize=font_size, fontweight='bold',
            color=txt_col,
            path_effects=[pe.withStroke(linewidth=3, foreground=out_col)],
            zorder=4,
        )

    # Survey point layers
    for pt in survey_data:
        size = 800 if pt['style'] == "Map Pin" else 60
        ax.scatter(
            pt['df']['Longitude'].values, pt['df']['Latitude'].values,
            color=pt['color'], edgecolor='black',
            marker=MARKER_MAP[pt['style']], s=size,
            zorder=5, linewidth=0.8, label="_nolegend_",
        )
        legend_handles.append(make_legend_handle(pt['style'], pt['color'], pt['label']))

    # Location layers
    txt_col_l, out_col_l = text_colors(basemap_choice)
    for loc in loc_data:
        size = 1200 if loc['style'] == "Map Pin" else 150
        ax.scatter(
            loc['df']['Longitude'].values, loc['df']['Latitude'].values,
            color=loc['color'], edgecolor='black',
            marker=MARKER_MAP[loc['style']], s=size,
            zorder=6, linewidth=1.2, label="_nolegend_",
        )

        name_col  = find_col(loc['df'], NAME_COL_CANDIDATES)
        short_col = find_col(loc['df'], SHORT_COL_CANDIDATES)
        y_offset  = 25 if loc['style'] == "Map Pin" else 15

        if show_loc_labels:
            for idx, r in loc['df'].iterrows():
                full_val  = str(r[name_col])  if name_col  and pd.notna(r[name_col])  else f"Loc {idx+1}"
                short_val = str(r[short_col]) if short_col and pd.notna(r[short_col]) else str(idx+1)
                display   = short_val if loc['use_abbr'] else full_val
                annotate_with_outline(ax, display, (r['Longitude'], r['Latitude']),
                                      y_offset, max(font_size-2, 8),
                                      txt_col_l, out_col_l)

                if loc['use_abbr']:
                    legend_handles.append(
                        make_legend_handle(loc['style'], loc['color'], f"{short_val} – {full_val}")
                    )

        if not loc['use_abbr']:
            legend_handles.append(make_legend_handle(loc['style'], loc['color'], loc['label']))

    # Basemap tiles
    if basemap_choice == "OpenStreetMap (Street View)":
        cx.add_basemap(ax, crs=gdf.crs.to_string(),
                       source=cx.providers.OpenStreetMap.Mapnik, zorder=0)
    elif basemap_choice == "Esri World Imagery (Satellite)":
        cx.add_basemap(ax, crs=gdf.crs.to_string(),
                       source=cx.providers.Esri.WorldImagery, zorder=0)

    # Coordinate grid
    if show_grid:
        ax.grid(True, linestyle='--', linewidth=0.4, color='gray', alpha=0.5, zorder=3)
        ax.xaxis.set_major_formatter(mticker.FormatStrFormatter('%.1f°E'))
        ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.1f°N'))
        ax.tick_params(labelsize=7)
    else:
        ax.set_xticks([]); ax.set_yticks([])

    ax.set_frame_on(True)

    # Scale bar
    add_scale_bar(ax)

    # Map title
    if map_title.strip():
        ax.set_title(map_title.strip(), fontsize=16, fontweight='bold', pad=10)

    # Legend
    if legend_pos != "None":
        plot_legend(ax, legend_handles, legend_pos, legend_font_size)

    # Compass rose
    add_compass(fig, compass_x, compass_y)

    # Inset locator
    add_inset(fig, inset_x, inset_y, state_gdf, highlighted, color_map_choice)

    st.pyplot(fig)

    # Downloads
    png_buf = io.BytesIO()
    fig.savefig(png_buf, format="png", dpi=300, bbox_inches='tight')
    pdf_buf = io.BytesIO()
    fig.savefig(pdf_buf, format="pdf", bbox_inches='tight')

    dl_col1, dl_col2 = st.columns(2)
    dl_col1.download_button(
        "⬇️ Download PNG", data=png_buf.getvalue(),
        file_name=f"survey_map_{tab_key}.png", mime="image/png",
        key=f"dl_png_{tab_key}",
    )
    dl_col2.download_button(
        "⬇️ Download PDF", data=pdf_buf.getvalue(),
        file_name=f"survey_map_{tab_key}.pdf", mime="application/pdf",
        key=f"dl_pdf_{tab_key}",
    )

# ─────────────────────────────────────────────
# SHARED SIDEBAR: Dynamic survey + location layer builder
# ─────────────────────────────────────────────
def survey_layer_ui(prefix: str) -> list[dict]:
    """Render dynamic survey-point layer cards; return list of layer dicts."""
    layers_key  = f"{prefix}_survey_layers"
    counter_key = f"{prefix}_next_survey"
    if layers_key  not in st.session_state: st.session_state[layers_key]  = [1]
    if counter_key not in st.session_state: st.session_state[counter_key] = 2

    result = []
    for lid in list(st.session_state[layers_key]):
        with st.container(border=True):
            c1, c2 = st.columns([4, 1])
            c1.markdown("**Survey Layer**")
            if c2.button("🗑️", key=f"{prefix}_del_sv_{lid}"):
                st.session_state[layers_key].remove(lid)
                st.rerun()
            lbl   = st.text_input("Legend Name", f"Survey {lid}", key=f"{prefix}_sv_lbl_{lid}")
            pc1, pc2 = st.columns(2)
            color = pc1.color_picker("Color", "#FF0000" if lid % 2 != 0 else "#0000FF", key=f"{prefix}_sv_col_{lid}")
            style = pc2.selectbox("Shape", ["Circle","Map Pin","Square","Triangle","Diamond","Star"], key=f"{prefix}_sv_sty_{lid}")
            f = st.file_uploader("Upload CSV", type=["csv"], key=f"{prefix}_sv_csv_{lid}")
            if f:
                df = process_uploaded_csv(f)
                if df is not None:
                    result.append({"df": df, "label": lbl, "color": color, "style": style})
                else:
                    st.warning("CSV must contain 'Latitude' and 'Longitude' columns.")

    if st.button("➕ Add Survey Layer", key=f"{prefix}_add_sv"):
        st.session_state[layers_key].append(st.session_state[counter_key])
        st.session_state[counter_key] += 1
        st.rerun()
    return result


def location_layer_ui(prefix: str) -> tuple[list[dict], bool]:
    """Render dynamic location-layer cards; return (list of dicts, show_labels)."""
    layers_key  = f"{prefix}_loc_layers"
    counter_key = f"{prefix}_next_loc"
    if layers_key  not in st.session_state: st.session_state[layers_key]  = [1]
    if counter_key not in st.session_state: st.session_state[counter_key] = 2

    show_labels = st.checkbox("Show Location Names on Map", value=True, key=f"{prefix}_loc_showlbl")
    result = []
    for lid in list(st.session_state[layers_key]):
        with st.container(border=True):
            c1, c2 = st.columns([4, 1])
            c1.markdown("**Location Layer**")
            if c2.button("🗑️", key=f"{prefix}_del_lc_{lid}"):
                st.session_state[layers_key].remove(lid)
                st.rerun()
            lbl      = st.text_input("Layer Name", "Locations", key=f"{prefix}_lc_lbl_{lid}")
            use_abbr = st.checkbox("Use Short Names on map, full names in legend", value=False, key=f"{prefix}_lc_abbr_{lid}")
            lc1, lc2 = st.columns(2)
            color = lc1.color_picker("Color", "#FFFF00", key=f"{prefix}_lc_col_{lid}")
            style = lc2.selectbox("Shape", ["Map Pin","Star","Diamond","Square","Circle","Triangle"], key=f"{prefix}_lc_sty_{lid}")
            f = st.file_uploader("Upload CSV", type=["csv"], key=f"{prefix}_lc_csv_{lid}")
            if f:
                df = process_uploaded_csv(f)
                if df is not None:
                    result.append({"df": df, "label": lbl, "color": color, "style": style, "use_abbr": use_abbr})
                else:
                    st.warning("CSV must contain 'Latitude' and 'Longitude' columns.")

    if st.button("➕ Add Location Layer", key=f"{prefix}_add_lc"):
        st.session_state[layers_key].append(st.session_state[counter_key])
        st.session_state[counter_key] += 1
        st.rerun()
    return result, show_labels


def element_placement_ui(prefix: str, legend_keys: list[str]) -> dict:
    """Render element placement controls and return a dict of values."""
    st.subheader("3. Element Placement")
    lc1, lc2 = st.columns(2)
    legend_pos       = lc1.selectbox("Legend Position", legend_keys, index=0, key=f"{prefix}_legend_pos")
    legend_font_size = lc2.slider("Legend Font Size", 6, 24, 10, key=f"{prefix}_leg_font")

    el1, el2 = st.columns(2)
    inset_pos   = el1.selectbox("Inset Base Pos",   ["Top Left","Top Right","Bottom Left","Bottom Right"], index=0, key=f"{prefix}_inset_pos")
    compass_pos = el2.selectbox("Compass Base Pos", ["Top Right","Top Left","Bottom Right","Bottom Left"], index=0, key=f"{prefix}_compass_pos")

    base_i = {"Top Left":[0.05,0.55],"Top Right":[0.70,0.55],"Bottom Left":[0.05,0.05],"Bottom Right":[0.70,0.05]}[inset_pos]
    base_c = {"Top Right":[0.85,0.70],"Top Left":[0.05,0.70],"Bottom Right":[0.85,0.05],"Bottom Left":[0.05,0.05]}[compass_pos]

    with st.expander("🛠️ Fine-Tune Inset & Compass (fix overlaps)"):
        st.caption("Use these sliders if the inset or compass overlaps your map.")
        fx1, fx2 = st.columns(2)
        inset_x   = fx1.slider("Inset X", 0.0, 1.0, base_i[0], 0.01, key=f"{prefix}_ix")
        inset_y   = fx1.slider("Inset Y", 0.0, 1.0, base_i[1], 0.01, key=f"{prefix}_iy")
        compass_x = fx2.slider("Compass X", 0.0, 1.0, base_c[0], 0.01, key=f"{prefix}_cx")
        compass_y = fx2.slider("Compass Y", 0.0, 1.0, base_c[1], 0.01, key=f"{prefix}_cy")

    return dict(
        legend_pos=legend_pos, legend_font_size=legend_font_size,
        inset_x=inset_x, inset_y=inset_y,
        compass_x=compass_x, compass_y=compass_y,
    )


def map_styling_ui(prefix: str) -> dict:
    """Render the Map Styling section and return a dict of style settings."""
    st.subheader("2. Map Styling")
    basemap = st.selectbox(
        "Background Map View",
        ["None (White Background)", "OpenStreetMap (Street View)", "Esri World Imagery (Satellite)"],
        key=f"{prefix}_basemap",
    )
    color_palette = st.selectbox("Highlight Palette", COLOR_PALETTES, key=f"{prefix}_palette")
    font_size     = st.slider("Region Label Font Size", 4, 40, 12, key=f"{prefix}_font")
    orientation   = st.selectbox("Page Orientation", ["Landscape (A4)", "Portrait (A4)"], key=f"{prefix}_ori")
    margin        = st.slider("Map Blank Space (Zoom Out)", 0.05, 1.50, 0.35, 0.05, key=f"{prefix}_margin",
                              help="Increase to zoom out and make room for the inset/compass.")
    map_title     = st.text_input("Map Title (printed on export)", "", key=f"{prefix}_title")
    show_grid     = st.checkbox("Show Coordinate Grid (lat/lon lines)", value=False, key=f"{prefix}_grid")
    return dict(basemap=basemap, color_palette=color_palette, font_size=font_size,
                orientation=orientation, margin=margin, map_title=map_title, show_grid=show_grid)

# ─────────────────────────────────────────────
# LOAD GEODATA (cached)
# ─────────────────────────────────────────────
sample_csv_data = load_sample_csv("1 - Copy.csv")

# Warn early if GeoJSON files are missing
for label, path in DATA_PATHS.items():
    if not os.path.exists(path):
        st.sidebar.warning(f"⚠️ Missing: `{path}` ({label})")

# ─────────────────────────────────────────────
# TITLE
# ─────────────────────────────────────────────
st.title("Gujarat Survey Map Generator")
st.markdown("Generate professional, publication-ready maps for your Ph.D. thesis.")

with st.sidebar:
    st.header("📥 Sample Template")
    st.download_button(
        "Download Sample CSV",
        data=sample_csv_data,
        file_name="sample_survey_data.csv",
        mime="text/csv",
    )
    st.caption("CSV must have `Latitude`, `Longitude`, `Name`, and optionally `Short Name` columns.")

# ─────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["🗺️ Interactive GPS Map", "📍 Static District Map", "📍 Static Taluka Map"])

# ══════════════════════════════════════════════
# TAB 1 — INTERACTIVE GPS MAP
# ══════════════════════════════════════════════
with tab1:
    st.header("Interactive Point Map")
    col1, col2 = st.columns([1, 3])

    with col1:
        st.subheader("1. Map Settings")
        highlight_type = st.selectbox("Boundary Level", ["None", "Gujarat State", "Districts", "Talukas"])

        st.subheader("2. Upload Survey Data")
        uploaded_gps = st.file_uploader("Upload GPS CSV", type=["csv"], key="interactive_csv")

    with col2:
        m = folium.Map(location=[22.2587, 71.1924], zoom_start=7)
        folium.TileLayer(tiles="cartodbpositron", name="Clean Street Map").add_to(m)
        folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            attr='Esri', name='Satellite View', overlay=False,
        ).add_to(m)
        folium.TileLayer(tiles="OpenStreetMap", name="Standard Street Map").add_to(m)

        if highlight_type != "None":
            fp = DATA_PATHS[highlight_type]
            if os.path.exists(fp):
                folium.GeoJson(fp, name=highlight_type,
                               style_function=lambda x: {'color':'blue','weight':1.5,'fillOpacity':0.1}).add_to(m)

        if uploaded_gps:
            df_gps = process_uploaded_csv(uploaded_gps)
            if df_gps is not None:
                with col1:
                    st.markdown("---")
                    st.subheader("3. Styling & Filtering")
                    color_options = ["None (All Red)"] + [c for c in df_gps.columns if c not in ['Latitude','Longitude']]
                    color_col = st.selectbox("Color markers by:", color_options)

                filtered_df = df_gps.copy()
                color_map   = {}

                if color_col != "None (All Red)":
                    unique_vals = df_gps[color_col].dropna().unique()
                    with col1:
                        st.markdown("**Toggle data groups:**")
                    selected_vals = []
                    for i, val in enumerate(unique_vals):
                        color_map[val] = FOLIUM_COLORS[i % len(FOLIUM_COLORS)]
                        if st.checkbox(f"Show {val}", value=True, key=f"chk_{val}"):
                            selected_vals.append(val)
                    filtered_df = df_gps[df_gps[color_col].isin(selected_vals)]

                for _, row in filtered_df.iterrows():
                    loc_name = row.get('Name', row.get('Location', 'Unknown'))
                    tooltip   = f"<b>{loc_name}</b>"
                    if color_col != "None (All Red)" and pd.notna(row.get(color_col)):
                        tooltip += f"<br>{color_col}: {row[color_col]}"
                    marker_color = color_map.get(row.get(color_col), "gray") if color_col != "None (All Red)" else "red"
                    folium.CircleMarker(
                        location=[row['Latitude'], row['Longitude']],
                        radius=6, color=marker_color, fill=True,
                        fill_color=marker_color, fill_opacity=0.8,
                        tooltip=tooltip, popup=loc_name,
                    ).add_to(m)

                st.success(f"Showing {len(filtered_df)} of {len(df_gps)} points.")
            else:
                st.error("CSV must contain 'Latitude' and 'Longitude' columns.")

        folium.LayerControl(position='topright').add_to(m)
        st_folium(m, width=800, height=500)
        st.download_button(
            "⬇️ Download Map (HTML)",
            data=m._repr_html_(),
            file_name="interactive_survey_map.html",
            mime="text/html",
        )

# ══════════════════════════════════════════════
# TAB 2 — STATIC DISTRICT MAP
# ══════════════════════════════════════════════
with tab2:
    st.header("Static District Highlight Map")

    if not os.path.exists(DATA_PATHS["Districts"]):
        st.error(f"Cannot find `{DATA_PATHS['Districts']}`.")
    else:
        gdf_dist = load_geodata(DATA_PATHS["Districts"])
        dist_col = find_region_col(gdf_dist, DISTRICT_COL_CANDIDATES)
        gdf_dist[dist_col] = gdf_dist[dist_col].astype(str).str.strip()
        all_districts = sorted([d for d in gdf_dist[dist_col].dropna().unique() if d != "nan"])

        # State outline for inset
        state_gdf = load_geodata(DATA_PATHS["Gujarat State"]) if os.path.exists(DATA_PATHS["Gujarat State"]) else gdf_dist

        col3, col4 = st.columns([1.2, 2.8])

        with col3:
            st.subheader("1. Select Surveyed Regions")
            selected_districts = st.multiselect(
                "Highlight districts:", all_districts,
                default=[d for d in all_districts if d.lower().strip() in IDEAL_DISTRICTS],
                key="dist_select",
            )

            style_d    = map_styling_ui("dist")
            placement_d = element_placement_ui("dist", list(LEGEND_MAPPING.keys()))

            st.markdown("---")
            st.subheader("4. Survey Points")
            survey_d = survey_layer_ui("dist")

            st.markdown("---")
            st.subheader("5. Important Locations")
            loc_d, show_loc_d = location_layer_ui("dist")

            generate_d = st.button("🗺️ Generate District Map", type="primary", key="gen_dist")

        with col4:
            if generate_d or st.session_state.get("dist_map_ready"):
                st.session_state["dist_map_ready"] = True
                with st.spinner("Rendering district map…"):
                    render_static_map(
                        gdf=gdf_dist, state_gdf=state_gdf,
                        region_col=dist_col, selected_regions=selected_districts,
                        basemap_choice=style_d["basemap"],
                        color_map_choice=style_d["color_palette"],
                        font_size=style_d["font_size"],
                        orientation=style_d["orientation"],
                        margin_multiplier=style_d["margin"],
                        map_title=style_d["map_title"],
                        show_grid=style_d["show_grid"],
                        legend_pos=placement_d["legend_pos"],
                        legend_font_size=placement_d["legend_font_size"],
                        inset_x=placement_d["inset_x"], inset_y=placement_d["inset_y"],
                        compass_x=placement_d["compass_x"], compass_y=placement_d["compass_y"],
                        survey_data=survey_d, loc_data=loc_d,
                        show_loc_labels=show_loc_d,
                        tab_key="district",
                    )
            else:
                st.info("Configure settings on the left, then click **Generate District Map**.")

# ══════════════════════════════════════════════
# TAB 3 — STATIC TALUKA MAP
# ══════════════════════════════════════════════
with tab3:
    st.header("Static Taluka Highlight Map")

    if not os.path.exists(DATA_PATHS["Talukas"]):
        st.error(f"Cannot find `{DATA_PATHS['Talukas']}`.")
    else:
        gdf_tal  = load_geodata(DATA_PATHS["Talukas"])
        tal_col  = find_region_col(gdf_tal, TALUKA_COL_CANDIDATES)
        gdf_tal[tal_col] = gdf_tal[tal_col].astype(str).str.strip()
        all_talukas = sorted([t for t in gdf_tal[tal_col].dropna().unique() if t != "nan"])

        state_gdf_t = load_geodata(DATA_PATHS["Gujarat State"]) if os.path.exists(DATA_PATHS["Gujarat State"]) else gdf_tal

        col5, col6 = st.columns([1.2, 2.8])

        with col5:
            st.subheader("1. Select Surveyed Regions")
            selected_talukas = st.multiselect("Highlight talukas:", all_talukas, key="taluka_select")

            style_t     = map_styling_ui("taluka")
            placement_t = element_placement_ui("taluka", list(LEGEND_MAPPING.keys()))

            st.markdown("---")
            st.subheader("4. Survey Points")
            survey_t = survey_layer_ui("taluka")

            st.markdown("---")
            st.subheader("5. Important Locations")
            loc_t, show_loc_t = location_layer_ui("taluka")

            generate_t = st.button("🗺️ Generate Taluka Map", type="primary", key="gen_taluka")

        with col6:
            if generate_t or st.session_state.get("taluka_map_ready"):
                st.session_state["taluka_map_ready"] = True
                with st.spinner("Rendering taluka map…"):
                    render_static_map(
                        gdf=gdf_tal, state_gdf=state_gdf_t,
                        region_col=tal_col, selected_regions=selected_talukas,
                        basemap_choice=style_t["basemap"],
                        color_map_choice=style_t["color_palette"],
                        font_size=style_t["font_size"],
                        orientation=style_t["orientation"],
                        margin_multiplier=style_t["margin"],
                        map_title=style_t["map_title"],
                        show_grid=style_t["show_grid"],
                        legend_pos=placement_t["legend_pos"],
                        legend_font_size=placement_t["legend_font_size"],
                        inset_x=placement_t["inset_x"], inset_y=placement_t["inset_y"],
                        compass_x=placement_t["compass_x"], compass_y=placement_t["compass_y"],
                        survey_data=survey_t, loc_data=loc_t,
                        show_loc_labels=show_loc_t,
                        tab_key="taluka",
                    )
            else:
                st.info("Configure settings on the left, then click **Generate Taluka Map**.")
