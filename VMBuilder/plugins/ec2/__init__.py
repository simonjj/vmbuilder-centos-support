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
import VMBuilder
from   VMBuilder import register_distro_plugin, register_hypervisor_plugin, Plugin, VMBuilderUserError, VMBuilderException
from   VMBuilder.util import run_cmd
import logging
import os

class EC2(Plugin):
    name = 'EC2 integration'

    def register_options(self):
        # Don't pretend like we can do EC2 
        if not isinstance(self.context.hypervisor, VMBuilder.plugins.xen.Xen):
            return
        group = self.context.setting_group('EC2 integation')
        group.add_option('--ec2', action='store_true', help='Build for EC2')
        group.add_option('--ec2-name','--ec2-prefix', metavar='EC2_NAME', help='Name for the EC2 image.')
        group.add_option('--ec2-cert', metavar='CERTFILE', help='PEM encoded public certificate for EC2.')
        group.add_option('--ec2-key', metavar='KEYFILE', help='PEM encoded private key for EC2.')
        group.add_option('--ec2-user', metavar='AWS_ACCOUNT', help='EC2 user ID (a.k.a. AWS account number, not AWS access key ID).')
        group.add_option('--ec2-bucket', metavar='BUCKET', help='S3 bucket to hold the AMI.')
        group.add_option('--ec2-access-key', metavar='ACCESS_ID', help='AWS access key ID.')
        group.add_option('--ec2-secret-key', metavar='SECRET_ID', help='AWS secret access key.')
        group.add_option('--ec2-kernel','--ec2-aki', metavar='AKI', help='EC2 AKI (kernel) to use.')
        group.add_option('--ec2-ramdisk','--ec2-ari', metavar='ARI', help='EC2 ARI (ramdisk) to use.')
        group.add_option('--ec2-version', metavar='EC2_VER', help='Specify the EC2 image version.')
        group.add_option('--ec2-landscape', action='store_true', help='Install landscape client support')
        group.add_option('--ec2-bundle', action='store_true', help='Bundle the instance')
        group.add_option('--ec2-upload', action='store_true', help='Upload the instance')
        group.add_option('--ec2-register', action='store_true', help='Register the instance')
        self.context.register_setting_group(group)

    def preflight_check(self):
        if not getattr(self.vm, 'ec2', False):
            return True

        if not self.context.hypervisor.name == 'Xen':
            raise VMBuilderUserError('When building for EC2 you must use the xen hypervisor.')

        if self.context.ec2_bundle:
            try:
                run_cmd('ec2-ami-tools-version')
            except VMBuilderException, e:
                raise VMBuilderUserError('You need to have the Amazon EC2 AMI tools installed')

            if not self.context.ec2_name:
                raise VMBuilderUserError('When building for EC2 you must supply the name for the image.')

            if not self.context.ec2_cert:
                if "EC2_CERT" in os.environ:
                    self.context.ec2_cert = os.environ["EC2_CERT"]
                else:
                    raise VMBuilderUserError('When building for EC2 you must provide your PEM encoded public key certificate')

            if not self.context.ec2_key:
                if "EC2_PRIVATE_KEY" in os.environ:
                    self.context.ec2_key = os.environ["EC2_PRIVATE_KEY"]
                else:
                    raise VMBuilderUserError('When building for EC2 you must provide your PEM encoded private key file')

            if not self.context.ec2_user:
                raise VMBuilderUserError('When building for EC2 you must provide your EC2 user ID (your AWS account number, not your AWS access key ID)')

            if not self.context.ec2_kernel:
                self.context.ec2_kernel = self.vm.distro.get_ec2_kernel()
                logging.debug('%s - to be used for AKI.' %(self.context.ec2_kernel))

            if not self.context.ec2_ramdisk:
                self.context.ec2_ramdisk = self.vm.distro.ec2_ramdisk_id()
                logging.debug('%s - to be use for the ARI.' %(self.context.ec2_ramdisk))

            if self.context.ec2_upload:
                if not self.context.ec2_bucket:
                    raise VMBuilderUserError('When building for EC2 you must provide an S3 bucket to hold the AMI')

                if not self.context.ec2_access_key:
                    raise VMBuilderUserError('When building for EC2 you must provide your AWS access key ID.')

                if not self.context.ec2_secret_key:
                    raise VMBuilderUserError('When building for EC2 you must provide your AWS secret access key.')

        if not self.context.ec2_version:
            raise VMBuilderUserError('When building for EC2 you must provide version info.')

        if not self.context.addpkg:
             self.context.addpkg = []

        if self.context.ec2_landscape:
            logging.info('Installing landscape support')
            self.context.addpkg += ['landscape-client']

    def post_install(self):
        if not getattr(self.vm, 'ec2', False):
            return

        logging.info("Running ec2 postinstall")
        self.install_from_template('/etc/ec2_version', 'ec2_version', { 'version' : self.context.ec2_version } )
        self.install_from_template('/etc/ssh/sshd_config', 'sshd_config')
        self.install_from_template('/etc/sudoers', 'sudoers')

        if self.context.ec2_landscape:
            self.install_from_template('/etc/default/landscape-client', 'landscape_client')

        self.context.distro.disable_hwclock_access()

    def deploy(self):
        if not getattr(self.vm, 'ec2', False):
            return False

        if self.context.ec2_bundle:
            logging.info("Building EC2 bundle")
            bundle_cmdline = ['ec2-bundle-image', '--image', self.context.filesystems[0].filename, '--cert', self.vm.ec2_cert, '--privatekey', self.vm.ec2_key, '--user', self.vm.ec2_user, '--prefix', self.vm.ec2_name, '-r', ['i386', 'x86_64'][self.vm.arch == 'amd64'], '-d', self.vm.workdir, '--kernel', self.vm.ec2_kernel, '--ramdisk', self.vm.ec2_ramdisk]
            run_cmd(*bundle_cmdline)

            manifest = '%s/%s.manifest.xml' % (self.context.workdir, self.vm.ec2_name)
            if self.context.ec2_upload:
                logging.info("Uploading EC2 bundle")
                upload_cmdline = ['ec2-upload-bundle', '--retry', '--manifest', manifest, '--bucket', self.context.ec2_bucket, '--access-key', self.vm.ec2_access_key, '--secret-key', self.vm.ec2_secret_key]
                run_cmd(*upload_cmdline)

                if self.context.ec2_register:
                    from boto.ec2.connection import EC2Connection
                    conn = EC2Connection(self.context.ec2_access_key, self.vm.ec2_secret_key)
                    amiid = conn.register_image('%s/%s.manifest.xml' % (self.context.ec2_bucket, self.vm.ec2_name))
                    print 'Image registered as %s' % amiid
            else:
                self.context.result_files.append(manifest)
        else:
            self.context.result_files.append(self.vm.filesystems[0].filename)

        return True

#register_plugin(EC2)
