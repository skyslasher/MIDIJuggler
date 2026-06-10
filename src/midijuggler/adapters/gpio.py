"""GPIO footswitch adapter stub."""

from midijuggler.adapters.base import Adapter


class GpioAdapter(Adapter):
    protocol = "GPIO"
