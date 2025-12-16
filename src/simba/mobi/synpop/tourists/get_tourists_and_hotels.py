from simba.mobi.synpop.tourists.config import dict_path
from simba.mobi.synpop.tourists.load_overnights_in_hotels import (
    load_overnights_in_hotels,
)
from simba.mobi.synpop.tourists.load_overnights_in_supplementaty_accommodation import (
    load_overnights_in_supplementary_accommodation,
)


def run():
    """
    This scripts loads
     - tourists from FSO data and
     - hotels and other accommodations from Openstreetmap.org.
    It generates CSV files as inputs for the distribution of tourists in hotels.
    It needs the following extra packages (in comparison with the rest of mobi-synpop):
     - osmnx for accessing OSM,
     - iteround for rounding the number of nights per day & per commune while maintaining their sum for Switzerland
    It also needs the following inputs files, from resources/data/input/tourism/:
     - Tourist accommodation statistics (HESTA), with reference year 2019 (for now at least), both
       - at the commune level (file_name.xlsx) and
       - per canton (FSO_file_name.csv)
     - The definition of cantons (as list of communes as of 2019, file_name.xlsx)
    """
    # Creates folder for outputs if it does not exist yet
    dict_path["cached_tourist_files"].mkdir(parents=True, exist_ok=True)
    load_overnights_in_hotels(dict_path)
    load_overnights_in_supplementary_accommodation(dict_path)


if __name__ == "__main__":
    run()
