#!/usr/bin/env python

#    Copyright (C) 2012  Florian Ludwig  <f.ludwig@greyrook.com>


import os
from errno import *
from stat import *
import time
import re
import thread
from posix import stat_result
from collections import OrderedDict

import fuse


fuse.fuse_python_api = (0, 2)
fuse.feature_assert('stateful_files', 'has_init')

#                         year    -   month  -   day    -   hour   -  minute
BACKUP_FILE = re.compile('[0-9]{4}-[0,1][0-9]-[0-3][0-9]-[0-2][0-9]-[0-5][0-9] ')


def flag2mode(flags): # from FUSE example
    md = {os.O_RDONLY: 'r', os.O_WRONLY: 'w', os.O_RDWR: 'w+'}
    m = md[flags & (os.O_RDONLY | os.O_WRONLY | os.O_RDWR)]

    if flags | os.O_APPEND:
        m = m.replace('w', 'a', 1)

    return m


class RSnapshotFS(fuse.Fuse):
    def __init__(self, *args, **kw):
        super(BackupFS, self).__init__(*args, **kw)
        thread.start_new_thread(self._update_backup_list, ())

    def _update_backup_list(self):
        """We update the backup list every 5 minutes"""
        while True:
            time.sleep(300)
            self._refresh_backup_list()

    def _refresh_backup_list(self):
        self.backups = OrderedDict()
        self.backup_times = {}
        backups = [self.root + path
                    for path in os.listdir(self.root)]
        backups.sort(key=lambda path: os.lstat(path).st_mtime)
        for backup in backups:
            self.backups[backup] = time.strftime('%Y-%m-%d-%H-%M',
                                       time.localtime(os.lstat(backup).st_mtime))
            self.backup_times[self.backups[backup]] = backup

    def getattr(self, path):
        for backup in self.backups:
            fpath = backup + path
            if os.path.exists(fpath):
                f_stat = os.lstat(fpath)
                mode = f_stat.st_mode
                if S_ISDIR(mode):
                    return f_stat
                else:
                    # it is a file, show as dir
                    f_stat = list(f_stat)
                    f_stat[0] = mode & 0b111111111111 | S_IFDIR
                    f_stat = stat_result(f_stat)
                    assert S_ISDIR(f_stat.st_mode)
                    return f_stat
        # either the path does not exist or it actually is a file
        real_path = self._get_real_path(path)
        if real_path:
            return os.lstat(real_path)

    def _get_real_path(self, path):
        pos = path.rfind('/')
        fname = path[pos+1:]
        if BACKUP_FILE.match(fname):
            # this might be a backup file.
            backup_time = fname[:16]
            if backup_time in self.backup_times:
                real_path = self.backup_times[backup_time] + path[:pos]
                return real_path

    def readlink(self, path): # TODO
        raise NotImplementedError()
        return os.readlink(self.root + path)

    def readdir(self, path, offset):
        assert offset == 0
        fnames = set()
        fname = path[path.rfind('/')+1:]
        mtimes = set()
        for backup, prefix in self.backups.items():
            if os.path.exists(backup + path):
                if os.path.isdir(backup + path):
                    fnames.update(os.listdir(backup + path))
                else:
                    # it is a file
                    # We only show the first appearance of any version of a
                    # file. self.backups is *orderd* so we show the earliest
                    # version of each file
                    mtime = os.stat(backup + path).st_mtime
                    if not mtime in mtimes:
                        fnames.add(prefix + ' ' + fname)
                        mtimes.add(mtime)

        for e in fnames:
            yield fuse.Direntry(e)


    # ---- modifications are not allowed, so I don't implement these:
    #def unlink(self, path):
    #def rmdir(self, path):
    #def symlink(self, path, path1):
    #def rename(self, path, path1):
    #def link(self, path, path1):
    #def chmod(self, path, mode):
    #def chown(self, path, user, group):
    #def truncate(self, path, len):
    #def mknod(self, path, mode, dev):
    #def mkdir(self, path, mode):
    #def utime(self, path, times):
#    def utimens(self, path, ts_acc, ts_mod):

    def access(self, path, mode):
        # TODO IMPLEMENT
        pass # we don't care about access
        #    return -EACCES

    # TODO
    #def statfs(self):
    #    """
    #    Should return an object with statvfs attributes (f_bsize, f_frsize...).
    #    Eg., the return value of os.statvfs() is such a thing (since py 2.2).
    #    If you are not reusing an existing statvfs object, start with
    #    fuse.StatVFS(), and define the attributes.
    #
    #    To provide usable information (ie., you want sensible df(1)
    #    output, you are suggested to specify the following attributes:
    #
    #        - f_bsize - preferred size of file blocks, in bytes
    #        - f_frsize - fundamental size of file blcoks, in bytes
    #            [if you have no idea, use the same as blocksize]
    #        - f_blocks - total number of blocks in the filesystem
    #        - f_bfree - number of free blocks
    #        - f_files - total number of file inodes
    #        - f_ffree - nunber of free file inodes
    #    """
    #    return os.statvfs(".")

    def fsinit(self):
        if not self.root.endswith('/'):
            self.root += '/'
        self._refresh_backup_list()
        self.BackUpFile.fs = self

    def main(self, *a, **kw):
        self.file_class = self.BackUpFile
        return super(RSnapshotFS, self).main(*a, **kw)

    class RSnapshotFile(object):
        def __init__(self, path, flags, *mode):
            real_path = self.fs._get_real_path(path)
            self.file = os.fdopen(os.open(real_path, flags, *mode),
                                  flag2mode(flags))
            self.fd = self.file.fileno()

        def read(self, length, offset):
            self.file.seek(offset)
            return self.file.read(length)

        def write(self, buf, offset):
            self.file.seek(offset)
            self.file.write(buf)
            return len(buf)

        def release(self, flags):
            self.file.close()

        def _fflush(self):
            if 'w' in self.file.mode or 'a' in self.file.mode:
                self.file.flush()

        def fsync(self, isfsyncfile):
            self._fflush()
            if isfsyncfile and hasattr(os, 'fdatasync'):
                os.fdatasync(self.fd)
            else:
                os.fsync(self.fd)

        def flush(self):
            self._fflush()
            # cf. xmp_flush() in fusexmp_fh.c
            os.close(os.dup(self.fd))

        def fgetattr(self):
            return os.fstat(self.fd)

        def ftruncate(self, len):
            self.file.truncate(len)

        def lock(self, cmd, owner, **kw):
            return -EINVAL


def main():
    usage = """Backup FS, view rsnapshot more comfortable

""" + fuse.Fuse.fusage

    server = RSnapshotFS(version="%prog " + fuse.__version__,
                         usage=usage,
                         dash_s_do='setsingle')

    server.parser.add_option(mountopt="root", metavar="PATH",
                             help="path to rsnapshort folder")
    server.parse(values=server, errex=1)
    server.main()


if __name__ == '__main__':
    main()
