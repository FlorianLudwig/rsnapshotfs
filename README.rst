rsnapshotfs
===========

Given the following example rsnopshot backup folder::

    snapshot_root/test.0/changed_file.txt
    snapshot_root/test.0/not_changed_file.txt

    snapshot_root/test.1/changed_file.txt
    snapshot_root/test.1/not_changed_file.txt


If you mount rsnapshot as a view for this folder via::

    python mount.py  -o root=/path/to/snapshot_root mount_point


The mount_point would look like this::

    snapshot_root/changed_file.txt/2015-02-02-18-39 changed_file.txt
    snapshot_root/changed_file.txt/2015-02-02-18-38 changed_file.txt

    snapshot_root/not_changed_file.txt/2015-02-02-18-38 not_changed_file.txt


TODO
----

 * docs
 * tests
 * handle snapshots less than 1 minute apart