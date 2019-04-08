#! /usr/bin/python
# -*- coding: utf-8 -*-
#
# (C) 2014 mhrusecky@suse.cz, openSUSE.org
# (C) 2014 tchvatal@suse.cz, openSUSE.org
# (C) 2014 aplanas@suse.de, openSUSE.org
# (C) 2014 coolo@suse.de, openSUSE.org
# (C) 2017 okurz@suse.de, openSUSE.org
# (C) 2018 dheidler@suse.de, openSUSE.org
# Distribute under GPLv2 or GPLv3

from __future__ import print_function

import re
from xml.etree import cElementTree as ET

from ttm.manager import ToTestManager, NotFoundException

class ToTestReleaser(ToTestManager):

    def __init__(self, tool):
        ToTestManager.__init__(self, tool)

    def setup(self, project):
        super(ToTestReleaser, self).setup(project)

    def release(self, project, force=False):
        self.setup(project)

        testing_snapshot = self.get_status('testing')
        new_snapshot = self.version_from_project()

        # not overwriting
        if new_snapshot == testing_snapshot:
            self.logger.debug('no change in snapshot version')
            return

        if testing_snapshot != self.get_status('failed') and testing_snapshot != self.get_status('published'):
            self.logger.debug('Snapshot {} is still in progress'.format(testing_snapshot))
            return

        self.logger.info('testing snapshot %s', testing_snapshot)
        self.logger.debug('new snapshot %s', new_snapshot)

        if not self.is_snapshotable():
            self.logger.debug('not snapshotable')
            return

        self.update_totest(new_snapshot)
        self.update_status('testing', new_snapshot)
        self.update_status('failed', '')
        self.write_version_to_dashboard('totest', new_snapshot)
        return 1

    def release_version(self):
        url = self.api.makeurl(['build', self.project.name, 'standard', self.project.arch,
                                '000release-packages:%s-release' % self.project.base])
        f = self.api.retried_GET(url)
        root = ET.parse(f).getroot()
        for binary in root.findall('binary'):
            binary = binary.get('filename', '')
            result = re.match(r'.*-([^-]*)-[^-]*.src.rpm', binary)
            if result:
                return result.group(1)

        raise NotFoundException("can't find %s version" % self.project.name)

    def version_from_project(self):
        if not self.project.take_source_from_product:
            return self.release_version()

        if len(self.project.main_products):
            return self.iso_build_version(self.project.name, self.project.main_products[0])

        return self.iso_build_version(self.project.name, self.project.image_products[0].package,
                                      arch=self.project.image_products[0].archs[0])

    def maxsize_for_package(self, package):
        if re.match(r'.*-mini-.*', package):
            return 737280000  # a CD needs to match

        if re.match(r'.*-dvd5-.*', package):
            return 4700372992  # a DVD needs to match

        if re.match(r'livecd-x11', package):
            return 681574400  # not a full CD

        if re.match(r'livecd-.*', package):
            return 999999999  # a GB stick

        if re.match(r'.*-(dvd9-dvd|cd-DVD)-.*', package):
            return 8539996159

        if re.match(r'.*-ftp-(ftp|POOL)-', package):
            return None

        # containers have no size limit
        if re.match(r'(opensuse|kubic)-.*-image.*', package):
            return None

        if '-Addon-NonOss-ftp-ftp' in package:
            return None

        if 'JeOS' in package or 'Kubic' in package:
            return 4700372992

        raise Exception('No maxsize for {}'.format(package))

    def package_ok(self, project, package, repository, arch):
        """Checks one package in a project and returns True if it's succeeded

        """

        query = {'package': package, 'repository': repository, 'arch': arch}

        url = self.api.makeurl(['build', project, '_result'], query)
        f = self.api.retried_GET(url)
        root = ET.parse(f).getroot()
        # [@code!='succeeded'] is not supported by ET
        failed = [status for status in root.findall('result/status') if status.get('code') != 'succeeded']

        if any(failed):
            self.logger.info(
                '%s %s %s %s -> %s' % (project, package, repository, arch, failed[0].get('code')))
            return False

        if not len(root.findall('result/status[@code="succeeded"]')):
            self.logger.info('No "succeeded" for %s %s %s %s' % (project, package, repository, arch))
            return False

        maxsize = self.maxsize_for_package(package)
        if not maxsize:
            return True

        url = self.api.makeurl(['build', project, repository, arch, package])
        f = self.api.retried_GET(url)
        root = ET.parse(f).getroot()
        for binary in root.findall('binary'):
            if not binary.get('filename', '').endswith('.iso'):
                continue
            isosize = int(binary.get('size', 0))
            if isosize > maxsize:
                self.logger.error('%s %s %s %s: %s' % (
                    project, package, repository, arch, 'too large by %s bytes' % (isosize - maxsize)))
                return False

        return True

    def is_snapshotable(self):
        """Check various conditions required for factory to be snapshotable

        """

        if not self.all_repos_done(self.project.name):
            return False

        for product in self.project.ftp_products + self.project.main_products:
            if not self.package_ok(self.project.name, product, self.project.product_repo, self.project.product_arch):
                return False

        for product in self.project.image_products + self.project.container_products:
            for arch in product.archs:
                if not self.package_ok(self.project.name, product.package, self.project.product_repo, arch):
                    return False

        if len(self.project.livecd_products):
            if not self.all_repos_done('%s:Live' % self.project.name):
                return False

            for product in self.project.livecd_products:
                for arch in product.archs:
                    if not self.package_ok('%s:Live' % self.project.name, product.package,
                                           self.project.product_repo, arch):
                        return False

        if self.project.need_same_build_number:
            # make sure all medias have the same build number
            builds = set()
            for p in self.project.ftp_products:
                if 'Addon-NonOss' in p:
                    # XXX: don't care about nonoss atm.
                    continue
                builds.add(self.ftp_build_version(self.project.name, p))
            for p in self.project.main_products:
                builds.add(self.iso_build_version(self.project.name, p))
            for p in self.project.livecd_products + self.project.image_products:
                for arch in p.archs:
                    builds.add(self.iso_build_version(self.project.name, p.package,
                                                      arch=arch))
            if len(builds) != 1:
                self.logger.debug('not all medias have the same build number')
                return False

        return True

    def _release(self, set_release=None):
        for container in self.project.container_products:
            # Containers are built in the same repo as other image products,
            # but released into a different repo in :ToTest
            self.release_package(self.project.name, container.package, repository=self.project.product_repo,
                                  target_project=self.project.test_project,
                                  target_repository=self.project.totest_container_repo)

        if len(self.project.main_products):
            for cd in self.project.main_products:
                self.release_package(self.project.name, cd, set_release=set_release,
                                      repository=self.project.product_repo)

            for product in self.project.ftp_products:
                self.release_package(self.project.name, product, repository=self.project.product_repo)

        for cd in self.project.livecd_products:
            self.release_package('%s:Live' %
                                  self.project.name, cd.package, set_release=set_release,
                                  repository=self.project.livecd_repo)

        for image in self.project.image_products:
            self.release_package(self.project.name, image.package, set_release=set_release,
                                  repository=self.project.product_repo)

    def update_totest(self, snapshot=None):
        # omit snapshot, we don't want to rename on release
        if not self.project.set_snapshot_number:
            snapshot = None
        release = 'Snapshot%s' % snapshot if snapshot else None
        self.logger.info('Updating snapshot %s' % snapshot)
        if not (self.dryrun or self.project.do_not_release):
            self.api.switch_flag_in_prj(self.project.test_project, flag='publish', state='disable',
                                        repository=self.project.product_repo)

        self._release(set_release=release)
