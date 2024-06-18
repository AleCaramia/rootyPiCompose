import json
import requests
import time
import datetime
import paho.mqtt.client as pahoMQTT
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from io import BytesIO
from PIL import Image
import base64
import threading
import cherrypy
import schedule


def convert_timestamps(timestamps, duration):
    """
    Converts a list of timestamps from the format '%Y-%m-%d %H:%M:%S' into 
    '%m-%d' or '%m-%d-%H:%M:%S' based on the duration.

    Parameters:
    timestamps (list of str): List of timestamps in the format '%Y-%m-%d %H:%M:%S'.
    duration (int): The duration to determine the format of conversion.

    Returns:
    list of str: List of converted timestamps in the specified format.
    """
    converted_timestamps = []
    
    if duration > 6 * 24:
        # Convert to '%m-%d' format
        for ts in timestamps:
            dt = ts[:10]
            converted_timestamps.append(dt)
    else:
        # Convert to '%m-%d-%H:%M:%S' format
        for ts in timestamps:
            dt = ts[11:]
            converted_timestamps.append(dt)
    
    return converted_timestamps

class Report_generator(object):
            
    exposed = True

    def __init__(self,config_path,stop_event):
        config =  json.load(open(config_path,'r'))
        self.registry_url = config['url_registry']
        self.url_adaptor = config['url_adaptor']
        #self.registry_url = 'http://127.0.0.1:8080'
        self.headers = config['headers']
        self.ID = config['ID']
        self.broker = config['broker']
        self.port = config['port']
        self.start_time = time.time()
        self.actual_time = time.time()
        self.time_zone_correction = 2
        self.interval = 2
        self.stop_event = stop_event
        self.start_web_server( )

    def start_web_server(self):


        conf={
            '/':{
            'request.dispatch':cherrypy.dispatch.MethodDispatcher(),
            'tools.sessions.on':True
            }
        }
        cherrypy.tree.mount(self,'/',conf)
        cherrypy.config.update({'server.socket_port': 8081})
        cherrypy.config.update({'server.socket_host':'0.0.0.0'})
        cherrypy.engine.start()
        print('report generator server exposed')
        #cherrypy.engine.block()
        
    def stop_server(self):
        pass


    def plot_lux_intensity(self, sunlight_timestamps, sunlight_lux, lamp_timestamps, lamp_lux):
        """
        Plots the lux intensity values over time for sunlight and lamp separately.
        
        :param sunlight_timestamps: List of timestamps for sunlight.
        :param sunlight_lux: List of lux values for sunlight.
        :param lamp_timestamps: List of timestamps for lamp.
        :param lamp_lux: List of lux values for lamp.
        :return: BytesIO object containing the plot image.
        """
        # Function to clean and convert timestamps to datetime format
        def clean_and_convert_timestamps(timestamps):
            return pd.to_datetime(timestamps.str.strip(), format='%H:%M:%S')
        
        # Create dataframes for both sunlight and lamp data
        sunlight_df = pd.DataFrame({'timestamp': clean_and_convert_timestamps(pd.Series(sunlight_timestamps)), 'lux_sunlight': sunlight_lux})
        lamp_df = pd.DataFrame({'timestamp': clean_and_convert_timestamps(pd.Series(lamp_timestamps)), 'lux_lamp': lamp_lux})
        
        # Plot the lux intensity for sunlight
        plt.figure(figsize=(10, 6))
        plt.plot(sunlight_df['timestamp'], sunlight_df['lux_sunlight'], label='Sunlight Lux', marker='o', linestyle='-')
        
        # Set the title and labels for sunlight plot
        plt.title('Lux Intensity Over Time - Sunlight')
        plt.xlabel('Time')
        plt.ylabel('Lux Intensity')
        plt.legend()
        plt.grid(True)
        
        # Adjust x-axis ticks based on the number of samples for sunlight
        max_samples_sunlight = len(sunlight_timestamps)
        if max_samples_sunlight > 50:
            step_sunlight = 7
        elif max_samples_sunlight > 20:
            step_sunlight = 2
        else:
            step_sunlight = 1
        
        ax_sunlight = plt.gca()
        ax_sunlight.set_xticks(ax_sunlight.get_xticks()[::step_sunlight])
        plt.xticks(rotation=45)
        plt.tight_layout()
        
        # Save the sunlight plot to a BytesIO object
        buffer_sunlight = BytesIO()
        plt.savefig(buffer_sunlight, format='png')
        buffer_sunlight.seek(0)
        
        # Clear the plot for lamp lux intensity
        plt.clf()
        
        # Plot the lux intensity for lamp
        plt.figure(figsize=(10, 6))
        plt.plot(lamp_df['timestamp'], lamp_df['lux_lamp'], label='Lamp Lux', marker='x', linestyle='--')
        
        # Set the title and labels for lamp plot
        plt.title('Lux Intensity Over Time - Lamp')
        plt.xlabel('Time')
        plt.ylabel('Lux Intensity')
        plt.legend()
        plt.grid(True)
        
        # Adjust x-axis ticks based on the number of samples for lamp
        max_samples_lamp = len(lamp_timestamps)
        if max_samples_lamp > 50:
            step_lamp = 7
        elif max_samples_lamp > 20:
            step_lamp = 2
        else:
            step_lamp = 1
        
        ax_lamp = plt.gca()
        ax_lamp.set_xticks(ax_lamp.get_xticks()[::step_lamp])
        plt.xticks(rotation=45)
        plt.tight_layout()
        
        # Save the lamp plot to a BytesIO object
        buffer_lamp = BytesIO()
        plt.savefig(buffer_lamp, format='png')
        buffer_lamp.seek(0)
        
        # Combine both images into a single BytesIO object
        combined_buffer = BytesIO()
        plt.figure(figsize=(10, 6))
        plt.imshow(plt.imread(buffer_sunlight), extent=[0, 1, 0, 0.5])
        plt.imshow(plt.imread(buffer_lamp), extent=[0, 1, 0.5, 1])
        plt.axis('off')
        plt.tight_layout()
        plt.savefig(combined_buffer, format='png')
        combined_buffer.seek(0)
        
        return combined_buffer


    def plot_data(self, timestamps, values, color,title,yax):
        """
        Plots the soil moisture values over time.

        :param timestamps: List of timestamps.
        :param moisture_values: List of soil moisture values.
        :param color: Color of the plot line.
        :return: BytesIO object containing the plot image.
        """
        plt.figure(figsize=(10, 6))
        plt.plot(timestamps, values, label=yax, marker='o', linestyle='-', color=color)
        plt.title(title)
        plt.xlabel('Time')
        plt.ylabel(yax)
        plt.legend()
        plt.grid(True)


        plt.xticks(rotation=45)

        plt.tight_layout()

        # Save the plot to a BytesIO object
        buffer = BytesIO()
        plt.savefig(buffer, format='png')
        buffer.seek(0)

        return buffer

        
    def concatenate_images_vertically(self, buffer1, buffer2, buffer3):
        """
        Concatenates four images vertically from BytesIO buffers and returns a new BytesIO buffer containing the combined image.
        
        :param buffer1: BytesIO object containing the first image.
        :param buffer2: BytesIO object containing the second image.
        :param buffer3: BytesIO object containing the third image.
        :param buffer4: BytesIO object containing the fourth image.
        :return: BytesIO object containing the concatenated image.
        """
        # Load images from buffers
        image1 = Image.open(buffer1)
        image2 = Image.open(buffer2)
        image3 = Image.open(buffer3)

        
        # Get dimensions
        width1, height1 = image1.size
        width2, height2 = image2.size
        width3, height3 = image3.size

        
        # Create a new image with combined height
        total_height = height1 + height2 + height3
        max_width = max(width1, width2, width3)
        combined_image = Image.new('RGB', (max_width, total_height))
        
        # Paste images into the new image
        combined_image.paste(image1, (0, 0))
        combined_image.paste(image2, (0, height1))
        combined_image.paste(image3, (0, height1 + height2))

        
        # Save the combined image to a new BytesIO buffer
        combined_buffer = BytesIO()
        combined_image.save(combined_buffer, format='png')
        combined_buffer.seek(0)
        
        return combined_buffer

    def on_connect(self, client, userdata, flags, rc):
        """
        Callback function for when the client receives a CONNACK response from the server.
        
        :param client: The client instance for this callback.
        :param userdata: The private user data as set in Client() or userdata_set().
        :param flags: Response flags sent by the broker.
        :param rc: The connection result.
        """
        if rc == 0:
            print("Connected to MQTT Broker successfully")
        else:
            print(f"Failed to connect, return code {rc}\n")

    def calculate_dli(self,light_data):
        """
        Calculate the Daily Light Integral (DLI) from the light data vector.
        DLI is the total amount of light (in mol/m²/day) received over a 24-hour period.
        """
        total_light = sum(light_data)  # Sum of light intensity over 24 hours
        dli = total_light / len(light_data)  # Average light intensity per hour
        return dli

    def calculate_light_fluctuation(self,light_data):
        """
        Calculate the light fluctuation from the light data vector.
        Light fluctuation measures how much the light levels fluctuate throughout the day.
        """
        max_light = max(light_data)
        min_light = min(light_data)
        fluctuation = max_light - min_light
        return fluctuation

    def calculate_water_absorption(self,soil_moisture_data):
        """
        Calculate the water absorption rate from the soil moisture data.
        Water absorption rate indicates how quickly the plant uses the water administered.
        """
        initial_moisture = soil_moisture_data[0]
        final_moisture = soil_moisture_data[-1]
        water_absorption = initial_moisture - final_moisture
        return water_absorption

    def analyze_plant_conditions(self, DLI, light_fluctuation, soil_moisture_data, water_absorption):
        try:
            tips = []

            # Daily Light Integral (DLI) analysis
            if DLI < 35000:
                tips.append("Increase the amount of light your plant receives.")
            elif DLI > 60000:
                tips.append("Reduce the amount of light your plant receives.")

            # Light Fluctuation Analysis
            if light_fluctuation > 100:
                tips.append("Ensure more consistent lighting conditions for your plant.")

            flag_humidity = False
            # Check for narrow peaks in soil moisture
            peak_width_threshold = 50  # Threshold for narrow peaks
            for i in range(1, len(soil_moisture_data) - 1):
                if soil_moisture_data[i] > soil_moisture_data[i - 1] and soil_moisture_data[i] > soil_moisture_data[i + 1]:
                    peak_width = soil_moisture_data[i] - min(soil_moisture_data[i - 1], soil_moisture_data[i + 1])
                    if peak_width < peak_width_threshold:
                        flag_humidity = True
                        
            if flag_humidity:
                tips.append("Consider moving the plant to a more humid environment.")
            # Water Administration Efficiency
            if water_absorption < 0.5:
                tips.append("Check for root health or consider changing watering methods.")

            # Additional checks and tips
            if light_fluctuation < 20:
                tips.append("Check for potential shading or obstruction affecting light levels.")
            if max(soil_moisture_data) > 95:
                tips.append("Ensure proper drainage to prevent waterlogging and root rot.")
            if min(soil_moisture_data) < 10:
                tips.append("Water your plant more frequently to prevent dehydration.")
            if water_absorption > 90:
                tips.append("Monitor for signs of overwatering such as yellowing leaves or wilting.")
            if min(soil_moisture_data) > 80 and DLI < 20000:
                tips.append("During periods of low light and high soil moisture, reduce watering to avoid root suffocation.")
            if max(soil_moisture_data) < 20 and DLI > 40000:
                tips.append("In periods of high light and low soil moisture, increase watering to prevent wilting.")
            if DLI < 10000 and max(soil_moisture_data) < 40:
                tips.append("During periods of very low light and moderate soil moisture, increase the received light to prevent fungal diseases.")
            if light_fluctuation > 40000 and min(soil_moisture_data) > 10:
                tips.append("In cases of high light fluctuation and consistently high soil moisture, ensure proper ventilation to prevent mold growth.")

            if DLI > 40000 and water_absorption < 20:
                tips.append("In periods of high light and low water absorption, consider fertilizing to support plant growth.")
            if DLI < 10000 and water_absorption > 60:
                tips.append("During periods of low light and high water absorption, reduce fertilization to prevent nutrient buildup.")

            string_of_tips = ''
            for tip in tips:
                string_of_tips = string_of_tips + '\n' + tip

            return string_of_tips
        except Exception as e:
            print(f"Error analyzing plant conditions: {e}")

    def publish_image_via_mqtt(self, combined_buffer,message, mqtt_broker, mqtt_port, mqtt_topic):
        """
        Publishes an image and a message via MQTT.
        
        :param combined_buffer: BytesIO object containing the combined image.
        :param mqtt_broker: MQTT broker address.
        :param mqtt_port: MQTT broker port.
        :param mqtt_topic: MQTT topic to publish to.
        :param message: Message to include with the image.
        """
        client = pahoMQTT.Client()

        # Assign the on_connect callback function
        client.on_connect = self.on_connect

        client.connect(mqtt_broker, mqtt_port, 60)

        # Start the loop
        client.loop_start()

        # Convert image to base64 string
        combined_buffer.seek(0)
        image_base64 = base64.b64encode(combined_buffer.read()).decode('utf-8')

        # Create payload dictionary
        payload = {
            'bn': self.ID,"e":[{"n":'image',"u":"","t":time.time(),"v":image_base64},{"n":'message',"u":"","t":time.time(),"v":message}]
        }
        # Serialize payload to JSON
        payload_json = json.dumps(payload)

        # Publish the JSON string
        client.publish(mqtt_topic, payload_json, qos=2)
        
        # Stop the loop
        time.sleep(2)  # Wait for the message to be sent
        client.loop_stop()
        client.disconnect()

    def create_image(self,sunlight_timestamps, sunlight_values, lamp_timestamps, lamp_lux, moisture_timestamps, moisture_values):
        lux_plot = self.plot_data(sunlight_timestamps, sunlight_values,'yellow','Daily light interval','DLI')
        lamp_plot = self.plot_data(lamp_timestamps, lamp_lux,'violet','uv light emitted over time','lux')
        moisture_plot = self.plot_data(moisture_timestamps, moisture_values,'blue','moisture over time','moisture')
        combined_plot = self.concatenate_images_vertically(lux_plot,lamp_plot,moisture_plot)

        return combined_plot

    def subtract_series(self,data1, data2, fill_method='nearest', fill_value=0):
        """
        Subtract two data series with different timestamps and lengths.

        Parameters:
        - data1: dict, first data series with keys 'timestamp' and 'value1'
        - data2: dict, second data series with keys 'timestamp' and 'value2'
        - fill_method: str, method to align timestamps ('nearest', 'ffill', 'bfill')
        - fill_value: numeric, value to fill missing data (default is 0)

        Returns:
        - pd.DataFrame: DataFrame with aligned timestamps and subtracted values
        """

        # Convert to DataFrame
        df1 = pd.DataFrame(data1)
        df2 = pd.DataFrame(data2)

        # Convert timestamps to datetime
        df1['t'] = pd.to_datetime(df1['t'])
        df2['t'] = pd.to_datetime(df2['t'])

        # Set the timestamp as the index
        df1.set_index('t', inplace=True)
        df2.set_index('t', inplace=True)

        df1.rename(columns={'v':'v1'},inplace=True)
        df2.rename(columns={'v':'v2'},inplace=True)
        # Merge the two DataFrames on the index (timestamps)
        df_merged = pd.merge_asof(df1, df2, left_index=True, right_index=True, direction=fill_method)

        # Handle missing values
        df_merged.fillna(fill_value, inplace=True)

        # Subtract the series
        df_merged['result'] = df_merged['v1'] - df_merged['v2']

        return df_merged
                

    def send_daily_reports(self):
        try:
            plants = requests.get(self.registry_url + '/plants')
            plants = json.loads(plants.text)
            print(f'GET request sent at {self.registry_url}/plants')
        except Exception as e:
            print(f'Error fetching plants: {e}')

        for plant in plants:
            if plant['report_frequency'] == 'daily':
                user = plant['userId']
                chatID = self.get_chatID_from_user(user)
                if chatID is None:
                    continue
                self.generate_report(user, plant['plantCode'], duration=24)

    def send_weekly_reports(self):
        try:
            plants = requests.get(self.registry_url + '/plants')
            plants = json.loads(plants.text)
            print(f'GET request sent at {self.registry_url}/plants')
        except Exception as e:
            print(f'Error fetching plants: {e}')


        for plant in plants:
            if plant['report_frequency'] == 'weekly':
                user = plant['userId']
                chatID = self.get_chatID_from_user(user)
                if chatID is None:
                    continue
                if plant['report_frequency'] == 'weekly':
                    self.generate_report(user, plant['plantCode'], duration=7*24)

    def send_biweekly_reports(self):
        try:
            plants = requests.get(self.registry_url + '/plants')
            plants = json.loads(plants.text)
            print(f'GET request sent at {self.registry_url}/plants')
        except Exception as e:
            print(f'Error fetching plants: {e}')

            for plant in plants:
                if plant['report_frequency'] == 'biweekly':
                    user = plant['userId']
                    chatID = self.get_chatID_from_user(user)
                    if chatID is None:
                        continue
                    if plant['report_frequency'] == 'biweekly':
                        self.generate_report(user, plant['plantCode'], duration=14*24)

    def send_monthly_reports(self):
        try:
            plants = requests.get(self.registry_url + '/plants')
            plants = json.loads(plants.text)
            print(f'GET request sent at {self.registry_url}/plants')
        except Exception as e:
            print(f'Error fetching plants: {e}')

            for plant in plants:
                if plant['report_frequency'] == 'monthly':
                    user = plant['userId']
                    chatID = self.get_chatID_from_user(user)
                    if chatID is None:
                        continue
                    if plant['report_frequency'] == 'monthly':
                        self.generate_report(user, plant['plantCode'], duration=30*24)

    def schedule_and_send_messages(self):
        while True:
            self.actual_time = time.time()
            if self.actual_time > self.start_time + 60:
                self.start_time = time.time()
                #print('checking time')
                now = datetime.datetime.now()

                if now.hour + self.time_zone_correction == 15 and now.minute == 32:
                    self.send_daily_reports()

                    if now.weekday() == 0:  # Sunday
                        self.send_weekly_reports()

                    
                    if now.day() == 14 or now.day == 28:
                        self.send_biweekly_reports()

                    
                    if now.day() == 15:
                        self.send_monthly_reports()



    def generate_report(self,user,plant,duration = 24,instant = False):

        lux_sensor =  json.loads(requests.get(f'{self.url_adaptor}/getData/{user}/{plant}',params={"measurament":'DLI',"duration":duration}).text)


        lux_emitted =  json.loads(requests.get(f'{self.url_adaptor}/getData/{user}/{plant}',params={"measurament":'current_intensity',"duration":duration}).text)
        lux_emitted_timestamps = []
        lux_emitted_values = []
        for datapoint in lux_emitted:
            lux_emitted_timestamps.append(datapoint['t'])
            lux_emitted_values.append(datapoint['v'])

        lux_sunlight_values = self.subtract_series(lux_sensor,lux_emitted)
        lux_sunlight_timestamps = []
        lux_sunlight_values = []
        for datapoint in lux_sensor:
            lux_sunlight_timestamps.append(datapoint['t'])
            lux_sunlight_values.append(datapoint['v'])
        #lux_sunlight_values = [a - b for a, b in zip(lux_sunlight_values, lux_emitted_values)]
        moisture_timestamps = []
        moisture_values = []
        moisture =   json.loads(requests.get(f'{self.url_adaptor}/getData/{user}/{plant}',params={"measurament":'moisture',"duration":duration}).text)
        for datapoint in moisture:
            moisture_timestamps.append(datapoint['t'])
            moisture_values.append(datapoint['v'])



        r = requests.get(self.registry_url+'/models')
        models = json.loads(r.text)
        for model in models:
            if model['model_code'] == plant[:2]:
                lamp_capacity = model['max_lux']

        lux_emitted_values_2 = []
        for element in lux_emitted_values:
            lux_emitted_values_2.append(element*lamp_capacity)
            
        lux_emitted_values = lux_emitted_values_2

        lux_sunlight_timestamps = convert_timestamps(lux_sunlight_timestamps,duration)
        lux_emitted_timestamps = convert_timestamps(lux_emitted_timestamps,duration)
        moisture_timestamps = convert_timestamps(moisture_timestamps,duration)


        combined_image = self.create_image(lux_sunlight_timestamps, lux_sunlight_values, lux_emitted_timestamps,lux_emitted_values, moisture_timestamps, moisture_values)
        dli = self.calculate_dli(lux_sunlight_values)
        light_fluctuation = self.calculate_light_fluctuation(lux_sunlight_values)
        water_absorption = self.calculate_water_absorption(moisture_values)
        tips = self.analyze_plant_conditions(dli, light_fluctuation, moisture_values, water_absorption)
        if not instant:
            self.publish_image_via_mqtt(combined_image, tips, self.broker, self.port, f'RootyPy/report_generator/{user}/{plant}')

        else:
            combined_image.seek(0)
            image_base64 = base64.b64encode(combined_image.read()).decode('utf-8')

            # Create payload dictionary
            body = {
                'image': image_base64,
                'message': tips
            }

            # Serialize payload to JSON
            print(f"Message sent to {user} for plant {plant} with instant: {instant}")
            return body

      

    def get_chatID_from_user(self,user):

        r = requests.get(self.registry_url+'/users',headers = self.headers)
        print(f'GET request sent at \'{self.registry_url}/users')
        output = json.loads(r.text)
        for diz in output:
            if diz['userId'] == user:
                if diz['chatID'] != None:
                    chatID =diz['chatID']
                    return chatID
                else:
                    return None


    def GET(self,*uri,**params):
        print(f'get request received at {uri}')
        if uri[0] == 'getreport':
            r = requests.get(self.registry_url+'/plants',headers=self.headers)
            output = json.loads(r.text)
            found = False
            for diz in output:
                if diz['plantCode'] == uri[1]:
                    found = True
                    userid = diz['userId']
                    plantname = diz['plantCode']
                    body =self.generate_report(userid,plantname,instant =True)
            if not found:   
                response = {"status": "NOT_OK", "code": 400, "message": "Invalid user"}
            else:
                response = body
            return json.dumps(response) 




class Iamalive(object):

    def __init__(self ,config_path,stop_event):

        json_config =  json.load(open(config_path,'r'))
        # mqtt attributes
        self.clientID = json_config["ID"]
        self.broker = json_config["broker"]
        self.port = json_config["port"]
        self.pub_topic = json_config["alive_topic"]
        self.paho_mqtt = pahoMQTT.Client(self.clientID,True)
        self.paho_mqtt.on_connect = self.myconnect_live
        self.message = {"bn": "updateCatalogService","e":[{ "n": f"{self.clientID}", "u": "", "t": time.time(), "v":"" }]}
        self.starting_time = time.time()
        self.interval = json_config["update_time"]
        self.start_mqtt()
        self.stop_event = stop_event
        

    def start_mqtt(self):
        print('>starting i am alive')

        self.paho_mqtt.connect(self.broker,self.port)
        self.paho_mqtt.loop_start()

    def myconnect_live(self,paho_mqtt, userdata, flags, rc):
       print(f"Report generator: Connected to {self.broker} with result code {rc}")

    def check_and_publish(self):
        while  not self.stop_event.is_set():
            actual_time = time.time()
            if actual_time > self.starting_time + self.interval:
                self.publish()
                self.starting_time = actual_time
            time.sleep(15)

    def publish(self):
        __message=json.dumps(self.message)
        print(f'message sent at {time.time()} to {self.pub_topic}')
        self.paho_mqtt.publish(topic=self.pub_topic,payload=__message,qos=2)

class ThreadManager:

    def __init__(self, reportgenerator, iamalive):
        self.reportgenerator = reportgenerator
        self.iamalive = iamalive

    def start_threads(self):
        threading.Thread(target=self.reportgenerator.schedule_and_send_messages).start()
        threading.Thread(target=self.iamalive.check_and_publish).start()

if __name__ == '__main__':
    config_path = 'config_report_generator.json'
    stop_event = threading.Event()
    report_generator = Report_generator(config_path,stop_event)
    iamalive = Iamalive(config_path,stop_event)  # Provide the actual path to your config file

    # Start the threads
    thread_manager = ThreadManager(report_generator, iamalive)
    thread_manager.start_threads()