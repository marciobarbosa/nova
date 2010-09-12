# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""
Drivers for volumes
"""

import logging

from twisted.internet import defer

from nova import exception
from nova import flags
from nova import process


FLAGS = flags.FLAGS
flags.DEFINE_string('volume_group', 'nova-volumes',
                    'Name for the VG that will contain exported volumes')
flags.DEFINE_string('aoe_eth_dev', 'eth0',
                    'Which device to export the volumes on')


class AOEDriver(object):
    """Executes commands relating to AOE volumes"""
    def __init__(self, execute=process.simple_execute, *args, **kwargs):
        self._execute = execute

    @defer.inlineCallbacks
    def create_volume(self, volume_name, size):
        """Creates a logical volume"""
        # NOTE(vish): makes sure that the volume group exists
        yield self._execute("vgs %s" % FLAGS.volume_group)
        if int(size) == 0:
            sizestr = '100M'
        else:
            sizestr = '%sG' % size
        yield self._execute(
                "sudo lvcreate -L %s -n %s %s" % (sizestr,
                                                  volume_name,
                                                  FLAGS.volume_group))

    @defer.inlineCallbacks
    def delete_volume(self, volume_name):
        """Deletes a logical volume"""
        yield self._execute(
                "sudo lvremove -f %s/%s" % (FLAGS.volume_group,
                                            volume_name))

    @defer.inlineCallbacks
    def create_export(self, volume_name, shelf_id, blade_id):
        """Creates an export for a logical volume"""
        yield self._execute(
                "sudo vblade-persist setup %s %s %s /dev/%s/%s" %
                (shelf_id,
                 blade_id,
                 FLAGS.aoe_eth_dev,
                 FLAGS.volume_group,
                 volume_name))

    @defer.inlineCallbacks
    def discover_volume(self, _volume_name):
        """Discover volume on a remote host"""
        yield self._execute("sudo aoe-discover")
        yield self._execute("sudo aoe-stat")

    @defer.inlineCallbacks
    def remove_export(self, _volume_name, shelf_id, blade_id):
        """Removes an export for a logical volume"""
        # NOTE(vish): These commands can partially fail sometimes, but
        #             running them a second time on failure will usually
        #             pick up the remaining tasks even though it also
        #             raises an exception
        try:
            yield self._execute("sudo vblade-persist stop %s %s" %
                                (shelf_id, blade_id))
        except exception.ProcessExecutionError:
            logging.exception("vblade stop threw an error, recovering")
            yield self._execute("sleep 2")
            yield self._execute("sudo vblade-persist stop %s %s" %
                                (shelf_id, blade_id),
                                check_exit_code=False)
        try:
            yield self._execute("sudo vblade-persist destroy %s %s" %
                                (shelf_id, blade_id))
        except exception.ProcessExecutionError:
            logging.exception("vblade destroy threw an error, recovering")
            yield self._execute("sleep 2")
            yield self._execute("sudo vblade-persist destroy %s %s" %
                                (shelf_id, blade_id),
                                check_exit_code=False)

    @defer.inlineCallbacks
    def ensure_exports(self):
        """Runs all existing exports"""
        # NOTE(ja): wait for blades to appear
        yield self._execute("sleep 2")
        yield self._execute("sudo vblade-persist auto all",
                            check_exit_code=False)
        yield self._execute("sudo vblade-persist start all",
                            check_exit_code=False)


class FakeAOEDriver(AOEDriver):
    """Logs calls instead of executing"""
    def __init__(self, *args, **kwargs):
        super(FakeAOEDriver, self).__init__(self.fake_execute)

    @staticmethod
    def fake_execute(cmd, *_args, **_kwargs):
        """Execute that simply logs the command"""
        logging.debug("FAKE AOE: %s", cmd)
