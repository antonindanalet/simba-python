import csv
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List

import geopandas
import iteround
import osmnx as ox
import pandas as pd

from simba.mobi.synpop.tourists.utils import fill_missing_values_beds
from simba.mobi.synpop.tourists.utils import removing_new_openings


def load_overnights_in_hotels(dict_path):
    """Load overnights in hotels per commune (to get the number of nights and the list of communes with data)"""
    overnights_in_hotels_raw = pd.read_excel(
        dict_path["persons_in_hotels_file_detailed"],
        sheet_name="Hotellerie V1",
        skiprows=[0, 1, 2],
        skipfooter=6,
    )
    # Delete first (empty) and last (total) column
    overnights_in_hotels_raw = overnights_in_hotels_raw.iloc[:, 1:-3]
    list_of_communes_with_hotels = get_communes_with_three_or_more_hotels(
        overnights_in_hotels_raw,
        dict_path,
    )
    overnights_in_hotels_detailed_per_year = get_overnights_in_hotels_detailed(
        list_of_communes_with_hotels,
        overnights_in_hotels_raw,
        dict_path,
    )

    # Load overnights in hotels per canton (in total)
    overnights_in_hotels_per_canton_raw = pd.read_csv(
        dict_path["persons_in_hotels_file_per_canton"], encoding="ISO-8859-1", sep=","
    )
    overnights_in_hotels_per_canton_raw = overnights_in_hotels_per_canton_raw[
        overnights_in_hotels_per_canton_raw.Canton != "Suisse"
    ]
    get_overnight_in_cantons_only(
        list_of_communes_with_hotels,
        overnights_in_hotels_detailed_per_year,
        overnights_in_hotels_per_canton_raw,
        dict_path,
    )

    load_hotels(list_of_communes_with_hotels, dict_path)


def get_overnight_in_cantons_only(
    list_of_communes_with_hotels,
    overnights_in_hotels_detailed_per_year,
    overnights_in_hotels_per_canton,
    dict_path,
):
    """This function reads an FSO data file for communes with two or less hotels, grouped by canton.
    It then merges it with the file containing overnights for communes with three or more hotels.
    Finally, it makes sure there is no double counting.
    It saves the hotels being in communes with two or less hotels grouped by canton as output as CSV file
        - in the repository /resources/data/output/tourism/,
        - with the name 'overnights_in_hotels_in_cantons_only_[date].csv',
    for visual checks and because it is not available from FSO.
    It returns nothing.
    """
    overnights_in_hotels_per_canton = clean_overnights_in_hotels_per_canton(
        overnights_in_hotels_per_canton
    )
    communes_by_canton = get_communes_with_the_canton_they_belong_to(
        list_of_communes_with_hotels, dict_path
    )

    # Make sure we can group communes by canton when we have the data per commune
    dict_commune2canton = {}
    for commune in list_of_communes_with_hotels:
        canton = communes_by_canton.loc[
            communes_by_canton["Gemeindename"] == commune, "Kanton"
        ]
        if len(canton) == 1:
            canton = canton.iloc[0]
            dict_commune2canton[commune] = canton
        elif (commune == "Klosters") | (commune == "La Punt Chamues-ch"):
            dict_commune2canton[commune] = "GR"
        else:
            raise ValueError("Could not find canton for commune", commune)
    overnights_in_hotels_detailed_per_year.rename(
        columns=dict_commune2canton, inplace=True
    )
    overnights_in_hotels_per_canton = renaming_cantons_from_name2acronyms(
        overnights_in_hotels_per_canton
    )

    countries_per_canton_only = overnights_in_hotels_per_canton.index.difference(
        overnights_in_hotels_detailed_per_year.index
    )
    countries_per_commune_only = (
        overnights_in_hotels_detailed_per_year.index.difference(
            overnights_in_hotels_per_canton.index
        )
    )
    if (len(countries_per_canton_only) != 0) | (len(countries_per_commune_only) != 0):
        raise ValueError(
            "There are countries of origin in the data by canton not in the data by commune:",
            countries_per_canton_only,
            "or there are countries of origin in the data by commune not in the data by canton:",
            countries_per_commune_only,
        )
    # Removing overnights by cantons if they already are in the overnights by commune '''
    overnights_in_hotels_in_cantons_only = (
        overnights_in_hotels_per_canton
        - overnights_in_hotels_detailed_per_year.groupby(
            overnights_in_hotels_detailed_per_year.columns, axis=1
        ).sum()
    )
    overnights_in_hotels_in_cantons_only = (
        overnights_in_hotels_in_cantons_only / 365
    )  # From yearly to daily data

    overnights_in_hotels_in_cantons_only = round_while_keeping_sum(
        overnights_in_hotels_in_cantons_only
    )

    # File used for loading in VISUM with data per canton
    path_to_cached_file = Path(dict_path["cached_tourist_files"])
    overnights_in_hotels_in_cantons_only_file_name = (
        f"overnights_in_hotels_in_cantons_only_{datetime.today():%Y_%m_%d}.csv"
    )
    overnights_in_hotels_in_cantons_only.to_csv(
        path_to_cached_file / overnights_in_hotels_in_cantons_only_file_name,
        encoding="utf-8-sig",
        index_label="country",
    )


def get_communes_with_the_canton_they_belong_to(
    list_of_communes_with_hotels: List[Any], dict_path: Dict
) -> pd.DataFrame:
    # Read a list of all Swiss communes, with the canton they belong to
    communes_by_canton = pd.read_excel(dict_path["communes_by_canton"])
    # Remove columns we don't need in the file from FSO
    communes_by_canton.drop(
        [
            "Datum der Aufnahme",
            "Hist.-Nummer",
            "Bezirksname",
            "BFS Gde-nummer",
            "Bezirks-nummer",
        ],
        axis=1,
        inplace=True,
    )
    nb_communes_with_hotels = len(
        list_of_communes_with_hotels
    )  # Computes number of communes with hotels in hotel data
    communes_by_canton["already_per_commune"] = communes_by_canton["Gemeindename"].isin(
        list_of_communes_with_hotels
    )

    communes_by_canton = manual_corrections_of_commune_names(communes_by_canton)

    nb_detected_communes = communes_by_canton.already_per_commune.sum()
    if nb_detected_communes != nb_communes_with_hotels:
        logging.warning(
            "Problem with detecting communes with hotels in the list of communes by canton: There are %s communes "
            "with 3 or more hotels in Switzerland. In the list, %s were detected.",
            nb_communes_with_hotels,
            nb_detected_communes,
        )
        communes_warn = [
            c
            for c in list_of_communes_with_hotels
            if c not in communes_by_canton["Gemeindename"].unique()
        ]
        logging.warning(communes_warn)
    return communes_by_canton


def manual_corrections_of_commune_names(
    communes_by_canton: pd.DataFrame,
) -> pd.DataFrame:
    # Manual corrections for the 2 communes with two (slightly) different names in the 2 data sources:
    # 'Klosters' & 'La Punt Chamues-ch'
    communes_by_canton.loc[
        communes_by_canton["Gemeindename"] == "La Punt-Chamues-ch",
        "already_per_commune",
    ] = True
    communes_by_canton.loc[
        communes_by_canton["Gemeindename"] == "Klosters-Serneus", "already_per_commune"
    ] = True
    return communes_by_canton


def clean_overnights_in_hotels_per_canton(
    overnights_in_hotels_per_canton: pd.DataFrame,
) -> pd.DataFrame:
    # Update name of origin country: "[country] Nuitées" --> "[country]"
    new_names: list[Any] = []
    for name in overnights_in_hotels_per_canton.columns:
        if name[-7:] == "Nuitées":
            new_names.append(name[:-8])
        else:
            new_names.append(name)
    overnights_in_hotels_per_canton.columns = new_names
    # Removing columns not needed and/or empty by name
    overnights_in_hotels_per_canton = overnights_in_hotels_per_canton.drop(
        [
            "Année",
            "Mois",
            "Pays de provenance - total",
            "Suisse",
            "Pays baltes",
            "Chili",
            "Amérique Centrale, Caraïbes",
            "Australie, N.Zélande, Océanie",
            "Pays du Golfe",
            "Serbie et Monténégro",
        ],
        axis=1,
    )
    overnights_in_hotels_per_canton = overnights_in_hotels_per_canton.transpose()
    overnights_in_hotels_per_canton.columns = overnights_in_hotels_per_canton.iloc[0]
    overnights_in_hotels_per_canton.drop(
        overnights_in_hotels_per_canton.index[0], inplace=True
    )
    return overnights_in_hotels_per_canton


def renaming_cantons_from_name2acronyms(
    overnights_in_hotels_per_canton: pd.DataFrame,
) -> pd.DataFrame:
    # Renaming canton by acronyms (e.g., GR) and not by full name ('Grisons')
    dict_canton2canton_acronym = {
        "Zürich": "ZH",
        "Luzern": "LU",
        "Bern / Berne": "BE",
        "Uri": "UR",
        "Schwyz": "SZ",
        "Obwalden": "OW",
        "Nidwalden": "NW",
        "Glarus": "GL",
        "Zug": "ZG",
        "Fribourg / Freiburg": "FR",
        "Solothurn": "SO",
        "Basel-Stadt": "BS",
        "Basel-Landschaft": "BL",
        "Schaffhausen": "SH",
        "Appenzell Ausserrhoden": "AR",
        "Appenzell Innerrhoden": "AI",
        "St. Gallen": "SG",
        "Graubünden / Grigioni / Grischun": "GR",
        "Aargau": "AG",
        "Thurgau": "TG",
        "Ticino": "TI",
        "Vaud": "VD",
        "Valais / Wallis": "VS",
        "Neuchâtel": "NE",
        "Genève": "GE",
        "Jura": "JU",
    }
    overnights_in_hotels_per_canton.rename(
        columns=dict_canton2canton_acronym, inplace=True
    )
    return overnights_in_hotels_per_canton


def round_while_keeping_sum(overnights_in_hotels_detailed):
    """Round the numbers while keeping the total sum of tourists. Inspired by
    https://stackoverflow.com/questions/74374334/python-how-can-i-round-each-value-in-a-two-dimensional-pandas-dataframe-to-n-de
    """
    # Convert the 2D DataFrame into a 1D DataFrame for compatibility with iteround.saferound()
    rounded_overnights_in_hotels = overnights_in_hotels_detailed.stack().to_frame().T
    rounded_overnights_in_hotels.iloc[0] = iteround.saferound(
        rounded_overnights_in_hotels.iloc[0], places=0
    )
    # Convert from 1D DataFrame back to 2D DataFrame
    rounded_overnights_in_hotels = rounded_overnights_in_hotels.T.unstack()
    # Drop the superfluous extra index header created by .unstack()
    rounded_overnights_in_hotels.columns = (
        rounded_overnights_in_hotels.columns.droplevel()
    )
    return rounded_overnights_in_hotels


def load_hotels(list_of_communes_with_hotels, dict_path):
    """
    Code for reading the data from Openstreetmap as of today. It saves different files in resources/data/output/tourism:
     1. hotels_[date].csv contains the raw data from OSM (but only a limited set of parameters, OSM contains much more)
     2. hotels_[date]_with_id_zones_without_duplicates.csv
         - removes duplicates,
         - imputes the number of rooms and beds, and
         - contains the NPVM zone ID
    The first file is saved to keep OSM raw data. The process of getting these data is long.
    The second file is then used for loading in VISUM.
    The code collects the categories 'hotel', 'motel' and 'guest_house' from Openstreetmap.
    This information about the hotel category is kept in the column 'hotel_type'.
    If there are no accommodation in the commune, a row is added, with the coordinates of the center of the commune.
    These artificially added rows have an empty 'hotel_type'.
    Hotels not in the list of communes with 3+ hotels are also collected and added in the list.
    """
    path_to_cached_file = Path(dict_path["cached_tourist_files"])

    # Get data from OSM
    load_hotels_from_osm(list_of_communes_with_hotels, path_to_cached_file)
    load_hotels_from_cached_file(path_to_cached_file)


def load_hotels_from_osm(list_of_communes_with_hotels, path_to_cached_file):
    print("Loading hotels from OSM...")
    # Define an empty dataframe to be filled by OSM data of each commune
    list_of_columns = [
        "addr:housenumber",
        "addr:street",
        "name",
        "geometry",
        "stars",
        "beds",
        "rooms",
        "osmid",
        "commune",
        "capacity:persons",
        "capacity:beds",
        "capacity:rooms",
    ]
    hotels = geopandas.GeoDataFrame(columns=list_of_columns, geometry="geometry")
    hotels = get_from_osm_by_commune(
        hotels, list_of_communes_with_hotels, list_of_columns
    )
    hotels = get_from_osm_by_canton(hotels, list_of_columns)

    # Set CRS and replace polygons by point
    hotels.crs = "epsg:4326"
    hotels["geometry"] = hotels["geometry"].to_crs(crs=2056)
    hotels["geometry"] = hotels["geometry"].centroid
    hotels["xcoord"] = hotels.geometry.apply(lambda p: p.x)
    hotels["ycoord"] = hotels.geometry.apply(lambda p: p.y)
    csv_file_name = f"hotels_{datetime.today():%Y_%m_%d}.csv"
    hotels.drop("geometry", axis=1).to_csv(
        path_to_cached_file / csv_file_name,
        index=False,
        encoding="utf-8-sig",
        quoting=csv.QUOTE_ALL,
    )


def get_from_osm_by_canton(hotels: pd.DataFrame, list_of_columns: List) -> pd.DataFrame:
    # Get data from OSM for each canton
    for canton in [
        "AG",
        "AI",
        "AR",
        "BE",
        "BL",
        "BS",
        "FR",
        "GE",
        "GL",
        "GR",
        "JU",
        "LU",
        "NE",
        "NW",
        "OW",
        "SG",
        "SH",
        "SO",
        "SZ",
        "TG",
        "TI",
        "UR",
        "VD",
        "VS",
        "ZG",
        "ZH",
    ]:
        print(canton)
        request_dict = {"state": canton, "country": "Switzerland", "countrycodes": "ch"}
        request = ox.geocode_to_gdf(request_dict)
        boundary_polygon = request["geometry"][0]
        # Get OSM data for "hotels", "guest houses" and "motels"
        hotels_per_canton = ox.geometries_from_polygon(
            boundary_polygon, tags={"tourism": "hotel"}
        )
        motels_per_canton = ox.geometries_from_polygon(
            boundary_polygon, tags={"tourism": "motel"}
        )
        guesthouses_per_canton = ox.geometries_from_polygon(
            boundary_polygon, tags={"tourism": "guest_house"}
        )
        if (
            (len(hotels_per_canton) > 0)
            | (len(motels_per_canton) > 0)
            | (len(guesthouses_per_canton) > 0)
        ):
            if len(hotels_per_canton) > 0:
                hotels = append_hotels(
                    hotels,
                    hotels_per_canton,
                    commune_with_hotels="",
                    list_of_columns=list_of_columns,
                    hotel_type="hotel",
                    canton=canton,
                )
            if len(motels_per_canton) > 0:
                hotels = append_hotels(
                    hotels,
                    motels_per_canton,
                    commune_with_hotels="",
                    list_of_columns=list_of_columns,
                    hotel_type="motel",
                    canton=canton,
                )
            if len(guesthouses_per_canton) > 0:
                hotels = append_hotels(
                    hotels,
                    guesthouses_per_canton,
                    commune_with_hotels="",
                    list_of_columns=list_of_columns,
                    hotel_type="guesthouses",
                    canton=canton,
                )
    return hotels


def get_from_osm_by_commune(
    hotels: pd.DataFrame, list_of_communes_with_hotels: List, list_of_columns: List[str]
) -> pd.DataFrame:
    # Get data from OSM for each commune
    print("By commune...")
    for commune_with_hotels in list_of_communes_with_hotels:
        print(commune_with_hotels)
        # Specifying "city" in the request to avoid looking for hotels in the district or canton of the same name
        request_dict = {
            "city": commune_with_hotels,
            "country": "Switzerland",
            "countrycodes": "ch",
        }
        request = ox.geocode_to_gdf(request_dict)
        boundary_polygon = request["geometry"][0]
        # Get OSM data for "hotels", "guest houses" and "motels"
        hotels_per_commune = ox.features_from_polygon(
            boundary_polygon, tags={"tourism": "hotel"}
        )
        motels_per_commune = ox.features_from_polygon(
            boundary_polygon, tags={"tourism": "motel"}
        )
        guesthouses_per_commune = ox.features_from_polygon(
            boundary_polygon, tags={"tourism": "guest_house"}
        )
        if (
            (len(hotels_per_commune) > 0)
            | (len(motels_per_commune) > 0)
            | (len(guesthouses_per_commune) > 0)
        ):
            if len(hotels_per_commune) > 0:
                hotels = append_hotels(
                    hotels,
                    hotels_per_commune,
                    commune_with_hotels,
                    list_of_columns,
                    hotel_type="hotel",
                )
            if len(motels_per_commune) > 0:
                hotels = append_hotels(
                    hotels,
                    motels_per_commune,
                    commune_with_hotels,
                    list_of_columns,
                    hotel_type="motel",
                )
            if len(guesthouses_per_commune) > 0:
                hotels = append_hotels(
                    hotels,
                    guesthouses_per_commune,
                    commune_with_hotels,
                    list_of_columns,
                    hotel_type="guesthouses",
                )
        else:
            # The center of the village is defined as a "hotel", in order to distribute the tourists in these communes
            new_row = {
                "commune": commune_with_hotels,
                "geometry": boundary_polygon,
                "name": "Center of " + commune_with_hotels,
            }
            hotels = hotels.append(new_row, ignore_index=True)
    return hotels


def append_hotels(
    hotels,
    hotels_per_commune,
    commune_with_hotels,
    list_of_columns,
    hotel_type,
    canton="",
):
    # Select the correct columns
    hotels_per_commune = hotels_per_commune[
        hotels_per_commune.columns.intersection(set(list_of_columns))
    ]
    # Removing hotels that opened in 2020 or later
    hotels_per_commune = removing_new_openings(hotels_per_commune)

    hotels_per_commune = hotels_per_commune.reset_index()
    hotels_per_commune = hotels_per_commune.drop(
        "element_type", axis=1
    )  # Is "node" or "way", internal OSM info

    hotels_per_commune["commune"] = commune_with_hotels
    hotels_per_commune["canton"] = canton
    hotels_per_commune["hotel_type"] = hotel_type

    # Add the hotels in the list of hotels without generating duplicates
    # (duplicates are generated when adding hotels per canton after adding hotels per commune with 3+ hotels)
    if len(hotels) > 0:
        existing_hotels_id = hotels.loc[:, "osmid"]
        new_hotels_id = hotels_per_commune.loc[:, "osmid"]
        take_rows = list(set(new_hotels_id) - set(existing_hotels_id))
        take_rows = [i in take_rows for i in new_hotels_id]
        hotels = pd.concat([hotels, hotels_per_commune.loc[take_rows, :]])
    else:
        hotels = pd.concat([hotels, hotels_per_commune])
    return hotels


def load_hotels_from_cached_file(path_to_cached_file):
    """Loads the cached file"""
    file_name = "hotels_2023_05_04.csv"
    hotels = pd.read_csv(path_to_cached_file / file_name)

    # Manual corrections for double entries:

    # One hotel is on two communes...
    hotels.drop(
        hotels.loc[
            (hotels.commune == "Lauterbrunnen") & (hotels.osmid == 230448945)
        ].index,
        inplace=True,
    )
    # Another hotel is on two communes...
    hotels.drop(
        hotels.loc[(hotels.commune == "Locarno") & (hotels.osmid == 419088729)].index,
        inplace=True,
    )
    # The communes Hemberg and Neckertal have merged in 2023
    hotels.drop(
        hotels.loc[(hotels.commune == "Neckertal") & (hotels.osmid == 177884755)].index,
        inplace=True,
    )
    hotels.drop(
        hotels.loc[(hotels.commune == "Neckertal") & (hotels.osmid == 177886555)].index,
        inplace=True,
    )
    hotels.drop(
        hotels.loc[
            (hotels.commune == "Neckertal") & (hotels.osmid == 1074541630)
        ].index,
        inplace=True,
    )

    # Checking that there are no double entries in the data
    ids = hotels["osmid"]
    if (
        len(hotels.loc[(ids.isin(ids[ids.duplicated()])) & (~hotels.osmid.isnull()), :])
        > 0
    ):
        print(
            len(
                hotels.loc[
                    (ids.isin(ids[ids.duplicated()])) & (~hotels.osmid.isnull()),
                    ["name", "commune", "osmid"],
                ]
            )
        )
        print(
            hotels.loc[
                (ids.isin(ids[ids.duplicated()])) & (~hotels.osmid.isnull()),
                ["name", "commune", "osmid"],
            ].sort_values("osmid")
        )
        raise ValueError("Duplicates in the hotel list!")
    # Manual corrections
    hotels.drop(
        hotels[hotels.osmid == 4927078763].index, inplace=True
    )  # Hotel does not exist anymore. Nb beds wrong.
    hotels = fill_missing_values_beds(hotels)

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
    if isinstance(hotels, pd.DataFrame):
        hotels = geopandas.GeoDataFrame(
            hotels,
            geometry=geopandas.points_from_xy(x=hotels.xcoord, y=hotels.ycoord),
            crs=2056,
        )
    number_of_observations = len(hotels)
    hotels = hotels.sjoin(zones_gdf, how="left")
    hotels.drop("index_right", axis=1, inplace=True)
    number_of_observations_after_join = len(hotels)
    if number_of_observations != number_of_observations_after_join:
        raise ValueError("sjoin added some observations!")
    # Manual correction for Hotel "Franco-Suisse", Rue de la Frontiere, a few centimeters out of Switzerland...
    hotels.loc[hotels.osmid == 102786964, "zone_id"] = 572701001
    # Check if there are other NA values
    if hotels.zone_id.isnull().values.any():
        print(hotels.loc[hotels.zone_id.isnull(), "osmid"])
        raise ValueError("There are hotels with NA values for the traffic zones!")

    new_csv_file_name = (
        f"hotels_{datetime.today():%Y_%m_%d}_with_id_zones_without_duplicates.csv"
    )
    hotels.to_csv(
        path_to_cached_file / new_csv_file_name,
        index=False,
        encoding="utf-8-sig",
        sep=";",
    )


def get_overnights_in_hotels_detailed(
    list_of_communes_with_hotels, overnights_in_hotels_detailed, dict_path
):
    """This function reads an FSO data files containing overnights for communes with three or more hotels.
    It saves the hotels being in communes with three or more hotels as output as CSV file
        - in the repository /resources/data/output/tourism/,
        - with the name 'overnights_in_hotels_detailed_[date].csv',
    for visual checks and to be used for loading in VISUM.
    It returns the same dataframe with the overnights per commune.
    """
    # Removes arrivals, keeps overnights
    overnights_in_hotels_detailed.drop(
        list_of_communes_with_hotels, axis=1, inplace=True
    )
    overnights_in_hotels_detailed = overnights_in_hotels_detailed.iloc[
        1:, :
    ]  # First rows of data contains header
    overnights_in_hotels_detailed = overnights_in_hotels_detailed.rename(
        columns={2019: "country"}
    )
    overnights_in_hotels_detailed.set_index(
        overnights_in_hotels_detailed["country"], inplace=True
    )
    overnights_in_hotels_detailed.drop("country", axis=1, inplace=True)
    overnights_in_hotels_detailed.drop("Suisse", inplace=True)
    overnights_in_hotels_detailed.columns = list_of_communes_with_hotels
    # Grouping "Iran" with "West Asia" so that it is coherent with the data by cantons
    overnights_in_hotels_detailed.fillna(0, inplace=True)
    overnights_in_hotels_detailed.loc["Autres Asie de l'Ouest"] += (
        overnights_in_hotels_detailed.loc["Iran"]
    )
    overnights_in_hotels_detailed.drop("Iran", inplace=True)

    # Keeping the yearly data for comparison with the cantonal data
    overnights_in_hotels_detailed_per_year = overnights_in_hotels_detailed

    overnights_in_hotels_detailed = (
        overnights_in_hotels_detailed / 365
    )  # From a yearly table to a daily table

    rounded_overnights_in_hotels = round_while_keeping_sum(
        overnights_in_hotels_detailed
    )

    path_to_cached_file = Path(dict_path["cached_tourist_files"])
    # File used for loading in VISUM with data per commune
    overnights_in_hotels_detailed_file_name = (
        f"overnights_in_hotels_detailed_{datetime.today():%Y_%m_%d}.csv"
    )
    rounded_overnights_in_hotels.to_csv(
        path_to_cached_file / overnights_in_hotels_detailed_file_name,
        encoding="utf-8-sig",
    )
    # Returning the file with the overnights per year.
    # It is then used to compute the overnights per canton in the function 'get_overnight_in_cantons_only'
    return overnights_in_hotels_detailed_per_year


def get_communes_with_three_or_more_hotels(overnights_in_hotels_detailed, dict_path):
    """This function reads an FSO data file for communes with three or more hotels
    It saves the list of communes with three or more hotels:
        - in the repository /resources/data/output/tourism/,
        - with the name 'list_of_communes_with_hotels_[date].json'.
    It returns the list of communes.
    """
    list_of_communes_with_hotels = list(overnights_in_hotels_detailed.columns[1::2])

    list_of_communes_with_hotels_file_name = (
        f"list_of_communes_with_hotels_{datetime.today():%Y_%m_%d}.json"
    )
    path_to_cached_file = Path(dict_path["cached_tourist_files"])
    if not os.path.exists(path_to_cached_file):
        os.makedirs(path_to_cached_file)
    with open(
        path_to_cached_file / list_of_communes_with_hotels_file_name,
        "w",
        encoding="utf-8-sig",
    ) as cached_file:
        json.dump(list_of_communes_with_hotels, cached_file, ensure_ascii=False)
    return list_of_communes_with_hotels
