from flask import Flask, request, Response
from dotenv import load_dotenv
import os

# This line imports the main logic function from your app.py file
from app import handle_ussd

# Load environment variables from a .env file
load_dotenv()

# This is the Flask app object that Vercel will run
app = Flask(__name__)

# This route handles all incoming POST requests to /api/ussd on Vercel
@app.route("/", methods=['POST'])
def ussd_wrapper():
    """
    This is the entry point for Vercel. It receives the web request,
    passes the data to your main logic function, and returns the response.
    """
    # Get the incoming data from the USSD provider
    data = request.form
    
    # Call your main logic function from app.py and get the response text
    text_response = handle_ussd(data)
    
    # Return the response to the USSD provider
    return Response(text_response, mimetype="text/plain")
