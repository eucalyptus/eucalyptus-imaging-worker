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
import config
from logging.handlers import RotatingFileHandler
from logging.handlers import SysLogHandler

#
# We can't specify the log file in the config module since that will
# import boto and keep us from initializing the boto logger.
#
LOG_FILE = '/var/log/eucalyptus-imaging-worker/worker.log'
LOG_BYTES = 1024 * 1024 # 1MB

log = logging.getLogger('worker')
botolog = logging.getLogger('boto')
log.setLevel(logging.INFO)
botolog.setLevel(logging.INFO)
# local handler
local_formatter = logging.Formatter('%(asctime)s %(name)s [%(levelname)s]:%(message)s')
file_log_handler = RotatingFileHandler(LOG_FILE, maxBytes=LOG_BYTES, backupCount=5)
file_log_handler.setFormatter(local_formatter)
log.addHandler(file_log_handler)
botolog.addHandler(file_log_handler)
# remote handler
if config.get_log_server() != None and config.get_log_server_port() != None:
    remote_formatter = logging.Formatter('imaging-worker ' + config.get_worker_id() + ' [%(levelname)s]:%(message)s')
    remote_log_handler = SysLogHandler(address=(config.get_log_server(), config.get_log_server_port()), facility=SysLogHandler.LOG_DAEMON)
    remote_log_handler.setFormatter(remote_formatter)
    log.addHandler(remote_log_handler)

# Log level will default to INFO
# If you want more information (like DEBUG) you will have to set the log level
def set_loglevel(lvl):
    global log
    lvl_num = None
    if isinstance(lvl, str):
        try:
            lvl_num = logging.__getattribute__(lvl.upper())
        except AttributeError:
            log.warn("Failed to set log level to '%s'" % lvl)
            return
    else:
        lvl_num = lvl

    log.setLevel(lvl_num)
    botolog.setLevel(lvl_num)
