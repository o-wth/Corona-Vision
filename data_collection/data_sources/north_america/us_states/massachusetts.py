import requests
import datetime
import calendar
import io
import zipfile


# Massachusetts data - from a ZIP file containing raw data.
def import_data():
    now = datetime.datetime.now()
    import_date(now)

def import_date(now):
    month = calendar.month_name[now.month].lower()
    day = now.day
    year = now.year

    queryURL = f"https://www.mass.gov/doc/covid-19-raw-data-{month}-{day}-{year}/download"
    # source: https://www.mass.gov/info-details/covid-19-response-reporting#covid-19-cases-in-massachusetts-

    response = requests.get(queryURL, timeout=10)
    if response.status_code == 200:
        bytesio = io.BytesIO(response.content)

        myzip = zipfile.ZipFile(bytesio)
        counties = myzip.open("County.csv").readlines()

        datapoints = []
        
        for county in counties[1:]:
            county = county.decode("utf-8").strip()
            dateStr, county, totalStr, deathsStr = county.split(",")
            dateVal = datetime.datetime.strptime(dateStr, "%m/%d/%Y").date()
            if dateVal != now.date():
                continue
            yield {
                "entry_date": dateVal,
                "country": "United States",
                "province": "Massachusetts",
                "total": int(totalStr or 0),
                "deaths": int(deathsStr or 0)
            }

        if upload.upload_datapoints(datapoints):
            lastDatapointsUpdate = time.time()

if __name__ == "__main__":
    import_data()