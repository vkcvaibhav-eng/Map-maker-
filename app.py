import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import matplotlib.path as mpath
import matplotlib.lines as mlines  # --- NEW: Required for custom legend handles ---
import numpy as np
import io
import os
import contextily as cx

# --- Page Configuration ---
st.set_page_config(page_title="Ph.D. Survey Map Generator", layout="wide")

# --- Set Global Font to Times New Roman for Streamlit UI ---
st.markdown("""
    <style>
    html, body, [class*="css"], [class*="st-"] {
        font-family: "Times New Roman", Times, serif !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- Set Global Font to Times New Roman for Matplotlib Outputs ---
plt.rcParams['font.family'] = 'serif'
plt.rcParams['font.serif'] = ['Times New Roman'] + plt.rcParams['font.serif']
plt.rcParams['axes.titlesize'] = 14
plt.rcParams['axes.labelsize'] = 12

st.title("Gujarat Survey Map Generator")
st.markdown("Generate professional, publication-ready maps for your Ph.D. thesis.")

# --- Custom Map Pin Path (High-Resolution Geometric Teardrop) ---
D = 2.5  
R = 1.0  
theta_tangent = np.arcsin(R / D)

angles = np.linspace(np.pi + theta_tangent, -theta_tangent, 100)
x_outer = R * np.cos(angles)
y_outer = R * np.sin(angles) + 2.5  

x_outer = np.concatenate([x_outer, [0.0], [x_outer[0]]])
y_outer = np.concatenate([y_outer, [0.0], [y_outer[0]]])

r_inner = 0.4
angles_inner = np.linspace(0, 2 * np.pi, 100)
x_inner = r_inner * np.cos(angles_inner)
y_inner = r_inner * np.sin(angles_inner) + 2.5

verts_outer = np.column_stack((x_outer, y_outer))
verts_inner = np.column_stack((x_inner, y_inner))

# The map pin WITH the dummy vertex for plotting precisely on GPS coordinates
verts_dummy = np.array([[0.0, -3.5]])
pin_verts = np.vstack((verts_outer, verts_inner, verts_dummy))
pin_codes = np.full(len(pin_verts), mpath.Path.LINETO)
pin_codes[0] = mpath.Path.MOVETO
pin_codes[len(verts_outer)] = mpath.Path.MOVETO
pin_codes[-1] = mpath.Path.MOVETO  
custom_pin = mpath.Path(pin_verts, pin_codes)

# --- NEW: The map pin WITHOUT the dummy vertex for perfect Legend Alignment ---
pin_verts_leg = np.vstack((verts_outer, verts_inner))
pin_codes_leg = np.full(len(pin_verts_leg), mpath.Path.LINETO)
pin_codes_leg[0] = mpath.Path.MOVETO
pin_codes_leg[len(verts_outer)] = mpath.Path.MOVETO
custom_pin_legend = mpath.Path(pin_verts_leg, pin_codes_leg)

marker_map = {
    "Map Pin": custom_pin, "Circle": "o", "Square": "s",
    "Triangle": "^", "Diamond": "D", "Star": "*"
}
legend_marker_map = {
    "Map Pin": custom_pin_legend, "Circle": "o", "Square": "s",
    "Triangle": "^", "Diamond": "D", "Star": "*"
}

# --- Legend Mapping Dictionary ---
legend_mapping = {
    "Outside Top Right": {"loc": "upper left", "bbox": (1.02, 1)},
    "Outside Center Right": {"loc": "center left", "bbox": (1.02, 0.5)},
    "Outside Bottom Right": {"loc": "lower left", "bbox": (1.02, 0)},
    "Inside Top Right": {"loc": "upper right", "bbox": None},
    "Inside Top Left": {"loc": "upper left", "bbox": None},
    "Inside Bottom Right": {"loc": "lower right", "bbox": None},
    "Inside Bottom Left": {"loc": "lower left", "bbox": None},
}

# --- Load User's Custom Sample CSV ---
sample_csv_path = "1 - Copy.csv"
if os.path.exists(sample_csv_path):
    with open(sample_csv_path, "rb") as file:
        sample_csv_data = file.read()
else:
    # --- NEW: Added 'Short Name' to sample template ---
    sample_csv_data = b"Latitude,Longitude,Name,Short Name\n20.9467,72.9520,Navsari Agricultural University,NAU\n"
    st.sidebar.warning(f"⚠️ Could not find '{sample_csv_path}'. Please make sure it is saved in the same folder as this script.")

# --- Initialize Dynamic Session States ---
if 'dist_survey_layers' not in st.session_state: st.session_state.dist_survey_layers = [1]
if 'next_dist_survey' not in st.session_state: st.session_state.next_dist_survey = 2
if 'dist_loc_layers' not in st.session_state: st.session_state.dist_loc_layers = [1]
if 'next_dist_loc' not in st.session_state: st.session_state.next_dist_loc = 2

if 'taluka_survey_layers' not in st.session_state: st.session_state.taluka_survey_layers = [1]
if 'next_taluka_survey' not in st.session_state: st.session_state.next_taluka_survey = 2
if 'taluka_loc_layers' not in st.session_state: st.session_state.taluka_loc_layers = [1]
if 'next_taluka_loc' not in st.session_state: st.session_state.next_taluka_loc = 2

def process_uploaded_csv(uploaded_file):
    df = pd.read_csv(uploaded_file)
    df.columns = df.columns.str.strip()
    df = df.loc[:, ~df.columns.duplicated()]
    if 'Latitude' in df.columns and 'Longitude' in df.columns:
        df['Latitude'] = pd.to_numeric(df['Latitude'], errors='coerce')
        df['Longitude'] = pd.to_numeric(df['Longitude'], errors='coerce')
        return df.dropna(subset=['Latitude', 'Longitude'])
    return None

tab1, tab2, tab3 = st.tabs(["Interactive GPS Map", "Static District Map", "Static Taluka Map"])

# ==========================================
# TAB 1: INTERACTIVE GPS MAP
# ==========================================
with tab1:
    st.header("Interactive Point Map")
    col1, col2 = st.columns([1, 3])
    with col1:
        st.subheader("1. Map Settings")
        highlight_type = st.selectbox("Select Boundary Level", ["None", "Gujarat State", "Districts", "Talukas"])
        st.subheader("2. Upload Survey Data")
        uploaded_file = st.file_uploader("Upload GPS CSV", type=["csv"], key="interactive_csv")
    with col2:
        m = folium.Map(location=[22.2587, 71.1924], zoom_start=7)
        folium.TileLayer(tiles="cartodbpositron", name="Clean Street Map").add_to(m)
        folium.TileLayer(tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', attr='Esri', name='Satellite View', overlay=False).add_to(m)
        folium.TileLayer(tiles="OpenStreetMap", name="Standard Street Map").add_to(m)

        file_mapping = {"Gujarat State": "data/gujarat_state.geojson", "Districts": "data/gujarat.geojson", "Talukas": "data/gujarat_talukas.geojson"}
        if highlight_type != "None":
            file_path = file_mapping[highlight_type]
            if os.path.exists(file_path):
                folium.GeoJson(file_path, name=highlight_type, style_function=lambda x: {'color': 'blue', 'weight': 1.5, 'fillOpacity': 0.1}).add_to(m)

        if uploaded_file:
            df = process_uploaded_csv(uploaded_file)
            if df is not None:
                with col1:
                    st.markdown("---")
                    st.subheader("3. Map Styling & Filtering")
                    color_options = ["None (All Red)"] + [col for col in df.columns if col not in ['Latitude', 'Longitude']]
                    color_col = st.selectbox("Color and filter markers by:", color_options)
                
                filtered_df = df.copy() 
                color_map = {}
                if color_col != "None (All Red)":
                    unique_values = df[color_col].dropna().unique()
                    with col1: st.markdown("**Select data to display:**")
                    selected_values = []
                    palette = ['red', 'blue', 'green', 'purple', 'orange', 'darkred', 'cadetblue', 'darkgreen', 'darkpurple', 'pink']
                    for i, val in enumerate(unique_values):
                        color_map[val] = palette[i % len(palette)]
                        if st.checkbox(f"Show {val} (●)", value=True, key=f"check_{val}"): selected_values.append(val)
                    filtered_df = df[df[color_col].isin(selected_values)]

                for _, row in filtered_df.iterrows():
                    loc_name = row.get('Name', row.get('Location', "Unknown Location"))
                    tooltip_text = f"<div style='font-family: \"Times New Roman\", Times, serif;'><b>Location:</b> {loc_name}"
                    if color_col != "None (All Red)" and pd.notna(row[color_col]):
                        tooltip_text += f"<br><b>{color_col}:</b> {row[color_col]}"
                    tooltip_text += "</div>"
                    
                    marker_color = color_map.get(row[color_col], "gray") if color_col != "None (All Red)" and pd.notna(row[color_col]) else "red"
                    folium.CircleMarker(location=[row['Latitude'], row['Longitude']], radius=6, color=marker_color, fill=True, fill_color=marker_color, fill_opacity=0.8, tooltip=tooltip_text, popup=loc_name).add_to(m)
                st.success(f"Displaying {len(filtered_df)} out of {len(df)} sample points.")
            else:
                st.error("⚠️ Your CSV file must contain exactly 'Latitude' and 'Longitude'.")

        folium.LayerControl(position='topright').add_to(m)
        st_folium(m, width=800, height=500)
        st.download_button("Download Map (HTML)", data=m._repr_html_(), file_name="interactive_survey_map.html", mime="text/html")


# ==========================================
# TAB 2: STATIC DISTRICT MAP
# ==========================================
with tab2:
    st.header("Static District Highlight Map")
    district_geojson_path = "data/gujarat.geojson"
    
    if not os.path.exists(district_geojson_path):
        st.error(f"Cannot find {district_geojson_path}.")
    else:
        gdf = gpd.read_file(district_geojson_path)
        if gdf.crs is None: gdf.set_crs(epsg=4326, inplace=True)
        district_col = next((col for col in ['dtname', 'NAME_2', 'district', 'Dist_Name', 'district_name', 'REGNAME'] if col in gdf.columns), None)
        gdf[district_col] = gdf[district_col].astype(str).str.strip()
            
        col3, col4 = st.columns([1.2, 2.8])
        
        with col3:
            st.subheader("1. Select Surveyed Regions")
            all_districts = sorted(list(set([d for d in gdf[district_col].dropna().tolist() if d != "nan"])))
            ideal_defaults = ["ahmedabad", "anand", "vadodara", "kheda", "panchmahal", "panch mahal", "dahod", "mahisagar", "chhotaudepur", "botad"]
            selected_districts = st.multiselect("Highlight districts:", options=all_districts, default=[d for d in all_districts if str(d).lower().strip() in ideal_defaults], key="dist_select")
            
            st.subheader("2. Map Styling")
            basemap_choice_d = st.selectbox("Background Map View", ["None (White Background)", "OpenStreetMap (Street View)", "Esri World Imagery (Satellite)"], key="dist_basemap")
            color_map_choice = st.selectbox("Highlight Palette", ["None (White)", "Set2", "Dark2", "Paired", "tab10", "Greens", "Blues", "YlGnBu", "OrRd", "viridis", "cividis", "plasma", "Pastel1", "Set3", "Accent"], key="dist_color")
            font_size_d = st.slider("Region Label Font Size", 4, 40, 12, key="dist_font")
            orientation_d = st.selectbox("Page Orientation", ["Landscape (A4)", "Portrait (A4)"], key="dist_ori")
            margin_multiplier_d = st.slider("Map Blank Space (Zoom Out)", 0.05, 1.50, 0.35, 0.05, key="dist_margin", help="Increase this to shrink the map and make more room for the Inset and Compass.")

            st.subheader("3. Element Placement")
            col_lg1, col_lg2 = st.columns(2)
            legend_pos_d = col_lg1.selectbox("Legend Position", list(legend_mapping.keys()), index=0, key="dist_legend")
            # --- NEW: Legend Font Size Slider ---
            legend_font_size_d = col_lg2.slider("Legend Font Size", 6, 24, 10, key="dist_leg_font")
            
            col_el1, col_el2 = st.columns(2)
            with col_el1: inset_pos = st.selectbox("Inset Base Pos", ["Top Left", "Top Right", "Bottom Left", "Bottom Right"], index=0, key="dist_inset")
            with col_el2: compass_pos = st.selectbox("Compass Base Pos", ["Top Right", "Top Left", "Bottom Right", "Bottom Left"], index=0, key="dist_compass")
            
            with st.expander("🛠️ Fine-Tune Inset & Compass (Fix Overlaps)"):
                st.markdown("<small>If elements still overlap your map, use these sliders to push them into empty space.</small>", unsafe_allow_html=True)
                cx1, cx2 = st.columns(2)
                base_i = {"Top Left": [0.05, 0.55], "Top Right": [0.70, 0.55], "Bottom Left": [0.05, 0.05], "Bottom Right": [0.70, 0.05]}[inset_pos]
                base_c = {"Top Right": [0.85, 0.70], "Top Left": [0.05, 0.70], "Bottom Right": [0.85, 0.05], "Bottom Left": [0.05, 0.05]}[compass_pos]
                
                inset_x_d = cx1.slider("Inset X (Left ↔ Right)", 0.0, 1.0, base_i[0], 0.01, key="ix_d")
                inset_y_d = cx1.slider("Inset Y (Bottom ↕ Top)", 0.0, 1.0, base_i[1], 0.01, key="iy_d")
                compass_x_d = cx2.slider("Compass X (Left ↔ Right)", 0.0, 1.0, base_c[0], 0.01, key="cx_d")
                compass_y_d = cx2.slider("Compass Y (Bottom ↕ Top)", 0.0, 1.0, base_c[1], 0.01, key="cy_d")
            
            # --- DYNAMIC SURVEY POINTS ---
            st.markdown("---")
            st.subheader("4. Survey Points")
            dist_survey_data = []
            
            for layer_id in st.session_state.dist_survey_layers:
                with st.container(border=True):
                    c1, c2 = st.columns([4, 1])
                    c1.markdown(f"**Survey Layer**")
                    if c2.button("🗑️", key=f"del_ds_{layer_id}"):
                        st.session_state.dist_survey_layers.remove(layer_id)
                        st.rerun()
                        
                    pt_lbl = st.text_input("Legend Name", f"Survey {layer_id}", key=f"dl_lbl_{layer_id}")
                    col_pt1, col_pt2 = st.columns(2)
                    pt_color = col_pt1.color_picker("Color", "#FF0000" if layer_id%2!=0 else "#0000FF", key=f"dl_col_{layer_id}")
                    pt_style = col_pt2.selectbox("Shape", ["Circle", "Map Pin", "Square", "Triangle", "Diamond", "Star"], key=f"dl_sty_{layer_id}")
                    
                    uploaded_file = st.file_uploader("Upload CSV", type=["csv"], key=f"dl_csv_{layer_id}")
                    if uploaded_file:
                        df_pts = process_uploaded_csv(uploaded_file)
                        if df_pts is not None:
                            dist_survey_data.append({"df": df_pts, "label": pt_lbl, "color": pt_color, "style": pt_style})
                        
            if st.button("➕ Add Survey Layer", key="add_dist_surv"):
                st.session_state.dist_survey_layers.append(st.session_state.next_dist_survey)
                st.session_state.next_dist_survey += 1
                st.rerun()

            # --- DYNAMIC IMPORTANT LOCATIONS ---
            st.markdown("---")
            st.subheader("5. Important Locations")
            show_loc_labels_d = st.checkbox("Show Location Names on Map", value=True, key="dist_loc_showlbl")
            
            dist_loc_data = []
            
            for layer_id in st.session_state.dist_loc_layers:
                with st.container(border=True):
                    c1, c2 = st.columns([4, 1])
                    c1.markdown(f"**Location Layer**")
                    if c2.button("🗑️", key=f"del_dl_{layer_id}"):
                        st.session_state.dist_loc_layers.remove(layer_id)
                        st.rerun()
                        
                    loc_lbl = st.text_input("Layer Name (General)", "Locations", key=f"dloc_lbl_{layer_id}")
                    
                    # --- NEW: Abbreviation Toggle ---
                    use_abbr_d = st.checkbox("Use Short Names on Map & Detail in Legend", value=False, key=f"dloc_abbr_{layer_id}")
                    
                    col_loc1, col_loc2 = st.columns(2)
                    loc_color = col_loc1.color_picker("Color", "#FFFF00", key=f"dloc_col_{layer_id}")
                    loc_style = col_loc2.selectbox("Shape", ["Map Pin", "Star", "Diamond", "Square", "Circle", "Triangle"], key=f"dloc_sty_{layer_id}")
                    
                    uploaded_loc = st.file_uploader("Upload CSV", type=["csv"], key=f"dloc_csv_{layer_id}")
                    if uploaded_loc:
                        df_loc = process_uploaded_csv(uploaded_loc)
                        if df_loc is not None:
                            dist_loc_data.append({
                                "df": df_loc, "label": loc_lbl, "color": loc_color, 
                                "style": loc_style, "use_abbr": use_abbr_d
                            })
                            
            if st.button("➕ Add Location Layer", key="add_dist_loc"):
                st.session_state.dist_loc_layers.append(st.session_state.next_dist_loc)
                st.session_state.next_dist_loc += 1
                st.rerun()

        # --- PLOTTING LOGIC DISTRICT ---
        with col4:
            fig, ax_main = plt.subplots(figsize=(11.69, 8.27) if orientation_d == "Landscape (A4)" else (8.27, 11.69), dpi=300)
            
            right_margin = 0.70 if "Outside" in legend_pos_d else 0.95
            plt.subplots_adjust(top=0.90, bottom=0.05, left=0.05, right=right_margin)
            
            poly_alpha_d = 1.0 if basemap_choice_d == "None (White Background)" else 0.55
            base_poly_alpha_d = 1.0 if basemap_choice_d == "None (White Background)" else 0.15

            gdf.plot(ax=ax_main, color='white' if basemap_choice_d == "None (White Background)" else 'none', edgecolor='black', alpha=base_poly_alpha_d, zorder=1)
            
            # --- CUSTOM LEGEND HANDLES LIST ---
            custom_legend_handles_d = []

            if selected_districts:
                highlighted_gdf = gdf[gdf[district_col].isin(selected_districts)]
                if color_map_choice == "None (White)":
                    highlighted_gdf.plot(ax=ax_main, color='white', edgecolor='black', linewidth=1.5, alpha=poly_alpha_d, zorder=2)
                else:
                    highlighted_gdf.plot(ax=ax_main, column=district_col, cmap=color_map_choice, edgecolor='black', linewidth=1.5, alpha=poly_alpha_d, zorder=2)
                
                minx, miny, maxx, maxy = highlighted_gdf.total_bounds
                margin_x = max((maxx - minx) * margin_multiplier_d, 0.05)
                margin_y = max((maxy - miny) * margin_multiplier_d, 0.05)
                ax_main.set_xlim(minx - margin_x, maxx + margin_x)
                ax_main.set_ylim(miny - margin_y, maxy + margin_y)
                
                import matplotlib.patheffects as pe
                for idx, row in highlighted_gdf.iterrows():
                    centroid = row.geometry.centroid
                    txt_color = 'white' if basemap_choice_d == "Esri World Imagery (Satellite)" else 'black'
                    outline_color = 'black' if txt_color == 'white' else 'white'
                    ax_main.annotate(text=row[district_col], xy=(centroid.x, centroid.y), ha='center', va='center', fontsize=font_size_d, fontweight='bold', color=txt_color, path_effects=[pe.withStroke(linewidth=3, foreground=outline_color)], zorder=4)
                    
                # Plot Survey Points
                for pt in dist_survey_data:
                    size = 800 if pt['style'] == "Map Pin" else 60
                    # Plot point but hide from standard legend logic
                    ax_main.scatter(pt['df']['Longitude'].values, pt['df']['Latitude'].values, color=pt['color'], edgecolor='black', marker=marker_map[pt['style']], s=size, zorder=5, linewidth=0.8, label="_nolegend_")
                    
                    # Create clean Custom Legend Handle
                    h = mlines.Line2D([], [], color='none', marker=legend_marker_map[pt['style']], markerfacecolor=pt['color'], markeredgecolor='black', markersize=12, label=pt['label'])
                    custom_legend_handles_d.append(h)
                
                # Plot Locations
                for loc in dist_loc_data:
                    size = 1200 if loc['style'] == "Map Pin" else 150
                    ax_main.scatter(loc['df']['Longitude'].values, loc['df']['Latitude'].values, color=loc['color'], edgecolor='black', marker=marker_map[loc['style']], s=size, zorder=6, linewidth=1.2, label="_nolegend_")
                    
                    if show_loc_labels_d:
                        name_col = next((c for c in loc['df'].columns if c.lower() in ['name', 'location', 'label', 'site']), None)
                        short_col = next((c for c in loc['df'].columns if c.lower() in ['short name', 'short', 'abbr', 'abbreviation']), None)
                        
                        y_offset = 25 if loc['style'] == "Map Pin" else 15
                        txt_color_l = 'white' if basemap_choice_d == "Esri World Imagery (Satellite)" else 'black'
                        out_color_l = 'black' if txt_color_l == 'white' else 'white'
                        
                        for idx, r in loc['df'].iterrows():
                            # Resolve names
                            full_val = str(r[name_col]) if name_col and pd.notna(r[name_col]) else f"Loc {idx+1}"
                            short_val = str(r[short_col]) if short_col and pd.notna(r[short_col]) else str(idx+1)
                            
                            # Determine what text prints on the map
                            display_text = short_val if loc['use_abbr'] else full_val
                            
                            ax_main.annotate(display_text, (r['Longitude'], r['Latitude']), 
                                             xytext=(0, y_offset), textcoords='offset points', 
                                             ha='center', va='bottom', fontsize=max(font_size_d - 2, 8), fontweight='bold', 
                                             color=txt_color_l, path_effects=[pe.withStroke(linewidth=2.5, foreground=out_color_l)], zorder=7)
                            
                            # If building explicit keys, append a legend line for EACH location
                            if loc['use_abbr']:
                                h = mlines.Line2D([], [], color='none', marker=legend_marker_map[loc['style']], markerfacecolor=loc['color'], markeredgecolor='black', markersize=12, label=f"{short_val} - {full_val}")
                                custom_legend_handles_d.append(h)
                                
                    # If NOT building explicit keys, append ONE line for the whole layer
                    if not loc['use_abbr']:
                         h = mlines.Line2D([], [], color='none', marker=legend_marker_map[loc['style']], markerfacecolor=loc['color'], markeredgecolor='black', markersize=12, label=loc['label'])
                         custom_legend_handles_d.append(h)

                if basemap_choice_d == "OpenStreetMap (Street View)":
                    cx.add_basemap(ax_main, crs=gdf.crs.to_string(), source=cx.providers.OpenStreetMap.Mapnik, zorder=0)
                elif basemap_choice_d == "Esri World Imagery (Satellite)":
                    cx.add_basemap(ax_main, crs=gdf.crs.to_string(), source=cx.providers.Esri.WorldImagery, zorder=0)

                # --- NEW: Enhanced Custom Legend ---
                if legend_pos_d != "None" and custom_legend_handles_d:
                    leg_config = legend_mapping[legend_pos_d]
                    kwargs = {
                        "loc": leg_config["loc"], "title": "Legend", 
                        "fontsize": legend_font_size_d, "title_fontsize": legend_font_size_d + 2, 
                        "frameon": True, "facecolor": 'white', "framealpha": 0.9, "edgecolor": 'black', 
                        "shadow": True, "borderpad": 1.2, "labelspacing": 1.0, "handletextpad": 0.8
                    }
                    if leg_config["bbox"] is not None:
                        kwargs["bbox_to_anchor"] = leg_config["bbox"]
                        
                    ax_main.legend(handles=custom_legend_handles_d, **kwargs)

                # Compass & Inset
                ax_compass = fig.add_axes([compass_x_d, compass_y_d, 0.1, 0.1])
                ax_compass.set_axis_off(); ax_compass.set_aspect('equal')
                w = 0.15 
                polys = [[[0,0],[0,1],[w,0], 'black'], [[0,0],[0,1],[-w,0], 'white'], [[0,0],[0,-1],[w,0], 'white'], [[0,0],[0,-1],[-w,0], 'black'], [[0,0],[1,0],[0,w], 'black'], [[0,0],[1,0],[0,-w], 'white'], [[0,0],[-1,0],[0,w], 'white'], [[0,0],[-1,0],[0,-w], 'black']]
                for p in polys: ax_compass.add_patch(patches.Polygon(p[:3], facecolor=p[3], edgecolor='black', lw=0.5))
                ax_compass.text(0, 1.25, 'N', ha='center', va='center', fontweight='bold', fontsize=14)
                for txt, pos in [('S', (0, -1.25)), ('E', (1.25, 0)), ('W', (-1.25, 0))]: ax_compass.text(*pos, txt, ha='center', va='center', fontsize=10, fontweight='bold')
                ax_compass.set(xlim=(-1.5, 1.5), ylim=(-1.5, 1.5))

                ax_inset = fig.add_axes([inset_x_d, inset_y_d, 0.25, 0.25]) 
                gdf.plot(ax=ax_inset, color='white', edgecolor='gray', linewidth=0.5)
                highlighted_gdf.plot(ax=ax_inset, color='#d3d3d3' if color_map_choice == "None (White)" else '#ff66b2', edgecolor='black', linewidth=0.8)
                ax_inset.set_xticks([]); ax_inset.set_yticks([])
                ax_inset.set_title("Gujarat State", fontsize=11, fontweight='bold', pad=4)
                for spine in ax_inset.spines.values(): spine.set_edgecolor('black')
                
            else:
                ax_main.text(0.5, 0.5, "Select districts to render map.", ha='center', va='center', transform=ax_main.transAxes, fontsize=14, color='gray')

            ax_main.set_xticks([]); ax_main.set_yticks([]); ax_main.set_frame_on(False)
            st.pyplot(fig)
            
            buf = io.BytesIO()
            fig.savefig(buf, format="png", dpi=300, bbox_inches='tight')
            st.download_button("Download District Map (PNG)", data=buf.getvalue(), file_name="academic_survey_district_map.png", mime="image/png", key="btn_dist")


# ==========================================
# TAB 3: STATIC TALUKA MAP
# ==========================================
with tab3:
    st.header("Static Taluka Highlight Map")
    taluka_geojson_path = "data/gujarat_talukas.geojson"
    state_geojson_path = "data/gujarat_state.geojson"
    
    if not os.path.exists(taluka_geojson_path):
        st.error(f"Cannot find {taluka_geojson_path}.")
    else:
        gdf_talukas = gpd.read_file(taluka_geojson_path)
        if gdf_talukas.crs is None: gdf_talukas.set_crs(epsg=4326, inplace=True)
        taluka_col = next((c for c in ['NAME_3', 'taluka', 'Taluka_Name', 'taluka_name', 'TALUKA', 'Sub_Distri', 'subdistrict', 'sdtname', 'tehsil_name', 'Tehsil', 'NAME_2'] if c in gdf_talukas.columns), None)
        gdf_talukas[taluka_col] = gdf_talukas[taluka_col].astype(str).str.strip()
            
        col5, col6 = st.columns([1.2, 2.8])
        
        with col5:
            st.subheader("1. Select Surveyed Regions")
            all_talukas = sorted(list(set([t for t in gdf_talukas[taluka_col].dropna().tolist() if t != "nan"])))
            selected_talukas = st.multiselect("Highlight talukas:", options=all_talukas, key="taluka_select")
            
            st.subheader("2. Map Styling")
            basemap_choice_t = st.selectbox("Background Map View", ["None (White Background)", "OpenStreetMap (Street View)", "Esri World Imagery (Satellite)"], key="taluka_basemap")
            color_map_choice_taluka = st.selectbox("Highlight Palette", ["None (White)", "Set2", "Dark2", "Paired", "tab10", "Greens", "Blues", "YlGnBu", "OrRd", "viridis", "cividis", "plasma", "Pastel1", "Set3", "Accent"], key="taluka_color")
            font_size_t = st.slider("Region Label Font Size", 4, 40, 10, key="taluka_font")
            orientation_t = st.selectbox("Page Orientation", ["Landscape (A4)", "Portrait (A4)"], key="taluka_ori")
            margin_multiplier_t = st.slider("Map Blank Space (Zoom Out)", 0.05, 1.50, 0.35, 0.05, key="taluka_margin", help="Increase this to shrink the map and make more room for the Inset and Compass.")

            st.subheader("3. Element Placement")
            col_tl1, col_tl2 = st.columns(2)
            legend_pos_t = col_tl1.selectbox("Legend Position", list(legend_mapping.keys()), index=0, key="taluka_legend")
            # --- NEW: Legend Font Size Slider ---
            legend_font_size_t = col_tl2.slider("Legend Font Size", 6, 24, 10, key="taluka_leg_font")
            
            col_el1_t, col_el2_t = st.columns(2)
            with col_el1_t: inset_pos_t = st.selectbox("Inset Base Pos", ["Top Left", "Top Right", "Bottom Left", "Bottom Right"], index=0, key="taluka_inset")
            with col_el2_t: compass_pos_t = st.selectbox("Compass Base Pos", ["Top Right", "Top Left", "Bottom Right", "Bottom Left"], index=0, key="taluka_compass")
            
            with st.expander("🛠️ Fine-Tune Inset & Compass (Fix Overlaps)"):
                st.markdown("<small>If elements still overlap your map, use these sliders to push them into empty space.</small>", unsafe_allow_html=True)
                cx3, cx4 = st.columns(2)
                base_i_t = {"Top Left": [0.05, 0.55], "Top Right": [0.70, 0.55], "Bottom Left": [0.05, 0.05], "Bottom Right": [0.70, 0.05]}[inset_pos_t]
                base_c_t = {"Top Right": [0.85, 0.70], "Top Left": [0.05, 0.70], "Bottom Right": [0.85, 0.05], "Bottom Left": [0.05, 0.05]}[compass_pos_t]
                
                inset_x_t = cx3.slider("Inset X (Left ↔ Right)", 0.0, 1.0, base_i_t[0], 0.01, key="ix_t")
                inset_y_t = cx3.slider("Inset Y (Bottom ↕ Top)", 0.0, 1.0, base_i_t[1], 0.01, key="iy_t")
                compass_x_t = cx4.slider("Compass X (Left ↔ Right)", 0.0, 1.0, base_c_t[0], 0.01, key="cx_t")
                compass_y_t = cx4.slider("Compass Y (Bottom ↕ Top)", 0.0, 1.0, base_c_t[1], 0.01, key="cy_t")

            # --- DYNAMIC SURVEY POINTS ---
            st.markdown("---")
            st.subheader("4. Survey Points")
            taluka_survey_data = [] 
            
            for layer_id in st.session_state.taluka_survey_layers:
                with st.container(border=True):
                    c1, c2 = st.columns([4, 1])
                    c1.markdown(f"**Survey Layer**")
                    if c2.button("🗑️", key=f"del_ts_{layer_id}"):
                        st.session_state.taluka_survey_layers.remove(layer_id)
                        st.rerun()
                        
                    pt_lbl_t = st.text_input("Legend Name", f"Survey {layer_id}", key=f"tl_lbl_{layer_id}")
                    col_pt1_t, col_pt2_t = st.columns(2)
                    pt_color_t = col_pt1_t.color_picker("Color", "#FF0000" if layer_id%2!=0 else "#0000FF", key=f"tl_col_{layer_id}")
                    pt_style_t = col_pt2_t.selectbox("Shape", ["Circle", "Map Pin", "Square", "Triangle", "Diamond", "Star"], key=f"tl_sty_{layer_id}")
                    
                    uploaded_file_t = st.file_uploader("Upload CSV", type=["csv"], key=f"tl_csv_{layer_id}")
                    if uploaded_file_t:
                        df_pts_t = process_uploaded_csv(uploaded_file_t)
                        if df_pts_t is not None:
                            taluka_survey_data.append({"df": df_pts_t, "label": pt_lbl_t, "color": pt_color_t, "style": pt_style_t})
            
            if st.button("➕ Add Survey Layer", key="add_taluka_surv"):
                st.session_state.taluka_survey_layers.append(st.session_state.next_taluka_survey)
                st.session_state.next_taluka_survey += 1
                st.rerun()

            # --- DYNAMIC IMPORTANT LOCATIONS ---
            st.markdown("---")
            st.subheader("5. Important Locations")
            show_loc_labels_t = st.checkbox("Show Location Names on Map", value=True, key="taluka_loc_showlbl")
            
            taluka_loc_data = []
            
            for layer_id in st.session_state.taluka_loc_layers:
                with st.container(border=True):
                    c1, c2 = st.columns([4, 1])
                    c1.markdown(f"**Location Layer**")
                    if c2.button("🗑️", key=f"del_tloc_{layer_id}"):
                        st.session_state.taluka_loc_layers.remove(layer_id)
                        st.rerun()
                        
                    loc_lbl_t = st.text_input("Layer Name (General)", "Locations", key=f"tloc_lbl_{layer_id}")
                    
                    # --- NEW: Abbreviation Toggle ---
                    use_abbr_t = st.checkbox("Use Short Names on Map & Detail in Legend", value=False, key=f"tloc_abbr_{layer_id}")

                    col_loc1_t, col_loc2_t = st.columns(2)
                    loc_color_t = col_loc1_t.color_picker("Color", "#FFFF00", key=f"tloc_col_{layer_id}")
                    loc_style_t = col_loc2_t.selectbox("Shape", ["Map Pin", "Star", "Diamond", "Square", "Circle", "Triangle"], key=f"tloc_sty_{layer_id}")
                    
                    uploaded_loc_t = st.file_uploader("Upload CSV", type=["csv"], key=f"tloc_csv_{layer_id}")
                    if uploaded_loc_t:
                        df_loc_t = process_uploaded_csv(uploaded_loc_t)
                        if df_loc_t is not None:
                            taluka_loc_data.append({
                                "df": df_loc_t, "label": loc_lbl_t, "color": loc_color_t, 
                                "style": loc_style_t, "use_abbr": use_abbr_t
                            })
                            
            if st.button("➕ Add Location Layer", key="add_taluka_loc"):
                st.session_state.taluka_loc_layers.append(st.session_state.next_taluka_loc)
                st.session_state.next_taluka_loc += 1
                st.rerun()

        # --- PLOTTING LOGIC TALUKA ---
        with col6:
            fig_t, ax_main_t = plt.subplots(figsize=(11.69, 8.27) if orientation_t == "Landscape (A4)" else (8.27, 11.69), dpi=300)
            
            right_margin_t = 0.70 if "Outside" in legend_pos_t else 0.95
            plt.subplots_adjust(top=0.90, bottom=0.05, left=0.05, right=right_margin_t)
            
            poly_alpha_t = 1.0 if basemap_choice_t == "None (White Background)" else 0.55
            base_poly_alpha_t = 1.0 if basemap_choice_t == "None (White Background)" else 0.15

            gdf_talukas.plot(ax=ax_main_t, color='white' if basemap_choice_t == "None (White Background)" else 'none', edgecolor='black', linewidth=0.3, alpha=base_poly_alpha_t, zorder=1)

            # --- CUSTOM LEGEND HANDLES LIST ---
            custom_legend_handles_t = []

            if selected_talukas:
                highlighted_talukas = gdf_talukas[gdf_talukas[taluka_col].isin(selected_talukas)]
                if color_map_choice_taluka == "None (White)":
                    highlighted_talukas.plot(ax=ax_main_t, color='white', edgecolor='black', linewidth=1.5, alpha=poly_alpha_t, zorder=2)
                else:
                    highlighted_talukas.plot(ax=ax_main_t, column=taluka_col, cmap=color_map_choice_taluka, edgecolor='black', linewidth=1.5, alpha=poly_alpha_t, zorder=2)
                
                minx, miny, maxx, maxy = highlighted_talukas.total_bounds
                margin_x_t = max((maxx - minx) * margin_multiplier_t, 0.05)
                margin_y_t = max((maxy - miny) * margin_multiplier_t, 0.05)
                ax_main_t.set_xlim(minx - margin_x_t, maxx + margin_x_t)
                ax_main_t.set_ylim(miny - margin_y_t, maxy + margin_y_t)
                
                import matplotlib.patheffects as pe
                for idx, row in highlighted_talukas.iterrows():
                    if row.geometry is not None and not row.geometry.is_empty:
                        centroid = row.geometry.centroid
                        txt_color = 'white' if basemap_choice_t == "Esri World Imagery (Satellite)" else 'black'
                        outline_color = 'black' if txt_color == 'white' else 'white'
                        ax_main_t.annotate(text=row[taluka_col], xy=(centroid.x, centroid.y), ha='center', va='center', fontsize=font_size_t, fontweight='bold', color=txt_color, path_effects=[pe.withStroke(linewidth=3, foreground=outline_color)], zorder=4)
                        
                # Plot Survey Points
                for pt in taluka_survey_data:
                    size = 800 if pt['style'] == "Map Pin" else 60
                    # Plot point but hide from standard legend logic
                    ax_main_t.scatter(pt['df']['Longitude'].values, pt['df']['Latitude'].values, color=pt['color'], edgecolor='black', marker=marker_map[pt['style']], s=size, zorder=5, linewidth=0.8, label="_nolegend_")
                    
                    # Create clean Custom Legend Handle
                    h = mlines.Line2D([], [], color='none', marker=legend_marker_map[pt['style']], markerfacecolor=pt['color'], markeredgecolor='black', markersize=12, label=pt['label'])
                    custom_legend_handles_t.append(h)

                # Plot Locations
                for loc in taluka_loc_data:
                    size = 1200 if loc['style'] == "Map Pin" else 150
                    ax_main_t.scatter(loc['df']['Longitude'].values, loc['df']['Latitude'].values, color=loc['color'], edgecolor='black', marker=marker_map[loc['style']], s=size, zorder=6, linewidth=1.2, label="_nolegend_")
                    
                    if show_loc_labels_t:
                        name_col_t = next((c for c in loc['df'].columns if c.lower() in ['name', 'location', 'label', 'site']), None)
                        short_col_t = next((c for c in loc['df'].columns if c.lower() in ['short name', 'short', 'abbr', 'abbreviation']), None)
                        
                        y_offset_t = 20 if loc['style'] == "Map Pin" else 15
                        txt_color_l = 'white' if basemap_choice_t == "Esri World Imagery (Satellite)" else 'black'
                        out_color_l = 'black' if txt_color_l == 'white' else 'white'
                        
                        for idx, r in loc['df'].iterrows():
                            # Resolve names
                            full_val = str(r[name_col_t]) if name_col_t and pd.notna(r[name_col_t]) else f"Loc {idx+1}"
                            short_val = str(r[short_col_t]) if short_col_t and pd.notna(r[short_col_t]) else str(idx+1)
                            
                            # Determine what text prints on the map
                            display_text = short_val if loc['use_abbr'] else full_val
                            
                            ax_main_t.annotate(display_text, (r['Longitude'], r['Latitude']), 
                                               xytext=(0, y_offset_t), textcoords='offset points', 
                                               ha='center', va='bottom', fontsize=max(font_size_t - 2, 8), fontweight='bold', 
                                               color=txt_color_l, path_effects=[pe.withStroke(linewidth=2.5, foreground=out_color_l)], zorder=7)
                            
                            # If building explicit keys, append a legend line for EACH location
                            if loc['use_abbr']:
                                h = mlines.Line2D([], [], color='none', marker=legend_marker_map[loc['style']], markerfacecolor=loc['color'], markeredgecolor='black', markersize=12, label=f"{short_val} - {full_val}")
                                custom_legend_handles_t.append(h)
                                
                    # If NOT building explicit keys, append ONE line for the whole layer
                    if not loc['use_abbr']:
                         h = mlines.Line2D([], [], color='none', marker=legend_marker_map[loc['style']], markerfacecolor=loc['color'], markeredgecolor='black', markersize=12, label=loc['label'])
                         custom_legend_handles_t.append(h)
                
                if basemap_choice_t == "OpenStreetMap (Street View)":
                    cx.add_basemap(ax_main_t, crs=gdf_talukas.crs.to_string(), source=cx.providers.OpenStreetMap.Mapnik, zorder=0)
                elif basemap_choice_t == "Esri World Imagery (Satellite)":
                    cx.add_basemap(ax_main_t, crs=gdf_talukas.crs.to_string(), source=cx.providers.Esri.WorldImagery, zorder=0)

                # --- NEW: Enhanced Custom Legend ---
                if legend_pos_t != "None" and custom_legend_handles_t:
                    leg_config_t = legend_mapping[legend_pos_t]
                    kwargs_t = {
                        "loc": leg_config_t["loc"], "title": "Legend", 
                        "fontsize": legend_font_size_t, "title_fontsize": legend_font_size_t + 2, 
                        "frameon": True, "facecolor": 'white', "framealpha": 0.9, "edgecolor": 'black', 
                        "shadow": True, "borderpad": 1.2, "labelspacing": 1.0, "handletextpad": 0.8
                    }
                    if leg_config_t["bbox"] is not None:
                        kwargs_t["bbox_to_anchor"] = leg_config_t["bbox"]
                        
                    ax_main_t.legend(handles=custom_legend_handles_t, **kwargs_t)

                # Compass & Inset
                ax_compass_t = fig_t.add_axes([compass_x_t, compass_y_t, 0.1, 0.1])
                ax_compass_t.set_axis_off(); ax_compass_t.set_aspect('equal')
                w = 0.15 
                polys = [[[0,0],[0,1],[w,0], 'black'], [[0,0],[0,1],[-w,0], 'white'], [[0,0],[0,-1],[w,0], 'white'], [[0,0],[0,-1],[-w,0], 'black'], [[0,0],[1,0],[0,w], 'black'], [[0,0],[1,0],[0,-w], 'white'], [[0,0],[-1,0],[0,w], 'white'], [[0,0],[-1,0],[0,-w], 'black']]
                for p in polys: ax_compass_t.add_patch(patches.Polygon(p[:3], facecolor=p[3], edgecolor='black', lw=0.5))
                ax_compass_t.text(0, 1.25, 'N', ha='center', va='center', fontweight='bold', fontsize=14)
                for txt, pos in [('S', (0, -1.25)), ('E', (1.25, 0)), ('W', (-1.25, 0))]: ax_compass_t.text(*pos, txt, ha='center', va='center', fontsize=10, fontweight='bold')
                ax_compass_t.set(xlim=(-1.5, 1.5), ylim=(-1.5, 1.5))

                ax_inset_t = fig_t.add_axes([inset_x_t, inset_y_t, 0.25, 0.25]) 
                if os.path.exists(state_geojson_path):
                    gpd.read_file(state_geojson_path).plot(ax=ax_inset_t, color='white', edgecolor='gray', linewidth=0.5)
                else:
                    gdf_talukas.plot(ax=ax_inset_t, color='white', edgecolor='gray', linewidth=0.1) 
                highlighted_talukas.plot(ax=ax_inset_t, color='#d3d3d3' if color_map_choice_taluka == "None (White)" else '#ff66b2', edgecolor='black', linewidth=0.8)
                ax_inset_t.set_xticks([]); ax_inset_t.set_yticks([])
                ax_inset_t.set_title("Gujarat State", fontsize=11, fontweight='bold', pad=4)
                for spine in ax_inset_t.spines.values(): spine.set_edgecolor('black')
                
            else:
                ax_main_t.text(0.5, 0.5, "Select talukas to render map.", ha='center', va='center', transform=ax_main_t.transAxes, fontsize=14, color='gray')

            ax_main_t.set_xticks([]); ax_main_t.set_yticks([]); ax_main_t.set_frame_on(False)
            st.pyplot(fig_t)
            
            buf_t = io.BytesIO()
            fig_t.savefig(buf_t, format="png", dpi=300, bbox_inches='tight')
            st.download_button("Download Taluka Map (PNG)", data=buf_t.getvalue(), file_name="academic_survey_taluka_map.png", mime="image/png", key="btn_taluka")
