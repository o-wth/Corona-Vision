from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func
from sqlalchemy import and_, between, not_

db = SQLAlchemy()

class DataEntry(db.Model):
	__tablename__ = "data_entries"
	entry_date = db.Column(db.Date, primary_key=True)
	total_confirmed = db.Column(db.Integer)
	total_recovered = db.Column(db.Integer)
	total_dead = db.Column(db.Integer)
	total_active = db.Column(db.Integer)

class Datapoint(db.Model):
	__tablename__ = "datapoints"
	data_id = db.Column(db.Integer, primary_key=True)
	entry_date = db.Column(db.Date)
	
	admin2 = db.Column(db.String(320))
	province = db.Column(db.String(320))
	country = db.Column(db.String(320))
	
	latitude = db.Column(db.Float(10, 6))
	longitude = db.Column(db.Float(10, 6))
	
	confirmed = db.Column(db.Integer)
	recovered = db.Column(db.Integer)
	dead = db.Column(db.Integer)
	active = db.Column(db.Integer)
	
	def json_serializable(self):
		return {
			"data_id": self.data_id,
			"admin2": self.admin2,
			"province": self.province,
			"country": self.country,
			"latitude": float(self.latitude),
			"longitude": float(self.longitude),
			"confirmed": float(self.confirmed),
			"recovered": float(self.recovered),
			"dead": float(self.dead),
			"active": float(self.active)
		}

class User(db.Model):
	__tablename__ = "users"
	user_id = db.Column(db.Integer, primary_key=True)
	email = db.Column(db.String(320))
	firstname = db.Column(db.String(32))
	lastname = db.Column(db.String(32))
	password_encrypt = db.Column(db.String(256))

def total_cases(country, province, date_):
	result = Datapoint.query.filter(
		and_(
			Datapoint.country == country,
			Datapoint.province == province,
			Datapoint.admin2 == '',
			Datapoint.entry_date == date_
		)
	).all()
	
	total_confirmed = 0
	total_recovered = 0
	total_dead = 0
	total_active = 0
	
	for case in result:
		total_confirmed += case.confirmed
		total_recovered += case.recovered
		total_dead += case.dead
		total_active += case.active
		
	return {
		"total_confirmed": total_confirmed,
		"total_recovered": total_recovered,
		"total_dead": total_dead,
		"total_active": total_active
	}

def find_cases(ne_lat, ne_lng, sw_lat, sw_lng, entry_date, exclude_level):
	min_lat = sw_lat
	max_lat = ne_lat
	
	min_lng = sw_lng
	max_lng = ne_lng

	lng_condition = between(Datapoint.longitude, min_lng, max_lng)

	if max_lng < min_lng:
		lng_condition = not_(between(Datapoint.longitude, max_lng, min_lng))

	levels = {
		"admin2": Datapoint.admin2,
		"province": Datapoint.province,
		"country": Datapoint.country
	}

	if exclude_level != 'none' and exclude_level in levels:
		result = Datapoint.query.filter(
			and_(
				between(Datapoint.latitude, min_lat, max_lat),
				lng_condition,
				Datapoint.entry_date==entry_date,
				levels[exclude_level]==''
			)
		)
	else:
		result = Datapoint.query.filter(
			and_(
				between(Datapoint.latitude, min_lat, max_lat),
				lng_condition,
				Datapoint.entry_date==entry_date
			)
		)
	
	return result.all()
