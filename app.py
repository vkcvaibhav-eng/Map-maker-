import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import io
import os

# --- Page Configuration ---
st.set_page_config(page_title="Ph.D. Survey Map Generator", layout="wide")

st.title("Gujarat Survey Map Generator")
st.markdown("Generate professional, publication-ready maps for your Ph.D. thesis.")

# --- Setup Tabs ---
tab1, tab2 = st.tabs(["Interactive GPS Map", "Static Thesis Region Map"])

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
            
            if 'Latitude' in df.columns and 'Longitude' in df.columns:
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
                st.error("Your CSV file must contain exactly 'Latitude' and 'Longitude' as column headers.")

        folium.LayerControl(position='topright').add_to(m)
        st_folium(m, width=800, height=500)
        
        st.download_button(
            label="Download Map (HTML)",
            data=m._repr_html_(),
            file_name="interactive_survey_map.html",
            mime="text/html"
        )


# ==========================================
# TAB 2: STATIC THESIS REGION MAP (A4 ACADEMIC FORMAT)
# ==========================================
with tab2:
    st.header("Static Region Highlight Map (Academic Standard)")
    st.markdown("Generate a zoomed-in A4 landscape map with an adjustable compass rose and inset.")
    
    district_geojson_path = "data/gujarat.geojson"
    taluka_geojson_path = "data/gujarat_talukas.geojson"
    
    if not os.path.exists(district_geojson_path):
        st.error(f"Cannot find {district_geojson_path}. Please ensure your GeoJSON is in the data folder.")
    else:
        gdf = gpd.read_file(district_geojson_path)
        
        # Try to load talukas if they exist
        gdf_talukas = None
        if os.path.exists(taluka_geojson_path):
            gdf_talukas = gpd.read_file(taluka_geojson_path)
        
        district_col = None
        for col in ['dtname', 'NAME_2', 'district', 'Dist_Name', 'district_name', 'REGNAME']:
            if col in gdf.columns:
                district_col = col
                break
                
        if not district_col:
            st.error(f"Could not automatically detect the district name column in your GeoJSON. Available columns: {list(gdf.columns)}")
        else:
            col3, col4 = st.columns([1, 3])
            
            with col3:
                st.subheader("1. Select Surveyed Regions")
                all_districts = sorted(gdf[district_col].dropna().unique().tolist())
                
                ideal_defaults = ["ahmedabad", "anand", "vadodara", "kheda", "panchmahal", "panch mahal", "dahod", "mahisagar", "chhotaudepur", "botad"]
                safe_defaults = [d for d in all_districts if str(d).lower().strip() in ideal_defaults]
                
                selected_districts = st.multiselect(
                    "Select districts to highlight:",
                    options=all_districts,
                    default=safe_defaults 
                )
                
                st.subheader("2. Map Styling")
                modern_palettes = [
                    "None (White)", 
                    "Set2", "Dark2", "Paired", "tab10",
                    "Greens", "Blues", "YlGnBu", "OrRd",
                    "viridis", "cividis", "plasma",
                    "Pastel1", "Set3", "Accent"
                ]
                color_map_choice = st.selectbox("Highlight Palette", modern_palettes)
                
                # New Taluka Toggle
                show_talukas = False
                if gdf_talukas is not None:
                    show_talukas = st.checkbox("Overlay Taluka (Sub-district) Boundaries")
                    st.caption("*Tip: Use this only when zoomed into 1-3 districts to avoid visual clutter.*")

                st.subheader("3. Element Placement")
                st.markdown("Adjust these to prevent the inset or compass from overlapping your selected districts.")
                inset_pos = st.selectbox("Inset Map Position", ["Top Left", "Top Right", "Bottom Left", "Bottom Right"], index=0)
                compass_pos = st.selectbox("Compass Position", ["Top Right", "Top Left", "Bottom Right", "Bottom Left"], index=0)
                
            with col4:
                inset_coords = {
                    "Top Left": [0.05, 0.55, 0.25, 0.25],
                    "Top Right": [0.70, 0.55, 0.25, 0.25],
                    "Bottom Left": [0.05, 0.05, 0.25, 0.25],
                    "Bottom Right": [0.70, 0.05, 0.25, 0.25]
                }
                
                compass_coords = {
                    "Top Right": [0.85, 0.70, 0.1, 0.1],
                    "Top Left": [0.05, 0.70, 0.1, 0.1],
                    "Bottom Right": [0.85, 0.05, 0.1, 0.1],
                    "Bottom Left": [0.05, 0.05, 0.1, 0.1]
                }

                fig, ax_main = plt.subplots(figsize=(11.69, 8.27), dpi=300)
                
                # FORCE THESIS BINDING MARGIN
                plt.subplots_adjust(top=0.82, bottom=0.05, left=0.05, right=0.95)
                
                if selected_districts:
                    # 1. MAIN MAP: Plot ONLY the selected districts
                    highlighted_gdf = gdf[gdf[district_col].isin(selected_districts)]
                    
                    if color_map_choice == "None (White)":
                        highlighted_gdf.plot(ax=ax_main, color='white', edgecolor='black', linewidth=1.5)
                    else:
                        highlighted_gdf.plot(
                            ax=ax_main, 
                            column=district_col, 
                            cmap=color_map_choice, 
                            edgecolor='black', 
                            linewidth=1.5, # Slightly thicker district borders
                            legend=False
                        )
                    
                    # 1b. OVERLAY TALUKAS (if checked)
                    if show_talukas and gdf_talukas is not None:
                        # Draw thin, dashed grey lines over the colored districts
                        # facecolor="none" ensures it doesn't cover up your palette colors
                        gdf_talukas.plot(
                            ax=ax_main, 
                            facecolor="none", 
                            edgecolor='#333333', 
                            linewidth=0.4, 
                            linestyle='--', 
                            alpha=0.7
                        )
                    
                    # Add district names to main map with white halos for readability
                    import matplotlib.patheffects as pe
                    for idx, row in highlighted_gdf.iterrows():
                        centroid = row.geometry.centroid
                        ax_main.annotate(
                            text=row[district_col],
                            xy=(centroid.x, centroid.y),
                            horizontalalignment='center',
                            verticalalignment='center',
                            fontsize=12,
                            fontweight='bold',
                            color='black',
                            path_effects=[pe.withStroke(linewidth=3, foreground="white")] 
                        )
                        
                    # 2. ACADEMIC COMPASS ROSE
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

                    # 3. INSET MAP
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
                    ax_main.text(0.5, 0.5, "Select districts to render map.", 
                                 horizontalalignment='center', verticalalignment='center', 
                                 transform=ax_main.transAxes, fontsize=14, color='gray')

                ax_main.set_xticks([])
                ax_main.set_yticks([])
                ax_main.set_frame_on(False)
                
                st.pyplot(fig)
                
                # --- Export High-Res Image ---
                buf = io.BytesIO()
                fig.savefig(buf, format="png", dpi=300)
                buf.seek(0)
                
                st.download_button(
                    label="Download High-Resolution Map (PNG)",
                    data=buf,
                    file_name="academic_survey_map_A4.png",
                    mime="image/png"
                )
