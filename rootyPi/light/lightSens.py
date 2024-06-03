from pathlib import Path
import threading
import paho.mqtt.client as PahoMQTT
import time
import random
from queue import Queue
import datetime
import json
import requests

P = Path(__file__).parent.absolute()
SETTINGS = P / 'settings.json'

class LightSens:
    def __init__(self, sensorId, baseTopic, plantCode):#baseTopic = "rootyPi/userId/plantId/"
        self.sensorId = sensorId
        self.sunLight = 0
        self.artificialLight = 0
        self.currentState = 0
        self.active = True
        self.pubTopic = baseTopic + "/light"
        self.subTopic = baseTopic + "/+"
        self.aliveBn = "updateCatalogDevice"
        self.plantCode = plantCode
        self.aliveTopic = baseTopic + "/alive"
        self.myPub = MyPublisher(self.sensorId + "Pub", self.pubTopic)
        self.mySub = MySubscriber(self.sensorId + "Sub1", self.subTopic)
        self.myPub.start()
        self.mySub.start()
        
    def stop(self):
        self.mySub.stop()
        self.myPub.stop()
    def setActiveFalse(self):
        self.active = False
    def setActiveTrue(self):
        self.active = True
        
    
        
    
def update_sensors(sensors):
    try:
        with open(SETTINGS, "r") as fs:                
            settings = json.loads(fs.read())            
    except Exception:
        print("Problem in loading settings")
    url = settings["registry_url"] + "/plants"
    response = requests.get(url)
    plants = json.loads(response.text)
    for plant in plants:
        sensId = plant["plantCode"]
        sensId
        found = 0
        for sens in sensors:
            if sens.sensorId == sensId:
                found = 1
        if found == 0:
            baseTopic = "RootyPy/" + plant["userId"] + "/" + plant["plantCode"]
            sens = LightSens(sensId, baseTopic, plant["plantCode"])
            sensors.append(sens)
    for sens in sensors:
        found = 0
        for plant in plants:
            
            sensId = plant["plantCode"]
            if sens.sensorId == sensId:
                found = 1
        if found == 0:
            sensors.remove(sens)
    
class MyPublisher:
    def __init__(self, clientID, topic):
        self.clientID = clientID
        self.topic = topic
		# create an instance of paho.mqtt.client
        self._paho_mqtt = PahoMQTT.Client(self.clientID, False) 
		# register the callback
        self._paho_mqtt.on_connect = self.myOnConnect

        try:
            with open(SETTINGS, "r") as fs:                
                self.settings = json.loads(fs.read())            
        except Exception:
            print("Problem in loading settings")
        self.messageBroker = self.settings["messageBroker"]
        self.port = self.settings["brokerPort"]
		#self.messageBroker = '192.168.1.5'

    def start (self):
		#manage connection to broker
        self._paho_mqtt.connect(self.messageBroker, self.port)
        self._paho_mqtt.loop_start()

    def stop (self):
        self._paho_mqtt.loop_stop()
        self._paho_mqtt.disconnect()

    def myPublish(self, message, topic):
		# publish a message with a certain topic
        self._paho_mqtt.publish(topic, message, 2)

    def myOnConnect (self, paho_mqtt, userdata, flags, rc):
        print ("Connected to %s with result code: %d" % (self.messageBroker, rc))

class MySubscriber:
    def __init__(self, clientID, topic):
        self.clientID = clientID
        self.q = Queue()
		# create an instance of paho.mqtt.client
        self._paho_mqtt = PahoMQTT.Client(clientID, False) 
		# register the callback
        self._paho_mqtt.on_connect = self.myOnConnect
        self._paho_mqtt.on_message = self.myOnMessageReceived
        self.topic = topic
        try:
            with open(SETTINGS, "r") as fs:                
                self.settings = json.loads(fs.read())            
        except Exception:
            print("Problem in loading settings")
        self.messageBroker = self.settings["messageBroker"]
        self.port = self.settings["brokerPort"]
		#self.messageBroker = '192.168.1.5'

    def start (self):
		#manage connection to broker
        self._paho_mqtt.connect(self.messageBroker, self.port)
        self._paho_mqtt.loop_start()
		# subscribe for a topic
        self._paho_mqtt.subscribe(self.topic, 2)

    def stop (self):
        self._paho_mqtt.unsubscribe(self.topic)
        self._paho_mqtt.loop_stop()
        self._paho_mqtt.disconnect()

    def myOnConnect (self, paho_mqtt, userdata, flags, rc):
        print ("Connected to %s with result code: %d" % (self.messageBroker, rc))

    def myOnMessageReceived (self, paho_mqtt , userdata, msg):
		# A new message is received
        if msg.topic.split("/")[3] in ["lampLight", "sunlight"]:
            self.q.put(msg)
            print ("Topic:'" + msg.topic+"', QoS: '"+str(msg.qos)+"' Message: '"+str(msg.payload) + "'")

class AllSens(threading.Thread):

    def __init__(self, ThreadID, name):
        """Initialise thread widh ID and name."""
        threading.Thread.__init__(self)
        self.ThreadID = ThreadID
        self.name = name
        #load all sensors
        self.sensors = []

    def run(self):
        """Run thread."""
        while True:
            update_sensors(self.sensors)
            print(len(self.sensors))
            for sens in self.sensors:
                if not sens.mySub.q.empty():
                    msg = sens.mySub.q.get()
                    if msg is None:
                        continue
                    else:
                        mess = json.loads(msg.payload.decode("utf-8"))
                        event = mess["e"][0]
                        if msg.topic.split("/")[3] == "lampLight":
                            print("-------lampLight")
                            if isinstance(event["v"], int):
                                sens.artificialLight = event["v"]
                        elif msg.topic.split("/")[3] == "sunlight":
                            print("-----------sunlight")
                            if isinstance(event["v"], int):
                                sens.sunLight = event["v"]                       
                sens.currentState = sens.artificialLight + sens.sunLight
                print(f"current state {sens.currentState}")
                event = {"n": "light", "u": "lux", "t": str(time.time()), "v": float(sens.currentState)}
                out = {"bn": sens.pubTopic,"e":[event]}
                print(out)
                sens.myPub.myPublish(json.dumps(out), sens.pubTopic)
                eventAlive = {"n": sens.plantCode+"/light", "u": "IP", "t": str(time.time()), "v": ""}
                outAlive = {"bn": sens.aliveBn ,"e":[eventAlive]}
                print("++++++++++++")
                print("++++++++++++")
                print( outAlive)
                sens.myPub.myPublish(json.dumps(outAlive), sens.aliveTopic)
                time.sleep(2)
            time.sleep(10)

if __name__ == '__main__':
    
    thredPub = AllSens(3, "AllPubs")
    print("Starting all publishers")
    thredPub.start()