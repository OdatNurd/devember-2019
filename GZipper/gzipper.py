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
        "unzip_on_load": True
    }


###----------------------------------------------------------------------------


def gz_setting(key):
    """
    Get a package setting from the cached settings object with a sensible
    default.
    """
    default = gz_setting.default.get(key, None)
    return gz_setting.obj.get(key, default)


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
        with gzip.open(org_name, 'rb') as infile:
            with open(new_name, 'wb') as outfile:
                shutil.copyfileobj(infile, outfile)

            # Open the uncompressed file and tell it what gzipped file it's
            # tracking.
            gzView = self.view.window().open_file(new_name)
            gzView.settings().set("_gzip_name", org_name)

            # Close our view now
            self.view.close()


    def is_enabled(self):
        """
        Only enable the command for files with a .gz extension (so that we can
        get the underlying name of the file) which are also gzipped files.
        """
        v = self.view
        return (v.encoding() == "Hexadecimal" and
                v.substr(sublime.Region(0, 4)) == "1f8b" and
                v.file_name() is not None and
                v.file_name().endswith(".gz"))


###----------------------------------------------------------------------------


class GzipFileListener(sublime_plugin.ViewEventListener):
    """
    Event listener exclusively for Gzipped file instances; every time a file
    is saved, the compressed version is recreated and the file is removed on
    close.
    """
    @classmethod
    def is_applicable(cls, settings):
        return settings.has("_gzip_name")

    def on_close(self):
        os.remove(self.view.file_name())

    def on_post_save(self):
        org_filename = self.view.settings().get("_gzip_name")

        with gzip.open(org_filename, 'wb') as outfile:
            with open(self.view.file_name(), 'rb') as infile:
                shutil.copyfileobj(infile, outfile)


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
