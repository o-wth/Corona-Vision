from datetime import date, timedelta, datetime
from bs4 import BeautifulSoup
from corona_sql import Datapoint, Session, upload, update_all_deltas
from flask import Flask, redirect
from threading import Thread
import chardet
import json

# data processing
import pandas as pd
import numpy as np

# native python
import traceback
import time
import json
import sys
import os
import io

import requests
import standards
import import_jhu


data_sources = {'live': [], 'historical': []}
source_files = [
	"data_sources/data_sources.json",
	"data_sources/us_states.json"
]
for filename in source_files:
	data_source = json.load(open(filename, encoding="utf-8"), encoding="utf-8")
	if 'live' in data_source:
		data_sources['live'] += data_source['live']
	if 'historical' in data_source:
		data_sources['historical'] += data_source['historical']

# daily reports link: https://github.com/CSSEGISandData/COVID-19/tree/master/csse_covid_19_data/csse_covid_19_daily_reports
def data_download():
	while True:
		try:
			update_live_data()
		except Exception as e:
			print("ERROR DURING DATA COLLECTION: ", e)

def update_live_data():
	for datasource in data_sources['live']:
		print("Loading live data from", datasource['label'])
		upload_datasource(datasource)

def update_historical_data():
	for datasource in data_sources['historical']:
		print("Loading historical data from", datasource['label'])
		upload_datasource(datasource)

def dict_match(source, search):
	for col in search:
		if col in source and source[col] == search[col]:
			return True
	return False

def upload_datasource(datasource):
	try:
		args = datasource['args']
		method = methods[datasource['method']]
		results = method(**args)
		if results:
			if "disallow" in datasource:
				# for each result, go through all the filters and see if they match. if not any of them match, then they're ok.
				results = [result for result in results if not any([dict_match(result, rule) for rule in datasource['disallow']])]

			upload(results, defaults=datasource['defaults'], source_link=datasource['source_link'])
	except Exception as e:
		print("Error during update: ", e, type(e), ". Data source: ", datasource['label'])
		traceback.print_tb(sys.exc_info()[2])

def number(string):
	if type(string) == float or type(string) == int:
		return string
	string = string.strip()
	if not string:
		return 0
	string = string.split()[0]
	number = string.replace(",", "").replace("+", "").replace(".", "").replace("*", "")
	try:
		return int(number)
	except:
		return 0

def import_worldometers():
	response = requests.get("http://www.worldometers.info/coronavirus")
	soup = BeautifulSoup(response.text, "html.parser")
	main_countries = soup.find(id="main_table_countries_today")
	labels = ['admin0', 'total', '', 'deaths', '', 'recovered', '', 'serious', '', '', 'tests', '']
	number_labels = {'total', 'deaths', 'recovered', 'serious', 'tests'}
	
	data = []
	for row in main_countries.find("tbody").findAll("tr"):
		if row.get("class") and "row_continent" in row.get("class"):
			continue

		tds = row.findAll("td")
		new_data = {}
		new_data['group'] = "" or tds[-1].get("data-continent")
		for label, td in zip(labels, tds):
			text = td.text.strip()
			if label:
				if label in number_labels:
					new_data[label] = number(text)
				elif label == 'admin0':
					new_data[label] = standards.fix_admin0_name(text)
				else:
					new_data[label] = text
		
		data.append(new_data)
	
	return data

def get_elem(soup, selector_chain):
	elem = soup
	for selector in selector_chain:
		if type(selector) == int:
			elem = elem[selector]
		elif type(selector) == str:
			if selector.startswith("::"):
				elem = json_methods[selector](elem)
			else:
				elem = elem.select(selector)
	
	return elem

def import_csv(url, labels, row='all'):
	response = requests.get(url)
	df = pd.read_csv(io.StringIO(response.text))
	return import_df(df, labels, row)

def import_table(url, table_selector, labels, row='all'):
	response = requests.get(url)
	soup = BeautifulSoup(response.text, "html.parser")
	table = get_elem(soup, table_selector)
	df = pd.read_html(table.prettify())[0]
	return import_df(df, labels, row)

def import_df(df, labels, row):
	all_data = []
	if row == 'all':
		for _, row in df.iterrows():
			data = {}
			for label in labels:
				label_selector = labels[label]
				if type(label_selector) == list:
					head = row
					for sel in label_selector:
						if sel.startswith("::"):
							head = json_methods[sel](head)
						else:
							head = head[sel]
					data[label] = head
				elif type(label_selector) == str:
					data[label] = row[label_selector]
				
			all_data.append(data)
	else:
		data = {}
		row = df.iloc[row]
		for label in labels:
			data[label] = row[labels[label]]
		all_data.append(data)
		
	return all_data

import chardet
def import_json(url, labels, namespace=['features'], allow=[], use_datestr=False):
	if use_datestr:
		url = date.today().strftime(url)
	# url = date(2020, 4, 19).strftime(url)
	resp = requests.get(url)
	# encoding = chardet.detect(resp.content)['encoding']
	# json_content = json.loads(resp.content, encoding=encoding)
	content = find_json(resp.json(), namespace)
	data = []
	if type(content) == list:
		for row in content:
			try:
				allowed = True
				for rule in allow:
					select, match, match_type = rule
					if match_type == '==':
						allowed = allowed and (find_json(row, select) == match)
					elif match_type == '!=':
						allowed = allowed and (find_json(row, select) != match)
				if allowed:
					data.append(extract_json_data(row, labels))
			except KeyError:
				print("\rKeyError", end='\r')
	else:
		data.append(extract_json_data(content, labels))
	
	return data
		
def extract_json_data(row, labels):
	result = {}
	for label in labels:
		try:
			j = find_json(row, labels[label])
		except KeyError:
			# print("\rKeyError on", label,"- skipping")
			continue
		if j is not None:
			result[label] = j
	return result

def dmy(s):
	d, m, y = s.split("/")
	if len(m) == 1:
		m = "0" + m

	if len(d) == 1:
		d = "0" + d

	return y + "-" + m + "-" + d

def find_json(head, selectors):
	for selector in selectors:
		if selector.startswith("::"):
			head = json_methods[selector](head)
		else:
			head = head[selector]
	return head

def date_t(s):
	return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S").strftime("%Y-%m-%d")

def import_jhu_runner():
	return import_jhu.download_data_for_date(date.today())

def import_jhu_historical():
	return import_jhu.add_date_range(date_1=date(2020, 1, 22), date_2=date.today())

json_methods = {
	"::unixtime": lambda x: datetime.utcfromtimestamp(x//1000).strftime("%Y-%m-%d"),
	"::number": lambda x: number(x),
	"::text": lambda x: x.text,
	"::strip": lambda x: x.strip(),
	"::cap": lambda x: x.capitalize(),
	"::dmy": lambda x: datetime.strptime(x, "%d%m%Y").strftime("%Y-%m-%d"),
	"::ymd": lambda x: datetime.strptime(x, "%Y%m%d").strftime("%Y-%m-%d"),
	"::date_t": date_t,
	"::us_state_code": lambda x: standards.get_admin1_name("United States", x),
	"::str": lambda x: str(x)
}

methods = {
	"worldometers": import_worldometers,
	"csv": import_csv,
	"json": import_json,
	"jhu": import_jhu_runner,
	"jhu_range": import_jhu_historical,
	"update_all_deltas": update_all_deltas,
	"table": import_table
}

bno_countries = [
	'China', 'Canada', 'Australia'
]

app = Flask(__name__)

@app.route("/")
def hello():
	return redirect("https://www.coronavision.us/")

def get_attr(attributes, selector):
	head = attributes
	for s in selector.split("."):
		if s.isdigit():
			s = int(s)
		if s.startswith("::"):
			head = json_methods[s](head)
		else:
			head = head[s]
	return head

def import_gis(gis_url, labels, use_geometry=True):
	query_url = gis_url + "/query?f=geojson&outFields=*&where=1%3D1"
	source_link = "http://www.arcgis.com/home/webmap/viewer.html?url=" + gis_url
	labels = {
		"location.admin0": "",
		"location.admin1": "",
		"location.admin2": "",
		"datapoint.admin0": "",
		"datapoint.admin1": "",
		"datapoint.admin2": "",
		"datapoint.entry_date": date.today(),
		**labels
	}
	geojson = requests.get(query_url).json()
	features = geojson['features']
	feature_rows = []
	for feature in features:
		row = {'location': {}, 'datapoint': {}}
		if use_geometry:
			row['location']['geometry'] = json.dumps(feature['geometry'])
		attributes = feature['properties']
		for label in labels:
			selector = labels[label]
			table, label = label.split(".")
			if type(selector) == list:
				row[table][label] = find_json(attributes, selector)
			else:
				row[table][label] = selector
		print(row)
		feature_rows.append(row)
	upload(feature_rows)

import_gis(
	"https://services6.arcgis.com/L1SotImj1AAZY1eK/arcgis/rest/services/dpc_regioni_covid19/FeatureServer/0/",
	{
		"location.admin1": ["denominazione_regione"],
		"datapoint.admin1": ["denominazione_regione"],
		"location.latitude": ["latitudine"],
		"location.longitude": ["longitudine"],
		"location.admin0": "Italy",
		"datapoint.admin0": "Italy",
		"datapoint.total": ["totale_casi"],
		"datapoint.deaths": ["deceduti"],
		"datapoint.entry_date": date.today()
	}
)

exit()
if __name__ == "__main__":
	# use_server = False
	use_server = "coronavision_import_data_use_server" not in os.environ

	# import_jhu.download_data_for_date(date.today() - timedelta(days=1))
	# upload_datasource(data_sources['historical'][4])
	# import_jhu.add_date_range(date(2020, 2, 7), date.today())
	# if use_server:
	# 	exit()

	# DEBUG MARKER
	jhu_url = "https://github.com/CSSEGISandData/COVID-19/tree/master/csse_covid_19_data/csse_covid_19_daily_reports"

	if len(sys.argv) == 1:
		downloader = Thread(target=data_download, name="Data downloader", daemon=not use_server)
		downloader.start()
	elif sys.argv[1] == 'testlast':
		print("Testing the most recent live data source...")
		upload_datasource(data_sources['live'][-1])
	elif sys.argv[1] == 'historical':
		downloader = Thread(target=update_historical_data, name="Data downloader", daemon=not use_server)
		downloader.start()
	elif sys.argv[1].startswith('jhu'):
		if len(sys.argv[1]) == 3:
			upload(import_jhu.download_data_for_date(date(2020, 3, 5)), defaults={}, source_link=jhu_url)
		else:
			d = sys.argv[1][3:]
			y, m, d = d.split('-')
			y = int(y)
			m = int(m)
			d = int(d)
			upload(import_jhu.download_data_for_date(date(y, m, d)), defaults={'entry_date': date(y, m, d)}, source_link=jhu_url)

	if use_server:
		# DEBUG MARKER
		PORT = 6060
		if "PORT" in os.environ:
			PORT = os.environ['PORT']
		app.run("0.0.0.0", port=PORT)
	else:
		input()