import paho.mqtt.client as mqtt
import logging
from time import sleep

measurement_grouper = {}
machine_id = 111
host = '127.0.0.1'
port = 10001
logger = logging.getLogger(__name__)
client_id = machine_id
hardware_serial_numbers = ['xxxxxx', 'yyyyyy', 'zzzzzz']
network_id = 'ai-gateway'

class MQTTGrouper:
	def __init__(self, host, port, machine_id, hardware_serial_numbers, network_id, logger):
		self.host = host
		self.port = port
		self.machine_id = machine_id
		self.hardware_serial_numbers = hardware_serial_numbers
		self.client_id = str(machine_id)
		self.network_id = network_id
		self.client = mqtt.Client(client_id=str(client_id), userdata={
            "host": host,
            "port": port,
        }, clean_session=False)
		self.client.on_message = lambda client, userdata, message: \
		            self.mqtt_receive(message.topic, message.payload, message.qos)

		self.client.on_disconnect = self.mqtt_reconnect
		self.logger = logger
		self.measurement_grouper = {}


	def connect(self):
		exit = False
		while not exit:
			try:
				self.client.connect(host, port)
				self.logger.error(f'MQTT-Grouper-{machine_id} connected')
				exit = True
			except Exception as e:
				self.logger.error(f'MQTT-Grouper-{machine_id} connect error, retrying in 10 seconds')
				self.logger.exception(e)
				sleep(10)

		for serial in self.hardware_serial_numbers:
			topic = f'networks/{network_id}/devices/wivers/{serial}/uq'
			self.logger.error(f'MQTT-Grouper-{machine_id} subscribed to {topic}')
			self.client.subscribe(topic, 2)



	def get_report_date(self, payload):
		# Should extract date from payload
		return payload

	def dates_clean_stale(self):
		# TODO: Should clean old dates that didnt complete the measurement
		return

	def dates_add(self, date, device, payload):
		
		if date not in self.measurement_grouper:
			self.measurement_grouper[date] = {}

		if device in self.measurement_grouper[date]:
			self.logger.error(f'MQTT-Grouper-{machine_id} received duplicate report for date {date}')
		
		self.measurement_grouper[date][device] = payload

	def dates_check_complete(self):
		complete_dates = []
		for date in self.measurement_grouper:
			if set(self.hardware_serial_numbers) == set(self.measurement_grouper[date].keys()):
				complete_dates+=[date]

		return complete_dates

	def dates_process_complete_dates(self, dates):
	
		for date in dates:
			self.logger.error(f'MQTT-Grouper-{self.machine_id} sending date {date} with data: {self.measurement_grouper[date]}')
			# TODO: Send measurement group to celery or task distributer.
			del self.measurement_grouper[date]


	def mqtt_receive(self, topic, payload, qos):
		print(f"Received a message at {topic}:{qos}")
		print('Payload:')
		print(payload)
		print('')

		date = self.get_report_date(payload)
		device = topic.split('/')[-2]

		print('Cleaning stale dates')
		self.dates_clean_stale()
		print(self.measurement_grouper)
		print('')

		print('Adding date')
		self.dates_add(date, device, payload)
		print(self.measurement_grouper)
		print('')

		print('Checking complete_dates')
		complete_dates = self.dates_check_complete()
		print(complete_dates)
		print('')

		print('Processing complete_dates')
		self.dates_process_complete_dates(complete_dates)
		print(self.measurement_grouper)
		print('')


	def mqtt_reconnect(self, client, userdata, rc):
		reconnected = False

		while not reconnected:
			try:
				self.client.reconnect()
				reconnected = True
			except Exception as e:
				self.logger.error(f'MQTT-Grouper-{machine_id} reconnect error, retrying in 10 seconds')
				sleep(10)

	def loop(self):
		self.logger.error(f'MQTT-Grouper-{machine_id} loop starting')
		self.client.loop_forever()



if __name__ == '__main__':
	grouper = MQTTGrouper(host, port, machine_id, hardware_serial_numbers, network_id, logger)
	grouper.connect()
	grouper.loop()

