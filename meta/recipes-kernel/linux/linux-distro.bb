# Distro kernel dummy package
#
# This software is a part of ISAR.
# Copyright (c) Siemens AG, 2018
#
# SPDX-License-Identifier: MIT

python() {
    distro_kernels = d.getVar('DISTRO_KERNELS') or ""
    for kernel in distro_kernels.split():
        d.appendVar('PROVIDES', ' linux-image-' + kernel)
        d.appendVar('PROVIDES', ' linux-headers-' + kernel)
    if d.getVar('KERNEL_IMAGE_PKG'):
        d.appendVar('PROVIDES', ' ' + d.getVar('KERNEL_IMAGE_PKG'))
    if d.getVar('KERNEL_HEADERS_PKG'):
        d.appendVar('PROVIDES', ' ' + d.getVar('KERNEL_HEADERS_PKG'))
}
