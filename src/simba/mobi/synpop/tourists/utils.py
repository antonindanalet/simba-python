import numpy as np
import pandas as pd


def fill_missing_values_beds(hotels):
    # TO DO: average bed not for whole Switzerland but by regions or canton.
    # See https://www.bfs.admin.ch/bfs/fr/home/statistiques/catalogues-banques-donnees.assetdetail.24225030.html
    # "In Geneva, an establishment had an average of 140.5 beds available in 2021, while in the Jura and Three Lakes
    # region the average was only 30.3."

    hotels = testing_data_quality(hotels)

    # Define the average number of beds, the average number of rooms and the number of beds per room (on average)
    average_beds = hotels.loc[
        ~hotels.beds.isnull()
        & ~hotels.rooms.isnull()
        & (hotels.rooms >= 1)
        & (hotels.beds >= 1),
        "beds",
    ].mean()
    average_rooms = hotels.loc[
        ~hotels.beds.isnull()
        & ~hotels.rooms.isnull()
        & (hotels.rooms >= 1)
        & (hotels.beds >= 1),
        "rooms",
    ].mean()
    beds_per_room = average_beds / average_rooms

    hotels = define_nb_beds(hotels, average_beds, average_rooms, beds_per_room)

    return hotels


def define_nb_beds(hotels, average_beds, average_rooms, beds_per_room):
    # We fill in the number of beds step by step depending on the available information
    if "number_of_apartments" in hotels.columns:
        hotels = hotels.astype(
            {"beds": float, "rooms": float, "number_of_apartments": float}
        )
    else:
        hotels = hotels.astype({"beds": float, "rooms": float})
    # Simplification: if we don't know the number of rooms, we define it as the number of apartments (if available)
    if "number_of_apartments" in hotels.columns:
        nb_apartments_without_nb_rooms = (
            hotels.rooms.isnull() & ~hotels.number_of_apartments.isnull()
        )
        hotels.loc[nb_apartments_without_nb_rooms, "rooms"] = hotels.loc[
            nb_apartments_without_nb_rooms, "number_of_apartments"
        ]
    # 'capacity' is not often available (12 holiday homes). But is precise. Used as "number of beds" when available.
    if "capacity" in hotels.columns:
        capacity_without_nb_beds = hotels.beds.isnull() & ~hotels.capacity.isnull()
        hotels.loc[capacity_without_nb_beds, "beds"] = hotels.loc[
            capacity_without_nb_beds, "capacity"
        ]
        try:
            hotels.beds = hotels.beds.astype(float)
        except ValueError as exc:
            beds_capacity_value_not_float = (
                pd.to_numeric(hotels["beds"], errors="coerce").isna()
            ) & ~hotels.capacity.isnull()
            print(hotels.loc[beds_capacity_value_not_float, ["osmid", "capacity"]])
            raise ValueError(
                "The newly added value for the number of beds is not a float. It is a string."
            ) from exc
    # 'capacity:persons' is almost never available (2 holiday homes). But is precise. Used as "number of beds".
    if "capacity:persons" in hotels.columns:
        capacity_without_nb_beds = (
            hotels.beds.isnull() & ~hotels["capacity:persons"].isnull()
        )
        hotels.loc[capacity_without_nb_beds, "beds"] = hotels.loc[
            capacity_without_nb_beds, "capacity:persons"
        ]
        try:
            hotels.beds = hotels.beds.astype(float)
        except ValueError as exc:
            beds_capacity_value_not_float = (
                pd.to_numeric(hotels["beds"], errors="coerce").isna()
            ) & ~hotels.capacity.isnull()
            print(
                hotels.loc[beds_capacity_value_not_float, ["osmid", "capacity:persons"]]
            )
            raise ValueError(
                'The newly added value for the number of beds is not a float, based on "capacity:persons". '
                "It is a string."
            ) from exc
    if (
        ("capacity:caravans" in hotels.columns)
        | ("capacity:pitches" in hotels.columns)
        | ("capacity:tents" in hotels.columns)
    ):
        capacity_without_nb_beds = hotels.beds.isnull() & (
            ~hotels["capacity:caravans"].isnull()
            | ~hotels["capacity:pitches"].isnull()
            | ~hotels["capacity:tents"].isnull()
        )
        hotels.loc[capacity_without_nb_beds, "beds"] = (
            hotels.loc[capacity_without_nb_beds, "capacity:caravans"]
            + hotels.loc[capacity_without_nb_beds, "capacity:pitches"]
            + hotels.loc[capacity_without_nb_beds, "capacity:tents"]
        )

    if np.isnan(average_beds) is False:
        hotels.loc[
            (hotels.beds.isnull() | (hotels.beds < 1))
            & (hotels.rooms.isnull() | (hotels.rooms < 1)),
            ["beds", "rooms"],
        ] = [average_beds, average_rooms]
        hotels.loc[
            (hotels.beds.isnull() | (hotels.beds < 1))
            & (~hotels.rooms.isnull() | (hotels.rooms >= 1)),
            "beds",
        ] = (
            hotels.loc[
                (hotels.beds.isnull() | (hotels.beds < 1))
                & (~hotels.rooms.isnull() | (hotels.rooms >= 1)),
                "rooms",
            ]
            * beds_per_room
        )
    else:
        average_beds = hotels.beds.mean()
        hotels.loc[hotels.beds.isnull() | (hotels.beds < 1), "beds"] = average_beds
    return hotels


def testing_data_quality(hotels):
    # Testing quality (empty, non-numeric values) of OSM data (variables "beds" and "rooms")
    if "beds" not in hotels.columns:
        hotels["beds"] = pd.Series(dtype="int")
    if (hotels.beds.dtypes != np.float64) & (hotels.beds.dtypes != np.int64):
        try:
            hotels["beds"] = hotels.beds.apply(pd.to_numeric)
        except ValueError as exc:
            hotels["beds_numeric"] = hotels.beds.apply(pd.to_numeric, errors="coerce")
            value = hotels.loc[
                (hotels["beds_numeric"].isna()) & (~hotels["beds"].isna()), "beds"
            ].values[0]
            osmid = hotels.loc[
                (hotels["beds_numeric"].isna()) & (~hotels["beds"].isna()), "osmid"
            ].values[0]
            raise ValueError(
                f'Hotel with osmid {osmid} has a non-numeric value for number of beds ("{value}")'
            ) from exc
    if "rooms" not in hotels.columns:
        hotels["rooms"] = pd.Series(dtype="int")
    if (hotels.rooms.dtypes != np.float64) & (hotels.rooms.dtypes != np.int64):
        try:
            hotels["rooms"] = hotels.rooms.apply(pd.to_numeric)
        except ValueError as exc:
            hotels["rooms_numeric"] = hotels.rooms.apply(pd.to_numeric, errors="coerce")
            value = hotels.loc[
                (hotels["rooms_numeric"].isna()) & (~hotels["rooms"].isna()), "rooms"
            ].values[0]
            osmid = hotels.loc[
                (hotels["rooms_numeric"].isna()) & (~hotels["rooms"].isna()), "osmid"
            ].values[0]
            raise ValueError(
                f'Hotel with osmid {osmid} has a non-numeric value for number of rooms ("{value}")'
            ) from exc
    return hotels


def removing_new_openings(lodging_per_commune):
    start_date_variable_exists = "start_date" in lodging_per_commune.columns
    opening_date_variable_exists = "opening_date" in lodging_per_commune.columns
    if start_date_variable_exists | opening_date_variable_exists:
        if start_date_variable_exists:
            opening_date_variable = "start_date"
        elif opening_date_variable_exists:
            opening_date_variable = "opening_date"
        lodging_per_commune[opening_date_variable] = pd.to_datetime(
            lodging_per_commune[opening_date_variable], errors="coerce"
        )
        lodging_per_commune = lodging_per_commune[
            (lodging_per_commune[opening_date_variable] < "2020-01-01")
            | (lodging_per_commune[opening_date_variable].isnull())
        ]
        lodging_per_commune = lodging_per_commune.drop(opening_date_variable, axis=1)
    return lodging_per_commune
