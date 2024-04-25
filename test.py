"""Just a demo of the new PyVLX module."""
import asyncio
from pyvlx import PyVLX, Position


async def main(loop):
    """Demonstrate functionality of PyVLX."""
    pyvlx = PyVLX(host="VELUX_KLF_1A15", password="velux123", loop=loop)
    # Alternative:
    # pyvlx = PyVLX(host="192.168.2.127", password="velux123", loop=loop)

    # Runing scenes:
    await pyvlx.load_scenes()
    #await pyvlx.scenes["All Windows Closed"].run()
    print(*pyvlx.scenes)

    # Changing position of windows:
    await pyvlx.load_nodes()
    await pyvlx.nodes[""].rename("West")
    print(*pyvlx.nodes)
    print("done")
    #await pyvlx.nodes['Bath'].open()
    #await pyvlx.nodes['Bath'].close()
    #await pyvlx.nodes['Bath'].set_position(Position(position_percent=45))

    # Read limits of windows
    # limit = await pyvlx.nodes['Bath'].get_limitation()
    # limit.min_value
    # limit.max_value
    
    # Changing of on-off switches:
    # await pyvlx.nodes['CoffeeMaker'].set_on()
    # await pyvlx.nodes['CoffeeMaker'].set_off()

    # You can easily rename nodes:
    # await pyvlx.nodes["Window 10"].rename("Window 11")
        
    await pyvlx.disconnect()

if __name__ == '__main__':
    # pylint: disable=invalid-name
    LOOP = asyncio.get_event_loop()
    LOOP.run_until_complete(main(LOOP))
    # LOOP.run_forever()
    LOOP.close()