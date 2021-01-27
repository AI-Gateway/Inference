from celery import Celery
from pottery import Redlock
from redis import Redis
from pottery import RedisList


app = Celery('tasks', broker='redis://localhost')
redis = Redis.from_url('redis://localhost:6379/1')

@app.task
def process_new_measurement(measurements):
	global redis
	lock = Redlock(key='process_new_measurement', masters={redis})
	with lock:
		measurements_list = RedisList(redis=redis, key='measurements_list')
		measurements_list += [measurements]
		valid = True
		if len(measurements_list) > 3:
			# TODO: Check if measurement must be added to queue and if measurement is valid
			measurements_list = measurements_list[len(measurements_list)-3:]

		if len(measurements_list) == 3 and valid:
			process_measurment_list.delay(list(measurements_list))


@app.task
def process_measurment_list(measurements_list):
	print(measurements_list)
