from sqlalchemy import and_, between, not_
from sqlalchemy import create_engine, Column, Integer, Float, Boolean, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.sql import func

import os
from datetime import date, datetime, timedelta
import json
import numpy as np

import standards

# Keep the actual SQL URL private
sql_uri = os.environ['DATABASE_URL']
engine = create_engine(sql_uri)

force_refresh = False

# Scoped_session is important here
Session = scoped_session(sessionmaker(bind=engine, autocommit=False))

# Class used to make tables
Base = declarative_base()

stat_labels = {'confirmed', 'dconfirmed', 'deaths', 'ddeaths', 'serious', 'dserious', 'recovered', 'drecovered', 'active', 'dactive', 'num_tests'}
increase_labels = {"confirmed", "deaths", "recovered", "num_tests"}

class Datapoint(Base):
	__tablename__ = "datapoints"

	# columns about the date/time of the datapoint
	entry_date = Column(String(16), primary_key=True)
	update_time = Column(DateTime, default=datetime.utcnow())
	
	# columns about the nominal location
	admin2 = Column(String(320), default='', primary_key=True)
	province = Column(String(320), default='', primary_key=True)
	country = Column(String(320), default='', primary_key=True)
	group = Column(String(320), default='')
	
	# columns about the numeric location
	latitude = Column(Float(10, 6))
	longitude = Column(Float(10, 6))
	
	# determines if this is the first time that that region has been seen
	is_first_day = Column(Boolean, default=False)
	
	# COVID-19 stats about this datapoint
	confirmed = Column(Integer, default=0)
	recovered = Column(Integer, default=0)
	deaths = Column(Integer, default=0)
	active = Column(Integer, default=0)
	serious = Column(Integer, default=0)
	
	dconfirmed = Column(Integer, default=0)
	drecovered = Column(Integer, default=0)
	ddeaths = Column(Integer, default=0)
	dactive = Column(Integer, default=0)
	dserious = Column(Integer, default=0)

	num_tests = Column(Integer, default=0)

	# used mostly for provincial data
	source_confirmed = Column(String())
	source_recovered = Column(String())
	source_deaths = Column(String())
	source_serious = Column(String())
	source_num_tests = Column(String())

	def location_labelled(self):
		return self.latitude != None and self.longitude != None

	def guess_location(self):
		# try to update the location
		if not self.location_labelled():
			# if the object's location is not accurate, however,
			# we try to estimate its location
			estimated_location = standards.get_estimated_location(self.country, self.province, self.admin2)

			# ^^^ returns none if no accurate data could be found
			if estimated_location:
				# update the old location
				est_lat, est_lng = estimated_location
				self.latitude = est_lat
				self.longitude = est_lng

	@staticmethod
	def less_detail(country, province, admin2):
		if admin2:
			return country, province, ''
		if province:
			return country, '', ''
		if country:
			return '', '', ''
		return None

	def update(self, data, source_link, session):
		delta = {label: 0 for label in stat_labels}

		for label in stat_labels:
			if label in data:
				if label in increase_labels:
					if data[label] > getattr(self, label) or force_refresh:
						delta[label] = data[label] - getattr(self, label)
						setattr(self, label, data[label])
				else:
					if data[label] != getattr(self, label) or force_refresh:
						delta[label] = data[label] - getattr(self, label)
						setattr(self, label, data[label])

		self.update_sources(delta, source_link)

		return delta

	def location_tuple(self):
		return (self.country, self.province, self.admin2)

	def update_sources(self, delta, source_link):
		# record the sources for each piece of data
		for label in ['confirmed', 'recovered', 'deaths', 'serious', 'num_tests']:
			if label in delta and delta[label] != 0:
				self.update_time = datetime.utcnow()
				setattr(self, "source_" + label, source_link)

def select(d, cols):
	return tuple(d[col] for col in cols)

def dfilter(d, cols):
	return dict({col: d[col] for col in d if col in cols})

def upload(rows, defaults={}, source_link='', recount=True):
	session = Session()

	location_maps = {}
	i = 0

	# so we don't have to recount things hella times
	updated_provinces = set()
	updated_countries = set()
	updated_world = set()
	unique_days = set()

	for row in rows:
		i += 1
		print(f"\rFinding changes--{i}/{len(rows)}               ", end='\r')
		row = _fill_defaults(row, defaults)

		row_link = None
		if 'source_link' in row:
			row_link = row['source_link']
			del row['source_link']
		
		# fix the location's name
		location = select(row, ['country', 'province', 'admin2'])
		location = standards.normalize_name(*location)
		row['country'] = location[0]
		row['province'] = location[1]
		row['admin2'] = location[2]

		# skip empty datapoints
		has_data = False
		for label in stat_labels:
			if label in row and row[label]:
				has_data = True

		if not has_data:
			continue

		# load the cache so we don't have to query a lot
		if row['entry_date'] not in location_maps:
			new_defaults = {**dfilter(defaults, ['country', 'province', 'admin2']), 'entry_date': row['entry_date']}
			locations = session.query(Datapoint).filter_by(**new_defaults)
			mapped = {loc.location_tuple(): loc for loc in locations}
			location_maps[row['entry_date']] = mapped

		# find the already-existing data
		if location in location_maps[row['entry_date']]:
			existing = location_maps[row['entry_date']][location]
		else:
			existing = None
		
		# actually update the data
		delta = {}
				
		if existing:
			delta = existing.update(row, row_link if row_link else source_link, session)
			is_updated = (len(delta) > 1) or 0 not in delta
			existing.guess_location()
		else:
			delta = dfilter(row, stat_labels)
			new_data = Datapoint(**row)
			new_data.guess_location()
			new_data.update_sources(delta, row_link if row_link else source_link)
			session.add(new_data)
			is_updated = True
		
		unique_days.add(row['entry_date'])

		# now we recalculate the totals
		if is_updated and recount:
		# print("This row was updated!")
			if row['admin2']:
				updated_provinces.add((row['country'], row['province'], row['entry_date']))
			if row['province']:
				updated_countries.add((row['country'], row['entry_date']))
			if row['country']:
				updated_world.add((row['entry_date'],))
		
	i = 0
	for province_dp in updated_provinces:
		i += 1
		print(f"\rRecounting provinces--{i}/{len(updated_provinces)}                       ", end='\r')
		province_overall = calc_overall_province(*province_dp, session)
		update_overall(session, *province_overall)
		# print("Overall:", country, province, row['entry_date'], confirmed, deaths, recovered)
	
	i = 0
	for country_dp in updated_countries:
		i += 1
		print(f"\rRecounting countries--{i}/{len(updated_countries)}                       ", end='\r')
		country_overall = calc_overall_country(*country_dp, session)
		update_overall(session, *country_overall)
		# print("Overall:", country, confirmed, row['entry_date'], deaths, recovered)

	i = 0
	for world_date in updated_world:
		i += 1
		print(f"\rRecounting worlds--{i}/{len(updated_world)}                    ", end='\r')
		
		world_overall = calc_overall(*world_date, session)
		update_overall(session, *world_overall)
		# print("Overall:", row['entry_date'], confirmed, deaths, recovered)

	for day in unique_days:
		if type(day) == date:
			update_deltas(day)
		elif type(day) == str:
			day_obj = datetime.strptime(day, "%Y-%m-%d")
			update_deltas(day_obj)

	print("\rCommitting all...                                               ", end='\r')
	session.commit()
	print("\rDone committing         ", end='\r')

def _is_nan(data):
	return type(data) == float and np.isnan(data)

def _fill_defaults(data, defaults):
	default_data = { 'entry_date': datetime.utcnow().strftime("%Y-%m-%d"), 'group': '', 'country': '', 'province': '', 'admin2': '', **defaults }

	# add default values if not found
	for label in default_data:
		if label not in data:
			data[label] = default_data[label]
		
	# remove NaN data
	for label in stat_labels:
		if label in data:
			if _is_nan(data[label]):
				del data[label]

	data['country'] = standards.fix_country_name(data['country'])
	data['group'] = standards.get_continent(data['country'])

	return data

sums = (func.sum(Datapoint.confirmed), func.sum(Datapoint.deaths), func.sum(Datapoint.recovered), func.sum(Datapoint.dconfirmed), func.sum(Datapoint.ddeaths), func.sum(Datapoint.drecovered), func.sum(Datapoint.num_tests))
sum_labels = ['confirmed', 'deaths', 'recovered', 'dconfirmed', 'ddeaths', 'drecovered', 'num_tests']

def calc_overall_province(country, province, entry_date, session):
	overall_province = session.query(Datapoint.country, Datapoint.province, *sums)\
			.filter(Datapoint.country == country, Datapoint.province == province, Datapoint.admin2 != '', Datapoint.entry_date == entry_date)\
			.group_by(Datapoint.country, Datapoint.province)\
			.first()
	if overall_province:
		return tuple([entry_date, country, province, '', *overall_province[2:]])
	else:
		fallback = session.query(Datapoint.country, Datapoint.province, *sums)\
			.filter_by(country=country, province=province, admin2='', entry_date=entry_date)\
			.first()
		if fallback:
			return tuple([entry_date, country, province, '', *fallback[2:]])
		else:
			return entry_date, country, province, '', 0, 0, 0, 0, 0, 0, 0

def calc_overall_country(country, entry_date, session):
	overall_country = session.query(Datapoint.country, *sums)\
		.filter(Datapoint.country == country, Datapoint.province != '', Datapoint.admin2 == '', Datapoint.entry_date == entry_date)\
		.group_by(Datapoint.country)\
		.first()
	if overall_country:
		return tuple([entry_date, country, '', '', *overall_country[1:]])
	else:
		fallback = session.query(Datapoint.country, *sums)\
			.filter_by(country=country, province='', admin2='', entry_date=entry_date)\
			.first()
		if fallback:
			return tuple([entry_date, fallback[0], '', '', *fallback[1:]])
		else:
			return entry_date, country, '', '', 0, 0, 0, 0, 0, 0, 0

def calc_overall(entry_date, session):
	overall = session.query(*sums)\
		.filter(Datapoint.country != '', Datapoint.province == '', Datapoint.admin2 == '', Datapoint.entry_date == entry_date)\
		.first()
	if overall:
		return tuple([entry_date, '', '', '', *overall])
	return entry_date, '', '', '', 0, 0, 0, 0, 0, 0, 0

def update_overall(session, entry_date, country, province, admin2, confirmed, deaths, recovered, dconfirmed, ddeaths, drecovered, num_tests):
	# find an overall datapoint
	overall_dp = session.query(Datapoint).filter_by(country=country, province=province, admin2=admin2, entry_date=entry_date).first()

	# if it doesn't exist, we create it
	if not overall_dp:
		overall_dp = Datapoint(country=country, province=province, admin2=admin2, entry_date=entry_date, confirmed=0, deaths=0, recovered=0, num_tests=0)
		overall_dp.guess_location()
		session.add(overall_dp)

	updated = False
	if not force_refresh:
		if confirmed > overall_dp.confirmed:
			overall_dp.confirmed = confirmed
			overall_dp.source_confirmed = "calculated"
			updated = True
		if deaths > overall_dp.deaths:
			overall_dp.deaths = deaths
			overall_dp.source_deaths = "calculated"
			updated = True
		if recovered > overall_dp.recovered:
			overall_dp.recovered = recovered
			overall_dp.source_recovered = "calculated"
			updated = True
		if num_tests > overall_dp.num_tests:
			overall_dp.num_tests = num_tests
			overall_dp.source_num_tests = "calculated"
			updated = True
	else:
		overall_dp.confirmed = confirmed
		overall_dp.source_confirmed = "calculated"

		overall_dp.deaths = deaths
		overall_dp.source_deaths = "calculated"

		overall_dp.recovered = recovered
		overall_dp.source_recovered = "calculated"

		overall_dp.num_tests = num_tests
		overall_dp.source_num_tests = "calculated"
		updated = True

	if updated:
		print("Updated an overall:", country, province, admin2)
		overall_dp.update_time = datetime.utcnow()


def update_deltas(day):
	compare_day = day + timedelta(days=-1)

	day_str = day.strftime("%Y-%m-%d")
	compare_day_str = compare_day.strftime("%Y-%m-%d")

	sess = Session()
	today_datapoints = sess.query(Datapoint).filter_by(entry_date=day_str)
	yesterday_datapoints = sess.query(Datapoint).filter_by(entry_date=compare_day_str)
	today_dict = {(d.country, d.province, d.admin2): d for d in today_datapoints}
	yesterday_dict = {(d.country, d.province, d.admin2): d for d in yesterday_datapoints}

	total = len(today_dict)
	i = 1

	for location in today_dict:
		print("\r", compare_day_str, "-->", day_str, f"{i}/{total}           ", end='\r')
		today_dp = today_dict[location]
		if today_dp.active != (today_dp.confirmed - today_dp.deaths - today_dp.recovered):
			today_dp.active = today_dp.confirmed - today_dp.deaths - today_dp.recovered
		if location in yesterday_dict:
			yesterday_dp = yesterday_dict[location]
		else:
			yesterday_dp = None
		for label in ['active', 'confirmed', 'deaths', 'recovered']:
			current_val = getattr(today_dp, 'd' + label)
			if yesterday_dp:
				new_val = getattr(today_dp, label) - getattr(yesterday_dp, label)
			else:
				new_val = getattr(today_dp, 'd' + label)
			if new_val != current_val:
				setattr(today_dp, 'd' + label, new_val)
		i += 1

	print("\rCommitting deltas...                         ", end='\r')
	sess.commit()

def update_all_deltas():
	start_date = date(2020, 1, 22)
	end_date = datetime.utcnow().date()
	while start_date <= end_date:
		next_day = start_date + timedelta(days=1)
		update_deltas(start_date)
		start_date = next_day

def generate_location_map(entry_date):
	sess = Session()
	results = sess.query(Datapoint).filter_by(entry_date=entry_date)
	return {result.location_tuple(): result for result in results}

if __name__ == "__main__":
	print("Past overhead")
	sess = Session()
	print(calc_overall_province("United States", "New York", date.today().isoformat(), sess))
	print(calc_overall_country("United States", date.today().isoformat(), sess))
	print(calc_overall(date.today().isoformat(), sess))
