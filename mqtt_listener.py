import paho.mqtt.client as mqtt
import logging
from time import sleep
from datetime import datetime
from datetime import timedelta
# from tasks import process_new_measurement
from Report_pb2 import Report
from google.protobuf.json_format import MessageToJson
from joblib import load
import json
import numpy as np
import struct
from MeasurementEnums_pb2 import VIBRATION_VECTOR

measurement_grouper = {}
machine_id = 111
host = '127.0.0.1'
port = 1883

logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)-15s %(levelname)-8s %(message)s",
    )
logger = logging.getLogger(__name__)
client_id = machine_id
hardware_serial_numbers = ['bc33acfffe1b3bbc', 'bc33acfffe1b3b29']
network_id = 'aigateway'
measurements_to_group = 2

class MQTTGrouper:
	def __init__(self, host, port, machine_id, hardware_serial_numbers, network_id, logger, measurements_to_group):
		self.host = host
		self.port = port
		self.machine_id = machine_id
		self.hardware_serial_numbers = hardware_serial_numbers
		self.client_id = str(machine_id)
		self.network_id = network_id
		self.measurements_list = []
		self.measurements_to_group = measurements_to_group
		self.client = mqtt.Client(client_id=str(client_id), userdata={
			"host": host,
			"port": port,
		}, clean_session=False)
		self.client.on_message = lambda client, userdata, message: \
					self.mqtt_receive(message.topic, message.payload, message.qos)

		self.client.on_disconnect = self.mqtt_reconnect
		self.logger = logger
		self.measurement_grouper = {}
		self.dates_last_update = {}
		self.last_sent_date = None


	def connect(self):
		exit = False
		while not exit:
			try:
				self.client.connect(host, port)
				self.logger.info('MQTT-Grouper-{} connected'.format(machine_id))
				exit = True
			except Exception as e:
				self.logger.error('MQTT-Grouper-{} connect error, retrying in 10 seconds'.format(machine_id))
				self.logger.exception(e)
				sleep(10)

		for serial in self.hardware_serial_numbers:
			topic = 'networks/{}/devices/wivers/{}/uq/q'.format(network_id, serial)
			self.logger.info('MQTT-Grouper-{} subscribed to {}'.format(machine_id, topic))
			self.client.subscribe(topic, 2)



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
					data_i = data[:,i]
					data_i = data_i[0:item.fs]
					data_i -= np.mean(data_i)
					data_i *= (1000/item.sensitivity)
					data_rms[i] = np.sqrt(np.mean(data_i ** 2))
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



	def mqtt_reconnect(self, client, userdata, rc):
		reconnected = False

		while not reconnected:
			try:
				self.client.reconnect()
				reconnected = True
			except Exception as e:
				self.logger.error('MQTT-Grouper-{} reconnect error, retrying in 10 seconds'.format(machine_id))
				sleep(10)

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
		print('Processing measurements...')



if __name__ == '__main__':
	grouper = MQTTGrouper(host, port, machine_id, hardware_serial_numbers, network_id, logger, measurements_to_group)
	grouper.connect()
	grouper.loop()

