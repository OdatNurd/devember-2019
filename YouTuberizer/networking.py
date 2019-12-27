import sublime
import sublime_plugin

from threading import Thread, Event, Lock
import queue

import os
import json
import textwrap

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


###----------------------------------------------------------------------------


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


def log(msg, *args, dialog=False, error=False, panel=False, **kwargs):
    """
    Generate a log message to the console, and then also optionally to a dialog
    or dedocated output panel.

    The message will be formatted and dedented before being displayed and will
    have a prefix that indicates where it's coming from.

    """
    msg = textwrap.dedent(msg.format(*args, **kwargs)).strip()

    # sublime.error_message() always displays its content in the console
    if error:
        print("YouTuberizer:")
        return sublime.error_message(msg)

    for line in msg.splitlines():
        print("YouTuberizer: {msg}".format(msg=line))

    if dialog:
        sublime.message_dialog(msg)

    if panel:
        window = sublime.active_window()
        if "output.youtuberizer" not in window.panels():
            view = window.create_output_panel("youtuberizer")
            view.set_read_only(True)
            view.settings().set("gutter", False)
            view.settings().set("rulers", [])
            view.settings().set("word_wrap", False)

        view = window.find_output_panel("youtuberizer")
        view.run_command("append", {
            "characters": msg + "\n",
            "force": True,
            "scroll_to_end": True})

        window.run_command("show_panel", {"panel": "output.youtuberizer"})


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
        "refresh_token": credentials.refresh_token,
        "id_token": credentials.id_token
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
        cached["id_token"],
        CLIENT_CONFIG["installed"]["token_uri"],
        CLIENT_CONFIG["installed"]["client_id"],
        CLIENT_CONFIG["installed"]["client_secret"],
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


class Request(dict):
    """
    Simple wrapper for a request object. This is essentially a hashable
    dictionary object that doesn't throw exceptions when you attempt to access
    a key that doesn't exist, and which inherently knows what it's name is.
    """
    def __init__(self, name, handler=None, **kwargs):
        super().__init__(self, **kwargs)
        self.name = name
        self.handler = handler or '_' + name

    def __key(self):
        return tuple((k,self[k]) for k in sorted(self))

    def __hash__(self):
        return hash(self.__key())

    def __eq__(self, other):
        return self.__key() == other.__key()

    def __getitem__(self, key):
        return self.get(key, None)

    def __set_name(self, value):
        self["_name"] = value

    def __get_name(self):
        return self.get("_name", None)

    def __set_handler(self, value):
        self["_handler"] = value

    def __get_handler(self):
        return self.get("_handler", None)

    name = property(__get_name, __set_name)
    handler = property(__get_handler, __set_handler)


###----------------------------------------------------------------------------


class NetworkManager():
    """
    This class manages all of our network interactions by using a background
    thread (or threads) to make requests, handing results back as they are
    obtained and signalling other events.

    There should be a single global instance of this class created; it connects
    the network data gathering with the Sublime front end.
    """
    def __init__(self):
        self.thr_event = Event()
        self.request_queue = queue.Queue()
        self.net_thread = NetworkThread(self.thr_event, self.request_queue)
        self.authorized = False
        self.cache = {}

    def startup(self):
        """
        Start up the networking system; this initializes and starts up the
        network thread. This should be called from plugin_loaded() get
        everything ready.
        """
        log("Initializing")
        self.net_thread.start()

    def shutdown(self):
        """
        Shut down the networking system; this shuts down any background threads
        that may be running. This should be called from plugin_unloaded() to do
        cleanup before we go away.
        """
        log("Shutting Down")
        self.thr_event.set()
        self.net_thread.join(0.25)

    def has_credentials(self):
        """
        Returns an indication of whether or not there are currently stored
        credentials for a YouTube login; this indicates that the user has
        already authorized the application to access their account.
        """
        return os.path.isfile(stored_credentials_path())

    def is_authorized(self):
        """
        Determine if the plugin is currently authorized or not; this
        is an indication that data requests can be made; prior to this point
        requests will fail.
        """
        return self.authorized

    def callback(self, request, user_callback, success, result):
        """
        This callback is what is submitted to the network thread to invoke
        when a result is delivered. We get the success and the result, as
        well as the request that was made and the user callback.

        NOTE: The NetworkThread always invokes this in Sublime's main thread,
        not from within itself; this is the barrier where the requested data
        shifts between threads.
        """
        if success:
            self.cache[request] = result
        elif request in self.cache:
            del self.cache[request]

        # Handle updates of internal state.
        if request.name == "authorize":
            self.authorized = success

        user_callback(request, success, result)

    def request(self, request, callback, refresh=False):
        """
        Submit the given request to the network thread; the thread will execute
        the task and then invoke the callback once complete; the callback gets
        called with a boolean that indicates the success or failure, and either
        the error reason (on fail) or the result (on success).

        Internally this class will cache the result of some requests; in order
        to force a re-request, set refresh to True.
        """
        if request in self.cache and not refresh:
            return callback(request, True, self.cache[request])

        self.request_queue.put({
            "request": request, 
            "callback": lambda s, r: self.callback(request, callback, s, r)
        })


###----------------------------------------------------------------------------


class NetworkThread(Thread):
    """
    The background thread that is responsible for doing all of network
    operations. All of the state is kept in this thread; requests are added in
    and callbacks are used to signal results out.
    """
    def __init__(self, event, queue):
        # log("== Creating network thread")
        super().__init__()
        self.event = event
        self.requests = queue
        self.youtube = None

        # The requests that we know how to service, and what method invokes
        # them.
        self.request_map = {
            "authorize": self.authenticate,
            "uploads_playlist": self.uploads_playlist,
            "playlist_contents": self.playlist_contents
        }

    # def __del__(self):
    #     log("== Destroying network thread")

    def authenticate(self, request):
        """
        Start the authorization flow. If the user has never authorized the app,
        this will launch a browser to ask them to do so and will return a
        result as appropriate. Otherwise it will used cached credentials.
        """
        self.youtube = get_authenticated_service()
        return "Authenticated"

    def uploads_playlist(self, request):
        """
        YouTube stores the list of uploaded videos for a user in a specific
        playlist designated for that purposes. This call obtains the playlist
        ID of that playlist and returns it.

        This can return None if the user has not uploaded any videos.
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

    def playlist_contents(self, request):
        """
        Given the ID of a playlsit for a user, fetch the contents of that
        playlist.
        """
        playlistitems_list_request = self.youtube.playlistItems().list(
            playlistId=request["playlist_id"],
            part='snippet',
            # maxResults=20
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

        return list(sorted(results))


    def handle_request(self, request_obj):
        """
        Handle the asked for request, dispatching an appropriate callback when
        the request is complete (depending on whether it worked or not).
        """
        request = request_obj["request"]
        callback = request_obj["callback"]

        success = True
        result = None

        try:
            handler = self.request_map.get(request.name, None)
            if handler is None:
                raise ValueError("Unknown request '%s'" % request.name)

            success = True
            result = handler(request)

        except Exception as err:
            success = False
            result = str(err)

        sublime.set_timeout(lambda: callback(success, result))
        self.requests.task_done()

    def run(self):
        """
        The main loop needs to loop until a semaphore tells it that it's time
        to quit, at which point it will drop out of the loop and gracefully
        exit, perhaps telling all connections to close in response.

        This needs to select all connections for reading, only those that have
        data pending send for writing, and needs to safely busy loop when there
        are no connections.
        """
        # log("== Entering network loop")
        while not self.event.is_set():
            try:
                request = self.requests.get(block=True, timeout=0.25)
                self.handle_request(request)

            except queue.Empty:
                pass

        log("network thread terminating")


###----------------------------------------------------------------------------
