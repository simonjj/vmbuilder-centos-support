#    Uncomplicated VM Builder
#    Copyright (C) 2007-2009 Canonical Ltd.
#
#    See AUTHORS for list of contributors
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License version 3, as
#    published by the Free Software Foundation.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#    CLI plugin
import logging
import optparse
import os
import pwd
import shutil
import sys
import tempfile
import VMBuilder
import VMBuilder.util as util
from   VMBuilder.disk import parse_size
import VMBuilder.hypervisor
from   VMBuilder.exception import VMBuilderUserError, VMBuilderException

class CLI(object):
    arg = 'cli'

    def main(self):
        tmpfs_mount_point = None
        try:
            optparser = optparse.OptionParser()

            self.set_usage(optparser)

            optparser.add_option('--version',
                                 action='callback',
                                 callback=self.versioninfo,
                                 help='Show version information')

            group = optparse.OptionGroup(optparser, 'Build options')
            group.add_option('--debug',
                             action='callback',
                             callback=self.set_verbosity,
                             help='Show debug information')
            group.add_option('--verbose',
                             '-v',
                             action='callback',
                             callback=self.set_verbosity,
                             help='Show progress information')
            group.add_option('--quiet',
                             '-q',
                             action='callback',
                             callback=self.set_verbosity,
                             help='Silent operation')
            group.add_option('--overwrite',
                             '-o',
                             action='store_true',
                             help='Configuration file')
            group.add_option('--config',
                             '-c',
                             type='str',
                             help='Configuration file')
            group.add_option('--templates',
                             metavar='DIR',
                             help='Prepend DIR to template search path.')
            group.add_option('--destdir',
                             '-d',
                             type='str',
                             help='Destination directory')
            group.add_option('--only-chroot',
                             action='store_true',
                             help=("Only build the chroot. Don't install it "
                                   "on disk images or anything."))
            group.add_option('--chroot-dir',
                             help="Build the chroot in directory.")
            group.add_option('--existing-chroot',
                             help="Use existing chroot.")
            group.add_option('--tmp',
                             '-t',
                             metavar='DIR',
                             dest='tmp_root',
                             default=tempfile.gettempdir(),
                             help=('Use TMP as temporary working space for '
                                   'image generation. Defaults to $TMPDIR if '
                                   'it is defined or /tmp otherwise. '
                                   '[default: %default]'))
            group.add_option('--tmpfs',
                             metavar="SIZE",
                             help=('Use a tmpfs as the working directory, '
                                   'specifying its size or "-" to use tmpfs '
                                   'default (suid,dev,size=1G).'))
            optparser.add_option_group(group)

            group = optparse.OptionGroup(optparser, 'Disk')
            group.add_option('--rootsize',
                             metavar='SIZE',
                             default=4096,
                             help=('Size (in MB) of the root filesystem '
                                   '[default: %default]'))
            group.add_option('--optsize',
                             metavar='SIZE',
                             default=0,
                             help=('Size (in MB) of the /opt filesystem. If not'
                                   ' set, no /opt filesystem will be added.'))
            group.add_option('--swapsize',
                             metavar='SIZE',
                             default=1024,
                             help=('Size (in MB) of the swap partition '
                                   '[default: %default]'))
            group.add_option('--raw',
                             metavar='PATH',
                             type='str',
                             action='append',
                             help=("Specify a file (or block device) to use as "
                                   "first disk image (can be specified multiple"
                                   " times)."))
            group.add_option('--part',
                             metavar='PATH',
                             type='str',
                             help=("Specify a partition table in PATH. Each "
                                   "line of partfile should specify (root "
                                   "first): \n    mountpoint size \none per "
                                   "line, separated by space, where size is "
                                   "in megabytes. You can have up to 4 "
                                   "virtual disks, a new disk starts on a "
                                   "line containing only '---'. ie: \n    root "
                                   "2000 \n    /boot 512 \n    swap 1000 \n    "
                                   "--- \n    /var 8000 \n    /var/log 2000"))
            optparser.add_option_group(group)

            optparser.disable_interspersed_args()
            (dummy, args) = optparser.parse_args(sys.argv[1:])
            optparser.enable_interspersed_args()

            hypervisor, distro = self.handle_args(optparser, args)

            self.add_settings_from_context(optparser, distro)
            self.add_settings_from_context(optparser, hypervisor)

            hypervisor.register_hook('fix_ownership', self.fix_ownership)

            config_files = ['/etc/vmbuilder.cfg',
                            os.path.expanduser('~/.vmbuilder.cfg')]
            (self.options, args) = optparser.parse_args(sys.argv[2:])

            if os.geteuid() != 0:
                raise VMBuilderUserError('Must run as root')

            distro.overwrite = hypervisor.overwrite = self.options.overwrite
            destdir = self.options.destdir or ('%s-%s' % (distro.arg,
                                                          hypervisor.arg))

            if self.options.tmpfs and self.options.chroot_dir:
                raise VMBuilderUserError('--chroot-dir and --tmpfs can not be used together.')

            if os.path.exists(destdir):
                if self.options.overwrite:
                    logging.debug('%s existed, but -o was specified. '
                                  'Nuking it.' % destdir)
                    shutil.rmtree(destdir)
                else:
                    raise VMBuilderUserError('%s already exists' % destdir)

            if self.options.config:
                config_files.append(self.options.config)
            util.apply_config_files_to_context(config_files, distro)
            util.apply_config_files_to_context(config_files, hypervisor)

            if self.options.templates:
                distro.template_dirs.insert(0, '%s/%%s'
                                                   % self.options.templates)
                hypervisor.template_dirs.insert(0, '%s/%%s'
                                                   % self.options.templates)

            for option in dir(self.options):
                if option.startswith('_') or option in ['ensure_value',
                                                        'read_module',
                                                        'read_file']:
                    continue
                val = getattr(self.options, option)
                option = option.replace('_', '-')
                if val:
                    if (distro.has_setting(option) and
                        distro.get_setting_default(option) != val):
                        distro.set_setting_fuzzy(option, val)
                    elif (hypervisor.has_setting(option) and
                          hypervisor.get_setting_default(option) != val):
                        hypervisor.set_setting_fuzzy(option, val)

            chroot_dir = None
            if self.options.existing_chroot:
                distro.set_chroot_dir(self.options.existing_chroot)
                distro.call_hooks('preflight_check')
            else:
                if self.options.tmpfs is not None:
                    if str(self.options.tmpfs) == '-':
                        tmpfs_size = 1024
                    else:
                        tmpfs_size = int(self.options.tmpfs)
                    tmpfs_mount_point = util.set_up_tmpfs(
                        tmp_root=self.options.tmp_root, size=tmpfs_size)
                    chroot_dir = tmpfs_mount_point
                elif self.options.chroot_dir:
                    os.mkdir(self.options.chroot_dir)
                    chroot_dir = self.options.chroot_dir
                else:
                    chroot_dir = util.tmpdir(tmp_root=self.options.tmp_root)
                distro.set_chroot_dir(chroot_dir)
                distro.build_chroot()

            if self.options.only_chroot:
                print 'Chroot can be found in %s' % distro.chroot_dir
                sys.exit(0)

            self.set_disk_layout(optparser, hypervisor)
            hypervisor.install_os()

            os.mkdir(destdir)
            self.fix_ownership(destdir)
            hypervisor.finalise(destdir)
            # If chroot_dir is not None, it means we created it,
            # and if we reach here, it means the user didn't pass
            # --only-chroot. Hence, we need to remove it to clean
            # up after ourselves.
            if chroot_dir is not None and tmpfs_mount_point is None:
                util.run_cmd('rm', '-rf', '--one-file-system', chroot_dir)
        except VMBuilderException, e:
            logging.error(e)
            raise
        finally:
            if tmpfs_mount_point is not None:
                util.clean_up_tmpfs(tmpfs_mount_point)
                util.run_cmd('rmdir', tmpfs_mount_point)

    def fix_ownership(self, filename):
        """
        Change ownership of file to $SUDO_USER.

        @type  path: string
        @param path: file or directory to give to $SUDO_USER
        """
        if 'SUDO_USER' in os.environ:
            logging.debug('Changing ownership of %s to %s' %
                          (filename, os.environ['SUDO_USER']))
            (uid, gid) = pwd.getpwnam(os.environ['SUDO_USER'])[2:4]
            os.chown(filename, uid, gid)

    def add_settings_from_context(self, optparser, context):
        setting_groups = set([setting.setting_group for setting
                                                in context._config.values()])
        for setting_group in setting_groups:
            optgroup = optparse.OptionGroup(optparser, setting_group.name)
            for setting in setting_group._settings:
                args = ['--%s' % setting.name]
                args += setting.extra_args
                kwargs = {}
                if setting.help:
                    kwargs['help'] = setting.help
                    if len(setting.extra_args) > 0:
                        setting.help += " Config option: %s" % setting.name
                if setting.metavar:
                    kwargs['metavar'] = setting.metavar
                if setting.get_default():
                    kwargs['default'] = setting.get_default()
                if type(setting) == VMBuilder.plugins.Plugin.BooleanSetting:
                    kwargs['action'] = 'store_true'
                if type(setting) == VMBuilder.plugins.Plugin.ListSetting:
                    kwargs['action'] = 'append'
                optgroup.add_option(*args, **kwargs)
            optparser.add_option_group(optgroup)

    def versioninfo(self, option, opt, value, parser):
        print ('%(major)d.%(minor)d.%(micro)s.r%(revno)d' %
                                                 VMBuilder.get_version_info())
        sys.exit(0)

    def set_usage(self, optparser):
        optparser.set_usage('%prog hypervisor distro [options]')
#        optparser.arg_help = (('hypervisor', vm.hypervisor_help), ('distro', vm.distro_help))

    def handle_args(self, optparser, args):
        if len(args) < 2:
            optparser.error("You need to specify at least the hypervisor type "
                            "and the distro")
        distro = VMBuilder.get_distro(args[1])()
        hypervisor = VMBuilder.get_hypervisor(args[0])(distro)
        return hypervisor, distro

    def set_verbosity(self, option, opt_str, value, parser):
        if opt_str == '--debug':
            VMBuilder.set_console_loglevel(logging.DEBUG)
        elif opt_str == '--verbose':
            VMBuilder.set_console_loglevel(logging.INFO)
        elif opt_str == '--quiet':
            VMBuilder.set_console_loglevel(logging.CRITICAL)

    def set_disk_layout(self, optparser, hypervisor):
        default_filesystem = hypervisor.distro.preferred_filesystem()
        if not self.options.part:
            rootsize = parse_size(self.options.rootsize)
            swapsize = parse_size(self.options.swapsize)
            optsize = parse_size(self.options.optsize)
            if hypervisor.preferred_storage == VMBuilder.hypervisor.STORAGE_FS_IMAGE:
                tmpfile = util.tmp_filename(tmp_root=self.options.tmp_root)
                hypervisor.add_filesystem(filename=tmpfile,
                                          size='%dM' % rootsize,
                                          type='ext3',
                                          mntpnt='/')
                if swapsize > 0:
                    tmpfile = util.tmp_filename(tmp_root=self.options.tmp_root)
                    hypervisor.add_filesystem(filename=tmpfile,
                                              size='%dM' % swapsize,
                                              type='swap',
                                              mntpnt=None)
                if optsize > 0:
                    tmpfile = util.tmp_filename(tmp_root=self.options.tmp_root)
                    hypervisor.add_filesystem(filename=tmpfile,
                                              size='%dM' % optsize,
                                              type='ext3',
                                              mntpnt='/opt')
            else:
                if self.options.raw:
                    for raw_disk in self.options.raw:
                        hypervisor.add_disk(filename=raw_disk)
                    disk = hypervisor.disks[0]
                else:
                    size = rootsize + swapsize + optsize
                    tmpfile = util.tmp_filename(tmp_root=self.options.tmp_root)
                    disk = hypervisor.add_disk(tmpfile, size='%dM' % size)
                offset = 0
                disk.add_part(offset, rootsize, default_filesystem, '/')
                offset += rootsize
                if swapsize > 0:
                    disk.add_part(offset, swapsize, 'swap', 'swap')
                    offset += swapsize
                if optsize > 0:
                    disk.add_part(offset, optsize, default_filesystem, '/opt')
        else:
            # We need to parse the file specified
            if hypervisor.preferred_storage == VMBuilder.hypervisor.STORAGE_FS_IMAGE:
                try:
                    for line in file(self.options.part):
                        elements = line.strip().split(' ')
			if len(elements) < 4:
				tmpfile = util.tmp_filename(tmp_root=self.options.tmp_root)
			else:
				tmpfile = elements[3]

                        if elements[0] == 'root':
                            hypervisor.add_filesystem(elements[1],
                                                       default_filesystem,
                                                       filename=tmpfile,
                                                       mntpnt='/')
                        elif elements[0] == 'swap':
                            hypervisor.add_filesystem(elements[1],
                                                      type='swap',
                                                      filename=tmpfile,
                                                      mntpnt=None)
                        elif elements[0] == '---':
                            # We just ignore the user's attempt to specify multiple disks
                            pass
                        elif len(elements) == 3:
                            hypervisor.add_filesystem(elements[1],
                                                      type=default_filesystem,
                                                      filename=tmpfile,
                                                      mntpnt=elements[0],
                                                      devletter='',
                                                      device=elements[2],
                                                      dummy=(int(elements[1]) == 0))
                        else:
                            hypervisor.add_filesystem(elements[1],
                                                      type=default_filesystem,
                                                      filename=tmpfile,
                                                      mntpnt=elements[0])
                except IOError, (errno, strerror):
                    optparser.error("%s parsing --part option: %s" %
                                    (errno, strerror))
            else:
                try:
                    curdisk = list()
                    size = 0
                    disk_idx = 0
                    for line in file(self.options.part):
                        pair = line.strip().split(' ',1)
                        if pair[0] == '---':
                            self.do_disk(hypervisor, curdisk, size, disk_idx)
                            curdisk = list()
                            size = 0
                            disk_idx += 1
                        elif pair[0] != '':
                            logging.debug("part: %s, size: %d" % (pair[0],
                                          int(pair[1])))
                            curdisk.append((pair[0], pair[1]))
                            size += int(pair[1])

                    self.do_disk(hypervisor, curdisk, size, disk_idx)

                except IOError, (errno, strerror):
                    optparser.error("%s parsing --part option: %s" %
                                    (errno, strerror))

    def do_disk(self, hypervisor, curdisk, size, disk_idx):
        default_filesystem = hypervisor.distro.preferred_filesystem()

        if self.options.raw:
            disk = hypervisor.add_disk(filename=self.options.raw[disk_idx])
        else:
            disk = hypervisor.add_disk(
                util.tmp_filename(tmp_root=self.options.tmp_root),
                size+1)

        logging.debug("do_disk #%i - size: %d" % (disk_idx, size))
        offset = 0
        for pair in curdisk:
            logging.debug("do_disk #%i - part: %s, size: %s, offset: %d" %
                                           (disk_idx, pair[0], pair[1], offset))
            if pair[0] == 'root':
                disk.add_part(offset, int(pair[1]), default_filesystem, '/')
            elif pair[0] == 'swap':
                disk.add_part(offset, int(pair[1]), pair[0], pair[0])
            else:
                disk.add_part(offset, int(pair[1]), default_filesystem, pair[0])
            offset += int(pair[1])

class UVB(CLI):
    arg = 'ubuntu-vm-builder'

    def set_usage(self, optparser):
        optparser.set_usage('%prog hypervisor suite [options]')
#        optparser.arg_help = (('hypervisor', vm.hypervisor_help), ('suite', self.suite_help))

    def suite_help(self):
        return ('Suite. Valid options: %s' %
                        " ".join(VMBuilder.plugins.ubuntu.distro.Ubuntu.suites))

    def handle_args(self, optparser, args):
        if len(args) < 2:
            optparser.error("You need to specify at least the hypervisor type "
                            "and the series")
        distro = VMBuilder.get_distro('ubuntu')()
        hypervisor = VMBuilder.get_hypervisor(args[0])(distro)
        distro.set_setting('suite', args[1])
        return hypervisor, distro
