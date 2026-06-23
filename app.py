from io import BytesIO
import streamlit as st
import pandas as pd
import requests
import math
import time
import random
import pdfplumber as plum

# define global variables
wyears = [2020 - i for i in range(2)]  # for lightning - hail; expand range when finished

# --------------------LIGHTNING - HAIL------------------------------
# Returns tables of occurences per month over wyears (fully functional; missing error handling)
def wtable(event, latp, longp):
    long = str(longp)
    lat = str(latp)
    table = []
    for yr in wyears:
        year = str(yr)
        nxtyr = str(yr+1)

        url = f'https://www.ncei.noaa.gov/swdiws/json/{event}/{year}0101:{nxtyr}0101?stat=tilesum%3A{long}%2C{lat}'
        data = requests.get(url).json()
        results = data["result"]

        row_val_data = [int(i['DAY'].split('-')[1]) for i in results]
        row = [0]*12
        for i in row_val_data:
            row[i-1] += 1

        table.append(row)
    return table

# -------------- RAIN - HEAT - COLD - SNOW--------------------------
# helper function to calculate distance between two decimal coordinate points
def dist(lat1, lon1, lat2, lon2):  # this function was completely built by Gemini
    # Earth's radius (6371.0 for km, 3958.8 for miles)
    r = 3958.8

    # 1. Convert degrees to radians
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    lambda1, lambda2 = math.radians(lon1), math.radians(lon2)

    # 2. Convert Spherical (Lat/Lon) to 3D Cartesian Vectors (X, Y, Z)
    # Point 1 Vector
    x1 = math.cos(phi1) * math.cos(lambda1)
    y1 = math.cos(phi1) * math.sin(lambda1)
    z1 = math.sin(phi1)

    # Point 2 Vector
    x2 = math.cos(phi2) * math.cos(lambda2)
    y2 = math.cos(phi2) * math.sin(lambda2)
    z2 = math.sin(phi2)

    # 3. Calculate Dot Product of the two vectors
    dot_product = (x1 * x2) + (y1 * y2) + (z1 * z2)

    # 4. Clamp dot product to [-1.0, 1.0] to prevent tiny floating-point errors from breaking acos()
    dot_product = max(-1.0, min(1.0, dot_product))

    # 5. Find the vertex angle at the center of the Earth and multiply by radius
    angular_distance_radians = math.acos(dot_product)

    return r * angular_distance_radians

# returns list of potentially viable station ids (sorted by distance, all under 50 mi) to use in pdf request
def test_ids(state, county):
    county = '%20'.join(county.split())  # ensure county name formatted correctly

    # Create URL to retreive station data for State/County
    url = f'https://www.ncei.noaa.gov/access/homr/services/station/search?date=2013-08-23&state={state}&county={county}&definitions=false'

    # Get relevant data (stations dictionary)
    data = requests.get(url).json()
    station_collect = data['stationCollection']
    stations = station_collect['stations']

    # GET LIST OF USABLE IDS
    pdf_ids = []
    distances = []

    for station in stations:
        for my_id in station['identifiers']:
            if my_id['idType'] == 'GHCND':
                coord = ((float(station['header']['latitude_dec']), float(station['header']['longitude_dec'])))
                d = dist(lat_in, long_in, *coord)
                if d < 50:
                    distances.append(d)
                    pdf_ids.append(my_id['id'])
                break

    # SORT IDs BY DISTANCE (sort/lambda)
    sorted_ids = [pdf_ids[i] for i in sorted(range(len(pdf_ids)), key=lambda j: distances[j])]
    return sorted_ids

# Return list of rain, heat, cold, snow data given station id (missing error handling)
def rain_temps_snow_test(station_id):
    pdfurl = f'https://www.ncei.noaa.gov/access/services/data/v1?dataset=normals-monthly-2006-2020&stations={station_id}' \
             '&format=pdf'  # for rain-cold-heat-snow
    pdf_bytes = requests.get(pdfurl).content  # for rain-cold-heat-snow
    with plum.open(BytesIO(pdf_bytes)) as pdf:
        rain_vals = []
        heat_vals = []
        cold_vals = []
        snow_vals = []
        for page in pdf.pages:
            page_data = page.extract_text()
            if "Precipitation (in.)" in page_data:
                lines = page_data.split('\n')
                rain_vals = [float(parts[2]) for line in lines if len(parts := line.split()) > 2 and parts[0].isdigit()]
            elif "Temperature (°F)" in page_data:
                lines = page_data.split('\n')
                heat_vals = [float(parts[18]) for line in lines if len(parts := line.split()) > 21 and parts[0].isdigit()]
                cold_vals = [float(parts[21]) for line in lines if len(parts := line.split()) > 21 and parts[0].isdigit()]
            elif "Snow (in.)" in page_data:
                lines = page_data.split('\n')
                snow_vals = [float(parts[2]) for line in lines if len(parts := line.split()) > 3 and parts[0].isdigit()]
            else:
                continue
        return [rain_vals, heat_vals, cold_vals, snow_vals]

# Returns best list of rain-heat-cold-snow data in specified county
#   if any station has all 4, returns list with rain, heat, cold, and snow data
#   if no station has all 4, but at least one has rain/heat/cold, returns list with rain/heat/cold and [] for snow
#   if no station has at least rain/heat/cold, returns empty list
def rain_temps_snow(state, county):
    county = '%20'.join(county.split())  # ensure county name formatted correctly

    ids = test_ids(state, county)  # get sorted list of ids to test one by one
    rain_heat_cold = []
    for id in ids:
        try:
            masterlist = rain_temps_snow_test(id)
        except Exception:
            print(f'an error occured (station {id} probably has no pdf data)')
            continue
        if all(len(sublist) == 12 and all(isinstance(item, (int, float)) and not math.isnan(item) for item in sublist) for sublist in masterlist):
            print(f'used station {id}')  # just to manually confirm values
            return masterlist
        if not rain_heat_cold:
            if all(len(sublist) == 12 and all(isinstance(item, (int, float)) and not math.isnan(item) for item in sublist) for sublist in masterlist[0:3]):
                print(f'used station {id}')  # just to manually confirm values
                rain_heat_cold = [*masterlist[0:3], []]
        wait_time = random.uniform(1.8, 2.9)
        time.sleep(wait_time)
    return rain_heat_cold




# BUILD WEB APP

# add title, define months
st.title("Weather Tool - Lightning, Hail, Rain, Cold, Heat, Snow")
months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "July", "Aug", "Sep", "Oct", "Nov", "Dec"]


# ask for location data (placeholder values used for now)
lat_in = st.number_input("Latitude (decimal form)", value=43)
long_in = st.number_input("Longitude (decimal form)", value=-113)
state_in = st.text_input("State (abbrev)", value='ID')
county_in = st.text_input("County (include periods if applicable, e.g. 'St. Mary')", value='Butte')
colorado_id = 'USW00023061'  # for testing (known to contain precip/temp/snow data); delete later

# SECTION: LIGHTNING - HAIL
if st.button("Generate Data: **LIGHTNING - HAIL**"):
    st.session_state['lightning'] = wtable('nldn', lat_in, long_in)
    st.session_state['hail'] = wtable('nx3hail', lat_in, long_in)

if "lightning" in st.session_state and "hail" in st.session_state:
    lightning = st.session_state['lightning']
    hail = st.session_state['hail']
    st.subheader("LIGHTNING - HAIL")
    df_lightning = pd.DataFrame(lightning, index=wyears, columns=months)
    df_hail = pd.DataFrame(hail, index=wyears, columns=months)
    st.markdown("**Lightning**")
    st.table(df_lightning)
    st.markdown("**Hail**")
    st.table(df_hail)


# SECTION: RAIN - HEAT - COLD - SNOW
if st.button("Generate Data: **RAIN - HEAT - COLD - SNOW**"):
    # result is either [rain, heat, cold, snow], [rain, heat, cold, []], or []
    st.session_state["rchs"] = rain_temps_snow(state_in, county_in)

if "rchs" in st.session_state:
    rchs = st.session_state['rchs']
    st.subheader("RAIN - HEAT - COLD - SNOW")
    if rchs:
        df_rchs = pd.DataFrame(rchs, index=["Rain", "Heat", "Cold", "Snow"], columns=months).T
        st.table(df_rchs.style.format("{:.1f}"))
        if not rchs[-1]:
            st.warning(f'No snow data found for {county_in}. Would you like to try another county?')
    else:
        st.warning(f'All {county_in} stations within 50 mi have missing rain or temperature data. Please try another county.')
