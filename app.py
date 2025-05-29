import os
import json
from flask import Flask, request, redirect, session, url_for, render_template
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth

import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors

app = Flask(__name__)
app.secret_key = '123456'

# --- Configurações Spotify ---
SPOTIFY_CLIENT_ID = '62105638db7042199049e9040993fd79'
SPOTIFY_CLIENT_SECRET = '759b02d8c5dc438f99317ceb9c1cac4b'
SPOTIFY_REDIRECT_URI = 'https://62fd-109-48-203-219.ngrok-free.app/spotify_callback'

# Escopos Spotify
SPOTIFY_SCOPE = 'playlist-read-private'

# --- Configurações YouTube ---
YOUTUBE_CLIENT_SECRETS_FILE = 'client_secret.json'
YOUTUBE_SCOPES = ['https://www.googleapis.com/auth/youtube']

# --- Spotify OAuth ---
sp_oauth = SpotifyOAuth(
    client_id=SPOTIFY_CLIENT_ID,
    client_secret=SPOTIFY_CLIENT_SECRET,
    redirect_uri=SPOTIFY_REDIRECT_URI,
    scope=SPOTIFY_SCOPE,
    cache_path=".spotifycache"
)

# --- Rotas ---

@app.route('/')
def index():
    # Começa login no Spotify
    auth_url = sp_oauth.get_authorize_url()
    return render_template('index.html', auth_url=auth_url)

@app.route('/spotify_callback')
def spotify_callback():
    code = request.args.get('code')
    token_info = sp_oauth.get_access_token(code)
    session['spotify_token'] = token_info['access_token']
    return redirect(url_for('choose_playlist'))

@app.route('/choose_playlist')
def choose_playlist():
    sp = Spotify(auth=session['spotify_token'])
    playlists = sp.current_user_playlists(limit=10)['items']
    return render_template('choose_playlist.html', playlists=playlists)

@app.route('/create_youtube_playlist')
def create_youtube_playlist():
    playlist_id = request.args.get('playlist_id')
    sp = Spotify(auth=session['spotify_token'])

    # Pega dados da playlist
    playlist = sp.playlist(playlist_id)
    tracks = playlist['tracks']['items']

    # Salva nomes e artistas para busca
    songs = []
    for item in tracks:
        track = item['track']
        name = track['name']
        artists = ', '.join([a['name'] for a in track['artists']])
        songs.append(f"{name} {artists}")

    # Autentica no YouTube
    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        YOUTUBE_CLIENT_SECRETS_FILE, scopes=YOUTUBE_SCOPES)
    flow.redirect_uri = url_for('youtube_callback', _external=True)

    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true')
    session['songs'] = songs
    session['state'] = state
    session['playlist_name'] = playlist['name']

    return redirect(authorization_url)

@app.route('/youtube_callback')
def youtube_callback():
    state = session['state']
    flow = google_auth_oauthlib.flow.Flow.from_client_secrets_file(
        YOUTUBE_CLIENT_SECRETS_FILE, scopes=YOUTUBE_SCOPES, state=state)
    flow.redirect_uri = url_for('youtube_callback', _external=True)

    authorization_response = request.url
    flow.fetch_token(authorization_response=authorization_response)

    credentials = flow.credentials
    youtube = googleapiclient.discovery.build(
        'youtube', 'v3', credentials=credentials)

    # Cria playlist no YouTube
    request_playlist = youtube.playlists().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": session['playlist_name'],
                "description": "Playlist criada a partir do Spotify",
                "tags": ["Spotify", "Playlist"],
                "defaultLanguage": "pt"
            },
            "status": {
                "privacyStatus": "private"
            }
        }
    )
    response_playlist = request_playlist.execute()
    youtube_playlist_id = response_playlist['id']

    # Para cada música, busca vídeo e adiciona na playlist
    for song in session['songs']:
        # Busca vídeo
        search_response = youtube.search().list(
            q=song,
            part='id,snippet',
            maxResults=1,
            type='video'
        ).execute()

        if search_response['items']:
            video_id = search_response['items'][0]['id']['videoId']
            # Adiciona vídeo na playlist
            youtube.playlistItems().insert(
                part='snippet',
                body={
                    'snippet': {
                        'playlistId': youtube_playlist_id,
                        'resourceId': {
                            'kind': 'youtube#video',
                            'videoId': video_id
                        }
                    }
                }
            ).execute()

    return render_template(
        'result.html',
        count=len(session["songs"]),
        playlist_url=f'https://www.youtube.com/playlist?list={youtube_playlist_id}'
    )

if __name__ == '__main__':
    app.run(debug=True)
