# coding=utf-8
# ------------------------------------------------------------------------------------------------------
# TDA596 - Lab 1
# server/server.py
# Input: Node_ID total_number_of_ID
# Student: Mats Högberg & Henrik Hildebrand
# ------------------------------------------------------------------------------------------------------

import traceback
import sys
import time
import json
import argparse
from threading import Thread
from random import randint

from bottle import Bottle, run, request, template
import requests


try:
    app = Bottle()

    # board keeps a mapping from id to entry.
    board = dict()

    # next_id keeps track of the next available id for an entry.
    next_id = 1

    node_id = None
    vessel_list = dict()

    # random_node_id is a randomly generated ID that is used when electing a leader in the network.
    random_node_id = None

    # next_node_address is the address to the next node in the ring.
    next_node_address = None

    # leader_address is the address of the elected leader in the network.
    leader_random_id = None
    leader_address = None

    # ------------------------------------------------------------------------------------------------------
    # BOARD FUNCTIONS
    # ------------------------------------------------------------------------------------------------------
    def add_new_element_to_store(entry_sequence, element, is_propagated_call=False):
        global board, node_id
        success = False
        try:
            board[entry_sequence] = element
            success = True
        except Exception as e:
            print(e)
        return success

    def modify_element_in_store(entry_sequence, modified_element, is_propagated_call=False):
        global board, node_id
        success = False
        try:
            board[entry_sequence] = modified_element
            success = True
        except Exception as e:
            print(e)
        return success

    def delete_element_from_store(entry_sequence, is_propagated_call=False):
        global board, node_id
        success = False
        try:
            board.pop(entry_sequence)
            success = True
        except Exception as e:
            print(e)
        return success

    # ------------------------------------------------------------------------------------------------------
    # DISTRIBUTED COMMUNICATIONS FUNCTIONS
    # ------------------------------------------------------------------------------------------------------
    def contact_vessel(vessel_ip, path, payload=None, req='POST'):
        # Try to contact another server (vessel) through a POST or GET, once
        success = False
        try:
            if 'POST' in req:
                res = requests.post('http://{}{}'.format(vessel_ip, path), data=payload)
            elif 'GET' in req:
                res = requests.get('http://{}{}'.format(vessel_ip, path))
            else:
                print('Non implemented feature!')
            # result is in res.text or res.json()
            print(res.text)
            if res.status_code == 200:
                success = True
        except Exception as e:
            print(e)
        return success

    def contact_vessel_async(vessel_ip, path, payload=None, req='POST'):
        thread = Thread(target=contact_vessel, args=(vessel_ip, path, payload, req))
        thread.daemon = True
        thread.start()

    def propagate_to_vessels(path, payload=None, req='POST'):
        global vessel_list, random_node_id

        for vessel_id, vessel_ip in vessel_list.items():
            if vessel_id != random_node_id: # don't propagate to yourself
                success = contact_vessel(vessel_ip, path, payload, req)
                if not success:
                    print("\n\nCould not contact vessel {}\n\n".format(vessel_id))
    
    def propagate_to_vessels_async(path, payload=None, req='POST'):
        # Start the propagation in a new daemon thread in order to not block the ongoing request.
        thread = Thread(target=propagate_to_vessels, args=(path, payload, req))
        thread.daemon = True
        thread.start()

    def send_to_leader(entry):
        global leader_address
        contact_vessel_async(leader_address, '/leader/add', payload={'entry': entry}, req='POST')

    # ------------------------------------------------------------------------------------------------------
    # ROUTES
    # ------------------------------------------------------------------------------------------------------
    @app.route('/')
    def index():
        global board, node_id, random_node_id, leader_address, leader_random_id
        return template('server/index.tpl', board_title='Vessel {} ({}), leader {} ({})'.format(node_id, random_node_id, leader_address, leader_random_id), board_dict=sorted(board.iteritems()), members_name_string='Mats Högberg & Henrik Hildebrand')

    @app.get('/board')
    def get_board():
        global board, node_id, random_node_id, leader_address, leader_random_id
        print(board)
        return template('server/boardcontents_template.tpl', board_title='Vessel {} ({}), leader {} ({})'.format(node_id, random_node_id, leader_address, leader_random_id), board_dict=sorted(board.iteritems()))

    @app.post('/board')
    def client_add_received():
        '''Adds a new element to the board
        Called directly when a user is doing a POST request on /board'''
        global board, node_id, next_id
        try:
            new_entry = request.forms.get('entry')
            send_to_leader(new_entry)
            return "add success"
        except Exception as e:
            print(e)
        return "add failure"

    @app.post('/board/<element_id:int>/')
    def client_action_received(element_id):
        try:
            delete = request.forms.get('delete')
            if delete == "1":
                delete_element_from_store(element_id)
                propagate_to_vessels_async("/propagate/remove/{}".format(element_id))
            else:
                entry = request.forms.get('entry')
                modify_element_in_store(element_id, entry)
                propagate_to_vessels_async("/propagate/modify/{}".format(element_id), {"entry": entry})
            return "modify/delete success"
        except Exception as e:
            print(e)
        return "modify/delete failure"

    @app.post('/propagate/<action>/<element_id:int>')
    def propagation_received(action, element_id):
        global next_id
        try:
            if action == "add":
                new_entry = request.forms.get("entry")
                add_new_element_to_store(element_id, new_entry)
            elif action == "remove":
                delete_element_from_store(element_id)
            elif action == "modify":
                modified_entry = request.forms.get("entry")
                modify_element_in_store(element_id, modified_entry)
            return "success"
        except Exception as e:
            print(e)
        return "failure"

    @app.post('/leader/add')
    def leader_add():
        global next_id
        print("leader begin")
        new_entry = request.forms.get('entry')
        add_new_element_to_store(next_id, new_entry)
        propagate_to_vessels_async("/propagate/add/{}".format(next_id), {"entry": new_entry})
        # Increment next_id to make room for the next entry.
        next_id += 1
        print("leader end")

    @app.post('/leader/modify')
    def leader_modify_delete():
        pass

    # ------------------------------------------------------------------------------------------------------
    # LEADER ELECTION
    # ------------------------------------------------------------------------------------------------------
    def initiate_leader_election():
        global random_node_id, next_node_address
        # Give the next node some time to start before initiating the leader election process.
        time.sleep(1.)
        contact_vessel_async(next_node_address, '/leader-election', payload=vessel_list, req='POST')

    @app.post('/leader-election')
    def election():
        global vessel_list, random_node_id, leader_random_id, leader_address, next_node_address
        received_vessel_list = dict(request.forms)
        if random_node_id in received_vessel_list:
            # The request that originated in this node has made its way around the entire ring.
            # This means that we now have the id and address of every other node, and we can elect a leader.
            vessel_list = received_vessel_list
            leader_random_id = str(max([int(x) for x in vessel_list.keys()]))
            leader_address = vessel_list[leader_random_id]
            print("elected leader: {} ({})".format(leader_address, leader_random_id))
        else:
            # This request originated in some other node. Add this node and pass along to next node.
            received_vessel_list[random_node_id] = vessel_list[random_node_id]
            contact_vessel_async(next_node_address, '/leader-election', payload=received_vessel_list, req='POST')

    # ------------------------------------------------------------------------------------------------------
    # EXECUTION
    # ------------------------------------------------------------------------------------------------------
    def main():
        global vessel_list, node_id, random_node_id, next_node_address, app

        port = 80
        parser = argparse.ArgumentParser(description='Your own implementation of the distributed blackboard')
        parser.add_argument('--id', nargs='?', dest='nid', default=1, type=int, help='This server ID')
        parser.add_argument('--vessels', nargs='?', dest='nbv', default=1, type=int, help='The total number of vessels present in the system')
        args = parser.parse_args()
        node_id = args.nid

        # On initialization only the address of the node and its next neighbour is known.
        node_address = '10.1.0.{}'.format(node_id)
        next_node_address = '10.1.0.{}'.format(((node_id) % args.nbv) + 1)

        # Initiate leader election in a new thread.
        random_node_id = str(randint(0, 1000))
        vessel_list[random_node_id] = node_address
        thread = Thread(target=initiate_leader_election)
        thread.daemon = True
        thread.start()

        run(app, host=vessel_list[random_node_id], port=port)

    if __name__ == '__main__':
        main()
except Exception as e:
    traceback.print_exc()
    while True:
        time.sleep(60.)
