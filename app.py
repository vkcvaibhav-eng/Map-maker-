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
    mpath.Path.MOVETO,
    mpath.Path.CURVE4,
    mpath.Path.CURVE4,
    mpath.Path.CURVE4,
    mpath.Path.CURVE4,
    mpath.Path.CURVE4,
    mpath.Path.CLOSEPOLY
]
custom_pin = mpath.Path(pin_verts, pin_codes)

# Dictionary to map user-friendly shape names to Matplotlib markers
marker_map = {
    "Map Pin": custom_pin,
    "Circle": "o",
    "Square": "s",
    "Triangle": "^",
    "Diamond": "D",
    "Star": "*"
}

# --- Load User's Custom Sample CSV ---
sample_csv_path = "1 - Copy.csv"
if os.path.exists(sample_csv_path):
    with open(sample_csv_path, "rb") as file:
        sample_csv_data = file.read()
else:
    # Fallback just in case the file gets moved
    sample_csv_data = b"Latitude,Longitude,Name\n"
    st.sidebar.warning(f"⚠️ Could not find '{sample_csv_path}'. Please make sure it is saved in the same folder as this script to allow users to download it.")

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
        highlight_type = st.selectbox(
            "Select Boundary Level", 
            ["None", "Gujarat State", "Districts", "Talukas"]
        )

        st.subheader("2. Upload Survey Data")
        st.markdown("Upload a CSV file containing `Latitude` and `Longitude` columns.")
        uploaded_file = st.file_uploader("Upload GPS CSV", type=["csv"], key="interactive_csv")
    
    with col2:
        m = folium.Map(location=[22.2587, 71.1924], zoom_start=7)

        folium.TileLayer(tiles="cartodbpositron", name="Clean Street Map").add_to(m)
        folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            attr='Esri',
            name='Satellite View',
            overlay=False
        ).add_to(m)
        folium.TileLayer(tiles="OpenStreetMap", name="Standard Street Map").add_to(m)

        file_mapping = {
            "Gujarat State": "data/gujarat_state.geojson",
            "Districts": "data/gujarat.geojson",
            "Talukas": "data/gujarat_talukas.geojson"
        }

        if highlight_type != "None":
            file_path = file_mapping[highlight_type]
            if os.path.exists(file_path):
                folium.GeoJson(
                    file_path, 
                    name=highlight_type,
                    style_function=lambda x: {'color': 'blue', 'weight': 1.5, 'fillOpacity': 0.1}
                ).add_to(m)
            else:
                st.warning(f"Boundary file not found: {file_path}. Please check your data folder.")

        if uploaded_file:
            df = pd.read_csv(uploaded_file)
            df.columns = df.columns.str.strip()
            df = df.loc[:, ~df.columns.duplicated()]
            
            if 'Latitude' in df.columns and 'Longitude' in df.columns:
                df['Latitude'] = pd.to_numeric(df['Latitude'], errors='coerce')
                df['Longitude'] = pd.to_numeric(df['Longitude'], errors='coerce')
                df = df.dropna(subset=['Latitude', 'Longitude'])
                
                with col1:
                    st.markdown("---")
                    st.subheader("3. Map Styling & Filtering")
                    categorical_columns = [col for col in df.columns if col not in ['Latitude', 'Longitude']]
                    color_options = ["None (All Red)"] + categorical_columns
                    color_col = st.selectbox("Color and filter markers by:", color_options)
                
                filtered_df = df.copy() 
                palette = ['red', 'blue', 'green', 'purple', 'orange', 'darkred', 'cadetblue', 'darkgreen', 'darkpurple', 'pink']
                color_map = {}
                
                if color_col != "None (All Red)":
                    unique_values = df[color_col].dropna().unique()
                    with col1:
                        st.markdown("**Select data to display:**")
                    selected_values = []
                    
                    for i, val in enumerate(unique_values):
                        color_map[val] = palette[i % len(palette)]
                        with col1:
                            is_checked = st.checkbox(f"Show {val} (●)", value=True, key=f"check_{val}")
                        if is_checked:
                            selected_values.append(val)
                    
                    filtered_df = df[df[color_col].isin(selected_values)]

                for _, row in filtered_df.iterrows():
                    loc_name = row.get('Location', "Unknown Location")
                    tooltip_text = f"<b>Location:</b> {loc_name}"
                    
                    if color_col != "None (All Red)" and pd.notna(row[color_col]):
                        category_val = row[color_col]
                        tooltip_text += f"<br><b>{color_col}:</b> {category_val}"
                    
                    marker_color = "red" 
                    if color_col != "None (All Red)" and pd.notna(row[color_col]):
                        marker_color = color_map.get(row[color_col], "gray")
                    
                    folium.CircleMarker(
                        location=[row['Latitude'], row['Longitude']],
                        radius=6,
                        color=marker_color,
                        fill=True,
                        fill_color=marker_color,
                        fill_opacity=0.8,
                        tooltip=tooltip_text,
                        popup=loc_name
                    ).add_to(m)
                    
                st.success(f"Displaying {len(filtered_df)} out of {len(df)} sample points.")
            else:
                st.error("⚠️ Your CSV file must contain exactly 'Latitude' and 'Longitude' as column headers.")

        folium.LayerControl(position='topright').add_to(m)
        st_folium(m, width=800, height=500)
        
        st.download_button(
            label="Download Map (HTML)",
            data=m._repr_html_(),
            file_name="interactive_survey_map.html",
            mime="text/html"
        )


# ==========================================
# TAB 2: STATIC DISTRICT MAP (A4 ACADEMIC FORMAT)
# ==========================================
with tab2:
    st.header("Static District Highlight Map")
    st.markdown("Generate a zoomed-in A4 map focusing on **District** boundaries.")
    
    district_geojson_path = "data/gujarat.geojson"
    
    if not os.path.exists(district_geojson_path):
        st.error(f"Cannot find {district_geojson_path}. Please ensure your GeoJSON is in the data folder.")
    else:
        gdf = gpd.read_file(district_geojson_path)
        
        district_col = None
        for col in ['dtname', 'NAME_2', 'district', 'Dist_Name', 'district_name', 'REGNAME']:
            if col in gdf.columns:
                district_col = col
                break
                
        if not district_col:
            st.error(f"Could not automatically detect the district name column in your GeoJSON.")
        else:
            gdf[district_col] = gdf[district_col].astype(str).str.strip()
            
            col3, col4 = st.columns([1, 3])
            
            with col3:
                st.subheader("1. Select Surveyed Regions")
                all_districts = sorted(list(set([d for d in gdf[district_col].dropna().tolist() if d != "nan"])))
                
                ideal_defaults = ["ahmedabad", "anand", "vadodara", "kheda", "panchmahal", "panch mahal", "dahod", "mahisagar", "chhotaudepur", "botad"]
                safe_defaults = [d for d in all_districts if str(d).lower().strip() in ideal_defaults]
                
                selected_districts = st.multiselect("Select districts to highlight:", options=all_districts, default=safe_defaults, key="dist_select")
                
                st.subheader("2. Map Styling")
                modern_palettes = ["None (White)", "Set2", "Dark2", "Paired", "tab10", "Greens", "Blues", "YlGnBu", "OrRd", "viridis", "cividis", "plasma", "Pastel1", "Set3", "Accent"]
                color_map_choice = st.selectbox("Highlight Palette", modern_palettes, key="dist_color")
                
                col_s1, col_s2 = st.columns(2)
                with col_s1:
                    font_size_d = st.slider("Label Font Size", 4, 40, 12, key="dist_font")
                with col_s2:
                    orientation_d = st.selectbox("Page Orientation", ["Landscape (A4)", "Portrait (A4)"], key="dist_ori")

                st.subheader("3. Element Placement")
                col_el1, col_el2 = st.columns(2)
                with col_el1:
                    inset_pos = st.selectbox("Inset Map", ["Top Left", "Top Right", "Bottom Left", "Bottom Right"], index=0, key="dist_inset")
                with col_el2:
                    compass_pos = st.selectbox("Compass", ["Top Right", "Top Left", "Bottom Right", "Bottom Left"], index=0, key="dist_compass")
                legend_pos_d = st.selectbox("Legend Position", ["None", "upper right", "upper left", "lower right", "lower left", "center left", "center right"], index=1, key="dist_legend")
                
                # --- SURVEY POINTS LAYER 1 ---
                st.subheader("4. Survey Points (Layer 1)")
                df_points_d1 = None
                
                col_pt1_d1, col_pt2_d1, col_pt3_d1 = st.columns(3)
                with col_pt1_d1:
                    pt_lbl_d1 = st.text_input("Legend Name", "Survey 1", key="dl1_lbl")
                with col_pt2_d1:
                    point_color_d1 = st.color_picker("Color", "#FF0000", key="dist_pt_color1")
                with col_pt3_d1:
                    point_style_d1 = st.selectbox("Shape", ["Circle", "Square", "Triangle", "Diamond", "Star"], key="dist_pt_style1")
                
                uploaded_file_d1 = st.file_uploader("Upload Layer 1 CSV", type=["csv"], key="dist_csv1")
                if uploaded_file_d1:
                    df_d1 = pd.read_csv(uploaded_file_d1)
                    df_d1.columns = df_d1.columns.str.strip()
                    df_d1 = df_d1.loc[:, ~df_d1.columns.duplicated()]
                    if 'Latitude' in df_d1.columns and 'Longitude' in df_d1.columns:
                        df_d1['Latitude'] = pd.to_numeric(df_d1['Latitude'], errors='coerce')
                        df_d1['Longitude'] = pd.to_numeric(df_d1['Longitude'], errors='coerce')
                        df_points_d1 = df_d1.dropna(subset=['Latitude', 'Longitude'])
                    else:
                        st.error("⚠️ Layer 1 CSV is missing 'Latitude' and 'Longitude' headers.")

                # --- SURVEY POINTS LAYER 2 ---
                st.subheader("4.1 Survey Points (Layer 2)")
                df_points_d2 = None
                
                col_pt1_d2, col_pt2_d2, col_pt3_d2 = st.columns(3)
                with col_pt1_d2:
                    pt_lbl_d2 = st.text_input("Legend Name", "Survey 2", key="dl2_lbl")
                with col_pt2_d2:
                    point_color_d2 = st.color_picker("Color", "#0000FF", key="dist_pt_color2")
                with col_pt3_d2:
                    point_style_d2 = st.selectbox("Shape", ["Square", "Circle", "Triangle", "Diamond", "Star"], key="dist_pt_style2")
                
                uploaded_file_d2 = st.file_uploader("Upload Layer 2 CSV", type=["csv"], key="dist_csv2")
                if uploaded_file_d2:
                    df_d2 = pd.read_csv(uploaded_file_d2)
                    df_d2.columns = df_d2.columns.str.strip()
                    df_d2 = df_d2.loc[:, ~df_d2.columns.duplicated()]
                    if 'Latitude' in df_d2.columns and 'Longitude' in df_d2.columns:
                        df_d2['Latitude'] = pd.to_numeric(df_d2['Latitude'], errors='coerce')
                        df_d2['Longitude'] = pd.to_numeric(df_d2['Longitude'], errors='coerce')
                        df_points_d2 = df_d2.dropna(subset=['Latitude', 'Longitude'])
                    else:
                        st.error("⚠️ Layer 2 CSV is missing 'Latitude' and 'Longitude' headers.")

                # --- IMPORTANT LOCATIONS ---
                st.subheader("5. Overlay Important Locations")
                st.markdown("*(e.g. Universities, Research Stations, Sugar Factories)*")
                
                st.download_button(
                    label="📄 Download Sample Locations CSV",
                    data=sample_csv_data,
                    file_name="1 - Copy.csv",
                    mime="text/csv",
                    key="sample_csv_dist"
                )
                
                df_loc_points_d = None
                
                col_loc1_d, col_loc2_d, col_loc3_d = st.columns(3)
                with col_loc1_d:
                    loc_lbl_d = st.text_input("Legend Name", "Locations", key="dloc_lbl")
                with col_loc2_d:
                    loc_color_d = st.color_picker("Color", "#FFFF00", key="dist_loc_color")
                with col_loc3_d:
                    loc_style_d = st.selectbox("Shape", ["Map Pin", "Star", "Diamond", "Square", "Circle", "Triangle"], key="dist_loc_style")
                
                show_loc_labels_d = st.checkbox("Show Location Names on Map", value=True, key="dist_loc_lbl")
                uploaded_loc_d = st.file_uploader("Upload Locations CSV", type=["csv"], key="dist_loc_csv")
                
                if uploaded_loc_d:
                    df_loc_d = pd.read_csv(uploaded_loc_d)
                    df_loc_d.columns = df_loc_d.columns.str.strip()
                    df_loc_d.loc[:, ~df_loc_d.columns.duplicated()]
                    
                    if 'Latitude' not in df_loc_d.columns or 'Longitude' not in df_loc_d.columns:
                        st.error("⚠️ Your CSV is missing 'Latitude' and 'Longitude' headers.")
                    else:
                        df_loc_d['Latitude'] = pd.to_numeric(df_loc_d['Latitude'], errors='coerce')
                        df_loc_d['Longitude'] = pd.to_numeric(df_loc_d['Longitude'], errors='coerce')
                        df_loc_points_d = df_loc_d.dropna(subset=['Latitude', 'Longitude'])

            with col4:
                inset_coords = {"Top Left": [0.05, 0.55, 0.25, 0.25], "Top Right": [0.70, 0.55, 0.25, 0.25], "Bottom Left": [0.05, 0.05, 0.25, 0.25], "Bottom Right": [0.70, 0.05, 0.25, 0.25]}
                compass_coords = {"Top Right": [0.85, 0.70, 0.1, 0.1], "Top Left": [0.05, 0.70, 0.1, 0.1], "Bottom Right": [0.85, 0.05, 0.1, 0.1], "Bottom Left": [0.05, 0.05, 0.1, 0.1]}

                if orientation_d == "Landscape (A4)":
                    fig, ax_main = plt.subplots(figsize=(11.69, 8.27), dpi=300)
                else:
                    fig, ax_main = plt.subplots(figsize=(8.27, 11.69), dpi=300)
                    
                plt.subplots_adjust(top=0.82, bottom=0.05, left=0.05, right=0.95)
                
                if selected_districts:
                    highlighted_gdf = gdf[gdf[district_col].isin(selected_districts)]
                    
                    if color_map_choice == "None (White)":
                        highlighted_gdf.plot(ax=ax_main, color='white', edgecolor='black', linewidth=1.5)
                    else:
                        highlighted_gdf.plot(ax=ax_main, column=district_col, cmap=color_map_choice, edgecolor='black', linewidth=1.5, legend=False)
                    
                    minx, miny, maxx, maxy = highlighted_gdf.total_bounds
                    margin_x = max((maxx - minx) * 0.25, 0.05)
                    margin_y = max((maxy - miny) * 0.25, 0.05)
                    ax_main.set_xlim(minx - margin_x, maxx + margin_x)
                    ax_main.set_ylim(miny - margin_y, maxy + margin_y)
                    
                    import matplotlib.patheffects as pe
                    for idx, row in highlighted_gdf.iterrows():
                        centroid = row.geometry.centroid
                        ax_main.annotate(
                            text=row[district_col], xy=(centroid.x, centroid.y),
                            horizontalalignment='center', verticalalignment='center',
                            fontsize=font_size_d, fontweight='bold', color='black',
                            path_effects=[pe.withStroke(linewidth=3, foreground="white")] 
                        )
                        
                    # PLOT GPS POINTS LAYER 1
                    if df_points_d1 is not None:
                        ax_main.scatter(df_points_d1['Longitude'].values, df_points_d1['Latitude'].values, 
                                        color=point_color_d1, edgecolor='black', marker=marker_map[point_style_d1],
                                        s=60, zorder=5, linewidth=0.8, label=pt_lbl_d1)

                    # PLOT GPS POINTS LAYER 2
                    if df_points_d2 is not None:
                        ax_main.scatter(df_points_d2['Longitude'].values, df_points_d2['Latitude'].values, 
                                        color=point_color_d2, edgecolor='black', marker=marker_map[point_style_d2],
                                        s=60, zorder=5, linewidth=0.8, label=pt_lbl_d2)
                    
                    # PLOT IMPORTANT LOCATIONS 
                    if df_loc_points_d is not None:
                        ax_main.scatter(df_loc_points_d['Longitude'].values, df_loc_points_d['Latitude'].values, 
                                        color=loc_color_d, edgecolor='black', marker=marker_map[loc_style_d],
                                        s=250 if loc_style_d == "Map Pin" else 150, zorder=6, linewidth=1.2, label=loc_lbl_d)
                        
                        # Annotate Location Names
                        if show_loc_labels_d:
                            name_col_d = next((col for col in df_loc_points_d.columns if col.lower() in ['name', 'location', 'label', 'site']), None)
                            if name_col_d:
                                for _, row in df_loc_points_d.iterrows():
                                    ax_main.annotate(
                                        str(row[name_col_d]),
                                        (row['Longitude'], row['Latitude']),
                                        xytext=(0, 12), textcoords='offset points',
                                        ha='center', va='bottom', fontsize=max(font_size_d - 2, 8), fontweight='bold', color='black',
                                        path_effects=[pe.withStroke(linewidth=2.5, foreground="white")],
                                        zorder=7
                                    )
                            else:
                                st.warning("⚠️ Could not find a 'Name', 'Location', or 'Label' column to print names on the map.")

                    # ADD LEGEND
                    if legend_pos_d != "None":
                        handles, labels = ax_main.get_legend_handles_labels()
                        if handles:
                            ax_main.legend(handles, labels, loc=legend_pos_d, title="Legend", 
                                           fontsize=10, title_fontsize=12, frameon=True, 
                                           facecolor='white', framealpha=0.9, edgecolor='black', shadow=True)
                                
                    ax_compass = fig.add_axes(compass_coords[compass_pos])
                    ax_compass.set_axis_off()
                    ax_compass.set_aspect('equal')
                    w = 0.15 
                    ax_compass.add_patch(patches.Polygon([[0, 0], [0, 1], [w, 0]], facecolor='black', edgecolor='black', lw=0.5))
                    ax_compass.add_patch(patches.Polygon([[0, 0], [0, 1], [-w, 0]], facecolor='white', edgecolor='black', lw=0.5))
                    ax_compass.add_patch(patches.Polygon([[0, 0], [0, -1], [w, 0]], facecolor='white', edgecolor='black', lw=0.5))
                    ax_compass.add_patch(patches.Polygon([[0, 0], [0, -1], [-w, 0]], facecolor='black', edgecolor='black', lw=0.5))
                    ax_compass.add_patch(patches.Polygon([[0, 0], [1, 0], [0, w]], facecolor='black', edgecolor='black', lw=0.5))
                    ax_compass.add_patch(patches.Polygon([[0, 0], [1, 0], [0, -w]], facecolor='white', edgecolor='black', lw=0.5))
                    ax_compass.add_patch(patches.Polygon([[0, 0], [-1, 0], [0, w]], facecolor='white', edgecolor='black', lw=0.5))
                    ax_compass.add_patch(patches.Polygon([[0, 0], [-1, 0], [0, -w]], facecolor='black', edgecolor='black', lw=0.5))
                    font_props = {'family': 'serif', 'fontweight': 'bold', 'fontsize': 14}
                    ax_compass.text(0, 1.25, 'N', ha='center', va='center', **font_props)
                    ax_compass.text(0, -1.25, 'S', ha='center', va='center', fontsize=10, fontweight='bold', family='serif')
                    ax_compass.text(1.25, 0, 'E', ha='center', va='center', fontsize=10, fontweight='bold', family='serif')
                    ax_compass.text(-1.25, 0, 'W', ha='center', va='center', fontsize=10, fontweight='bold', family='serif')
                    ax_compass.set_xlim(-1.5, 1.5)
                    ax_compass.set_ylim(-1.5, 1.5)

                    ax_inset = fig.add_axes(inset_coords[inset_pos]) 
                    gdf.plot(ax=ax_inset, color='white', edgecolor='gray', linewidth=0.5)
                    if color_map_choice == "None (White)":
                        highlighted_gdf.plot(ax=ax_inset, color='#d3d3d3', edgecolor='black', linewidth=0.8)
                    else:
                        highlighted_gdf.plot(ax=ax_inset, color='#ff66b2', edgecolor='black', linewidth=0.8)
                    ax_inset.set_xticks([])
                    ax_inset.set_yticks([])
                    ax_inset.set_title("Gujarat State", fontsize=11, fontweight='bold', pad=4)
                    for spine in ax_inset.spines.values():
                        spine.set_edgecolor('black')
                        spine.set_linewidth(1)
                    
                else:
                    gdf.plot(ax=ax_main, color='white', edgecolor='black')
                    ax_main.text(0.5, 0.5, "Select districts to render map.", horizontalalignment='center', verticalalignment='center', transform=ax_main.transAxes, fontsize=14, color='gray')

                ax_main.set_xticks([])
                ax_main.set_yticks([])
                ax_main.set_frame_on(False)
                st.pyplot(fig)
                
                buf = io.BytesIO()
                fig.savefig(buf, format="png", dpi=300)
                buf.seek(0)
                st.download_button("Download District Map (PNG)", data=buf, file_name="academic_survey_district_map.png", mime="image/png", key="btn_dist")


# ==========================================
# TAB 3: STATIC TALUKA MAP (A4 ACADEMIC FORMAT)
# ==========================================
with tab3:
    st.header("Static Taluka Highlight Map")
    st.markdown("Generate a zoomed-in A4 map focusing on **Taluka (Sub-district)** boundaries.")
    
    taluka_geojson_path = "data/gujarat_talukas.geojson"
    state_geojson_path = "data/gujarat_state.geojson"
    
    if not os.path.exists(taluka_geojson_path):
        st.error(f"Cannot find {taluka_geojson_path}. Please ensure your GeoJSON is in the data folder.")
    else:
        gdf_talukas = gpd.read_file(taluka_geojson_path)
        
        taluka_col = None
        possible_t_cols = ['NAME_3', 'taluka', 'Taluka_Name', 'taluka_name', 'TALUKA', 'Sub_Distri', 'subdistrict', 'Taluka', 'subdistrict_name', 'sdtname', 'tehsil_name', 'Tehsil', 'tehsil', 'sdt_name', 'NAME_2']
        
        for col in possible_t_cols:
            if col in gdf_talukas.columns:
                taluka_col = col
                break
                
        if not taluka_col:
            st.error(f"Could not automatically detect the taluka name column in your GeoJSON.")
        else:
            gdf_talukas[taluka_col] = gdf_talukas[taluka_col].astype(str).str.strip()
            
            col5, col6 = st.columns([1, 3])
            
            with col5:
                st.subheader("1. Select Surveyed Regions")
                all_talukas = sorted(list(set([t for t in gdf_talukas[taluka_col].dropna().tolist() if t != "nan"])))
                selected_talukas = st.multiselect("Select talukas to highlight:", options=all_talukas, key="taluka_select")
                
                st.subheader("2. Map Styling")
                modern_palettes = ["None (White)", "Set2", "Dark2", "Paired", "tab10", "Greens", "Blues", "YlGnBu", "OrRd", "viridis", "cividis", "plasma", "Pastel1", "Set3", "Accent"]
                color_map_choice_taluka = st.selectbox("Highlight Palette", modern_palettes, key="taluka_color")
                
                col_t1, col_t2 = st.columns(2)
                with col_t1:
                    font_size_t = st.slider("Label Font Size", 4, 40, 10, key="taluka_font")
                with col_t2:
                    orientation_t = st.selectbox("Page Orientation", ["Landscape (A4)", "Portrait (A4)"], key="taluka_ori")

                st.subheader("3. Element Placement")
                col_el1_t, col_el2_t = st.columns(2)
                with col_el1_t:
                    inset_pos_t = st.selectbox("Inset Map", ["Top Left", "Top Right", "Bottom Left", "Bottom Right"], index=0, key="taluka_inset")
                with col_el2_t:
                    compass_pos_t = st.selectbox("Compass", ["Top Right", "Top Left", "Bottom Right", "Bottom Left"], index=0, key="taluka_compass")
                legend_pos_t = st.selectbox("Legend Position", ["None", "upper right", "upper left", "lower right", "lower left", "center left", "center right"], index=1, key="taluka_legend")
                
                # --- SURVEY POINTS LAYER 1 ---
                st.subheader("4. Survey Points (Layer 1)")
                df_points_t1 = None
                
                col_pt1_t1, col_pt2_t1, col_pt3_t1 = st.columns(3)
                with col_pt1_t1:
                    pt_lbl_t1 = st.text_input("Legend Name", "Survey 1", key="tl1_lbl")
                with col_pt2_t1:
                    point_color_t1 = st.color_picker("Color", "#FF0000", key="taluka_pt_color1")
                with col_pt3_t1:
                    point_style_t1 = st.selectbox("Shape", ["Circle", "Square", "Triangle", "Diamond", "Star"], key="taluka_pt_style1")
                
                uploaded_file_t1 = st.file_uploader("Upload Layer 1 CSV", type=["csv"], key="taluka_csv1")
                if uploaded_file_t1:
                    df_t1 = pd.read_csv(uploaded_file_t1)
                    df_t1.columns = df_t1.columns.str.strip()
                    df_t1 = df_t1.loc[:, ~df_t1.columns.duplicated()]
                    if 'Latitude' in df_t1.columns and 'Longitude' in df_t1.columns:
                        df_t1['Latitude'] = pd.to_numeric(df_t1['Latitude'], errors='coerce')
                        df_t1['Longitude'] = pd.to_numeric(df_t1['Longitude'], errors='coerce')
                        df_points_t1 = df_t1.dropna(subset=['Latitude', 'Longitude'])
                    else:
                        st.error("⚠️ Layer 1 CSV is missing 'Latitude' and 'Longitude' headers.")

                # --- SURVEY POINTS LAYER 2 ---
                st.subheader("4.1 Survey Points (Layer 2)")
                df_points_t2 = None
                
                col_pt1_t2, col_pt2_t2, col_pt3_t2 = st.columns(3)
                with col_pt1_t2:
                    pt_lbl_t2 = st.text_input("Legend Name", "Survey 2", key="tl2_lbl")
                with col_pt2_t2:
                    point_color_t2 = st.color_picker("Color", "#0000FF", key="taluka_pt_color2")
                with col_pt3_t2:
                    point_style_t2 = st.selectbox("Shape", ["Square", "Circle", "Triangle", "Diamond", "Star"], key="taluka_pt_style2")
                
                uploaded_file_t2 = st.file_uploader("Upload Layer 2 CSV", type=["csv"], key="taluka_csv2")
                if uploaded_file_t2:
                    df_t2 = pd.read_csv(uploaded_file_t2)
                    df_t2.columns = df_t2.columns.str.strip()
                    df_t2 = df_t2.loc[:, ~df_t2.columns.duplicated()]
                    if 'Latitude' in df_t2.columns and 'Longitude' in df_t2.columns:
                        df_t2['Latitude'] = pd.to_numeric(df_t2['Latitude'], errors='coerce')
                        df_t2['Longitude'] = pd.to_numeric(df_t2['Longitude'], errors='coerce')
                        df_points_t2 = df_t2.dropna(subset=['Latitude', 'Longitude'])
                    else:
                        st.error("⚠️ Layer 2 CSV is missing 'Latitude' and 'Longitude' headers.")

                # --- IMPORTANT LOCATIONS ---
                st.subheader("5. Overlay Important Locations")
                st.markdown("*(e.g. Universities, Research Stations, Sugar Factories)*")
                
                st.download_button(
                    label="📄 Download Sample Locations CSV",
                    data=sample_csv_data,
                    file_name="1 - Copy.csv",
                    mime="text/csv",
                    key="sample_csv_taluka"
                )
                
                df_loc_points_t = None
                
                col_loc1_t, col_loc2_t, col_loc3_t = st.columns(3)
                with col_loc1_t:
                    loc_lbl_t = st.text_input("Legend Name", "Locations", key="tloc_lbl")
                with col_loc2_t:
                    loc_color_t = st.color_picker("Color", "#FFFF00", key="taluka_loc_color")
                with col_loc3_t:
                    loc_style_t = st.selectbox("Shape", ["Map Pin", "Star", "Diamond", "Square", "Circle", "Triangle"], key="taluka_loc_style")
                
                show_loc_labels_t = st.checkbox("Show Location Names on Map", value=True, key="taluka_loc_lbl")
                uploaded_loc_t = st.file_uploader("Upload Locations CSV", type=["csv"], key="taluka_loc_csv")
                
                if uploaded_loc_t:
                    df_loc_t = pd.read_csv(uploaded_loc_t)
                    df_loc_t.columns = df_loc_t.columns.str.strip()
                    df_loc_t.loc[:, ~df_loc_t.columns.duplicated()]
                    
                    if 'Latitude' not in df_loc_t.columns or 'Longitude' not in df_loc_t.columns:
                        st.error("⚠️ Your CSV is missing 'Latitude' and 'Longitude' headers.")
                    else:
                        df_loc_t['Latitude'] = pd.to_numeric(df_loc_t['Latitude'], errors='coerce')
                        df_loc_t['Longitude'] = pd.to_numeric(df_loc_t['Longitude'], errors='coerce')
                        df_loc_points_t = df_loc_t.dropna(subset=['Latitude', 'Longitude'])

            with col6:
                inset_coords_t = {"Top Left": [0.05, 0.55, 0.25, 0.25], "Top Right": [0.70, 0.55, 0.25, 0.25], "Bottom Left": [0.05, 0.05, 0.25, 0.25], "Bottom Right": [0.70, 0.05, 0.25, 0.25]}
                compass_coords_t = {"Top Right": [0.85, 0.70, 0.1, 0.1], "Top Left": [0.05, 0.70, 0.1, 0.1], "Bottom Right": [0.85, 0.05, 0.1, 0.1], "Bottom Left": [0.05, 0.05, 0.1, 0.1]}

                if orientation_t == "Landscape (A4)":
                    fig_t, ax_main_t = plt.subplots(figsize=(11.69, 8.27), dpi=300)
                else:
                    fig_t, ax_main_t = plt.subplots(figsize=(8.27, 11.69), dpi=300)
                    
                plt.subplots_adjust(top=0.82, bottom=0.05, left=0.05, right=0.95)
                
                if selected_talukas:
                    highlighted_talukas = gdf_talukas[gdf_talukas[taluka_col].isin(selected_talukas)]
                    
                    if color_map_choice_taluka == "None (White)":
                        highlighted_talukas.plot(ax=ax_main_t, color='white', edgecolor='black', linewidth=1.5)
                    else:
                        highlighted_talukas.plot(ax=ax_main_t, column=taluka_col, cmap=color_map_choice_taluka, edgecolor='black', linewidth=1.5, legend=False)
                    
                    minx, miny, maxx, maxy = highlighted_talukas.total_bounds
                    margin_x = max((maxx - minx) * 0.25, 0.05)
                    margin_y = max((maxy - miny) * 0.25, 0.05)
                    ax_main_t.set_xlim(minx - margin_x, maxx + margin_x)
                    ax_main_t.set_ylim(miny - margin_y, maxy + margin_y)
                    
                    import matplotlib.patheffects as pe
                    for idx, row in highlighted_talukas.iterrows():
                        if row.geometry is not None and not row.geometry.is_empty:
                            centroid = row.geometry.centroid
                            ax_main_t.annotate(
                                text=row[taluka_col], xy=(centroid.x, centroid.y),
                                horizontalalignment='center', verticalalignment='center',
                                fontsize=font_size_t, fontweight='bold', color='black',
                                path_effects=[pe.withStroke(linewidth=3, foreground="white")] 
                            )
                            
                    # PLOT GPS POINTS LAYER 1
                    if df_points_t1 is not None:
                        ax_main_t.scatter(df_points_t1['Longitude'].values, df_points_t1['Latitude'].values, 
                                        color=point_color_t1, edgecolor='black', marker=marker_map[point_style_t1],
                                        s=60, zorder=5, linewidth=0.8, label=pt_lbl_t1)
                                        
                    # PLOT GPS POINTS LAYER 2
                    if df_points_t2 is not None:
                        ax_main_t.scatter(df_points_t2['Longitude'].values, df_points_t2['Latitude'].values, 
                                        color=point_color_t2, edgecolor='black', marker=marker_map[point_style_t2],
                                        s=60, zorder=5, linewidth=0.8, label=pt_lbl_t2)

                    # PLOT IMPORTANT LOCATIONS
                    if df_loc_points_t is not None:
                        ax_main_t.scatter(df_loc_points_t['Longitude'].values, df_loc_points_t['Latitude'].values, 
                                        color=loc_color_t, edgecolor='black', marker=marker_map[loc_style_t],
                                        s=250 if loc_style_t == "Map Pin" else 150, zorder=6, linewidth=1.2, label=loc_lbl_t)
                        
                        # Annotate Location Names
                        if show_loc_labels_t:
                            name_col_t = next((col for col in df_loc_points_t.columns if col.lower() in ['name', 'location', 'label', 'site']), None)
                            if name_col_t:
                                for _, row in df_loc_points_t.iterrows():
                                    ax_main_t.annotate(
                                        str(row[name_col_t]),
                                        (row['Longitude'], row['Latitude']),
                                        xytext=(0, 12), textcoords='offset points',
                                        ha='center', va='bottom', fontsize=max(font_size_t - 2, 8), fontweight='bold', color='black',
                                        path_effects=[pe.withStroke(linewidth=2.5, foreground="white")],
                                        zorder=7
                                    )
                            else:
                                st.warning("⚠️ Could not find a 'Name', 'Location', or 'Label' column to print names on the map.")
                    
                    # ADD LEGEND
                    if legend_pos_t != "None":
                        handles, labels = ax_main_t.get_legend_handles_labels()
                        if handles:
                            ax_main_t.legend(handles, labels, loc=legend_pos_t, title="Legend", 
                                             fontsize=10, title_fontsize=12, frameon=True, 
                                             facecolor='white', framealpha=0.9, edgecolor='black', shadow=True)

                    ax_compass_t = fig_t.add_axes(compass_coords_t[compass_pos_t])
                    ax_compass_t.set_axis_off()
                    ax_compass_t.set_aspect('equal')
                    w = 0.15 
                    ax_compass_t.add_patch(patches.Polygon([[0, 0], [0, 1], [w, 0]], facecolor='black', edgecolor='black', lw=0.5))
                    ax_compass_t.add_patch(patches.Polygon([[0, 0], [0, 1], [-w, 0]], facecolor='white', edgecolor='black', lw=0.5))
                    ax_compass_t.add_patch(patches.Polygon([[0, 0], [0, -1], [w, 0]], facecolor='white', edgecolor='black', lw=0.5))
                    ax_compass_t.add_patch(patches.Polygon([[0, 0], [0, -1], [-w, 0]], facecolor='black', edgecolor='black', lw=0.5))
                    ax_compass_t.add_patch(patches.Polygon([[0, 0], [1, 0], [0, w]], facecolor='black', edgecolor='black', lw=0.5))
                    ax_compass_t.add_patch(patches.Polygon([[0, 0], [1, 0], [0, -w]], facecolor='white', edgecolor='black', lw=0.5))
                    ax_compass_t.add_patch(patches.Polygon([[0, 0], [-1, 0], [0, w]], facecolor='white', edgecolor='black', lw=0.5))
                    ax_compass_t.add_patch(patches.Polygon([[0, 0], [-1, 0], [0, -w]], facecolor='black', edgecolor='black', lw=0.5))
                    font_props = {'family': 'serif', 'fontweight': 'bold', 'fontsize': 14}
                    ax_compass_t.text(0, 1.25, 'N', ha='center', va='center', **font_props)
                    ax_compass_t.text(0, -1.25, 'S', ha='center', va='center', fontsize=10, fontweight='bold', family='serif')
                    ax_compass_t.text(1.25, 0, 'E', ha='center', va='center', fontsize=10, fontweight='bold', family='serif')
                    ax_compass_t.text(-1.25, 0, 'W', ha='center', va='center', fontsize=10, fontweight='bold', family='serif')
                    ax_compass_t.set_xlim(-1.5, 1.5)
                    ax_compass_t.set_ylim(-1.5, 1.5)

                    ax_inset_t = fig_t.add_axes(inset_coords_t[inset_pos_t]) 
                    if os.path.exists(state_geojson_path):
                        gdf_state = gpd.read_file(state_geojson_path)
                        gdf_state.plot(ax=ax_inset_t, color='white', edgecolor='gray', linewidth=0.5)
                    else:
                        gdf_talukas.plot(ax=ax_inset_t, color='white', edgecolor='gray', linewidth=0.1) 

                    if color_map_choice_taluka == "None (White)":
                        highlighted_talukas.plot(ax=ax_inset_t, color='#d3d3d3', edgecolor='black', linewidth=0.8)
                    else:
                        highlighted_talukas.plot(ax=ax_inset_t, color='#ff66b2', edgecolor='black', linewidth=0.8)
                        
                    ax_inset_t.set_xticks([])
                    ax_inset_t.set_yticks([])
                    ax_inset_t.set_title("Gujarat State", fontsize=11, fontweight='bold', pad=4)
                    for spine in ax_inset_t.spines.values():
                        spine.set_edgecolor('black')
                        spine.set_linewidth(1)
                    
                else:
                    gdf_talukas.plot(ax=ax_main_t, color='white', edgecolor='black', linewidth=0.3)
                    ax_main_t.text(0.5, 0.5, "Select talukas to render map.", horizontalalignment='center', verticalalignment='center', transform=ax_main_t.transAxes, fontsize=14, color='gray')

                ax_main_t.set_xticks([])
                ax_main_t.set_yticks([])
                ax_main_t.set_frame_on(False)
                st.pyplot(fig_t)
                
                buf_t = io.BytesIO()
                fig_t.savefig(buf_t, format="png", dpi=300)
                buf_t.seek(0)
                st.download_button("Download Taluka Map (PNG)", data=buf_t, file_name="academic_survey_taluka_map.png", mime="image/png", key="btn_taluka")
