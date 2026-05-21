import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import matplotlib.path as mpath
import io
import os

# --- Page Configuration ---
st.set_page_config(page_title="Ph.D. Survey Map Generator", layout="wide")

st.title("Gujarat Survey Map Generator")
st.markdown("Generate professional, publication-ready maps for your Ph.D. thesis.")

# --- Custom Map Pin Path ---
pin_verts = [
    (0.0, -1.0),   # Bottom tip
    (0.5, -0.3),   # Right bottom curve
    (0.8, 0.4),    # Right top curve
    (0.0, 1.0),    # Top center
    (-0.8, 0.4),   # Left top curve
    (-0.5, -0.3),  # Left bottom curve
    (0.0, -1.0)    # Bottom tip
]
pin_codes = [
    mpath.Path.MOVETO, mpath.Path.CURVE4, mpath.Path.CURVE4,
    mpath.Path.CURVE4, mpath.Path.CURVE4, mpath.Path.CURVE4,
    mpath.Path.CLOSEPOLY
]
custom_pin = mpath.Path(pin_verts, pin_codes)

# Dictionary to map user-friendly shape names to Matplotlib markers
marker_map = {
    "Map Pin": custom_pin, "Circle": "o", "Square": "s",
    "Triangle": "^", "Diamond": "D", "Star": "*"
}

# --- Load User's Custom Sample CSV ---
sample_csv_path = "1 - Copy.csv"
if os.path.exists(sample_csv_path):
    with open(sample_csv_path, "rb") as file:
        sample_csv_data = file.read()
else:
    sample_csv_data = b"Latitude,Longitude,Name\n"
    st.sidebar.warning(f"⚠️ Could not find '{sample_csv_path}'. Please make sure it is saved in the same folder as this script.")

# --- Initialize Dynamic Session States ---
# District Dynamic Layers
if 'dist_survey_layers' not in st.session_state: st.session_state.dist_survey_layers = [1]
if 'next_dist_survey' not in st.session_state: st.session_state.next_dist_survey = 2
if 'dist_loc_layers' not in st.session_state: st.session_state.dist_loc_layers = [1]
if 'next_dist_loc' not in st.session_state: st.session_state.next_dist_loc = 2

# Taluka Dynamic Layers
if 'taluka_survey_layers' not in st.session_state: st.session_state.taluka_survey_layers = [1]
if 'next_taluka_survey' not in st.session_state: st.session_state.next_taluka_survey = 2
if 'taluka_loc_layers' not in st.session_state: st.session_state.taluka_loc_layers = [1]
if 'next_taluka_loc' not in st.session_state: st.session_state.next_taluka_loc = 2

# Helper function to process uploaded CSVs
def process_uploaded_csv(uploaded_file):
    df = pd.read_csv(uploaded_file)
    df.columns = df.columns.str.strip()
    df = df.loc[:, ~df.columns.duplicated()]
    if 'Latitude' in df.columns and 'Longitude' in df.columns:
        df['Latitude'] = pd.to_numeric(df['Latitude'], errors='coerce')
        df['Longitude'] = pd.to_numeric(df['Longitude'], errors='coerce')
        return df.dropna(subset=['Latitude', 'Longitude'])
    return None

# --- Setup Tabs ---
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
                    loc_name = row.get('Location', "Unknown Location")
                    tooltip_text = f"<b>Location:</b> {loc_name}"
                    if color_col != "None (All Red)" and pd.notna(row[color_col]):
                        tooltip_text += f"<br><b>{color_col}:</b> {row[color_col]}"
                    marker_color = color_map.get(row[color_col], "gray") if color_col != "None (All Red)" and pd.notna(row[color_col]) else "red"
                    folium.Marker(
                        location=[row['Latitude'], row['Longitude']],
                        icon=folium.Icon(color=marker_color, icon="info-sign"), # Built-in teardrop pin
                        tooltip=tooltip_text,
                        popup=loc_name
                    ).add_to(m)
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
        district_col = next((col for col in ['dtname', 'NAME_2', 'district', 'Dist_Name', 'district_name', 'REGNAME'] if col in gdf.columns), None)
        gdf[district_col] = gdf[district_col].astype(str).str.strip()
            
        col3, col4 = st.columns([1.2, 2.8]) # Adjusted column ratio for dynamic UI
        
        with col3:
            st.subheader("1. Select Surveyed Regions")
            all_districts = sorted(list(set([d for d in gdf[district_col].dropna().tolist() if d != "nan"])))
            ideal_defaults = ["ahmedabad", "anand", "vadodara", "kheda", "panchmahal", "panch mahal", "dahod", "mahisagar", "chhotaudepur", "botad"]
            selected_districts = st.multiselect("Highlight districts:", options=all_districts, default=[d for d in all_districts if str(d).lower().strip() in ideal_defaults], key="dist_select")
            
            st.subheader("2. Map Styling")
            modern_palettes = ["None (White)", "Set2", "Dark2", "Paired", "tab10", "Greens", "Blues", "YlGnBu", "OrRd", "viridis", "cividis", "plasma", "Pastel1", "Set3", "Accent"]
            color_map_choice = st.selectbox("Highlight Palette", modern_palettes, key="dist_color")
            font_size_d = st.slider("Label Font Size", 4, 40, 12, key="dist_font")
            orientation_d = st.selectbox("Page Orientation", ["Landscape (A4)", "Portrait (A4)"], key="dist_ori")

            st.subheader("3. Element Placement")
            col_el1, col_el2 = st.columns(2)
            with col_el1: inset_pos = st.selectbox("Inset Map", ["Top Left", "Top Right", "Bottom Left", "Bottom Right"], index=0, key="dist_inset")
            with col_el2: compass_pos = st.selectbox("Compass", ["Top Right", "Top Left", "Bottom Right", "Bottom Left"], index=0, key="dist_compass")
            legend_pos_d = st.selectbox("Legend Position", ["None", "upper right", "upper left", "lower right", "lower left", "center left", "center right"], index=1, key="dist_legend")
            
            # --- DYNAMIC SURVEY POINTS ---
            st.markdown("---")
            st.subheader("4. Survey Points")
            dist_survey_data = [] # Store valid configurations here to plot later
            
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
                    pt_style = col_pt2.selectbox("Shape", ["Circle", "Square", "Triangle", "Diamond", "Star"], key=f"dl_sty_{layer_id}")
                    
                    uploaded_file = st.file_uploader("Upload CSV", type=["csv"], key=f"dl_csv_{layer_id}")
                    if uploaded_file:
                        df_pts = process_uploaded_csv(uploaded_file)
                        if df_pts is not None:
                            dist_survey_data.append({"df": df_pts, "label": pt_lbl, "color": pt_color, "style": pt_style})
                        else:
                            st.error("Missing Latitude/Longitude headers.")
            
            if st.button("➕ Add Survey Layer", key="add_dist_surv"):
                st.session_state.dist_survey_layers.append(st.session_state.next_dist_survey)
                st.session_state.next_dist_survey += 1
                st.rerun()

            # --- DYNAMIC IMPORTANT LOCATIONS ---
            st.markdown("---")
            st.subheader("5. Important Locations")
            st.download_button("📄 Download Sample Locations CSV", data=sample_csv_data, file_name="sample_locations.csv", mime="text/csv", key="sample_loc_d")
            show_loc_labels_d = st.checkbox("Show Location Names on Map", value=True, key="dist_loc_showlbl")
            
            dist_loc_data = []
            
            for layer_id in st.session_state.dist_loc_layers:
                with st.container(border=True):
                    c1, c2 = st.columns([4, 1])
                    c1.markdown(f"**Location Layer**")
                    if c2.button("🗑️", key=f"del_dl_{layer_id}"):
                        st.session_state.dist_loc_layers.remove(layer_id)
                        st.rerun()
                        
                    loc_lbl = st.text_input("Legend Name", "Locations", key=f"dloc_lbl_{layer_id}")
                    col_loc1, col_loc2 = st.columns(2)
                    loc_color = col_loc1.color_picker("Color", "#FFFF00", key=f"dloc_col_{layer_id}")
                    loc_style = col_loc2.selectbox("Shape", ["Map Pin", "Star", "Diamond", "Square", "Circle", "Triangle"], key=f"dloc_sty_{layer_id}")
                    
                    uploaded_loc = st.file_uploader("Upload CSV", type=["csv"], key=f"dloc_csv_{layer_id}")
                    if uploaded_loc:
                        df_loc = process_uploaded_csv(uploaded_loc)
                        if df_loc is not None:
                            dist_loc_data.append({"df": df_loc, "label": loc_lbl, "color": loc_color, "style": loc_style})
                        else:
                            st.error("Missing Latitude/Longitude headers.")
                            
            if st.button("➕ Add Location Layer", key="add_dist_loc"):
                st.session_state.dist_loc_layers.append(st.session_state.next_dist_loc)
                st.session_state.next_dist_loc += 1
                st.rerun()

        # --- PLOTTING LOGIC DISTRICT ---
        with col4:
            inset_coords = {"Top Left": [0.05, 0.55, 0.25, 0.25], "Top Right": [0.70, 0.55, 0.25, 0.25], "Bottom Left": [0.05, 0.05, 0.25, 0.25], "Bottom Right": [0.70, 0.05, 0.25, 0.25]}
            compass_coords = {"Top Right": [0.85, 0.70, 0.1, 0.1], "Top Left": [0.05, 0.70, 0.1, 0.1], "Bottom Right": [0.85, 0.05, 0.1, 0.1], "Bottom Left": [0.05, 0.05, 0.1, 0.1]}

            fig, ax_main = plt.subplots(figsize=(11.69, 8.27) if orientation_d == "Landscape (A4)" else (8.27, 11.69), dpi=300)
            plt.subplots_adjust(top=0.82, bottom=0.05, left=0.05, right=0.95)
            
            if selected_districts:
                highlighted_gdf = gdf[gdf[district_col].isin(selected_districts)]
                if color_map_choice == "None (White)":
                    highlighted_gdf.plot(ax=ax_main, color='white', edgecolor='black', linewidth=1.5)
                else:
                    highlighted_gdf.plot(ax=ax_main, column=district_col, cmap=color_map_choice, edgecolor='black', linewidth=1.5)
                
                minx, miny, maxx, maxy = highlighted_gdf.total_bounds
                ax_main.set_xlim(minx - max((maxx - minx) * 0.25, 0.05), maxx + max((maxx - minx) * 0.25, 0.05))
                ax_main.set_ylim(miny - max((maxy - miny) * 0.25, 0.05), maxy + max((maxy - miny) * 0.25, 0.05))
                
                import matplotlib.patheffects as pe
                for idx, row in highlighted_gdf.iterrows():
                    centroid = row.geometry.centroid
                    ax_main.annotate(text=row[district_col], xy=(centroid.x, centroid.y), ha='center', va='center', fontsize=font_size_d, fontweight='bold', color='black', path_effects=[pe.withStroke(linewidth=3, foreground="white")])
                    
                # DYNAMIC PLOT: SURVEY POINTS
                for pt in dist_survey_data:
                    ax_main.scatter(pt['df']['Longitude'].values, pt['df']['Latitude'].values, color=pt['color'], edgecolor='black', marker=marker_map[pt['style']], s=60, zorder=5, linewidth=0.8, label=pt['label'])
                
                # DYNAMIC PLOT: LOCATIONS
                for loc in dist_loc_data:
                    ax_main.scatter(loc['df']['Longitude'].values, loc['df']['Latitude'].values, color=loc['color'], edgecolor='black', marker=marker_map[loc['style']], s=250 if loc['style'] == "Map Pin" else 150, zorder=6, linewidth=1.2, label=loc['label'])
                    if show_loc_labels_d:
                        name_col = next((c for c in loc['df'].columns if c.lower() in ['name', 'location', 'label', 'site']), None)
                        if name_col:
                            for _, r in loc['df'].iterrows():
                                ax_main.annotate(str(r[name_col]), (r['Longitude'], r['Latitude']), xytext=(0, 12), textcoords='offset points', ha='center', va='bottom', fontsize=max(font_size_d - 2, 8), fontweight='bold', path_effects=[pe.withStroke(linewidth=2.5, foreground="white")], zorder=7)
                
                # LEGEND
                if legend_pos_d != "None":
                    handles, labels = ax_main.get_legend_handles_labels()
                    if handles: ax_main.legend(handles, labels, loc=legend_pos_d, title="Legend", fontsize=10, title_fontsize=12, frameon=True, facecolor='white', framealpha=0.9, edgecolor='black', shadow=True)

                # COMPASS & INSET MAP (Standard logic)
                ax_compass = fig.add_axes(compass_coords[compass_pos])
                ax_compass.set_axis_off(); ax_compass.set_aspect('equal')
                w = 0.15 
                polys = [[[0,0],[0,1],[w,0], 'black'], [[0,0],[0,1],[-w,0], 'white'], [[0,0],[0,-1],[w,0], 'white'], [[0,0],[0,-1],[-w,0], 'black'], [[0,0],[1,0],[0,w], 'black'], [[0,0],[1,0],[0,-w], 'white'], [[0,0],[-1,0],[0,w], 'white'], [[0,0],[-1,0],[0,-w], 'black']]
                for p in polys: ax_compass.add_patch(patches.Polygon(p[:3], facecolor=p[3], edgecolor='black', lw=0.5))
                ax_compass.text(0, 1.25, 'N', ha='center', va='center', fontweight='bold', fontsize=14, family='serif')
                for txt, pos in [('S', (0, -1.25)), ('E', (1.25, 0)), ('W', (-1.25, 0))]: ax_compass.text(*pos, txt, ha='center', va='center', fontsize=10, fontweight='bold', family='serif')
                ax_compass.set(xlim=(-1.5, 1.5), ylim=(-1.5, 1.5))

                ax_inset = fig.add_axes(inset_coords[inset_pos]) 
                gdf.plot(ax=ax_inset, color='white', edgecolor='gray', linewidth=0.5)
                highlighted_gdf.plot(ax=ax_inset, color='#d3d3d3' if color_map_choice == "None (White)" else '#ff66b2', edgecolor='black', linewidth=0.8)
                ax_inset.set_xticks([]); ax_inset.set_yticks([])
                ax_inset.set_title("Gujarat State", fontsize=11, fontweight='bold', pad=4)
                for spine in ax_inset.spines.values(): spine.set_edgecolor('black')
                
            else:
                gdf.plot(ax=ax_main, color='white', edgecolor='black')
                ax_main.text(0.5, 0.5, "Select districts to render map.", ha='center', va='center', transform=ax_main.transAxes, fontsize=14, color='gray')

            ax_main.set_xticks([]); ax_main.set_yticks([]); ax_main.set_frame_on(False)
            st.pyplot(fig)
            
            buf = io.BytesIO()
            fig.savefig(buf, format="png", dpi=300)
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
        taluka_col = next((c for c in ['NAME_3', 'taluka', 'Taluka_Name', 'taluka_name', 'TALUKA', 'Sub_Distri', 'subdistrict', 'sdtname', 'tehsil_name', 'Tehsil', 'NAME_2'] if c in gdf_talukas.columns), None)
        gdf_talukas[taluka_col] = gdf_talukas[taluka_col].astype(str).str.strip()
            
        col5, col6 = st.columns([1.2, 2.8])
        
        with col5:
            st.subheader("1. Select Surveyed Regions")
            all_talukas = sorted(list(set([t for t in gdf_talukas[taluka_col].dropna().tolist() if t != "nan"])))
            selected_talukas = st.multiselect("Highlight talukas:", options=all_talukas, key="taluka_select")
            
            st.subheader("2. Map Styling")
            color_map_choice_taluka = st.selectbox("Highlight Palette", modern_palettes, key="taluka_color")
            font_size_t = st.slider("Label Font Size", 4, 40, 10, key="taluka_font")
            orientation_t = st.selectbox("Page Orientation", ["Landscape (A4)", "Portrait (A4)"], key="taluka_ori")

            st.subheader("3. Element Placement")
            col_el1_t, col_el2_t = st.columns(2)
            with col_el1_t: inset_pos_t = st.selectbox("Inset Map", ["Top Left", "Top Right", "Bottom Left", "Bottom Right"], index=0, key="taluka_inset")
            with col_el2_t: compass_pos_t = st.selectbox("Compass", ["Top Right", "Top Left", "Bottom Right", "Bottom Left"], index=0, key="taluka_compass")
            legend_pos_t = st.selectbox("Legend Position", ["None", "upper right", "upper left", "lower right", "lower left", "center left", "center right"], index=1, key="taluka_legend")
            
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
                    pt_style_t = col_pt2_t.selectbox("Shape", ["Circle", "Square", "Triangle", "Diamond", "Star"], key=f"tl_sty_{layer_id}")
                    
                    uploaded_file_t = st.file_uploader("Upload CSV", type=["csv"], key=f"tl_csv_{layer_id}")
                    if uploaded_file_t:
                        df_pts_t = process_uploaded_csv(uploaded_file_t)
                        if df_pts_t is not None:
                            taluka_survey_data.append({"df": df_pts_t, "label": pt_lbl_t, "color": pt_color_t, "style": pt_style_t})
                        else:
                            st.error("Missing Latitude/Longitude headers.")
            
            if st.button("➕ Add Survey Layer", key="add_taluka_surv"):
                st.session_state.taluka_survey_layers.append(st.session_state.next_taluka_survey)
                st.session_state.next_taluka_survey += 1
                st.rerun()

            # --- DYNAMIC IMPORTANT LOCATIONS ---
            st.markdown("---")
            st.subheader("5. Important Locations")
            st.download_button("📄 Download Sample Locations CSV", data=sample_csv_data, file_name="sample_locations.csv", mime="text/csv", key="sample_loc_t")
            show_loc_labels_t = st.checkbox("Show Location Names on Map", value=True, key="taluka_loc_showlbl")
            
            taluka_loc_data = []
            
            for layer_id in st.session_state.taluka_loc_layers:
                with st.container(border=True):
                    c1, c2 = st.columns([4, 1])
                    c1.markdown(f"**Location Layer**")
                    if c2.button("🗑️", key=f"del_tloc_{layer_id}"):
                        st.session_state.taluka_loc_layers.remove(layer_id)
                        st.rerun()
                        
                    loc_lbl_t = st.text_input("Legend Name", "Locations", key=f"tloc_lbl_{layer_id}")
                    col_loc1_t, col_loc2_t = st.columns(2)
                    loc_color_t = col_loc1_t.color_picker("Color", "#FFFF00", key=f"tloc_col_{layer_id}")
                    loc_style_t = col_loc2_t.selectbox("Shape", ["Map Pin", "Star", "Diamond", "Square", "Circle", "Triangle"], key=f"tloc_sty_{layer_id}")
                    
                    uploaded_loc_t = st.file_uploader("Upload CSV", type=["csv"], key=f"tloc_csv_{layer_id}")
                    if uploaded_loc_t:
                        df_loc_t = process_uploaded_csv(uploaded_loc_t)
                        if df_loc_t is not None:
                            taluka_loc_data.append({"df": df_loc_t, "label": loc_lbl_t, "color": loc_color_t, "style": loc_style_t})
                        else:
                            st.error("Missing Latitude/Longitude headers.")
                            
            if st.button("➕ Add Location Layer", key="add_taluka_loc"):
                st.session_state.taluka_loc_layers.append(st.session_state.next_taluka_loc)
                st.session_state.next_taluka_loc += 1
                st.rerun()

        # --- PLOTTING LOGIC TALUKA ---
        with col6:
            inset_coords_t = {"Top Left": [0.05, 0.55, 0.25, 0.25], "Top Right": [0.70, 0.55, 0.25, 0.25], "Bottom Left": [0.05, 0.05, 0.25, 0.25], "Bottom Right": [0.70, 0.05, 0.25, 0.25]}
            compass_coords_t = {"Top Right": [0.85, 0.70, 0.1, 0.1], "Top Left": [0.05, 0.70, 0.1, 0.1], "Bottom Right": [0.85, 0.05, 0.1, 0.1], "Bottom Left": [0.05, 0.05, 0.1, 0.1]}

            fig_t, ax_main_t = plt.subplots(figsize=(11.69, 8.27) if orientation_t == "Landscape (A4)" else (8.27, 11.69), dpi=300)
            plt.subplots_adjust(top=0.82, bottom=0.05, left=0.05, right=0.95)
            
            if selected_talukas:
                highlighted_talukas = gdf_talukas[gdf_talukas[taluka_col].isin(selected_talukas)]
                if color_map_choice_taluka == "None (White)":
                    highlighted_talukas.plot(ax=ax_main_t, color='white', edgecolor='black', linewidth=1.5)
                else:
                    highlighted_talukas.plot(ax=ax_main_t, column=taluka_col, cmap=color_map_choice_taluka, edgecolor='black', linewidth=1.5)
                
                minx, miny, maxx, maxy = highlighted_talukas.total_bounds
                ax_main_t.set_xlim(minx - max((maxx - minx) * 0.25, 0.05), maxx + max((maxx - minx) * 0.25, 0.05))
                ax_main_t.set_ylim(miny - max((maxy - miny) * 0.25, 0.05), maxy + max((maxy - miny) * 0.25, 0.05))
                
                import matplotlib.patheffects as pe
                for idx, row in highlighted_talukas.iterrows():
                    if row.geometry is not None and not row.geometry.is_empty:
                        centroid = row.geometry.centroid
                        ax_main_t.annotate(text=row[taluka_col], xy=(centroid.x, centroid.y), ha='center', va='center', fontsize=font_size_t, fontweight='bold', color='black', path_effects=[pe.withStroke(linewidth=3, foreground="white")])
                        
                # DYNAMIC PLOT: SURVEY POINTS
                for pt in taluka_survey_data:
                    ax_main_t.scatter(pt['df']['Longitude'].values, pt['df']['Latitude'].values, color=pt['color'], edgecolor='black', marker=marker_map[pt['style']], s=60, zorder=5, linewidth=0.8, label=pt['label'])

                # DYNAMIC PLOT: LOCATIONS
                for loc in taluka_loc_data:
                    ax_main_t.scatter(loc['df']['Longitude'].values, loc['df']['Latitude'].values, color=loc['color'], edgecolor='black', marker=marker_map[loc['style']], s=250 if loc['style'] == "Map Pin" else 150, zorder=6, linewidth=1.2, label=loc['label'])
                    if show_loc_labels_t:
                        name_col_t = next((c for c in loc['df'].columns if c.lower() in ['name', 'location', 'label', 'site']), None)
                        if name_col_t:
                            for _, r in loc['df'].iterrows():
                                ax_main_t.annotate(str(r[name_col_t]), (r['Longitude'], r['Latitude']), xytext=(0, 12), textcoords='offset points', ha='center', va='bottom', fontsize=max(font_size_t - 2, 8), fontweight='bold', path_effects=[pe.withStroke(linewidth=2.5, foreground="white")], zorder=7)
                
                # LEGEND
                if legend_pos_t != "None":
                    handles, labels = ax_main_t.get_legend_handles_labels()
                    if handles: ax_main_t.legend(handles, labels, loc=legend_pos_t, title="Legend", fontsize=10, title_fontsize=12, frameon=True, facecolor='white', framealpha=0.9, edgecolor='black', shadow=True)

                # COMPASS & INSET MAP
                ax_compass_t = fig_t.add_axes(compass_coords_t[compass_pos_t])
                ax_compass_t.set_axis_off(); ax_compass_t.set_aspect('equal')
                w = 0.15 
                polys = [[[0,0],[0,1],[w,0], 'black'], [[0,0],[0,1],[-w,0], 'white'], [[0,0],[0,-1],[w,0], 'white'], [[0,0],[0,-1],[-w,0], 'black'], [[0,0],[1,0],[0,w], 'black'], [[0,0],[1,0],[0,-w], 'white'], [[0,0],[-1,0],[0,w], 'white'], [[0,0],[-1,0],[0,-w], 'black']]
                for p in polys: ax_compass_t.add_patch(patches.Polygon(p[:3], facecolor=p[3], edgecolor='black', lw=0.5))
                ax_compass_t.text(0, 1.25, 'N', ha='center', va='center', fontweight='bold', fontsize=14, family='serif')
                for txt, pos in [('S', (0, -1.25)), ('E', (1.25, 0)), ('W', (-1.25, 0))]: ax_compass_t.text(*pos, txt, ha='center', va='center', fontsize=10, fontweight='bold', family='serif')
                ax_compass_t.set(xlim=(-1.5, 1.5), ylim=(-1.5, 1.5))

                ax_inset_t = fig_t.add_axes(inset_coords_t[inset_pos_t]) 
                if os.path.exists(state_geojson_path):
                    gpd.read_file(state_geojson_path).plot(ax=ax_inset_t, color='white', edgecolor='gray', linewidth=0.5)
                else:
                    gdf_talukas.plot(ax=ax_inset_t, color='white', edgecolor='gray', linewidth=0.1) 
                highlighted_talukas.plot(ax=ax_inset_t, color='#d3d3d3' if color_map_choice_taluka == "None (White)" else '#ff66b2', edgecolor='black', linewidth=0.8)
                ax_inset_t.set_xticks([]); ax_inset_t.set_yticks([])
                ax_inset_t.set_title("Gujarat State", fontsize=11, fontweight='bold', pad=4)
                for spine in ax_inset_t.spines.values(): spine.set_edgecolor('black')
                
            else:
                gdf_talukas.plot(ax=ax_main_t, color='white', edgecolor='black', linewidth=0.3)
                ax_main_t.text(0.5, 0.5, "Select talukas to render map.", ha='center', va='center', transform=ax_main_t.transAxes, fontsize=14, color='gray')

            ax_main_t.set_xticks([]); ax_main_t.set_yticks([]); ax_main_t.set_frame_on(False)
            st.pyplot(fig_t)
            
            buf_t = io.BytesIO()
            fig_t.savefig(buf_t, format="png", dpi=300)
            st.download_button("Download Taluka Map (PNG)", data=buf_t.getvalue(), file_name="academic_survey_taluka_map.png", mime="image/png", key="btn_taluka")
