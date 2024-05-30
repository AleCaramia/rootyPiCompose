import json
import cherrypy
import time
import requests
import threading
import paho.mqtt.client as PahoMQTT
from pathlib import Path


P = Path(__file__).parent.absolute()
CATALOG = P / 'catalog.json'
SETTINGS = P / 'settings.json'
INDEX = P / 'index.html'
MAXDELAY = 30


class Catalog(object):
    def __init__(self):
        self.filename_catalog = CATALOG
        self.load_file()
    
    def load_file(self):
        try:
            with open(self.filename_catalog, "r") as fs:                
                self.catalog = json.loads(fs.read())            
        except Exception:
            print("Problem in loading catalog")

        #self.broker_ip = self.service["broker"]["IP"]
        #self.mqtt_port = self.service["broker"]["mqtt_port"]

    def write_catalog(self):
        """Write data on service json file."""
        with open(self.filename_catalog, "w") as fs:
            json.dump(self.catalog, fs, ensure_ascii=False, indent=2)
            fs.write("\n")

    def add_device(self, device_json, user):
        self.load_file()
        flag = 0
        for dev in self.catalog["devices"]:
            if dev["deviceID"] == device_json["deviceID"]:
                flag = 1
        if flag == 0:
            device_res_json = {
                "deviceID": device_json["deviceID"],
                "Services": device_json["Services"],
                "lastUpdate": time.time()
            }
            self.catalog["devices"].append(device_res_json)
        self.write_catalog()

    def add_service(self, service_json , user):
        self.load_file()
        flag = 0
        for service in self.catalog["services"]:
            if service["serviceID"] == service_json["serviceID"]:
                flag = 1
        if flag == 0:
            service_res_json = {
                "serviceID": service_json["serviceID"],
                "lastUpdate": time.time()
            }
            self.catalog["services"].append(service_res_json)
        self.write_catalog()
    #todo 
    def add_user(self, user_json):
        self.load_file()
        found = 0
        for user in self.catalog["users"]:
            if user["userId"] == user_json["userId"]:
                found = 1
        if found == 0:
            user_json = {
                "userId": user_json["userId"],
                "password": user_json["password"],
                "plants": []
            }
            self.catalog["users"].append(user_json)
            self.write_catalog()
            return "Added user"
        else:
            return "User already registered"
    def remove_user(self, userId):
        self.load_file()
        found = 0
        index = 0
        for user in self.catalog["users"]:
            if user["userId"] == userId:
                found = 1
                del self.catalog["users"][index]
                self.write_catalog()
            index += 1
        if found == 0:
            return "User not found"
            
    def add_plant(self, plant_json):
        self.load_file()
        found = 0
        foundP = 0
        valideCode = False
        for mod in self.catalog["models"]:
            if plant_json["plantCode"].startswith(mod["model_code"]):
                validCode = True
        if not validCode:
            return "Invalid plant code"
        for user in self.catalog["users"]:
            if user["userId"] == plant_json["userId"]:
                found = 1
                for plant in user["plants"]:
                    if plant == plant_json["plantCode"]:
                        foundP = 1
                        return "Plant already registered"
                if foundP == 0:
                    plant_res ={
                        "userId": plant_json["userId"],
                        "plantId": plant_json["plantId"],
                        "plantCode": plant_json["plantCode"],
                        "type": plant_json["type"]
                    }
                    user["plants"].append(plant_json["plantCode"])
                    self.catalog["plants"].append(plant_json)
                    self.write_catalog()
                    return "done"
        if found == 0:
            return "User not found"
    def removeFromPlants(self, plantCode):
        index = 0
        for plant in self.catalog["plants"]:
            if plant["plantCode"] == plantCode:
                del self.catalog["plants"][index]
            index +=1
    def remove_plant(self, userId, plantCode):
        self.load_file()
        found = 0
        foundP = 0
        for user in self.catalog["users"]:
            if user["userId"] == userId:
                found = 1
                for plant in user["plants"]:
                    if plant == plantCode:
                        foundP = 1
                        user["plants"].remove(plant)
                        self.removeFromPlants(plantCode)
                        self.write_catalog()
                        return "Plant removed"
                if foundP == 0:
                    return "Plant not found"
        if found == 0:
            return "User not found"

    def update_device(self, deviceID, service):
        """Update timestamp of a device.
        Update timestamp or insert it again in the resource catalog if it has
        expired.
        """
        print(deviceID, service)
        self.load_file()
        found = 0
        for dev in self.catalog['devices']:
            if dev['deviceID'] == deviceID:
                found = 1
                print("Updating %s timestamp." % deviceID)
                dev['lastUpdate'] = time.time()    
        if not found:# Insert again the device
            print("not found")
            device_json = {
                "deviceID": deviceID,
                "lastUpdate": time.time()
            }
            self.catalog["devices"].append(device_json)
        self.write_catalog()

    
    def remove_old_device(self):
        """Remove old devices whose timestamp is expired.
        Check all the devices whose timestamps are old and remove them from
        the resource catalog.
        """
        self.load_file()
        removable = []
        for counter, d in enumerate(self.catalog['devices']):
            #print(counter, d)
            if time.time() - d['lastUpdate'] > MAXDELAY:
                print("Removing... %s" % (d['deviceID']))
                removable.append(counter)
        for index in sorted(removable, reverse=True):
                #print (p['device_list'][index])
                del self.catalog['device_list'][index]
        #print(self.resource)
        self.write_catalog()

class Webserver(object):
    """CherryPy webserver."""
    exposed = True
    def start(self):
        conf={
            '/':{
            'request.dispatch':cherrypy.dispatch.MethodDispatcher(),
            'tools.sessions.on':True
            }
        }
        cherrypy.tree.mount(self,'/',conf)
        cherrypy.config.update({'server.socket_port':8081})
        cherrypy.config.update({'server.socket_host':'0.0.0.0'})
        cherrypy.engine.start()
        #cherrypy.engine.block()
        try:
            with open(SETTINGS, "r") as fs:                
                self.settings = json.loads(fs.read())            
        except Exception:
            print("Problem in loading settings")

    #@cherrypy.tools.json_out()
    def GET(self, *uri, **params):
        """Define GET HTTP method for RESTful webserver."""
        cat = Catalog()
        cat.load_file()
        # Get Devices catalog json.
        if len(uri) == 0:
            return open(INDEX)
        else:            
            if uri[0] == 'devices':
                return json.dumps(cat.catalog["devices"])
            # Get Devices catalog json.
            if uri[0] == 'services':
                return json.dumps(cat.catalog["services"])
            if uri[0] == 'users':
                return json.dumps(cat.catalog["users"])
            if uri[0] == 'models':
                return json.dumps(cat.catalog["models"])
            if uri[0] == 'plants':
                return json.dumps(cat.catalog["plants"])
        

    def POST(self, *uri, **params):
        """Define POST HTTP method for RESTful webserver.Modify content of catalogs"""  
        # Add new device.
        if uri[0] == 'addd':
            body = json.loads(cherrypy.request.body.read())  # Read body data
            cat = Catalog()
            print(json.dumps(body))
            cat.add_device(body, uri[1])#(device, user)
            return 200
        
        if uri[0] == 'adds':
            body = json.loads(cherrypy.request.body.read())  # Read body data
            cat = Catalog()
            print(json.dumps(body))
            cat.add_service(body, uri[1])
            return 200
        if uri[0] == 'addu':
            body = json.loads(cherrypy.request.body.read())  # Read body {userid, password}
            cat = Catalog()
            out = cat.add_user(body)
            print(out)
            if out == "User already registered":
                response = {"status": "NOT_OK",
                            "code": 400}
                #raise cherrypy.HTTPError("400", "User already registered")
                return json.dumps(response)
            else:
                
                headers = {'content-type': 'application/json; charset=UTF-8'}
                response = requests.post(self.settings["adaptor_url"] + "/addUser", data=json.dumps(body), headers=headers)
                response = {"status": "OK", "code": 200, "message": "Data processed"}
                return json.dumps(response)
                
        if uri[0] == 'addp':
            body = json.loads(cherrypy.request.body.read())  # Read body data
            cat = Catalog()
            print(json.dumps(body))
            out = cat.add_plant(body)
            if out == "Plant already registered":
                response = {"status": "NOT_OK", "code": 400, "message": "Plant already registered"}
                return json.dumps(response)
            elif out == "User not found":
                response = {"status": "NOT_OK", "code": 400, "message": "User not found"}
                return json.dumps(response)
            elif out == "done":
                response = {"status": "OK", "code": 200, "message": "Plant registered successfully"}
                return json.dumps(response)
            elif out == "Invalid plant code":
                response = {"status": "NOT_OK", "code": 400, "message": "Invalid plant code"}
    def DELETE(self, *uri, **params):
        if uri[0] == 'rmu':
            cat = Catalog()
            out = cat.remove_user(uri[1])
            print(out)
            if out == "User not found":
                response = {"status": "NOT_OK",
                            "code": 400}
                #raise cherrypy.HTTPError("400", "User already registered")
                return json.dumps(response)
            else:
                headers = {'content-type': 'application/json; charset=UTF-8'}
                response = requests.delete(self.settings["adaptor_url"] + "/deleteUser/" + uri[1])
                response = {"status": "OK", "code": 200}
                return json.dumps(response)
                
        if uri[0] == 'rmp':
            cat = Catalog()
            out = cat.remove_plant(uri[1], uri[2])
            if out == "User not found":
                raise cherrypy.HTTPError("400", "user not found")
            if out == "Plant not found":
                raise cherrypy.HTTPError("400", "plant not found")
            else:
                print("success")
                result = {"status": "OK", "code": 200, "message": "Data processed"}
                return json.dumps(result)

class MySubscriber:
        def __init__(self, clientID, topic, broker, port):
            self.clientID = clientID
			# create an instance of paho.mqtt.client
            self._paho_mqtt = PahoMQTT.Client(clientID, False) 
            
			# register the callback
            self._paho_mqtt.on_connect = self.myOnConnect
            self._paho_mqtt.on_message = self.myOnMessageReceived 
            self.topic = topic
            self.messageBroker = broker
            self.port = port
            print(port)
            print(broker)



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
            msg.payload = msg.payload.decode("utf-8")
            message = json.loads(msg.payload)
            catalog = Catalog()
            devID = message['bn'].replace("rootyPi/", "")
            #devID = devID.split('/')[0]
            print("test")
            try:
                for e in message['e']:
                    j = json.loads(e)
                    if float(j['t']) > 0:
                        print(j["t"])
                        service = j['n']
                        print("devID")
                        catalog.update_device(devID, service)
            except Exception:
                pass

# Threads
class First(threading.Thread):
    """Thread to run CherryPy webserver."""
    exposed=True
    def __init__(self, ThreadID, name):
        """Initialise thread widh ID and name."""
        threading.Thread.__init__(self)
        self.ThreadID = ThreadID
        self.name = name
        self.webserver = Webserver()
        self.webserver.start()
        

class Second(threading.Thread):
    """MQTT Thread.
    Subscribe to MQTT in order to update timestamps of sensors in the dynamic
    part of the catalog.
    """

    def __init__(self, ThreadID, name):
        """Initialise thread widh ID and name."""
        threading.Thread.__init__(self)
        self.ThreadID = ThreadID
        self.name = name
        with open(SETTINGS, 'r') as file:
            data = json.load(file)
        self.topic = data["base_topic"]
        self.broker = data["broker"]
        self.mqtt_port = int(data["port"])

    def run(self):
        """Run thread."""
        cat = Catalog()
        cat.load_file()
        sub = MySubscriber("Sub1", self.topic, self.broker, self.mqtt_port)
        sub.loop_flag = 1
        sub.start()

        while sub.loop_flag:
            #print("Waiting for connection...")
            time.sleep(1)

        while True:
            time.sleep(1)

        sub.stop()

class Third(threading.Thread):
    """Old device remover thread.
    Remove old devices which do not send alive messages anymore.
    Devices are removed every five minutes.
    """

    def __init__(self, ThreadID, name):
        """Initialise thread widh ID and name."""
        threading.Thread.__init__(self)
        self.ThreadID = ThreadID
        self.name = self.name

    def run(self):
        """Run thread."""
        time.sleep(MAXDELAY+1)
        while True:
            cat = Catalog()
            cat.remove_old_device()
            time.sleep(MAXDELAY+1)

#Main

def main():
    """Start all threads."""
    thread1 = First(1, "CherryPy")
    thread2 = Second(2, "Updater")
    thread3 = Third(3, "Remover")

    print("> Starting CherryPy...")
    thread1.start()

    time.sleep(1)
    print("\n> Starting MQTT device updater...")
    thread2.start()

    time.sleep(1)
    print("\n> Starting remover...\nDelete old devices every %d seconds."% MAXDELAY)
    thread3.start()

if __name__ == '__main__':
    main()