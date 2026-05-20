import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import io
import os

# --- Page Configuration ---
st.set_page_config(page_title="Ph.D. Survey Map Generator", layout="wide")

st.title("Gujarat Survey Map Generator")
st.markdown("Generate professional, publication-ready maps for your Ph.D. thesis.")

# --- Setup Tabs ---
tab1, tab2 = st.tabs(["Interactive GPS Map", "Static Thesis Region Map"])

# ==========================================
# TAB 1: INTERACTIVE GPS MAP (Original App)
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
# TAB 2: STATIC THESIS REGION MAP (INSET STYLE)
# ==========================================
with tab2:
    st.header("Static Region Highlight Map (Inset Style)")
    st.markdown("Generate a zoomed-in main map with a state-wide inset, exactly like the *P. gossypiella* reference plate.")
    
    district_geojson_path = "data/gujarat.geojson"
    
    if not os.path.exists(district_geojson_path):
        st.error(f"Cannot find {district_geojson_path}. Please ensure your GeoJSON is in the data folder.")
    else:
        gdf = gpd.read_file(district_geojson_path)
        
# Ensure we have a column that uniquely identifies districts
        district_col = None
        # Added 'district_name' and 'REGNAME' to match your specific GeoJSON file
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
                # Default to the middle Gujarat cluster
                selected_districts = st.multiselect(
                    "Select districts to highlight:",
                    options=all_districts,
                    default=["Ahmedabad", "Anand", "Vadodara", "Kheda", "Panchmahal", "Dahod", "Mahisagar", "Chhotaudepur", "Botad"] 
                )
                
                st.subheader("2. Map Styling")
                plate_title = st.text_area("Plate Title / Caption", value="Plate 3.1: Map showing the districts of middle Gujarat surveyed for the collection of pink bollworm, P. gossypiella", height=100)
                color_map_choice = st.selectbox("Highlight Palette", ["Pastel1", "Set3", "Accent", "tab20c"])
                
            with col4:
                # Create the main figure
                fig, ax_main = plt.subplots(figsize=(10, 7), dpi=300)
                
                if selected_districts:
                    # 1. MAIN MAP: Plot ONLY the selected districts
                    highlighted_gdf = gdf[gdf[district_col].isin(selected_districts)]
                    
                    highlighted_gdf.plot(
                        ax=ax_main, 
                        column=district_col, 
                        cmap=color_map_choice, 
                        edgecolor='black', 
                        linewidth=1.2,
                        legend=False
                    )
                    
                    # Add district names to main map
                    for idx, row in highlighted_gdf.iterrows():
                        centroid = row.geometry.centroid
                        ax_main.annotate(
                            text=row[district_col],
                            xy=(centroid.x, centroid.y),
                            horizontalalignment='center',
                            verticalalignment='center',
                            fontsize=9,
                            fontweight='bold',
                            color='black'
                        )
                        
                    # 2. INSET MAP: Add the small map in the top left
                    # Coordinates: [left, bottom, width, height] as fractions of figure
                    ax_inset = fig.add_axes([0.05, 0.65, 0.25, 0.25]) 
                    
                    # Plot whole state in white
                    gdf.plot(ax=ax_inset, color='white', edgecolor='gray', linewidth=0.5)
                    # Highlight selected region in pink
                    highlighted_gdf.plot(ax=ax_inset, color='#ff99cc', edgecolor='black', linewidth=0.5)
                    
                    # Remove axis from inset map
                    ax_inset.set_xticks([])
                    ax_inset.set_yticks([])
                    ax_inset.set_frame_on(False)
                    
                else:
                    # Fallback if nothing is selected
                    gdf.plot(ax=ax_main, color='white', edgecolor='black')

                # Remove axis from main map for a clean look
                ax_main.set_xticks([])
                ax_main.set_yticks([])
                ax_main.set_frame_on(False)
                
                # 3. TITLE BLOCK: Blue rectangle at the bottom
                if plate_title:
                    plt.figtext(
                        0.5, 0.05,  # Positioned at the bottom center
                        plate_title, 
                        wrap=True, 
                        horizontalalignment='center', 
                        verticalalignment='center',
                        fontsize=12, 
                        fontweight='bold', 
                        color="white",
                        bbox=dict(
                            facecolor="#4A7EBB", # The matching blue shade
                            edgecolor="black", 
                            boxstyle="square,pad=1", # Pad adds space around text
                            linewidth=0.5
                        )
                    )
                
                st.pyplot(fig)
                
                # --- Export High-Res Image ---
                buf = io.BytesIO()
                fig.savefig(buf, format="png", dpi=300, bbox_inches="tight")
                buf.seek(0)
                
                st.download_button(
                    label="Download High-Resolution Map (PNG)",
                    data=buf,
                    file_name="thesis_survey_map_inset.png",
                    mime="image/png"
                )
