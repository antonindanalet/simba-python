from datetime import datetime
from pathlib import Path

import geopandas
import iteround
import osmnx as ox
import pandas as pd

from simba.mobi.synpop.tourists.utils import fill_missing_values_beds
from simba.mobi.synpop.tourists.utils import removing_new_openings


def load_overnights_in_supplementary_accommodation(dict_path):
    """--- Supplementary accommodation ---"""
    # Get the geodata of the aggregation regions
    major_regions = get_major_regions(dict_path)

    get_overnights_in_holiday_homes(dict_path)
    load_holiday_homes(major_regions, dict_path)

    get_overnights_in_collective_accomodation(dict_path)
    load_collective_accommodation(major_regions, dict_path)

    get_overnights_in_campsites(dict_path)
    load_campsites(major_regions, dict_path)


def get_major_regions(dict_path):
    major_regions = geopandas.read_file(dict_path["major_regions_shape_file"])
    major_regions = major_regions.rename(columns={"ID1": "name"})
    major_regions.drop(["ID0", "ID2", "ID3"], axis=1, inplace=True)
    major_regions["name"] = major_regions["name"].map(
        {
            "R": "Région lémanique",
            "Espace Mittelland": "Espace Mittelland",
            "Nordwestschweiz": "Suisse du Nord-Ouest",
            "Z": "Zürich",
            "Ostschweiz": "Suisse orientale",
            "Zentralschweiz": "Zentralschweiz",
            "Ticino": "Tessin",
        }
    )
    major_regions.to_crs(crs="epsg:4326", inplace=True)
    return major_regions


def get_overnights_in_holiday_homes(dict_path):
    overnights_in_holiday_homes = pd.read_excel(
        dict_path["overnights_in_holiday_homes_file"],
        sheet_name="2019",
        skiprows=[0, 1, 2, 3, 4],
        skipfooter=21,
    )
    # Keeping only name of region (column 0) and overnight by foreigners (column 7)
    overnights_in_holiday_homes = overnights_in_holiday_homes.iloc[:, [0, 7]]
    overnights_in_holiday_homes.columns = ["region", "overnights"]
    overnights_in_holiday_homes["overnights"] = (
        overnights_in_holiday_homes["overnights"] / 365.0
    )  # Yearly to daily
    overnights_in_holiday_homes["overnights"] = iteround.saferound(
        overnights_in_holiday_homes["overnights"], places=0
    )
    # File used in mobiconnect with data per major region
    overnights_in_holiday_homes_file_name = (
        f"overnights_in_holiday_homes_{datetime.today():%Y_%m_%d}.csv"
    )
    path_to_cached_file = Path(dict_path["cached_tourist_files"])
    overnights_in_holiday_homes.to_csv(
        path_to_cached_file / overnights_in_holiday_homes_file_name,
        encoding="utf-8-sig",
        index=False,
    )


def load_holiday_homes(major_regions, dict_path):
    path_to_cached_file = Path(dict_path["cached_tourist_files"])
    load_holiday_homes_from_osm(major_regions, path_to_cached_file)
    load_holiday_homes_from_cached_file(path_to_cached_file)


def load_holiday_homes_from_osm(major_regions, path_to_cached_file):
    """Get data from OSM"""
    # Define an empty dataframe to be filled by OSM data of each major region
    list_of_columns = [
        "addr:housenumber",
        "addr:street",
        "name",
        "geometry",
        "beds",
        "rooms",
        "osmid",
        "addr:city",
        "capacity:persons",
        "stars",
        "capacity",
        "number_of_apartments",
    ]
    holiday_homes = geopandas.GeoDataFrame(columns=list_of_columns, geometry="geometry")

    # Get data from OSM for each commune
    for index in major_regions.index:
        region_name = major_regions.loc[index, "name"]
        boundary_polygon = major_regions.loc[index, "geometry"]
        print(region_name)

        # Get OSM data for "chalets" and "apartments"
        chalet_per_region = ox.geometries_from_polygon(
            boundary_polygon, tags={"tourism": "chalet"}
        )
        apartment_per_region = ox.geometries_from_polygon(
            boundary_polygon, tags={"tourism": "apartment"}
        )
        if (len(chalet_per_region) > 0) | (len(apartment_per_region) > 0):
            if len(chalet_per_region) > 0:
                holiday_homes = append_holiday_homes(
                    holiday_homes,
                    chalet_per_region,
                    list_of_columns,
                    holiday_homes_type="chalet",
                    region=region_name,
                )
            if len(apartment_per_region) > 0:
                holiday_homes = append_holiday_homes(
                    holiday_homes,
                    apartment_per_region,
                    list_of_columns,
                    holiday_homes_type="apartment",
                    region=region_name,
                )
        else:
            # The center of the village is defined as a "hotel", in order to distribute the tourists in these communes
            new_row = {
                "region": region_name,
                "geometry": boundary_polygon,
                "name": "Center of " + region_name,
            }
            holiday_homes = holiday_homes.append(new_row, ignore_index=True)
    # Set CRS and replace polygons by point
    holiday_homes.crs = "epsg:4326"
    holiday_homes["geometry"] = holiday_homes["geometry"].to_crs(crs=2056)
    holiday_homes["geometry"] = holiday_homes["geometry"].centroid
    holiday_homes["xcoord"] = holiday_homes.geometry.apply(lambda p: p.x)
    holiday_homes["ycoord"] = holiday_homes.geometry.apply(lambda p: p.y)
    csv_file_name = f"holiday_homes_{datetime.today():%Y_%m_%d}.csv"
    holiday_homes.drop("geometry", axis=1).to_csv(
        path_to_cached_file / csv_file_name, index=False, encoding="utf-8-sig"
    )


def load_holiday_homes_from_cached_file(path_to_cached_file):
    """Loads the cached file"""
    file_name = "file_name.csv"
    holiday_homes = pd.read_csv(path_to_cached_file / file_name)

    # Checking that there are no double entries in the data
    ids = holiday_homes["osmid"]
    if (
        len(
            holiday_homes.loc[
                (ids.isin(ids[ids.duplicated()])) & (~holiday_homes.osmid.isnull()), :
            ]
        )
        > 0
    ):
        print(
            len(
                holiday_homes.loc[
                    (ids.isin(ids[ids.duplicated()])) & (~holiday_homes.osmid.isnull()),
                    ["name", "region", "osmid"],
                ]
            )
        )
        print(
            holiday_homes.loc[
                (ids.isin(ids[ids.duplicated()])) & (~holiday_homes.osmid.isnull()),
                ["name", "commune", "osmid"],
            ].sort_values("osmid")
        )
        raise ValueError("Duplicates in the hotel list!")

    # Manual corrections
    holiday_homes.loc[holiday_homes.osmid == 7896984659, "rooms"] = 6.0
    holiday_homes.loc[holiday_homes.osmid == 258561119, "capacity"] = 5.0
    holiday_homes = fill_missing_values_beds(holiday_homes)

    # Add zone ID
    path_to_zones = Path("../resources/geodata/")
    zones_gdf = geopandas.read_file(
        Path(path_to_zones / "zones.gpkg"),
        ignore_fields=[
            "mun_name",
            "agglo_id",
            "agglo_name",
            "amgr_id",
            "amgr_name",
            "amr_id",
            "amr_name",
            "msr_id",
            "msr_name",
            "mun_id",
            "sl3_id",
            "sl3_name",
            "kt_id",
            "kt_name",
        ],
    )
    zones_gdf.to_crs(2056, inplace=True)
    # Transform the dataframe of hotels into a geodataframe if needed
    if isinstance(holiday_homes, pd.DataFrame):
        holiday_homes = geopandas.GeoDataFrame(
            holiday_homes,
            geometry=geopandas.points_from_xy(
                x=holiday_homes.xcoord, y=holiday_homes.ycoord
            ),
            crs=2056,
        )
    number_of_observations = len(holiday_homes)
    holiday_homes = holiday_homes.sjoin(zones_gdf, how="left")
    holiday_homes.drop("index_right", axis=1, inplace=True)
    number_of_observations_after_join = len(holiday_homes)
    if number_of_observations != number_of_observations_after_join:
        raise ValueError("sjoin added some observations!")
    # Check if there are other NA values
    if holiday_homes.zone_id.isnull().values.any():
        print(holiday_homes.loc[holiday_homes.zone_id.isnull(), "osmid"])
        raise ValueError(
            "There are holiday homes with NA values for the traffic zones!"
        )

    new_csv_file_name = f"holiday_homes_{datetime.today():%Y_%m_%d}_with_id_zones_without_duplicates.csv"
    holiday_homes.to_csv(
        path_to_cached_file / new_csv_file_name, index=False, encoding="utf-8-sig"
    )


def get_overnights_in_collective_accomodation(dict_path):
    overnights_in_collective_accommodation = pd.read_excel(
        dict_path["overnights_in_collective_accommodation_file"],
        sheet_name="2019",
        skiprows=[0, 1, 2, 3, 4],
        skipfooter=22,
    )
    # Keeping only name of region (column 0) and overnight by foreigners (column 7)
    overnights_in_collective_accommodation = (
        overnights_in_collective_accommodation.iloc[:, [0, 7]]
    )
    overnights_in_collective_accommodation.columns = ["region", "overnights"]
    overnights_in_collective_accommodation["overnights"] = (
        overnights_in_collective_accommodation["overnights"] / 365.0
    )
    overnights_in_collective_accommodation["overnights"] = iteround.saferound(
        overnights_in_collective_accommodation["overnights"], places=0
    )
    # File used in mobiconnect with data per major region
    overnights_in_collective_accommodation_file_name = (
        f"overnights_in_collective_accommodation_{datetime.today():%Y_%m_%d}.csv"
    )
    path_to_cached_file = Path(dict_path["cached_tourist_files"])
    overnights_in_collective_accommodation.to_csv(
        path_to_cached_file / overnights_in_collective_accommodation_file_name,
        encoding="utf-8-sig",
        index=False,
    )


def load_collective_accommodation(major_regions, dict_path):
    path_to_cached_file = Path(dict_path["cached_tourist_files"])

    # Get data from OSM. Comment if you only want to use the cached files.
    load_collective_accommodation_from_osm(major_regions, path_to_cached_file)
    load_collective_accommodation_from_cached_file(path_to_cached_file)


def load_collective_accommodation_from_cached_file(path_to_cached_file):
    """Loads the cached file"""
    file_name = "collective_accommodation_date.csv"
    collective_accommodation = pd.read_csv(path_to_cached_file / file_name)

    ## Checking that there are no double entries in the data
    # Manual corrections
    collective_accommodation.drop(
        collective_accommodation.loc[
            (collective_accommodation.region == "Espace Mittelland")
            & (collective_accommodation.osmid == 229667105)
        ].index,
        inplace=True,
    )
    ids = collective_accommodation["osmid"]
    if (
        len(
            collective_accommodation.loc[
                (ids.isin(ids[ids.duplicated()]))
                & (~collective_accommodation.osmid.isnull()),
                :,
            ]
        )
        > 0
    ):
        print(
            len(
                collective_accommodation.loc[
                    (ids.isin(ids[ids.duplicated()]))
                    & (~collective_accommodation.osmid.isnull()),
                    ["name", "region", "osmid"],
                ]
            )
        )
        print(
            collective_accommodation.loc[
                (ids.isin(ids[ids.duplicated()]))
                & (~collective_accommodation.osmid.isnull()),
                ["name", "region", "osmid"],
            ].sort_values("osmid")
        )
        raise ValueError("Duplicates in the hotel list!")

    # No manual corrections needed here

    collective_accommodation = fill_missing_values_beds(collective_accommodation)

    # Add zone ID
    path_to_zones = Path("../resources/geodata/")
    zones_gdf = geopandas.read_file(
        Path(path_to_zones / "zones.gpkg"),
        ignore_fields=[
            "mun_name",
            "agglo_id",
            "agglo_name",
            "amgr_id",
            "amgr_name",
            "amr_id",
            "amr_name",
            "msr_id",
            "msr_name",
            "mun_id",
            "sl3_id",
            "sl3_name",
            "kt_id",
            "kt_name",
        ],
    )
    zones_gdf.to_crs(2056, inplace=True)
    # Transform the dataframe of hotels into a geodataframe if needed
    if isinstance(collective_accommodation, pd.DataFrame):
        collective_accommodation = geopandas.GeoDataFrame(
            collective_accommodation,
            geometry=geopandas.points_from_xy(
                x=collective_accommodation.xcoord, y=collective_accommodation.ycoord
            ),
            crs=2056,
        )
    number_of_observations = len(collective_accommodation)
    collective_accommodation = collective_accommodation.sjoin(zones_gdf, how="left")
    collective_accommodation.drop("index_right", axis=1, inplace=True)
    number_of_observations_after_join = len(collective_accommodation)
    if number_of_observations != number_of_observations_after_join:
        raise ValueError("sjoin added some observations!")
    # Manual correction for alpine hut "Rifugio Jean-Antoine Carrel", in Italy
    collective_accommodation.drop(
        collective_accommodation.loc[collective_accommodation.osmid == 254529621].index,
        inplace=True,
    )
    # Rifugio Teodulo in Italy (for a few meters)
    collective_accommodation.drop(
        collective_accommodation.loc[collective_accommodation.osmid == 295875967].index,
        inplace=True,
    )
    # Rifugio Gaspare Oberto e Paolo Maroli in Italy
    collective_accommodation.drop(
        collective_accommodation.loc[
            collective_accommodation.osmid == 9427942453
        ].index,
        inplace=True,
    )
    # Rifugio Capanna Regina Margherita in Italy
    collective_accommodation.drop(
        collective_accommodation.loc[collective_accommodation.osmid == 149862629].index,
        inplace=True,
    )
    # All very close from the border
    collective_accommodation.drop(
        collective_accommodation.loc[
            (collective_accommodation.osmid == 274305272)
            | (collective_accommodation.osmid == 102786915)
            | (collective_accommodation.osmid == 102786983)
            | (collective_accommodation.osmid == 3018567020)
            | (collective_accommodation.osmid == 91766432)
            | (collective_accommodation.osmid == 152050783)
            | (collective_accommodation.osmid == 232443735)
            | (collective_accommodation.osmid == 233835059)
            | (collective_accommodation.osmid == 174466995)
            | (collective_accommodation.osmid == 861837620)
        ].index,
        inplace=True,
    )
    # Check if there are other NA values
    if collective_accommodation.zone_id.isnull().values.any():
        print(
            collective_accommodation.loc[
                collective_accommodation.zone_id.isnull(), "osmid"
            ]
        )
        raise ValueError(
            "There are holiday homes with NA values for the traffic zones!"
        )

    new_csv_file_name = f"collective_accommodation_{datetime.today():%Y_%m_%d}_with_id_zones_without_duplicates.csv"
    collective_accommodation.to_csv(
        path_to_cached_file / new_csv_file_name, index=False, encoding="utf-8-sig"
    )


def load_collective_accommodation_from_osm(major_regions, path_to_cached_file):
    # Define an empty dataframe to be filled by OSM data of each major region
    list_of_columns = [
        "addr:housenumber",
        "addr:street",
        "name",
        "geometry",
        "beds",
        "rooms",
        "osmid",
        "addr:city",
        "capacity:persons",
        "stars",
        "capacity",
    ]
    collective_accommodation = geopandas.GeoDataFrame(
        columns=list_of_columns, geometry="geometry"
    )

    # Get data from OSM for each commune
    for index in major_regions.index:
        region_name = major_regions.loc[index, "name"]
        boundary_polygon = major_regions.loc[index, "geometry"]
        print(region_name)

        # Get OSM data for "hostels", "alpine_huts" and "wilderness_huts"
        hostel_per_region = ox.geometries_from_polygon(
            boundary_polygon, tags={"tourism": "hostel"}
        )
        alpine_hut_per_region = ox.geometries_from_polygon(
            boundary_polygon, tags={"tourism": "alpine_hut"}
        )
        wilderness_hut_per_region = ox.geometries_from_polygon(
            boundary_polygon, tags={"tourism": "wilderness_hut"}
        )
        if (
            (len(hostel_per_region) > 0)
            | (len(alpine_hut_per_region) > 0)
            | (len(wilderness_hut_per_region) > 0)
        ):
            if len(hostel_per_region) > 0:
                collective_accommodation = append_holiday_homes(
                    collective_accommodation,
                    hostel_per_region,
                    list_of_columns,
                    holiday_homes_type="hostel",
                    region=region_name,
                )
            if len(alpine_hut_per_region) > 0:
                collective_accommodation = append_holiday_homes(
                    collective_accommodation,
                    alpine_hut_per_region,
                    list_of_columns,
                    holiday_homes_type="alpine_hut",
                    region=region_name,
                )
            if len(wilderness_hut_per_region) > 0:
                collective_accommodation = append_holiday_homes(
                    collective_accommodation,
                    wilderness_hut_per_region,
                    list_of_columns,
                    holiday_homes_type="wilderness_hut",
                    region=region_name,
                )
        else:
            # The center of the region is defined as a "hotel", in order to distribute the tourists in these communes
            new_row = {
                "region": region_name,
                "geometry": boundary_polygon,
                "name": "Center of " + region_name,
            }
            collective_accommodation = collective_accommodation.append(
                new_row, ignore_index=True
            )
    # Set CRS and replace polygons by point
    collective_accommodation.crs = "epsg:4326"
    collective_accommodation["geometry"] = collective_accommodation["geometry"].to_crs(
        crs=2056
    )
    collective_accommodation["geometry"] = collective_accommodation["geometry"].centroid
    collective_accommodation["xcoord"] = collective_accommodation.geometry.apply(
        lambda p: p.x
    )
    collective_accommodation["ycoord"] = collective_accommodation.geometry.apply(
        lambda p: p.y
    )
    csv_file_name = f"collective_accommodation_{datetime.today():%Y_%m_%d}.csv"
    collective_accommodation.drop("geometry", axis=1).to_csv(
        path_to_cached_file / csv_file_name, index=False, encoding="utf-8-sig"
    )


def get_overnights_in_campsites(dict_path):
    overnights_in_campsites = pd.read_excel(
        dict_path["overnights_in_campsites_file"],
        sheet_name="2019",
        skiprows=[0, 1, 2, 3, 4],
        skipfooter=4,
    )
    # Keeping only name of region (column 0) and overnight by foreigners (column 7)
    overnights_in_campsites = overnights_in_campsites.iloc[:, [0, 7]]
    overnights_in_campsites.columns = ["region", "overnights"]
    overnights_in_campsites["overnights"] = (
        overnights_in_campsites["overnights"] / 365.0
    )  # From yearly to daily table
    overnights_in_campsites["overnights"] = iteround.saferound(
        overnights_in_campsites["overnights"], places=0
    )
    # File used in mobiconnect with data per major region
    overnights_in_campsites_file_name = (
        f"overnights_in_campsites_{datetime.today():%Y_%m_%d}.csv"
    )
    path_to_cached_file = Path(dict_path["cached_tourist_files"])
    overnights_in_campsites.to_csv(
        path_to_cached_file / overnights_in_campsites_file_name,
        encoding="utf-8-sig",
        index=False,
    )


def load_campsites(major_regions, dict_path):
    path_to_cached_file = Path(dict_path["cached_tourist_files"])

    # Get data from OSM
    load_campsites_from_osm(major_regions, path_to_cached_file)
    load_campsites_from_cached_file(path_to_cached_file)


def load_campsites_from_osm(major_regions, path_to_cached_file):
    # Define an empty dataframe to be filled by OSM data of each major region
    list_of_columns = [
        "addr:housenumber",
        "addr:street",
        "name",
        "geometry",
        "osmid",
        "addr:city",
        "capacity:persons",
        "stars",
        "capacity",
        "capacity:caravans",
        "opening_date",
        "capacity:pitches",
        "capacity:tents",
    ]
    campsites = geopandas.GeoDataFrame(columns=list_of_columns, geometry="geometry")

    # Get data from OSM for each commune
    for index in major_regions.index:
        region_name = major_regions.loc[index, "name"]
        boundary_polygon = major_regions.loc[index, "geometry"]
        print(region_name)

        # Get OSM data for "hostels", "alpine_huts" and "wilderness_huts"
        campsites_per_region = ox.geometries_from_polygon(
            boundary_polygon, tags={"tourism": "camp_site"}
        )
        if len(campsites_per_region) > 0:
            campsites = append_holiday_homes(
                campsites,
                campsites_per_region,
                list_of_columns,
                holiday_homes_type="camp_site",
                region=region_name,
            )
        else:
            # The center of the region is defined as a "hotel", in order to distribute the tourists in these communes
            new_row = {
                "region": region_name,
                "geometry": boundary_polygon,
                "name": "Center of " + region_name,
            }
            campsites = campsites.append(new_row, ignore_index=True)
    # Set CRS and replace polygons by point
    campsites.crs = "epsg:4326"
    campsites["geometry"] = campsites["geometry"].to_crs(crs=2056)
    campsites["geometry"] = campsites["geometry"].centroid
    campsites["xcoord"] = campsites.geometry.apply(lambda p: p.x)
    campsites["ycoord"] = campsites.geometry.apply(lambda p: p.y)
    csv_file_name = f"campsites_{datetime.today():%Y_%m_%d}.csv"
    campsites.drop("geometry", axis=1).to_csv(
        path_to_cached_file / csv_file_name, index=False, encoding="utf-8-sig"
    )


def load_campsites_from_cached_file(path_to_cached_file):
    # ''' Loads the cached file '''
    file_name = "campsites_2023_03_28.csv"
    campsites = pd.read_csv(path_to_cached_file / file_name)

    ### Checking that there are no double entries in the data
    # Manual corrections
    campsites.drop(
        campsites.loc[
            (campsites.region == "Suisse du Nord-Ouest")
            & (campsites.osmid == 402952895)
        ].index,
        inplace=True,
    )
    ids = campsites["osmid"]
    if (
        len(
            campsites.loc[
                (ids.isin(ids[ids.duplicated()])) & (~campsites.osmid.isnull()), :
            ]
        )
        > 0
    ):
        print(
            len(
                campsites.loc[
                    (ids.isin(ids[ids.duplicated()])) & (~campsites.osmid.isnull()),
                    ["name", "region", "osmid"],
                ]
            )
        )
        print(
            campsites.loc[
                (ids.isin(ids[ids.duplicated()])) & (~campsites.osmid.isnull()),
                ["name", "region", "osmid"],
            ].sort_values("osmid")
        )
        raise ValueError("Duplicates in the campsite list!")

    campsites = fill_missing_values_beds(campsites)

    # Add zone ID
    path_to_zones = Path("../resources/geodata/")
    zones_gdf = geopandas.read_file(
        Path(path_to_zones / "zones.gpkg"),
        ignore_fields=[
            "mun_name",
            "agglo_id",
            "agglo_name",
            "amgr_id",
            "amgr_name",
            "amr_id",
            "amr_name",
            "msr_id",
            "msr_name",
            "mun_id",
            "sl3_id",
            "sl3_name",
            "kt_id",
            "kt_name",
        ],
    )
    zones_gdf.to_crs(2056, inplace=True)
    # Transform the dataframe of hotels into a geodataframe if needed
    if isinstance(campsites, pd.DataFrame):
        campsites = geopandas.GeoDataFrame(
            campsites,
            geometry=geopandas.points_from_xy(x=campsites.xcoord, y=campsites.ycoord),
            crs=2056,
        )
    number_of_observations = len(campsites)
    campsites = campsites.sjoin(zones_gdf, how="left")
    campsites.drop("index_right", axis=1, inplace=True)
    number_of_observations_after_join = len(campsites)
    if number_of_observations != number_of_observations_after_join:
        raise ValueError("sjoin added some observations!")
    # Manual correction for Camping Municipal La Forge, in France
    campsites.drop(campsites.loc[campsites.osmid == 715384952].index, inplace=True)
    # Laag, camping of the Kanu-Club Schaffhausen, aber in Germany
    campsites.drop(campsites.loc[campsites.osmid == 166388438].index, inplace=True)
    # Check if there are other NA values
    if campsites.zone_id.isnull().values.any():
        print(campsites.loc[campsites.zone_id.isnull(), ["osmid", "name"]])
        raise ValueError("There are campsites with NA values for the traffic zones!")

    new_csv_file_name = (
        f"campsites_{datetime.today():%Y_%m_%d}_with_id_zones_without_duplicates.csv"
    )
    campsites.to_csv(
        path_to_cached_file / new_csv_file_name, index=False, encoding="utf-8-sig"
    )


def append_holiday_homes(
    holiday_homes, accommodation_per_region, list_of_columns, holiday_homes_type, region
):
    # Select the correct columns
    accommodation_per_region = accommodation_per_region[
        accommodation_per_region.columns.intersection(set(list_of_columns))
    ]
    # Removing holiday homes that opened in 2020 or later
    accommodation_per_region = removing_new_openings(accommodation_per_region)

    accommodation_per_region = accommodation_per_region.reset_index()
    if (
        "element_type" in accommodation_per_region.columns
    ):  # Is "node" or "way", internal OSM info, not needed
        accommodation_per_region = accommodation_per_region.drop("element_type", axis=1)

    accommodation_per_region["region"] = region
    accommodation_per_region["holiday_homes_type"] = holiday_homes_type

    holiday_homes = pd.concat([holiday_homes, accommodation_per_region])

    return holiday_homes
