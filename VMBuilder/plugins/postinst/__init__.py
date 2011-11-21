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
from VMBuilder import register_distro_plugin, Plugin, VMBuilderUserError

import logging
import os
import VMBuilder.util as util

class postinst(Plugin):
    """
    Plugin to provide --exec and --copy post install capabilities
    """
    name ='Post install plugin'

    def register_options(self):
        group = self.setting_group('Post install actions')
        group.add_setting('copy', metavar='FILE', help="Read 'source dest' lines from FILE, copying source files from host to dest in the guest's file system.")
        group.add_setting('execscript', extra_args=['--exec'], metavar='SCRIPT', help="Run SCRIPT after distro installation finishes. Script will be called with the guest's chroot as first argument, so you can use 'chroot $1 <cmd>' to run code in the virtual machine.")

    def preflight_check(self):
        copy = self.context.get_setting('copy')
        if copy:
            logging.debug("Checking if copy PATH exists: %s" % copy)
            if not(os.path.isfile(copy)):
                raise VMBuilderUserError('The path to the copy directive is invalid: %s. Make sure you are providing a full path.' % copy)
                
        execscript = self.context.get_setting('execscript')
        if execscript:
            logging.debug("Checking if exec PATH exists: %s" % execscript)
            if not(os.path.isfile(execscript)):
                raise VMBuilderUserError('The path to the execscript file is invalid: %s. Make sure you are providing a full path.' % execscript) 

            logging.debug("Checking permissions of exec PATH: %s" % execscript)
            if not os.access(execscript, os.X_OK|os.R_OK):
                raise VMBuilderUserError('The path to the execscript file has invalid permissions: %s. Make sure the path is readable and executable.' % execscript)

    def post_install(self):
        copy = self.context.get_setting('copy')
        execscript = self.context.get_setting('execscript')
        if copy:
            logging.info("Copying files specified by copy in: %s" % copy)
            try:
                for line in file(copy):
                    pair = line.strip().split(' ')
                    if len(pair) < 2: # skip blank and incomplete lines
                        continue
                    directory = '%s%s' % (self.context.chroot_dir, os.path.dirname(pair[1]))
                    if not os.path.exists(directory):
                        os.makedirs(directory)
                    util.run_cmd('cp', '-LpR', pair[0], '%s%s' % (self.context.chroot_dir, pair[1]))

            except IOError, (errno, strerror):
                raise VMBuilderUserError("%s executing copy directives: %s" % (errno, strerror))

        if execscript:
            logging.info("Executing script: %s" % execscript)
            util.run_cmd(execscript, self.context.chroot_dir)

        return True

register_distro_plugin(postinst)
