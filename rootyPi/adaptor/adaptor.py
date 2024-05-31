from datetime import datetime
from influxdb_client import InfluxDBClient, Point, WritePrecision, BucketRetentionRules
from influxdb_client.client.write_api import SYNCHRONOUS
import json
import cherrypy
import paho.mqtt.client as PahoMQTT
import time
import threading
from pathlib import Path
import os
import requests

P = Path(__file__).parent.absolute()
SETTINGS = P / "settings.json"

def senmlToInflux(senml, plantId):
    output = []   
    for e in senml["e"]:
        point = {
        "measurement":"",
        "tags":"",
        "fields": ""
        }
        point["measurement"] = plantId
        point["tags"] = {"unit": e["u"]}
        point["fields"] = {e["n"]:e["v"]}
        output.append(point)
    return output  
class Adaptor(object):
    exposed=True
    def __init__(self):
        with open(SETTINGS, 'r') as file:
                settings = json.load(file)
        self.token = settings["influx_token"]
        self.org = settings["influx_org"]
        self.url = settings["adaptor_url"]
        self.influxUrl = settings["url_db"]
        self.registryBaseUrl = settings["registry_url"]
        self.possServices = settings["services4db"]
        self.client = InfluxDBClient(url=self.influxUrl, token=self.token)
        self.bucket_api = self.client.buckets_api()
        self.loadUsers()
        
    def loadUsers(self):
        url = self.registryBaseUrl + "/users"
        input = requests.get(url)
        self.users = json.loads(input._content)
    def checkUserPresent(self, userId):
        for user in self.users:
            if user["userId"] == userId:
                return True
        return False
    def checkPlantPresent(self,userId, plantId):
        for user in self.users:
            if user["userId"] == userId:
                for plant in user["plants"]:
                    if plant["plantId"] == plantId:
                        return True
        return False
                
    def start(self):
        conf={
            '/':{
            'request.dispatch':cherrypy.dispatch.MethodDispatcher(),
            'tools.sessions.on':True
            }
        }
        cherrypy.tree.mount(self,'/',conf)
        cherrypy.config.update({'server.socket_port': 8080})
        cherrypy.config.update({'server.socket_host':'0.0.0.0'})
        cherrypy.engine.start()
        #cherrypy.engine.block()
        
    def stop(self):
        pass
        
    def GET(self,*uri,**params):
        #http://localhost:8080/getData/user1/plant1?measurament=humidity&duration=1 
        if len(uri)!=0:
            if uri[0] == "getData":
                print(1)
                if self.checkUserPresent(uri[1]):
                    if self.checkPlantPresent(uri[1],uri[2]): 
                        if params["measurament"] in self.possServices:
                            try:
                                duration = int(params["duration"])
                            except:
                                raise cherrypy.HTTPError("400", "invalid duration")
                            bucket = uri[1]
                            #query = f'from(bucket:"{bucket}") |> range(start: -1h) |> filter(fn:(r) => r["_measurement"] == "plant1"))'#test query    
                            query = f'from(bucket: "{bucket}") \
                                |> range(start: -{duration}h) \
                                    |> filter(fn: (r) => r["_measurement"] == "{uri[2]}") \
                                        |> filter(fn: (r) => r["_field"] == "{params["measurament"]}")'
                            tables = self.client.query_api().query(org=self.org, query=query)
                            out = []
                            for table in tables:
                                for row in table.records:
                                    line = {"t": row.get_time().strftime("%m/%d/%Y, %H:%M:%S"), "v": row.get_value()}
                                    #print(line)
                                    print(type(row.get_time()))
                                    out.append(line)
                                    #out = out + (f"Time: {row.get_time().strftime("%m/%d/%Y, %H:%M:%S")}, Value: {row.get_value()}\n")
                            return json.dumps(out)
                    else:
                        raise cherrypy.HTTPError("400", "Invalid plantId")                    
                else:
                    raise cherrypy.HTTPError("400", "Invalid User")
            else:
                raise cherrypy.HTTPError("400", "Invalid operation")
        else:
            raise cherrypy.HTTPError("400", "no uri")

    def PUT(self,*uri,**params):
        return  
    
    def POST(self,*uri,**params):
        if uri[0] == "addUser":
            body = json.loads(cherrypy.request.body.read())  # Read body data
            self.addUserBuckets(body["userId"])
            response = {"status": "OK", "code": 200}
            return response 
    def DELETE(self,*uri,**params):
        if uri[0] == "deleteUser":
            self.deleteUserBuckets(uri[1])
            print(f"Deleted {uri[1]}'s buckets")
            response = {"status": "OK", "code": 200}
            return response             
    def addUserBuckets(self, userID):  
        retention_rules = BucketRetentionRules(type="expire", every_seconds=2592000)
        created_bucket = self.bucket_api.create_bucket(bucket_name=f"{userID}", retention_rules = retention_rules,org = self.org)
        print(created_bucket)
    def listBuckets(self):
        buckets = self.bucket_api.find_buckets().buckets
        return buckets
    def deleteUserBuckets(self, userID):
        buckets = self.listBuckets()
        for bucket in buckets:
            if bucket.name.startswith(userID):
                self.bucket_api.delete_bucket(bucket)
                print(f"Succesfully deleted bucket: {bucket.name}")

class MySubscriber:
        def __init__(self, clientID, topic, broker, port, write_api):
            self.clientID = clientID
			# create an instance of paho.mqtt.client
            self._paho_mqtt = PahoMQTT.Client(clientID, False) 
            
			# register the callback
            self._paho_mqtt.on_connect = self.myOnConnect
            self._paho_mqtt.on_message = self.myOnMessageReceived 
            self.write_api = write_api
            self.topic = topic
            self.messageBroker = broker
            self.port = port
            with open(SETTINGS, 'r') as file:
                data = json.load(file)
            self.services2register = data["services4db"]
            self.org = data["influx_org"]
            self.registry_url = data["registry_url"]
            url = self.registry_url + "/users"
            response = requests.get(url)
            self.users = json.loads(response.text)

        def update_users(self):
            url = self.registry_url + "/users"
            response = requests.get(url)
            self.users = json.loads(response.text)

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
        def checkUserPlantPresence(self, userId, plantCode):
            self.update_users()
            print(self.users)
            for user in self.users:
                if user["userId"] == userId:
                    for plant in user["plants"]:
                        if plant == plantCode:
                            return True
            return False
            
        def myOnMessageReceived (self, paho_mqtt , userdata, msg):
            if len(msg.topic.split("/")) > 3:
                userId = msg.topic.split("/")[1]
                plantCode = msg.topic.split("/")[2]
                service = msg.topic.split("/")[3]                
                if service in self.services2register and self.checkUserPlantPresence(userId, plantCode):
                    converted = senmlToInflux(json.loads(msg.payload), plantCode)
                    for c in converted:
                        print(c)                
                        self.write_api.write(bucket=userId, org=self.org, record= c)


# Threads
class MQTTreciver(threading.Thread):

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
        self.client = InfluxDBClient(url=data["url_db"], token=data["influx_token"])
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)

    def run(self):
        """Run thread."""
        global time_flag
        print(self.topic)
        # Start subscriber.
        sub = MySubscriber("J", self.topic, self.broker, self.mqtt_port, self.write_api)
        sub.start()

        while True:
            time.sleep(1)

if __name__ == '__main__':
    adaptor = Adaptor()
    adaptor.start()
    
    reciver = MQTTreciver(1, "mqttReciver")
    reciver.run()
