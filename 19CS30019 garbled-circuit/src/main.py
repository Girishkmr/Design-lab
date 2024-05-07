#!/usr/bin/env python3
import logging
import os
import ot
import util
import yao
from abc import ABC, abstractmethod

logging.basicConfig(format="[%(levelname)s] %(message)s",
                    level=logging.WARNING)


class YaoGarbler(ABC):
    """An abstract class for Yao garblers (e.g. Alice)."""
    def __init__(self, circuit):
        self.circuit = circuit
        self.garbled_circuit = yao.GarbledCircuit(circuit)
        self.pbits = self.garbled_circuit.get_pbits()
        self.entry = {
            "circuit": circuit,
            "garbled_circuit": self.garbled_circuit,
            "garbled_tables": self.garbled_circuit.get_garbled_tables(),
            "keys": self.garbled_circuit.get_keys(),
            "pbits": self.pbits,
            "pbits_out": {w: self.pbits[w]
                          for w in circuit["out"]},
        }

    @abstractmethod
    def start(self):
        pass


class Alice(YaoGarbler):
    """Alice is the creator of the Yao circuit."""
    def __init__(self, circuit, oblivious_transfer=True):
        super().__init__(circuit)
        self.socket = util.GarblerSocket()
        self.ot = ot.ObliviousTransfer(self.socket, enabled=oblivious_transfer)
        self.alice_inputs = self.get_alice_inputs()

    
    def start(self):
        """Start Yao protocol."""
        to_send = {
            "circuit": self.entry["circuit"],
            "garbled_tables": self.entry["garbled_tables"],
            "pbits_out": self.entry["pbits_out"],
        }
        logging.debug(f"Sending {self.entry['circuit']['id']}")
        self.socket.send_wait(to_send)
        # self.socket.send_from(address, "EVALUATE")  # Send signal to Bob to start evaluation
        self.print()

    def print(self):
        """Print circuit evaluation."""
        circuit, pbits, keys = self.entry["circuit"], self.entry["pbits"], self.entry["keys"]
        outputs = circuit["out"]
        a_wires = circuit.get("alice", [])  # Alice's wires
        a_inputs = self.alice_inputs  # Alice's inputs
        b_wires = circuit.get("bob", [])  # Bob's wires
        b_keys = {  # map from Bob's wires to a pair (key, encr_bit)
            w: self._get_encr_bits(pbits[w], key0, key1)
            for w, (key0, key1) in keys.items() if w in b_wires
        }

        print(f"======== {circuit['id']} ========")

        # Send Alice's encrypted inputs and keys to Bob
        result = self.ot.get_result(a_inputs, b_keys)

        # Format output
        str_bits_a = ' '.join([str(a_inputs[w][1]) for w in a_wires])
        str_result = ' '.join([str(result[w]) for w in outputs])

        print(f"  Alice{a_wires} = {str_bits_a}  "
              f"Outputs{outputs} = {str_result}")

        print()

    def _get_encr_bits(self, pbit, key0, key1):
        return ((key0, 0 ^ pbit), (key1, 1 ^ pbit))

    def get_alice_inputs(self):
        """Get Alice's inputs from the user."""
        circuit = self.entry["circuit"]
        a_wires = circuit.get("alice", [])
        a_inputs = {}

        print(f"Enter Alice's inputs for circuit {circuit['id']}:")
        for wire in a_wires:
            while True:
                try:
                    value = int(input(f"Input for wire {wire}: "))
                    if value not in [0, 1]:
                        print("Input must be either 0 or 1.")
                        continue
                    break
                except ValueError:
                    print("Invalid input. Please enter 0 or 1.")

            keys = self.entry["keys"][wire]
            a_inputs[wire] = (keys[value], self.pbits[wire] ^ value)

        return a_inputs


class Bob:
    """Bob is the receiver and evaluator of the Yao circuit."""
    def __init__(self, oblivious_transfer=True):
        self.socket = util.EvaluatorSocket()
        self.ot = ot.ObliviousTransfer(self.socket, enabled=oblivious_transfer)

    
    def listen(self):
        """Start listening for Alice messages."""
        logging.info("Start listening")
        try:
            for entry in self.socket.poll_socket():
                # address, entry = self.socket.receive_with_address()
                # print("address:" , address)
                self.socket.send(True)  # Acknowledge receipt of circuit information

                # signal = self.socket.receive_from(address)  # Wait for Alice's signal
                # if signal == "EVALUATE":
                self.send_evaluation(entry)
                # else:
                    # logging.error(f"Received unknown signal: {signal}")
        except KeyboardInterrupt:
            logging.info("Stop listening")


    def send_evaluation(self, entry):
        """Evaluate yao circuit for Alice's inputs and Bob's inputs
        and send back the results.

        Args:
            entry: A dict representing the circuit to evaluate.
        """
        circuit, pbits_out = entry["circuit"], entry["pbits_out"]
        garbled_tables = entry["garbled_tables"]
        a_wires = circuit.get("alice", [])  # list of Alice's wires
        b_wires = circuit.get("bob", [])  # list of Bob's wires
        b_inputs_clear = self.get_bob_inputs(b_wires)

        print(f"Received {circuit['id']}")

        # Evaluate and send result to Alice
        self.ot.send_result(circuit, garbled_tables, pbits_out,
                            b_inputs_clear)

    def get_bob_inputs(self, b_wires):
        """Get Bob's inputs from the user."""
        b_inputs_clear = {}

        print("Enter Bob's inputs:")
        for wire in b_wires:
            while True:
                try:
                    value = int(input(f"Input for wire {wire}: "))
                    if value not in [0, 1]:
                        print("Input must be either 0 or 1.")
                        continue
                    break
                except ValueError:
                    print("Invalid input. Please enter 0 or 1.")

            b_inputs_clear[wire] = value

        return b_inputs_clear

def main(party, oblivious_transfer=True):
    
    if party == "alice":
        circuits_dir = "circuits"
        circuit_files = [f for f in os.listdir(circuits_dir) if f.endswith(".json")]

        if not circuit_files:
            print("No circuit files found in the 'circuits' directory.")
            return

        print("Available circuit files:")
        for i, file in enumerate(circuit_files, start=1):
            print(f"{i}. {file}")

        while True:
            try:
                file_choice = int(input("Enter the number of the circuit file: "))
                if file_choice < 1 or file_choice > len(circuit_files):
                    print("Invalid choice. Please try again.")
                    continue
                break
            except ValueError:
                print("Invalid input. Please enter a number.")

        circuit_file = circuit_files[file_choice - 1]
        circuits = util.parse_json(os.path.join(circuits_dir, circuit_file))
        circuit_ids = [circuit["id"] for circuit in circuits["circuits"]]

        print(f"Available circuits in {circuit_file}:")
        for i, circuit_id in enumerate(circuit_ids, start=1):
            print(f"{i}. {circuit_id}")

        while True:
            try:
                circuit_choice = int(input("Enter the number of the circuit: "))
                if circuit_choice < 1 or circuit_choice > len(circuit_ids):
                    print("Invalid choice. Please try again.")
                    continue
                break
            except ValueError:
                print("Invalid input. Please enter a number.")

        circuit = circuits["circuits"][circuit_choice - 1]
        alice = Alice(circuit, oblivious_transfer=oblivious_transfer)
        alice.start()

    elif party == "bob":
        bob = Bob(oblivious_transfer=oblivious_transfer)
        bob.listen()
    else:
        logging.error(f"Unknown party '{party}'")
    




if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run Yao protocol.")
    parser.add_argument("party", choices=["alice", "bob"], help="the yao party to run")
    parser.add_argument("--no-oblivious-transfer", action="store_true", help="disable oblivious transfer")

    args = parser.parse_args()

    main(args.party, oblivious_transfer= True)