"""(c) isithotrightnow.com by Mat Lipson, Steefan Contractor and James Goldie (2025)

This file loops through locations and invokes the GetHistoricalObs lambda function.
Triggers just before midnight AEST for daily tasks.
"""

import logging

import boto3
import os
import json
import datetime

import pandas as pd
from flask import Flask, jsonify
from wetterdienst import Settings
from wetterdienst.provider.dwd.observation import DwdObservationRequest


def handle():
    # read in the locations.json file from s3
    s3_fpath = "1-datasources/locations.json"
    local_fpath = download_from_aws(s3_fpath)

    # Open the JSON file
    with open(local_fpath) as file:
        locations = json.load(file)

    # define date for calculating historical period
    date = datetime.date.today() + datetime.timedelta(days=1)
    date_str = date.strftime("%Y-%m-%d")
    print(f"date for historical period: {date}")

    # loop through locations and invoke the GetHistoricalObs lambda function
    for location in locations:
        station_id = location["id"]
        station_name = location["name"]

        print(f"invoking {station_id}: {station_name}")
        get_historical_orbs(station_id=station_id, date=date_str, window=7)

    status = {"statusCode": 200, "body": "Uploaded historical data to bucket"}

    return status


def download_from_aws(s3_fpath):
    s3 = boto3.client(
        "s3",
        region_name="fr-par",
        endpoint_url="https://s3.fr-par.scw.cloud",
        aws_access_key_id=os.environ["SCW_ACCESS_KEY"],
        aws_secret_access_key=os.environ["SCW_SECRET_KEY"],
    )
    bucket_name = "isithot-data"

    fname = os.path.basename(s3_fpath)
    local_file_path = f"/tmp/{fname}"

    try:
        # Get the object from S3 bucket
        response = s3.get_object(Bucket=bucket_name, Key=s3_fpath)

        # Save the object to local file
        with open(local_file_path, "wb") as f:
            f.write(response["Body"].read())

        print(f"File saved to {local_file_path}")

        return local_file_path

    except Exception as e:
        print(f"Error getting S3 object: {e}")
        return None


def upload_to_aws(local_file, s3_file):
    s3 = boto3.client(
        "s3",
        region_name="fr-par",
        endpoint_url="https://s3.fr-par.scw.cloud",
        aws_access_key_id=os.environ["SCW_ACCESS_KEY"],
        aws_secret_access_key=os.environ["SCW_SECRET_KEY"],
    )
    bucket_name = "isithot-data"

    try:
        s3.upload_file(local_file, bucket_name, s3_file)
        url = s3.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": bucket_name, "Key": s3_file},
            ExpiresIn=24 * 3600,
        )

        print("Upload Successful", url)
        return url
    except FileNotFoundError:
        print("The file was not found")
        return None


def get_historical_orbs(station_id, date, window):
    """
    Saves a DataFrame of historical Tmax, Tmin, and Tavg observations for the given date to s3 bucket.
    event Args:
        station_id (int): Station ID to retrieve data for.
        date (date, optional): Date to retrieve data for. Defaults to today's date.
        window (int, optional): Number of days to include in the historical window. Defaults to 7.
    Returns:
        pandas.DataFrame: writes pandas DataFrame containing historical Tmax, Tmin, and Tavg observations.
    """
    print("this is GetHistoricalObs")

    try:
        date = pd.Timestamp(date)
    except KeyError:
        date = datetime.date.today()
        print(
            f"Warning: Date missing. Calculating percentiles for today's date: {date}"
        )

    settings = Settings(  # default
        ts_shape="wide",  # tidy data
        ts_humanize=True,  # humanized parameters
        ts_convert_units=True,  # convert values to SI units
    )
    start_date = "1990-01-01"
    request = DwdObservationRequest(
        parameters=[
            ("daily", "climate_summary", "temperature_air_min_2m"),
            ("daily", "climate_summary", "temperature_air_max_2m"),
            ("daily", "climate_summary", "temperature_air_mean_2m"),
        ],
        periods="historical",
        start_date=start_date,
        end_date=datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(days=2),
        settings=settings,
    ).filter_by_station_id(station_id=[station_id])

    hist_obs = request.values.all().df.to_pandas()
    print(hist_obs.head())

    # Filter by date window
    hist_obs["monthDay"] = hist_obs["date"].dt.strftime("%m%d")
    window_dates = [
        date + datetime.timedelta(days=x) for x in range(-window, window + 1)
    ]
    window_days = [x.strftime("%m%d") for x in window_dates]
    result = hist_obs[hist_obs["monthDay"].isin(window_days)].drop(columns=["monthDay"])

    # Calculate averages
    result["Tavg"] = (
        result["temperature_air_max_2m"] + result["temperature_air_min_2m"]
    ) / 2

    # Convert index to datetime
    result.set_index("date", inplace=True)

    # upload to s3
    result.to_csv(f"/tmp/historical_{station_id}.txt")
    bucket_url = upload_to_aws(
        f"/tmp/historical_{station_id}.txt", f"2-processed/historical_{station_id}.txt"
    )
    print(" Find this on the bucket at " + bucket_url)


app = Flask(__name__)


@app.route("/")
def root():
    app.logger.info("hi")
    handle()
    return jsonify({"status": "200"})


@app.route("/health")
def health():
    # You could add more complex logic here, for example checking the health of a database...
    return jsonify({"status": "UP"})


if __name__ == "__main__":
    port_env = os.getenv("PORT", 8080)
    port = int(port_env)
    app.run(host="0.0.0.0", port=port)


if __name__ != "__main__":
    gunicorn_logger = logging.getLogger("gunicorn.error")
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)
