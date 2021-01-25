import paho.mqtt.client as mqtt
import logging
from time import sleep
from datetime import datetime
from datetime import timedelta

measurement_grouper = {}
machine_id = 111
host = '127.0.0.1'
port = 10001

logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)-15s %(levelname)-8s %(message)s",
    )
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
		self.dates_last_update = {}


	def connect(self):
		exit = False
		while not exit:
			try:
				self.client.connect(host, port)
				self.logger.info(f'MQTT-Grouper-{machine_id} connected')
				exit = True
			except Exception as e:
				self.logger.error(f'MQTT-Grouper-{machine_id} connect error, retrying in 10 seconds')
				self.logger.exception(e)
				sleep(10)

		for serial in self.hardware_serial_numbers:
			topic = f'networks/{network_id}/devices/wivers/{serial}/uq'
			self.logger.info(f'MQTT-Grouper-{machine_id} subscribed to {topic}')
			self.client.subscribe(topic, 2)



	def get_report_date(self, payload):
		# Should extract date from payload
		return payload

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
		
		if date not in self.measurement_grouper:
			self.measurement_grouper[date] = {}

		if device in self.measurement_grouper[date]:
			self.logger.error(f'MQTT-Grouper-{machine_id} received duplicate report for date {date}')
		
		self.measurement_grouper[date][device] = payload
		self.dates_last_update[date] = datetime.now()

	def dates_check_complete(self):
		complete_dates = []
		for date in self.measurement_grouper:
			if set(self.hardware_serial_numbers) == set(self.measurement_grouper[date].keys()):
				complete_dates+=[date]

		return complete_dates

	def dates_process_complete_dates(self, dates):
	
		for date in dates:
			self.logger.info(f'MQTT-Grouper-{self.machine_id} sending date {date} with data: {self.measurement_grouper[date]}')
			# TODO: Send measurement group to celery or task distributer.
			del self.measurement_grouper[date]
			del self.dates_last_update[date]


	def mqtt_receive(self, topic, payload, qos):
		self.logger.info(f"Received a message at {topic}:{qos} with payload: {payload}")

		date = self.get_report_date(payload)
		device = topic.split('/')[-2]

		self.dates_add(date, device, payload)

		self.dates_clean_stale()

		complete_dates = self.dates_check_complete()

		self.dates_process_complete_dates(complete_dates)



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
		self.logger.info(f'MQTT-Grouper-{machine_id} loop starting')
		self.client.loop_forever()



if __name__ == '__main__':
	grouper = MQTTGrouper(host, port, machine_id, hardware_serial_numbers, network_id, logger)
	grouper.connect()
	grouper.loop()

