"""Virtual interconnect: collective communication between ranks (devices, processes, machines)
over the encrypted SWP/2 transport, with an alpha-beta cost model that picks the algorithm.

This is NOT NVLink: it is a software layer over commodity links (loopback, Ethernet), thousands of
times slower in bandwidth. Its value is abstraction (the same collective over any set of devices,
across vendors and machines) and the measured choice of algorithm. See docs/INTERCONNECT.md.
"""
from .comm import Comm, launch  # noqa: F401
from .collectives import allreduce, broadcast, ALGOS  # noqa: F401
from .model import choose, fit_link, predict  # noqa: F401
