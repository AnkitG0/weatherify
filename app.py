import os
from flask import Flask, render_template, request, jsonify
import requests
from dotenv import load_dotenv
import pandas as pd
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import json

load_dotenv() # Load env variables from .env file

app = Flask(__name__)

# Accuweather API key
ACCUWEATHER_API_KEY = os.getenv('ACCUWEATHER_API_KEY')
# Spotify API creds
SPOTIPY_CLIENT_ID = os.getenv('SPOTIPY_CLIENT_ID')
SPOTIPY_CLIENT_SECRET = os.getenv('SPOTIPY_CLIENT_SECRET')

# Verify that the keys are present
if not ACCUWEATHER_API_KEY:
    raise ValueError("ACCUWEATHER_API_KEY not found in .env file.")
if not SPOTIPY_CLIENT_ID or not SPOTIPY_CLIENT_SECRET:
    raise ValueError("SPOTIPY_CLIENT_ID or SPOTIPY_CLIENT_SECRET not found in .env file.")

# Initializing spotify client
sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(client_id=SPOTIPY_CLIENT_ID,
                                                           client_secret=SPOTIPY_CLIENT_SECRET))

@app.route('/')
def hello_world():
    return render_template('index.html')

@app.route('/get_weather', methods=['POST'])
def get_weather():
    city = request.form.get('city')
    if not city:
        return jsonify({"error": "City name is required"}), 400
    
    # Get the location key
    location_url = f"http://dataservice.accuweather.com/locations/v1/cities/search"
    location_params = {
        'apikey': ACCUWEATHER_API_KEY,
        'q': city
    }

    try:
        location_response = requests.get(location_url, params=location_params)
        location_response.raise_for_status() # in case there's an error, it will be raised
        location_data = location_response.json()

        if not location_data:
            return jsonify({"error": "City not found"}), 404
        
        location_key = location_data[0]["Key"]
        city_name_found = location_data[0]["EnglishName"]

        # Get current weather condition
        current_conditions_url = f'http://dataservice.accuweather.com/currentconditions/v1/{location_key}'
        current_conditions_params = {
            'apikey': ACCUWEATHER_API_KEY,
            'details': 'true'
        }

        conditions_response = requests.get(current_conditions_url, params=current_conditions_params)
        conditions_response.raise_for_status()
        conditions_data = conditions_response.json()

        print(conditions_data)

        if not conditions_data:
            return jsonify({"error": f"Could not retrieve weather conditions."}), 500
        
        weather_text = conditions_data[0]['WeatherText']
        temperature = conditions_data[0]['Temperature']['Metric']['Value']
        # rel_humidity = conditions_data[0]['RelativeHumidity']
        icon_code = conditions_data[0]['WeatherIcon']
        is_day_time = conditions_data[0]['IsDayTime'] 

        music_mood = get_music_mood_from_weather(weather_text=weather_text, temperature=temperature)
        print(music_mood)

        return jsonify({
            'city': city_name_found,
            'weather_text': weather_text,
            'temperature': f'{temperature} deg. C',
            'icon_code': icon_code,
            'is_day_time': is_day_time,
            'music_mood': music_mood
        })
    
    except requests.exceptions.RequestException as e:
        return jsonify({'error': f'API request failed: {e}'}), 500
    except Exception as e:
        return jsonify({'error': f'An unexpected error occurred: {e}'}), 500

def get_mood_mappings():
    try:
        # Load weather_mood dataframe from .csv - will be used to determine the mood
        script_dir = os.path.dirname(os.path.abspath(__file__))
        weather_mood_path = os.path.join(script_dir, 'data', 'mood_mappings.csv')

        MAPPING_DF = pd.read_csv(weather_mood_path)
        # Convert relevant columns to lowercase strings
        cols_to_format = ['weather_text', 'mood', 'genre', 'season']
        MAPPING_DF[cols_to_format]= MAPPING_DF[cols_to_format].astype(str).apply(lambda col: col.str.lower())

        return MAPPING_DF
    except FileNotFoundError:
        raise FileNotFoundError("mood_mappings.csv not found. Please add it in the 'data' folder")
    except Exception as e:
        raise Exception(f"Error in get_mood_mappings: {e}")


def get_music_mood_from_weather(weather_text, temperature):
    try:
        MAPPINGS_DF = get_mood_mappings()

        weather_text = weather_text.lower()
        
        match = MAPPINGS_DF[
            (MAPPINGS_DF['temp_min'] <= temperature) &
            (MAPPINGS_DF['temp_max'] > temperature) & 
            (MAPPINGS_DF['weather_text'].apply(lambda x: x in weather_text))
            ]

        if not match.empty:
            mood = match['mood'].iloc[0]
            genre = match['genre'].iloc[0]
            season = match['season'].iloc[0]

            return f"{mood} {season} {genre}"
        
        if match.empty:
            # If an exact match is not found, return its mood and genre
            mood = match.iloc[0]['mood']
            genre = match.iloc[0]['genre']
            return f"{mood} {genre}"
        
        else:
            return "chill pop"
    except Exception as e:
        raise Exception(f"Error in {get_music_mood_from_weather.__name__}: {e}")


@app.route('/get_songs', methods=['POST'])
def get_songs():
    print("DEBUG: Entered /get_songs route.") # Added DEBUG prefix for clarity
    mood = request.form.get('mood')
    print(f"DEBUG: Received mood: '{mood}'") # Added DEBUG prefix for clarity
    if not mood:
        print("DEBUG: Mood is empty or None, returning 400.") # Added DEBUG prefix
        return jsonify({"error": "Music mood is required."}), 400
    
    try:
        # The 'type' parameter here correctly specifies 'track' (singular) for the search
        results = sp.search(q=mood, type='track', limit=5) 
        
        # Print the full result to see its structure if you are still unsure
        # print(f"DEBUG: Spotify Search Result: {results}") 

        songs = []
        # >>> IMPORTANT FIX HERE: Use 'tracks' (plural) for accessing the items <<<
        for track in results['tracks']['items']: 
            artists = ', '.join([artist['name'] for artist in track['artists']])
            songs.append({
                'title': track['name'],
                'artist': artists,
                'url': track['external_urls']['spotify']
            })

        return jsonify({'songs': songs})

    except spotipy.exceptions.SpotifyException as e:
        print(f"Spotify API error in get_songs: {e}") # Print error for debugging
        return jsonify({"error": f"Spotify API error: {e}"}), 500
    except Exception as e:
        # This will now catch the KeyError and print it
        print(f"Unexpected error in get_songs: {e}") 
        return jsonify({"error": f"An unexpected error occurred: {e}"}), 500
    
if __name__ == '__main__':
    # result = sp.search(q='relaxing summer indie', type='track', limit=5)
    # print(result)
    app.run(debug=True)
    # print(get_mood_mappings())
    # print(get_music_mood_from_weather("Mostly cloudy", 24))