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

from bottle import Bottle, run, request, template
import requests


try:
    app = Bottle()

    # board keeps a mapping from id to entry.
    board = dict()

    # next_id keeps track of the next available id for an entry
    next_id = 1

    node_id = None
    vessel_list = dict()

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

    def propagate_to_vessels(path, payload=None, req='POST'):
        global vessel_list, node_id

        for vessel_id, vessel_ip in vessel_list.items():
            if int(vessel_id) != node_id: # don't propagate to yourself
                success = contact_vessel(vessel_ip, path, payload, req)
                if not success:
                    print("\n\nCould not contact vessel {}\n\n".format(vessel_id))
    
    def propagate_to_vessels_async(path, payload=None, req='POST'):
        # Start the propagation in a new daemon thread in order to not block the ongoing request.
        thread = Thread(target=propagate_to_vessels, args=(path, payload, req))
        thread.daemon = True
        thread.start()

    # ------------------------------------------------------------------------------------------------------
    # ROUTES
    # ------------------------------------------------------------------------------------------------------
    @app.route('/')
    def index():
        global board, node_id
        return template('server/index.tpl', board_title='Vessel {}'.format(node_id), board_dict=sorted(board.iteritems()), members_name_string='Mats Högberg & Henrik Hildebrand')

    @app.get('/board')
    def get_board():
        global board, node_id
        print(board)
        return template('server/boardcontents_template.tpl', board_title='Vessel {}'.format(node_id), board_dict=sorted(board.iteritems()))

    @app.post('/board')
    def client_add_received():
        '''Adds a new element to the board
        Called directly when a user is doing a POST request on /board'''
        global board, node_id, next_id
        try:
            new_entry = request.forms.get('entry')
            add_new_element_to_store(next_id, new_entry)
            propagate_to_vessels_async("/propagate/add/{}".format(next_id), {"entry": new_entry})
            # Increment next_id to make room for the next entry.
            next_id += 1
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
                next_id = element_id + 1
            elif action == "remove":
                delete_element_from_store(element_id)
            elif action == "modify":
                modified_entry = request.forms.get("entry")
                modify_element_in_store(element_id, modified_entry)
            return "success"
        except Exception as e:
            print(e)
        return "failure"
        
    # ------------------------------------------------------------------------------------------------------
    # EXECUTION
    # ------------------------------------------------------------------------------------------------------
    def main():
        global vessel_list, node_id, app

        port = 80
        parser = argparse.ArgumentParser(description='Your own implementation of the distributed blackboard')
        parser.add_argument('--id', nargs='?', dest='nid', default=1, type=int, help='This server ID')
        parser.add_argument('--vessels', nargs='?', dest='nbv', default=1, type=int, help='The total number of vessels present in the system')
        args = parser.parse_args()
        node_id = args.nid
        vessel_list = dict()
        # We need to write the other vessels IP, based on the knowledge of their number
        for i in range(1, args.nbv):
            vessel_list[str(i)] = '10.1.0.{}'.format(str(i))

        try:
            run(app, host=vessel_list[str(node_id)], port=port)
        except Exception as e:
            print(e)

    if __name__ == '__main__':
        main()
except Exception as e:
    traceback.print_exc()
    while True:
        time.sleep(60.)
