from pathlib import Path

assets_path = Path(r"path_to_the_folder_with_all_your_input_data_regarding_tourism")
dict_path = {
    "persons_in_campsites_file": assets_path
    / r"\PASTA\Campsites\something_from_FSO.xlsx",
    "persons_in_hotels_file_detailed": assets_path
    / r"\HESTA\something.xlsx",
    "persons_in_hotels_file_per_canton": assets_path
    / r"\HESTA\something_from_FSO.csv",
    "communes_by_canton": assets_path / r"\something.xlsx",
    "overnights_in_holiday_homes_file": assets_path
    / r"\PASTA\HolidayHomes\something_from_FSO.xlsx",
    "overnights_in_collective_accommodation_file": assets_path
    / r"\PASTA\CollectiveAccomodation\something_from_FSO.xlsx",
    "overnights_in_campsites_file": assets_path
    / r"\PASTA\Campsites\something_from_FSO.xlsx",
    "major_regions_shape_file": assets_path
    / r"\GrossRegionen\2019\something.shp",
    "cached_tourist_files": Path(r"..\assets\resources/tourism_output/"),
}
