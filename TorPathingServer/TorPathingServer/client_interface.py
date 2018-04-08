from shared import *
import socket
import struct
from Crypto.PublicKey import RSA
from Crypt import Crypt
from random import shuffle
from os import urandom
import struct

ROUTE_INFO_SIZE = DER_KEY_SIZE + 8


class PathingFailed(Exception):
    pass


class Connection(object):
    def __init__(self, server_ip, server_port, private_key):
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.connect((server_ip, server_port))
        self._crypt = Crypt(private_key)
        self._handshake(private_key)

    def __del__(self):
        self.close()

    def _handshake(self, private_key):
        self.send(private_key.publickey().exportKey(format='DER'))
        k = self.receive(DER_KEY_SIZE)
        self._crypt.setPublicKey(RSA.import_key(k))

    def send(self, data):
        if (self._crypt.available()):
            data = self._crypt.sign_and_encrypt(data)
        self._socket.sendall(data)

    def receive(self, size=1024):
        data = self._socket.recv(size)
        if (self._crypt.available()):
            data = self._crypt.decrypt_and_auth(data)
        return data

    def close(self):
        self.send(MSG_TYPES.CLOSE)
        self._socket.close()


class TORPathingServer(object):
    """
    TORPathingServer

    Wrapper around communication between the TOR pathing server and the clients or
    routers in the network. Supports sregistering and deregistering TOR routers
    and getting a route for a client in the network.

    args:
        server_ip (str): ip address of pathing server
        server_port (int): port number of the pathing server
    """

    def __init__(self, server_ip, server_port):
        self._server_ip = server_ip
        self._server_port = server_port
        self._router_id = None
        self._private_key = Crypt().generate_key()

    def __del__(self):
        self.unregister()

    def _newconnection(self):
        return Connection(self._server_ip, self._server_port, self._private_key)

    def _parse_route_node(self, data):
        (ip, port, pub_key) = struct.unpack("!4sI%ds" % DER_KEY_SIZE, data)
        return (socket.inet_ntoa(ip), port, RSA.import_key(pub_key))

    """
    Registers a new TOR router with the pathing server

    args:
        port (int): port that the router is listening on
        publicKey (Crypto.PublicKey.RSA instance): public key for the router

    returns: None
    """
    def register(self, port, publicKey):
        assert self._router_id is None, "Error: instance is already registered with server"
        conn = self._newconnection()
        conn.send(struct.pack("!cI%ds" % DER_KEY_SIZE, MSG_TYPES.REGISTER_SERVER, port, publicKey.exportKey(format='DER')))
        self._router_id = conn.receive()

    """
    Unregisters a TOR router from the pathing server. Note that this is done automatically when the
    object is garbage collected.

    returns: None
    """
    def unregister(self):
        if self._router_id is None:
            return
        conn = self._newconnection()
        conn.send(struct.pack("!c%ds" % len(self._router_id), MSG_TYPES.DEREGISTER_SERVER, self._router_id))
        self._router_id = None

    """
    Gets a new TOR route from the pathing server.

    returns: a list of the routers to pass through. Each router is represented
        as a 3-tuple containing in order the ip address (str), port (int), and
        the router's public key (Crypto.PublicKey.RSA instance). No assumptions
        should be made about the length of the route (although it is currently 3
        or less)
    """
    def get_route(self):
        conn = self._newconnection()
        conn.send(struct.pack("!c", MSG_TYPES.GET_ROUTE))
        route_data = conn.receive(2048)

        i = 0
        route = []
        while (i + 1) * ROUTE_INFO_SIZE <= len(route_data):
            data = route_data[i * ROUTE_INFO_SIZE:(i + 1) * ROUTE_INFO_SIZE]
            route.append(self._parse_route_node(data))
            i += 1

        return route


class TestTORPathingServer(object):
    def __init__(self, server_ip, server_port):
        self._server_ip = server_ip
        self._server_port = server_port
        self._router_id = None
        self.private_key = Crypt().generate_key()
        self.routers = []

    def __del__(self):
        self.unregister()

    def register(self, port, public_key):
        self.routers = ("127.0.0.1", port, public_key)

    def unregister(self):
        pass

    def get_route(self):
        shuffle(self.routers)
        route = []
        for r in self.routers[:3]:
            ip, port, pk = r
            c = Crypt(public_key=pk, private_key=self.private_key)
            sid = urandom(16)
            sym_key = urandom(16)
            enc_pkt = c.sign_and_encrypt("ESTB" + sid + sym_key)
            route += (enc_pkt, ip, port, pk, sym_key)

        return route
