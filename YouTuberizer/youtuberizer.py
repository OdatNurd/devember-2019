import sublime
import sublime_plugin

import os


from .networking import NetworkManager, stored_credentials_path, log


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
        print("Running the dirty hack")
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
