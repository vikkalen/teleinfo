import os, sys, serial, time, datetime, threading, json, yaml
import paho.mqtt.client

baudrate = 1200
port = os.getenv('TELEINFO_PORT', '/dev/ttyUSB0')
debug = os.getenv('TELEINFO_DEBUG') == '1'
publishInterval = float(os.getenv('TELEINFO_PUBLISH_INTERVAL', 30))
lastPublish = 0.

mqttHost = os.getenv('MQTT_HOST')
mqttPort = int(os.getenv('MQTT_PORT', 1883))
mqttClientId = os.getenv('MQTT_CLIENT_ID', 'teleinfo')
mqttUsername = os.getenv('MQTT_USERNAME')
mqttPassword = os.getenv('MQTT_PASSWORD')
mqttDiscoveryTopic = os.getenv('MQTT_DISCOVERY_TOPIC', 'homeassistant')
mqttStateTopic = os.getenv('MQTT_STATE_TOPIC', 'teleinfo')

info = {}

def receive(input, info):
  if len(input) < 3:
    return False
  key = input[0]
  value = input[1]
  checksum = input[2]
  if checksum == '':
    checksum = ' '
  computed_checksum = (sum(bytearray(key + ' ' + value, encoding='ascii')) & 0x3F) + 0x20
  if chr(computed_checksum) != checksum:
    return False
  if key == 'MOTDETAT':
    return True
  else:
    info[key] = int(value) if value.isdigit() else value
    return False

class MqttException(Exception):
  pass

def mqttConnect(mqtt, userdata, flags, rc):
  if rc == 0:
    print('Connected to MQTT Broker', file=sys.stderr)
    mqtt.subscribe(f'{mqttDiscoveryTopic}/status')
  else:
    raise MqttException(f'Failed to connect to MQTT: code {rc}')

def mqttMessage(mqtt, userdata, msg):
    if msg.payload.decode() == 'online':
      mqttDiscover(mqtt)

def mqttPublish(mqtt, topic, info):
  result = mqtt.publish(topic, json.dumps(info))
  status = result[0]
  if status != 0:
    raise MqttException(f'Failed to send message to MQTT topic: {topic}') 

def mqttDiscover(mqtt):
  with open('teleinfo.yml', 'r') as file:
    config = yaml.safe_load(file)

  device = config['device']
  entities = config['entities']
  for key, entity in entities.items():
    keyLow = key.lower()
    entity['device'] = device
    entity['enabled_by_default'] = True
    entity['name'] = f'Teleinfo {key}'
    entity['state_topic'] = mqttStateTopic
    entity['unique_id'] = f'teleinfo_{keyLow}'
    entity['value_template'] = '{{ value_json.' + key.upper() + ' }}'
    mqttPublish(mqtt, f'{mqttDiscoveryTopic}/sensor/teleinfo/{keyLow}/config', entity)

print('Starting teleinfo', file=sys.stderr)

while True:
  try:
    mqtt = paho.mqtt.client.Client(client_id=mqttClientId)
    mqtt.username_pw_set(mqttUsername, mqttPassword)
    mqtt.on_connect = mqttConnect
    mqtt.on_message = mqttMessage
    mqtt.connect(mqttHost, mqttPort)
    mqtt.loop_start()
    mqttDiscover(mqtt)
    with serial.Serial( port=port,
                        baudrate=baudrate,
                        parity=serial.PARITY_EVEN,
                        stopbits=serial.STOPBITS_ONE,
                        bytesize=serial.SEVENBITS) as teleinfo:
      while True:
        data = []
        line = teleinfo.readline()
        if debug:
           print(datetime.datetime.now(), file=sys.stderr, end='')
           print(' - ' + line.decode(), file=sys.stderr)
        data = line.decode().strip('\r\n').split(' ')
        if data:
          if receive(data, info):
            if (time.time() - lastPublish) > publishInterval :
              mqttPublish(mqtt, mqttStateTopic, info)
              info = {}
              lastPublish = time.time()
  except (serial.serialutil.SerialException, MqttException) as e:
    print(e, file=sys.stderr)
    time.sleep(30)
