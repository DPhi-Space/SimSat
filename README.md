# SimSat
This tool simulates the accessibility of Earth imagery from a satellite. An orbit propagator calculates the satellite position over time and an API serves as an interface to on-board users, sharing the current position, timestamp and providing satellite imagery from that location. A web-based dashboard controls and visualizes the simulation.

## Upcoming Hackathon: AI in Space | Liquid AI x DPhi Space

This is the official repository for the upcoming [AI in Space Hackathon](https://luma.com/n9cw58h0), organised in partnership between DPhi Space and Liquid AI.

This is a fully online event, open to builders from all around the globe.

<div align="center">
  <a href="https://luma.com/n9cw58h0">
    <img
      src="banner.jpeg"
      alt="SimSat"
      style="width: 70%; max-width: 70%; height: auto; display: inline-block; margin-bottom: 0.5em; margin-top: 0.5em;"
    />
  </a>
  <div>
    <a href="https://luma.com/n9cw58h0"><img src="https://img.shields.io/badge/Register%20for%20the%20Event-C026D3?style=for-the-badge" alt="Register for the Event" /></a>
  </div>
</div>


## Table of Contents
- [Getting Started](#getting-started)
- [Simulation Control](#simulation-control)
- [APIs](#apis)
  - [/data/current/position](#get-datacurrentposition)
  - [/data/current/image/sentinel](#get-datacurrentimagesentinel)
  - [/data/current/image/mapbox](#get-datacurrentimagemapbox)
  - [/data/image/sentinel](#get-dataimagesentinel)
  - [/data/image/mapbox](#get-dataimagemapbox)
- [Datasets](#datasets)
  - [Sentinel-2](#sentinel-2)
  - [Mapbox](#mapbox)
- [Test Examples](#test-examples)

---
# Getting Started
To start the environment, start the Docker containers with

```bash
docker compose up
```

After the startup, the dashboard is accessible at [http://localhost:8000](http://localhost:8000). To start the simulation, press the start button. Then you can follow the satellite by clicking on the blue dot followed by clicking on the camera icon in the popup window. 

The API to fetch images is accessible at [http://localhost:9005](http://localhost:9005). In order to test this, you can run the provided script `scripts/api_test.py` from your host machine. This will fetch an image from the API and display it using matplotlib.
```bash
python scripts/api_test.py
```

Note: if no image is displayed, the satellite might be over the ocean. More details about image availability are reported in the [Datasets Section](#datasets).

---
# Simulation Control
The simulation can be controlled through the web dashboard by setting the following parameters:
- **Start time:** it must be in the ISO-8601 UTC format `YYYY-MM-DDThh:mm:ssZ`. For example `2026-01-01T16:00:00Z`. 
- **Step size:** simulated time increment (in seconds) between each simulation update.
- **Replay speed:** how fast simulation time runs compared to real time (`1` = real time, `2` = twice as fast).

The changes are applied when the start button is pressed. If the simulation is not able to run as fast as the settings require, the system will throttle itself down. We recommend to set the step size and replay speed such that `replay_speed / step_size <= 2`.

---
# APIs

The satellite can be accessed through the provided APIs. The base URL for the APIs is [http://localhost:9005](http://localhost:9005).

### GET /data/current/position

This endpoint returns the current position of the satellite in latitude (degrees), longitude (degrees), and altitude (kilometers), as well as the current simulation timestamp.

**Response Example:**
```bash
{
  'lon-lat-alt':[130.39051988505403,17.87271962388168,791.3415172015517],
  'timestamp':'2026-01-01T16:00:00Z'
}
```

### GET /data/current/image/sentinel
This endpoint returns an image from the Sentinel-2 dataset for the current satellite position. More information about Sentinel-2 images can be found in the [Datasets Section](#datasets)

**Query Parameters:**
- `spectral_bands`: Comma-separated list of spectral bands to include in the image (default: "red","green","blue")
- `size_km`: Size of the image in kilometers (default: 5.0)
- `return_type`: Format of the returned image, either "png" or "array" (default: "png")
- `window_seconds`: Length of the time window (in seconds) used to search Sentinel images before the current simulation timestamp (default: 864000, i.e. 10 days)


**Response Example:**
If `return_type="png"` an image file is returned as the response, while if `return_type="array"` base64-encoded raw array bytes are returned. Also, the following metadata are returned:
```bash
{
  'image_available': True, 
  'source': 'sentinel-2a', 
  'spectral_bands': ['red', 'green', 'blue'], 
  'footprint': [-31.744769220901965, 67.84555724102906, -31.62541380860759, 67.890523321325],'size_km': 5.0, 
  'cloud_cover': 86.716813, 
  'datetime': '2026-03-16T13:53:37Z', 
  'satellite_position': [-31.685091514754777, 67.86804028117703, 800.0824433233049],
  'timestamp': '2026-03-17T14:03:19Z'
}
```
`image_available` is False when a Sentinel image for the current location does not exist (usually over the ocean or near the poles), or when it's not available in the specified time window.

`source` can be either "sentinel-2a", "sentinel-2b" or "sentinel-2c" depending on which of the three Sentinel satellites captured the image.

`footprint` specifies the ground area included in the image in the format [lon_min, lat_min, lon_max, lat_max].

`cloud_cover` represents the percentage of the image covered by clouds.

`datetime` indicates the timestamp at which the image was captured by the Sentinel satellite, which in general does not coincide with the timestamp of the simulated satellite. However, the retrieved image is the latest one relative to the simulation timestamp.

### GET /data/current/image/mapbox
This endpoint returns an image from the Mapbox dataset for the current satellite position pointing to a specified target location. The bearing (direction) and pitch (angle) are calculated based on the satellite position and the target location. If the elevation angle is smaller than 30° the target location is considered not visible from the satellite. More information about Mapbox images can be found in the [Datasets Section](#datasets)

**Query Parameters:**
- `lon`: Longitude of the target location (default: current satellite longitude)
- `lat`: Latitude of the target location (default: current satellite latitude)

**Response Example:**
A PNG image file is returned as the response. Also, the following metadata are returned:
```bash
{
  'target_visible': True, 
  'image_available': True, 
  'elevation_degrees': 90.0, 
  'zoom_factor': 13.406814757215615, 
  'bearing': 0.0, 
  'pitch': 0.0, 
  'satellite_position': [-64.45602720609857, -27.086293979486268, 799.2307382513263]
  'timestamp': '2026-03-17T14:30:20Z'
}
```

An API key for Mapbox (free tier available) is required to use this endpoint. Set the environment variable `MAPBOX_ACCESS_TOKEN` to your access token before starting the simulation. More details can be found in the [Datasets Section](#datasets).

### GET /data/image/sentinel
This endpoint returns an image from the Sentinel-2 dataset for a given position and timestamp (not from the current satellite simulation). The metadata returned are the same as the `/data/current/image/sentinel` endpoint except `satellite_position` and `timestamp`.

**Query Parameters:**
- `lon`: Longitude of the requested location (float)
- `lat`: Latitude of the requested location (float)
- `timestamp`: Timestamp of the request (ISO-8601 UTC format) 
- `spectral_bands`: Comma-separated list of spectral bands to include in the image (default: "red","green","blue")
- `size_km`: Size of the image in kilometers (default: 5.0)
- `return_type`: Format of the returned image, either "png" or "array" (default: "png")
- `window_seconds`: Length of the time window (in seconds) used to search Sentinel images before the requested timestamp (default: 864000, i.e. 10 days)

### GET /data/image/mapbox
This endpoint returns an image from the Mapbox dataset for a given satellite position (not from the current satellite simulation) and a given target location. The metadata returned are the same as the `/data/current/image/mapbox` endpoint except `satellite_position` and `timestamp`.

**Query Parameters:**
- `lon_target`: Longitude of the target location (float)
- `lat_target`: Latitude of the target location (float)
- `lon_satellite`: Longitude of the satellite (float)
- `lat_satellite`: Latitude of the satellite (float)
- `alt_satellite`: Altitude of the satellite in kilometers (float)

---
# Datasets
We provide access to two different datasets. This section describes their features and limitations.

## Sentinel-2
[Sentinel-2](https://dataspace.copernicus.eu/data-collections/copernicus-sentinel-data/sentinel-2) is a European multispectral Earth observation mission. The data is freely available in high (3-5 days interval) temporal resolution and medium (10m) spatial resolution.

Multispectral images allow the observation of spectral bands outside the commonly used red-green-blue (RGB) color space. This allows the analysis of features not visible in RGB images. The example below shows a landscape in RGB (left) and false color infrared (right). It is almost impossible to see the river in the RGB image while it is clearly visible in the false color infrared image.

<img src="fig/rgb_and_multispectral_example.png" alt="Sentinel image example" width="800">

### Image Availability
Sentinel-2 consists of three satellites (Sentinel-2A, Sentinel-2B, and Sentinel-2C) that together provide a revisit frequency of about 5 days at the equator, and higher frequency (typically 2–3 days) at mid-latitudes. This means that a new image of the same location, with a similar viewing geometry, is usually available every 2 to 5 days. The mission follows a predefined acquisition plan that determines when the sensor is active and when images are recorded. As a result, not every satellite overpass produces usable imagery, even if the satellite passes over the requested area. In particular, acquisitions over the ocean are often not recorded unless they are close to the coastline. More detailed information about the mission, coverage and acquisition can be found here: [Sentinel-2 Mission](https://sentiwiki.copernicus.eu/web/s2-mission)

### Spectral Bands
Sentinel-2 provides 13 spectral bands spanning from the visible and near infrared to the shortwave infrared. Detailed information about the available bands, how they can be combined to obtain useful insights, and popular remote sensing indices can be found here: [Sentinel-2 Multispectral](https://custom-scripts.sentinel-hub.com/custom-scripts/sentinel/sentinel-2/) 

### Uses and Limitations
Sentinel-2 images should be used for applications where temporal information and multispectral analysis are required, but high resolution is not.

It is important to note that, due to the Sentinel-2 acquisition plan, at a given time the most recent images of nearby areas around a given location may have been captured at different times and possibly by different satellites. Therefore, for some applications additional checks may be required to ensure temporal consistency.

In addition, Sentinel-2 data is divided in tiles. As a result, some requested regions may lie close to tile boundaries, causing images to appear partially cut off or filled with black areas where no data is available. If an image appears completely white, it is most likely due to cloud coverage at the time of acquisition.

The Sentinel-2 API is quite slow, so take it into account when developing your applications.

## Mapbox

The [Mapbox static images API](https://docs.mapbox.com/api/maps/static-images/) is used to generate satellite imagery of a given location, bearing, and pitch. The images have high spatial resolution (10-30cm) but are static, meaning they don't have a timestamp associated and they are not updated regularly. Only RGB images are provided, with no other bands available. The data is cloud-free and available globally in an uniform manner.

To use Mapbox images, go to [mapbox.com](https://www.mapbox.com/) and create an account to get an access token. Set the environment variable `MAPBOX_ACCESS_TOKEN` to your access token.

### Uses and Limitations
Mapbox images should be used for applications that are not time-dependent, where high resolution is necessary and radiometric accuracy is not required. 

Mapbox uses a 2D map on a 3D globe to create perspectives. This looks ok when observing regions where the 2D approximation holds. However, when we observe skyscrapers for instance, we have completely wrong perspectives. Also, Mapbox does not use real images to map the ocean which can lead to unrealistic monocolor images or sometimes even sampling bugs with white regions. Some examples are shown below:

<img src="fig/country_example.png" alt="Image of the country region" width="500">

*Figure 1: Mapbox static image of a nature region.*

<img src="fig/wrong_perspective_example.png" alt="Image of New York City with incorrect perspective" width="500">

*Figure 2: Mapbox static image of New York City with incorrect perspective as the image was taken at a different angle than the current prespective.*



<img src="fig/ocean_example.png" alt="Image of an ocean region" width="500">

*Figure 3: Mapbox static image of an ocean region.*

<img src="fig/bug_example.png" alt="Image with sampling bug in the ocean region" width="500">

*Figure 4: Mapbox static image with sampling bug in the ocean region.*

---
# Test Examples

`scripts/api_test.py` contains test functions for the available API endpoints and can be used as a reference for how to interact with the API. Several tests are provided, each demonstrating a different endpoint.

You can run a specific test by passing an argument to the script:
```bash
python scripts/api_test.py ARG
```

Available arguments:
- `sentinel`: Retrieves and displays a Sentinel-2 RGB image for a predefined location and timestamp
- `sentinel_current`: Retrieves and displays a Sentinel-2 RGB image for the current simulated satellite position and timestamp
- `sentinel_multispectral`: Retrieves and displays Sentinel-2 images using five different band combinations for the current simulated satellite position and timestamp
- `mapbox`: Retrieves and displays a Mapbox image for a predefined location
- `mapbox_current`: Retrieves and displays a Mapbox image for the current simulated satellite's position

If no argument is provided, the script runs the `sentinel_current` test by default.

