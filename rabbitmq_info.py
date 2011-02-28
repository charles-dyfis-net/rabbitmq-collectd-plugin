# rabbitmq-collectd-plugin - rabbitmq_info.py
#
# Author: Daniel Maher (http://www.dark.ca/)
# Description: This plugin uses collectd's Python plugin to obtain Rabbitmq metrics.
#
# Loosely based on Garret Heaton's "redis-collectd-plugin"
#   https://github.com/powdahound/redis-collectd-plugin


import collectd
import collections
import subprocess
import re


NAME = 'rabbitmq_info'
# Override in config by specifying 'RmqcBin'.
RABBITMQCTL_BIN = '/usr/sbin/rabbitmqctl'
# Override in config by specifying 'PmapBin'
PMAP_BIN = '/usr/bin/pmap'
# Override in config by specifying 'PidofBin'.
PIDOF_BIN = '/bin/pidof'
# Override in config by specifying 'Verbose'.
VERBOSE_LOGGING = False


# Obtain the interesting statistical info
def get_stats():
    stats = collections.defaultdict(int)

    try:
        p = subprocess.Popen([RABBITMQCTL_BIN, 'list_vhosts', '-q'], shell=False, stdout=subprocess.PIPE)
    except:
        logger('err', 'Failed to run %s' % RABBITMQCTL_BIN)
        return None

    vhosts = p.communicate()[0].split('\n')

    for vhost in vhosts:
        # call rabbitmqctl
        try:
            p = subprocess.Popen([RABBITMQCTL_BIN, 'list_queues', '-q', '-p', vhost, 'name', 'messages', 'memory', 'consumers'], shell=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        except:
            logger('err', 'Failed to run %s' % RABBITMQCTL_BIN)
            return None



        for line in p.stdout.readlines():
            name, messages, memory, consumers = line.split()
            stats['%s.%s.ctl_messages' % (vhost, name)] = messages
            stats['%s.%s.ctl_memory' % (vhost, name)] = memory
            stats['%s.%s.ctl_consumers' % (vhost, name)] = consumers
            if not memory > 0:
                logger('warn', '%s reports 0 memory usage for %s.%s. This is probably incorrect.' % (RABBITMQCTL_BIN, vhost, name))

        # get the pid of rabbitmq (beam.smp)
        try:
            p = subprocess.Popen([PIDOF_BIN, 'beam.smp'], shell=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        except:
            logger('err', 'Failed to run %s' % PIDOF_BIN)
            return None

        line = p.stdout.read().strip()
        if not re.search('\D', line):
            pid = line
        else:
            logger('err', '%s returned something strange.' % PIDOF_BIN)
            return None

        # use pmap to get proper memory stats
        try:
            p = subprocess.Popen([PMAP_BIN, '-d', pid], shell=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        except:
            logger('err', 'Failed to run %s' % PMAP_BIN)
            return None

        line = p.stdout.readlines()[-1].strip()
        if re.match('mapped', line):
            m = re.match(r"\D+(\d+)\D+(\d+)\D+(\d+)", line)
            stats['pmap_mapped'] = int(m.group(1))
            stats['pmap_used'] = int(m.group(2))
            stats['pmap_shared'] = int(m.group(3))
        else:
            logger('warn', '%s returned something strange.' % PMAP_BIN)
            return None
            
        # Verbose output
        logger('verb', '[rmqctl] Messages: %i, Memory: %i, Consumers: %i' % (stats['ctl_messages'], stats['ctl_memory'], stats['ctl_consumers']))
        logger('verb', '[pmap] Mapped: %i, Used: %i, Shared: %i' % (stats['pmap_mapped'], stats['pmap_used'], stats['pmap_shared']))

    return stats


# Config data from collectd
def configure_callback(conf):
    global RABBITMQCTL_BIN, PMAP_BIN, PIDOF_BIN, VERBOSE_LOGGING
    for node in conf.children:
        if node.key == 'RmqcBin':
            RABBITMQCTL_BIN = node.values[0]
        elif node.key == 'PmapBin':
            PMAP_BIN = node.values[0]
        elif node.key == 'PidofBin':
            PIDOF_BIN = node.values[0]
        elif node.key == 'Verbose':
            VERBOSE_LOGGING = bool(node.values[0])
        else:
            logger('warn', 'Unknown config key: %s' % node.key)


# Send info to collectd
def read_callback():
    logger('verb', 'read_callback')
    info = get_stats()

    if not info:
        logger('err', 'No information received - very bad.')
        return

    logger('verb', 'About to trigger the dispatch..')

    # send values
    for key in info:
        logger('verb', 'Dispatching %s : %i' % (key, info[key]))
        val = collectd.Values(plugin=NAME)
        val.type = 'gauge'
        val.type_instance = key
        val.values = [int(info[key])]
        val.dispatch()


# Send log messages (via collectd) 
def logger(t, msg):
    if t == 'err':
        collectd.error('%s: %s' % (NAME, msg))
    if t == 'warn':
        collectd.warning('%s: %s' % (NAME, msg))
    elif t == 'verb' and VERBOSE_LOGGING:
        collectd.info('%s: %s' % (NAME, msg))
    else:
        collectd.notice('%s: %s' % (NAME, msg))


# Runtime
collectd.register_config(configure_callback)
collectd.register_read(read_callback)
