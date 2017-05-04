# Copyright (C) IBM Corp. 2016.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import datetime
import logging
import os

from lib import exception
from lib import utils
from lib import distro_utils
from lib import packages_groups_xml_creator
from lib.constants import LATEST_SYMLINK_NAME

LOG = logging.getLogger(__name__)
ISO_REPO_MINIMAL_PACKAGES_GROUPS = ["core"]
ISO_REPO_MINIMAL_PACKAGES = ["authconfig", "chrony", "grub2"]


class MockPungiIsoBuilder(object):

    def __init__(self, config):
        self.config = config
        self.work_dir = self.config.get('work_dir')
        self.timestamp = datetime.datetime.now().isoformat()
        self.result_dir = os.path.join(self.config.get('result_dir'),
            'iso', self.timestamp)
        self.distro = self.config.get("iso_name")
        self.version = datetime.date.today().strftime("%y%m%d")
        (_, _, self.arch) = distro_utils.detect_distribution()
        self.mock_binary = self.config.get('mock_binary')
        self.mock_args = self.config.get('mock_args') or ""
        self.pungi_binary = self.config.get('pungi_binary') or "pungi"
        self.pungi_args = self.config.get('pungi_args') or ""

    def _run_mock_command(self, cmd):
        distro = distro_utils.get_distro(
            self.config.get('distro_name'),
            self.config.get('distro_version'),
            self.config.get('architecture'))
        mock_config_file = self.config.get('mock_config').get(distro.name).get(
            distro.version)
        try:
            utils.run_command("%s -r %s %s %s" % (
                self.mock_binary, mock_config_file,
                self.mock_args, cmd))
        except exception.SubprocessError:
            LOG.error("Failed to build ISO")
            raise

    def build(self):
        LOG.info("Starting ISO build process")
        self._setup()
        self._build()
        self._save()

    def _setup(self):
        LOG.info("Initializing a chroot")
        self._run_mock_command("--init")

        package_list = ["createrepo", "pungi"]
        LOG.info("Installing %s inside the chroot" % " ".join(package_list))
        self._run_mock_command("--install %s" % " ".join(package_list))

        self._create_iso_repo()

        self._create_iso_kickstart()

    def _create_iso_repo(self):
        LOG.info("Creating ISO yum repository inside chroot")

        LOG.debug("Creating ISO yum repository directory")
        mock_iso_repo_dir = self.config.get('mock_iso_repo_dir')
        self._run_mock_command("--shell 'mkdir -p %s'" % mock_iso_repo_dir)

        LOG.debug("Copying rpm packages to ISO yum repo directory")
        packages_dir = self.config.get('packages_dir')
        rpm_files = utils.recursive_glob(packages_dir, "*.rpm")
        self._run_mock_command("--copyin %s %s" %
                               (" ".join(rpm_files), mock_iso_repo_dir))

        LOG.debug("Creating package groups metadata file (comps.xml)")
        comps_xml_str = packages_groups_xml_creator.create_comps_xml(
            self.config.get('installable_environments'))
        comps_xml_file = "host-os-comps.xml"
        comps_xml_path = os.path.join(self.work_dir, comps_xml_file)
        try:
            with open(comps_xml_path, 'wt') as f:
                f.write(comps_xml_str)
        except IOError:
            LOG.error("Failed to write XML to %s file." % comps_xml_path)
            raise

        comps_xml_chroot_path = os.path.join("/", comps_xml_file)
        self._run_mock_command("--copyin %s %s" %
                               (comps_xml_path, comps_xml_chroot_path))

        LOG.debug("Creating ISO yum repository")
        createrepo_cmd = "createrepo -v -g %s %s" % (comps_xml_chroot_path,
                                                     mock_iso_repo_dir)
        self._run_mock_command("--shell '%s'" % createrepo_cmd)

    def _create_iso_kickstart(self):
        kickstart_file = self.config.get('automated_install_file')
        kickstart_path = os.path.join(self.work_dir, kickstart_file)
        LOG.info("Creating ISO kickstart file %s" % kickstart_path)

        repo_urls = self.config.get('distro_repos_urls')
        mock_iso_repo_name = self.config.get('mock_iso_repo_name')
        mock_iso_repo_dir = self.config.get('mock_iso_repo_dir')
        repo_urls[mock_iso_repo_name] = "file://%s/" % mock_iso_repo_dir
        iso_repo_packages_groups = (
            ISO_REPO_MINIMAL_PACKAGES_GROUPS
            + self.config.get('iso_repo_packages_groups'))
        iso_repo_packages = (
            ISO_REPO_MINIMAL_PACKAGES
            + self.config.get('iso_repo_packages'))

        with open(kickstart_path, "wt") as kickstart_file:
            for name, url in repo_urls.items():
                repo = ("repo --name=%s --baseurl=%s\n" % (name, url))
                kickstart_file.write(repo)
            kickstart_file.write("%packages\n")
            for group in iso_repo_packages_groups:
                kickstart_file.write("@{}\n".format(group))
            for package in iso_repo_packages:
                kickstart_file.write("{}\n".format(package))
            kickstart_file.write("%end\n")

        self._run_mock_command("--copyin %s /" % kickstart_path)

    def _build(self):
        LOG.info("Building ISO")
        build_cmd = ("%s %s -c %s --name %s --ver %s" %
                    (self.pungi_binary, self.pungi_args,
                     self.config.get('automated_install_file'),
                     self.distro, self.version))
        self._run_mock_command("--shell '%s'" % build_cmd)

    def _save(self):
        utils.create_directory(self.result_dir)
        latest_dir = os.path.join(os.path.dirname(self.result_dir),
                                  LATEST_SYMLINK_NAME)
        utils.force_symlink(self.timestamp, latest_dir)

        iso_file = "%s-DVD-%s-%s.iso" % (self.distro, self.arch, self.version)
        checksum_file = ("%s-%s-%s-CHECKSUM" %
                         (self.distro, self.version, self.arch))
        iso_dir = "/%s/%s/iso" % (self.version, self.arch)
        iso_path = os.path.join(iso_dir, iso_file)
        checksum_path = os.path.join(iso_dir, checksum_file)
        chroot_files = "%s %s" % (iso_path, checksum_path)

        LOG.info("Saving ISO %s and checksum %s at %s" %
                 (iso_file, checksum_file, self.result_dir))
        self._run_mock_command("--copyout %s %s" %
                               (chroot_files, self.result_dir))

    def clean(self):
        self._run_mock_command("--clean")
