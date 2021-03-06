#!/usr/bin/env python
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

import argparse
import os
import sys
import logging

repo_root_dir = os.path.realpath(os.path.join(
    os.path.dirname(__file__), os.pardir))
sys.path.insert(0, repo_root_dir)

from lib import exception
from lib import log_helper
from lib.utils import is_package_installed
from lib.utils import recursive_glob
from lib.utils import run_command

def validate_rpm_spec(spec_file_path):
    """
    Validate RPM specification file

    Args:
        spec_file_path (str): RPM specification file path

    Returns:
        bool: if RPM specification file is valid
    """

    try:
        LOG.info("Verifying file %s" % spec_file_path)
        run_command("rpmlint -f .rpmlint -v %s" % spec_file_path)
    except exception.SubprocessError as e:
        #pylint: disable=no-member
        LOG.exception("validation of RPM specification file %s failed, output: %s" % (spec_file_path, e.stdout))
        return False
    return True


def validate_rpm_specs(base_dir):
    """
    Validate specification files of rpm packages in a base directory

    Args:
        base_dir (str): base directory path

    Returns:
        bool: if RPM specification files are valid
    """

    files = recursive_glob(base_dir, "*.spec")
    valid = True
    for _file in files:
        if not validate_rpm_spec(_file):
            valid = False

    if valid:
        LOG.info("Validation completed successfully.")
    else:
        LOG.info("Validation failed.")

    return valid


def parse_cli_options():
    """
    Parse CLI options

    Returns:
        Namespace: CLI options. Valid attributes: rpm_specs_base_dir
    """

    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--rpm-specs-base-dir', dest='rpm_specs_base_dir',
                        required=True, help='RPM specification files base directory path')
    args = parser.parse_args()
    return args


if __name__ == '__main__':
    log_helper.LogHelper()
    LOG = logging.getLogger(__name__)
    if not is_package_installed('rpmlint'):
        LOG.error("rpmlint package should be installed before running this script")
        sys.exit(1)
    args = parse_cli_options()
    if not validate_rpm_specs(args.rpm_specs_base_dir):
        LOG.error("RPM spec files contain errors.")
        sys.exit(2)
