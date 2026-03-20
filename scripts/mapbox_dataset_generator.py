"""
Generate random images using the mapbox static API. 
In order to use this, go to mapbox.com, create an account and get an access token (free up to 50k images).

Image parameters used: 
- longitude and latitude: random uniform over the globe. It might be smart to exlude the oceans here (not done)
- zoom: mapbox zoom factor (see documentation). The zoom is calculated to match a satellite at 560km given the pitch
- bearing: random from any direction. Angle relative to north
- pitch: random from 0 to 60 degrees. 0 degrees is nadir, 60 degrees is very oblique (limit supported by the API)


Problems: 
- the location is random -> around 70% of the images are 100% water
- the distribution of the images is purely random (uniformly distributed) and does not consider satellite orbital mechanics. 
- geometric simplifications (yes, the earth is flat!)
"""


from fileinput import filename
import random
from math import cos, log2, radians
import requests
import os

MAPBOX_TOKEN = os.environ.get("MAPBOX_ACCESS_TOKEN")


def get_image(data):
    url = f"https://api.mapbox.com/styles/v1/mapbox/satellite-v9/static/{data['lon']},{data['lat']},{data['zoom']},{data['bearing']},{data['pitch']}/1280x1280@2x?access_token={MAPBOX_TOKEN}"
    filename = f"./scripts/mapbox_dataset/lon{data['lon']}_lat{data['lat']}_b{data['bearing']}_p{data['pitch']}_z{data['zoom']}.png"
    response = requests.get(url)
    if response.status_code == 200:            
        with open(filename, "wb") as f:
            f.write(response.content)
            print(f"Saved {filename}")
    else:
        print(f"Error fetching image: {response.status_code} - {response.text}")

def get_random_image_parameters():
    pitch = random.uniform(0,60)
    data = {
        "lon": random.uniform(-180, 180),
        "lat": random.uniform(-90, 90),
        "zoom": 13.92 + log2(560/random.uniform(560, 560/cos(radians(pitch)))),
        "bearing": random.uniform(0,360),
        "pitch": pitch
    }
    return data

for _ in range(20):
    params = get_random_image_parameters()
    print(params)
    get_image(params)