import sublime
import sublime_plugin

#!/usr/bin/python

# Retrieve the authenticated user's uploaded videos.
# Sample usage:
# python my_uploads.py

import argparse
import os
import re
import json

import google.oauth2.credentials
import google_auth_oauthlib.flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow


# The CLIENT_SECRETS_FILE variable specifies the name of a file that contains
# the OAuth 2.0 information for this application, including its client_id and
# client_secret. You can acquire an OAuth 2.0 client ID and client secret from
# the {{ Google Cloud Console }} at
# {{ https://cloud.google.com/console }}.
# Please ensure that you have enabled the YouTube Data API for your project.
# For more information about using OAuth2 to access the YouTube Data API, see:
#   https://developers.google.com/youtube/v3/guides/authentication
# For more information about the client_secrets.json file format, see:
#   https://developers.google.com/api-client-library/python/guide/aaa_client_secrets
CLIENT_SECRETS_FILE = '{packages}/YouTuberizer/client_id.json'

# This OAuth 2.0 access scope allows for read-only access to the authenticated
# user's account, but not other types of account access.
SCOPES = ['https://www.googleapis.com/auth/youtube.readonly']
API_SERVICE_NAME = 'youtube'
API_VERSION = 'v3'

def plugin_loaded():
    # Update the location of the client secrets file since it's packed in our
    # package.
    global CLIENT_SECRETS_FILE
    CLIENT_SECRETS_FILE = CLIENT_SECRETS_FILE.format(packages=sublime.packages_path())


def get_secrets_file():
    """
    Load the client secrets file and return it back; this will currently raise
    an exception if the file is broken (so don't break it).

    This loads the file as a resource, not from the global variable (which is
    still in place for the standard library calls until we fix things.)
    """
    return sublime.decode_value(sublime.load_resource("Packages/YouTuberizer/client_id.json"))


def cache_credentials(credentials):
    """
    Given a credentials object, cache the given credentials into a file in the
    Cache directory for later use.
    """
    cache_data = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "id_token": credentials.id_token
    }

    cache_path = os.path.join(sublime.packages_path(), "..", "Cache", "YouTuberizerCredentials.json")
    with open(os.path.normpath(cache_path), "wt") as handle:
        handle.write(json.dumps(cache_data, indent=4))


def get_cached_credentials():
    """
    Fetch the cached credentials from a previous operation; this will return
    None if there is currently no cached credentials. This will currently
    raise an exception if the file is broken (so don't break it).
    """
    secrets = get_secrets_file()
    installed = secrets["installed"]

    try:
        cache_path = os.path.join(sublime.packages_path(), "..", "Cache", "YouTuberizerCredentials.json")
        with open(os.path.normpath(cache_path), "rt") as handle:
            cached = json.loads(handle.read())
    except FileNotFoundError:
        return None

    return google.oauth2.credentials.Credentials(
        cached["token"],
        cached["refresh_token"],
        cached["id_token"],
        secrets["installed"]["token_uri"],
        secrets["installed"]["client_id"],
        secrets["installed"]["client_secret"],
        SCOPES
        )


# Authorize the request and store authorization credentials.
def get_authenticated_service():
  credentials = get_cached_credentials()
  if credentials is None or not credentials.valid:
      flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
      credentials = flow.run_local_server(client_type="installed")

      cache_credentials(credentials)

  return build(API_SERVICE_NAME, API_VERSION, credentials = credentials)


  # Retrieve the contentDetails part of the channel resource for the
  # authenticated user's channel.
  channels_response = youtube.channels().list(
    mine=True,
    part='contentDetails'
  ).execute()

  for channel in channels_response['items']:
    # From the API response, extract the playlist ID that identifies the list
    # of videos uploaded to the authenticated user's channel.
    return channel['contentDetails']['relatedPlaylists']['uploads']

  return None


  # Retrieve the list of videos uploaded to the authenticated user's channel.
  playlistitems_list_request = youtube.playlistItems().list(
    playlistId=uploads_playlist_id,
    part='snippet',
    maxResults=5
  )

  print ('Videos in list %s' % uploads_playlist_id)
  while playlistitems_list_request:
    playlistitems_list_response = playlistitems_list_request.execute()

    # Print information about each video.
    for playlist_item in playlistitems_list_response['items']:
      title = playlist_item['snippet']['title']
      video_id = playlist_item['snippet']['resourceId']['videoId']
      print ('%s (%s)' % (title, video_id))

    playlistitems_list_request = youtube.playlistItems().list_next(
      playlistitems_list_request, playlistitems_list_response)

if __name__ == '__main__':
  youtube = get_authenticated_service()
  try:
    uploads_playlist_id = get_my_uploads_list()
    if uploads_playlist_id:
      list_my_uploaded_videos(uploads_playlist_id)
    else:
      print('There is no uploaded videos playlist for this user.')
  except HttpError as e:
    print ('An HTTP error %d occurred:\n%s' % (e.resp.status, e.content))