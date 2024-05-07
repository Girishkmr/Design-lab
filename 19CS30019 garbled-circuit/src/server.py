#!/usr/bin/env python3
import logging
import ot
import socketserver
import util
import yao

logging.basicConfig(format="[%(levelname)s] %(message)s", level=logging.DEBUG)


class YaoServer(socketserver.TCPServer):
    """Server acts as the Yao circuit evaluator."""

    def __init__(self, hostname, port):
        super().__init__((hostname, port), YaoRequestHandler)

    def verify_request(self, request, client_address):
        # Implement custom verification logic if needed (e.g., check IP)
        return True


class YaoRequestHandler(socketserver.BaseRequestHandler):
    """Request handler for the Yao server."""

    def handle(self):
        logging.info("Connection from: %s", self.client_address[0])

        # Receive circuit and keys from Alice
        circuit_data = self.request.recv(1024 * 1024).decode()  # Adjust buffer size as needed
        circuit = util.parse_json(circuit_data)["circuit"]
        garbled_tables, keys = self.receive_garbled_data()

        # Receive Bob's inputs
        bob_inputs = self.receive_inputs(circuit)

        # Evaluate circuit
        pbits_out = {w: circuit["wires"][w]["pbit"] for w in circuit["out"]}
        result = yao.evaluate(circuit, garbled_tables, pbits_out, None, bob_inputs)

        # Send result back to client (either Alice or Bob)
        self.send_data(result)

    def receive_garbled_data(self):
        """Receive garbled tables and keys from the client."""
        num_tables = self.request.recv(1024).decode()
        garbled_tables = {}
        for _ in range(int(num_tables)):
            table_name, table_data = self.receive_data()
            garbled_tables[table_name] = util.parse_bytes(table_data)

        num_keys = self.request.recv(1024).decode()
        keys = {}
        for _ in range(int(num_keys)):
            wire, key_data = self.receive_data()
            keys[wire] = (key_data[: len(key_data) // 2], key_data[len(key_data) // 2:])

        return garbled_tables, keys

    def receive_inputs(self, circuit):
        """Receive Bob's inputs for the circuit."""
        num_inputs = len(
            [w for w in circuit["wires"] if circuit["wires"][w]["type"] == "BOB"]
        )
        inputs = {}
        for _ in range(num_inputs):
            wire, value = self.receive_data().decode().split()
            inputs[wire] = int(value)
        return inputs

    def send_data(self, data):
        """Send data (circuit result) to the client."""
        self.request.sendall(util.to_bytes(data).encode())

    def receive_data(self):
        """Receive data (variable length) from the client."""
        data_length = int(self.request.recv(1024).decode())
        data = self.request.recv(data_length)
        return data_length, data


if __name__ == "__main__":
    HOST, PORT = "localhost", 5000
    server = YaoServer(HOST, PORT)
    logging.info(f"Server listening on {HOST}:{PORT}")
    server.serve_forever()
