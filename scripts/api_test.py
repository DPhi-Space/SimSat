# make the equivalent of curl http://127.0.0.1:8000/data/current/image/sentinel in python

import requests
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
import xarray as xr
import base64
import numpy as np
import io
import json
from PIL import Image
from io import BytesIO

def show_image(image_data):
    def scale_rgb(image_array):
        """Normalize 16-bit reflectance to 0-1 for display"""
        return (image_array / 3000).clip(0, 1)
    
    images = {}

    
    # create false color images using different band combinations
    # True Color (Red, Green, Blue)
    images['rgb'] = {'image': scale_rgb(image_data[["red", "green", "blue"]].to_array().values.transpose(1, 2, 0))}
    images['rgb']['description'] = "True Color (red, green, blue)"

    print(f"Prepared {len(images)} images for display.")

    if len(images) == 0:
        print("No images to display.")
        return
    elif len(images) == 1:
        key, img_info = next(iter(images.items()))
        plt.figure(figsize=(8, 8))
        plt.imshow(img_info['image'])
        plt.title(img_info['description'])
        plt.axis('off')
    else:
        n_cols = min(5, len(images))
        n_rows = (len(images) + n_cols - 1) // n_cols
        fig, ax = plt.subplots(n_rows, n_cols, figsize=(20, 10))

        for i, (key, img_info) in enumerate(images.items()):
            r = i // n_cols
            c = i % n_cols
            ax[r, c].imshow(img_info['image'])
            ax[r, c].set_title(img_info['description'])
            ax[r, c].axis('off')

    plt.tight_layout()
    print("Displaying images...")
    plt.show()

def test_sentinel_old():
    response = requests.get("http://localhost:9005/data/current/image/sentinel")

    # check whether the request returned an error
    if response.status_code != 200:
        print(f"Error: Received status code {response.status_code}")
        print(f"Response: {response.text}")
        exit(1)


    response_json = response.json()
    meta = response_json['metadata']

    # 1. Decode and reshape
    raw_bytes = base64.b64decode(response_json['image'])
    flat_array = np.frombuffer(raw_bytes, dtype=meta['dtype'])
    reshaped_array = flat_array.reshape(meta['shape'])

    # 2. Rebuild the Dataset
    # We put it back into the (Band, Y, X) structure
    image_xr = xr.DataArray(
        reshaped_array,
        dims=("band", "y", "x"),
        coords={"band": meta['bands']}
    ).to_dataset(dim="band")

    # Now this will work!
    show_image(image_xr)

def test_mapbox():
    # get the satellite position from the api

    position = requests.get("http://localhost:9005/data/current/position").json()
    lon = position["lon-lat-alt"][0]
    lat = position["lon-lat-alt"][1]

    # we always look straight down

    print(f"Satellite position lon={lon}, lat={lat}")


    params = {
        "lat": lat,
        "lon": lon
    }
    response = requests.get("http://localhost:9005/data/current/image/mapbox", params=params)

    # check whether the request returned an error
    if response.status_code != 200:
        print(f"Error: Received status code {response.status_code}")
        print(f"Response: {response.text}")
        print(response.content)
        exit(1)

    metadata = json.loads(response.headers.get("mapbox_metadata"))
    print(f"Mapbox metadata: {metadata}")
    if not metadata.get("image_available", False):
        print("No image available")
        return

    # show the image
    image = mpimg.imread(io.BytesIO(response.content), format='PNG')
    plt.figure(figsize=(8, 8))
    plt.imshow(image)
    plt.title(f"Mapbox Image at lon={lon}, lat={lat}")
    plt.axis('off')
    plt.show()

def test_mapbox_lon_lat():
 
    params = {
        "lon_target": 6.6323,
        "lat_target": 46.5197,
        "lon_satellite": 6.6323,
        "lat_satellite": 46.5197,
        "alt_satellite": 500
    }
    response = requests.get("http://localhost:9005/data/image/mapbox", params=params)

    # check whether the request returned an error
    if response.status_code != 200:
        print(f"Error: Received status code {response.status_code}")
        print(f"Response: {response.text}")
        print(response.content)
        exit(1)

    metadata = json.loads(response.headers.get("mapbox_metadata"))
    print(f"Mapbox metadata: {metadata}")
    if not metadata.get("image_available", False):
        print("No image available")
        return

    # show the image
    image = mpimg.imread(io.BytesIO(response.content), format='PNG')
    plt.figure(figsize=(8, 8))
    plt.imshow(image)
    plt.axis('off')
    plt.show()


def test_sentinel():
    params = {
        "spectral_bands": ["red", "green", "blue"],
        "size_km": 5.0,
        "window_seconds": 60.0,
        "return_type": "png"
    }
    response = requests.get("http://localhost:9005/data/current/image/sentinel", params=params)

    if response.status_code == 200:
        if params["return_type"] == "png":
            metadata = json.loads(response.headers.get("sentinel_metadata"))
            print(f"Sentinel metadata: {metadata}")
            if metadata["image_available"]:
                img = Image.open(BytesIO(response.content))
                img.show()  # This opens your default OS image viewer
            else:    
                print("No image available")
        else:
            metadata = response.json()["sentinel_metadata"]
            print(f"Sentinel metadata: {metadata}")
            if metadata["image_available"]:
                image = response.json()["image"]
                print(f"Sentinel image: {image["metadata"]["shape"]}")
            else:
                print("No image available")
    else:
        print(f"Error: Received status code {response.status_code}")
        print(f"Response: {response.text}")

def test_sentinel_lon_lat():
    params = {
        "lon": 6.6323,
        "lat": 46.5197,
        "timestamp": "2024-07-28T23:59:59Z",
        "spectral_bands": ["red", "green", "blue"],
        "size_km": 15.0,
        "window_seconds": 60.0,
        "return_type": "array"
    }
    response = requests.get("http://localhost:9005/data/image/sentinel", params=params)

    if response.status_code == 200:
        if params["return_type"] == "png":
            metadata = json.loads(response.headers.get("sentinel_metadata"))
            print(f"Sentinel metadata: {metadata}")
            if metadata["image_available"]:
                img = Image.open(BytesIO(response.content))
                img.show()  # This opens your default OS image viewer
            else:    
                print("No image available")
        else:
            metadata = response.json()["sentinel_metadata"]
            print(f"Sentinel metadata: {metadata}")
            if metadata["image_available"]:
                image = response.json()["image"]
                print(f"Sentinel image: {image["metadata"]["shape"]}")
            else:
                print("No image available")
    else:
        print(f"Error: Received status code {response.status_code}")
        print(f"Response: {response.text}")


def test_sentinel_hyperspectral():

    """
    # create false color images using different band combinations
    # True Color (Red, Green, Blue)
    images['rgb'] = {'image': scale_rgb(image_data[["red", "green", "blue"]].to_array().values.transpose(1, 2, 0))}
    images['rgb']['description'] = "True Color (red, green, blue)"
    # traditional NIR image. healthy plants reflect NIR and are therefore  a strong red. Allows to see different vegetation. Bright red = healthy forest/crops; Dull red = grasslands; Cyan/Grey = buildings and other non-vegetated surfaces
    images['tnir'] = {'image': scale_rgb(image_data[["nir", "red", "green"]].to_array().values.transpose(1, 2, 0))}
    images['tnir']['description'] = "Traditional NIR (nir, red, green)"
    # SWIR (showrt-wave infrared): sensiteive to water and water. Deep green indicates lush, water-rich vegetation. Very dark blue/black indicates clear water.
    images['swir'] = {'image': scale_rgb(image_data[["swir22", "nir", "green"]].to_array().values.transpose(1, 2, 0))}
    images['swir']['description'] = "SWIR (swir22, nir, green)"
    # urban false color with swire22, swir16, red: This combination "sees" through atmospheric haze and smoke much better than visible light. Urban areas and bare soil pop in shades of purple and brown, while vegetation appears in green.
    images['ufc'] = {'image': scale_rgb(image_data[["swir22", "swir16", "red"]].to_array().values.transpose(1, 2, 0))}
    images['ufc']['description'] = "Urban False Color (swir22, swir16, red)"
    # vegetation index: rededge3, rededge2, rededge1 Sentinel-2 is unique because of these three "Red Edge" bands. They capture the specific point where plant reflectance jumps. Precision agriculture and detecting early-stage plant stress before it’s visible in RGB. Color differences indicate differences in platn health/development.
    images['vi'] = {'image': scale_rgb(image_data[["rededge3", "rededge2", "rededge1"]].to_array().values.transpose(1, 2, 0))}
    images['vi']['description'] = "Vegetation Index (rededge3, rededge2, rededge1)"

    """

    images = []
    for i, spectral_bands in enumerate([ ['red', 'green', 'blue'], 
                                         ['nir', 'red', 'green'], 
                                         ["swir22", "nir", "green"],
                                         ["swir22", "swir16", "red"],
                                         ['rededge1', 'rededge2', 'rededge3']]):
        params = {
        "spectral_bands": spectral_bands,
        "size_km": 5.0,
        "return_type": "png",
        "window_seconds": 60.0,
        }
        response = requests.get("http://localhost:9005/data/current/image/sentinel", params=params)
        if response.status_code != 200:
            print(f"Error: Received status code {response.status_code}")
            print(f"Response: {response.text}")
            return
        images.append([(mpimg.imread(io.BytesIO(response.content), format='PNG')), "_".join(spectral_bands)]) 

    # show all images side by side
    n_images = len(images)
    fig, ax = plt.subplots(1, n_images, figsize=(5 * n_images, 5))
    for i in range(n_images):
        ax[i].imshow(images[i][0])
        ax[i].set_title(f"Bands: {images[i][1]}")
        ax[i].axis('off')
    plt.show()
        
    

    # mapbox image

if __name__ == "__main__":
    test_sentinel()
    #test_mapbox()
    #test_sentinel_hyperspectral()
    #test_sentinel_lon_lat()
    #test_mapbox_lon_lat()