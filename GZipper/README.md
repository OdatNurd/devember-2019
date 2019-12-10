# GZipper
---------

This package performs simple `gzip` operations, allowing you to easily work
with gzipped files from directly within Sublime. When opening a `gzip`d file,
the package will uncompress it to a temporary file for you to edit,
recompressing every time you make changes, and remove the temporary version of
the file when you close it.

Various functionality in the package requires that `enable_hexadecimal_encoding`
be enabled in your user preferences, since this will allow Sublime to open a
binary file without data loss.


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
