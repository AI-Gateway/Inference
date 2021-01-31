from celery import Celery
from pottery import Redlock
from redis import Redis
f#rom pottery import RedisList
# from joblib import load
# import numpy as np

# # COMENTAR EN COLIBRI
# try:
#     print('Attempting colibri import')
#     import tflite_runtime.interpreter as tflite
#     COLIBRI=True
#     print('Succeded, running on colibri platform')
# except Exception as e:
#     import tensorflow as tf
#     COLIBRI=False
#     print('Failed, running on full platform')


# # Load the TFLite model and allocate tensors.
# if COLIBRI is True:
#     interpreter = tflite.Interpreter(model_path="model.tflite")
# else:
#     interpreter = tf.lite.Interpreter(model_path="model.tflite")


# interpreter.allocate_tensors()

# # Get input and output tensors.
# input_details = interpreter.get_input_details()
# output_details = interpreter.get_output_details()


MEASUREMENTS_TO_GROUP = 3

app = Celery('tasks', broker='redis://localhost')
redis = Redis.from_url('redis://localhost:6379/1')

@app.task
def process_new_measurement(measurements):
	global redis, MEASUREMENTS_TO_GROUP
	# lock = Redlock(key='process_new_measurement', masters={redis})
	# with lock:
	measurements_list = RedisList(redis=redis, key='measurements_list')
	measurements_list += [measurements]
	valid = True
	if len(measurements_list) > MEASUREMENTS_TO_GROUP:
		# TODO: Check if measurement must be added to queue and if measurement is valid
		measurements_list = measurements_list[len(measurements_list)-MEASUREMENTS_TO_GROUP:]

	if len(measurements_list) == MEASUREMENTS_TO_GROUP and valid:
		process_measurment_list.delay(list(measurements_list))


@app.task
def process_measurment_list(measurements_list):
	# Extract values from protobuf report and take average
	print(measurements_list)


# @app.task
# def pre_process_measurements(raw_measurements, measurements):
# 	colibri_scaler = load('scaler.sklearn')
# 	colibri_scaler.transform(measurements)
# 	inference_measurements.delay(raw_measurements, measurements)

# @app.task
# def inference_measurements(raw_measurements, measurements):
# 	global interpreter

# 	interpreter.set_tensor(input_details[0]['index'], input_data)

# 	interpreter.invoke()

# 	output_data = interpreter.get_tensor(output_details[0]['index'])

# 	# Calculo de mae
# 	mae = np.mean(np.abs(output_data-input_data[-1]))
# 	anomaly = mae > anomaly_threshold