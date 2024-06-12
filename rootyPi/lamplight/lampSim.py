from pathlib import Path
import threading
import paho.mqtt.client as PahoMQTT
import time
from queue import Queue
import datetime
from datetime import datetime
import json
import requests

P = Path(__file__).parent.absolute()
SETTINGS = P / 'settings.json'

class LampSimulator:
    def __init__(self, simId,  baseTopic, plantCode,models):
        self.simId = simId
        self.active = True
        self.isAuto = True
        self.isOn = True
        self.maxIntensity = self.getMaxLux(models,plantCode) #lux?
        self.percentIntensity = 100
        self.pubTopic = baseTopic + "/lampLight"
        self.subTopic = baseTopic + "/lightShift/+" #check with Simone
        self.plantCode = plantCode
        self.aliveTopic = baseTopic + "/alive"
        self.aliveBn = "updateCatalogDevice"
        self.myPub = MyPublisher(self.simId + "Pub", self.pubTopic)
        self.mySub = MySubscriber(self.simId + "Sub", self.subTopic)
        self.myPub.start()
        self.mySub.start()

    def getMaxLux(self,models,plantCode):
        code=plantCode[0:2]
        found=0
        for model in models:
            if model['model_code']==code:
                maxIntensity=model["max_lux"]
                found=1
                break

        if found==0:
            maxIntensity=900
        return maxIntensity

    def stop(self):
        self.mySub.stop()
        self.myPub.stop()
    def setActiveFalse(self):
        self.active = False
    def setActiveTrue(self):
        self.active = True
        

class MyPublisher:
    def __init__(self, clientID, topic):
        self.clientID = clientID  + "lamp"
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
        try:
            with open(SETTINGS, "r") as fs:                
                self.settings = json.loads(fs.read())            
        except Exception:
            print("Problem in loading settings")
        self.messageBroker = self.settings["messageBroker"]
        self.port = self.settings["brokerPort"]
        self.topic = topic

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
        self.q.put(msg)
        print ("Topic:'" + msg.topic+"', QoS: '"+str(msg.qos)+"' Message: '"+str(msg.payload) + "'")


def update_simulators(simulators):
    try:
        with open(SETTINGS, "r") as fs:                
            settings = json.loads(fs.read())            
    except Exception:
        print("Problem in loading settings")
    url = settings["registry_url"] + "/plants"
    response = requests.get(url)
    plants = json.loads(response.text)

    req_models = requests.get(settings["registry_url"] + "/models")
    models = json.loads(req_models.text)

    for plant in plants:
        simId = plant["plantCode"]
        simId
        found = 0
        for sim in simulators:
            if sim.simId == simId:
                found = 1
        if found == 0:
            baseTopic = "RootyPy/" + plant["userId"] + "/" + plant["plantCode"]
            sim = LampSimulator(simId, baseTopic, plant["plantCode"],models)
            simulators.append(sim)
    for sim in simulators:
        found = 0
        for plant in plants:            
            sensId = plant["plantCode"]
            if sim.simId == sensId:
                found = 1
        if found == 0:
            simulators.remove(sim)

class AllPubs(threading.Thread):

    def __init__(self, ThreadID, name):
        """Initialise thread widh ID and name."""
        threading.Thread.__init__(self)
        self.ThreadID = ThreadID
        self.name = name
        #load all sensors
        self.simulators = []

    def run(self):
        """Run thread."""
        while True:
            update_simulators(self.simulators)
            print(len(self.simulators))
            for sim in self.simulators:
                if not sim.mySub.q.empty():
                    msg = sim.mySub.q.get()
                    if msg is None:
                        continue
                    else:
                        mess = json.loads(msg.payload)
                        sim.percentIntensity = mess["e"][0]["v"]
                event = {"n": "lampLight", "u": "lux", "t": str(time.time()), 
                        "v": float(sim.maxIntensity*sim.percentIntensity/100)}
                out = {"bn": sim.pubTopic,"e":[event]}
                print(out)
                sim.myPub.myPublish(json.dumps(out), sim.pubTopic)
                eventAlive = {"n": sim.plantCode + "/lampLight", "u": "IP", "t": str(time.time()), "v": ""}
                outAlive = {"bn": sim.aliveBn,"e":[eventAlive]}
                print(outAlive)
                print(sim.aliveTopic)
                sim.myPub.myPublish(json.dumps(outAlive), sim.aliveTopic)
                time.sleep(2)
            time.sleep(10)

if __name__ == '__main__':

    thredPub = AllPubs(1, "AllPubs")
    print("Starting all publishers")
    thredPub.start()