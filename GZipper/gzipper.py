import sublime
import sublime_plugin

import os
import tempfile
import gzip
import shutil
import threading


###----------------------------------------------------------------------------


def plugin_loaded():
    """
    On plugin load, cache the settings object for our package.
    """
    gz_setting.obj = sublime.load_settings("GZipper.sublime-settings")
    gz_setting.default = {
        "unzip_on_load": True,
        "compression_level": 9,
        "trash_temp_on_close": True,
        "delete_on_trash_fail": False,
        "close_temp_on_delete": False
    }


###----------------------------------------------------------------------------


def gz_setting(key):
    """
    Get a package setting from the cached settings object with a sensible
    default.
    """
    default = gz_setting.default.get(key, None)
    return gz_setting.obj.get(key, default)


def home_relative_path(path):
    """
    Given a filename, return back a version relative to the home directory,
    if that's applicable.
    """
    home = os.path.expanduser("~")
    return path if not path.startswith(home) else "~" + path[len(home):]


def is_gzip_file(view):
    """
    Given a view, determine if that view (probably) contains a gzipped file
    or not. This is currently based on a combination of the extension and the
    file being a binary file with the right magic bytes.
    """
    return (view.encoding() == "Hexadecimal" and
            view.substr(sublime.Region(0, 4)) == "1f8b" and
            view.file_name() is not None and view.file_name().endswith(".gz"))


def gzip_file(from_path, to_path):
    """
    Compress a file on disk to the file named.
    """
    with gzip.open(to_path, 'wb', gz_setting('compression_level')) as outfile:
        with open(from_path, 'rb') as infile:
            shutil.copyfileobj(infile, outfile)


def gunzip_file(from_path, to_path):
    """
    Uncompress a file on disk to the file named. If to_path is not provided, a
    new temporary file based on the from_path will be used instead.

    The name of the file that was gzipped to will be returned; this may be the
    same as the input.
    """
    handle = None
    if to_path is None:
        _, file = os.path.split(from_path)
        root, ext = os.path.splitext(os.path.splitext(file)[0])
        handle, to_path = tempfile.mkstemp(ext, root + "_")

    with gzip.open(from_path, 'rb') as infile:
        with open(handle, 'wb') as outfile:
            shutil.copyfileobj(infile, outfile)

    return to_path


def trash_file(filename):
    """
    Given a file name, send it to the trash on the system.
    """
    trash_it = gz_setting("trash_temp_on_close")
    try:
        if not trash_it:
            os.remove(filename)
        else:
            # Import send2trash on demand; see Default/side_bar.py.
            import Default.send2trash as send2trash

            # send2trash tries to put files in a Trash folder on the same
            # partition as where the file came from (so it can simply move the
            # file there).
            send2trash.send2trash(filename)
    except:
        if trash_it and gz_setting("delete_on_trash_fail"):
            os.remove(filename)
        else:
            sublime.status_message("GZipper: Unable to clean up temp file")


def apply_gzip_settings(view, temp_name, gzip_name, delete_on_close):
    """
    Given a view, apply the appropriate settings to indicate to the plugin
    that the view represents a gzipped file. The temp_name is the version of
    the file that is being edited.
    """
    settings = view.settings()

    settings.set("_gz_tmp_name", temp_name)
    settings.set("_gz_name", gzip_name)
    settings.set("_gz_delete", delete_on_close)

    # Flag the view as a gzipped file
    view.set_status("gzipper", "[gzipped file]")


def remove_gzip_settings(view):
    """
    Given a view, remove the settings that mark it as being a gzipped file
    buffer.
    """
    settings = view.settings()

    settings.erase("_gz_tmp_name")
    settings.erase("_gz_name")
    settings.erase("_gz_delete")
    view.erase_status("gzipper")


def spinner_key():
    """
    Get a unique spinner key for displaying a spinner in the status bar. This
    needs to be thread safe.
    """
    with spinner_key.lock:
        spinner_key.counter += 1
        return "_gz_spinner_%d" % spinner_key.counter

spinner_key.counter = 0
spinner_key.lock = threading.Lock()


###----------------------------------------------------------------------------


class Spinner():
    """
    Implement a simple spinner. Given a window and a thread, this will display
    an updating spinner in the status bar of that window, moving from view to
    view as the current view changes. When the thread stops running, the
    spinner automatically removes itself.
    """
    spin_characters = "|/-\\"

    def __init__(self, window, thread, text):
        self.window = window
        self.thread = thread
        self.text = text
        self.key = spinner_key()
        self.view = None

        sublime.set_timeout(lambda: self.tick(0), 250)

    def tick(self, position):
        current_view = self.window.active_view()

        if self.view is not None and current_view != self.view:
            self.view.erase_status(self.key)
            self.view = None

        if not self.thread.is_alive():
            return current_view.erase_status(self.key)

        text = "%s [%s]" % (self.text, self.spin_characters[position])
        position = (position + 1) % len(self.spin_characters)

        current_view.set_status(self.key, text)
        if self.view is None:
            self.view = current_view

        sublime.set_timeout(lambda: self.tick(position), 250)


###----------------------------------------------------------------------------


class WorkerThread(threading.Thread):
    """
    Perform work in the background, maintaining an active spinner to show that
    the thread is running. The given callback will be invoked once the thread
    has completed.

    This is meant to be a base class for background work, abstracting away the
    work of maintaining the spinner and
    """
    def __init__(self, window, spin_text, callback, **kwargs):
        super().__init__()

        self.window = window
        self.spin_text = spin_text
        self.callback = callback
        self.args = kwargs

        self.start()

    def _process(self):
        pass

    def run(self):
        Spinner(self.window, self, self.spin_text)

        self._process(self.args)

        if self.callback is not None:
            # Hard learned lessons; If we don't break this link, our thread
            # will dangle forever because it's holding a reference to the
            # callback and the callback is holding a reference to the thread.
            callback = self.callback
            del self.callback

            # Trigger the callback in the main Sublime thread
            sublime.set_timeout(lambda: callback(self), 0)


###----------------------------------------------------------------------------


class GzipThread(WorkerThread):
    """
    Perform a gzip operation in a background thread so that large files don't
    block the user interface.
    """
    def _process(self, args):
        gzip_file(args["from_path"], args["to_path"])


###----------------------------------------------------------------------------


class GunzipThread(WorkerThread):
    """
    Perform a gunzip operation in a background thread so that large files
    don't block the user interface.
    """
    def _process(self, args):
        args["to_path"] = gunzip_file(args["from_path"], args["to_path"])


###----------------------------------------------------------------------------


class ReopenAsGzipCommand(sublime_plugin.TextCommand):
    """
    For a view that is a gzipped file, this will open up a new view that is
    the uncompressed version of the file, then close this view. The new view
    will re-create this gzipped file on save.
    """
    def run(self, edit):
        # Save the current file name so that we can recreate this file later.
        org_name = self.view.file_name()

        def on_done(thread):
            # Get the name the other end used.
            new_name = thread.args["to_path"]

            # Open the uncompressed file and tell it what gzipped file it's
            # tracking.
            gzView = self.view.window().open_file(new_name)
            apply_gzip_settings(gzView, new_name, org_name, delete_on_close=True)

            # Close our view now
            self.view.close()

        # Uncompress the file into the buffer now; provide None as the output
        # so a new temporary file gets created.
        GunzipThread(self.view.window(), "Unzipping", on_done,
                     from_path=org_name, to_path=None)


    def is_enabled(self):
        """
        Only enable the command for files with a .gz extension (so that we can
        get the underlying name of the file) which are also gzipped files.
        """
        return is_gzip_file(self.view)


###----------------------------------------------------------------------------


class GzipCompressCommand(sublime_plugin.TextCommand):
    """
    For a view that is not currently a gzipped file, create a compressed
    version of the file on disk,
    """
    def run(self, edit, only_compress=False, delete_on_close=False, force=False):
        current_name = self.view.file_name()
        gzip_name = current_name + ".gz"

        # If the output file exists, verify if we should clobber it
        if os.path.exists(gzip_name) and not force:
            msg = "%s\n\nFile already exists; overwrite it?" % gzip_name
            if sublime.yes_no_cancel_dialog(msg) == sublime.DIALOG_YES:
                self.view.run_command("gzip_compress", {
                    "only_compress": only_compress,
                    "delete_on_close": delete_on_close,
                    "force": True
                })

            return

        def on_done(thread):
            if only_compress:
                return

            apply_gzip_settings(self.view, current_name, gzip_name, delete_on_close)

        GzipThread(self.view.window(), "Zipping", on_done,
                   from_path=current_name, to_path=gzip_name)


    def is_enabled(self, only_compress=False, delete_on_close=False, force=False):
        return not is_gzip_file(self.view) and self.view.file_name() is not None


###----------------------------------------------------------------------------


class GzipRemoveArchiveCommand(sublime_plugin.TextCommand):
    """
    Remove the underlying gzip archive for a file and (if asked to) the
    temporary file being used to edit it as well. This could be used to decide
    that you no longer want an archive that you created (from a non-gzip file)
    or to get rid of a gzip file as well as the temporary file.
    """
    def run(self, edit, remove_temp=False, force=False):
        if not force:
            msg = "This will remove the gzip file%s\n\nAre you sure?" % (
                " and this temporary file" if remove_temp else "")
            if sublime.yes_no_cancel_dialog(msg) == sublime.DIALOG_YES:
                return self.view.run_command("gzip_remove_archive", {
                    "remove_temp": remove_temp,
                    "force": True
                })

            return


        gzip_name = self.view.settings().get("_gz_name")
        trash_file(gzip_name)

        if remove_temp:
            trash_file(self.view.file_name())
            if gz_setting("close_temp_on_delete"):
                self.view.set_scratch(True)
                self.view.close()
                return

        # Temporary file was not removed, or it was but it was left open; break
        # the connection to the now-missing file.
        remove_gzip_settings(self.view)

    def is_enabled(self, remove_temp=False, force=False):
        return self.view.settings().has("_gz_name")


###----------------------------------------------------------------------------


class GzipFileListener(sublime_plugin.ViewEventListener):
    """
    Event listener exclusively for Gzipped file instances; every time a file
    is saved, the compressed version is recreated and the file is removed on
    close.
    """
    @classmethod
    def is_applicable(cls, settings):
        return settings.has("_gz_name")

    def on_close(self):
        if self.view.settings().get("_gz_delete", False):
            trash_file(self.view.file_name())

    def on_pre_save(self):
        s = self.view.settings()
        if s.get("_gz_tmp_name") != self.view.file_name():
            # Get rid of the old temporary file since we're effectively
            # closing it.
            if s.get("_gz_delete", False):
                trash_file(s.get("_gz_tmp_name"))

            # Erase the settings that we use to track ourselves.
            remove_gzip_settings(self.view)

    def on_post_save(self):
        archive_name = self.view.settings().get("_gz_name")

        def on_done(thread):
            # Show a status message after the command exits, so we can override
            # the default save message.
            sublime.set_timeout(lambda: self.view.window().status_message(
                "Compressed %s" % home_relative_path(archive_name)))

        GzipThread(self.view.window(), "Zipping", on_done,
                   from_path=self.view.file_name(), to_path=archive_name)



###----------------------------------------------------------------------------


class GzipLoadListener(sublime_plugin.EventListener):
    """
    For every file that is loaded, attempt to re-open it as a gzip file. This
    will only actualy trigger for files that are legitimately gzipped files;
    the command will not enable itself for other files.
    """
    def on_load(self, view):
        if gz_setting("unzip_on_load"):
            view.run_command("reopen_as_gzip")


###----------------------------------------------------------------------------
