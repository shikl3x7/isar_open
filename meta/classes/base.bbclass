# Copyright (C) 2003  Chris Larson
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR
# OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.

THISDIR = "${@os.path.dirname(d.getVar('FILE'))}"
FILESPATH = "${@base_set_filespath(["${FILE_DIRNAME}/${PF}", "${FILE_DIRNAME}/${P}", "${FILE_DIRNAME}/${PN}", "${FILE_DIRNAME}/files", "${FILE_DIRNAME}"], d)}"

OE_IMPORTS += "os sys time oe.path oe.patch oe.sstatesig oe.utils"
OE_IMPORTS[type] = "list"

def oe_import(d):
    import sys

    bbpath = d.getVar("BBPATH").split(":")
    sys.path[0:0] = [os.path.join(dir, "lib") for dir in bbpath]

    def inject(name, value):
        """Make a python object accessible from the metadata"""
        if hasattr(bb.utils, "_context"):
            bb.utils._context[name] = value
        else:
            __builtins__[name] = value

    import oe.data
    for toimport in oe.data.typed_value("OE_IMPORTS", d):
        try:
            imported = __import__(toimport)
            inject(toimport.split(".", 1)[0], imported)
        except AttributeError as e:
            bb.error("Error importing OE modules: %s" % str(e))
    return ""

# We need the oe module name space early (before INHERITs get added)
OE_IMPORTED := "${@oe_import(d)}"

def get_deb_host_arch(d):
    import subprocess
    if d.getVar("ISAR_CROSS_COMPILE") != "1":
        return d.getVar("DISTRO_ARCH")
    host_arch = subprocess.check_output(
        ["dpkg", "--print-architecture"]
    ).decode('utf-8').strip()
    return host_arch
HOST_ARCH ??= "${@get_deb_host_arch(d)}"
HOST_DISTRO ??= "${DISTRO}"

die() {
	bbfatal "$*"
}

inherit logging
inherit template

# Derived from bitbake: bitbake/classes/base.bbclass
addtask showdata
do_showdata[nostamp] = "1"
python do_showdata() {
    for e in d.keys():
        if d.getVarFlag(e, 'python'):
            code = d.getVar(e)
            if code.startswith("def"):
                bb.plain("\n" + code + "\n")
            else:
                bb.plain(
                    "\npython {name} () {{\n{code}}}\n".format(
                        name=e, code=code
                    )
                )
}

# Derived from Open Embedded: openembedded-core/meta/classes/utility-tasks.bbclass
addtask listtasks
do_listtasks[nostamp] = "1"
python do_listtasks() {
    tasks = {}
    maxlen = 0
    for e in d.keys():
        if d.getVarFlag(e, 'task'):
            maxlen = max(maxlen, len(e))
            if e.endswith('_setscene'):
                tasks[e] = (
                    d.getVarFlag(e[:-9], 'doc') or ''
                ) + " (setscene version)"
            else:
                tasks[e] = d.getVarFlag(e, 'doc') or ''

    for name, desc in sorted(tasks.items()):
        bb.plain("{0:{len}}  {1}".format(name, desc, len=maxlen))
}

root_cleandirs() {
    ROOT_CLEANDIRS_DIRS_PY="${@d.getVar("ROOT_CLEANDIRS_DIRS") or ""}"
    ROOT_CLEANDIRS_DIRS="${ROOT_CLEANDIRS_DIRS-${ROOT_CLEANDIRS_DIRS_PY}}"
    TMPDIR_PY="${@d.getVar("TMPDIR") or ""}"
    TMPDIR="${TMPDIR-${TMPDIR_PY}}"
    for i in $ROOT_CLEANDIRS_DIRS; do
        awk '{ print $2 }' /proc/mounts | grep -q "^${i}\(/\|\$\)" && \
            die "Could not remove $i, because subdir is mounted"
    done
    for i in $ROOT_CLEANDIRS_DIRS; do
        sudo rm -rf --one-file-system "$TMPDIR$i"
        mkdir -p "$TMPDIR$i"
    done
}

python() {
    import re

    needsrcrev = False
    srcuri = d.getVar('SRC_URI')
    for uri_string in srcuri.split():
        uri = bb.fetch.URI(uri_string)
        if uri.scheme in ("svn", "git", "gitsm", "hg", "p4", "repo"):
            needsrcrev = True

    if needsrcrev:
        d.setVar("SRCPV", "${@bb.fetch2.get_srcrev(d)}")

    for e in d.keys():
        flags = d.getVarFlags(e)
        if flags and flags.get('task'):
            rcleandirs = flags.get('root_cleandirs')
            if rcleandirs:
                tmpdir = os.path.normpath(d.getVar("TMPDIR"))
                rcleandirs = list(
                    os.path.normpath(d.expand(i)) for i in rcleandirs.split()
                )

                for i in rcleandirs:
                    if not i.startswith(tmpdir):
                        bb.fatal(
                            "root_cleandirs entry {} is not contained in TMPDIR {}".format(
                                i, tmpdir
                            )
                        )

                if flags.get('python'):
                    cleandir_code = (
                        "{ws}d.setVar('ROOT_CLEANDIRS_DIRS', '{dirlist}')\n"
                        "{ws}bb.build.exec_func('root_cleandirs', d)\n"
                    )
                else:
                    cleandir_code = (
                        "{ws}ROOT_CLEANDIRS_DIRS='{dirlist}'\n"
                        "{ws}root_cleandirs\n"
                    )

                ws = re.match(r"^\s*", d.getVar(e, False)).group()
                # remove prefix ${TMPDIR}, so we don't have absolute paths in variable e
                dirs = [dir[len(tmpdir):] for dir in rcleandirs]
                d.prependVar(
                    e, cleandir_code.format(ws=ws, dirlist=" ".join(dirs))
                )

    need_machine = d.getVar('COMPATIBLE_MACHINE')
    if need_machine and not d.getVar('PARSE_ALL_RECIPES', False):
        compat_machines = (d.getVar('MACHINEOVERRIDES') or "").split(":")
        for m in compat_machines:
            if re.match(need_machine, m):
                break
        else:
            raise bb.parse.SkipRecipe("incompatible with machine %s (not in COMPATIBLE_MACHINE)" % d.getVar('MACHINE'))
}

def isar_export_proxies(d):
    deadend_proxy = 'http://this.should.fail:4242'
    variables = ['http_proxy', 'HTTP_PROXY', 'https_proxy', 'HTTPS_PROXY',
                    'ftp_proxy', 'FTP_PROXY' ]

    if d.getVar('BB_NO_NETWORK') == "1":
        for v in variables:
            d.setVar(v, deadend_proxy)
        for v in [ 'no_proxy', 'NO_PROXY' ]:
            d.setVar(v, '')

    return bb.utils.export_proxies(d)

def isar_export_ccache(d):
    if d.getVar('USE_CCACHE') == '1':
        os.environ['CCACHE_DIR'] = '/ccache'
        os.environ['PATH_PREPEND'] = '/usr/lib/ccache'
        if d.getVar('CCACHE_DEBUG') == '1':
            os.environ['CCACHE_DEBUG'] = '1'
            os.environ['CCACHE_DEBUGDIR'] = '/ccache/debug'
    else:
        os.environ['CCACHE_DISABLE'] = '1'

do_fetch[dirs] = "${DL_DIR}"
do_fetch[file-checksums] = "${@bb.fetch.get_checksum_file_list(d)}"
do_fetch[vardeps] += "SRCREV"
do_fetch[network] = "${TASK_USE_NETWORK}"

# Fetch package from the source link
python do_fetch() {
    src_uri = (d.getVar('SRC_URI') or "").split()
    if len(src_uri) == 0:
        return

    try:
        fetcher = bb.fetch2.Fetch(src_uri, d)
        fetcher.download()
    except bb.fetch2.BBFetchException as e:
        bb.fatal(str(e))
}

addtask fetch

do_unpack[dirs] = "${WORKDIR}"

# Unpack package and put it into working directory
python do_unpack() {
    src_uri = (d.getVar('SRC_URI') or "").split()
    if len(src_uri) == 0:
        return

    rootdir = d.getVar('WORKDIR')

    try:
        fetcher = bb.fetch2.Fetch(src_uri, d)
        fetcher.unpack(rootdir)
    except bb.fetch2.BBFetchException as e:
        bb.fatal(str(e))
}

addtask unpack after do_fetch

do_build[noexec] = "1"
do_build () {
    :
}

addtask build

CLEANFUNCS ?= ""

# Derived from OpenEmbedded Core: meta/classes/utility-tasks.bbclass
addtask clean
do_clean[nostamp] = "1"
do_clean[network] = "${TASK_USE_SUDO}"
python do_clean() {
    import subprocess
    import glob

    for f in (d.getVar('CLEANFUNCS') or '').split():
        bb.build.exec_func(f, d)

    workdir = d.expand("${WORKDIR}")
    subprocess.check_call(["sudo", "rm", "-rf", workdir])

    stampclean = bb.data.expand(d.getVar('STAMPCLEAN', False), d)
    stampdirs = glob.glob(stampclean)
    subprocess.check_call(["sudo", "rm", "-rf"] + stampdirs)
}

# Derived from OpenEmbedded Core: meta/classes/base.bbclass
addtask cleansstate after do_clean
do_cleansstate[nostamp] = "1"
python do_cleansstate() {
    sstate_clean_cachefiles(d)
}

addtask cleanall after do_cleansstate
do_cleanall[nostamp] = "1"
python do_cleanall() {
    src_uri = (d.getVar('SRC_URI') or "").split()
    if len(src_uri) == 0:
        return

    try:
        fetcher = bb.fetch2.Fetch(src_uri, d)
        fetcher.clean()
    except bb.fetch2.BBFetchException as e:
        bb.fatal(str(e))
}

# Derived from OpenEmbedded Core: meta/classes/utils.bbclass
def base_set_filespath(path, d):
    filespath = []
    extrapaths = (d.getVar("FILESEXTRAPATHS") or "")
    # Remove default flag which was used for checking
    extrapaths = extrapaths.replace("__default:", "")
    # Don't prepend empty strings to the path list
    if extrapaths != "":
        path = extrapaths.split(":") + path
    # The ":" ensures we have an 'empty' override
    overrides = (":" + (d.getVar("FILESOVERRIDES") or "")).split(":")
    overrides.reverse()
    for o in overrides:
        for p in path:
            if p != "":
                filespath.append(os.path.join(p, o))
    return ":".join(filespath)

def calculate_build_uuid(d):
    import uuid

    uuid_data = bb.persist_data.persist('BB_ISAR_UUID_DATA', d)
    if "uuid" not in uuid_data or not uuid_data["uuid"]:
        # Generate new UUID
        uuid_data["uuid"] = str(uuid.uuid4())

    return uuid_data["uuid"]

# Unique ID for this build, used to avoid name clashes on external mountpoints
# When running parallel builds in different PID namespaces
ISAR_BUILD_UUID = "${@ calculate_build_uuid(d)}"
