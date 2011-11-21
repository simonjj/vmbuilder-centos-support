#
#    Uncomplicated VM Builder
#    Copyright (C) 2007-2010 Canonical Ltd.
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

class Firstscripts(Plugin):
    """
    Plugin to provide --firstboot and --firstlogin scripts capabilities
    """
    name = 'First-Scripts plugin'

    def register_options(self):
        group = self.setting_group('Scripts')
        group.add_setting('firstboot', metavar='PATH', help='Specify a script that will be copied into the guest and executed the first time the machine boots.  This script must not be interactive.')
        group.add_setting('firstlogin', metavar='PATH', help='Specify a script that will be copied into the guest and will be executed the first time the user logs in. This script can be interactive.')

    def preflight_check(self):
        firstboot = self.context.get_setting('firstboot')
        if firstboot:
            logging.debug("Checking if firstboot script %s exists" % (firstboot,))
            if not(os.path.isfile(firstboot) and firstboot.startswith('/')):
                raise VMBuilderUserError('The path to the first-boot script is invalid: %s. Make sure you are providing a full path.' % firstboot)

        firstlogin = self.context.get_setting('firstlogin')
        if firstlogin:
            logging.debug("Checking if first login script %s exists" % (firstlogin,))
            if not(os.path.isfile(firstlogin) and firstlogin.startswith('/')):
                raise VMBuilderUserError('The path to the first-login script is invalid: %s.  Make sure you are providing a full path.' % firstlogin)

    def post_install(self):
        firstboot = self.context.get_setting('firstboot')
        if firstboot:
            logging.debug("Installing firstboot script %s" % (firstboot,))
            self.context.install_file('/root/firstboot.sh', source=firstboot, mode=0700)
            os.rename('%s/etc/rc.local' % self.context.chroot_dir, '%s/etc/rc.local.orig' % self.context.chroot_dir)
            self.install_from_template('/etc/rc.local', 'firstbootrc', mode=0755)

        firstlogin = self.context.get_setting('firstlogin')
        if firstlogin:
            logging.debug("Installing first login script %s" % (firstlogin,))
            self.context.install_file('/root/firstlogin.sh', source=firstlogin, mode=0755)
            os.rename('%s/etc/bash.bashrc' % self.context.chroot_dir, '%s/etc/bash.bashrc.orig' % self.context.chroot_dir)
            self.install_from_template('/etc/bash.bashrc', 'firstloginrc')

        return True

register_distro_plugin(Firstscripts)
