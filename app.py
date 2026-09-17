from io import BytesIO
from bs4 import BeautifulSoup
import streamlit as st
import pandas as pd
from curl_cffi import requests
import math
import time
import random
import os
import pdfplumber as plum

# define global variables
wyears = [2020 - i for i in range(11)]  # for lightning - hail; expand range to 11
FIPS_CACHE = "county_fips.csv"
STATES = {
    "AL": ["ALABAMA", "01"], "AK": ["ALASKA", "02"], "AZ": ["ARIZONA", "04"], "AR": ["ARKANSAS", "05"],
    "CA": ["CALIFORNIA", "06"], "CO": ["COLORADO", "08"], "CT": ["CONNECTICUT", "09"], "DE": ["DELAWARE", "10"],
    "FL": ["FLORIDA", "12"], "GA": ["GEORGIA", "13"], "HI": ["HAWAII", "15"], "ID": ["IDAHO", "16"],
    "IL": ["ILLINOIS", "17"], "IN": ["INDIANA", "18"], "IA": ["IOWA", "19"], "KS": ["KANSAS", "20"],
    "KY": ["KENTUCKY", "21"], "LA": ["LOUISIANA", "22"], "ME": ["MAINE", "23"], "MD": ["MARYLAND", "24"],
    "MA": ["MASSACHUSETTS", "25"], "MI": ["MICHIGAN", "26"], "MN": ["MINNESOTA", "27"], "MS": ["MISSISSIPPI", "28"],
    "MO": ["MISSOURI", "29"], "MT": ["MONTANA", "30"], "NE": ["NEBRASKA", "31"], "NV": ["NEVADA", "32"],
    "NH": ["NEW HAMPSHIRE", "33"], "NJ": ["NEW JERSEY", "34"], "NM": ["NEW MEXICO", "35"], "NY": ["NEW YORK", "36"],
    "NC": ["NORTH CAROLINA", "37"], "ND": ["NORTH DAKOTA", "38"], "OH": ["OHIO", "39"], "OK": ["OKLAHOMA", "40"],
    "OR": ["OREGON", "41"], "PA": ["PENNSYLVANIA", "42"], "RI": ["RHODE ISLAND", "44"], "SC": ["SOUTH CAROLINA", "45"],
    "SD": ["SOUTH DAKOTA", "46"], "TN": ["TENNESSEE", "47"], "TX": ["TEXAS", "48"], "UT": ["UTAH", "49"],
    "VT": ["VERMONT", "50"], "VA": ["VIRGINIA", "51"], "WA": ["WASHINGTON", "53"], "WV": ["WEST VIRGINIA", "54"],
    "WI": ["WISCONSIN", "55"], "WY": ["WYOMING", "56"], "DC": ["DISTRICT OF COLUMBIA", "11"],
}
station_id_used = ''  # will be updated with actual id ised for rain/heat/cold/snow


# --------------------LIGHTNING - HAIL------------------------------
# Returns tables of occurences per month over wyears (fully functional; missing error handling)
def wtable(event, latp, longp):
    long = str(longp)
    lat = str(latp)
    table = []

    with requests.Session() as session:
        for yr in wyears:
            year = str(yr)
            nxtyr = str(yr + 1)

            url = f'https://www.ncei.noaa.gov/swdiws/json/{event}/{year}0101:{nxtyr}0101?stat=tilesum%3A{long}%2C{lat}'
            data = session.get(url).json()
            results = data["result"]

            row_val_data = [int(i['DAY'].split('-')[1]) for i in results]
            row = [0] * 12
            for i in row_val_data:
                row[i - 1] += 1

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
def _rain_temps_snow_test(station_id):
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
                heat_vals = [float(parts[18]) for line in lines if
                             len(parts := line.split()) > 21 and parts[0].isdigit()]
                cold_vals = [float(parts[21]) for line in lines if
                             len(parts := line.split()) > 21 and parts[0].isdigit()]
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
    global station_id_used

    ids = test_ids(state, county)  # get sorted list of ids to test one by one
    rain_heat_cold = []
    for id in ids:
        try:
            masterlist = _rain_temps_snow_test(id)
        except Exception:
            print(f'an error occured (station {id} probably has no pdf data)')
            continue
        if all(len(sublist) == 12 and all(isinstance(item, (int, float)) and not math.isnan(item) for item in sublist)
               for sublist in masterlist):
            station_id_used = id  # just to manually confirm values
            return masterlist
        if not rain_heat_cold:
            if all(len(sublist) == 12 and all(
                    isinstance(item, (int, float)) and not math.isnan(item) for item in sublist) for sublist in
                   masterlist[0:3]):
                station_id_used = id  # just to manually confirm values
                rain_heat_cold = [*masterlist[0:3], []]
        wait_time = random.uniform(1.8, 2.9)
        time.sleep(wait_time)
    return rain_heat_cold


# -------------- TORNADO --------------------------
def get_tornado_dates(st_in, cty_in):
    state = STATES[st_in][0].title()
    county = cty_in.title()
    start_date = '1950-01-01'
    end_date = "2025-12-31"

    payload = {"stateList": [state], "countyList": [county], "eventList": ["Tornado"], "mapList": [], "addressList": [],
               "beginDate": start_date, "endDate": end_date, "searchName": "", "floodFilter": [], "onThisDay": False,
               "beginDate_isValid": True, "endDate_isValid": True, "activeTab": 1,
               "mapData": []}  # not sure if all these parameters are needed

    endpoint = 'https://www.ncei.noaa.gov/access/storm-events-database/api/search-events'

    response = requests.post(endpoint, json=payload)
    data_json = response.json()

    dates = [i['begin_date_time_formatted'].split(' ')[0] for i in data_json['data']]

    return dates


# -------------- HURRICANE --------------------------
def get_state(abbr):
    return STATES[abbr.upper()]

def get_hurricane_dates(st_in, cty_in):
    county = cty_in.strip().replace(' ', '-')
    state = get_state(st_in.strip())[0].replace(' ', '-')

    url = f'https://www.homefacts.com/hurricanes/{state}/{county}-county.html'

    # get hurricane data
    # with (requests.Session() as session):
    #     response = sessio
    #
    response = requests.get(url, impersonate='chrome120')

    # 1. CHECK THE HTTP STATUS CODE
    print(f"Status Code: {response.status_code}")


    # print("scrollcontent_listingpage" in response.text)
    soup = BeautifulSoup(response.text, 'lxml')

    # 2. CHECK THE WEBPAGE TITLE
    if soup.title:
        print(f"Page Title: {soup.title.text}")
    # print('---------------------TITLE')
    # print(soup.title)
    # print('---------------------STATUS CODE')
    # print(response.url)
    # print(response.status_code)
    # print('----------------------RESPONSE TEXT')
    # print(response.text[:500])
    # print('START SOUP_____________________')
    # print(soup)
    # print('END SOUP_____________________')
    if soup.title:
        st.write(f"The target page title is: {soup.title.text}")
    container = soup.find('div', class_='scrollcontent_listingpage')
    if container is None:
        print("Could not find the target layout container on the page!")
        return [] # Returns an empty list safely instead of crashing the app
    # print(container)
    rows = container.find_all('div', recursive=False)

    # get dates
    dates = []
    for row in rows:
        cells = row.find_all('div', class_='table_row_cell')
        if len(cells) >= 2:
            dates.append(cells[1].text.strip())

    return dates


# BUILD WEB APP

# add title, define months
st.title("Weather Tool - Lightning, Hail, Rain, Cold, Heat, Snow, Tornado, Hurricane - 710")
months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "July", "Aug", "Sep", "Oct", "Nov", "Dec"]

# ask for location data (placeholder values used for now)
lat_in = st.number_input("Latitude (decimal form)", value=43.00)
long_in = st.number_input("Longitude (decimal form)", value=-113.00)
state_in = st.text_input("State (abbrev)", value='ID')
county_in = st.text_input("County (include periods if applicable, e.g. 'St. Mary')", value='Butte')

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
    st.dataframe(df_lightning)
    st.markdown("**Hail**")
    st.dataframe(df_hail)

# SECTION: RAIN - HEAT - COLD - SNOW
if st.button("Generate Data: **RAIN - HEAT - COLD - SNOW**"):
    # result is either [rain, heat, cold, snow], [rain, heat, cold, []], or []
    st.session_state["rchs"] = rain_temps_snow(state_in, county_in)

if "rchs" in st.session_state:
    rchs = st.session_state['rchs']
    st.subheader("RAIN - HEAT - COLD - SNOW")
    if rchs:
        df_rchs = pd.DataFrame(rchs, index=["Rain", "Heat", "Cold", "Snow"], columns=months).T
        st.dataframe(df_rchs.style.format("{:.1f}"))
        if not rchs[-1]:
            st.warning(f'No snow data found for {county_in}. Would you like to try another county?')
        st.write(f'Station ID: {station_id_used}')
    else:
        st.warning(
            f'All {county_in} stations within 50 mi have missing rain or temperature data. Please try another county.')

# SECTION: TORNADO
if st.button("Generate Data: **TORNADO**"):
    st.session_state['tornado'] = get_tornado_dates(state_in, county_in)

if "tornado" in st.session_state:
    tornado = st.session_state['tornado']
    st.subheader("TORNADO")
    df_tornado = pd.DataFrame(tornado, columns=["Dates"])
    df_tornado.index = range(1, len(df_tornado) + 1)
    st.dataframe(df_tornado)

# SECTION: HURRICANE
if st.button("Generate Data: **HURRICANE**"):
    st.session_state['hurricane'] = get_hurricane_dates(state_in, county_in)

if "hurricane" in st.session_state:
    hurricane = st.session_state['hurricane']
    st.subheader("HURRICANE")
    df_hurricane = pd.DataFrame(hurricane, columns=["Dates"])
    df_hurricane.index = range(1, len(df_hurricane) + 1)
    st.dataframe(df_hurricane)
