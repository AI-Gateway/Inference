import paho.mqtt.client as mqtt
import logging
from time import sleep
from datetime import datetime
from datetime import timedelta
import subprocess
# from tasks import process_new_measurement
from Report_pb2 import Report
from google.protobuf.json_format import MessageToJson
from joblib import load
import json
import numpy as np
import struct
import time
from MeasurementEnums_pb2 import VIBRATION_VECTOR



measurement_grouper = {}
machine_id = 111
host = '127.0.0.1'
port = 1883
platSerial = "06416153"
networkName = "aigateway"
prefix = "networks/{}/devices/gateways/gw-{}".format(networkName,platSerial)


logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)-15s %(levelname)-8s %(message)s",
    )
logger = logging.getLogger(__name__)
client_id = machine_id
hardware_serial_numbers = ['bc33acfffe1b3bbc', 'bc33acfffe1b3b29']
network_id = 'aigateway'
measurements_to_group = 16

class MQTTGrouper:
	def __init__(self, host, port, machine_id, hardware_serial_numbers, network_id, logger, measurements_to_group):
		self.host = host
		self.port = port
		self.machine_id = machine_id
		self.hardware_serial_numbers = hardware_serial_numbers
		self.client_id = str(machine_id)
		self.network_id = network_id
		self.measurements_list = [{'2021-02-05 20:04:51+0000': {'bc33acfffe1b3b29': 4.944361864166737, 'bc33acfffe1b3bbc': 4.047561224704669}}, {'2021-02-05 20:08:51+0000': {'bc33acfffe1b3b29': 4.971373374836214, 'bc33acfffe1b3bbc': 4.351644868584873}}, {'2021-02-05 20:12:51+0000': {'bc33acfffe1b3b29': 4.978876937067107, 'bc33acfffe1b3bbc': 4.4078936330025655}}, {'2021-02-05 20:16:51+0000': {'bc33acfffe1b3b29': 5.094096137239828, 'bc33acfffe1b3bbc': 4.504038118055039}}, {'2021-02-05 20:20:51+0000': {'bc33acfffe1b3b29': 5.121054475564105, 'bc33acfffe1b3bbc': 4.269319428850096}}, {'2021-02-05 20:24:51+0000': {'bc33acfffe1b3b29': 5.0984439764642655, 'bc33acfffe1b3bbc': 4.296945490271843}}, {'2021-02-05 20:28:51+0000': {'bc33acfffe1b3b29': 4.899074141772485, 'bc33acfffe1b3bbc': 4.078140561113334}}, {'2021-02-05 20:32:51+0000': {'bc33acfffe1b3b29': 5.2363356002015085, 'bc33acfffe1b3bbc': 4.5982004034632835}}, {'2021-02-05 20:36:51+0000': {'bc33acfffe1b3b29': 5.021669394311739, 'bc33acfffe1b3bbc': 4.591848985015221}}, {'2021-02-05 20:40:51+0000': {'bc33acfffe1b3b29': 4.93103502849748, 'bc33acfffe1b3bbc': 4.095602220245687}}, {'2021-02-05 20:44:51+0000': {'bc33acfffe1b3b29': 5.1752667938019155, 'bc33acfffe1b3bbc': 4.337177955503193}}, {'2021-02-05 20:48:51+0000': {'bc33acfffe1b3b29': 5.148468203304066, 'bc33acfffe1b3bbc': 4.355532899786829}}, {'2021-02-05 20:52:51+0000': {'bc33acfffe1b3b29': 4.767974356705115, 'bc33acfffe1b3bbc': 3.9031349182737465}}, {'2021-02-05 20:56:51+0000': {'bc33acfffe1b3b29': 4.730049347214426, 'bc33acfffe1b3bbc': 3.9982868471022215}}, {'2021-02-05 21:00:51+0000': {'bc33acfffe1b3b29': 4.938351372829005, 'bc33acfffe1b3bbc': 4.322176441372153}}, {'2021-02-05 21:04:51+0000': {'bc33acfffe1b3b29': 4.882837548280008, 'bc33acfffe1b3bbc': 3.9262821238051813}}]
		self.measurements_to_group = measurements_to_group
		self.client = mqtt.Client(client_id=str(client_id), userdata={
			"host": host,
			"port": port,
		}, clean_session=False)
		self.client.on_message = lambda client, userdata, message: \
					self.mqtt_receive(message.topic, message.payload, message.qos)

		self.client.on_disconnect = self.mqtt_ondisconnect
		self.client.on_connect = self.mqtt_onconnect
		self.logger = logger
		self.measurement_grouper = {}
		self.dates_last_update = {}
		self.last_sent_date = None
		self.min_values = []
		self.max_values = []


	def minMaxScaler(self, X, min_values, max_values):
		for i in range(X.shape[2]):
			X[0,:,i] = (X[0,:,i] - min_values[i]) / (max_values[i] - min_values[i])

	
	def connect(self):
		exit = False
		while not exit:
			try:
				self.client.connect(host, port)
				exit = True
			except Exception as e:
				self.logger.error('MQTT-Grouper-{} connect error, retrying in 10 seconds'.format(machine_id))
				self.logger.exception(e)
				sleep(10)

		with open('minMaxScaler.aigateway') as fp:
			self.max_values = [float(x) for x in fp.readline().split(',')]
			self.min_values = [float(x) for x in fp.readline().split(',')]


	def get_report_date(self, payload):
		report = Report()
		report.ParseFromString(payload)
		timestamp = datetime.utcfromtimestamp(int(report.timestamp)+0x5e400000).strftime('%Y-%m-%d %H:%M:%S') + '+0000'
		return timestamp
		# return datetime.now().isoformat()

	def dates_clean_stale(self):
		current = datetime.now()
		stale_dates = []
		for date in self.dates_last_update:
			if (current-self.dates_last_update[date]) >= timedelta(minutes=10):
				stale_dates += [date]

		for date in stale_dates:
			del self.dates_last_update[date]
			del self.measurement_grouper[date]


	def dates_add(self, date, device, payload):

		if self.last_sent_date is not None and date < self.last_sent_date:
			return False
		
		if date not in self.measurement_grouper:
			self.measurement_grouper[date] = {}

		if device in self.measurement_grouper[date]:
			self.logger.error('MQTT-Grouper-{} received duplicate report for date {}'.format(machine_id, date))
		
		report = Report()
		report.ParseFromString(payload)	
		json_report = 	json.loads(MessageToJson(report)) # payload
		for idx, item in enumerate(report.item):
			if item.type in [VIBRATION_VECTOR]:
				data = np.array([sample for sample in struct.iter_unpack(item.rawFormat, item.value)])
				data_rms = np.zeros(3)
				for ax in range(3):
					data_i = data[:,ax]
					data_i = np.array(data_i, dtype=np.float)
					data_i = data_i[0:item.fs]
					data_i -= np.mean(data_i)
					data_i *= (1000/item.sensitivity)
					data_rms[ax] = np.sqrt(np.mean(data_i ** 2))
				#x_rms = np.sqrt(np.mean(data[:,0] ** 2))
				#y_rms = np.sqrt(np.mean(data[len(data)//3:2*len(data)//3] ** 2))
				#z_rms = np.sqrt(np.mean(data[2*len(data)//3:] ** 2))
				#self.measurement_grouper[date][device] = np.mean([x_rms, y_rms, z_rms])
				self.measurement_grouper[date][device] = np.mean(data_rms)
		
		self.dates_last_update[date] = datetime.now()
		return True

	def dates_check_complete(self):
		complete_dates = []
		for date in self.measurement_grouper:
			if set(self.hardware_serial_numbers) == set(self.measurement_grouper[date].keys()):
				complete_dates+=[date]

		return complete_dates

	def dates_process_complete_dates(self, dates):
		dates.sort()
		for date in dates:
			self.logger.info('MQTT-Grouper-{} sending date {}'.format(self.machine_id,date))
			# TODO: Send measurement group to celery or task distributer.
			self.process_new_measurement({date:self.measurement_grouper[date]})
			self.last_sent_date = date
			del self.measurement_grouper[date]
			del self.dates_last_update[date]


	def mqtt_receive(self, topic, payload, qos):
		self.logger.info("Received a message at {}:{}".format(topic,qos,payload))
		payload = payload
		date = self.get_report_date(payload)
		device = topic.split('/')[-3]

		valid = self.dates_add(date, device, payload)
		self.dates_clean_stale()
		if valid is not True:
			return

		complete_dates = self.dates_check_complete()

		self.dates_process_complete_dates(complete_dates)



	def mqtt_ondisconnect(self, client, userdata, rc):
		self.logger.error('MQTT-Grouper-{} disconnected'.format(machine_id))

	def mqtt_onconnect(self, client, userdata, flags, rc):
		self.logger.info('MQTT-Grouper-{} connected'.format(machine_id))
		for serial in self.hardware_serial_numbers:
			topic = 'networks/{}/devices/wivers/{}/uq/q'.format(network_id, serial)
			self.logger.info('MQTT-Grouper-{} subscribed to {}'.format(machine_id, topic))
			self.client.subscribe(topic, 2)



	def loop(self):
		self.logger.info('MQTT-Grouper-{} loop starting'.format(machine_id))
		self.client.loop_forever()


	def process_new_measurement(self, measurements):
		# lock = Redlock(key='process_new_measurement', masters={redis})
		# with lock:
		# measurements_list =  [] #RedisList(redis=redis, key='measurements_list')
		self.measurements_list += [measurements]
		valid = True
		if len(self.measurements_list) > self.measurements_to_group:
			# TODO: Check if measurement must be added to queue and if measurement is valid
			self.measurements_list = self.measurements_list[len(self.measurements_list)-self.measurements_to_group:]

		if len(self.measurements_list) == self.measurements_to_group and valid:
			self.process_measurment_list(list(self.measurements_list))

	def process_measurment_list(self, measurements_list):
		# Extract values from protobuf report and take average
		print(measurements_list)
		self.logger.info('Processing measurements...')
		# COMENTAR EN COLIBRI
		try:
		    self.logger.info('Attempting colibri import')
		    import tflite_runtime.interpreter as tflite
		    COLIBRI=True
		    self.logger.info('Succeded, running on colibri platform')
		except Exception as e:
		    import tensorflow as tf
		    COLIBRI=False
		    self.logger.info('Failed, running on full platform')


		# Load the TFLite model and allocate tensors.
		if COLIBRI is True:
		    interpreter = tflite.Interpreter(model_path="model.tflite")
		else:
		    interpreter = tf.lite.Interpreter(model_path="model.tflite")


		interpreter.allocate_tensors()

		# Get input and output tensors.
		input_details = interpreter.get_input_details()
		output_details = interpreter.get_output_details()

		# Test the model on measurements input data.
		input_shape = input_details[0]['shape']
		print(input_shape)

		# Format measurement list to input shape
		# meas = [{'date1': {'sen1': 1, 'sen2': 2}},{'date2': {'sen1': 1.5, 'sen2': 2.5}}]
		# input_data = np.zeros([1,2,2])
		input_data = np.zeros(input_shape, dtype=np.float32)
		for i,date in enumerate(measurements_list):
			for j,serial in enumerate(self.hardware_serial_numbers):
				input_data[0,i,j] = list(date.values())[0][serial]
			# for j,x in enumerate(list(date.values())[0].values()):
			# 	input_data[0,i,j] = x

		# data = np.zeros(input_shape)
		# input_data = np.array(np.random.random_sample(input_shape), dtype=np.float32)

		# Scale data
		#colibri_scaler = load('scaler.sklearn')
		#colibri_scaler.transform(input_data)
		self.minMaxScaler(input_data, self.min_values, self.max_values)

		# Inference
		interpreter.set_tensor(input_details[0]['index'], input_data)

		interpreter.invoke()

		# The function `get_tensor()` returns a copy of the tensor data.
		# Use `tensor()` in order to get a pointer to the tensor.

		start = time.time()
		output_data = interpreter.get_tensor(output_details[0]['index'])
		end = time.time()
		self.logger.info('Process: {} in'.format(input_data))
		self.logger.info('{} ms'.format((end - start)*1000))
		self.logger.info('with output {}'.format(output_data))

		# Calculo de mae
		mae = np.mean(np.abs(output_data-input_data[0,-1]))
		threshold = 0.3681974401380784 # 0.3821387717979858
		anomaly = mae > threshold
		score = mae / threshold

		self.logger.info('Result at {}: Anomaly {} '.format(list(measurements_list[-1].keys())[0],anomaly))

		def blinkLed(ledNumber):
			path = "/sys/class/leds/led{}/brightness".format(ledNumber)
			subprocess.call("echo 1 > " + path +
							"&& sleep 0.5 &&"
							"echo 0 > " + path +
							"&& sleep 0.5 &&"
							"echo 1 > " + path +
							"&& sleep 0.5 &&"
							"echo 0 > " + path, shell=True)
		if anomaly:
			blinkLed(1)
		else:
			blinkLed(3)

		self.client.publish("{}/anomaly".format(prefix),int(anomaly),qos=1)
		self.client.publish("{}/score".format(prefix),score,qos=1)





if __name__ == '__main__':
	grouper = MQTTGrouper(host, port, machine_id, hardware_serial_numbers, network_id, logger, measurements_to_group)
	grouper.connect()
	grouper.loop()

