import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
import os
from PIL import Image

# --- Page Configuration ---
# Set the page config ONLY ONCE at the very top of the script
st.set_page_config(page_title="Acarology Research Suite", layout="wide")

# ==========================================
# Sidebar Navigation
# ==========================================
st.sidebar.title("🔬 Acarology Suite")
app_mode = st.sidebar.radio("Select Application:", ["🗺️ Survey Map Generator", "🕷️ Mite ID Pro"])
st.sidebar.markdown("---")

# ==========================================
# APP 1: SURVEY MAP GENERATOR
# ==========================================
if app_mode == "🗺️ Survey Map Generator":
    st.title("Gujarat Survey Map Generator")
    st.markdown("Generate professional, publication-ready maps for your Ph.D. thesis.")

    # --- Map Settings ---
    st.sidebar.header("1. Map Settings")
    highlight_type = st.sidebar.selectbox(
        "Select Boundary Level", 
        ["None", "Gujarat State", "Districts", "Talukas"]
    )

    st.sidebar.header("2. Upload Survey Data")
    st.sidebar.markdown("Upload a CSV file containing `Latitude` and `Longitude` columns.")
    uploaded_file = st.sidebar.file_uploader("Upload GPS CSV", type=["csv"])

    # --- Initialize Map ---
    m = folium.Map(location=[22.2587, 71.1924], zoom_start=7)

    folium.TileLayer(tiles="cartodbpositron", name="Clean Street Map").add_to(m)
    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Esri', name='Satellite View', overlay=False
    ).add_to(m)
    folium.TileLayer(tiles="OpenStreetMap", name="Standard Street Map").add_to(m)

    # --- Add Boundaries ---
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

    # --- Process GPS Coordinates ---
    if uploaded_file:
        df = pd.read_csv(uploaded_file)
        
        if 'Latitude' in df.columns and 'Longitude' in df.columns:
            st.sidebar.markdown("---")
            st.sidebar.header("3. Map Styling & Filtering")
            
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
                for i, val in enumerate(unique_values):
                    color_map[val] = palette[i % len(palette)]
                    st.sidebar.markdown(f"<span style='color:{color_map[val]}'>●</span>", unsafe_allow_html=True)
                    is_checked = st.sidebar.checkbox(f"Show {val}", value=True, key=f"check_{val}")
                    if is_checked:
                        selected_values.append(val)
                filtered_df = df[df[color_col].isin(selected_values)]

            for _, row in filtered_df.iterrows():
                loc_name = row.get('Location', "Unknown Location")
                tooltip_text = f"<b>Location:</b> {loc_name}"
                if color_col != "None (All Red)" and pd.notna(row[color_col]):
                    tooltip_text += f"<br><b>{color_col}:</b> {row[color_col]}"
                
                marker_color = color_map.get(row[color_col], "gray") if color_col != "None (All Red)" and pd.notna(row[color_col]) else "red"
                
                folium.CircleMarker(
                    location=[row['Latitude'], row['Longitude']],
                    radius=6, color=marker_color, fill=True, fill_color=marker_color,
                    fill_opacity=0.8, tooltip=tooltip_text, popup=loc_name
                ).add_to(m)
                
            st.success(f"Displaying {len(filtered_df)} out of {len(df)} sample points.")
        else:
            st.error("Your CSV file must contain exactly 'Latitude' and 'Longitude' columns.")

    folium.LayerControl(position='topright').add_to(m)
    st_folium(m, width=800, height=600)

    st.download_button(
        label="Download Map (HTML)",
        data=m._repr_html_(),
        file_name="survey_map.html",
        mime="text/html"
    )

# ==========================================
# APP 2: MITE ID PRO
# ==========================================
elif app_mode == "🕷️ Mite ID Pro":
    st.title("Mite ID Pro: Agricultural Acarology")
    st.markdown("Upload microscopic images for AI-powered mite identification and management protocols.")

    # --- Sidebar Inputs for AI ---
    st.sidebar.header("Upload Details")
    mite_image = st.sidebar.file_uploader("Upload Mite Image", type=["jpg", "jpeg", "png"])
    host_crop = st.sidebar.selectbox("Host Crop Context", ["Cotton", "Brinjal", "Chilli", "Okra", "Rice", "Other"])
    
    st.sidebar.markdown("---")
    st.sidebar.header("Analysis Settings")
    confidence_threshold = st.sidebar.slider("Confidence Threshold", 50, 99, 85)

    if mite_image is not None:
        # Create two columns for the layout (Image on left, Results on right)
        col1, col2 = st.columns([1, 1.2])

        with col1:
            st.subheader("Uploaded Specimen")
            image = Image.open(mite_image)
            st.image(image, use_container_width=True, caption="Microscopic View")

        with col2:
            st.subheader("AI Analysis Results")
            
            # ---------------------------------------------------------
            # 🚨 ML MODEL INTEGRATION POINT 🚨
            # Here is where you will pass 'image' to your PyTorch/TensorFlow model
            # For now, we simulate the output based on your screenshot:
            predicted_species = "Tetranychus urticae (Two-spotted spider mite)"
            confidence_score = 98.5
            # ---------------------------------------------------------

            if confidence_score >= confidence_threshold:
                st.success("Identification Successful")
                
                # Display the prediction beautifully
                st.markdown(f"### Prediction: **{predicted_species}**")
                st.progress(confidence_score / 100)
                st.markdown(f"**Confidence:** {confidence_score}%")

                st.error("⚠️ High risk of economic damage to Cotton in dry conditions.")

                st.markdown("### Management Recommendations:")
                st.markdown("""
                * **Chemical:** Abamectin 1.9 EC or Spiromesifen 22.9 SC
                * **Biological:** Introduction of *Phytoseiulus persimilis* predators
                * **Cultural:** Remove broadleaf weeds near field borders; maintain irrigation
                """)

                with st.expander("🔍 Morphological Traits Identified"):
                    st.markdown("""
                    * Prominent pair of dark spots on the lateral aspects of the idiosoma.
                    * Globular body shape typical of Tetranychidae.
                    * Detected webbing structures in the background image.
                    """)
            else:
                st.warning(f"Confidence score ({confidence_score}%) is below your threshold ({confidence_threshold}%). Please upload a clearer image.")
    else:
        st.info("👈 Please upload an image from the sidebar to begin analysis.")
