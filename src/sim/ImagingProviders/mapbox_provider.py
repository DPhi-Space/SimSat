from math import acos, radians, sin, cos, sqrt, atan2, log2
import os
import requests

import numpy as np
EARTH_RADIUS_KM = 6371.0
EPS = 1e-12

class MapboxlProvider:

    def __init__(self):
        self.api_token = os.environ.get("MAPBOX_ACCESS_TOKEN")
        if self.api_token is None:
            raise ValueError("MAPBOX_ACCESS_TOKEN environment variable not set")



    def get_target_image(self, sat_lon, sat_lat, sat_alt, target_lon, target_lat):
        print(f"get target input vars: sat_lon={sat_lon}, sat_lat={sat_lat}, sat_alt={sat_alt}, target_lon={target_lon}, target_lat={target_lat}")
        cartesian_sat = self._spherical_to_cartesian(sat_lon, sat_lat,  EARTH_RADIUS_KM + sat_alt)
        cartesian_target = self._spherical_to_cartesian(target_lon, target_lat, EARTH_RADIUS_KM)

        distance = np.linalg.norm(cartesian_sat - cartesian_target)

        # zoom factor
        zoom_factor = 13.92 + log2(560/distance) # empirical choice of factors.

        target_to_sat_vector = cartesian_sat - cartesian_target
        target_to_sat_unit_vector = target_to_sat_vector / np.linalg.norm(target_to_sat_vector)

        target_unit_vector = cartesian_target / np.linalg.norm(cartesian_target)

        # calculate elevation angle: theta = angle between the plane normal vector and the target to satellite vector
        theta = acos(np.clip(np.dot(target_unit_vector, target_to_sat_unit_vector), -1.0, 1.0))
        elevation_degrees = 90 - np.degrees(theta)
        pitch = np.degrees(theta) # mapbox pitch
        target_visible = elevation_degrees >= 30
        
        # calculate bearing
        earth_center_to_south_vector = np.array([0, 0, 1])  # Z-axis points to North Pole
        target_to_sat_vec_projection_to_earth_surface = target_to_sat_unit_vector - np.dot(target_to_sat_unit_vector, target_unit_vector) * target_unit_vector
        target_proj_norm = np.linalg.norm(target_to_sat_vec_projection_to_earth_surface)
        if target_proj_norm < EPS:
            # Near nadir view: bearing is undefined; use a stable default.
            bearing = 0.0
        else:
            target_to_sat_vec_projection_to_earth_surface_unit_vector = target_to_sat_vec_projection_to_earth_surface / target_proj_norm
            south_vec_projection_to_earth_surface = earth_center_to_south_vector - np.dot(earth_center_to_south_vector, target_unit_vector) * target_unit_vector
            south_proj_norm = np.linalg.norm(south_vec_projection_to_earth_surface)
            if south_proj_norm < EPS:
                # Degenerate case close to poles; use the same stable default.
                bearing = 0.0
            else:
                south_vec_projection_to_earth_surface_unit_vector = south_vec_projection_to_earth_surface / south_proj_norm
                bearing = 180 - np.degrees(acos(np.clip(np.dot(south_vec_projection_to_earth_surface_unit_vector, target_to_sat_vec_projection_to_earth_surface_unit_vector), -1.0, 1.0)))
                # determine if bearing should be negative
                bearing_cross = np.cross(south_vec_projection_to_earth_surface_unit_vector, target_to_sat_vec_projection_to_earth_surface_unit_vector)
                if np.dot(bearing_cross, target_unit_vector) < 0:
                    bearing = -bearing
                if bearing < 0:
                    bearing += 360

        # no image can be requested if the target is not visible from this geometry
        if not target_visible:
            return {
                "image": None,
                "metadata": {
                    "target_visible": False,
                    "image_available": False,
                    "elevation_degrees": None,
                    "zoom_factor": None,
                    "bearing": None,
                    "pitch": None
                }
            }
        
        # get image from mapbox
        filename = "test.png"

        url = f"https://api.mapbox.com/styles/v1/mapbox/satellite-v9/static/{target_lon},{target_lat},{zoom_factor},{bearing},{pitch}/1280x1280@2x?access_token={self.api_token}"
        response = requests.get(url)
        metadata = {
            "target_visible": True,
            "image_available": False,
            "elevation_degrees": elevation_degrees,
            "zoom_factor": zoom_factor,
            "bearing": bearing,
            "pitch": pitch
        }
        if response.status_code != 200:
            print(f"Error fetching image: {response.status_code} - {response.text}")
            return {
                "image": None,
                "metadata": metadata
            }

        metadata["image_available"] = True
        return {
            "image": response.content,
            "metadata": metadata
        }

    # --------------------------------------------------------
    # Helper functions
    # --------------------------------------------------------

    def _spherical_to_cartesian(self, lon, lat, radius):
        # Convert degrees to radians
        lon_rad = radians(lon)
        lat_rad = radians(lat)

        x = radius * cos(lat_rad) * cos(lon_rad)
        y = radius * cos(lat_rad) * sin(lon_rad)
        z = radius * sin(lat_rad)

        return np.array([x, y, z])


if __name__ == "__main__":
    provider = MapboxlProvider()
    lausanne = {'lon': 6.6322734, 'lat': 46.5218266}
    lausanne_north = {'lon': 6.6322734, 'lat': 46.5318266}
    paris = {'lon': 2.3522219, 'lat': 48.856614}
    stuttgart = {'lon': 9.1829321, 'lat': 48.7758459}
    p1 = {'lon': 6.6322734-1, 'lat': 46.5218266}

    h = 500  # km

    sat = stuttgart
    target = lausanne

    provider.get_target_image(sat['lon'], sat['lat'], h, target['lon'], target['lat'])

        # def get_target_image(self, sat_lon, sat_lat, sat_alt, target_lon, target_lat):