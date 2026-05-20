import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
import os

# --- Page Configuration ---
st.set_page_config(page_title="Ph.D. Survey Map Generator", layout="wide")

st.title("Gujarat Survey Map Generator")
st.markdown("Generate professional, publication-ready maps for your Ph.D. thesis.")

# --- Sidebar Controls ---
st.sidebar.header("1. Map Settings")
highlight_type = st.sidebar.selectbox(
    "Select Boundary Level", 
    ["None", "Gujarat State", "Districts", "Talukas"]
)

st.sidebar.header("2. Upload Survey Data")
st.sidebar.markdown("Upload a CSV file containing `Latitude` and `Longitude` columns.")
uploaded_file = st.sidebar.file_uploader("Upload GPS CSV", type=["csv"])

# --- Initialize Map ---
# Centered on Gujarat
m = folium.Map(location=[22.2587, 71.1924], zoom_start=7)

# 1. Add the clean, publication-friendly street map (Default)
folium.TileLayer(
    tiles="cartodbpositron", 
    name="Clean Street Map"
).add_to(m)

# 2. Add Esri high-resolution Satellite Imagery
folium.TileLayer(
    tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attr='Esri',
    name='Satellite View',
    overlay=False
).add_to(m)

# 3. Add OpenStreetMap as an alternative detailed street map
folium.TileLayer(
    tiles="OpenStreetMap",
    name="Standard Street Map"
).add_to(m)

# --- Add Boundaries ---
# Pointing to the exact file names you uploaded and organized
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
        st.sidebar.warning(f"Boundary file not found: {file_path}. Please check your data folder on GitHub.")

# --- Process and Plot GPS Coordinates ---
if uploaded_file:
    df = pd.read_csv(uploaded_file)
    
    if 'Latitude' in df.columns and 'Longitude' in df.columns:
        
        # UI for Map Styling & Filtering
        st.sidebar.markdown("---")
        st.sidebar.header("3. Map Styling & Filtering")
        
        # Find categorical columns (exclude coordinates)
        categorical_columns = [col for col in df.columns if col not in ['Latitude', 'Longitude']]
        color_options = ["None (All Red)"] + categorical_columns
        
        color_col = st.sidebar.selectbox("Color and filter markers by:", color_options)
        
        filtered_df = df.copy() 
        palette = ['red', 'blue', 'green', 'purple', 'orange', 'darkred', 'cadetblue', 'darkgreen', 'darkpurple', 'pink']
        color_map = {}
        
        if color_col != "None (All Red)":
            unique_values = df[color_col].dropna().unique()
            st.sidebar.markdown("**Select data to display:**")
            
            selected_values = []
            
            # Generate checkboxes and color legend
            for i, val in enumerate(unique_values):
                color_map[val] = palette[i % len(palette)]
                
                # Show colored dot next to checkbox
                st.sidebar.markdown(f"<span style='color:{color_map[val]}'>●</span>", unsafe_allow_html=True)
                is_checked = st.sidebar.checkbox(f"Show {val}", value=True, key=f"check_{val}")
                
                if is_checked:
                    selected_values.append(val)
            
            # Filter the dataframe based on checkboxes
            filtered_df = df[df[color_col].isin(selected_values)]

        # Plot the points
        for _, row in filtered_df.iterrows():
            loc_name = row.get('Location', "Unknown Location")
            
            # Build HTML tooltip for hover effect
            tooltip_text = f"<b>Location:</b> {loc_name}"
            
            if color_col != "None (All Red)" and pd.notna(row[color_col]):
                category_val = row[color_col]
                tooltip_text += f"<br><b>{color_col}:</b> {category_val}"
            
            # Assign color
            marker_color = "red" 
            if color_col != "None (All Red)" and pd.notna(row[color_col]):
                marker_color = color_map.get(row[color_col], "gray")
            
            # Add marker to map
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

# --- Finalize Map ---
# The LayerControl must be added AFTER all tiles, geojson, and markers are added
folium.LayerControl(position='topright').add_to(m)

# Render in Streamlit
st_folium(m, width=800, height=600)

# --- Exporting ---
st.info("💡 **Exporting for Print:** Click the download button below to save the interactive map as an HTML file. Open the HTML file in your web browser, select your preferred background layer, frame your shot, and use a screen capture tool or print to PDF for your thesis.")

st.download_button(
    label="Download Map (HTML)",
    data=m._repr_html_(),
    file_name="survey_map.html",
    mime="text/html"
)
