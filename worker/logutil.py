# Copyright 2009-2014 Eucalyptus Systems, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; version 3 of the License.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see http://www.gnu.org/licenses/.
#
# Please contact Eucalyptus Systems, Inc., 6755 Hollister Ave., Goleta
# CA 93117, USA or visit http://www.eucalyptus.com/licenses/ if you need
# additional information or have any questions.

import logging
import os
import worker.config as config
from logging.handlers import RotatingFileHandler
from logging.handlers import SysLogHandler

class RestrictedPermissionRotatingFileHandler(RotatingFileHandler):
    def _open(self):
        """
        Override base class method to set 600 mod on a newly created log.
        """
        umask=os.umask(0o066)
        rfh = RotatingFileHandler._open(self)
        os.umask(umask)
        return rfh

#
# We can't specify the log file in the config module since that will
# import boto and keep us from initializing the boto logger.
#
LOG_FILE = '/var/log/eucalyptus-imaging-worker/worker.log'
LOG_BYTES = 1024 * 1024  # 1MB

log = logging.getLogger('worker')
boto_log = logging.getLogger('boto')
workflow_log = logging.getLogger('euca-workflow')
log.setLevel(logging.INFO)
boto_log.setLevel(logging.INFO)
workflow_log.setLevel(logging.INFO)
# local handler
local_formatter = logging.Formatter('%(asctime)s %(name)s [%(levelname)s]:%(message)s')
file_log_handler = RestrictedPermissionRotatingFileHandler(LOG_FILE, maxBytes=LOG_BYTES, backupCount=5)
file_log_handler.setFormatter(local_formatter)
log.addHandler(file_log_handler)
boto_log.addHandler(file_log_handler)
workflow_log.addHandler(file_log_handler)
# remote handler
# config.query_user_data()
remote_server = config.get_log_server()
remote_port = config.get_log_server_port()
if remote_server is not None and remote_port is not None:
    remote_formatter = logging.Formatter('imaging-worker ' + config.get_worker_id() + ' [%(levelname)s]:%(message)s')
    remote_log_handler = SysLogHandler(address=(remote_server, remote_port),
                                       facility=SysLogHandler.LOG_DAEMON)
    remote_log_handler.setFormatter(remote_formatter)
    log.addHandler(remote_log_handler)
    workflow_log.addHandler(remote_log_handler)
    log.info('Adder remote sys log handler')
else:
    log.warn('Remote sys log handler is not configured. Log server is set to %s with port %s ' % (remote_server, remote_port))


def get_log_level_as_num(lvl):
    lvl_num = None
    if isinstance(lvl, str):
        try:
            lvl_num = logging.__getattribute__(lvl.upper())
        except AttributeError:
            log.warn("Failed to set log level to '%s'" % lvl)
            return
    else:
        lvl_num = lvl
    return lvl_num


def set_log_file_count(rotating_files_count):
    try:
        file_log_handler.backupCount = int(rotating_files_count)
    except Exception, err:
        log.warn("Failed to set backup file count to '%s' due to '%s'" % (rotating_files_count, err))


def set_log_file_size(size_bytes):
    try:
        file_log_handler.maxBytes = int(size_bytes)
    except Exception, err:
        log.warn("Failed to set log file count to '%s' due to '%s'" % (size_bytes, err))


# Log level will default to INFO
# If you want more information (like DEBUG) you will have to set the log level
def set_loglevel(lvl):
    log.setLevel(get_log_level_as_num(lvl))
    workflow_log.setLevel(get_log_level_as_num(lvl))


def set_boto_loglevel(lvl):
    boto_log.setLevel(get_log_level_as_num(lvl))


class CustomLog:
    def __init__(self, logger_name):
        self.log = logging.getLogger(logger_name)

    def info(self, message, process=None):
        self.log.info(message if process is None else '(%s) %s' % (process, message))

    def warn(self, message, process=None):
        self.log.warn(message if process is None else '(%s) %s' % (process, message))

    def error(self, message, process=None):
        self.log.error(message if process is None else '(%s) %s' % (process, message))

    def debug(self, message, process=None):
        self.log.debug(message if process is None else '(%s) %s' % (process, message))

    def critical(self, message, process=None):
        self.log.critical(message if process is None else '(%s) %s' % (process, message))

    def exception(self, message, process=None):
        self.log.exception(message if process is None else '(%s) %s' % (process, message))
