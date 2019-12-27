import sublime
import sublime_plugin

import os


from .networking import NetworkManager, Request, stored_credentials_path, log


###----------------------------------------------------------------------------


# Our global network manager object
netManager = None


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


class YoutubeRequest():
    """
    This class abstracts away the common portions of using the NetworkManager
    to make requests and get responses back.

    A request can be made via the `request()` method, and the result will
    be automatically directed to a method in the class. The default handler
    is the name of the request preceeded by an underscore.
    """
    def request(self, request, handler=None, **kwargs):
        netManager.request(Request(request, handler, **kwargs), self.result)

    def result(self, request, success, result):
        attr = request.handler if success else "_error"
        if not hasattr(self, attr):
            raise RuntimeError("'%s' has no handler for request '%s'" % (
                self.name(), request.name))

        handler = getattr(self, attr)
        handler(request, result)

    def _error(self, request, result):
        log("""
            An error occured while talking to YouTube

            Request: {req}
            Result:  {err}
            """, error=True, req=request.name, err=result)


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
        return netManager.has_credentials()


###----------------------------------------------------------------------------


class YoutuberizerListVideosCommand(sublime_plugin.ApplicationCommand, YoutubeRequest):
    """
    Generate a list of videos for a user's YouTube channel into a new view
    in the currently active window. This will use cached credentials if there
    are any, and ask the user to log in if not.
    """
    def run(self):
        self.request("authorize")

    def _authorize(self, request, result):
        self.request("uploads_playlist")

    def _uploads_playlist(self, request, result):
        self.request("playlist_contents", playlist_id=result)

    def _playlist_contents(self, request, result):
        window = sublime.active_window()
        window.show_quick_panel(result, lambda i: self.select_video(result[i]))

    def select_video(self, video):
        sublime.set_clipboard(video[1])
        sublime.status_message('URL Copied: %s' % video[0])

    def is_enabled(self, force=False):
        return netManager.has_credentials()


###----------------------------------------------------------------------------
