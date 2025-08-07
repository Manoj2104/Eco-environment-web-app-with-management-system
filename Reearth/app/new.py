# new.py - Speed Diagnostic Entry Point for PythonAnywhere
from flask import Flask, request
import time
import logging

app = Flask(__name__)

# Basic logger setup to file
logging.basicConfig(filename='speed_debug.log', level=logging.INFO)

@app.before_request
def before_request():
    request.start_time = time.time()

@app.after_request
def after_request(response):
    if hasattr(request, 'start_time'):
        elapsed = time.time() - request.start_time
        log_msg = f"{request.method} {request.path} - {elapsed:.3f}s"
        print(log_msg)
        logging.info(log_msg)
    return response

@app.route('/')
def index():
    return "Hello from / (new.py) — performance check!"

if __name__ == '__main__':
    app.run(debug=True)
