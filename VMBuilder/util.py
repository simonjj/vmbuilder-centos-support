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
#    Various utility functions
import ConfigParser
import errno
import fcntl
import logging
import os.path
import select
import subprocess
import tempfile
from   exception        import VMBuilderException, VMBuilderUserError

class NonBlockingFile(object):
    def __init__(self, fp, logfunc):
        self.file = fp
        self.set_non_blocking()
        self.buf = ''
        self.logbuf = ''
        self.logfunc = logfunc

    def set_non_blocking(self):
        flags = fcntl.fcntl(self.file, fcntl.F_GETFL)
        flags = flags | os.O_NONBLOCK
        fcntl.fcntl(self.file, fcntl.F_SETFL, flags)

    def __getattr__(self, attr):
        if attr == 'closed':
            return self.file.closed
        else:
            raise AttributeError()

    def process_input(self):
        data = self.file.read()
        if data == '':
            self.file.close()
            if self.logbuf:
                self.logfunc(self.logbuf)
        else:
            self.buf += data
            self.logbuf += data
            while '\n' in self.logbuf:
                line, self.logbuf = self.logbuf.split('\n', 1)
                self.logfunc(line)

def run_cmd(*argv, **kwargs):
    """
    Runs a command.

    Locale is reset to C to make parsing error messages possible.

    @type  stdin: string
    @param stdin: input to provide to the process on stdin. If None, process'
                  stdin will be attached to /dev/null
    @type  ignore_fail: boolean
    @param ignore_fail: If True, a non-zero exit code from the command will not 
                        cause an exception to be raised.
    @type  env: dict
    @param env: Dictionary of extra environment variables to set in the new process

    @rtype:  string
    @return: string containing the stdout of the process
    """

    env = kwargs.get('env', {})
    print argv
    print kwargs
    stdin = kwargs.get('stdin', None)
    ignore_fail = kwargs.get('ignore_fail', False)
    args = [str(arg) for arg in argv]
    logging.debug(args.__repr__())
    if stdin:
        logging.debug('stdin was set and it was a string: %s' % (stdin,))
        stdin_arg = subprocess.PIPE
    else:
        stdin_arg = file('/dev/null', 'r')
    proc_env = dict(os.environ)
    proc_env['LANG'] = 'C'
    proc_env['LC_ALL'] = 'C'
    proc_env.update(env)

    try:
        proc = subprocess.Popen(args, stdin=stdin_arg, stderr=subprocess.PIPE, stdout=subprocess.PIPE, env=proc_env)
    except OSError, error:
        if error.errno == errno.ENOENT:
            raise VMBuilderUserError, "Couldn't find the program '%s' on your system" % (argv[0])
        else:
            raise VMBuilderUserError, "Couldn't launch the program '%s': %s" % (argv[0], error)

    if stdin:
        proc.stdin.write(stdin)
        proc.stdin.close()

    mystdout = NonBlockingFile(proc.stdout, logfunc=logging.debug)
    mystderr = NonBlockingFile(proc.stderr, logfunc=(ignore_fail and logging.debug or logging.info))

    while not (mystdout.closed and mystderr.closed):
        # Block until either of them has something to offer
        fds = select.select([x.file for x in [mystdout, mystderr] if not x.closed], [], [])[0]
        for fp in [mystderr, mystdout]:
            if fp.file in fds:
                fp.process_input()

    status = proc.wait()
    if not ignore_fail and status != 0:
        raise VMBuilderException, "Process (%s) returned %d. stdout: %s, stderr: %s" % (args.__repr__(), status, mystdout.buf, mystderr.buf)
    return mystdout.buf

def checkroot():
    """
    Check if we're running as root, and bail out if we're not.
    """

    if os.geteuid() != 0:
        raise VMBuilderUserError("This script must be run as root (e.g. via sudo)")

def render_template(plugin, context, tmplname, extra_context=None):
    # Import here to avoid having to build-dep on python-cheetah
    from   Cheetah.Template import Template
    searchList = []
    if context:
        searchList.append(extra_context)
    searchList.append(context)

#        tmpldirs.insert(0,'%s/%%s' % vm.templates)
    
    tmpldirs = [dir % plugin for dir in context.template_dirs]

    for dir in tmpldirs:
        tmplfile = '%s/%s.tmpl' % (dir, tmplname)
        if os.path.exists(tmplfile):
            t = Template(file=tmplfile, searchList=searchList)
            output = t.respond()
            logging.debug('Output from template \'%s\': %s' % (tmplfile, output))
            return output

    raise VMBuilderException('Template %s.tmpl not found in any of %s' % (tmplname, ', '.join(tmpldirs)))

def call_hooks(context, func, *args, **kwargs):
    logging.info('Calling hook: %s' % func)
    logging.debug('(args=%r, kwargs=%r)' % (args, kwargs))
    for plugin in context.plugins:
        logging.debug('Calling %s method in %s plugin.' % (func, plugin.__module__))
        getattr(plugin, func, log_no_such_method)(*args, **kwargs)

    for f in context.hooks.get(func, []):
        logging.debug('Calling %r.' % (f,))
        f(*args, **kwargs)

    logging.debug('Calling %s method in context plugin %s.' % (func, context.__module__))
    getattr(context, func, log_no_such_method)(*args, **kwargs)

def log_no_such_method(*args, **kwargs):
    logging.debug('No such method')
    return

def tmp_filename(suffix='', tmp_root=None):
    # There is a risk in using tempfile.mktemp(): it's not recommended
    # to run vmbuilder on machines with untrusted users.
    return tempfile.mktemp(suffix=suffix, dir=tmp_root)

def tmpdir(suffix='', tmp_root=None):
    return tempfile.mkdtemp(suffix=suffix, dir=tmp_root)

def set_up_tmpfs(tmp_root=None, size=1024):
    """Sets up a tmpfs storage under `tmp_root` with the size of `size` MB.

    `tmp_root` defaults to tempfile.gettempdir().
    """
    mount_point = tmpdir('tmpfs', tmp_root)
    mount_cmd = ["mount", "-t", "tmpfs",
                 "-o", "size=%dM,mode=0770" % int(size),
                 "tmpfs", mount_point ]
    logging.info('Mounting tmpfs under %s' % mount_point)
    logging.debug('Executing: %s' % mount_cmd)
    run_cmd(*mount_cmd)

    return mount_point

def clean_up_tmpfs(mount_point):
    """Unmounts a tmpfs storage under `mount_point`."""
    umount_cmd = ["umount", "-t", "tmpfs", mount_point ]
    logging.info('Unmounting tmpfs from %s' % mount_point)
    logging.debug('Executing: %s' % umount_cmd)
    run_cmd(*umount_cmd)


def get_conf_value(context, confparser, key):
    confvalue = None
    try:
        confvalue = confparser.get('DEFAULT', key)
    except ConfigParser.NoSectionError:
        pass
    except ConfigParser.NoOptionError:
        pass

    if confparser.has_option(context.arg, key):
        confvalue = confparser.get(context.arg, key)

    logging.debug('Returning value %s for configuration key %s' % (repr(confvalue), key))
    return confvalue

def apply_config_files_to_context(config_files, context):
    confparser = ConfigParser.SafeConfigParser()
    confparser.read(config_files)

    for (key, setting) in context._config.iteritems():
        confvalue = get_conf_value(context, confparser, key)
        if confvalue:
            setting.set_value_fuzzy(confvalue)
