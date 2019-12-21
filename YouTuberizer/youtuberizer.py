import sublime
import sublime_plugin

import os
import json

# A compatible version of this is available in hashlib in more recent builds of
# Python, but it takes keyword only arguments. You can swap to that one by
# modifying the call site as appropriate.
from pyscrypt import hash as scrypt
import pyaes

import google.oauth2.credentials
import google_auth_oauthlib.flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow

from .networking import NetworkManager, log


###----------------------------------------------------------------------------


# Our global network manager object
netManager = None


# The configuration information for our application; the values here are taken
# from the Google Application Console.
#
# Note that the client_secret is (as far as I can gather) not supposed to be
# used in this flow because there's no way to keep it a secret. However, the
# underlying library requires it to be there, and so does the Google endpoint.
#
# Basically everything I know is a lie, or there is some magic that I don't
# understand that somehow stops another application from masquerading as us
# because I don't see how you could possibly keep this informationa secret.
CLIENT_CONFIG = {
    "installed":{
        "client_id":"771245933356-mlq371ev2shqmv757uf24c009j4bv17q.apps.googleusercontent.com",
        "auth_uri":"https://accounts.google.com/o/oauth2/auth",
        "token_uri":"https://oauth2.googleapis.com/token",
        "client_secret":"v9GXqmgwHXssHuj8yKS3JXQa",
    }
}


# This OAuth 2.0 access scope allows for read-only access to the authenticated
# user's account, but not other types of account access.
SCOPES = ['https://www.googleapis.com/auth/youtube.readonly']
API_SERVICE_NAME = 'youtube'
API_VERSION = 'v3'

# The PBKDF Salt value; it needs to be in bytes.
_PBKDF_Salt = "YouTuberizerSaltValue".encode()

# The encoded password; later the user will be prompted for this on the fly,
# but for expediency in testing the password is currently hard coded.
_PBKDF_Key = scrypt("password".encode(), _PBKDF_Salt, 1024, 1, 1, 32)


###----------------------------------------------------------------------------


def plugin_loaded():
    """
    Initialize plugin state.
    """
    global netManager

    netManager = NetworkManager()
    netManager.startup()


def plugin_unloaded():
    global netManager

    if netManager is not None:
        netManager.shutdown()
        netManager = None


###----------------------------------------------------------------------------


def stored_credentials_path():
    """
    Obtain the cached credentials path, which is stored in the Cache folder of
    the User's configuration information.

    """
    if hasattr(stored_credentials_path, "path"):
        return stored_credentials_path.path

    path = os.path.join(sublime.packages_path(), "..", "Cache", "YouTuberizer.credentials")
    stored_credentials_path.path = os.path.normpath(path)

    return stored_credentials_path.path


def cache_credentials(credentials):
    """
    Given a credentials object, cache the given credentials into a file in the
    Cache directory for later use.
    """
    cache_data = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token
    }

    # Encrypt the cache data using our key and write it out as bytes.
    aes = pyaes.AESModeOfOperationCTR(_PBKDF_Key)
    cache_data = aes.encrypt(json.dumps(cache_data, indent=4))

    with open(stored_credentials_path(), "wb") as handle:
        handle.write(cache_data)


def get_cached_credentials():
    """
    Fetch the cached credentials from a previous operation; this will return
    None if there is currently no cached credentials. This will currently
    raise an exception if the file is broken (so don't break it).
    """
    try:
        # Decrypt the data with the key and convert it back to JSON.
        with open(stored_credentials_path(), "rb") as handle:
            aes = pyaes.AESModeOfOperationCTR(_PBKDF_Key)
            cache_data = aes.decrypt(handle.read()).decode("utf-8")

            cached = json.loads(cache_data)

    except FileNotFoundError:
        return None

    return google.oauth2.credentials.Credentials(
        cached["token"],
        cached["refresh_token"],
        CLIENT_CONFIG["installed"]["token_uri"],
        CLIENT_CONFIG["installed"]["client_id"],
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
        # TODO: This can raise exceptions, AccessDeniedError
        flow = InstalledAppFlow.from_client_config(CLIENT_CONFIG, SCOPES)
        credentials = flow.run_local_server(client_type="installed",
            authorization_prompt_message='YouTuberizer: Launching browser to log in',
            success_message='YouTuberizer login complete! You can close this window.')

        cache_credentials(credentials)

    return build(API_SERVICE_NAME, API_VERSION, credentials = credentials)


###----------------------------------------------------------------------------


class YoutuberizerLogoutCommand(sublime_plugin.ApplicationCommand):
    """
    If there are any cached credentials for the user's YouTube account,
    remove them. This will require that the user authenticate the app again
    in order to continue using it.
    """
    def run(self, force=False):
        if not force:
            msg = "If you proceed, you will need to re-authenticate. Continue?"
            if sublime.yes_no_cancel_dialog(msg) == sublime.DIALOG_YES:
                sublime.run_command("youtuberizer_logout", {"force": True})

            return

        # TODO: This would actually need to remove the current YouTube object,
        # but we're not our own thread yet. So this takes effect at the next
        # reload/restart instead.
        try:
            os.remove(stored_credentials_path())
            sublime.message_dialog("YouTuberizer credentials have been removed")

        except:
            pass

    def is_enabled(self, force=False):
        return os.path.isfile(stored_credentials_path())


###----------------------------------------------------------------------------


class YoutuberizerListVideosCommand(sublime_plugin.ApplicationCommand):
    """
    Generate a list of videos for a user's YouTube channel into a new view
    in the currently active window. This will use cached credentials if there
    are any, and ask the user to log in if not.
    """
    # The cached object for talking to YouTube; when this is None, the command
    # will load credentials (and possibly prompt the user to log into YouTube)
    # before continuing.
    youtube = None

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
                sublime.message_dialog("There are no uploaded videos to display")
        except HttpError as e:
            sublime.error_message("An HTTP error %d occurred:\n%s" % (e.resp.status, e.content))


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
            maxResults=20
        )

        results = []
        while playlistitems_list_request:
            playlistitems_list_response = playlistitems_list_request.execute()

            # Print information about each video.
            for playlist_item in playlistitems_list_response['items']:
                title = playlist_item['snippet']['title']
                video_id = playlist_item['snippet']['resourceId']['videoId']
                results.append([title, 'https://youtu.be/%s' % video_id])

            playlistitems_list_request = self.youtube.playlistItems().list_next(
                playlistitems_list_request, playlistitems_list_response)

        results = list(sorted(results))
        window = sublime.active_window()
        window.show_quick_panel(results, lambda idx: self.select_video(results[idx]))

    def select_video(self, video):
        sublime.set_clipboard(video[1])
        sublime.status_message('URL Copied: %s' % video[0] )


###----------------------------------------------------------------------------
