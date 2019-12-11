import sublime
import sublime_plugin

import os
import gzip
import shutil


###----------------------------------------------------------------------------


def plugin_loaded():
    """
    On plugin load, cache the settings object for our package.
    """
    gz_setting.obj = sublime.load_settings("GZipper.sublime-settings")
    gz_setting.default = {
        "unzip_on_load": True,
        "compression_level": 9,
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
    Uncompress a file on disk to the file named.
    """
    with gzip.open(from_path, 'rb') as infile:
        with open(to_path, 'wb') as outfile:
            shutil.copyfileobj(infile, outfile)


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

        # From the name of the file, get the path and underlying file name; to
        # do that here we just throw the .gz off the end of the filename.
        path, file = os.path.split(org_name)
        name, ext = os.path.splitext(os.path.splitext(file)[0])

        # Create a new filename to store the uncompressed output.
        #
        # TODO: This will clobber files; maybe put the file in TMP or such?
        new_name = os.path.join(path, name + "_ungz" + ext)

        # Uncompress the file into the buffer now.
        gunzip_file(org_name, new_name)

        # Open the uncompressed file and tell it what gzipped file it's
        # tracking.
        gzView = self.view.window().open_file(new_name)
        gzView.settings().set("_gz_tmp_name", new_name)
        gzView.settings().set("_gz_name", org_name)
        gzView.settings().set("_gz_delete", True)

        # Flag the view as a gzipped file
        gzView.set_status("gzipper", "[gzipped file]")

        # Close our view now
        self.view.close()


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
    def run(self, edit, only_compress=False, delete_on_close=False):
        new_name = self.view.file_name() + ".gz"
        gzip_file(self.view.file_name(), new_name)

        if only_compress:
            return

        self.view.settings().set("_gz_name", new_name)
        self.view.settings().set("_gz_delete", delete_on_close)
        if delete_on_close:
            self.view.settings().set("_gz_tmp_name", self.view.file_name())

        gzView.set_status("gzipper", "[gzipped file]")

    def is_enabled(self, only_compress=False, delete_on_close=False):
        return not is_gzip_file(self.view)


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
            # Import send2trash on demand; see Default/side_bar.py.
            import Default.send2trash as send2trash

            send2trash.send2trash(self.view.file_name())

    def on_pre_save(self):
        s = self.view.settings()
        if s.get("_gz_tmp_name") != self.view.file_name():
            # Get rid of the old temporary file since we're effectively
            # closing it.
            if s.get("_gz_delete", False):
                import Default.send2trash as send2trash
                send2trash.send2trash(s.get("_gz_tmp_name"))

            # Erase the settings that we use to track ourselves.
            s.erase("_gz_name")
            s.erase("_gz_tmp_name")
            s.erase("_gz_delete")
            self.view.erase_status("gzipper")

    def on_post_save(self):
        archive_name = self.view.settings().get("_gz_name")
        gzip_file(self.view.file_name(), archive_name)

        # Show a status message after the command exits, so we can override
        # the default save message.
        sublime.set_timeout(lambda: self.view.window().status_message(
            "Compressed %s" % home_relative_path(archive_name)))


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
