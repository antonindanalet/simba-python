import json
import random
from typing import List

import numpy
import pandas as pd

from simba.mobi.synpop.tourists.config_distribute_tourists import dict_path
from simba.mobi.synpop.tourists.config_distribute_tourists import FIRST_RESERVED_ID


def distribute_tourists_in_tourist_accommodation():
    """
    This script distributes foreign tourists in tourist accommodation (hotels, supplementary accommodation).
    It generates 2 CSV files that can be loaded in VISUM later: households and persons.
    This function adds IDs to tourists (persons) and hotels (households) in order to import them in VISUM later.
    Some identification numbers are reserved for tourists (Liechtenstein, Grenzgänger, Touristen)
    """
    # Save a file with all tourist accommodation with household ID
    tourist_accommodation = get_tourist_accommodation()

    # Distribute tourists in tourists accommodations
    persons_in_hotels = add_tourists_in_hotels(tourist_accommodation)
    persons_in_other_accommodation = add_tourists_in_supplementary_accommodation(
        tourist_accommodation
    )
    # Save a file with all tourists with person ID
    save_persons(persons_in_hotels, persons_in_other_accommodation)


def get_tourist_accommodation() -> pd.DataFrame:
    """This function adds IDs to tourist accommodations in order to import them in VISUM.
    This file is saved in path_to_output_data_from_simba-python/distribute_tourists_in_tourist_accommodation.
    Some identification numbers are reserved for tourists.
     The OSM ID:
    - allows to get back to the original data from openstreetmap.org,
    - is saved in VISUM as string (because the OSM IDs are sometimes too large for 'int' variables)."""
    hotels = get_hotels()
    hotels["tourist_accommodation_category"] = "hotels"

    all_supplementary_accommodation = pd.DataFrame(
        columns=[
            "addr:housenumber",
            "addr:street",
            "name",
            "osmid",
            "addr:city",
            "capacity:persons",
            "stars",
            "capacity",
            "capacity:caravans",
            "capacity:pitches",
            "capacity:tents",
            "region",
            "holiday_homes_type",
            "xcoord",
            "ycoord",
            "beds",
            "rooms",
            "zone_id",
            "household_id",
        ]
    )
    for type_of_accommodation in [
        "campsites",
        "holiday_homes",
        "collective_accommodation",
    ]:
        df_supplementary_accommodation = pd.read_csv(
            dict_path[type_of_accommodation + "_from_OSM"]
        )
        df_supplementary_accommodation["tourist_accommodation_category"] = (
            type_of_accommodation
        )
        all_supplementary_accommodation = pd.concat(
            [all_supplementary_accommodation, df_supplementary_accommodation]
        )
    tourist_accommodation = pd.concat([hotels, all_supplementary_accommodation])
    # Add ID to tourist accommodation
    tourist_accommodation["household_id"] = range(
        FIRST_RESERVED_ID, FIRST_RESERVED_ID + len(tourist_accommodation)
    )

    # Rename variable "stars" in "hotel_stars" for clarity in MOBi Plans in the general scope
    tourist_accommodation = tourist_accommodation.rename(
        columns={"stars": "hotel_stars"}
    )

    save_households(tourist_accommodation)
    return tourist_accommodation


def save_households(tourist_accommodation: pd.DataFrame):
    path_to_output_files = dict_path["output_files"]
    new_csv_file_name = "households.csv"
    tourist_accommodation.to_csv(
        path_to_output_files / new_csv_file_name, index=False, encoding="utf-8-sig"
    )


def save_persons(
    persons_in_hotels: pd.DataFrame, persons_in_other_accommodation: pd.DataFrame
):
    persons = pd.concat([persons_in_hotels, persons_in_other_accommodation])
    persons["is_swiss"] = False
    persons = add_person_attributes(persons)
    path_to_output_files = dict_path["output_files"]
    new_csv_file_name = "persons.csv"
    persons.to_csv(
        path_to_output_files / new_csv_file_name, index=False, encoding="utf-8-sig"
    )


def get_list_of_communes_with_hotels() -> List:
    with open(
        dict_path["list_of_communes_with_hotels"],
        "r",
        encoding="utf-8-sig",
    ) as f_communes:
        list_of_communes_with_hotels = json.load(f_communes)
    return list_of_communes_with_hotels


def add_tourists_in_hotels(tourist_accommodation: pd.DataFrame) -> pd.DataFrame:
    """This function returns tourists with the ID of a hotel (household ID), distributed both:
     - at the communal level when available and
     - at the cantonal level otherwise.
    Specifically, it uses the list of all hotels, including their number of beds, where they are located and their ID.
    Then, for each commune and each canton:
     - It distributes the tourists by commune into the hotels proportionally to the number of beds, and
     - It adds the household zone ID to which each tourist belongs.
    It takes as input all tourist accommodation, then filtered to keep only hotels.
    """
    # Load overnights in hotels (to get the number of nights as well as the list of communes with data)
    list_of_communes_with_hotels = get_list_of_communes_with_hotels()
    overnights_in_hotels_in_communes = pd.read_csv(
        dict_path["overnights_in_hotels_detailed"]
    )
    overnights_in_hotels_in_cantons = pd.read_csv(
        dict_path["overnights_in_hotels_in_cantons_only"]
    )
    # Get all/only hotels
    hotels = tourist_accommodation.loc[
        tourist_accommodation.tourist_accommodation_category == "hotels", :
    ]
    # Distribute tourists in hotels
    persons = distribute_tourists_in_hotels(
        overnights_in_hotels_in_communes,
        overnights_in_hotels_in_cantons,
        list_of_communes_with_hotels,
        hotels,
    )
    return persons


def distribute_tourists_in_hotels(
    overnights_in_hotels_in_communes: pd.DataFrame,
    overnights_in_hotels_in_cantons: pd.DataFrame,
    list_of_communes_with_hotels: List,
    hotels: pd.DataFrame,
) -> pd.DataFrame:
    list_of_countries = []  # A list of origin countries for each single tourist
    list_of_overnight_hotels = []  # A list of hotel/household ID for each single tourist

    (
        list_of_countries,
        list_of_overnight_hotels,
    ) = distribute_tourists_in_hotels_for_communes(
        list_of_communes_with_hotels,
        overnights_in_hotels_in_communes,
        list_of_countries,
        hotels,
        list_of_overnight_hotels,
    )

    (
        list_of_countries,
        list_of_overnight_hotels,
    ) = distribute_tourists_in_hotels_for_cantons(
        overnights_in_hotels_in_cantons,
        list_of_countries,
        hotels,
        list_of_overnight_hotels,
    )

    dict_persons = {
        "household_id": list_of_overnight_hotels,
        "country_of_origin": list_of_countries,
    }
    persons = pd.DataFrame(dict_persons)
    return persons


def distribute_tourists_in_hotels_for_cantons(
    overnights_in_hotels_in_cantons: pd.DataFrame,
    list_of_countries: List,
    hotels: pd.DataFrame,
    list_of_overnight_hotels: List,
) -> (List, List):
    # Second for each canton
    list_of_cantons_acronym = overnights_in_hotels_in_cantons.columns[1:]
    for canton in list_of_cantons_acronym:
        list_of_countries_in_canton = overnights_in_hotels_in_cantons.loc[
            overnights_in_hotels_in_cantons.index.repeat(
                overnights_in_hotels_in_cantons[canton]
            ),
            "country",
        ].tolist()
        overnights_in_hotels_in_cantons.drop(
            canton, axis=1, inplace=True
        )  # Removing the column with data about the canton
        list_of_countries.extend(
            list_of_countries_in_canton
        )  # Adding the tourist of the canton to the whole list
        number_of_tourists_in_canton = len(list_of_countries_in_canton)
        # Distribute people in hotels of the commune
        if number_of_tourists_in_canton > 0:
            hotels_in_canton = hotels.loc[hotels.canton == canton, :]
            random.seed(2019)
            list_of_overnight_hotels.extend(
                random.choices(
                    population=hotels_in_canton["household_id"].tolist(),
                    weights=hotels_in_canton["beds"],
                    k=number_of_tourists_in_canton,
                )
            )
    return list_of_countries, list_of_overnight_hotels


def distribute_tourists_in_hotels_for_communes(
    list_of_communes_with_hotels: List,
    overnights_in_hotels_in_communes: pd.DataFrame,
    list_of_countries: List,
    hotels: pd.DataFrame,
    list_of_overnight_hotels: List,
) -> (List, List):
    """Exploding the dataframe so that we have one row per person"""
    # First for each commune
    for commune in list_of_communes_with_hotels:
        list_of_countries_in_commune = overnights_in_hotels_in_communes.loc[
            overnights_in_hotels_in_communes.index.repeat(
                overnights_in_hotels_in_communes[commune]
            ),
            "country",
        ].tolist()
        overnights_in_hotels_in_communes.drop(
            commune, axis=1, inplace=True
        )  # Removing the column with data about the commune
        list_of_countries.extend(
            list_of_countries_in_commune
        )  # Adding the tourist of the commune to the whole list
        number_of_tourists_in_commune = len(list_of_countries_in_commune)
        # Distribute people in hotels of the commune
        if number_of_tourists_in_commune > 0:
            hotels_in_commune = hotels.loc[hotels.commune == commune, :]
            random.seed(2019)
            list_of_overnight_hotels.extend(
                random.choices(
                    population=hotels_in_commune["household_id"].tolist(),
                    weights=hotels_in_commune["beds"],
                    k=number_of_tourists_in_commune,
                )
            )
    return list_of_countries, list_of_overnight_hotels


def update_list_of_communes_with_hotels_for_ai_only(
    list_of_communes_with_hotels: List[str],
) -> List[str]:
    list_of_appenzell_commune = [
        "Appenzell",
        "Gonten",
        "Rüte",
        "Schlatt-Haslen",
        "Schwende",
        "Oberegg",
    ]
    list_of_communes_with_hotels = [
        commune
        for commune in list_of_communes_with_hotels
        if commune in list_of_appenzell_commune
    ]
    return list_of_communes_with_hotels


def add_person_attributes(persons: pd.DataFrame) -> pd.DataFrame:
    """Add new persons in VISUM"""
    # Add unique 'No' attribute for Visum
    persons["person_id"] = range(FIRST_RESERVED_ID, FIRST_RESERVED_ID + len(persons))
    persons["current_edu"] = 0
    persons["highest_education"] = 0
    persons["level_of_employment"] = 0
    persons["level_of_employment_cat"] = 0
    persons["current_job_rank"] = 0

    # Randomly add age based on the distribution of the Tourismus Monitor Schweiz
    numpy.random.seed(2023)
    persons["age"] = numpy.random.choice(
        range(18, 100, 5),
        len(persons["person_id"]),
        p=[
            0.030929457494933546,
            0.0971193410775369,
            0.12554980478361738,
            0.11344834203260572,
            0.10159469376562605,
            0.10306493497481213,
            0.10121274384169025,
            0.10185967867462829,
            0.07983600246463862,
            0.06827708178232175,
            0.044943030334914605,
            0.02127205315042922,
            0.008042705403412684,
            0.0022631718454858892,
            0.0001701480855424969,
            0.00014495552848662948,
            0.00027185475931774397,
        ],
    )
    persons["age_cat"] = persons["age"].map(
        {
            18: 2,
            23: 2,
            28: 3,
            33: 3,
            38: 3,
            43: 3,
            48: 4,
            53: 4,
            58: 4,
            63: 4,
            68: 5,
            73: 5,
            78: 6,
            83: 6,
            88: 6,
            93: 6,
            98: 6,
        }
    )

    return persons  # We don't save a CSV here, we still need to add other types of tourism accommodation


def get_hotels() -> pd.DataFrame:
    """This function uses the file generated by mobi/synpop/get_tourists.
    It returns the hotels as households including the OSM ID and the household ID.
    """
    path_to_hotel_file = dict_path["hotels_from_OSM"]
    # Loads the cached file
    hotels = pd.read_csv(path_to_hotel_file)

    list_of_columns_we_keep = [
        "xcoord",  # needed for the import in VISUM
        "ycoord",  # needed for the import in VISUM
        "commune",  # needed for the distribution of tourists living in a specific commune
        "beds",  # needed for weighting how many tourists are going to a specific hotel
        "zone_id",  # needed for the import in VISUM
        "canton",  # needed for the distribution of tourists sleeping in a specific canton
        "osmid",  # optional
        "stars",  # needed for the main mode choice model
    ]
    hotels = hotels.reindex(columns=list_of_columns_we_keep)
    return hotels


def distribute_tourists_in_supplementary_accommodation(
    overnights_in_supplementary_accommodation: pd.DataFrame,
    df_supplementary_accommodation: pd.DataFrame,
    type_of_accommodation: str,
) -> pd.DataFrame:
    number_of_tourists = 0  # A count of tourists, independently of the region
    list_of_overnight_supplementary_accommodation = []
    list_of_regions = overnights_in_supplementary_accommodation.region
    for region in list_of_regions:
        number_of_tourists_in_region = int(
            overnights_in_supplementary_accommodation.loc[
                overnights_in_supplementary_accommodation.region == region, "overnights"
            ].item()
        )
        number_of_tourists += number_of_tourists_in_region  # Adding the tourist of the region to the general count

        # Distribute people in hotels of the commune
        if region not in df_supplementary_accommodation["region"]:
            if region == "Zurich":
                region = "Zürich"
            elif region == "Suisse centrale":
                region = "Zentralschweiz"
        supplementary_accommodation_in_region = df_supplementary_accommodation.loc[
            df_supplementary_accommodation.region == region, :
        ]
        random.seed(2019)
        list_of_overnight_supplementary_accommodation.extend(
            random.choices(
                population=supplementary_accommodation_in_region[
                    "household_id"
                ].tolist(),
                weights=supplementary_accommodation_in_region["beds"],
                k=number_of_tourists_in_region,
            )
        )
    dict_persons = {
        "household_id": list_of_overnight_supplementary_accommodation,
        "level_of_employment_cat": "0",
        "level_of_employment": 0,
        "country_of_origin": type_of_accommodation,
    }
    persons = pd.DataFrame(dict_persons)
    return persons


def add_tourists_in_supplementary_accommodation(
    tourist_accommodation: pd.DataFrame,
) -> pd.DataFrame:
    """
    This scripts loads tourists from the Supplementary accommodation Statistics, Tourist accommodation Statistics,
    Federal Statistical Office (FSO). We use data of 2019.
    """
    all_persons_in_supplementary_accommodation = pd.DataFrame(
        columns=[
            "is_swiss",
            "level_of_employment_cat",
            "level_of_employment",
            "country_of_origin",
            "person_id",
            "household_id",
            "current_edu",
            "highest_education",
            "current_job_rank",
            "age",
            "age_cat",
        ]
    )
    for type_of_accommodation in [
        "campsites",
        "holiday_homes",
        "collective_accommodation",
    ]:
        df_supplementary_accommodation = tourist_accommodation.loc[
            tourist_accommodation.tourist_accommodation_category
            == type_of_accommodation,
            :,
        ]
        persons = add_agents_in_each_supplementary_accommodation(
            type_of_accommodation,
            df_supplementary_accommodation,
        )
        all_persons_in_supplementary_accommodation = pd.concat(
            [all_persons_in_supplementary_accommodation, persons]
        )
    return all_persons_in_supplementary_accommodation


def add_agents_in_each_supplementary_accommodation(
    type_of_accommodation: str,
    df_supplementary_accommodation: pd.DataFrame,
) -> pd.DataFrame:
    """This function adds tourists in one type of supplementary accommodation, e.g. campsites, for integration in VISUM.
    The tourists are added based on data at the regional level.
    Specifically, it loads the list of all campsites (as an example), including:
     - their number of beds,
     - where they are located and
     - their ID.
    Then, for each region:
     - It distributes the tourists by commune into the campsites proportionally to the number of beds,
     - It adds the household zone ID to which each tourist belongs, and finally
     - It adds the tourist as 'persons', including person_id, household_id and residence_zone_id (i.e., location_id).
    It takes as input:
     - a list of campsites including the commune or the canton they are in and their IDs, and
     - the category of supplementary accommodation (in our exemple: campsites)"""
    overnights_in_supplementary_accommodation = pd.read_csv(
        dict_path["overnights_in_" + type_of_accommodation]
    )

    # Add tourists in supplementary accommodation
    persons = distribute_tourists_in_supplementary_accommodation(
        overnights_in_supplementary_accommodation,
        df_supplementary_accommodation,
        type_of_accommodation,
    )
    return persons


if __name__ == "__main__":
    distribute_tourists_in_tourist_accommodation()
