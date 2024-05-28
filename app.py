import logging
import requests
import sys
from time import sleep, time
import plotly.graph_objects as go
import pandas as pd
from dash import Dash, dcc, html
from dash.dependencies import Input, Output
import dash_bootstrap_components as dbc
from threading import Thread, Lock

READ_BUFFER_SIZE = 4096  # max number of characters to read in one call
HEADERS = {'Accept': 'vdn.dac.v1', 'Content-Type': 'application/json'}

# Adjust this according to the correct endpoint - set up for analog inputs
API_ROOT = "/api/slot/0/io/ai"

# Configure logging to write to a file
logging.basicConfig(filename='moxa_reader.log', level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(message)s')

class ioLogikAPI_reader:
    def __init__(self, address, polling_rate=5, timeout=1, analog_channels='0,1,2,3', max_retries=5, retry_delay=5):
        self.address = address
        self.polling_rate = polling_rate
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.analog_channels = [int(i) for i in analog_channels.split(',')]
        self.last_get_time = 0
        self.failed_attempts = 0
        self.df = pd.DataFrame(columns=['Timestamp'] + [f'Channel {i}' for i in self.analog_channels])
        self.data_lock = Lock()
        
        self.connect_to_device()

    def connect_to_device(self):
        for attempt in range(self.max_retries):
            try:
                res = requests.get(f'http://{self.address}{API_ROOT}', headers=HEADERS, timeout=self.timeout)
                res.raise_for_status()
                print("Connected to the device successfully.")
                logging.info("Connected to the device successfully.")
                return
            except requests.exceptions.HTTPError as http_err:
                logging.error(f"HTTP error occurred: {http_err}")
                print(f"HTTP error occurred: {http_err}")
            except Exception as err:
                logging.error(f"Error connecting to device: {err}")
                print(f"Error connecting to device: {err}")
            
            logging.info(f"Retrying in {self.retry_delay} seconds...")
            sleep(self.retry_delay)

        logging.error("Failed to connect to the device after multiple attempts.")
        print("Failed to connect to the device after multiple attempts.")
        sys.exit(1)

    def fetch_data(self):
        while True:
            try:
                url = f'http://{self.address}{API_ROOT}'
                response = requests.get(url, timeout=self.timeout, headers=HEADERS)
                response.raise_for_status()
                data = response.json()
                return_channels = data['io']['ai']

                new_data = pd.DataFrame({'Timestamp': [pd.Timestamp.now()]} | 
                                        {f'Channel {channel["aiIndex"]}': [channel['aiValueScaled']] 
                                         for channel in return_channels})
                new_data = new_data.dropna(how='all')
                
                with self.data_lock:
                    self.df = pd.concat([self.df, new_data], ignore_index=True)

                logging.info(f"Data: {new_data.to_dict(orient='records')}")
                print(f"Fetched data: {new_data.to_dict(orient='records')}")
            except requests.exceptions.HTTPError as http_err:
                logging.warning(f"HTTP error occurred while retrieving data from device: {self.address}. Error: {http_err}")
                print(f"HTTP error occurred while retrieving data from device: {self.address}. Error: {http_err}")
                self.failed_attempts += 1
            except Exception as err:
                logging.warning(f"Problem retrieving data from device: {self.address}")
                logging.debug("URL: %s", url)
                logging.debug(str(err))
                self.failed_attempts += 1
                print(f"Problem retrieving data from device: {self.address}. Error: {err}")

            elapsed_time = time() - self.last_get_time
            remaining_time = self.polling_rate - elapsed_time
            if remaining_time > 0:
                sleep(remaining_time)

    def run(self):
        thread = Thread(target=self.fetch_data)
        thread.daemon = True
        thread.start()
        print("Data fetching thread started.")
        logging.info("Data fetching thread started.")

app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

app.layout = html.Div([
    html.H1("Analog Channel Voltages"),
    dcc.Graph(id='live-update-graph'),
    dcc.Interval(
        id='interval-component',
        interval=5*1000,  # in milliseconds
        n_intervals=0
    )
])

@app.callback(Output('live-update-graph', 'figure'),
              Input('interval-component', 'n_intervals'))
def update_graph_live(n):
    with reader.data_lock:
        df = reader.df.copy()
    
    fig = go.Figure()
    
    for channel in reader.analog_channels:
        trace_name = f'Channel {channel}'
        if not df.empty:
            fig.add_trace(go.Scatter(x=df['Timestamp'], y=df[trace_name], mode='lines', name=trace_name))
    
    fig.update_layout(title=f'Analog Channel Voltages<br>Failed Connection Attempts: {reader.failed_attempts}',
                      xaxis_title='Timestamp',
                      yaxis_title='Voltage',
                      xaxis=dict(range=[df['Timestamp'].min(), df['Timestamp'].max()] if not df.empty else []),
                      yaxis=dict(range=[df.iloc[:, 1:].min().min(), df.iloc[:, 1:].max().max()] if not df.empty else []))
    
    return fig

if __name__ == '__main__':
    reader = ioLogikAPI_reader(address='10.23.10.45', polling_rate=5, timeout=1, analog_channels='0,1,2,3')
    reader.run()
    app.run_server(debug=True, use_reloader=False)  # Set use_reloader=False to prevent issues with multiple threads
    print("Dash server started.")
    logging.info("Dash server started.")
