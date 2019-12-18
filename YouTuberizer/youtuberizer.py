import sublime
import sublime_plugin

import os
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
    """
    This builds the appropriate endpoint object to talk to the YouTube data
    API, using a combination of the client secrets file and either cached
    credentials or asking the user to log in first.

    If there is no cached credentials, or if they are not valid, then the user
    is asked to log in again before this returns.

    The result is an object that can be used to make requests to the API.
    This fetches the authenticated service for use
    """
    credentials = get_cached_credentials()
    if credentials is None or not credentials.valid:
        flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS_FILE, SCOPES)
        credentials = flow.run_local_server(client_type="installed")

        cache_credentials(credentials)

    return build(API_SERVICE_NAME, API_VERSION, credentials = credentials)


class ListYoutubeVideosCommand(sublime_plugin.ApplicationCommand):
    # The cached object for talking to YouTube; when this is None, the command
    # will load credentials (and possibly prompt the user to log into YouTube)
    # before continuing.
    youtube = None

    """
    Generate a list of videos for a user's YouTube channel into a new view
    in the currently active window. This will use cached credentials if there
    are any, and ask the user to log in if not.
    """
    def run(self):
        # This operation might need to block, so use the async thread to run
        # it, which is awful and terrible in many ways, but good enough until
        # we know enough about this whole process to be able to decide on an
        # appropriate structure.
        sublime.set_timeout_async(lambda: self.dirty_hack())

    def dirty_hack(self):
        if self.youtube == None:
            self.youtube = get_authenticated_service()

        try:
            uploads_playlist_id = self.get_uploads_playlist()
            if uploads_playlist_id:
                self.get_playlist_contents(uploads_playlist_id)
            else:
                print('There is no uploaded videos playlist for this user.')
        except HttpError as e:
            print('An HTTP error %d occurred:\n%s' % (e.resp.status, e.content))


    def get_uploads_playlist(self):
        """
        Retreive the playlist ID for the uploaded videos of the user that is
        currently logged in

        This can return None if there are no videos.
        """

        channels_response = self.youtube.channels().list(
            mine=True,
            part='contentDetails'
        ).execute()

        # From the API response, extract the playlist ID that identifies the
        # list of videos uploaded to the authenticated user's channel.
        for channel in channels_response['items']:
            return channel['contentDetails']['relatedPlaylists']['uploads']

        return None


    def get_playlist_contents(self, playlist_id):
        """
        Given the ID of a playlsit for a user, fetch the contents of that
        playlist.
        """
        playlistitems_list_request = self.youtube.playlistItems().list(
            playlistId=playlist_id,
            part='snippet',
            maxResults=5
        )

        print('Videos in list %s' % playlist_id)
        while playlistitems_list_request:
            playlistitems_list_response = playlistitems_list_request.execute()

            # Print information about each video.
            for playlist_item in playlistitems_list_response['items']:
                title = playlist_item['snippet']['title']
                video_id = playlist_item['snippet']['resourceId']['videoId']
                print('%s (%s)' % (title, video_id))

            playlistitems_list_request = self.youtube.playlistItems().list_next(
                playlistitems_list_request, playlistitems_list_response)

