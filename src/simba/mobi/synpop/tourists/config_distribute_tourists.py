from pathlib import Path

FIRST_RESERVED_ID = A_NUMBER_TO_BE_SURE_IT_HAS_ANOTHER_ID_THAT_THE_RESIDENT_POPULATION_FROM_THE_SYNPOP

base_path = Path(r"path_to_data_folder_with_simba-python-output")

dict_path = {
    "overnights_in_hotels_detailed": base_path
    / "get_tourists_and_hotels/overnights_in_hotels_detailed_with_a_date.csv",
    "list_of_communes_with_hotels": base_path
    / "get_tourists_and_hotels/list_of_communes_with_hotels_with_a_date.json",
    "overnights_in_hotels_in_cantons_only": base_path
    / "get_tourists_and_hotels/overnights_in_hotels_in_cantons_only_with_a_date.csv",
    "hotels_from_OSM": base_path
    / "get_tourists_and_hotels/hotels_2023_03_14_with_id_zones_without_duplicates.csv",
    "campsites_from_OSM": base_path
    / "get_tourists_and_hotels/campsites_2023_03_28_with_id_zones_without_duplicates.csv",
    "collective_accommodation_from_OSM": base_path
    / "get_tourists_and_hotels/collective_accommodation_2023_05_04_with_id_zones_without_duplicates.csv",
    "holiday_homes_from_OSM": base_path
    / "get_tourists_and_hotels/holiday_homes_2023_05_04_with_id_zones_without_duplicates.csv",
    "overnights_in_holiday_homes": base_path
    / "get_tourists_and_hotels/overnights_in_holiday_homes_with_a_date.csv",
    "overnights_in_collective_accommodation": base_path
    / "get_tourists_and_hotels/overnights_in_collective_accomodation_with_a_date.csv",
    "overnights_in_campsites": base_path
    / "get_tourists_and_hotels/overnights_in_campsites_with_a_date.csv",
    "persons_for_VISUM": base_path
    / ("distribute_tourists_in_tourist_accommodation/persons.csv"),
    "output_files": base_path / "distribute_tourists_in_tourist_accommodation",
}
