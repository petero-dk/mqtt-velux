#!/usr/bin/env python3
#coding:utf-8

import getopt, asyncio, json, sys, configparser, signal, logging, re
from pyvlx import PyVLX, Position, UnknownPosition, PyVLXException, OpeningDevice
from time import sleep
import paho.mqtt.client as mqtt

import platform

__usage__ = """
 usage: python mqtt-velux.py [options] configuration_file
 options are:
  -h or --help      display this help
  -v or --verbose   increase amount of reassuring messages
  -d or --debug     maximum verbosity published to mqtt topics
"""

class DebugStreamHandler(logging.StreamHandler):
    def __init__(self):
        logging.StreamHandler.__init__(self)
    def emit(self, record):
        print(record.levelname + ": " + record.getMessage())
        if not parms["debug"]:
            logging.StreamHandler.emit(self, record)
            return
        self.format(record)
        try:
            sub.publish(
                config.get("mqtt", "response") + "/mqtt-velux/system/" + record.levelname.lower(),
                record.message,
                retain=config.retain)
        except Exception as e:
            print(e)

logger = logging.getLogger('pyvlx')
logging.basicConfig(format='%(asctime)s %(message)s',handlers=[DebugStreamHandler()])
parms = {}
config = {}
sub = {}
vlx = {}
done = 0
truthy = ['true', '1', 't', 'y', 'yes']
retain = False

def on_mqtt_connect(client, userdata, flags, rc):
    logger.warning("mqtt connected with result code "+str(rc))
    client.subscribe(config.get("mqtt", "prefix") + "/#")

def on_mqtt_message(client, loop, msg):
    try:
        device = msg.topic.replace(config.get("mqtt", "prefix") + "/", '', 1).split("/", 1)
        node = device[0]
        action = device[1]
        if node == "echo":
            sub.publish(
                config.get("mqtt", "response") + "/echo",
                msg.payload.decode('utf-8'),
                retain=config.retain)
            return
        payload = msg.payload.decode('utf-8').lower()
        logger.info("message received @%s: setting %s via %s to %s " % (msg.topic, node, action, payload))
        if not node in vlx.nodes:
            raise Exception("unknown node: " + node)
        
        if action == "closed":
            payload = "0" if payload in truthy else "100"

                
        logger.info("setting position pre @%s: %s" % (node, payload))
            
        asyncio.run_coroutine_threadsafe(vlx_set_position(node, payload), loop)
    except Exception as msg:
        logger.error(msg)

async def vlx_set_position(node, pos):
    if pos == "close":
        pos = "closed"
    pct = 100 if pos == "open" else 0 if pos == "closed" else (100 - int(pos)) if pos.isdigit() else None
    if pct is None:
        logger.error("invalid position for @%s: %s" % (node, pos))
        return
    logger.info("setting position @%s: %s" % (node, pct))
    await vlx.nodes[node].set_position(Position(position_percent=pct), wait_for_completion=False)


async def on_device_updated(node):
    if not isinstance(node, OpeningDevice):
        return
    if node.position == UnknownPosition():
        logger.info("device position unknown: %s" % node.name)
        return
    pct = node.position.position_percent
    logger.info("device updated: %s = %s" % (node.name, pct))
    sub.publish(
        config.get("mqtt", "response") + "/" + node.name.replace("-", "/") + "/position",
        str(100 - pct),
        retain=config.retain)
    
    closed = str(pct == 0)
    sub.publish(
        config.get("mqtt", "response") + "/" + node.name.replace("-", "/") + "/closed",
        closed,
        retain=config.retain)

async def main(loop):
    global parms, config, logger, sub, vlx, done
    logger.setLevel(logging.ERROR)
    try:
        opts, args = getopt.getopt(sys.argv[1:], "dhv", ['debug', 'help', 'verbose'])
    except getopt.error as msg:
        print(msg)
        print(__usage__)
        return 1
    # process options
    parms["debug"] = False
    for o, a in opts:
        if o == '-h' or o == '--help':
            print(__usage__)
            return 0
        if o == '-d' or o == '--debug':
            parms["debug"] = True
            logger.setLevel(logging.DEBUG)
        elif o == '-v' or o == '--verbose':
            #if logger.getEffectiveLevel() == logging.ERROR:
            #    logger.setLevel(logging.WARNING)
            #elif logger.getEffectiveLevel() == logging.WARNING:
            logger.setLevel(logging.INFO)
            #else:
            #    logger.setLevel(logging.DEBUG)
    # check arguments
    if len(args) < 1:
        logger.error("at least 1 argument required")
        logger.error(__usage__)
        return 2
    # read config
    config = configparser.ConfigParser()
    config.optionxform = str
    config.read(args.pop(0))
    config.retain = config.get("mqtt", "retain") in truthy

    # mqtt
    sub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, userdata=loop)
    sub.on_connect = on_mqtt_connect
    sub.on_message = on_mqtt_message
    if eval(config.get("mqtt", "auth")):
        sub.username_pw_set(config.get("mqtt", "user"), config.get("mqtt", "password"))
    sub.connect(config.get("mqtt", "hostname"), eval(config.get("mqtt", "port")), 60)
    sub.loop_start()

    # velux
    if not done:
        vlx = PyVLX(host=config.get("velux", "hostname"), password=config.get("velux", "password"), loop=loop)
        nodes = []
        await vlx.load_nodes()
        for n in vlx.nodes:
            n.register_device_updated_cb(on_device_updated)
            logger.info(str(n))
            nodes.append(n.name)
        nodes = ", ".join(nodes)
        logger.info("started: " + nodes)
        sub.publish(
            config.get("mqtt", "response") + "/mqtt-velux/system/message",
            "started: " + nodes,
            retain=config.retain)

    logger.info("looping...")
    while not done:
        for n in vlx.nodes:
            n.register_device_updated_cb(on_device_updated)
            logger.info(str(n))
            s = await vlx.nodes[n.name].get_limitation()
            

            sub.publish(
                config.get("mqtt", "response") + "/" + n.name.replace("-", "/") + "/rain",
                s.min_value,
                retain=config.retain)
            
            on_device_updated(n)
        await asyncio.sleep(60)
        

    logger.info("done.")
    sub.loop_stop()
    await vlx.disconnect()

    sub.publish(
        config.get("mqtt", "response") + "/mqtt-velux/system/message",
        "ended.",
        retain=config.retain)
    logger.info("ended.")

def signal_handler(signum, frame):
    global done
    signame = signal.Signals(signum).name
    logger.error("%s received" % signame)
    done = 1

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)
    
    if platform.system() == 'Linux':
        signal.signal(signal.SIGHUP, signal_handler)
    
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        LOOP = asyncio.get_event_loop()
        LOOP.run_until_complete(main(LOOP))
    except Exception as msg:
        logger.error(msg)
        raise
    LOOP.close()
