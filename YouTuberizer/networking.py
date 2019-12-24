import sublime
import sublime_plugin

from threading import Thread, Event, Lock
import queue

import os
import time
import textwrap


###----------------------------------------------------------------------------


def log(msg, *args, dialog=False, error=False, panel=False, **kwargs):
    """
    Generate a log message to the console, and then also optionally to a dialog
    pr dedocated output panel.

    THe message will be formatted and dedented before being displayed and will
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

    def request(self, request, callback):
        """
        Submit the given request to the network thread; the thread will execute
        the task and then invoke the callback once complete; the callback gets
        called with a boolean that indicates the success or failure, and either
        the error reason (on fail) or the result (on success).
        """
        self.request_queue.put({"request": request, "callback": callback})


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

    # def __del__(self):
    #     log("== Destroying network thread")

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
            result = "The result goes here"

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
