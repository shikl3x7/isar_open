#!/usr/bin/env python3

import logging
import os
import re
import select
import shutil
import subprocess
import time
import tempfile

import start_vm

from avocado import Test
from avocado.utils import path
from avocado.utils import process

DEF_VM_TO_SEC = 600

isar_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
backup_prefix = '.ci-backup'

app_log = logging.getLogger("avocado.app")

class CanBeFinished(Exception):
    pass

class CIBuilder(Test):
    def setUp(self):
        super(CIBuilder, self).setUp()
        job_log = os.path.join(os.path.dirname(self.logdir), '..', 'job.log')
        self._file_handler = logging.FileHandler(filename=job_log)
        self._file_handler.setLevel(logging.ERROR)
        fmt = ('%(asctime)s %(module)-16.16s L%(lineno)-.4d %('
               'levelname)-5.5s| %(message)s')
        formatter = logging.Formatter(fmt=fmt)
        self._file_handler.setFormatter(formatter)
        app_log.addHandler(self._file_handler)

    def init(self, build_dir='build'):
        # initialize build_dir and setup environment
        # needs to run once (per test case)
        if hasattr(self, 'build_dir'):
            self.error("Broken test implementation: init() called multiple times.")
        self.build_dir = os.path.join(isar_root, build_dir)
        os.chdir(isar_root)
        path.usable_rw_dir(self.build_dir)
        output = process.getoutput('/bin/bash -c "source isar-init-build-env \
                                    %s 2>&1 >/dev/null; env"' % self.build_dir)
        env = dict(((x.split('=', 1) + [''])[:2] \
                    for x in output.splitlines() if x != ''))
        os.environ.update(env)

    def check_init(self):
        if not hasattr(self, 'build_dir'):
            self.error("Broken test implementation: need to call init().")

    def configure(self, compat_arch=True, cross=True, debsrc_cache=False,
                  container=False, ccache=False, sstate=False, offline=False,
                  gpg_pub_key=None, wic_deploy_parts=False, dl_dir=None,
                  sstate_dir=None, ccache_dir=None,
                  source_date_epoch=None, image_install=None, **kwargs):
        # write configuration file and set bitbake_args
        # can run multiple times per test case
        self.check_init()

        # get parameters from avocado cmdline
        quiet = bool(int(self.params.get('quiet', default=1)))

        # set those to "" to not set dir value but use system default
        if dl_dir is None:
            dl_dir = os.path.join(isar_root, 'downloads')
        if sstate_dir is None:
            sstate_dir = os.path.join(isar_root, 'sstate-cache')
        if ccache_dir is None:
            ccache_dir = '${TOPDIR}/ccache'

        # get parameters from environment
        distro_apt_premir = os.getenv('DISTRO_APT_PREMIRRORS')

        self.log.info(f'===================================================\n'
                      f'Configuring build_dir {self.build_dir}\n'
                      f'  compat_arch = {compat_arch}\n'
                      f'  cross = {cross}\n'
                      f'  debsrc_cache = {debsrc_cache}\n'
                      f'  offline = {offline}\n'
                      f'  container = {container}\n'
                      f'  ccache = {ccache}\n'
                      f'  sstate = {sstate}\n'
                      f'  gpg_pub_key = {gpg_pub_key}\n'
                      f'  wic_deploy_parts = {wic_deploy_parts}\n'
                      f'  source_date_epoch = {source_date_epoch} \n'
                      f'  dl_dir = {dl_dir}\n'
                      f'  sstate_dir = {sstate_dir}\n'
                      f'  ccache_dir = {ccache_dir}\n'
                      f'  image_install = {image_install}\n'
                      f'===================================================')

        # determine bitbake_args
        self.bitbake_args = []
        if not quiet:
            self.bitbake_args.append('-v')
        if not sstate:
            self.bitbake_args.append('--no-setscene')

        # write ci_build.conf
        with open(self.build_dir + '/conf/ci_build.conf', 'w') as f:
            if compat_arch:
                f.write('ISAR_ENABLE_COMPAT_ARCH:amd64 = "1"\n')
                f.write('IMAGE_INSTALL:remove:amd64 = "hello-isar"\n')
                f.write('IMAGE_INSTALL:append:amd64 = " hello-isar-compat"\n')
                f.write('ISAR_ENABLE_COMPAT_ARCH:arm64 = "1"\n')
                f.write('IMAGE_INSTALL:remove:arm64 = "hello-isar"\n')
                f.write('IMAGE_INSTALL:append:arm64 = " hello-isar-compat"\n')
                f.write('IMAGE_INSTALL += "kselftest"\n')
            if cross:
                f.write('ISAR_CROSS_COMPILE = "1"\n')
            if debsrc_cache:
                f.write('BASE_REPO_FEATURES = "cache-deb-src"\n')
            if offline:
                f.write('ISAR_USE_CACHED_BASE_REPO = "1"\n')
                f.write('BB_NO_NETWORK = "1"\n')
            if container:
                f.write('SDK_FORMATS = "docker-archive"\n')
                f.write('IMAGE_INSTALL:remove = "example-module-${KERNEL_NAME} enable-fsck"\n')
            if gpg_pub_key:
                f.write('BASE_REPO_KEY="file://' + gpg_pub_key + '"\n')
            if wic_deploy_parts:
                f.write('WIC_DEPLOY_PARTITIONS = "1"\n')
            if distro_apt_premir:
                f.write('DISTRO_APT_PREMIRRORS = "%s"\n' % distro_apt_premir)
            if ccache:
                f.write('USE_CCACHE = "1"\n')
                f.write('CCACHE_TOP_DIR = "%s"\n' % ccache_dir)
            if source_date_epoch:
                f.write('SOURCE_DATE_EPOCH = "%s"\n' % source_date_epoch)
            if dl_dir:
                f.write('DL_DIR = "%s"\n' % dl_dir)
            if sstate_dir:
                f.write('SSTATE_DIR = "%s"\n' % sstate_dir)
            if image_install is not None:
                f.write('IMAGE_INSTALL = "%s"' % image_install)

        # include ci_build.conf in local.conf
        with open(self.build_dir + '/conf/local.conf', 'r+') as f:
            for line in f:
                if 'include ci_build.conf' in line:
                    break
            else:
                f.write('\ninclude ci_build.conf')

    def unconfigure(self):
        self.check_init()
        open(self.build_dir + '/conf/ci_build.conf', 'w').close()

    def delete_from_build_dir(self, path):
        self.check_init()
        process.run('rm -rf ' + self.build_dir + '/' + path, sudo=True)

    def move_in_build_dir(self, src, dst):
        self.check_init()
        process.run('mv ' + self.build_dir + '/' + src + ' ' + self.build_dir + '/' + dst, sudo=True)

    def bitbake(self, target, bitbake_cmd=None, **kwargs):
        self.check_init()
        self.log.info('===================================================')
        self.log.info('Building ' + str(target))
        self.log.info('===================================================')
        os.chdir(self.build_dir)
        cmdline = ['bitbake']
        if self.bitbake_args:
            cmdline.extend(self.bitbake_args)
        if bitbake_cmd:
            cmdline.append('-c')
            cmdline.append(bitbake_cmd)
        if isinstance(target, list):
            cmdline.extend(target)
        else:
            cmdline.append(target)

        with subprocess.Popen(" ".join(cmdline), stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, universal_newlines=True,
                              shell=True) as p1:
            poller = select.poll()
            poller.register(p1.stdout, select.POLLIN)
            poller.register(p1.stderr, select.POLLIN)
            while p1.poll() is None:
                events = poller.poll(1000)
                for fd, event in events:
                    if event != select.POLLIN:
                        continue
                    if fd == p1.stdout.fileno():
                        self.log.info(p1.stdout.readline().rstrip())
                    if fd == p1.stderr.fileno():
                        app_log.error(p1.stderr.readline().rstrip())
            p1.wait()
            if p1.returncode:
                self.fail('Bitbake failed')

    def backupfile(self, path):
        self.check_init()
        try:
            shutil.copy2(path, path + backup_prefix)
        except FileNotFoundError:
            self.log.warn(path + ' not exist')

    def backupmove(self, path):
        self.check_init()
        try:
            shutil.move(path, path + backup_prefix)
        except FileNotFoundError:
            self.log.warn(path + ' not exist')

    def restorefile(self, path):
        self.check_init()
        try:
            shutil.move(path + backup_prefix, path)
        except FileNotFoundError:
            self.log.warn(path + backup_prefix + ' not exist')

    def getlayerdir(self, layer):
        self.check_init()
        output = process.getoutput('bitbake -e | grep "^LAYERDIR_.*="')
        env = dict(((x.split('=', 1) + [''])[:2] \
                    for x in output.splitlines() if x != ''))

        return env['LAYERDIR_' + layer].strip('"')

    def get_ssh_cmd_prefix(self, port, priv_key):
        port_args = ''
        if port:
            port_args = ' -p ' + str(port)

        cmd_prefix = 'ssh' + port_args + \
                     ' -o ConnectTimeout=5 -o IdentityFile=' + priv_key + \
                     ' -o StrictHostKeyChecking=no ci@localhost '

        return cmd_prefix


    def exec_cmd(self, cmd, cmd_prefix):
        rc = subprocess.call('exec ' + str(cmd_prefix) + ' "' + str(cmd) + '"', shell=True,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return rc


    def run_script(self, script, cmd_prefix):
        script_dir = self.params.get('test_script_dir',
                                     default=os.path.abspath(os.path.dirname(__file__))) + '/'
        script_path = script_dir + script
        rc = subprocess.call('cat ' + script_path + ' | ' + str(cmd_prefix), shell=True,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return rc


    def wait_connection(self, proc, cmd_prefix, timeout):
        self.log.debug('Waiting for SSH server ready...')

        rc = None
        goodcnt = 0
        while time.time() < timeout:
            if proc.poll() is not None:
                self.log.error('Machine is not running')
                return rc

            rc = self.exec_cmd('/bin/true', cmd_prefix)
            time_left = timeout - time.time()
            self.log.debug('SSH ping result: %d, left: %.fs' % (rc, time_left))
            time.sleep(1)

            if rc == 0:
                goodcnt += 1
                # Let 3 good SSH pings to make sure SSH connection is stable
                if goodcnt >= 3:
                    self.log.debug('SSH server is ready')
                    break
            else:
                goodcnt = 0

        if rc != 0:
            self.log.error('SSH server is not ready')

        return rc


    def vm_start(self, arch='amd64', distro='buster',
                 enforce_pcbios=False, skip_modulecheck=False,
                 image='isar-image-base', cmd=None, script=None):
        time_to_wait = self.params.get('time_to_wait', default=DEF_VM_TO_SEC)

        self.log.info('===================================================')
        self.log.info('Running Isar VM boot test for (' + distro + '-' + arch + ')')
        self.log.info('Remote command is ' + str(cmd))
        self.log.info('Remote script is ' + str(script))
        self.log.info('Isar build folder is: ' + self.build_dir)
        self.log.info('===================================================')

        self.check_init()

        logdir = '%s/vm_start' % self.build_dir
        if not os.path.exists(logdir):
            os.mkdir(logdir)
        prefix = '%s-vm_start_%s_%s_' % (time.strftime('%Y%m%d-%H%M%S'),
                                         distro, arch)
        fd, output_file = tempfile.mkstemp(suffix='_log.txt', prefix=prefix,
                                           dir=logdir, text=True)
        os.chmod(output_file, 0o644)
        latest_link = '%s/vm_start_%s_%s_latest.txt' % (logdir, distro, arch)
        if os.path.exists(latest_link):
            os.unlink(latest_link)
        os.symlink(os.path.basename(output_file), latest_link)

        cmdline = start_vm.format_qemu_cmdline(arch, self.build_dir, distro, image,
                                               output_file, None, enforce_pcbios)
        cmdline.insert(1, '-nographic')

        self.log.info('QEMU boot line:\n' + ' '.join(cmdline))

        login_prompt = b'isar login:'
        # the printk of recipes-kernel/example-module
        module_output = b'Just an example'
        resize_output = None

        bb_output = start_vm.get_bitbake_env(arch, distro, image).decode()
        image_fstypes = start_vm.get_bitbake_var(bb_output, 'IMAGE_FSTYPES')
        wks_file = start_vm.get_bitbake_var(bb_output, 'WKS_FILE')
        # only the first type will be tested in start_vm.py
        if image_fstypes.split()[0] == 'wic':
            if wks_file:
                bbdistro = start_vm.get_bitbake_var(bb_output, 'DISTRO')
                # ubuntu is less verbose so we do not see the message
                # /etc/sysctl.d/10-console-messages.conf
                if bbdistro and "ubuntu" not in bbdistro:
                    if "sdimage-efi-sd" in wks_file:
                        # output we see when expand-on-first-boot runs on ext4
                        resize_output = b'resized filesystem to'
                    if "sdimage-efi-btrfs" in wks_file:
                        resize_output = b': resize device '

        timeout = time.time() + int(time_to_wait)

        p1 = subprocess.Popen('exec ' + ' '.join(cmdline), shell=True,
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True)

        if cmd is not None or script is not None:
            rc = None
            try:
                port = None
                for arg in cmdline:
                    match = re.match(r".*hostfwd=tcp::(\d*).*", arg)
                    if match:
                        port = match.group(1)
                        break

                # copy private key to build directory
                priv_key = '%s/ci_priv_key' % self.build_dir
                if not os.path.exists(priv_key):
                    shutil.copy(os.path.dirname(__file__) + '/keys/ssh/id_rsa', priv_key)
                    os.chmod(priv_key, 0o400)

                cmd_prefix = self.get_ssh_cmd_prefix(port, priv_key)
                self.log.debug('Connect command:\n' + cmd_prefix)
                rc = self.wait_connection(p1, cmd_prefix, timeout)

                if rc == 0:
                    if cmd is not None:
                        rc = self.exec_cmd(cmd, cmd_prefix)
                        self.log.debug('`' + cmd + '` returned ' + str(rc))
                    elif script is not None:
                        rc = self.run_script(script, cmd_prefix)
                        self.log.debug('`' + script + '` returned ' + str(rc))

            finally:
                if p1.poll() is None:
                    self.log.debug('Killing qemu...')
                    p1.kill()
                p1.wait()

            if rc != 0:
                self.fail('Log ' + output_file)

            return

        try:
            poller = select.poll()
            poller.register(p1.stdout, select.POLLIN)
            poller.register(p1.stderr, select.POLLIN)
            while time.time() < timeout and p1.poll() is None:
                events = poller.poll(1000 * (timeout - time.time()))
                for fd, event in events:
                    if event != select.POLLIN:
                        continue
                    if fd == p1.stdout.fileno():
                        # Wait for the complete string if it is read in chunks
                        # like "i", "sar", " login:"
                        time.sleep(0.01)
                        data = os.read(fd, 1024)
                        if login_prompt in data:
                            raise CanBeFinished
                    if fd == p1.stderr.fileno():
                        app_log.error(p1.stderr.readline().rstrip())
        except CanBeFinished:
            self.log.debug('Got login prompt')
        finally:
            if p1.poll() is None:
                p1.kill()
            p1.wait()

        if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
            with open(output_file, "rb") as f1:
                data = f1.read()
                if (module_output in data or skip_modulecheck) \
                   and login_prompt in data:
                    if resize_output:
                        if resize_output in data:
                            return
                    else:
                        return
                app_log.error(data.decode(errors='replace'))

        self.fail('Log ' + output_file)
