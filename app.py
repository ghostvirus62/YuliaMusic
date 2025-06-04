from flask import Flask, render_template, request, redirect,url_for,session, jsonify, send_from_directory, current_app
from flask_sqlalchemy import SQLAlchemy
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth
from mutagen.flac import FLAC
import os
import tempfile
from PIL import Image
import io
from collections import Counter




app = Flask(__name__)
app.config['SESSION_COOKIE_NAME'] = 'IAMTHENIGHT'
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_BINDS'] = {
    'music_db': 'sqlite:///music.db'
}
app.config['SPOTIPY_CLIENT_ID'] = '' #add your Spotify Client ID here
app.config['SPOTIPY_CLIENT_SECRET'] = '' #add your Spotify Client Secret here
app.config['SPOTIPY_REDIRECT_URI'] = 'http://localhost:5000/callback'
app.secret_key = 'your_secret_key_here'  # Replace with your actual secret key
sp_oauth = SpotifyOAuth(
    app.config['SPOTIPY_CLIENT_ID'],
    app.config['SPOTIPY_CLIENT_SECRET'],
    app.config['SPOTIPY_REDIRECT_URI'],
    scope='user-library-read user-top-read')
app.config['FLAC_MUSIC_FOLDER'] = os.path.join('music', 'Dubstep_FLAC')

db = SQLAlchemy(app)  #user databse


class User(db.Model):
    __tablename__ = 'users'
    user_id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False) 
    username = db.Column(db.String(80), unique=True, nullable=False)
    display_name = db.Column(db.String(80), nullable=False)
    password = db.Column(db.String(120), nullable=False)

class Music(db.Model):
    __bind_key__ = 'music_db'
    __tablename__ = 'music'
    song_id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    artist = db.Column(db.String(255), nullable=True)
    album = db.Column(db.String(255), nullable=True)
    file_path = db.Column(db.String(255), nullable=False)
    cover_image = db.Column(db.String(255), nullable=True)


with app.app_context():
    db.create_all()

@app.route('/add_flac_music', methods=['POST'])
def add_flac_music():

    relative_folder_path = current_app.config['FLAC_MUSIC_FOLDER']
    folder_path = os.path.join(current_app.root_path, relative_folder_path)

    # Iterate through files in the folder
    for filename in os.listdir(folder_path):
        if filename.endswith('.flac'):
            # Read metadata from the FLAC file
            flac_path = os.path.join(folder_path, filename)
            flac = FLAC(flac_path)

            title = flac.get("title", [""])[0]
            artist = flac.get("artist", [""])[0]
            album = flac.get("album", [""])[0]

            cover_data = None
            if 'covr' in flac:
                cover_data = flac['covr'][0]

            new_song = Music(title=title, artist=artist, album=album)

            # Handle cover art data
            if cover_data:
                try:
                    # Use Pillow to create a valid PNG image from cover_data
                    image = Image.open(io.BytesIO(cover_data))
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as cover_image_file:
                        image.save(cover_image_file.name, format='PNG')
                    # Set the cover_image field to the path of the saved image
                    new_song.cover_image = cover_image_file.name
                except Exception as e:
                    # Handle any exceptions that occur during cover art processing
                    print(f"Error processing cover art for '{filename}': {str(e)}")

           # Replace backslashes with forward slashes in file_path
            relative_file_path = os.path.join(relative_folder_path, filename).replace('\\', '/')
            new_song.file_path = relative_file_path 


            # Create a new Music object and add it to the database
            db.session.add(new_song)

    db.session.commit()
    
    return jsonify({'message': 'FLAC files added to the music database'})


@app.route('/music/<path:filename>')
def serve_audio(filename):
    audio_folder = os.path.join(app.root_path, 'music')  # Adjust to your folder structure
    return send_from_directory(audio_folder, filename)



def login_required(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('register'))
        return view_func(*args, **kwargs)
    return wrapped_view


@app.route("/")
@login_required
def index():
    return render_template("index.html")



@app.route('/login_spotify')
def login_spotify():
    auth_url = sp_oauth.get_authorize_url()
    return redirect(auth_url)


@app.route('/callback')
def callback():
    token_info = sp_oauth.get_access_token(request.args['code'])
    sp = Spotify(auth=token_info['access_token'])
    session['user_id'] = 'spotify_user_id'
    return redirect(url_for('index'))



@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email")
        username = request.form.get("username")
        display_name = request.form.get("display_name")
        password = request.form.get("password")

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            error_message = "Email already registered. Please use a different email."
            return render_template("register.html", error=error_message)

        else:
            new_user = User(
                email=email,
                username=username,
                display_name=display_name,
                password=generate_password_hash(password),
            )
            db.session.add(new_user)
            db.session.commit()
            return redirect(url_for("login"))

    return render_template("register.html")



@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username_email = request.form.get("username_email")  # Get input for username or email
        password = request.form.get("password")

        # Check if the input matches a username or an email
        user = User.query.filter((User.username == username_email) | (User.email == username_email)).first()

        if user and check_password_hash(user.password, password):
            session['user_id'] = user.user_id
            return redirect(url_for("index"))
        else:
            error_message = "Invalid username or email or password"
            return render_template("login.html", error=error_message)

    return render_template("login.html", error=None)

@app.route('/music_player')
def music_player():
    # Fetch songs from the database
    songs = Music.query.all()
    
    # Pass the songs data to the HTML template
    return render_template('music_player.html', music=songs)

@app.route("/about")
def about():
    return render_template("about.html")




# Function to get the top genres for the user's top artists
def get_top_genres(sp):
    # Fetch the user's top artists
    top_artists = sp.current_user_top_artists(limit=5, time_range='long_term')

    # Create a list to store genre names
    genre_list = []

    # Iterate through the user's top artists and extract genres
    for artist in top_artists['items']:
        # Fetch the artist's details, including genres
        artist_details = sp.artist(artist['id'])
        
        # Get the genres for the artist (if available)
        if 'genres' in artist_details:
            genres = artist_details['genres']
            genre_list.extend(genres)

    # Count the occurrences of each genre
    genre_counts = Counter(genre_list)

    # Get the top 5 genres
    top_genres = genre_counts.most_common(5)

    return top_genres


def get_user_playlists(sp):
    playlists = sp.current_user_playlists()

    # Create a list to store playlist information
    playlist_info_list = []

    for playlist in playlists['items']:
        playlist_info = {
            'name': playlist['name'],
            'owner': playlist['owner']['display_name'],
            'link': playlist['external_urls']['spotify'],  # URL to the playlist on Spotify
        }
        playlist_info_list.append(playlist_info)

    return playlist_info_list

# Route to the community page
@app.route("/community")
def community():
    # Fetch the top 5 most-played tracks and create a list of track_info dictionaries
    token_info = sp_oauth.get_cached_token()
    if not token_info:
        return redirect(url_for('login_spotify'))

    sp = Spotify(auth=token_info['access_token'])
    top_tracks = sp.current_user_top_tracks(limit=5, time_range='long_term')  # Retrieve the top 5 most-played tracks

    # Create a list to store the track_info dictionaries for each song
    track_info_list = []

    for top_track in top_tracks['items']:
        track_info = {
            'name': top_track['name'],
            'artist': top_track['artists'][0]['name'],
            'album': top_track['album']['name'],
            'cover_image_url': top_track['album']['images'][0]['url'],
        }
        track_info_list.append(track_info)

    top_genres = get_top_genres(sp)
    playlist_info_list = get_user_playlists(sp)

    return render_template("community.html", track_info_list=track_info_list, top_genres=top_genres,playlist_info_list=playlist_info_list)





@app.route("/dashboard")
@login_required
def dashboard():
    user_id = session.get('user_id')
    if user_id:
        return "Welcome to the dashboard!"
    else:
        return redirect(url_for('login'))
    

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('login'))








if __name__ == "__main__":
    app.run(debug=True)