#
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
#    The VM class
import ConfigParser
from   gettext             import gettext
import logging
import os
import optparse
import textwrap
import urllib
import VMBuilder
import VMBuilder.util      as util
import VMBuilder.log       as log
import VMBuilder.disk      as disk
from   VMBuilder.disk      import Disk, Filesystem
from   VMBuilder.exception import VMBuilderException, VMBuilderUserError
_ = gettext

class VM(object):
    """The VM object has the following attributes of relevance to plugins:

    distro: A distro object, representing the distro running in the vm

    disks: The disk images for the vm.
    filesystems: The filesystem images for the vm.

    result_files: A list of the files that make up the entire vm.
                  The ownership of these files will be fixed up.

    optparser: Will be of interest mostly to frontends. Any sort of option
               a plugin accepts will be represented in the optparser.
    

    """
    def __init__(self, conf=None):
        self.hypervisor = None #: hypervisor object, representing the hypervisor the vm is destined for
        self.distro = None

        self.disks = []
        self.filesystems = []

        self.result_files = []
        self.plugins  = []
        self._cleanup_cbs = []

        #: final destination for the disk images
        self.destdir = None
        #: tempdir where we do all the work
        self.workdir = None
        #: mount point where the disk images will be mounted
        self.rootmnt = None
        #: directory where we build up the guest filesystem
        self.tmproot = None

        self.fsmounted = False

        self.optparser = _MyOptParser(epilog="ubuntu-vm-builder is Copyright (C) 2007-2009 Canonical Ltd. and written by Soren Hansen <soren@linux2go.dk>.", usage='%prog hypervisor distro [options]')
        self.optparser.arg_help = (('hypervisor', self.hypervisor_help), ('distro', self.distro_help))

        self.confparser = ConfigParser.SafeConfigParser()

        if conf:
            if not(os.path.isfile(conf)):
                raise VMBuilderUserError('The path to the configuration file is not valid: %s.' % conf)
        else:
            conf = ''

        self.confparser.read(['/etc/vmbuilder.cfg', os.path.expanduser('~/.vmbuilder.cfg'), conf])

        self._register_base_settings()

        self.add_clean_cmd('rm', log.logfile)

    def distro_help(self):
        return 'Distro. Valid options: %s' % " ".join(VMBuilder.distros.keys())

    def hypervisor_help(self):
        return 'Hypervisor. Valid options: %s' % " ".join(VMBuilder.hypervisors.keys())

    def register_setting(self, *args, **kwargs):
        return self.optparser.add_option(*args, **kwargs)

    def register_setting_group(self, group):
        return self.optparser.add_option_group(group)

    def setting_group(self, *args, **kwargs):
        return optparse.OptionGroup(self.optparser, *args, **kwargs)

    def _register_base_settings(self):
        self.register_setting('-d', '--dest', dest='destdir', help='Specify the destination directory. [default: <hypervisor>-<distro>].')
        self.register_setting('-c', '--config',  type='string', help='Specify a additional configuration file')
        self.register_setting('--debug', action='callback', callback=log.set_verbosity, help='Show debug information')
        self.register_setting('-v', '--verbose', action='callback', callback=log.set_verbosity, help='Show progress information')
        self.register_setting('-q', '--quiet', action='callback', callback=log.set_verbosity, help='Silent operation')
        self.register_setting('-t', '--tmp', default=os.environ.get('TMPDIR', '/tmp'), help='Use TMP as temporary working space for image generation. Defaults to $TMPDIR if it is defined or /tmp otherwise. [default: %default]')
        self.register_setting('--templates', metavar='DIR', help='Prepend DIR to template search path.')
        self.register_setting('-o', '--overwrite', action='store_true', default=False, help='Force overwrite of destination directory if it already exist. [default: %default]')
        self.register_setting('--in-place', action='store_true', default=False, help='Install directly into the filesystem images. This is needed if your $TMPDIR is nodev and/or nosuid, but will result in slightly larger file system images.')
        self.register_setting('--tmpfs', metavar="OPTS", help='Use a tmpfs as the working directory, specifying its size or "-" to use tmpfs default (suid,dev,size=1G).')
        self.register_setting('-m', '--mem', type='int', default=128, help='Assign MEM megabytes of memory to the guest vm. [default: %default]')

    def add_disk(self, *args, **kwargs):
        """Adds a disk image to the virtual machine"""
        disk = Disk(self, *args, **kwargs)
        self.disks.append(disk)
        return disk

    def add_filesystem(self, *args, **kwargs):
        """Adds a filesystem to the virtual machine"""
        fs = Filesystem(self, *args, **kwargs)
        self.filesystems.append(fs)
        return fs

    def call_hooks(self, func):
        for plugin in self.plugins:
            getattr(plugin, func)()
        getattr(self.hypervisor, func)()
        getattr(self.distro, func)()

    def preflight_check(self):
        for opt in sum([self.confparser.options(section) for section in self.confparser.sections()], []) + [k for (k,v) in self.confparser.defaults().iteritems()]:
            if '-' in opt:
                raise VMBuilderUserError('You specified a "%s" config option in a config file, but that is not valid. Perhaps you meant "%s"?' % (opt, opt.replace('-', '_')))

        self.call_hooks('preflight_check')

        # Check repository availability
        if self.mirror:
            testurl = self.mirror
        else:
            testurl = 'http://archive.ubuntu.com/'

        try:
            logging.debug('Testing access to %s' % testurl)
            testnet = urllib.urlopen(testurl)
        except IOError:
            raise VMBuilderUserError('Could not connect to %s. Please check your connectivity and try again.' % testurl)

        testnet.close()

    def create(self):
        """
        The core vm creation method
        
        The VM creation happens in the following steps:

        A series of preliminary checks are performed:
         - We check if we're being run as root, since 
           the filesystem handling requires root priv's
         - Each plugin's preflight_check method is called.
           See L{VMBuilder.plugins.Plugin} documentation for details
         - L{create_directory_structure} is called
         - VMBuilder.disk.create_partitions is called
         - VMBuilder.disk.create_filesystems is called
         - .mount_partitions is called
         - .install is called

        """
        util.checkroot()

        finished = False
        try:
            self.preflight_check()
            self.create_directory_structure()

            disk.create_partitions(self)
            disk.create_filesystems(self)
            self.mount_partitions()

            self.install()

            self.umount_partitions()

            self.hypervisor.finalize()

            self.deploy()

            util.fix_ownership(self.result_files)

            finished = True
        except VMBuilderException:
            raise
        finally:
            if not finished:
                logging.debug("Oh, dear, an exception occurred")
            self.cleanup()

        if not finished:
            return(1)
        return(0)

class _MyOptParser(optparse.OptionParser):
    def format_arg_help(self, formatter):
        result = []
        for arg in self.arg_help:
            result.append(self.format_arg(formatter, arg))
        return "".join(result)

    def format_arg(self, formatter, arg):
        result = []
        arghelp = arg[1]()
        arg = arg[0]
        width = formatter.help_position - formatter.current_indent - 2
        if len(arg) > width:
            arg = "%*s%s\n" % (self.current_indent, "", arg)
            indent_first = formatter.help_position
        else:                       # start help on same line as opts
            arg = "%*s%-*s  " % (formatter.current_indent, "", width, arg)
            indent_first = 0
        result.append(arg)
        help_lines = textwrap.wrap(arghelp, formatter.help_width)
        result.append("%*s%s\n" % (indent_first, "", help_lines[0]))
        result.extend(["%*s%s\n" % (formatter.help_position, "", line)
                           for line in help_lines[1:]])
        return "".join(result)

    def format_option_help(self, formatter=None):
        if formatter is None:
            formatter = self.formatter
        formatter.store_option_strings(self)
        result = []
        if self.arg_help:
            result.append(formatter.format_heading(_("Arguments")))
            formatter.indent()
            result.append(self.format_arg_help(formatter))
            result.append("\n")
            result.append("*** Use vmbuilder <hypervisor> <distro> --help to get more options. Hypervisor, distro, and plugins specific help is only available when the first two arguments are supplied.\n")
            result.append("\n")
            formatter.dedent()
        result.append(formatter.format_heading(_("Options")))
        formatter.indent()
        if self.option_list:
            result.append(optparse.OptionContainer.format_option_help(self, formatter))
            result.append("\n")
        for group in self.option_groups:
            result.append(group.format_help(formatter))
            result.append("\n")
        formatter.dedent()
        # Drop the last "\n", or the header if no options or option groups:
        return "".join(result[:-1])

