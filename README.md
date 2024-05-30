# Moxa-IOLogik-API
API request for analog voltage data from Moxa iOLogik E1200 and graph in a stand-alone WebUI with Plotly DASH
Also saves a .log and csv of all data
![Screenshot 2024-05-29 at 11 51 14](https://github.com/KaarelRaeis-SOI/Moxa-IOLogik-API-monitor/assets/160142038/5a09cdd6-bd7d-4ade-bcdf-554b8b3fac05)


## Install
1. Create a new conda environment:
conda create -n moxa-api
2. Install the required packages:
pip install -r requirements.txt

## Usage

To run the application, simply execute the `app.py` script:

## Daemonize(optional)
You can optionally daemonize the application using `pm2`:
pm2 start app.py --name moxa-api --interpreter ~/miniconda3/envs/moxa-api/bin/python

This will start the application as a background process managed by `pm2`.
