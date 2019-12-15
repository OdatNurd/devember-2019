# GZipper
---------

This package performs simple `gzip` operations, allowing you to easily work
with gzipped files from directly within Sublime. Various functionality in the
package requires that `enable_hexadecimal_encoding` be enabled in your user
preferences, since this will allow Sublime to open a binary file without data
loss.

By default, the package will automatically recognize gzipped files and will
uncompress them for editing. This is done by creating an uncompressed version
of the file for you to edit which will be recompressed every time you save the
file, and will be deleted when you close the file.

You can turn this off by turning off `unzip_on_load` in the package settings,
in which case you need to manually trigger the command instead.

## Commands
-----------

  * `GZipper: Unzip and Edit` will be displayed for any gzipped file that is
  open and not currently uncompressed. This command will not be available if
  `unzip_on_load` is enabled because it will be triggerd automatically in that
  case.

  * `GZipper: Create Compressed Version` will create a gzipped version of the
  file that you are currently editing by appending `.gz` to the name of the
  current file (which must already exist on disk). This is a one time operation,
  and the original file is left as-is.

  * `GZipper: Convert to Gzip` will create a gzipped version of the file that
  you are already editing as if you had opened a gzip archive; this means that
  every time you save the file, the compressed version will change. When you
  close the file, the original file will be deleted.


## Settings
-----------

This package provides the following settings:

  * `unzip_on_load` (default: `true`) controls whether or not the package will
  check automatically on every file load to see if the current file is a
  `gzip` file, and if so unzip and open it for editing.

  * `compression_level` (default: 9) controls how much compression is used
  when writing the output file. This value can range from 0 to 9, where 0 is
  no compression and 9 is maximum compression. Compression takes longer at
  higher settings.

  * `trash_temp_on_close` (default: true) controls what should happen to the
  temporary file used while editing a `gzipped` file when you close it. The
  default value will put the temporary file in the trash; set it to `false` to
  permanently delete the file instead (e.g. if you don't want a backup just
  in case).

  * `delete_on_trash_faile` (default: false) controls what should happen when
  an attempt to trash a temporary file fails. When this is `false`, the
  temporary file is left in place; setting this to `true` will ***permanently
  delete*** the temporary file, as if `trash_temp_on_close` was `false`.

  * `close_temp_on_delete` (default: false) controls what happens to the
  temporary file buffer used to edit a gzipped file when you use the command
  that deletes the `gzip` file and also select to delete the temporary file as
  well. When this is `false`, the tab is left open after the file is deleted,
  allowing you to see the content and revive the file by saving it. Set this
  to `true` to close the tab when this happens.