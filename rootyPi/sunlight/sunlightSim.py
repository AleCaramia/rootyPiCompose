from pathlib import Path
import threading
import numpy as np
import paho.mqtt.client as PahoMQTT
import time
from queue import Queue
import datetime
from datetime import datetime
import json
import requests

P = Path(__file__).parent.absolute()
SETTINGS = P / 'settings.json'
def gaussian(x, mu, sig):
    return (
        1.0 / (np.sqrt(2.0 * np.pi) * sig) * np.exp(-np.power((x - mu) / sig, 2.0) / 2)
    )
def sunnyDaySim():#total lux daily 47000 with peak at 13
    out = 50000*gaussian(np.linspace(0, 24, 24), 13, 3)
    return out.tolist()

class SunlightSimulator:
    def __init__(self, simId, baseTopic, plantCode):
        self.simId = simId
        self.active = True
        self.luxList = sunnyDaySim()
        self.pubTopic = baseTopic + "/sunlight"
        self.plantCode = plantCode
        self.aliveTopic = baseTopic + "/alive"
        self.aliveBn = "updateCatalogDevice"
        self.myPub = MyPublisher(self.simId + "Pub", self.pubTopic)
        self.myPub.start()
        
    def stop(self):
        self.myPub.stop()
    def setActiveFalse(self):
        self.active = False
    def setActiveTrue(self):
        self.active = True
        

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


def update_simulators(simulators):
    try:
        with open(SETTINGS, "r") as fs:                
            settings = json.loads(fs.read())            
    except Exception:
        print("Problem in loading settings")
    url = settings["registry_url"] + "/plants"
    response = requests.get(url)
    plants = json.loads(response.text)
    for plant in plants:
        sensId = plant["plantCode"] + "_sunlight"
        sensId
        found = 0
        for sim in simulators:
            if sim.simId == sensId:
                found = 1
        if found == 0:
            baseTopic = "RootyPy/" + plant["userId"] + "/" + plant["plantCode"]
            sim = SunlightSimulator(sensId, baseTopic, plant["plantCode"])
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
            index = datetime.now().hour
            print(len(self.simulators))
            for sim in self.simulators:
                event = {"n": "sunlight", "u": "lux", "t": str(time.time()), "v": float(sim.luxList[index])}
                out = {"bn": sim.pubTopic,"e":[event]}
                print(out)
                sim.myPub.myPublish(json.dumps(out), sim.pubTopic)
                eventAlive = {"n": sim.plantCode + "/sunlight", "u": "IP", "t": str(time.time()), "v": ""}
                outAlive = {"bn": sim.aliveBn,"e":[eventAlive]}
                print(outAlive)
                sim.myPub.myPublish(json.dumps(outAlive), sim.aliveTopic)
                time.sleep(2)
            time.sleep(10)

def main():
    #thredSub = AllSubs(1, "AllSubs")
    thredPub = AllPubs(1, "AllPubs")
    #print("Starting all subscribers")
    #thredSub.start()
    print("Starting all publishers")
    thredPub.start()

if __name__ == '__main__':
    main()
    