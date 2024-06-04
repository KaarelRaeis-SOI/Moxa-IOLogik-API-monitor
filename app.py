import logging
from logging.handlers import TimedRotatingFileHandler
import sys
from datetime import datetime
import time
from threading import Thread, Lock

import pandas as pd
import plotly.graph_objects as go
import requests
from dash import Dash, dcc, html
from dash.dependencies import Input, Output
import dash_bootstrap_components as dbc

READ_BUFFER_SIZE = 4096  # max number of characters to read in one call
HEADERS = {'Accept': 'vdn.dac.v1', 'Content-Type': 'application/json'}

# Adjust this according to the correct endpoint - set up for analog inputs
API_ROOT = '/api/slot/0/io/ai'


def setup_logging():
    """Set up logging configuration with timestamped log filename and rotation."""
    log_filename = 'moxa_reader.log'
    handler = TimedRotatingFileHandler(log_filename, when='midnight', interval=1, backupCount=7)
    handler.suffix = '%Y%m%d'
    logging.basicConfig(level=logging.DEBUG,
                        format='%(asctime)s - %(levelname)s - %(message)s',
                        handlers=[handler])


def get_csv_filename():
    """Get timestamped CSV filename."""
    timestamp = datetime.now().strftime('%Y%m%d')
    return f'data_log_{timestamp}.csv'


class IoLogikAPIReader:
    def __init__(self, address, polling_rate=5, timeout=1, analog_channels='0,1,2,3',
                 max_retries=5, retry_delay=5):
        """
        Initialize IoLogikAPIReader.

        Args:
            address (str): IP address of the device.
            polling_rate (int): Polling rate in seconds (default: 5).
            timeout (int): Timeout in seconds for API requests (default: 1).
            analog_channels (str): Comma-separated list of analog channel indices (default: '0,1,2,3').
            max_retries (int): Maximum number of retries for connection attempts (default: 5).
            retry_delay (int): Delay in seconds between retries (default: 5).
        """
        self.address = address
        self.polling_rate = polling_rate
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.analog_channels = [int(i) for i in analog_channels.split(',')]
        self.last_get_time = 0
        self.failed_attempts = 0
        self.total_retries = 0
        self.df = pd.DataFrame(columns=['Timestamp'] + [f'Channel {i}' for i in self.analog_channels])
        self.data_lock = Lock()
        self.csv_filename = get_csv_filename()

        # Load existing data if present
        self.load_existing_data()

        self.connect_to_device()

    def load_existing_data(self):
        """Load existing data from the CSV file if it exists."""
        try:
            self.df = pd.read_csv(self.csv_filename)
        except FileNotFoundError:
            logging.info(f"No existing data file found. Starting fresh.")

    def connect_to_device(self):
        """Connect to the device with retries."""
        for attempt in range(self.max_retries):
            try:
                res = requests.get(f'http://{self.address}{API_ROOT}', headers=HEADERS, timeout=self.timeout)
                res.raise_for_status()
                print('Connected to the device successfully.')
                logging.info('Connected to the device successfully.')
                return
            except requests.exceptions.HTTPError as http_err:
                logging.error(f'HTTP error occurred: {http_err}')
                print(f'HTTP error occurred: {http_err}')
            except Exception as err:
                logging.error(f'Error connecting to device: {err}')
                print(f'Error connecting to device: {err}')

            self.total_retries += 1
            logging.info(f'Retrying in {self.retry_delay} seconds...')
            time.sleep(self.retry_delay)

        logging.error('Failed to connect to the device after multiple attempts.')
        print('Failed to connect to the device after multiple attempts.')
        sys.exit(1)

    def fetch_data(self):
        """Fetch data from the device continuously."""
        while True:
            start_time = time.time()
            try:
                url = f'http://{self.address}{API_ROOT}'
                response = requests.get(url, timeout=self.timeout, headers=HEADERS)
                response.raise_for_status()
                data = response.json()
                return_channels = data['io']['ai']

                # Record precise timestamps for fetched data
                timestamp = pd.Timestamp.now()
                new_data = {'Timestamp': [timestamp]}
                new_data.update({f'Channel {channel["aiIndex"]}': [channel['aiValueScaled']]
                                 for channel in return_channels})
                new_data = pd.DataFrame(new_data)

                with self.data_lock:
                    self.df = pd.concat([self.df, new_data], ignore_index=True)
                    self.df.drop_duplicates(subset=['Timestamp'], keep='last', inplace=True)

                logging.info(f'Fetched Data: {new_data.to_dict(orient="records")}')
                print(f'Fetched data: {new_data.to_dict(orient="records")}')

                # Periodically write to CSV
                if time.time() - self.last_get_time >= 60:  # Every minute
                    with self.data_lock:
                        self.df.to_csv(self.csv_filename, mode='w',
                                       header=True, index=False)
                    self.last_get_time = time.time()
            except requests.exceptions.HTTPError as http_err:
                logging.warning(f'HTTP error occurred while retrieving data from device: {self.address}. '
                                f'Error: {http_err}')
                print(f'HTTP error occurred while retrieving data from device: {self.address}. Error: {http_err}')
                self.failed_attempts += 1
            except Exception as err:
                logging.warning(f'Problem retrieving data from device: {self.address}')
                logging.debug('URL: %s', url)
                logging.debug(str(err))
                self.failed_attempts += 1
                print(f'Problem retrieving data from device: {self.address}. Error: {err}')

            # Ensure the loop runs at the correct polling rate
            elapsed_time = time.time() - start_time
            time_to_sleep = self.polling_rate - elapsed_time
            if time_to_sleep > 0:
                time.sleep(time_to_sleep)

            # Check if it's midnight and start a new CSV file
            current_time = datetime.now()
            if current_time.hour == 0 and current_time.minute == 0 and current_time.second == 0:
                self.csv_filename = get_csv_filename()

    def run(self):
        """Start the data fetching thread."""
        thread = Thread(target=self.fetch_data)
        thread.daemon = True
        thread.start()
        print('Data fetching thread started.')
        logging.info('Data fetching thread started.')


def update_graph_live(n):
    """
    Update the live graph with the latest data.

    Args:
        n (int): Number of intervals passed.

    Returns:
        go.Figure: Updated graph figure.
    """
    with reader.data_lock:
        df = reader.df.copy()

    # Convert 'Timestamp' column to datetime
    df['Timestamp'] = pd.to_datetime(df['Timestamp'])

    # Filter data to show only the last 24h
    current_time = pd.Timestamp.now()
    start_time = current_time - pd.Timedelta(hours=24)
    df = df[df['Timestamp'] >= start_time]

    # Aggregate data by minute
    df = df.set_index('Timestamp')
    df = df.resample('1T').mean().reset_index()

    fig = go.Figure()

    for channel in reader.analog_channels:
        trace_name = f'Channel {channel}'
        if not df.empty:
            fig.add_trace(go.Scatter(x=df['Timestamp'], y=df[trace_name], mode='lines', name=trace_name))

    fig.update_layout(title=f'Analog Channel Voltages (Last 24 Hours, Aggregated by Minute)<br>Failed Connection Attempts: {reader.failed_attempts} | '
                            f'Total Retries: {reader.total_retries}',
                      xaxis_title='Timestamp',
                      yaxis_title='Voltage')

    return fig


if __name__ == '__main__':
    setup_logging()
    reader = IoLogikAPIReader(address='10.23.10.45', polling_rate=1, timeout=1, analog_channels='0,1,2,3')
    reader.run()

    app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

    app.layout = html.Div([
        html.H1('Analog Channel Voltages'),
        dcc.Graph(id='live-update-graph'),
        dcc.Interval(
            id='interval-component',
            interval=5*1000,  # in milliseconds
            n_intervals=0
        )
    ])

    app.callback(Output('live-update-graph', 'figure'),
                 Input('interval-component', 'n_intervals'))(update_graph_live)

    app.run_server(host='0.0.0.0', port=8050, debug=True, use_reloader=False)
    print('Dash server started.')
    logging.info('Dash server started.')