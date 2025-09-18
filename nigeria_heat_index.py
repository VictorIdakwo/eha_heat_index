import streamlit as st
import ee
import geemap.foliumap as geemap  # Folium backend for Streamlit
import json
import os
import tempfile
from io import StringIO
import sys, types
sys.modules["blessings"] = types.ModuleType("blessings")

if "earthengine" in st.secrets:
    # Streamlit Cloud secret
    sa_info = dict(st.secrets["earthengine"])
    service_account = sa_info["client_email"]

    with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json") as f:
        json.dump(sa_info, f)
        key_file = f.name

    credentials = ee.ServiceAccountCredentials(service_account, key_file)

elif os.getenv("EE_SA_JSON"):
    # GitHub Actions secret
    sa_json = os.getenv("EE_SA_JSON")
    sa_info = json.loads(sa_json)
    service_account = sa_info["client_email"]

    with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".json") as f:
        json.dump(sa_info, f)
        key_file = f.name

    credentials = ee.ServiceAccountCredentials(service_account, key_file)

else:
    # Local development (with file in keys/)
    service_account = "heatindex-analytics@ee-victoridakwo.iam.gserviceaccount.com"
    key_file = "keys/service_account.json"
    credentials = ee.ServiceAccountCredentials(service_account, key_file)

# Initialize Earth Engine
ee.Initialize(credentials)


# =======================
# STEP 2: Define boundary & dates
# =======================
boundary = ee.FeatureCollection('projects/ee-victoridakwo/assets/Northern_Nigeria')
startDate = '1980-01-01'
endDate = '2025-09-15'

# =======================
# STEP 3: Load datasets
# =======================
era5_2mt = ee.ImageCollection('ECMWF/ERA5/DAILY') \
    .select('mean_2m_air_temperature') \
    .filter(ee.Filter.date(startDate, endDate)) \
    .map(lambda image: image.clip(boundary))

era5_2d = ee.ImageCollection('ECMWF/ERA5/DAILY') \
    .select('dewpoint_2m_temperature') \
    .filter(ee.Filter.date(startDate, endDate)) \
    .map(lambda image: image.clip(boundary))

# Compute Relative Humidity
def compute_relative_humidity(tempImage):
    tempDate = tempImage.date()
    dewpointImage = era5_2d.filterDate(tempDate, tempDate.advance(1, 'day')).first()

    rh = ee.Image(dewpointImage).expression(
        '100 - 5 * (T - D)',
        {'T': tempImage, 'D': ee.Image(dewpointImage)}
    ).rename('relative_humidity')

    return tempImage.addBands(rh.set('system:time_start', tempImage.get('system:time_start')))

relativeHumidity = era5_2mt.map(compute_relative_humidity)

# Compute Heat Index
def compute_heat_index(image):
    tempC = image.select('mean_2m_air_temperature')
    tempF = tempC.subtract(273.15).multiply(9/5).add(32)
    RH = image.select('relative_humidity')

    c1, c2, c3, c4, c5, c6, c7, c8, c9 = [
        -42.379, 2.04901523, 10.14333127, -0.22475541,
        -0.00683783, -0.05481717, 0.00122874,
        0.00085282, -0.00000199
    ]

    HI = tempF.expression(
        'c1 + c2*T + c3*R + c4*T*R + c5*T**2 + c6*R**2 + c7*T**2*R + c8*T*R**2 + c9*T**2*R**2',
        {'T': tempF, 'R': RH, 'c1': c1, 'c2': c2, 'c3': c3,
         'c4': c4, 'c5': c5, 'c6': c6, 'c7': c7, 'c8': c8, 'c9': c9}
    ).rename('heat_index')

    return image.addBands(HI.set('system:time_start', image.get('system:time_start')))

heatIndex = relativeHumidity.map(compute_heat_index)

# =======================
# STEP 4: Streamlit UI
# =======================
st.set_page_config(page_title="Climate Explorer", layout="wide")
st.title("🌍 Climate Data Explorer (1980–2025)")

col1, col2, col3 = st.columns(3)
year = col1.slider("Year", 1980, 2019, 2000)
month = col2.slider("Month", 1, 12, 7)
day = col3.slider("Day", 1, 31, 15)

selected_date = f"{year:04d}-{month:02d}-{day:02d}"
st.write(f"📅 Selected Date: **{selected_date}**")

# =======================
# STEP 5: Map Visualization
# =======================
Map = geemap.Map(center=[10, 9], zoom=6)

# Add Heat Index layer
visHI = {'min': 0, 'max': 150, 'palette': ['blue', 'cyan', 'green', 'yellow', 'orange', 'red', 'purple']}
Map.addLayer(heatIndex.filter(ee.Filter.date(selected_date)).select('heat_index'), visHI, "Heat Index")

# Add boundary
boundary_styled = boundary.style(color='black', fillColor='00000000', width=2)
Map.addLayer(boundary_styled, {}, 'Northern Nigeria')

# Add map to Streamlit
Map.to_streamlit(height=700)

# =======================
# STEP 6: Legend
# =======================
with st.expander("📖 Legend"):
    st.markdown("""
    **Heat Index (°F)**  
    - Blue → Cool  
    - Cyan → Mild  
    - Green → Warm  
    - Yellow → Hot  
    - Orange → Very Hot  
    - Red → Extreme  
    - Purple → Dangerous  
    """)

