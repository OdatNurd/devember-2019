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


class YoutuberizerListVideosCommand(sublime_plugin.ApplicationCommand):
    """
    Generate a list of videos for a user's YouTube channel into a new view
    in the currently active window. This will use cached credentials if there
    are any, and ask the user to log in if not.
    """
    def run(self):
        netManager.request(Request("authorize"), self.result)

    def result(self, request, success, result):
        if success:
            if request.name == "authorize":
                netManager.request(Request("uploads_playlist"), self.result)
            elif request.name == "uploads_playlist":
                netManager.request(Request("playlist_contents", playlist_id=result), self.result)
            elif request.name == "playlist_contents":
                window = sublime.active_window()
                window.show_quick_panel(result, lambda idx: self.select_video(result[idx]))

    def select_video(self, video):
        sublime.set_clipboard(video[1])
        sublime.status_message('URL Copied: %s' % video[0])


###----------------------------------------------------------------------------
